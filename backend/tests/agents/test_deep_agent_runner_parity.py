"""Phase-1 verify gate — streamed event-vocabulary parity between the legacy
``app.agents.deep_agent.DeepAgent`` and the new
``app.agents.deep_agent_runner.DeepAgentRunner`` (spec
``specs/002-deepagents-migration/plan.md`` → Phase 1 "Verify gate", task #29).

WHAT THIS PROVES
----------------
The migration swaps a hand-rolled ReAct loop (legacy ``DeepAgent``) for an
adapter over the LangChain ``deepagents`` graph (``DeepAgentRunner``). The
engine (``agents/execution_engine/engine.py:742-832``) consumes the agent purely
through its *streamed event vocabulary*; the UI is built from those events. The
migration's headline invariant is "visuals identical". This module drives BOTH
implementations over the **same scripted model behaviour** (no network, no
credentials) and asserts the streamed events are equivalent on every axis the
engine actually reads.

Parity is asserted on event **type/semantics**, NOT on byte-identical chunking:
the legacy yields text per loop-iteration while the runner yields per LangGraph
token, so consecutive ``chunk`` events are collapsed into one text blob before
comparison (the plan explicitly states parity is on type/semantics). Everything
the engine reads off the stream — chunk text (concatenated), summed token usage,
tool name, tool args, tool-result tool-name, the ordered event-TYPE sequence,
and (text-only path) the single terminal ``TokenUsage`` — is asserted equal.

THE SCRIPTED FAKE MODEL (proven recipe — stock LangChain fakes do NOT work)
---------------------------------------------------------------------------
``GenericFakeChatModel`` / ``FakeMessagesListChatModel`` cannot drive this code:
they raise on ``bind_tools`` and their ``_stream`` drops ``tool_calls`` /
``usage_metadata``. :class:`_ScriptedFakeChatModel` is a minimal
``BaseChatModel`` that:
  * streams a DIFFERENT scripted turn on each successive model invocation (turn
    1 = text + a tool call; turn 2 = final text), tracked by an internal index —
    both the legacy ``.stream()`` loop and the deepagents graph consume turns in
    order;
  * carries ``usage_metadata`` on the FINAL chunk of each turn;
  * carries ``tool_call_chunks`` (via ``tool_call_chunk(...)``) on a tool turn;
  * marks each turn's final chunk with ``chunk_position="last"``.

The ``chunk_position="last"`` flag is load-bearing and NOT a hack: langchain-core
1.4.0's ``BaseChatModel.stream()`` appends a synthetic trailing **empty** chunk
(``usage_metadata=None``) after the provider's chunks *unless* the last real
chunk already sets ``chunk_position`` (see ``BaseChatModel.stream`` source — the
``if yielded and ... and not chunk.message.chunk_position`` guard). The legacy
``astream_with_usage`` reads usage off *the last chunk it saw*; without the flag
that last chunk is the synthetic empty one and usage reads as 0. Real streaming
providers set the terminal-chunk marker, so setting it here makes the fake
behave like a real provider rather than papering over anything.

INJECTION
---------
  * Legacy: construct ``DeepAgent`` normally (construction is credential-free —
    it builds, but never calls, a Bedrock client), then overwrite
    ``agent.llm_with_tools = fake``. The legacy uses ``self.llm_with_tools.stream``,
    which routes through ``BaseChatModel._stream`` on the fake. The SAME ``tools``
    list is passed to the constructor so ``tool_map`` can execute the tool.
  * Runner: inject ``model=<fake>`` (bypasses ``build_model`` entirely → offline).
    Pass the SAME ``tools`` + an ``InMemorySaver`` + a ``thread_id``. No
    ``interrupt_on`` → ``_hitl_armed`` is False → no gate path is exercised.

ONE DOCUMENTED, NON-MASKING DIVERGENCE (``tool_result.result`` string)
----------------------------------------------------------------------
The ``tool_result`` event's ``tool`` name, and the meaningful tool output, are
equal on both sides. The raw ``result`` STRING is NOT byte-identical:
  * legacy: ``str(tool.invoke(args))``           → ``"✓ done"``  (the raw return)
  * runner: ``str(on_tool_end.data["output"])``  → ``"content='✓ done'
    name='report_task_complete' tool_call_id='call_1'"`` (deepagents/langgraph
    hand ``on_tool_end`` a ``ToolMessage``; ``str(ToolMessage)`` is its repr).
The runner stringifies a ``ToolMessage`` exactly as the plan prescribes
(plan §5 table: ``result=str(data.output)``; runner docstring line ~304), so this
is the adapter behaving to spec, not a coding mistake. The meaningful payload is
preserved — the legacy ``result`` equals the runner ``ToolMessage.content`` and
is a substring of the runner ``result``. We therefore assert that **semantic**
equivalence (content recoverable on both) with strict checks, rather than a
byte-equal ``==`` we know would be false, and we do NOT silently relax it. The
byte-level difference is surfaced as a Phase-1 finding for the migration owners
(the engine forwards ``result[:500]`` to the UI ``tool_result`` payload; the
``report_task_complete`` *sentinel* keys on the tool **name**, so it is
unaffected — but the on-screen result text for tools would differ). See the
report accompanying task #29.
"""

from __future__ import annotations

import json
from typing import Any, Iterator

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.messages.tool import tool_call_chunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from app.agents.base import TokenUsage
from app.agents.deep_agent import DeepAgent
from app.agents.deep_agent_runner import DeepAgentRunner


# ===========================================================================
# Scripted fake chat model
# ===========================================================================


class _ScriptedTurn:
    """One scripted model invocation: text piece(s), optional tool call(s), usage.

    ``tool_calls`` items are ``(name, json_args_str, call_id)`` tuples (args are a
    JSON *string*, mirroring how providers emit ``tool_call_chunks``). ``usage`` is
    an ``(input_tokens, output_tokens)`` tuple or ``None``.
    """

    def __init__(
        self,
        texts: list[str],
        tool_calls: list[tuple[str, str, str]] | None = None,
        usage: tuple[int, int] | None = None,
    ) -> None:
        self.texts = texts
        self.tool_calls = tool_calls or []
        self.usage = usage


class _ScriptedFakeChatModel(BaseChatModel):
    """Minimal ``BaseChatModel`` that streams a different scripted turn per call.

    Drives BOTH the legacy ``.stream()`` loop and the deepagents graph. See the
    module docstring for why the stock LangChain fakes are unusable here and why
    ``chunk_position="last"`` on each turn's final chunk is required.
    """

    # We stash non-pydantic call state via object.__setattr__, so allow it.
    model_config = {"arbitrary_types_allowed": True}

    def __init__(self, turns: list[_ScriptedTurn], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # Bypass pydantic's field machinery for the mutable call cursor + script.
        object.__setattr__(self, "_turns", list(turns))
        object.__setattr__(self, "_call_index", 0)

    @property
    def _llm_type(self) -> str:
        return "scripted-fake-chat-model"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "_ScriptedFakeChatModel":
        # No-op: the fake already scripts its own tool calls. (Stock fakes raise
        # NotImplementedError here, which is exactly why this subclass exists.)
        return self

    def _next_turn(self) -> _ScriptedTurn:
        """Return the next scripted turn, advancing the per-instance cursor.

        Both consumers (legacy loop + graph) call the model once per turn and
        consume turns in order; past the script we repeat the last turn so a
        stray extra call can never IndexError the test.
        """
        idx: int = self._call_index
        turns: list[_ScriptedTurn] = self._turns
        turn = turns[idx] if idx < len(turns) else turns[-1]
        object.__setattr__(self, "_call_index", idx + 1)
        return turn

    def _stream(
        self,
        messages: list,
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        turn = self._next_turn()
        # Always yield at least one chunk (covers a hypothetical tool-only turn
        # with no text); the final chunk carries tool_call_chunks + usage and is
        # marked chunk_position="last" so core does not append a synthetic empty
        # trailing chunk (which would null out the legacy's last-chunk usage read).
        pieces = turn.texts if turn.texts else [""]
        last_i = len(pieces) - 1
        for i, piece in enumerate(pieces):
            extra: dict[str, Any] = {}
            tcc: list = []
            usage = None
            if i == last_i:
                for idx, (name, json_args, call_id) in enumerate(turn.tool_calls):
                    tcc.append(
                        tool_call_chunk(name=name, args=json_args, id=call_id, index=idx)
                    )
                if turn.usage is not None:
                    t_in, t_out = turn.usage
                    usage = {
                        "input_tokens": t_in,
                        "output_tokens": t_out,
                        "total_tokens": t_in + t_out,
                    }
                extra["chunk_position"] = "last"
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content=piece,
                    tool_call_chunks=tcc,
                    usage_metadata=usage,
                    **extra,
                )
            )

    def _generate(
        self,
        messages: list,
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        # Fallback non-streaming path (in case any code hits .invoke/.generate
        # instead of streaming). Collapses the scripted turn into a single message.
        chunks = list(self._stream(messages, stop=stop, run_manager=run_manager, **kwargs))
        text = "".join(c.message.content for c in chunks if isinstance(c.message.content, str))
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])


# ===========================================================================
# The tool both sides execute (same instance passed to both constructors)
# ===========================================================================


@tool
def report_task_complete(summary: str) -> str:
    """Report that the assigned task is complete."""
    return "✓ done"


# ===========================================================================
# Scripts
# ===========================================================================


def _script_case_a() -> list[_ScriptedTurn]:
    """Tool-using sequence: turn 1 text + tool call (usage 11/7); turn 2 final text (13/5)."""
    return [
        _ScriptedTurn(
            texts=["working "],
            tool_calls=[("report_task_complete", json.dumps({"summary": "x"}), "call_1")],
            usage=(11, 7),
        ),
        _ScriptedTurn(texts=["all done"], usage=(13, 5)),
    ]


def _script_case_b() -> list[_ScriptedTurn]:
    """Text-only single turn: 'hello ' + 'world', usage 9/4."""
    return [_ScriptedTurn(texts=["hello ", "world"], usage=(9, 4))]


# ===========================================================================
# Builders — inject the SAME fake script into each implementation
# ===========================================================================


def _build_legacy(script: list[_ScriptedTurn], tools: list) -> DeepAgent:
    """Construct the legacy DeepAgent and overwrite its bound LLM with the fake.

    Construction is credential-free: with no ANTHROPIC_API_KEY the constructor
    builds a ChatBedrockConverse client object (no network call), which we
    immediately replace. The fake's ``.stream()`` is ``BaseChatModel._stream``.
    """
    agent = DeepAgent(system_prompt="You are a test agent.", tools=tools)
    agent.llm_with_tools = _ScriptedFakeChatModel(script)
    return agent


def _build_runner(
    script: list[_ScriptedTurn], tools: list, *, exclude_builtin_tools: bool = False
) -> DeepAgentRunner:
    """Construct the new DeepAgentRunner with the fake injected as ``model=``.

    Bypasses ``build_model`` (so no provider/creds needed). An InMemorySaver +
    thread_id are harmless: without ``interrupt_on`` the runner's ``_hitl_armed``
    is False, so the post-loop gate path (``aget_state``) is never taken.
    """
    return DeepAgentRunner(
        system_prompt="You are a test agent.",
        tools=tools,
        model=_ScriptedFakeChatModel(script),
        checkpointer=InMemorySaver(),
        thread_id="parity-test-thread",
        exclude_builtin_tools=exclude_builtin_tools,
    )


# ===========================================================================
# Collection helpers
# ===========================================================================


async def _collect_events(agent: Any, message: str) -> list[dict[str, Any]]:
    """Drain ``astream_events`` into a list of event dicts."""
    return [event async for event in agent.astream_events(message)]


async def _collect_with_usage(agent: Any, message: str) -> list[Any]:
    """Drain ``astream_with_usage`` into a list (text chunks then one TokenUsage)."""
    return [item async for item in agent.astream_with_usage(message)]


def _normalized_types(events: list[dict[str, Any]]) -> list[str]:
    """Ordered event-TYPE sequence with consecutive ``chunk`` events collapsed to one.

    Chunk granularity legitimately differs (legacy per-iteration vs runner
    per-token); parity is on type/semantics, so a run of ``chunk`` events counts
    once. All other event types are preserved in order.
    """
    out: list[str] = []
    for e in events:
        t = e["type"]
        if t == "chunk" and out and out[-1] == "chunk":
            continue
        out.append(t)
    return out


def _chunk_text(events: list[dict[str, Any]]) -> str:
    return "".join(e["chunk"] for e in events if e["type"] == "chunk")


def _usage_sums(events: list[dict[str, Any]]) -> tuple[int, int]:
    in_sum = sum(e.get("input_tokens", 0) for e in events if e["type"] == "usage")
    out_sum = sum(e.get("output_tokens", 0) for e in events if e["type"] == "usage")
    return in_sum, out_sum


def _events_of(events: list[dict[str, Any]], etype: str) -> list[dict[str, Any]]:
    return [e for e in events if e["type"] == etype]


# ===========================================================================
# Case A — tool-using sequence: astream_events parity
# ===========================================================================


@pytest.mark.asyncio
async def test_case_a_tool_sequence_event_parity() -> None:
    """Legacy and runner emit the same event vocabulary for a tool-call turn.

    Asserts (all on the engine-relevant axes):
      * identical normalized ordered event-TYPE sequence
        ``[chunk, usage, tool_call, tool_result, chunk, usage, done]``;
      * identical concatenated ``chunk`` text (``"working all done"``);
      * identical summed token usage (in: 11+13=24, out: 7+5=12);
      * identical ``tool_call`` tool name + args;
      * identical ``tool_result`` tool name + meaningful payload (content), with
        the documented byte-level ``result`` divergence handled explicitly
        (see module docstring) — NOT silently weakened.
    """
    legacy_events = await _collect_events(
        _build_legacy(_script_case_a(), [report_task_complete]), "go"
    )
    runner_events = await _collect_events(
        _build_runner(_script_case_a(), [report_task_complete]), "go"
    )

    expected_types = ["chunk", "usage", "tool_call", "tool_result", "chunk", "usage", "done"]
    legacy_types = _normalized_types(legacy_events)
    runner_types = _normalized_types(runner_events)

    # Both sides reach the exact expected ordered type sequence (no documented
    # ordering nuance was needed — the legacy and the graph order identically).
    assert legacy_types == expected_types, f"legacy types {legacy_types}"
    assert runner_types == expected_types, f"runner types {runner_types}"
    assert legacy_types == runner_types

    # Concatenated chunk text identical.
    assert _chunk_text(legacy_events) == "working all done"
    assert _chunk_text(runner_events) == "working all done"
    assert _chunk_text(legacy_events) == _chunk_text(runner_events)

    # Summed usage identical (11+13 in, 7+5 out).
    assert _usage_sums(legacy_events) == (24, 12)
    assert _usage_sums(runner_events) == (24, 12)
    assert _usage_sums(legacy_events) == _usage_sums(runner_events)

    # tool_call: same tool name + same args on both.
    legacy_tc = _events_of(legacy_events, "tool_call")
    runner_tc = _events_of(runner_events, "tool_call")
    assert len(legacy_tc) == len(runner_tc) == 1
    assert legacy_tc[0]["tool"] == runner_tc[0]["tool"] == "report_task_complete"
    assert legacy_tc[0]["args"] == runner_tc[0]["args"] == {"summary": "x"}

    # tool_result: same tool name on both; meaningful payload preserved on both.
    legacy_tr = _events_of(legacy_events, "tool_result")
    runner_tr = _events_of(runner_events, "tool_result")
    assert len(legacy_tr) == len(runner_tr) == 1
    assert legacy_tr[0]["tool"] == runner_tr[0]["tool"] == "report_task_complete"

    # The tool *output* is "✓ done" on both, BYTE-IDENTICAL. The runner extracts
    # the ToolMessage's ``.content`` (task #32), so its ``result`` is the tool's raw
    # return — exactly the legacy ``str(result)``. This is the string the engine
    # forwards into the UI ``tool_result`` payload, so the on-screen text matches.
    assert legacy_tr[0]["result"] == runner_tr[0]["result"] == "✓ done"


# ===========================================================================
# Case B — text-only astream_with_usage parity
# ===========================================================================


@pytest.mark.asyncio
async def test_case_b_text_only_astream_with_usage_parity() -> None:
    """Text-only agents (tools=[]) yield identical chunks + one matching TokenUsage.

    Both sides must yield the text chunks (concatenation ``"hello world"``)
    followed by exactly ONE ``TokenUsage``; the two ``TokenUsage`` objects must
    have equal ``input_tokens`` (9), ``output_tokens`` (4), ``total_tokens`` (13).

    Only input/output/total are asserted — NOT the cache fields. The runner
    leaves cache counts at 0 (its usage comes from ``on_chat_model_end`` which
    surfaces no cache counts); the legacy may populate them from the last chunk.
    The engine's text-only consumer (``engine.py:825-827``) reads only
    ``input_tokens`` / ``output_tokens``, so cache fields are immaterial to parity.
    """
    legacy_items = await _collect_with_usage(_build_legacy(_script_case_b(), []), "go")
    runner_items = await _collect_with_usage(
        _build_runner(_script_case_b(), [], exclude_builtin_tools=True), "go"
    )

    # Split each stream into text chunks and TokenUsage objects.
    def split(items: list[Any]) -> tuple[list[str], list[TokenUsage]]:
        texts = [x for x in items if not isinstance(x, TokenUsage)]
        usages = [x for x in items if isinstance(x, TokenUsage)]
        return texts, usages

    legacy_texts, legacy_usages = split(legacy_items)
    runner_texts, runner_usages = split(runner_items)

    # Text chunks: same concatenation on both.
    assert "".join(legacy_texts) == "hello world"
    assert "".join(runner_texts) == "hello world"
    assert "".join(legacy_texts) == "".join(runner_texts)

    # Exactly ONE TokenUsage, and it is the final item, on both sides.
    assert len(legacy_usages) == 1, f"legacy yielded {len(legacy_usages)} TokenUsage"
    assert len(runner_usages) == 1, f"runner yielded {len(runner_usages)} TokenUsage"
    assert isinstance(legacy_items[-1], TokenUsage)
    assert isinstance(runner_items[-1], TokenUsage)

    legacy_usage, runner_usage = legacy_usages[0], runner_usages[0]

    # Assert ONLY input/output/total (NOT cache fields).
    assert legacy_usage.input_tokens == runner_usage.input_tokens == 9
    assert legacy_usage.output_tokens == runner_usage.output_tokens == 4
    assert legacy_usage.total_tokens == runner_usage.total_tokens == 13
