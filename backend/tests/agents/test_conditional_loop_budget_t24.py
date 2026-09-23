"""T24 (spec 014 / Phase 3 dispatch loop): ``ex_A1_loop`` (A1, the
loop fixture) driven end-to-end via the shared offline scripted-model harness
(``tests.agents._scripted_model._drive``), with the ``check`` step scripted to ALWAYS
answer ``{"decision": "retry"}`` (never ``"ok"``).

[convergence-limit fix] An exhausted ``loop_iterations`` budget on a BACKWARD/SELF
conditional route is a CONVERGENCE LIMIT, not a fatal error: the dispatch loop stops
looping but proceeds FORWARD to the step after the loop (here: ``done``), exactly as
if the gate had returned "done". This is NOT "silently swallowed" — the same visible
``budget_aborted`` event (``dimension == "loop_iterations"``) still fires after exactly
``loop_max_iterations`` (3, per the fixture's own ``route.loop_max_iterations: 3``)
retry passes.

[A14 fix] A tripped cap alone is a WARNING, not a terminal verdict: ``done`` (the step
after the loop) still runs and produces a real, non-empty deliverable, so the eventual
``pipeline_complete`` reports the cap message additively on ``warnings`` and stays a
CLEAN completion (no ``status="degraded"``, no ``degraded_reason``) — the same honesty
bar a resolved deliverable + zero agent failures gets everywhere else. Before this fix
the mere presence of the (suppressed, non-fatal) cap unconditionally flipped ``status``
to "degraded" regardless of what ran afterward — see
``test_loop_cap_warning_not_degraded.py`` for the deliverable-missing counter-case
(cap trips AND the run ends with nothing to show for it → still "degraded").

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

_PIPELINE = "ex_A1_loop"


def _always_retry_scripts_for(agent_id: str) -> list[_ScriptedTurn]:
    """Per-agent scripted turns: ``check`` ALWAYS answers retry; everything else is inert."""
    if agent_id == "custom-agent:check":
        return [_ScriptedTurn(texts=['{"decision": "retry"}'], usage=(5, 3))]
    return [_ScriptedTurn(texts=[f"{agent_id} default output."], usage=(5, 3))]


@pytest.mark.asyncio
async def test_always_retry_stops_looping_but_completes_cleanly_with_a_warning():
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
    completes = [e for e in events if e.get("type") == "pipeline_complete"]

    print("EVENT TYPES:", types)
    print("AGENT_START agent_ids:", started)
    print("BUDGET_ABORTED events:", budget_events)

    # ── The load-bearing assertions (convergence-limit fix) ────────────────
    # The budget_aborted event is STILL emitted (never swallowed) — fail-closed on
    # visibility, not on the run.
    assert len(budget_events) == 1, (
        f"expected exactly one budget_aborted event (the cap is still enforced, "
        f"just no longer fatal), got {len(budget_events)}. Events: {types}"
    )
    assert budget_events[0]["data"].get("dimension") == "loop_iterations", budget_events[0]

    # The run must NOT be thrown away: it proceeds forward past the loop and reaches
    # a terminal pipeline_complete rather than aborting.
    assert len(completes) == 1, (
        f"{_PIPELINE} did not reach pipeline_complete after the loop cap stopped "
        f"the retry loop — the run was aborted instead of continuing forward. "
        f"Events: {types}"
    )
    # [A14 fix] ``done`` produced a real deliverable and nothing failed — a
    # suppressed loop-cap alone must NOT flip the run to "degraded".
    assert completes[0]["data"].get("status") != "degraded", (
        "a suppressed loop-cap convergence limit must not, by itself, degrade a "
        f"run whose deliverable resolved cleanly: {completes[0]['data']}"
    )
    assert not completes[0]["data"].get("degraded_reason"), (
        f"a clean completion must carry no degraded_reason: {completes[0]['data']}"
    )
    # The cap message is still recorded — just as a WARNING, not a verdict.
    assert completes[0]["data"].get("warnings"), (
        f"the suppressed loop-cap message was dropped entirely: {completes[0]['data']}"
    )

    # 'done' is the step immediately after the loop in array order — the dispatch
    # loop must advance to it, exactly as if check's gate had returned "ok".
    assert "custom-agent:done" in started, (
        f"'done' never ran despite the loop cap stopping the retry loop — the run "
        f"did not continue forward past the loop. started={started}"
    )
