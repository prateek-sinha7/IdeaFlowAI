"""Unit tests for ``agents/capabilities/gates/conditional.py`` — the ``end`` outcome.

A conditional gate that matches a ``trigger: end`` outcome returns ``GATE_ROUTE`` with
``trigger == "end"`` so the dispatch loop can finish the run. A decision that matches
nothing and has no ``default_next`` must still BLOCK (ISS-170): ``end`` is how the happy
path is declared, not a loosening of the fail-closed rule.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agents.capabilities.gates.base import GATE_BLOCK, GATE_ROUTE
from agents.capabilities.gates.conditional import ConditionalGate
from agents.workflows.plan import RouteOutcome, RouteSpec


def _ctx(reply: str):
    """A ctx whose ``runner`` serves ``reply`` as the decision source's artifact."""
    events: list[tuple] = []

    async def _record(step, gate, outcome, detail):
        events.append((step, gate, outcome, detail))

    runner = SimpleNamespace(
        latest_typed_content=lambda _source: reply,
        record_gate_event=_record,
    )
    return SimpleNamespace(runner=runner), events


def _loop_step(*, default_next: str | None = None):
    route = RouteSpec(
        outcomes={
            "pass": RouteOutcome(trigger="end", target=""),
            "revise": RouteOutcome(
                trigger="step", target="screen-planner", feedback="fix it"
            ),
        },
        default_next=default_next,
    )
    return SimpleNamespace(agent_id="custom-agent:e2e-tester", route=route)


@pytest.mark.asyncio
async def test_evaluate_returns_route_end_when_decision_matches_an_end_outcome():
    ctx, events = _ctx('{"decision": "pass"}')

    outcome = await ConditionalGate().evaluate(_loop_step(), ctx)

    assert outcome.outcome == GATE_ROUTE
    assert outcome.detail["trigger"] == "end"
    assert outcome.detail["decision"] == "pass"
    assert events[0][2] == GATE_ROUTE


@pytest.mark.asyncio
async def test_evaluate_lists_other_step_targets_as_skipped_when_decision_ends_the_run():
    """Every other ``step`` outcome is, by definition, not walked on this pass."""
    ctx, _events = _ctx('{"decision": "pass"}')

    outcome = await ConditionalGate().evaluate(_loop_step(), ctx)

    assert outcome.detail["skipped_targets"] == ["screen-planner"]


@pytest.mark.asyncio
async def test_evaluate_still_routes_a_step_outcome_when_decision_is_revise():
    ctx, _events = _ctx('Analysis first.\n{"decision": "revise"}')

    outcome = await ConditionalGate().evaluate(_loop_step(), ctx)

    assert outcome.outcome == GATE_ROUTE
    assert outcome.detail["trigger"] == "step"
    assert outcome.detail["target"] == "screen-planner"


@pytest.mark.asyncio
async def test_evaluate_blocks_when_decision_matches_nothing_and_no_default_next():
    """ISS-170 stays closed: an unknown decision is a refusal, never a quiet success."""
    ctx, _events = _ctx('{"decision": "passed"}')

    outcome = await ConditionalGate().evaluate(_loop_step(), ctx)

    assert outcome.outcome == GATE_BLOCK
    assert outcome.detail["reason"] == "no matching route outcome and no default_next"
