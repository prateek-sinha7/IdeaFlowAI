"""Regression: a NON-loop budget dimension still terminates the run (unaffected by
the [convergence-limit fix] to the ``loop_iterations`` dimension only — see
``engine.py``'s R-07 loop-cap enforcement site and ``test_conditional_loop_budget_t24.py``
for the loop case).

The engine's ``except BudgetExceeded`` graceful-abort handler
(``ExecutionEngine.execute`` — persists the snapshot, emits ``budget_aborted``,
transitions the run to ``failed``, and RETURNS with no ``pipeline_complete``) is
completely untouched by that fix: the fix only suppresses the RAISE at ONE call
site (the backward/self conditional-route loop-cap check) and leaves every other
``BudgetExceeded`` call site (``BudgetManager.reserve`` — subagents/concurrency/
depth/workspace; ``note_tokens``; ``note_wall_clock``) raising exactly as before.

Drives ``sample_subagents_parallel`` (a real 3-way fan-out: apple/ball/cat) fully
OFFLINE via the shared ``_drive`` harness, with ``DEFAULT_MAX_SUBAGENTS``
monkeypatched down to 1 so the fan-out's own ``reserve(subagents=3, ...)`` raises
``BudgetExceeded(dimension="subagents")`` — a non-loop dimension — BEFORE any
worker spawns, hitting the SAME graceful-abort handler the loop-cap case used to.
"""

from __future__ import annotations

import pytest

import agents.execution_engine.budget as budget_mod
from tests.agents._scripted_model import _drive

_PIPELINE = "sample_subagents_parallel"


@pytest.mark.asyncio
async def test_subagents_dimension_still_aborts_the_run(monkeypatch):
    # Cap subagents at 1 — the fixture's 3-way fan-out (apple/ball/cat) always
    # requests 3, so reserve() must refuse before any worker spawns.
    monkeypatch.setattr(budget_mod, "DEFAULT_MAX_SUBAGENTS", 1)

    events = await _drive(_PIPELINE)
    assert events, f"{_PIPELINE} produced no events"

    types = [e.get("type") for e in events]
    started = [e["data"].get("agent_id") for e in events if e.get("type") == "agent_start"]
    budget_events = [e for e in events if e.get("type") == "budget_aborted"]

    print("EVENT TYPES:", types)
    print("BUDGET_ABORTED events:", budget_events)

    assert len(budget_events) == 1, (
        f"expected exactly one budget_aborted event, got {len(budget_events)}. "
        f"Events: {types}"
    )
    assert budget_events[0]["data"].get("dimension") == "subagents", budget_events[0]

    # A non-loop dimension keeps the ORIGINAL terminating behaviour: no
    # pipeline_complete, no degraded status — the run is aborted, not continued.
    assert "pipeline_complete" not in types, (
        f"{_PIPELINE} reached pipeline_complete despite a non-loop budget breach — "
        f"the fix must NOT have made every dimension non-fatal. Events: {types}"
    )
    # None of the (never-spawned) siblings ran — reserve-before-spawn.
    for sibling in ("custom-agent:apple", "custom-agent:ball", "custom-agent:cat"):
        assert sibling not in started, (
            f"{sibling} started despite the pre-spawn subagents budget refusal. "
            f"started={started}"
        )
