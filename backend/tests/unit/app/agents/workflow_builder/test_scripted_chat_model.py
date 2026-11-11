"""Unit tests for ``tests/fakes/scripted_chat_model.py``.

The fake is test infrastructure for the builder's turn tests (tasks 15.7 to 15.9 and
22.x), so these tests check it from the outside: first as a plain chat model, then
inside a real ``DeepAgentRunner`` (the way ``build_builder_runner`` uses it).
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool

from app.agents.deep_agent_runner import DeepAgentRunner
from tests.fakes.scripted_chat_model import (
    FakeChatModel,
    ModelTurn,
    ScriptedToolCall,
    ScriptedUsage,
    ScriptExhaustedError,
)


@tool
def echo(text: str) -> str:
    """Return the text it is given."""
    return f"echo:{text}"


def _runner(model: FakeChatModel) -> DeepAgentRunner:
    return DeepAgentRunner("sys", [echo], model=model, exclude_builtin_tools=True)


async def _events(runner: DeepAgentRunner) -> list[dict[str, Any]]:
    return [event async for event in runner.astream_events("go")]


async def test_astream_merges_pieces_when_a_turn_has_text_calls_and_usage():
    model = FakeChatModel(
        turns=(
            ModelTurn(
                text=("Hel", "lo"),
                tool_calls=(ScriptedToolCall("echo", {"text": "a"}, "c1"),),
                usage=ScriptedUsage(10, 5),
            ),
        )
    )

    message = await model.ainvoke([HumanMessage("hi")])

    assert isinstance(message, AIMessage)
    assert message.content == "Hello"
    assert [(c["name"], c["args"], c["id"]) for c in message.tool_calls] == [
        ("echo", {"text": "a"}, "c1")
    ]
    assert message.usage_metadata is not None
    assert message.usage_metadata["input_tokens"] == 10
    assert message.usage_metadata["output_tokens"] == 5


def test_invoke_returns_the_turn_when_called_synchronously():
    model = FakeChatModel(turns=(ModelTurn(text=("sync",)),))

    message = model.invoke([HumanMessage("hi")])

    assert message.content == "sync"


def test_invoke_numbers_call_ids_when_a_call_has_no_id():
    model = FakeChatModel(
        turns=(
            ModelTurn(
                tool_calls=(
                    ScriptedToolCall("echo", {"text": "a"}),
                    ScriptedToolCall("echo", {"text": "b"}),
                )
            ),
        )
    )

    message = model.invoke([HumanMessage("hi")])

    assert [c["id"] for c in message.tool_calls] == ["call_0_0", "call_0_1"]


def test_invoke_raises_script_exhausted_when_called_past_the_script():
    model = FakeChatModel(turns=(ModelTurn(text=("only",)),))
    model.invoke([HumanMessage("hi")])

    with pytest.raises(ScriptExhaustedError):
        model.invoke([HumanMessage("again")])


def test_invoke_replays_the_last_turn_when_repeat_last_is_set():
    model = FakeChatModel(turns=(ModelTurn(text=("again",)),), repeat_last=True)

    contents = [model.invoke([HumanMessage("hi")]).content for _ in range(3)]

    assert contents == ["again", "again", "again"]


def test_invoke_records_the_messages_each_call_received():
    model = FakeChatModel(turns=(ModelTurn(text=("a",)), ModelTurn(text=("b",))))

    model.invoke([HumanMessage("one")])
    model.invoke([HumanMessage("two")])

    assert model.call_count == 2
    assert [m[0].content for m in model.calls] == ["one", "two"]


def test_bind_tools_records_names_when_tools_are_objects_and_dicts():
    model = FakeChatModel()

    bound = model.bind_tools([echo, {"type": "function", "function": {"name": "x"}}])

    assert bound is model
    assert model.bound_tool_names == ["echo", "x"]


async def test_astream_events_yields_thinking_tool_text_and_usage_when_run_in_a_runner():
    model = FakeChatModel(
        turns=(
            ModelTurn(
                thinking=("hm ", "ok"),
                tool_calls=(ScriptedToolCall("echo", {"text": "a"}, "c1"),),
                usage=ScriptedUsage(
                    100, 20, cache_read_tokens=40, cache_write_tokens=5
                ),
            ),
            ModelTurn(text=("done",), usage=ScriptedUsage(7, 3)),
        )
    )

    events = await _events(_runner(model))

    kinds = [e["type"] for e in events]
    assert "".join(e["thinking"] for e in events if e["type"] == "thinking") == "hm ok"
    assert [(e["tool"], e["result"]) for e in events if e["type"] == "tool_result"] == [
        ("echo", "echo:a")
    ]
    assert "".join(e["chunk"] for e in events if e["type"] == "chunk") == "done"
    assert kinds.index("tool_result") < kinds.index("chunk")
    usage = [e for e in events if e["type"] == "usage"]
    assert len(usage) == 2
    assert usage[0]["input_tokens"] == 105
    assert usage[0]["cache_read_tokens"] == 40
    assert usage[0]["cache_write_tokens"] == 5
    assert usage[0]["output_tokens"] == 20
    assert "echo" in model.bound_tool_names


async def test_astream_events_yields_an_error_event_after_the_pieces_when_a_turn_has_an_error():
    model = FakeChatModel(turns=(ModelTurn(text=("part",), error=ValueError("boom")),))

    events = await _events(_runner(model))

    kinds = [e["type"] for e in events]
    assert "".join(e["chunk"] for e in events if e["type"] == "chunk") == "part"
    assert kinds[-1] == "error"
    assert events[-1]["error"] == "boom"
    assert "usage" not in kinds


async def test_astream_events_yields_only_an_error_event_when_an_error_turn_has_no_pieces():
    model = FakeChatModel(turns=(ModelTurn(error=ValueError("early")),))

    events = await _events(_runner(model))

    assert [e["type"] for e in events] == ["error"]
    assert events[0]["error"] == "early"


async def test_ainvoke_waits_for_the_delay_when_a_turn_has_one():
    model = FakeChatModel(turns=(ModelTurn(text=("slow",), delay=0.05),))

    loop = asyncio.get_running_loop()
    started = loop.time()
    await model.ainvoke([HumanMessage("hi")])

    assert loop.time() - started >= 0.04
