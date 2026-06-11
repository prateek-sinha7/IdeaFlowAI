"""SC-001 WAVE-SCHEDULER PROOF — a brand-new wave workflow (``sample_wave``) runs from a
manifest + AGENT.md ONLY, with ZERO engine edits authored FOR IT (12-01 / WAVE-01/02/03).

``CLAUDE.md`` Core Value / SC-001:

    "A brand-new custom workflow can replicate ``prototype`` by manifest + AGENT.md
     only — with zero engine edits."

The ``sample_wave`` manifest lives at the REAL manifest home
(``agents/workflows/sample_wave/``) so ``compile_for_run`` loads it with ZERO engine
edit (the 11-05 sample_fanout / 09-04 sample_brownfield precedent). It declares a
``wave_scheduler`` step sourcing a structured ``json_tasks`` plan of 4 tasks:
  * t1 → part_a.txt, t2 → part_b.txt (no deps, disjoint targets → WAVE 1, 2 parallel
    workers);
  * t3 → part_c.txt depends_on [t1], t4 → part_d.txt depends_on [t2] → WAVE 2.
merged ``copy_disjoint`` — using ONLY already-registered capabilities (``wave_scheduler``
strategy + ``json_tasks`` parser + ``spawn_subagents`` tool + ``copy_disjoint`` merge).
The worker AGENT.md specs are test-scoped fixtures (the sc001 precedent).

The test drives the workflow end-to-end OFFLINE (scripted model, no network) binding a
REAL in-memory SQLite ScopedStore (RESEARCH Open Q3) so ``wave_runs`` / ``subagent_runs``
rows persist, and asserts:
  (1) >= 2 ``wave_runs`` rows with distinct ``wave_index`` and terminal ``completed``;
  (2) >= 2 ``subagent_runs`` rows for a single wave (the 2 parallel workers in wave 1);
  (3) the merged base contains every task's file (part_a/b/c/d.txt);
  (4) wave lifecycle events (wave_started/wave_completed) fired;
  (5) SC-001: the kernel names NO workflow (``grep sample_wave
      backend/agents/execution_engine/`` == 0) and the proof artifacts live OUTSIDE the
      engine package.
"""

from __future__ import annotations

import json as _json
import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Iterator

import frontmatter  # type: ignore[import-untyped]
import pytest
from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from tests.agents._scripted_model import (  # noqa: E402
    _RUNS_ROOT,
    ScriptedFakeChatModel,
    _ScriptedTurn,
)

# The manifest lives at the REAL home; the AGENT.md worker specs are test-scoped.
_MANIFEST_HOME = Path(__file__).resolve().parents[2] / "agents" / "workflows"
_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "sample_wave"
_FIXTURE_ID = "sample_wave"
_PART_RE = re.compile(r"part_([a-d])\.txt")

# The 4-task JSON plan the scripted planner emits (fenced ```json block). t1/t2 have no
# deps + disjoint targets (wave 1, parallel); t3 deps t1, t4 deps t2 (wave 2).
_TASK_PLAN = (
    "Here is the plan:\n\n```json\n"
    + _json.dumps(
        {
            "tasks": [
                {"id": "t1", "title": "Write A", "body": "Write the file part_a.txt with the content 'a'.", "targets": ["part_a.txt"]},
                {"id": "t2", "title": "Write B", "body": "Write the file part_b.txt with the content 'b'.", "targets": ["part_b.txt"]},
                {"id": "t3", "title": "Write C", "body": "Write the file part_c.txt with the content 'c'.", "targets": ["part_c.txt"], "depends_on": ["t1"]},
                {"id": "t4", "title": "Write D", "body": "Write the file part_d.txt with the content 'd'.", "targets": ["part_d.txt"], "depends_on": ["t2"]},
            ]
        },
        indent=2,
    )
    + "\n```\n"
)


class _PartWritingModel(ScriptedFakeChatModel):
    """A scripted model whose worker turn writes the ``part_X.txt`` named in its input."""

    def __init__(self, turns, *, is_worker: bool = False, **kwargs: Any) -> None:
        super().__init__(turns, **kwargs)
        object.__setattr__(self, "_is_worker", is_worker)

    def _stream(
        self, messages: list, stop: Any = None, run_manager: Any = None, **kwargs: Any
    ) -> Iterator[ChatGenerationChunk]:
        if not self._is_worker:
            yield from super()._stream(messages, stop, run_manager, **kwargs)
            return
        blob = "\n".join(str(getattr(m, "content", "")) for m in messages)
        task_blocks = re.findall(
            r"=== CURRENT TASK ===\n(.*?)\n=== END CURRENT TASK ===", blob, re.DOTALL
        )
        scope = task_blocks[-1] if task_blocks else blob
        matches = list(_PART_RE.finditer(scope))
        already_wrote = bool(self._call_index)
        object.__setattr__(self, "_call_index", self._call_index + 1)
        if not matches or already_wrote:
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content="Done.",
                    usage_metadata={"input_tokens": 4, "output_tokens": 2, "total_tokens": 6},
                    chunk_position="last",
                )
            )
            return
        m = matches[-1]
        fname = m.group(0)
        letter = m.group(1)
        yield ChatGenerationChunk(
            message=AIMessageChunk(
                content=f"Writing {fname}. ",
                tool_call_chunks=[
                    {
                        "name": "write_file",
                        "args": _json.dumps({"file_path": fname, "content": f"{letter}\n"}),
                        "id": f"c_w_{letter}",
                        "index": 0,
                    }
                ],
                usage_metadata={"input_tokens": 12, "output_tokens": 6, "total_tokens": 18},
                chunk_position="last",
            )
        )


def _load_fixture_specs():
    from agents.loader import AgentSpec

    specs = []
    for agent_dir in sorted(_FIXTURE_DIR.iterdir()):
        agent_file = agent_dir / "AGENT.md"
        if not agent_file.is_file():
            continue
        post = frontmatter.loads(agent_file.read_text(encoding="utf-8"))
        md = post.metadata
        specs.append(
            AgentSpec(
                id=md["id"],
                name=md["name"],
                role=md["role"],
                pipeline_type=md["pipeline_type"],
                order=int(md["order"]),
                max_tokens=int(md["max_tokens"]),
                prompt_body=post.content,
                tools=list(md.get("tools", []) or []),
                guardrails=list(md.get("guardrails", []) or []),
                context_from=list(md.get("context_from", []) or []),
                produces=list(md.get("produces", []) or []),
                consumes=list(md.get("consumes", []) or []),
            )
        )
    specs.sort(key=lambda s: s.order)
    return specs


def _scripts_for(agent_id: str):
    if agent_id == "sample-wave-plan":
        return [_ScriptedTurn(texts=[_TASK_PLAN], usage=(20, 16))]
    return [_ScriptedTurn(texts=[f"{agent_id} default."], usage=(5, 3))]


async def _drive_wave() -> tuple[list[dict], dict]:
    """Drive the sample_wave workflow end-to-end offline. Returns (events, probe)."""
    import agents.execution_engine.engine as engine_mod
    import agents.factory as factory_mod
    import agents.registry as registry_mod
    from agents.execution_engine.engine import ExecutionEngine
    from agents.loader import _SPEC_CACHE
    from agents.workflows.manifest import load_manifest

    import app.models  # noqa: F401 — register models on Base.metadata
    from app.models.database import Base
    from agents.authz import ScopedStore

    from app.core.config import settings as _settings
    _settings.RUNS_ROOT = _RUNS_ROOT

    # A real in-memory SQLite store so wave_runs / subagent_runs persist (Open Q3).
    db = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=db)
    Session = sessionmaker(bind=db, autocommit=False, autoflush=False)
    session = Session()

    specs = _load_fixture_specs()
    spec_ids = [s.id for s in specs]
    probe: dict = {"session": session}

    _orig_compile = engine_mod.compile_for_run
    _orig_resolve_alias = engine_mod.resolve_alias
    _CAPABILITY_REGISTRY = engine_mod._CAPABILITY_REGISTRY
    _WORKFLOW_COMPILER = engine_mod._WORKFLOW_COMPILER

    def _patched_compile(pipeline_type, _orig=_orig_compile):
        if pipeline_type == _FIXTURE_ID:
            manifest = load_manifest(_FIXTURE_ID, _MANIFEST_HOME)
            compiled = _WORKFLOW_COMPILER.compile(manifest, _CAPABILITY_REGISTRY)
            compiled.clarify.mode = "off"
            return compiled
        compiled = _orig(pipeline_type)
        compiled.clarify.mode = "off"
        return compiled

    def _patched_resolve_alias(pipeline_type, _orig=_orig_resolve_alias):
        if pipeline_type == _FIXTURE_ID:
            return _FIXTURE_ID
        return _orig(pipeline_type)

    _orig_get_pipeline_agents = registry_mod.get_pipeline_agents

    def _patched_get_pipeline_agents(pipeline_type, _orig=_orig_get_pipeline_agents):
        if pipeline_type == _FIXTURE_ID:
            return list(specs)
        return _orig(pipeline_type)

    _orig_create_runner = factory_mod.create_runner
    _orig_engine_create_runner = getattr(engine_mod, "create_runner", None)

    def _patched_create_runner(agent_id, ctx, **kw):
        ctx.model = _PartWritingModel(
            _scripts_for(agent_id), is_worker=(agent_id == "sample-wave-worker")
        )
        return _orig_create_runner(agent_id, ctx, **kw)

    # Bind a session-backed ScopedStore into the engine so wave_runs persist offline.
    _orig_scoped_store = engine_mod.ScopedStore

    def _patched_scoped_store(*a, **k):
        k.setdefault("session", session)
        return _orig_scoped_store(*a, **k)

    for s in specs:
        _SPEC_CACHE[s.id] = s

    engine_mod.compile_for_run = _patched_compile
    engine_mod.resolve_alias = _patched_resolve_alias
    registry_mod.get_pipeline_agents = _patched_get_pipeline_agents
    factory_mod.create_runner = _patched_create_runner
    engine_mod.create_runner = _patched_create_runner
    engine_mod.ScopedStore = _patched_scoped_store

    engine = ExecutionEngine()

    async def _fake_run_planner(user_message, pipeline_run_id, model_id, cancel_event, ptype="custom", **kwargs):
        return engine._default_planning_context(user_message), "PROCEED"

    engine._run_planner = _fake_run_planner  # type: ignore[assignment]

    async def _noop_store(*a, **k):
        return "artifact-id"

    engine._store.store = _noop_store  # type: ignore[assignment]

    async def _noop_gate(*a, **k):
        return
        yield  # pragma: no cover

    engine._run_review_gate = _noop_gate  # type: ignore[assignment]

    events: list[dict] = []
    run_id = f"sw-{uuid.uuid4().hex[:8]}"
    sandbox_root: Path | None = None
    try:
        async for ev in engine.execute(
            agents=list(specs),
            user_message="Run the wave workflow.",
            pipeline_run_id=run_id,
            pipeline_type=_FIXTURE_ID,
            user_id="sw-user",
            gate_agent_ids=[],
        ):
            events.append(ev)
        from app.agents.sandbox import RunSandbox

        sandbox_root = RunSandbox("sw-user", run_id).root
    finally:
        engine_mod.compile_for_run = _orig_compile
        engine_mod.resolve_alias = _orig_resolve_alias
        registry_mod.get_pipeline_agents = _orig_get_pipeline_agents
        factory_mod.create_runner = _orig_create_runner
        if _orig_engine_create_runner is not None:
            engine_mod.create_runner = _orig_engine_create_runner
        engine_mod.ScopedStore = _orig_scoped_store
        for sid in spec_ids:
            _SPEC_CACHE.pop(sid, None)
    probe["sandbox_root"] = sandbox_root
    probe["run_id"] = run_id
    return events, probe


@pytest.mark.asyncio
async def test_sample_wave_runs_multiple_waves_and_persists_wave_runs() -> None:
    """>=2 wave_runs (distinct wave_index, terminal) + >=2 workers in wave 1 + merged files."""
    from app.models.wave_run import WaveRun
    from app.models.subagent_run import SubagentRun

    events, probe = await _drive_wave()
    assert events, "sample_wave produced no events (drove nothing / errored)"
    errors = [e for e in events if e.get("type") == "error"]
    assert not errors, f"sample_wave errored: {errors}"

    session = probe["session"]
    run_id = probe["run_id"]

    # (1) >= 2 wave_runs rows with distinct wave_index, all terminal 'completed'.
    wave_rows = (
        session.query(WaveRun)
        .filter(WaveRun.run_id == run_id)
        .order_by(WaveRun.wave_index.asc())
        .all()
    )
    assert len(wave_rows) >= 2, f"expected >=2 wave_runs rows, saw {len(wave_rows)}"
    indices = [r.wave_index for r in wave_rows]
    assert len(set(indices)) == len(indices), f"wave_index not distinct: {indices}"
    assert all(r.status == "completed" for r in wave_rows), (
        f"a wave did not reach terminal completed: {[r.status for r in wave_rows]}"
    )

    # (2) >= 2 subagent_runs rows for a single wave (the 2 parallel workers in wave 1).
    sub_rows = session.query(SubagentRun).filter(SubagentRun.parent_run_id == run_id).all()
    assert len(sub_rows) >= 4, f"expected >=4 subagent_runs (4 tasks), saw {len(sub_rows)}"
    # Wave 1 fans out exactly the 2 disjoint root tasks (t1,t2).
    assert wave_rows[0].wave_index == 0
    assert len(wave_rows[0].task_ids) >= 2, (
        f"wave 1 should fan >=2 parallel workers, saw task_ids={wave_rows[0].task_ids}"
    )

    # (3) The merged base contains every task's file (part_a/b/c/d.txt).
    sandbox_root = probe["sandbox_root"]
    assert sandbox_root is not None and sandbox_root.is_dir(), "run sandbox missing on disk"
    produced = {
        p.name for p in sandbox_root.rglob("*.txt")
        if _PART_RE.fullmatch(p.name) and ".worktrees" not in p.parts
    }
    assert produced == {"part_a.txt", "part_b.txt", "part_c.txt", "part_d.txt"}, (
        f"the wave workers did not produce all 4 distinct merged files: {sorted(produced)}"
    )

    # (4) Wave lifecycle events fired (>=2 started/completed pairs).
    started = [e for e in events if e.get("type") == "wave_started"]
    completed = [e for e in events if e.get("type") == "wave_completed"]
    assert len(started) >= 2, f"expected >=2 wave_started events, saw {len(started)}"
    assert len(completed) >= 2, f"expected >=2 wave_completed events, saw {len(completed)}"
    assert not any(e.get("type") == "wave_failed" for e in events)
    assert not any(e.get("type") == "merge_conflict" for e in events), (
        "copy_disjoint reported a conflict over disjoint files"
    )

    session.close()


def test_sample_wave_runs_on_registered_capabilities_only() -> None:
    """SC-001 (a): the workflow runs PURELY off already-registered capabilities."""
    from agents.capabilities.registry import CapabilityRegistry, discover

    discover()
    reg = CapabilityRegistry()
    assert reg.is_registered("strategy", "wave_scheduler")
    assert reg.is_registered("task_parser", "json_tasks")
    assert reg.is_registered("tool", "spawn_subagents")
    assert reg.is_registered("merge", "copy_disjoint")

    manifest_text = (_MANIFEST_HOME / _FIXTURE_ID / "workflow.yaml").read_text(encoding="utf-8")
    assert "strategy: wave_scheduler" in manifest_text
    assert "parser: json_tasks" in manifest_text
    assert "spawn_subagents: true" in manifest_text


def test_sample_wave_kernel_names_no_workflow() -> None:
    """SC-001 (b): the kernel contains NO reference to sample_wave by name (INV-1)."""
    repo_root = Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    )
    engine_pkg = repo_root / "backend" / "agents" / "execution_engine"
    hits = subprocess.run(
        ["grep", "-rl", "sample_wave", str(engine_pkg)],
        capture_output=True, text=True,
    ).stdout.strip()
    assert hits == "", (
        f"the kernel names the workflow sample_wave (INV-1 violation) in:\n{hits}"
    )

    proof_artifacts = [
        "backend/agents/workflows/sample_wave/workflow.yaml",
        "backend/tests/agents/fixtures/sample_wave/sample-wave-plan/AGENT.md",
        "backend/tests/agents/fixtures/sample_wave/sample-wave-worker/AGENT.md",
        "backend/tests/agents/test_sample_wave_workflow.py",
    ]
    for rel in proof_artifacts:
        assert (repo_root / rel).is_file(), f"missing proof artifact: {rel}"
        assert not rel.startswith("backend/agents/execution_engine/"), (
            f"SC-001 proof artifact {rel} lives under the engine package"
        )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-q"]))
