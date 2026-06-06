"""Runner output capture must survive a no-stream model turn (Bedrock no-chunk case).

ROOT-CAUSE GUARD
----------------
``DeepAgentRunner`` builds its output ONLY from ``on_chat_model_stream`` deltas
(yielded as ``chunk`` events and accumulated into ``full_output`` / the terminal
``done`` event). On Bedrock a model turn can surface ``on_chat_model_end`` with
the full assistant message but NO ``on_chat_model_stream`` deltas — leaving
``full_output`` empty. The engine then joins zero chunks → ``output == ""`` → a
Human review gate (``prototype-specify`` / ``prototype-plan``) opens with BLANK
content (the user sees Approve/Reject with nothing to review).

The runner must fall back to the ``on_chat_model_end`` message content when a
turn streamed no text. These tests reproduce the no-delta turn with a
non-streaming model and assert the content still reaches both the live ``chunk``
stream and the terminal ``done`` output — while ``usage`` (already read off
``on_chat_model_end``) keeps working.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.agents.deep_agent_runner import DeepAgentRunner

SPEC_TEXT = "<spec>\n## Pages\n- Dashboard (KPIs)\n- Settings\n</spec>"


class _GenerateOnlyModel(BaseChatModel):
    """A model that returns its message via ``_generate`` only (no ``_stream``).

    With ``disable_streaming=True`` LangChain delegates ``.astream()`` to
    ``.ainvoke()``, so inside ``astream_events`` the turn fires
    ``on_chat_model_start``/``on_chat_model_end`` but NO ``on_chat_model_stream``
    — exactly the Bedrock no-delta case. The message carries no tool calls, so a
    text-only agent ends after one turn.
    """

    model_config = {"arbitrary_types_allowed": True}

    def __init__(self, content: str, **kwargs: Any) -> None:
        super().__init__(disable_streaming=True, **kwargs)
        object.__setattr__(self, "_content", content)

    @property
    def _llm_type(self) -> str:
        return "generate-only-fake"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "_GenerateOnlyModel":
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:  # type: ignore[override]
        msg = AIMessage(
            content=self._content,
            usage_metadata={"input_tokens": 5, "output_tokens": 7, "total_tokens": 12},
        )
        return ChatResult(generations=[ChatGeneration(message=msg)])


async def _collect(runner: DeepAgentRunner) -> list[dict]:
    return [ev async for ev in runner.astream_events("produce the spec")]


def _make_runner(thread: str) -> DeepAgentRunner:
    return DeepAgentRunner(
        system_prompt="You are a text agent. Output the spec.",
        tools=[],
        model=_GenerateOnlyModel(SPEC_TEXT),
        exclude_builtin_tools=True,
        thread_id=thread,
    )


@pytest.mark.asyncio
async def test_no_stream_turn_still_produces_done_output():
    events = await _collect(_make_runner("runner-fallback-done"))
    done = [e for e in events if e.get("type") == "done"]
    assert done, f"expected a terminal 'done' event; got {[e.get('type') for e in events]}"
    assert SPEC_TEXT in done[-1]["output"], (
        f"done.output lost the model content (no-stream turn): {done[-1]['output']!r}"
    )


@pytest.mark.asyncio
async def test_no_stream_turn_still_surfaces_a_chunk():
    # The engine assembles agent output from `chunk` events, and the live UI
    # renders them — so the content must surface as a chunk even with no deltas.
    events = await _collect(_make_runner("runner-fallback-chunk"))
    chunk_text = "".join(e["chunk"] for e in events if e.get("type") == "chunk")
    assert SPEC_TEXT in chunk_text, f"no chunk carried the content: {chunk_text!r}"


@pytest.mark.asyncio
async def test_usage_still_emitted_on_no_stream_turn():
    events = await _collect(_make_runner("runner-fallback-usage"))
    usage = [e for e in events if e.get("type") == "usage"]
    assert usage, "usage must still be emitted from on_chat_model_end"
    assert usage[-1]["output_tokens"] == 7
