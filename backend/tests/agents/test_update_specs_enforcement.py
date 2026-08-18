"""tests/agents/test_update_specs_enforcement.py — ISS-053: the eligibility flag is BINDING.

``_update_specs_eligible`` computes whether a gate firing may start a spec-revision
cycle, and ``_run_review_gate`` stamps that verdict onto ``review_gate_ready``. Until this
suite, nothing ever read it back: the gate acted on the client-supplied ``action`` string
alone, so a replayed or crafted POST ran the sub-pipeline at gates that advertised the
affordance as unavailable. ``gate_key`` is ``f"{run_id}:{agent_id}"`` — a gate SLOT, not a
gate FIRING — so replaying a legitimate earlier click is enough; nothing need be crafted.

What is proven here:

  * **Refusal is "keep waiting".** An ineligible ``update_specs`` must not fire the
    sub-pipeline, must not approve (fail-open — the exact hole the Phase-23 F1a redo
    defence exists to close, and against WR-07's "HITL gates fail closed") and must not
    reject (that would cancel the run). The gate stays open. Test 1.
  * **Dormancy.** An ELIGIBLE ``update_specs`` behaves exactly as it always has. Test 2.
  * **The three-gate verdict.** The eligibility values are HARVESTED from a real engine
    drive rather than hardcoded, then fed into the real gate: honored at the OUTER analyze
    gate, REFUSED at the IN-PASS one, honored again at the RE-OPENED one. This is the
    reachability proof — enforcement must not make a second revision cycle unreachable.
    Test 3.
  * **The declared gates consume it.** ``gates/human.py`` / ``gates/approval.py`` handle
    ``_gate_rejected`` / ``_gate_redo`` / ``_gate_edited`` but had NO ``_gate_update_specs``
    branch, so it hit the ``yield event`` fall-through: an internal signal on the SSE wire
    (against ``.kiro/steering/backend-engine.md`` §39) AND ``GATE_PASS`` — a silent approve
    on a declared ``gates:[human]`` / ``gates:[approval]`` step. Test 4, the F1a treatment
    applied to redo's sibling.

Its sibling ``test_spec_revision_cycles.py`` proves what the engine PASSES to the gate (it
stubs ``_run_review_gate`` out entirely). This file proves what the gate DOES with it.

Offline-safe: scripted model only — no Bedrock / Postgres / Chromium.
"""

from __future__ import annotations

import asyncio

import pytest

# Importing the harness sets RUNS_ROOT to a temp dir + forces the InMemory checkpointer
# BEFORE app.core.config loads — keep this import first.
from tests.agents._scripted_model import ScriptedFakeChatModel  # noqa: E402,F401

from agents.capabilities.gates.approval import ApprovalGate  # noqa: E402
from agents.capabilities.gates.base import GATE_PASS, GateOutcome  # noqa: E402
from agents.capabilities.gates.human import HumanGate  # noqa: E402

# A refused action re-arms the gate rather than resolving it, so every drive is bounded:
# a wiring mistake must fail loudly instead of hanging the suite.
_DRIVE_TIMEOUT = 10.0
_ARM_TIMEOUT = 1.5

_HONORED = "honored"
_REFUSED = "refused"


async def _wait_until(pred, timeout: float = _ARM_TIMEOUT) -> bool:
    """Poll ``pred`` until true or the timeout elapses. False ⇒ it never became true."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if pred():
            return True
        await asyncio.sleep(0.01)
    return False


def _fresh_engine():
    """An ExecutionEngine on a FRESH artifact-store singleton.

    The store is a per-process HITL registry; a leaked armed event or recorded response
    would let one test resolve another's gate.
    """
    import agents.artifact_store.store as store_mod
    from agents.execution_engine.engine import ExecutionEngine

    store_mod._STORE = None
    return ExecutionEngine()


async def _post_update_specs_at_real_gate(engine, run_id: str, *, eligible: bool):
    """Drive ONE real ``_run_review_gate`` firing while a client posts ``update_specs``.

    Returns ``(verdict, events)`` where verdict is ``honored`` (the gate emitted
    ``_gate_update_specs``, i.e. the sub-pipeline would run) or ``refused`` (it did not).

    The client posts a follow-up approve ONLY after observing the gate RE-ARM, so an
    approve can never be what closes an honored gate — the two outcomes stay distinguishable.
    """
    store = engine._store
    agent_id = "gated-agent"
    gate_key = f"{run_id}:{agent_id}"
    posted: list[str] = []

    async def _client() -> None:
        # An armed-but-unset review event is the ground truth that the gate is waiting
        # (KAN-94 — the same signal run_commands._gate_is_pending reads).
        if not await _wait_until(lambda: store.review_event_pending(gate_key)):
            return
        await store.set_review_response(
            gate_key, approved=False, action="update_specs", instructions="THE REPORT"
        )
        posted.append("update_specs")
        # Re-armed ⇒ the gate refused and is still waiting. Unblock it so the drive ends.
        if not await _wait_until(lambda: store.review_event_pending(gate_key)):
            return
        await store.set_review_response(gate_key, approved=True)
        posted.append("approve")

    events: list[dict] = []

    async def _collect() -> None:
        async for ev in engine._run_review_gate(
            pipeline_run_id=run_id,
            agent_id=agent_id,
            agent_name="Gated Agent",
            output="THE ANALYZE OUTPUT",
            redoable=True,
            update_specs_eligible=eligible,
            artifact_kind="summary",
        ):
            events.append(ev)

    client = asyncio.create_task(_client())
    try:
        await asyncio.wait_for(_collect(), timeout=_DRIVE_TIMEOUT)
    finally:
        client.cancel()

    assert posted[:1] == ["update_specs"], (
        f"the gate never armed, so nothing was tested; posted={posted} events={events}"
    )
    types = [e.get("type") for e in events]
    verdict = _HONORED if "_gate_update_specs" in types else _REFUSED
    return verdict, events


# ===========================================================================
# 1 + 2 — the fence itself, and its dormancy
# ===========================================================================


@pytest.mark.asyncio
async def test_ineligible_update_specs_keeps_the_gate_waiting() -> None:
    """An ``update_specs`` at a gate that published ``update_specs_eligible: False`` is
    refused — and the gate stays OPEN rather than being resolved either way.

    Degrading to approve would be fail-open on a HITL gate (WR-07 says they fail closed);
    degrading to reject would cancel the user's run. Neither is acceptable, so the only
    correct degrade is to keep waiting.
    """
    engine = _fresh_engine()
    verdict, events = await _post_update_specs_at_real_gate(
        engine, "iss053-refuse", eligible=False
    )
    types = [e.get("type") for e in events]

    assert verdict == _REFUSED, (
        "the gate ran the spec-revision sub-pipeline at a firing that advertised "
        f"update_specs_eligible=False (ISS-053); events={types}"
    )
    assert "_gate_rejected" not in types, (
        f"an ineligible action must never cancel the run; events={types}"
    )
    # The gate was still open afterwards: the follow-up approve is what closed it.
    assert "review_gate_approved" in types, (
        "the gate did not stay open — an ineligible action must leave approve / reject / "
        f"redo / edit still available to the user; events={types}"
    )


@pytest.mark.asyncio
async def test_eligible_update_specs_still_fires() -> None:
    """Dormancy guard: at an ELIGIBLE gate the action behaves exactly as it always has.

    Green before AND after the fence — the fence must narrow nothing the rule permits.
    """
    engine = _fresh_engine()
    verdict, events = await _post_update_specs_at_real_gate(
        engine, "iss053-eligible", eligible=True
    )
    types = [e.get("type") for e in events]

    assert verdict == _HONORED, (
        f"an eligible update_specs no longer fires the sub-pipeline; events={types}"
    )
    report = [e for e in events if e.get("type") == "_gate_update_specs"]
    assert report and report[0].get("analysis_report") == "THE REPORT", (
        f"the analysis report was dropped on the way to the sub-pipeline; got {report}"
    )


# ===========================================================================
# 3 — the three-gate verdict, against the REAL gate (the reachability proof)
# ===========================================================================


@pytest.mark.asyncio
async def test_three_gate_vector_is_enforced_and_leaves_a_second_cycle_reachable() -> None:
    """Outer analyze gate → honored, in-pass gate → REFUSED, re-opened gate → honored.

    The eligibility values are HARVESTED from a real engine drive (``_drive_cycles``
    records what ``_update_specs_eligible`` actually returned at each firing) rather than
    hardcoded, then each is fed into the real ``_run_review_gate``. So this asserts the
    rule and its enforcement together.

    The third element is the load-bearing one: enforcement must not make a second revision
    cycle unreachable. If the re-opened gate ever stops advertising eligibility, this fails
    — which is the signal to STOP, not to loosen the rule (loosening it re-opens the
    nesting recursion ISS-051 closed).
    """
    from tests.agents.test_spec_revision_cycles import _drive_cycles

    records, _tids, _ectx, _ordered, _events = await _drive_cycles("iss053-vector", {0})
    vector = [r["eligible"] for r in records]

    assert vector == [True, False, True], (
        "the eligibility rule changed — outer/in-pass/re-opened analyze gates must be "
        f"True/False/True; got {vector}"
    )

    verdicts = []
    for n, eligible in enumerate(vector):
        engine = _fresh_engine()
        verdict, _evs = await _post_update_specs_at_real_gate(
            engine, f"iss053-vector-gate{n}", eligible=eligible
        )
        verdicts.append(verdict)

    assert verdicts == [_HONORED, _REFUSED, _HONORED], (
        "expected the OUTER gate to honor update_specs, the IN-PASS gate to refuse it "
        "(the one route that nests) and the RE-OPENED gate to honor it again (the flat "
        f"sibling route that keeps a second cycle reachable); got {verdicts}"
    )


# ===========================================================================
# 4 — the declared gates consume _gate_update_specs (the F1a treatment for redo's sibling)
# ===========================================================================


class _UpdateSpecsEmittingRunner:
    """A KernelServices-shaped fake whose ``run_human_gate`` delegate yields a
    ``review_gate_ready`` then a stray internal ``_gate_update_specs`` — what the shared
    ``_run_review_gate`` emits when a client sends ``action: "update_specs"`` on a
    DECLARED gate (which passes ``update_specs_eligible=False`` by default)."""

    def __init__(self, run_id: str = "declared-run") -> None:
        self.run_id = run_id
        self.recorded: list[tuple] = []

    async def run_human_gate(self, step, *, output: str = "", payload=None):
        gate_key = f"{self.run_id}:{getattr(step, 'agent_id', '?')}"
        yield {
            "type": "review_gate_ready",
            "data": {"gate_key": gate_key, "redoable": False,
                     "update_specs_eligible": False},
        }
        yield {"type": "_gate_update_specs", "analysis_report": "a crafted report"}

    async def record_gate_event(self, step, gate, outcome, detail=None):
        self.recorded.append((step, gate, outcome, detail))
        return "gate-event-id"

    async def read_gate_events(self, run_id):
        return []  # no prior approval → ApprovalGate falls through to the delegate


class _FakeStep:
    def __init__(self, agent_id: str = "declared-step") -> None:
        self.agent_id = agent_id
        self.tools = None  # _exec_policy_snapshot's getattr-chain tolerates this


class _FakeCtx:
    def __init__(self, runner) -> None:
        self.runner = runner
        self.last_streamed = "the gated output"


@pytest.mark.asyncio
@pytest.mark.parametrize("gate_cls", [HumanGate, ApprovalGate])
async def test_declared_gate_consumes_update_specs_never_passes_or_leaks(gate_cls) -> None:
    """A declared human|approval gate receiving ``_gate_update_specs`` must CONSUME it:
    never yield the internal signal to the wire, never resolve to ``GATE_PASS``.

    Exactly the F1a contract already enforced for ``_gate_redo``. Without it the step
    silently advances on a gate action the user never took, and an internal ``_gate_*``
    signal reaches SSE (``run_commands`` enqueues with no type filter).
    """
    runner = _UpdateSpecsEmittingRunner()
    ctx = _FakeCtx(runner)
    step = _FakeStep()

    events: list[dict] = []
    terminal: GateOutcome | None = None
    async for item in gate_cls().evaluate_stream(step, ctx):
        if isinstance(item, dict):
            events.append(item)
        else:
            terminal = item

    leaked = [e for e in events if e.get("type") == "_gate_update_specs"]
    assert leaked == [], (
        f"{gate_cls.__name__} leaked the internal _gate_update_specs signal to the wire"
    )

    assert terminal is not None, f"{gate_cls.__name__} produced no terminal GateOutcome"
    assert terminal.outcome != GATE_PASS, (
        f"{gate_cls.__name__} silently PASSED on a stray update_specs — a declared gate "
        "signed itself off on an action the user never took"
    )

    # The public ready event still flows through unchanged (parity).
    ready = [e for e in events if e.get("type") == "review_gate_ready"]
    assert ready, f"{gate_cls.__name__} swallowed the public review_gate_ready"

    # The audit row records the HONEST non-PASS outcome (F9), not a misleading PASS.
    assert runner.recorded, f"{gate_cls.__name__} wrote no audit row"
    assert runner.recorded[-1][2] != GATE_PASS
