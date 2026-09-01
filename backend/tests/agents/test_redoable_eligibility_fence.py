"""tests/agents/test_redoable_eligibility_fence.py — ISS-090.

``redoable`` has no eligibility fence — unlike ``update_specs_eligible`` (computed
structurally by ``_update_specs_eligible(artifact_kind, ectx)``, see
``test_sc001_gate_flag.py``), ``redoable`` is an inline ``True`` literal at all three
gate call sites in ``engine.py`` (the REQ-RESUME-17 re-entry, the post-revision
re-open, and the live post-stream gate). So ANY agent named in a per-run
``gate_agent_ids`` gets a Redo button with no server-side rule.

The fix mirrors ``_update_specs_eligible`` exactly: a structural predicate derived
from ``artifact_kind`` / ``ectx``, published at the same three sites, instead of a
bare ``True`` literal. This test pins that structural shape directly against the
source, exactly as ``test_eligibility_introduces_no_agent_id_literal`` pins SC-001.

Offline-safe: static source inspection only, no agent run, no Bedrock, no Postgres.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import agents.execution_engine.engine as engine_mod


@pytest.mark.issue("ISS-090")
def test_redoable_is_not_a_hardcoded_true_literal_at_gate_call_sites() -> None:
    """``redoable`` must be computed the same way ``update_specs_eligible`` is —
    via a call, not a bare ``True`` literal — at every ``_run_review_gate(...)``
    call site. Today all three sites pass ``redoable=True`` verbatim."""
    lines = Path(engine_mod.__file__).read_text(encoding="utf-8").splitlines()
    hardcoded = [ln for ln in lines if "redoable=True" in ln]
    assert not hardcoded, (
        "redoable is still an inline True literal at gate call site(s), with no "
        f"eligibility predicate (ISS-090): {hardcoded!r}"
    )


# ===========================================================================
# (a) On the way OUT — the predicate itself withholds the affordance for a
# per-task build dispatch (the task_loop step this card names). The FE half —
# "no Request-changes control renders when redoable is False" — is already
# pinned generically (any redoable=False gate) by
# frontend/src/components/chat/InlineGateActions.test.tsx::
# "hides Request changes entirely when the server did not mark the gate redoable".
# ===========================================================================


def _fresh_engine():
    """An ExecutionEngine on a FRESH artifact-store singleton — mirrors
    ``test_update_specs_enforcement.py::_fresh_engine`` so no leaked armed event or
    recorded response lets one test resolve another's gate."""
    import agents.artifact_store.store as store_mod
    from agents.execution_engine.engine import ExecutionEngine

    store_mod._STORE = None
    return ExecutionEngine()


@pytest.mark.issue("ISS-090")
def test_redoable_is_false_for_a_per_task_build_dispatch() -> None:
    """``_redoable(ectx)`` — the predicate every inline gate call site now reads —
    must withhold the Redo affordance for exactly the dispatch ISS-090 names: a
    per-task build dispatch, signalled by ``ectx.build_task_number`` being set (the
    scratch field ``KernelServices.run_agent`` binds around one task_loop iteration).
    Every other dispatch (the field unset/empty) keeps the affordance — dormancy.
    """
    engine = _fresh_engine()
    from agents.execution_engine.context import ExecutionContext

    ectx = ExecutionContext(run_id="redoable-fence-run", owner_id="anon")

    assert engine._redoable(ectx) is True, (
        "a plain dispatch (no build_task_number) must still offer Redo — dormancy"
    )

    ectx.build_task_number = "3"
    assert engine._redoable(ectx) is False, (
        "a per-task build dispatch (build_task_number set) must NOT offer Redo (ISS-090) "
        "— its gate already carries a compacted view of the deliverable"
    )

    ectx.build_task_number = ""
    assert engine._redoable(ectx) is True, (
        "clearing build_task_number (the task loop's own finally-restore) must restore "
        "the affordance for the next, non-per-task dispatch"
    )


# ===========================================================================
# (b) On the way IN — ``_run_review_gate`` must REFUSE a "redo" action the firing
# never advertised, exactly as it already refuses an ineligible "update_specs"
# (test_update_specs_enforcement.py). Pre-fix ``_run_review_gate`` acted on
# ``action == "redo"`` unconditionally, never reading the ``redoable`` it had just
# published.
# ===========================================================================

_DRIVE_TIMEOUT = 10.0
_ARM_TIMEOUT = 1.5


async def _wait_until(pred, timeout: float = _ARM_TIMEOUT) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if pred():
            return True
        await asyncio.sleep(0.01)
    return False


async def _post_redo_at_real_gate(engine, run_id: str, *, redoable: bool):
    """Drive ONE real ``_run_review_gate`` firing while a client posts ``redo``.

    Mirrors ``test_update_specs_enforcement.py::_post_update_specs_at_real_gate``: the
    client posts the follow-up approve only after observing the gate RE-ARM, so an
    approve can never be what closes a firing that actually honoured the redo.
    """
    store = engine._store
    agent_id = "gated-agent"
    gate_key = f"{run_id}:{agent_id}:0"
    posted: list[str] = []

    async def _client() -> None:
        if not await _wait_until(lambda: store.review_event_pending(gate_key)):
            return
        await store.set_review_response(
            gate_key, approved=False, action="redo", instructions="do it differently"
        )
        posted.append("redo")
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
            output="THE OUTPUT",
            redoable=redoable,
            update_specs_eligible=False,
            artifact_kind="summary",
        ):
            events.append(ev)

    client = asyncio.create_task(_client())
    try:
        await asyncio.wait_for(_collect(), timeout=_DRIVE_TIMEOUT)
    finally:
        client.cancel()

    assert posted[:1] == ["redo"], (
        f"the gate never armed, so nothing was tested; posted={posted} events={events}"
    )
    types = [e.get("type") for e in events]
    verdict = "honored" if "_gate_redo" in types else "refused"
    return verdict, events


@pytest.mark.issue("ISS-090")
@pytest.mark.asyncio
async def test_a_redo_is_refused_when_the_firing_published_redoable_false() -> None:
    """A ``redo`` at a gate that published ``redoable: False`` must be REFUSED — the
    gate stays OPEN (neither approved nor rejected) rather than re-running the agent.

    Pre-fix: ``_run_review_gate`` acted on ``action == "redo"`` unconditionally, so this
    re-ran the gated agent even though the firing never advertised the button — exactly
    the "way in" half of ISS-090.
    """
    engine = _fresh_engine()
    verdict, events = await _post_redo_at_real_gate(engine, "iss090-refuse", redoable=False)
    types = [e.get("type") for e in events]

    assert verdict == "refused", (
        "the gate re-ran the agent on a redo that this firing published redoable=False "
        f"for (ISS-090); events={types}"
    )
    assert "_gate_rejected" not in types, (
        f"a refused redo must never cancel the run; events={types}"
    )
    assert "review_gate_approved" in types, (
        "the gate did not stay open after refusing the redo — approve must still be "
        f"available; events={types}"
    )


@pytest.mark.asyncio
async def test_a_redo_still_fires_when_the_firing_published_redoable_true() -> None:
    """Dormancy guard: at a firing that published ``redoable: True`` a redo behaves
    exactly as it always has — the enforcement in (a) above must narrow nothing the
    rule permits."""
    engine = _fresh_engine()
    verdict, events = await _post_redo_at_real_gate(engine, "iss090-honour", redoable=True)
    types = [e.get("type") for e in events]

    assert verdict == "honored", f"an advertised redo no longer re-runs the agent; events={types}"
    redo = [e for e in events if e.get("type") == "_gate_redo"]
    assert redo and redo[0].get("instructions") == "do it differently", (
        f"the redo instructions were dropped on the way to the re-run; got {redo}"
    )
