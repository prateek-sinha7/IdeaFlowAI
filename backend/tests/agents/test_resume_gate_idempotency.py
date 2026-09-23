"""tests/agents/test_resume_gate_idempotency.py — STABILIZATION A3.

Bug (pdf_to_prototype STABILIZATION.md item A3, DB evidence from runs 9432cf6c /
c01479ba / 7e8a8e71): a run cancelled (or crashed) while a review gate was durably
open, then resumed — either a crash-restart or the explicit "resume a
cancelled/failed run" action — re-opened an ALREADY-APPROVED gate, sometimes
landing 2+ steps BACKWARD past steps that had genuinely completed.

Two independent, compounding root causes, both fixed here:

  1. ``derive_open_gate`` (gate_pendency.py) treats a run's own
     ``pipeline_cancelled``/``pipeline_failed`` marker as a REVIEW_RESOLUTIONS
     match — correct for "is this run's gate still live for a client watching it
     right now" (chat_router / run_stream), but WRONG for the resume-offset
     derivation: the marker records the INTERRUPTION a resume exists to continue
     past, not a human resolving the gate. Left unfiltered, the offset
     computation's RESUME-17 override goes dormant and falls back to the
     per-step completeness scan, which can land on an EARLIER, already-approved
     gate. Fixed by ``strip_premature_stops`` applied at the resume call sites.

  2. Even when the offset legitimately re-enters a step whose ``before-human``
     (pre-step) gate was durably approved BEFORE that step's own agent finished
     running (the approval only clears the step to RUN — it is not the step's
     own completion), the declared-gate evaluator re-opened the SAME gate from
     scratch, re-asking a question the human already answered. Fixed by
     ``derive_approved_gate_keys`` + a per-gate-key skip in
     ``ExecutionEngine._evaluate_gates``.

Offline, direct-classifier / direct-gate-evaluator unit tests (the same style as
``tests/agents/test_restart_resume.py``'s RESUME-17 suite and
``tests/agents/test_gates.py``'s engine step-boundary seam suite) — no live LLM,
no WebSocket, no full ``execute()`` drive.
"""

from __future__ import annotations

import types
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def _make_session():
    import app.models  # noqa: F401 — register models on Base.metadata
    from app.models.database import Base

    db = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=db)
    Session = sessionmaker(bind=db, autocommit=False, autoflush=False)
    return Session(), db


def _pb_hash(content: str) -> str:
    import hashlib

    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class _IdSpec:
    """Minimal ``.id``-bearing spec — the classifier reads getattr(spec, 'id')."""

    def __init__(self, agent_id):
        self.id = agent_id


async def _build_cancel_after_later_gate_fixture(session):
    """Reproduce run 9432cf6c's durable shape (STABILIZATION A3).

    Four single_shot steps: ``reader`` -> ``shell`` (``before-human``, PRE-step) ->
    ``mid`` -> ``tail`` (``human``, POST-step). Durable log, in order:

      1. ``shell``'s before-human gate opens and is APPROVED — a real historical
         resume evidenced this happening BEFORE ``shell``'s own agent run
         persisted its artifact/``agent_complete`` (the approval only clears the
         step to run), so — matching the real evidence exactly — this fixture
         seeds NO artifact/``agent_complete`` for ``shell``.
      2. ``reader`` and ``mid`` complete normally (artifact + ``agent_complete``)
         — "complete later steps".
      3. ``tail``'s POST-step gate opens and is left UNRESOLVED.
      4. ``pipeline_cancelled`` — the interruption a resume exists to continue
         past.

    Pre-fix: the ``pipeline_cancelled`` marker erases the RESUME-17 override's
    view of the still-open ``tail`` gate, so the per-step completeness scan
    runs and returns the FIRST incomplete step left-to-right — ``shell``
    (index 1), which already durably has its gate APPROVED. That is the exact
    "2+ steps backward, already approved" bug.
    """
    from agents.artifacts.graph import ArtifactRef
    from agents.authz import ScopedStore
    from agents.execution_engine.context import ExecutionContext
    from agents.workflows.plan import Step
    from app.models.workflow import WorkflowRun

    run_id = f"a3-{uuid.uuid4().hex[:8]}"
    owner = "a3-user"
    ws = "ws-a3"
    session.add(
        WorkflowRun(
            id=run_id, user_id=owner, owner_id=owner, workspace_id=ws,
            status="waiting_for_user", type="pdf_to_prototype", input="brief",
        )
    )
    session.commit()

    agent_ids = ["reader", "shell", "mid", "tail"]
    store = ScopedStore(owner_id=owner, workspace_id=ws, session=session)

    _seq = 0

    def _next_seq() -> int:
        nonlocal _seq
        _seq += 1
        return _seq

    # (1) shell's before-human gate: opened, then APPROVED. No artifact/agent_complete
    # for shell follows (matching the real evidence — its own run had not yet
    # persisted when the run was interrupted).
    await store.append_event(
        run_id, seq=_next_seq(), event_id="rg-shell", type="review_gate_ready",
        payload_json={"gate_key": f"{run_id}:shell:0"},
    )
    await store.append_event(
        run_id, seq=_next_seq(), event_id="ra-shell", type="review_gate_approved",
        payload_json={"agent_id": "shell"},
    )

    # (2) reader and mid completed normally.
    for agent_id in ("reader", "mid"):
        content = f"<output of {agent_id}>"
        await store.write_ref(
            ArtifactRef(
                id=str(uuid.uuid4()), run_id=run_id, owner_id=owner, workspace_id=ws,
                kind="summary", producer_step=agent_id, producer_agent=agent_id,
                task_id=None, content=content, content_hash=_pb_hash(content),
                location=f"artifact_refs/{agent_id}", version=1,
            )
        )
        await store.append_event(
            run_id, seq=_next_seq(), event_id=f"ac-{agent_id}", type="agent_complete",
            payload_json={"agent_id": agent_id},
        )

    # (3) tail's post-step gate opens — still unresolved.
    await store.append_event(
        run_id, seq=_next_seq(), event_id="rg-tail", type="review_gate_ready",
        payload_json={"gate_key": f"{run_id}:tail:0"},
    )

    # (4) the run is interrupted while tail's gate is open, then resumed.
    await store.append_event(
        run_id, seq=_next_seq(), event_id="pc", type="pipeline_cancelled",
        payload_json={},
    )
    session.commit()

    compiled = types.SimpleNamespace(
        steps=[
            Step(agent_id="reader", strategy="single_shot"),
            Step(agent_id="shell", strategy="single_shot", gates=["before-human"]),
            Step(agent_id="mid", strategy="single_shot"),
            Step(agent_id="tail", strategy="single_shot", gates=["human"]),
        ]
    )
    ordered_agents = [_IdSpec(a) for a in agent_ids]
    tmp = ExecutionContext(run_id=run_id, owner_id=owner, disk_principal="anon")
    tmp.workspace_id = ws
    tmp.scoped_store = ScopedStore(owner_id=owner, workspace_id=ws, session=session)
    return ordered_agents, compiled, tmp


@pytest.mark.asyncio
async def test_resume_after_cancel_lands_past_completed_steps_not_on_approved_gate():
    """A3 fix 1: a ``pipeline_cancelled`` marker after a LATER open gate must not
    make the resume offset fall back to an EARLIER, already-approved gate."""
    from agents.execution_engine.engine import ExecutionEngine

    session, _db = _make_session()
    try:
        ordered_agents, compiled, tmp = await _build_cancel_after_later_gate_fixture(
            session
        )
        idx = await ExecutionEngine()._first_incomplete_step(
            tmp, ordered_agents, compiled
        )
        assert idx == 3, (
            "resume must re-enter AT the still-open LATER gate (tail, idx=3), not "
            "fall back to shell's index (1) just because pipeline_cancelled "
            f"followed tail's review_gate_ready in the durable log; got idx={idx}"
        )
    finally:
        session.close()


@pytest.mark.asyncio
async def test_resume_reentry_skips_already_approved_before_human_gate():
    """A3 fix 2: re-entering a step whose EXACT gate_key already has a durable
    ``review_gate_approved`` must not re-open the gate — only the step's own
    agent (the strategy, not exercised here) re-runs."""
    from agents.execution_engine.engine import ExecutionEngine
    from tests.unit.agents.test_gates import _Ctx, _GatedStep, _RecordingRunner, _collect_gates

    engine = ExecutionEngine()
    runner = _RecordingRunner(
        review_events=[
            {"type": "review_gate_ready", "data": {"gate_key": "run-x:shell:0"}},
            {"type": "review_gate_approved", "data": {"edited": False}},
        ]
    )
    ctx = _Ctx(runner)
    ctx.run_id = "run-x"
    ctx.step_visit_counts = {}
    ctx.resume_approved_gate_keys = {"run-x:shell:0"}
    step = _GatedStep("shell", gates=["before-human"])

    events, outcomes = await _collect_gates(engine, step, ctx, phase="pre")

    assert events == [] and outcomes == [], (
        "an already durably-approved before-human gate must not re-open on resume "
        f"re-entry; got events={events!r} outcomes={outcomes!r}"
    )
    assert runner.delegate_payloads == [], "the HITL delegate must not even be called"


@pytest.mark.asyncio
async def test_before_human_gate_still_fires_without_resume_approved_keys():
    """Negative control (INV-3): with no ``resume_approved_gate_keys`` (a normal
    live run, or a resume whose gate genuinely never resolved), the SAME
    before-human gate fires exactly as before — byte-identical."""
    from agents.execution_engine.engine import ExecutionEngine
    from tests.unit.agents.test_gates import _Ctx, _GatedStep, _RecordingRunner, _collect_gates

    engine = ExecutionEngine()
    runner = _RecordingRunner(
        review_events=[
            {"type": "review_gate_ready", "data": {"gate_key": "run-x:shell:0"}},
            {"type": "review_gate_approved", "data": {"edited": False}},
        ]
    )
    ctx = _Ctx(runner)
    step = _GatedStep("shell", gates=["before-human"])

    events, outcomes = await _collect_gates(engine, step, ctx, phase="pre")

    assert any(e["type"] == "review_gate_ready" for e in events), (
        f"a before-human gate with no resume_approved_gate_keys must still fire "
        f"normally; got events={events!r}"
    )
