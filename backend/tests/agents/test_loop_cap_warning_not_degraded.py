"""A14: a tripped R-07 loop cap is a WARNING on the run, not a terminal verdict.

Reproduces run a786cc27 (also 5130337e): the review loop's convergence cap tripped
(``loop_max_iterations=2``), suppressed the backward jump, kept the dispatch loop
going FORWARD, and every step after it (assembler, structure-check, story-layer,
publish) completed cleanly with a resolved ``prototype.html`` — yet the run was
persisted ``status="degraded"`` with ``error`` carrying the cap's internal message,
which the run-history UI renders as a red "Failed" badge decided on a budget guard
tens of minutes before the run actually finished (verified against the read-only DB:
``workflow_runs.error`` for a786cc27 is byte-identical to the cap message below).

``test_conditional_loop_budget_t24.py`` covers the COMPLETING case (deliverable
resolves, no agent failure → clean completion + a ``warnings`` entry — this is
"test 1" from the fix's acceptance criteria). This file covers the counter-case
("test 2"): a tripped cap that ends the run WITHOUT a deliverable is still,
honestly, ``degraded`` — the fix narrows WHEN the cap escalates status, it does not
remove the escalation.

Same offline recipe as T24 (``ex_A1_loop`` + the shared scripted-model harness),
with ``done`` (the step after the loop) scripted to stream nothing, so the
``single_file`` deliverable resolver's every fallback chain bottoms out at ``""``.
"""

from __future__ import annotations

import pytest

from tests.agents import _scripted_model as _sm
from tests.agents._scripted_model import _ScriptedTurn, _drive

_PIPELINE = "ex_A1_loop"


def _retry_then_empty_deliverable_scripts_for(agent_id: str) -> list[_ScriptedTurn]:
    """``check`` ALWAYS retries (trips the cap); ``done`` streams nothing (no
    deliverable for the single_file resolver to fall back to); everything else
    is the same inert default turn T24 uses."""
    if agent_id == "custom-agent:check":
        return [_ScriptedTurn(texts=['{"decision": "retry"}'], usage=(5, 3))]
    if agent_id == "custom-agent:done":
        return [_ScriptedTurn(texts=[""], usage=(0, 0))]
    return [_ScriptedTurn(texts=[f"{agent_id} default output."], usage=(5, 3))]


@pytest.mark.asyncio
async def test_cap_trip_with_no_deliverable_still_degrades():
    orig_scripts_for = _sm._scripts_for
    _sm._scripts_for = _retry_then_empty_deliverable_scripts_for
    try:
        events = await _drive(_PIPELINE)
    finally:
        _sm._scripts_for = orig_scripts_for

    assert events, f"{_PIPELINE} produced no events"

    types = [e.get("type") for e in events]
    budget_events = [e for e in events if e.get("type") == "budget_aborted"]
    completes = [e for e in events if e.get("type") == "pipeline_complete"]

    assert len(budget_events) == 1, (
        f"expected exactly one budget_aborted event, got {len(budget_events)}. "
        f"Events: {types}"
    )
    cap_message = budget_events[0]["data"].get("message")
    assert cap_message, budget_events[0]

    assert len(completes) == 1, (
        f"{_PIPELINE} did not reach pipeline_complete. Events: {types}"
    )
    data = completes[0]["data"]

    # No deliverable resolved (``done`` streamed nothing) → the run genuinely has
    # nothing to show for itself. The cap trip is the ONLY reason, so it must
    # still be the honest terminal verdict, not just a warning.
    assert not data.get("final_output"), data
    assert data.get("status") == "degraded", (
        f"a tripped cap that leaves the run with NO deliverable must still degrade "
        f"it: {data}"
    )
    # Same message text as the budget_aborted event — no new wording invented.
    assert data.get("degraded_reason") == cap_message, data
    # The warning seam still carries it too (additive, never instead-of).
    assert data.get("warnings") == [cap_message], data
