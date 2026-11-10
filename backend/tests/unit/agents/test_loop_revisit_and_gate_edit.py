"""Loop-revisit reuse bypass + approve-with-edits propagation.

Bug 1 (run 8d6245dc): a conditional-route loop-back re-dispatched ``fix`` and the
gate step ``verify`` with an UNCHANGED upstream hash, so ``_find_reused_completion``
served pass-1's completion (``step_reused``) and the loop never re-executed.
Bug 2: ``POST /gate`` ``edited_content`` on a declared post-step human gate was
dropped; the step's ``.agents/NN-<agent>.md`` kept the pre-edit text.
"""

from __future__ import annotations

import asyncio

import pytest

from agents.artifacts.graph import ArtifactGraph
from agents.execution_engine.engine import ExecutionEngine
from tests.unit.agents.test_step_retry import (
    _collect,
    _FakeCtx,
    _FakeStrategy,
    _RunEventRow,
    _step,
)


class _LiveStore:
    """read_events returns every step_completed/step_reused seen so far."""

    def __init__(self) -> None:
        self.rows: list[_RunEventRow] = []

    async def read_events(self, run_id, after_seq):
        return list(self.rows)

    def record(self, events) -> None:
        for e in events:
            if e["type"] in ("step_completed", "step_reused"):
                self.rows.append(_RunEventRow(e["type"], e["data"]))


def _pin_hash(engine, monkeypatch):
    # The evidence run carried ONE hash for every step; pin it so the lookup would
    # match on revisit exactly as it did live.
    monkeypatch.setattr(engine, "_compute_step_input_hash", lambda s, c: "H")


@pytest.mark.asyncio
async def test_loop_revisits_always_execute_never_reused(monkeypatch):
    engine = ExecutionEngine()
    _pin_hash(engine, monkeypatch)
    ctx = _FakeCtx(scoped_store=_LiveStore())
    fix, verify = (
        _step(max_attempts=2, agent_id="fix"),
        _step(max_attempts=2, agent_id="verify"),
    )
    fix_s = _FakeStrategy([], step_agent="fix")
    verify_s = _FakeStrategy([], step_agent="verify")

    all_events = []
    for _ in range(3):  # fix -> verify(retry) -> fix -> verify(retry) -> fix -> verify
        for step, strat in ((fix, fix_s), (verify, verify_s)):
            evs = await _collect(engine, step, ctx, strat)
            ctx.scoped_store.record(evs)
            all_events += evs

    assert fix_s.calls == 3
    assert verify_s.calls == 3
    assert not [e for e in all_events if e["type"] == "step_reused"]


@pytest.mark.asyncio
async def test_resume_first_dispatch_still_reuses_completed_steps(monkeypatch):
    engine = ExecutionEngine()
    _pin_hash(engine, monkeypatch)
    ctx = _FakeCtx()
    ref = ctx.artifacts.write_ref(
        run_id=ctx.run_id,
        owner_id=ctx.owner_id,
        workspace_id=ctx.workspace_id,
        kind="summary",
        producer_step="fix",
        producer_agent="fix",
        task_id=None,
        content="prior",
        location="memory://p",
    )
    store = _LiveStore()
    store.rows.append(
        _RunEventRow(
            "step_completed",
            {"step": "fix", "input_hash": "H", "output_ref_id": ref.id},
        )
    )
    ctx.scoped_store = store
    strat = _FakeStrategy([], step_agent="fix")
    step = _step(max_attempts=2, agent_id="fix")

    first = await _collect(engine, step, ctx, strat)
    assert [e["type"] for e in first] == ["step_reused"]
    assert strat.calls == 0

    # A loop-back revisit in the same (resumed) attempt must now execute.
    second = await _collect(engine, step, ctx, strat)
    assert strat.calls == 1
    assert "step_reused" not in [e["type"] for e in second]


# --------------------------------------------------------------------------
# Bug 2
# --------------------------------------------------------------------------


class _PreSetEvent(asyncio.Event):
    """Already-answered gate: the engine's initial ``clear()`` must not re-arm it."""

    def clear(self) -> None:
        pass


class _GateStore:
    def __init__(self, response) -> None:
        self._response = response

    async def get_review_event(self, key):
        ev = _PreSetEvent()
        ev.set()
        return ev

    async def get_review_response(self, key):
        return self._response


async def _drive_gate(response, output="ORIGINAL"):
    engine = ExecutionEngine()
    engine._store = _GateStore(response)
    return [
        e
        async for e in engine._run_review_gate(
            pipeline_run_id="gate-run",
            agent_id="custom-agent:ledger",
            agent_name="Ledger",
            output=output,
        )
    ]


@pytest.mark.asyncio
async def test_gate_approve_with_edit_flags_edited_and_emits_edit():
    evs = await _drive_gate({"approved": True, "edited_content": "EDITED"})
    approved = next(e for e in evs if e["type"] == "review_gate_approved")
    assert approved["data"]["edited"] is True
    assert {"type": "_gate_edited", "edited_content": "EDITED"} in evs


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "resp",
    [
        {"approved": True},
        {"approved": True, "edited_content": ""},
        {"approved": True, "edited_content": "ORIGINAL"},
    ],
)
async def test_gate_approve_without_real_edit_is_unchanged(resp):
    evs = await _drive_gate(resp)
    approved = next(e for e in evs if e["type"] == "review_gate_approved")
    assert approved["data"]["edited"] is False
    assert not [e for e in evs if e["type"] == "_gate_edited"]


@pytest.mark.asyncio
async def test_post_step_edit_rewrites_sandbox_file_and_latest_content(
    tmp_path, monkeypatch
):
    from app.agents.sandbox import agent_output_relpath, write_agent_output

    engine = ExecutionEngine()

    class _Spec:
        id = "custom-agent:ledger"
        name = "Ledger"

    class _Sandbox:
        def __init__(self) -> None:
            self.files: dict[str, str] = {}

        def write(self, rel, content):
            self.files[rel] = content

    class _Ectx:
        last_streamed = "ORIGINAL"
        run_id = "run-x"
        owner_id = "o"
        workspace_id = "w"
        artifacts = ArtifactGraph()
        step_visit_counts: dict = {}
        build_task_number = ""

    async def _dual(ectx, **kw):
        ectx.artifacts.write_ref(
            run_id=ectx.run_id,
            owner_id=ectx.owner_id,
            workspace_id=ectx.workspace_id,
            kind=kw["kind"],
            producer_step=kw["producer_step"],
            producer_agent=kw["producer_agent"],
            task_id=None,
            content=kw["content"],
            location=kw["location"],
        )

    monkeypatch.setattr(engine, "_dual_write_artifact", _dual)
    sb, ectx, spec = _Sandbox(), _Ectx(), _Spec()
    write_agent_output(sb, index=1, agent_id=spec.id, name=spec.name, output="ORIGINAL")
    ectx.artifacts.write_ref(
        run_id="run-x",
        owner_id="o",
        workspace_id="w",
        kind="summary",
        producer_step=spec.id,
        producer_agent=spec.id,
        task_id=None,
        content="ORIGINAL",
        location="x",
    )
    results = [{"agent_id": spec.id, "output": "ORIGINAL"}]

    await engine._apply_declared_gate_edit(
        "REVIEW + DECISIONS",
        results,
        [spec],
        ectx,
        target_spec=spec,
        index=1,
        sandbox=sb,
    )

    rel = agent_output_relpath(index=1, agent_id=spec.id)
    assert sb.files[rel].endswith("REVIEW + DECISIONS")
    assert "ORIGINAL" not in sb.files[rel]
    assert engine._latest_typed_content(ectx, spec.id) == "REVIEW + DECISIONS"
    assert results[-1]["output"] == "REVIEW + DECISIONS"
    assert ectx.last_streamed == "REVIEW + DECISIONS"
