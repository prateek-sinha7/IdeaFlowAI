"""tests/agents/test_task_list_gate_lineage.py — RESUME-15 gate-Edit lineage.

A user edit to the versioned ``task_list`` artifact rides the EXISTING gate-Edit
mechanism (WR-03: ``edited_content`` via ``POST /{id}/gate`` only) — it mints a
NEW ``task_list`` version through the sole ``_dual_write_artifact`` writer, and
``_latest_typed_content`` (max-version, F5) is what the strategy re-parses. The
one RESUME-15 gap this suite pins: the edited version must record ``derived_from``
lineage back to the version it supersedes, at BOTH the declared gate-edit site
(``_apply_declared_gate_edit``) AND the inline post-step review-gate site
(``_gate_edited`` in ``_run_agent``). No new table / endpoint / status — the only
substrate is the existing versioned ``task_list`` artifact (12-era lock).

Offline-safe: no Bedrock / Postgres / Chromium. The inline-path test reuses the
proven direct ``_run_agent`` drive harness from ``test_redo_gate_safety``.
"""

from __future__ import annotations

import pytest

# The harness import sets RUNS_ROOT to a temp dir + forces the InMemory
# checkpointer BEFORE app.core.config loads — keep these imports first.
from tests.agents.test_redo_gate_safety import (  # noqa: E402
    _EngineHarness,
    _drive_agent,
    _make_ectx,
)
from tests.agents._scripted_model import ScriptedFakeChatModel, _ScriptedTurn  # noqa: E402

from agents.execution_engine.context import ExecutionContext  # noqa: E402
from agents.execution_engine.engine import ExecutionEngine  # noqa: E402

# ``prototype-plan`` is the agent whose _artifact_kind_for → "task_list" (the kind
# whose gate-edit lineage RESUME-15 closes). Keyed structurally, not by literal.
_PLAN_AGENT = "prototype-plan"


def _engine() -> ExecutionEngine:
    return ExecutionEngine()


async def _seed_v1_task_list(engine: ExecutionEngine, ectx: ExecutionContext) -> None:
    await engine._dual_write_artifact(
        ectx,
        producer_agent=_PLAN_AGENT,
        producer_step=_PLAN_AGENT,
        content="ORIGINAL PLAN",
        kind="task_list",
        location=f"artifact_refs/{_PLAN_AGENT}",
    )


def _task_list_refs(ectx: ExecutionContext):
    return sorted(
        (
            r
            for r in ectx.artifacts.tree(ectx.run_id)
            if r.producer_agent == _PLAN_AGENT and r.kind == "task_list"
        ),
        key=lambda r: r.version,
    )


@pytest.mark.asyncio
async def test_declared_gate_edit_stamps_derived_from_on_task_list() -> None:
    """The DECLARED gate-edit path (`_apply_declared_gate_edit`) mints a v2
    task_list whose ``derived_from`` == the v1 ref id, and ``_latest_typed_content``
    returns the edited (max-version) content."""
    engine = _engine()
    ectx = ExecutionContext(run_id="lineage-declared", owner_id="anon")

    await _seed_v1_task_list(engine, ectx)
    v1 = _task_list_refs(ectx)
    assert [r.version for r in v1] == [1]

    class _Spec:
        id = _PLAN_AGENT
        name = "Prototype Plan"

    results = [{"agent_id": _PLAN_AGENT, "output": "ORIGINAL PLAN"}]
    await engine._apply_declared_gate_edit("EDITED PLAN", results, [_Spec()], ectx)

    refs = _task_list_refs(ectx)
    assert [r.version for r in refs] == [1, 2], (
        f"expected v1 + edited v2, got versions {[r.version for r in refs]}"
    )
    assert refs[1].derived_from == refs[0].id, (
        "declared gate-edit did NOT stamp derived_from lineage to the prior "
        "task_list version (RESUME-15 gap)"
    )
    assert engine._latest_typed_content(ectx, _PLAN_AGENT) == "EDITED PLAN"


@pytest.mark.asyncio
async def test_inline_gate_edited_stamps_derived_from_on_task_list() -> None:
    """The INLINE post-step review-gate edit path (`_gate_edited` in `_run_agent`)
    mints a v2 task_list whose ``derived_from`` == the v1 (model-produced) ref id."""
    from agents.loader import load_agent_spec

    spec = load_agent_spec(_PLAN_AGENT)

    async def _fake_gate(*, pipeline_run_id, agent_id, agent_name, output, **kwargs):
        yield {
            "type": "review_gate_ready",
            "data": {"gate_key": f"{pipeline_run_id}:{agent_id}"},
        }
        yield {"type": "_gate_edited", "edited_content": "EDITED PLAN"}

    def _model_for(agent_id, idx):
        return ScriptedFakeChatModel([_ScriptedTurn(texts=["ORIGINAL PLAN. "], usage=(5, 3))])

    with _EngineHarness(_model_for) as h:
        h.engine._run_review_gate = _fake_gate  # type: ignore[assignment]
        ectx = _make_ectx("lineage-inline", gate_agent_ids=[spec.id])
        results: list[dict] = []
        await _drive_agent(h.engine, spec, ectx, results, [spec])

    refs = _task_list_refs(ectx)
    assert [r.version for r in refs] == [1, 2], (
        f"expected v1 (model) + edited v2, got versions {[r.version for r in refs]}"
    )
    assert refs[1].derived_from == refs[0].id, (
        "inline gate-edit did NOT stamp derived_from lineage to the prior "
        "task_list version (RESUME-15 gap)"
    )
    assert h.engine._latest_typed_content(ectx, spec.id) == "EDITED PLAN"
