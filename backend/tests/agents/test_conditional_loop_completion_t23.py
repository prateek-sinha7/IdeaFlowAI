"""T23 (spec 014 / Phase 3 dispatch loop): ``ex_A1_loop`` (A1, the
loop fixture) driven end-to-end via the shared offline scripted-model harness
(``tests.agents._scripted_model._drive``), with the ``check`` step scripted to answer
``{"decision": "retry"}`` on its first two dispatches, then ``{"decision": "ok"}`` on its
third.

Confirms the "loops N times then completes" half of AC-03 (spec.md §6):

    "A run whose conditional gate resolves to a `trigger: step` outcome pointing at an
    earlier step re-executes that step and everything after it, within the SAME run id,
    up to `loop_max_iterations` times before failing closed."

T24 (``test_conditional_loop_budget_t24.py``) already proves the fail-CLOSED half (an
always-retry run raises ``budget_aborted`` at the cap); this test proves the complementary
happy-path half — a bounded number of loop-backs (2, one less than the fixture's declared
``loop_max_iterations: 3``) still lets the run complete NORMALLY once the decision resolves
to ``"ok"``. Asserts: ``greet`` and ``check`` each dispatch exactly 3 times (the initial pass
plus the two retry loop-backs), ``done`` dispatches exactly once, and the run reaches
``pipeline_complete`` with no ``budget_aborted`` event — 3 total passes never exceeds the
cap of 3 (R-07: the visit-count check fires BEFORE a jump proceeds, so exactly-at-cap is not
an off-by-one over-cap).

No live LLM: the model is fully scripted offline (``ScriptedFakeChatModel``), matching the
recipe every other ``tests/agents/_scripted_model.py``-based suite uses. ``check``'s per-call
decision is supplied by locally monkeypatching ``_scripted_model._scripts_for`` for the
duration of the test (restored in ``finally``) — the shared per-agent-id registry has no
static branch that varies its answer BY CALL NUMBER, so this override closes over a small
per-test call counter (the same recipe T24 documents for a step needing a decision the
static registry cannot express, adapted here from "always the same answer" to "count-gated").
"""

from __future__ import annotations

import pytest

from tests.agents import _scripted_model as _sm
from tests.agents._scripted_model import _ScriptedTurn, _drive

_PIPELINE = "ex_A1_loop"


def _make_scripts_for():
    """Build a fresh ``_scripts_for`` override with its OWN call counter: ``check``
    answers ``retry`` on its first two calls and ``ok`` on its third (and any further)
    call; everything else is inert. A fresh closure per test means each invocation
    starts counting from zero (no cross-test leakage via shared state)."""
    calls = {"check": 0}

    def _fn(agent_id: str) -> list[_ScriptedTurn]:
        if agent_id == "custom-agent:check":
            calls["check"] += 1
            decision = "retry" if calls["check"] <= 2 else "ok"
            return [_ScriptedTurn(texts=[f'{{"decision": "{decision}"}}'], usage=(5, 3))]
        return [_ScriptedTurn(texts=[f"{agent_id} default output."], usage=(5, 3))]

    return _fn


@pytest.mark.asyncio
async def test_retry_twice_then_ok_completes_normally():
    orig_scripts_for = _sm._scripts_for
    _sm._scripts_for = _make_scripts_for()
    try:
        events = await _drive(_PIPELINE)
    finally:
        _sm._scripts_for = orig_scripts_for

    assert events, f"{_PIPELINE} produced no events"

    types = [e.get("type") for e in events]
    started = [e["data"].get("agent_id") for e in events if e.get("type") == "agent_start"]

    print("EVENT TYPES:", types)
    print("AGENT_START agent_ids:", started)

    # ── The load-bearing assertions (T23 / AC-03 happy-path half) ───────────
    assert started.count("custom-agent:greet") == 3, (
        f"expected 'greet' to dispatch 3 times (the initial pass plus the two "
        f"retry loop-backs), got {started.count('custom-agent:greet')}. started={started}"
    )
    assert started.count("custom-agent:check") == 3, (
        f"expected 'check' to dispatch 3 times (once per pass through the loop), "
        f"got {started.count('custom-agent:check')}. started={started}"
    )
    assert started.count("custom-agent:done") == 1, (
        f"expected 'done' to run exactly once after the third pass resolved 'ok', "
        f"got {started.count('custom-agent:done')}. started={started}"
    )
    assert "budget_aborted" not in types, (
        f"run failed closed despite only 2 loop-back passes against "
        f"loop_max_iterations=3 (should have completed normally). Events: {types}"
    )
    assert "pipeline_complete" in types, (
        f"run never reached pipeline_complete after the third pass resolved 'ok'; "
        f"got {types[-5:]}"
    )
