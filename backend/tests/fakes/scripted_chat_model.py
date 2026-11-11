"""Scripted chat model for the workflow builder's turn tests.

``FakeChatModel`` is a real :class:`langchain_core.language_models.BaseChatModel`.
A test hands it to ``DeepAgentRunner`` (through ``BuilderTurnInputs.chat_model``),
and the runner uses it verbatim, so the whole agent loop, the middleware, the tools
and the event translation run unmodified with no network.

What it plays back is a list of :class:`ModelTurn`, one per model call, in order.
A turn can carry any mix of:

- ``thinking``: extended-thinking pieces, streamed as ``{"type": "thinking"}``
  content blocks (the ChatAnthropic shape that ``deepagents`` runner reads);
- ``text``: answer pieces;
- ``tool_calls``: :class:`ScriptedToolCall` entries, streamed as tool-call chunks;
- ``usage``: a :class:`ScriptedUsage`, reported in the shape ``langchain_aws``
  uses (cache reads and writes folded into ``input_tokens`` and split out in
  ``input_token_details``);
- ``error``: an exception raised after the pieces above have streamed. With no
  pieces it is raised before the first token;
- ``delay``: seconds to wait before the turn starts (async paths only). Use
  milliseconds to simulate a slow model, or a large value to simulate a hang that a
  cancel or a time cap must end.

When the script runs out, the next call raises :class:`ScriptExhaustedError`, so a
test that under-scripts a loop fails loudly. ``repeat_last=True`` replays the last
turn instead, for tests that need a model that never stops calling tools.

Every call is recorded: ``calls`` holds a copy of the messages the model received,
``bound_tool_names`` the tool names the agent bound. Nothing here asserts.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessageChunk, BaseMessage
from langchain_core.messages.tool import tool_call_chunk
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from pydantic import ConfigDict, PrivateAttr

__all__ = [
    "FakeChatModel",
    "ModelTurn",
    "ScriptExhaustedError",
    "ScriptedToolCall",
    "ScriptedUsage",
]


class ScriptExhaustedError(AssertionError):
    """The model was called more times than its script has turns."""


@dataclass(frozen=True)
class ScriptedToolCall:
    """One tool call the scripted model makes.

    Attributes:
        name: Tool name.
        args: Tool arguments. Serialised to JSON when streamed.
        call_id: Tool call id. ``None`` gives ``call_<turn>_<position>``.
    """

    name: str
    args: Mapping[str, Any]
    call_id: str | None = None


@dataclass(frozen=True)
class ScriptedUsage:
    """Token counts for one model call.

    ``input_tokens`` is the uncached input. The fake folds the cache counts into the
    reported ``input_tokens`` the way ``langchain_aws`` does, so the production
    usage conversion splits them out again.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


def _no_pieces() -> tuple[str, ...]:
    return ()


def _no_calls() -> tuple[ScriptedToolCall, ...]:
    return ()


@dataclass(frozen=True)
class ModelTurn:
    """What the model does on one call. See the module docstring."""

    thinking: tuple[str, ...] = ()
    text: tuple[str, ...] = ()
    tool_calls: tuple[ScriptedToolCall, ...] = ()
    usage: ScriptedUsage | None = None
    error: BaseException | None = None
    delay: float = 0.0


def _tool_name(tool: Any) -> str:
    """Name of a bound tool, whatever form the agent passed it in."""
    if isinstance(tool, Mapping):
        function = tool.get("function")
        if isinstance(function, Mapping) and "name" in function:
            return str(function["name"])
        return str(tool.get("name", ""))
    return str(getattr(tool, "name", None) or getattr(tool, "__name__", ""))


def _usage_metadata(usage: ScriptedUsage) -> dict[str, Any]:
    folded = usage.input_tokens + usage.cache_read_tokens + usage.cache_write_tokens
    return {
        "input_tokens": folded,
        "output_tokens": usage.output_tokens,
        "total_tokens": folded + usage.output_tokens,
        "input_token_details": {
            "cache_read": usage.cache_read_tokens,
            "cache_creation": usage.cache_write_tokens,
        },
    }


class FakeChatModel(BaseChatModel):
    """Plays back ``turns``, one per model call. No network.

    Attributes:
        turns: The script.
        repeat_last: Replay the last turn when the script has run out, instead of
            raising :class:`ScriptExhaustedError`.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    turns: tuple[ModelTurn, ...] = ()
    repeat_last: bool = False

    _next_index: int = PrivateAttr(default=0)
    _calls: list[list[BaseMessage]] = PrivateAttr(default_factory=list)
    _bound_tool_names: list[str] = PrivateAttr(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "fake-scripted-chat-model"

    @property
    def calls(self) -> list[list[BaseMessage]]:
        """A copy of the messages each call received, oldest call first."""
        return [list(messages) for messages in self._calls]

    @property
    def call_count(self) -> int:
        """Number of model calls so far."""
        return len(self._calls)

    @property
    def bound_tool_names(self) -> list[str]:
        """Names of the tools the agent bound, in the order bound."""
        return list(self._bound_tool_names)

    def bind_tools(self, tools: Any, **kwargs: Any) -> FakeChatModel:
        """Record the tool names and return ``self``; the script ignores them."""
        self._bound_tool_names = [_tool_name(tool) for tool in tools]
        return self

    def _begin_call(self, messages: list[BaseMessage]) -> tuple[int, ModelTurn]:
        index = self._next_index
        if index < len(self.turns):
            turn = self.turns[index]
        elif self.repeat_last and self.turns:
            turn = self.turns[-1]
        else:
            raise ScriptExhaustedError(
                f"FakeChatModel was called {index + 1} times but has "
                f"{len(self.turns)} scripted turn(s)"
            )
        self._next_index = index + 1
        self._calls.append(list(messages))
        return index, turn

    @staticmethod
    def _chunks(index: int, turn: ModelTurn) -> list[ChatGenerationChunk]:
        """The generation chunks of one turn. The last carries calls and usage.

        An error turn gets only its thinking and text pieces: it never reports
        calls or usage, and the caller raises the error after the last piece.
        """
        failing = turn.error is not None
        contents: list[str | list[dict[str, Any]]] = [
            [{"type": "thinking", "thinking": piece}] for piece in turn.thinking
        ]
        # Text goes out as blocks when thinking is present, so every chunk of the
        # turn has the same content shape and merges cleanly.
        for piece in turn.text:
            contents.append(
                [{"type": "text", "text": piece}] if turn.thinking else piece
            )
        if not contents and not failing:
            contents.append("")
        last = len(contents) - 1
        chunks: list[ChatGenerationChunk] = []
        for position, content in enumerate(contents):
            if position != last or failing:
                chunks.append(
                    ChatGenerationChunk(message=AIMessageChunk(content=content))
                )
                continue
            call_chunks = [
                tool_call_chunk(
                    name=call.name,
                    args=json.dumps(dict(call.args)),
                    id=call.call_id or f"call_{index}_{n}",
                    index=n,
                )
                for n, call in enumerate(turn.tool_calls)
            ]
            usage = _usage_metadata(turn.usage) if turn.usage is not None else None
            chunks.append(
                ChatGenerationChunk(
                    message=AIMessageChunk(
                        content=content,
                        tool_call_chunks=call_chunks,
                        usage_metadata=usage,  # type: ignore[arg-type]
                        chunk_position="last",
                    )
                )
            )
        return chunks

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        index, turn = self._begin_call(messages)
        if turn.error is not None:
            # An error turn streams its pieces, then raises.
            yield from self._chunks(index, turn)
            raise turn.error
        yield from self._chunks(index, turn)

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        index, turn = self._begin_call(messages)
        if turn.delay:
            await asyncio.sleep(turn.delay)
        if turn.error is not None:
            for chunk in self._chunks(index, turn):
                yield chunk
            raise turn.error
        for chunk in self._chunks(index, turn):
            yield chunk

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        merged: ChatGenerationChunk | None = None
        async for chunk in self._astream(messages, stop=stop, run_manager=run_manager):
            merged = chunk if merged is None else merged + chunk
        return ChatResult(
            generations=[
                merged or ChatGenerationChunk(message=AIMessageChunk(content=""))
            ]
        )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        merged: ChatGenerationChunk | None = None
        for chunk in self._stream(messages, stop=stop, run_manager=run_manager):
            merged = chunk if merged is None else merged + chunk
        return ChatResult(
            generations=[
                merged or ChatGenerationChunk(message=AIMessageChunk(content=""))
            ]
        )
