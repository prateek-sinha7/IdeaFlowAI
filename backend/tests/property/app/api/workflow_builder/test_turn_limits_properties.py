"""Property tests for the builder turn limits.

# Feature: ai-workflow-builder, Property 16: Limits warn once and stop at the cap

For any number of tool calls and any sequence of token-usage events,
``limit_warning`` for each kind is sent exactly once when 80 % is first reached,
the agent's limit notice is appended exactly once per kind, the call after the
cap is refused and stops the turn, and a configured token budget stops the turn
when it is reached.

**Validates: Requirements 28.4, 28.7, 28.8, 28.9, 47.8**

Tool calls drive ``BuilderToolObserverMiddleware`` with ``FakeTurnPort``. Token
usage drives ``_on_usage`` from ``app.api.workflow_builder.turns`` with a real
``LiveTurn``. Time is held at zero so the time limit never fires. Nothing touches
a database, the network or a model.
"""

from __future__ import annotations

import asyncio
import math
from types import SimpleNamespace
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage

from app.agents.workflow_builder.events import (
    BuilderEvent,
    LimitWarning,
    ToolFinished,
)
from app.agents.workflow_builder.middleware import (
    TOOL_LIMIT_MESSAGE,
    BuilderToolObserverMiddleware,
)
from app.agents.workflow_builder.ports import TurnLimits
from app.api.workflow_builder.turns import LiveTurn, TurnRunState, _on_usage
from tests.fakes.builder_turn import FakeTurnPort

_FRACTION = 0.8
_NOTICE = "[builder]"


def _request(call_id: str) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": "ls", "args": {}, "id": call_id, "type": "tool_call"},
        tool=None,
        state={},
        runtime=None,  # type: ignore[arg-type]
    )


class _Handler:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, request: ToolCallRequest) -> ToolMessage:
        self.calls += 1
        return ToolMessage(
            content="ok", tool_call_id=request.tool_call["id"] or "", name="ls"
        )


async def _drive_tool_calls(
    cap: int, calls: int
) -> tuple[FakeTurnPort, _Handler, list[ToolMessage]]:
    turn = FakeTurnPort(
        limits=TurnLimits(
            timeout_seconds=3600,
            max_tool_calls=cap,
            max_gate_rejections=2,
            warning_fraction=_FRACTION,
        )
    )
    middleware = BuilderToolObserverMiddleware(turn, elapsed_seconds=lambda: 0.0)
    handler = _Handler()
    results: list[ToolMessage] = []
    for index in range(calls):
        result = await middleware.awrap_tool_call(_request(f"c{index}"), handler)
        assert isinstance(result, ToolMessage)
        results.append(result)
    return turn, handler, results


def _warnings(events: list[BuilderEvent], kind: str) -> list[LimitWarning]:
    return [e for e in events if isinstance(e, LimitWarning) and e.kind == kind]


@settings(max_examples=100, deadline=None)
@given(cap=st.integers(1, 80), calls=st.integers(0, 160))
def test_tool_call_limit_warns_once_and_refuses_after_cap(cap: int, calls: int) -> None:
    # Feature: ai-workflow-builder, Property 16: Limits warn once and stop at the cap
    turn, handler, results = asyncio.run(_drive_tool_calls(cap, calls))

    point = max(1, math.ceil(round(cap * _FRACTION, 6)))
    reached = min(calls, cap) >= point

    warnings = _warnings(turn.events, "tool_calls")
    assert len(warnings) == (1 if reached else 0)
    if warnings:
        assert warnings[0].limit == cap
        assert warnings[0].used == point

    noticed = [r for r in results if _NOTICE in str(r.content)]
    assert len(noticed) == (1 if reached else 0)

    assert handler.calls == min(calls, cap)
    refused = [
        e for e in turn.events if isinstance(e, ToolFinished) and e.status == "refused"
    ]
    assert len(refused) == max(0, calls - cap)
    assert turn.stop_reasons == ["tool_calls"] * max(0, calls - cap)
    if calls > cap:
        assert results[cap].content.startswith(TOOL_LIMIT_MESSAGE)  # type: ignore[union-attr]


def _drive_usage(
    budget: int, increments: list[tuple[int, int]]
) -> tuple[LiveTurn, list[Any]]:
    turn = LiveTurn(
        session_id="s",
        turn_id="t",
        user_message_id="m",
        user_id="u",
        model_id="model",
        effort=None,
    )
    emitted: list[Any] = []
    runner = SimpleNamespace(
        live=turn,
        limits=TurnLimits(
            timeout_seconds=3600,
            max_tool_calls=60,
            max_gate_rejections=2,
            warning_fraction=_FRACTION,
            token_budget=budget,
        ),
        emit=emitted.append,
    )
    run = TurnRunState()
    for tokens_in, tokens_out in increments:
        _on_usage(
            runner,  # type: ignore[arg-type]
            run,
            {"input_tokens": tokens_in, "output_tokens": tokens_out},
        )
    return turn, emitted


@settings(max_examples=100, deadline=None)
@given(
    budget=st.integers(1, 5000),
    increments=st.lists(
        st.tuples(st.integers(0, 800), st.integers(0, 800)), max_size=30
    ),
)
def test_token_budget_warns_once_and_stops_when_reached(
    budget: int, increments: list[tuple[int, int]]
) -> None:
    # Feature: ai-workflow-builder, Property 16: Limits warn once and stop at the cap
    turn, emitted = _drive_usage(budget, increments)

    totals: list[int] = []
    running = 0
    for tokens_in, tokens_out in increments:
        running += tokens_in + tokens_out
        totals.append(running)

    warnings = [e for e in emitted if isinstance(e, LimitWarning)]
    in_warning_band = any(_FRACTION * budget <= t < budget for t in totals)
    assert len(warnings) == (1 if in_warning_band else 0)
    for warning in warnings:
        assert warning.kind == "tokens"
        assert warning.limit == budget
        assert _FRACTION * budget <= warning.used < budget

    assert (turn.stop_reason == "tokens") == any(t >= budget for t in totals)
