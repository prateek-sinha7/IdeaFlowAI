"""T24 (spec 014 / Phase 3 dispatch loop): ``sample_conditional_previous_step`` (A1, the
loop fixture) driven end-to-end via the shared offline scripted-model harness
(``tests.agents._scripted_model._drive``), with the ``check`` step scripted to ALWAYS
answer ``{"decision": "retry"}`` (never ``"ok"``).

Confirms whether the run fails closed with ``BudgetExceeded`` (surfaced as the engine's
``budget_aborted`` terminal event, ``dimension == "loop_iterations"``) after exactly
``loop_max_iterations`` (3, per the fixture's own ``route.loop_max_iterations: 3``)
successful loop-back passes — not 4, not unbounded, not silently swallowed as a normal
completion.

No live LLM: the model is fully scripted offline (``ScriptedFakeChatModel``), matching
the recipe every other ``tests/agents/_scripted_model.py``-based suite uses (e.g.
``test_characterization_sample_subagents_parallel.py``). The ``check`` step's per-call
decision is supplied by locally monkeypatching ``_scripted_model._scripts_for`` for the
duration of the test (restored in ``finally``) — the shared per-agent-id registry has no
static branch for this fixture's steps, and this scenario needs the SAME step
(``custom-agent:check``) to answer identically on every dispatch, which a static
registry entry already provides for the "always retry" case.
"""

from __future__ import annotations

import pytest

from tests.agents import _scripted_model as _sm
from tests.agents._scripted_model import _ScriptedTurn, _drive

_PIPELINE = "sample_conditional_previous_step"


def _always_retry_scripts_for(agent_id: str) -> list[_ScriptedTurn]:
    """Per-agent scripted turns: ``check`` ALWAYS answers retry; everything else is inert."""
    if agent_id == "custom-agent:check":
        return [_ScriptedTurn(texts=['{"decision": "retry"}'], usage=(5, 3))]
    return [_ScriptedTurn(texts=[f"{agent_id} default output."], usage=(5, 3))]


@pytest.mark.asyncio
async def test_always_retry_fails_closed_with_budget_exceeded_at_loop_cap():
    orig_scripts_for = _sm._scripts_for
    _sm._scripts_for = _always_retry_scripts_for
    try:
        events = await _drive(_PIPELINE)
    finally:
        _sm._scripts_for = orig_scripts_for

    assert events, f"{_PIPELINE} produced no events"

    types = [e.get("type") for e in events]
    started = [e["data"].get("agent_id") for e in events if e.get("type") == "agent_start"]
    budget_events = [e for e in events if e.get("type") == "budget_aborted"]

    print("EVENT TYPES:", types)
    print("AGENT_START agent_ids:", started)
    print("BUDGET_ABORTED events:", budget_events)

    # ── The load-bearing assertions (T24) ──────────────────────────────────
    assert "pipeline_complete" not in types, (
        f"{_PIPELINE} completed normally despite an always-retry decision — the loop "
        f"cap was NOT enforced (not silently swallowed is violated). Events: {types}"
    )
    assert len(budget_events) == 1, (
        f"expected exactly one budget_aborted event (fail-closed, not unbounded), "
        f"got {len(budget_events)}. Events: {types}"
    )
    assert budget_events[0]["data"].get("dimension") == "loop_iterations", budget_events[0]

    assert "custom-agent:done" not in started, (
        f"'done' ran despite the loop never resolving to ok — the run did not fail "
        f"closed before reaching the terminal step. started={started}"
    )
