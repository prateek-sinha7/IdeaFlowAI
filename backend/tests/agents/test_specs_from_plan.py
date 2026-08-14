"""FIX-266 — engine._specs_from_plan is the SINGLE source for rebuilding an `agents`
list from a compiled plan's steps, and it MUST overlay the composer's display_name.

Regression context: execute() applied `dataclasses.replace(spec, name=s.display_name)`;
resume_run() and _derive_offset() rebuilt the same list from a bare
`[load_agent_spec(s.agent_id) for s in compiled.steps]` — no overlay. A resumed composed
workflow reported every step under its template's name ("Custom Agent" x N) instead of
the composer's labels ("Brief Builder", "Writer", ...). `_specs_from_plan` is the fix:
one implementation, three callers, so the overlay cannot silently drop out of one of
them again.

Four layers, cheapest first:
  1. Unit — `_specs_from_plan` against constructed Step objects (no I/O).
  2. Integration — the same function against the REAL compiled `sample_subagents_parallel`
     manifest (a real, disk-backed custom workflow), pinning today's actual names.
  3. Source guard — resume_run/_derive_offset must call `_specs_from_plan`, not a bare
     `load_agent_spec` comprehension. Fails loudly if a future edit reintroduces the
     divergence, even before any behavioral test would catch it.
  4. Behavioral — a real call through `resume_run()` itself, against an in-memory
     SQLite `workflow_runs` row, proving the fix end-to-end rather than just at the
     helper/source level.

No LLM. Layers 1-3 are offline/no DB; layer 4 uses an ephemeral in-memory SQLite.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from agents.execution_engine.engine import ExecutionEngine, compile_for_run
from agents.workflows.plan import Step

_ENGINE_PY = (
    Path(__file__).resolve().parents[2] / "agents" / "execution_engine" / "engine.py"
)


# ---------------------------------------------------------------------------
# 1. Unit — _specs_from_plan against constructed Steps
# ---------------------------------------------------------------------------


def test_specs_from_plan_overlays_display_name():
    """A step with a display_name gets it grafted onto the loaded spec's .name."""
    engine = ExecutionEngine()
    steps = [
        Step(agent_id="custom-agent:brief", display_name="Brief Builder"),
        Step(agent_id="custom-agent:writer", display_name="Writer"),
    ]

    specs = engine._specs_from_plan(steps)

    assert [s.name for s in specs] == ["Brief Builder", "Writer"]


def test_specs_from_plan_falls_back_to_template_name_when_display_name_is_empty():
    """No display_name (e.g. a built-in registry agent) -> the loaded spec is untouched."""
    engine = ExecutionEngine()
    steps = [Step(agent_id="domain-analyst")]  # a real, non-template registry agent

    specs = engine._specs_from_plan(steps)

    assert specs[0].name != ""
    assert specs[0].name != "Brief Builder"  # sanity: not accidentally overlaid


def test_specs_from_plan_never_mutates_agent_id():
    """The overlay touches ONLY .name — agent_id (and therefore dispatch) is untouched."""
    engine = ExecutionEngine()
    steps = [Step(agent_id="custom-agent:writer", display_name="Writer")]

    specs = engine._specs_from_plan(steps)

    assert specs[0].id == "custom-agent:writer"


def test_specs_from_plan_empty_list_returns_empty_list():
    engine = ExecutionEngine()
    assert engine._specs_from_plan([]) == []


# ---------------------------------------------------------------------------
# 2. Integration — the real, disk-backed sample_subagents_parallel manifest
# ---------------------------------------------------------------------------


def test_specs_from_plan_matches_real_composed_manifest():
    """Pins today's actual sample_subagents_parallel display names (spec 012 nesting
    fixture) — a real custom workflow, not a synthetic Step. If this manifest's node
    names ever change, update this assertion; if it goes back to reporting "Custom
    Agent", the overlay broke."""
    engine = ExecutionEngine()
    compiled = compile_for_run("sample_subagents_parallel")
    assert compiled.steps, "fixture manifest compiled to zero steps — update the fixture reference"

    specs = engine._specs_from_plan(compiled.steps)
    names = {s.id: s.name for s in specs}

    assert names == {
        "custom-agent:apple": "Apple Writer",
        "custom-agent:ball": "Ball Writer",
        "custom-agent:cat": "Cat Writer",
        "custom-agent:page": "Page Builder",
    }
    assert "Custom Agent" not in names.values(), (
        "a composed step reported the TEMPLATE's name instead of its display_name — "
        "this is the exact FIX-266 regression"
    )


# ---------------------------------------------------------------------------
# 3. Source guard — resume_run / _derive_offset must call the shared helper
# ---------------------------------------------------------------------------


def test_resume_paths_call_the_shared_helper_not_a_bare_comprehension():
    """FIX-266 ratchet: resume_run and _derive_offset's plan-rebuild sites must read
    `self._specs_from_plan(compiled.steps)`. A future edit reintroducing the bare
    `[load_agent_spec(s.agent_id) for s in compiled.steps]` pattern at either site would
    silently drop the display_name overlay again — this fails the build instead."""
    source = _ENGINE_PY.read_text(encoding="utf-8")

    banned = re.compile(r"\[\s*load_agent_spec\(s\.agent_id\)\s+for\s+s\s+in\s+compiled\.steps\s*\]")
    assert not banned.search(source), (
        "engine.py contains a bare `[load_agent_spec(s.agent_id) for s in "
        "compiled.steps]` — this is the FIX-266 regression pattern (no display_name "
        "overlay). Use `self._specs_from_plan(compiled.steps)` instead."
    )

    calls = source.count("self._specs_from_plan(compiled.steps)")
    assert calls >= 3, (
        f"expected _specs_from_plan(compiled.steps) at all 3 known call sites "
        f"(execute, resume_run, _derive_offset); found {calls}. If a call site was "
        f"legitimately removed, lower this bound deliberately — do not delete the test."
    )


# ---------------------------------------------------------------------------
# 4. Behavioral — resume_run() itself, against a real composed-workflow row
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_run_builds_display_names_for_a_real_composed_workflow():
    """FIX-266, behavioral: resume_run() on a `sample_subagents_parallel` row (no
    static registry membership, so it MUST take the plan-fallback branch at
    engine.py:8793) reaches the resume-offset call with an `agents` list carrying
    the composer's display_name — not the template's "Custom Agent" name.
    Complements the source-guard test above with a live call through resume_run()
    itself, using the same fixture and expected names pinned in layer 2."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import app.models  # noqa: F401 — register models on Base.metadata
    import app.models.database as db_mod
    from app.models.database import Base
    from app.models.workflow import WorkflowRun

    db = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=db)
    session = sessionmaker(bind=db, autocommit=False, autoflush=False)()
    session.add(
        WorkflowRun(
            id="resume-fixture-run", user_id="u1", owner_id="u1", workspace_id=None,
            status="running", type="sample_subagents_parallel", input="topic",
        )
    )
    session.commit()

    orig_session_local = db_mod.SessionLocal
    db_mod.SessionLocal = sessionmaker(
        bind=db, autocommit=False, autoflush=False, expire_on_commit=False
    )

    class _ReachedOffset(Exception):
        pass

    captured: dict = {}

    async def _spy_offset(run_id, user_id, session_id, pipeline_type, agents):
        captured["agents"] = agents
        raise _ReachedOffset()

    engine = ExecutionEngine()
    engine._compute_resume_offset = _spy_offset  # type: ignore[assignment]

    try:
        try:
            await engine.resume_run("resume-fixture-run")
        except _ReachedOffset:
            pass

        assert "agents" in captured, "resume_run never reached the offset call"
        names = {s.id: s.name for s in captured["agents"]}
        assert names == {
            "custom-agent:apple": "Apple Writer",
            "custom-agent:ball": "Ball Writer",
            "custom-agent:cat": "Cat Writer",
            "custom-agent:page": "Page Builder",
        }
        assert "Custom Agent" not in names.values(), (
            "resume_run reported the TEMPLATE's name instead of its display_name — "
            "the exact FIX-266 regression, this time via the real resume path"
        )
    finally:
        db_mod.SessionLocal = orig_session_local
        session.close()
