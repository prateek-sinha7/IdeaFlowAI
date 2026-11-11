"""A failed tool call reaches the model with advice, through a REAL compiled agent graph.

``test_tool_recovery.py`` drives the middleware hooks directly. This one proves the wiring:
``DeepAgentRunner`` attaches the middleware, LangGraph's ToolNode routes a tool result
through it on the async path, and the NEXT model call sees the recovery note.

The tool below stands in for a Playwright tool: it returns failure text and never raises
(ADR-0036), which is exactly the shape the framework could not previously tell from a result.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool

from app.agents.deep_agent_runner import DeepAgentRunner
from tests.agents._scripted_model import ScriptedFakeChatModel, _ScriptedTurn

_NAV_FAILURE = "navigation timeout or failed: Page.goto: net::ERR_FILE_NOT_FOUND at file:///x/p.html?r=3"


class _Recorder(ScriptedFakeChatModel):
    """Scripted model that also records the messages of every call."""

    def __init__(self, turns, seen, **kwargs):
        super().__init__(turns, **kwargs)
        object.__setattr__(self, "_seen", seen)

    def _stream(self, messages, *args, **kwargs):
        self._seen.append(list(messages))
        return super()._stream(messages, *args, **kwargs)


def _failing_navigate():
    @tool
    def playwright_navigate(url: str) -> str:
        """Open a page."""
        return _NAV_FAILURE

    return playwright_navigate


async def _run(tools, *, recover: bool = True) -> list[list]:
    seen: list[list] = []
    model = _Recorder(
        [
            _ScriptedTurn(
                texts=["Opening the page. "],
                tool_calls=[
                    ("playwright_navigate", '{"url": "prototype.html?r=3"}', "call-1")
                ],
            ),
            _ScriptedTurn(texts=["Done."]),
        ],
        seen,
    )
    runner = DeepAgentRunner(
        "sys",
        tools,
        model=model,
        exclude_builtin_tools=True,
        thread_id="run-1:custom-agent:e2e-tester",
        recover_tool_failures=recover,
    )
    _ = [event async for event in runner.astream_events("test it")]
    return seen


def _tool_messages(call: list) -> list[ToolMessage]:
    return [m for m in call if isinstance(m, ToolMessage)]


@pytest.mark.asyncio
async def test_next_model_call_sees_recovery_advice_when_a_tool_returns_failure_text():
    seen = await _run([_failing_navigate()])

    follow_up = _tool_messages(seen[1])
    assert len(follow_up) == 1
    text = follow_up[0].content
    assert text.startswith("navigation timeout or failed")
    assert "[tool recovery] playwright_navigate failed (argument)" in text
    assert follow_up[0].status == "error"


@pytest.mark.asyncio
async def test_next_model_call_sees_the_bare_failure_when_recovery_is_off():
    seen = await _run([_failing_navigate()], recover=False)

    follow_up = _tool_messages(seen[1])
    assert follow_up[0].content == _NAV_FAILURE
    assert follow_up[0].status != "error"
