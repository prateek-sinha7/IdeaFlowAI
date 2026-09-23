"""Regression: a conditional gate's untaken outcome target must NOT be reported
skipped while a later route can still loop back and reach it.

``ex_test_loop_reachable_skip`` (agents/workflows/ex_test_loop_reachable_skip/workflow.yaml):

    0. worker
    1. verdict       pass 1 "bad" -> revise, pass 2 "good" -> finish
    2. revise
    3. revise-route  always "rechecked" -> worker (loop back)
    4. finish

Before the fix, choosing "bad" reported the sibling target ``finish`` skipped
the moment the route resolved — then pass 2 ran it, and the UI had already
greyed it out. Only a step that no later route can come back to is skipped.
"""

from __future__ import annotations

import pytest

from tests.agents import _scripted_model as _sm
from tests.agents._scripted_model import _ScriptedTurn, _drive

_PIPELINE = "ex_test_loop_reachable_skip"
_VERDICT = "custom-agent:verdict"
_REVISE_ROUTE = "custom-agent:revise-route"


def _make_scripts():
    calls: dict[str, int] = {}

    def _scripts_for(agent_id: str) -> list[_ScriptedTurn]:
        n = calls.get(agent_id, 0)
        calls[agent_id] = n + 1
        if agent_id == _VERDICT:
            # First pass "bad", every later pass "good". Correct whether the
            # harness builds one model per invocation (``n`` advances) or one
            # model for the whole run (the turn list advances).
            turns = ['{"decision": "bad"}', '{"decision": "good"}'][n:] or ['{"decision": "good"}']
            return [_ScriptedTurn(texts=[t], usage=(5, 3)) for t in turns]
        if agent_id == _REVISE_ROUTE:
            return [_ScriptedTurn(texts=['{"decision": "rechecked"}'], usage=(5, 3))]
        return [_ScriptedTurn(texts=[f"{agent_id} default output."], usage=(5, 3))]

    return _scripts_for


async def _drive_loop():
    orig = _sm._scripts_for
    _sm._scripts_for = _make_scripts()
    try:
        return await _drive(_PIPELINE)
    finally:
        _sm._scripts_for = orig


@pytest.mark.asyncio
async def test_branch_target_reachable_by_a_later_loop_is_not_skipped():
    events = await _drive_loop()

    started = [e["data"].get("agent_id") for e in events if e.get("type") == "agent_start"]
    skipped = [e["data"].get("agent_id") for e in events if e.get("type") == "agent_skipped"]

    print("AGENT_START:", started)
    print("AGENT_SKIPPED:", skipped)

    assert started.count(_VERDICT) == 2, f"verdict should run twice (bad, then good): {started}"
    assert "custom-agent:revise" in started
    assert "custom-agent:finish" in started, f"finish must run on pass 2: {started}"
    assert "custom-agent:finish" not in skipped, (
        "finish was reported skipped when 'bad' was chosen, although the revise "
        f"loop could (and did) come back and reach it: skipped={skipped}"
    )
    assert skipped == [], f"nothing in this workflow is ever unreachable: {skipped}"
