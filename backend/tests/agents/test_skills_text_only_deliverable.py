"""spec 011 / D-02 verify gate — text-only agent + attached skill deliverable safety.

61 of 87 agents are text-only (``tools: []``): they have never had filesystem tools,
and their deliverable is resolved from their STREAMED TEXT (the engine builds each
agent's authoritative output by joining ``chunk`` events — see
``agents/execution_engine/engine.py``'s ``output = "".join(output_chunks)`` and the
``streamed_text`` deliverable resolver, which reads exactly that joined string back
off ``ctx.last_streamed``).

Under the new skills design (``agents/factory.py::create_runner``), a run with staged
skills (``delivery.staged``) grants EVERY agent — including text-only ones — the full
native filesystem tool set (read AND write), so it can carry out a skill's procedure
rather than merely read it. This is D-02's accepted risk: a text-only agent, now
holding ``write_file``, might write its answer to a file instead of streaming it,
producing an EMPTY authoritative output/deliverable while the run still "succeeds" —
a silent, severe regression.

This module drives ``create_runner`` directly (offline, scripted model — no network),
mirroring the wiring pattern in ``tests/agents/test_create_runner.py``:
  1. ``test_text_only_agent_with_skill_streams_nonempty_deliverable`` — the realistic
     good case: a text-only agent (``domain-analyst``), in a run with a skill attached
     (so it is granted the full fs tool set and the anti-fabrication
     ``_NO_TOOLS_PREAMBLE`` is suppressed), streams normal text and produces a
     NON-EMPTY authoritative output.
  2. ``test_text_only_agent_writing_file_instead_of_streaming_yields_empty_deliverable``
     — the failure mode: the same agent/setup, but the scripted model calls
     ``write_file`` and streams nothing. The assertion below was written AFTER running
     this test and observing the actual outcome (see the docstring on that test for
     what was observed) — it is not a guess.
"""

from __future__ import annotations

import json
from typing import Any, Iterator

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.messages.tool import tool_call_chunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

from agents.factory import AgentContext, create_runner


# ===========================================================================
# Scripted fake chat model (recording bind_tools) — same recipe as
# tests/agents/test_create_runner.py / tests/agents/_scripted_model.py.
# ===========================================================================


class _ScriptedTurn:
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
    """Minimal ``BaseChatModel`` that streams scripted turns and records the tool
    names it is offered on each ``bind_tools`` call (the "what does the model see"
    probe, used to confirm the full fs tool grant)."""

    model_config = {"arbitrary_types_allowed": True}

    def __init__(self, turns: list[_ScriptedTurn], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        object.__setattr__(self, "_turns", list(turns))
        object.__setattr__(self, "_call_index", 0)
        object.__setattr__(self, "_bind_calls", [])

    @property
    def _llm_type(self) -> str:
        return "scripted-fake-chat-model"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "_ScriptedFakeChatModel":
        names: list[str] = []
        for t in tools:
            if isinstance(t, dict):
                names.append(t.get("name"))
            else:
                names.append(getattr(t, "name", None))
        self._bind_calls.append(names)
        return self

    @property
    def recorded_tool_names(self) -> set[str]:
        out: set[str] = set()
        for call in self._bind_calls:
            out.update(n for n in call if n)
        return out

    def _next_turn(self) -> _ScriptedTurn:
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
        pieces = turn.texts if turn.texts else [""]
        last_i = len(pieces) - 1
        for i, piece in enumerate(pieces):
            extra: dict[str, Any] = {}
            tcc: list = []
            usage = None
            if i == last_i:
                for tc_idx, (name, json_args, call_id) in enumerate(turn.tool_calls):
                    tcc.append(
                        tool_call_chunk(name=name, args=json_args, id=call_id, index=tc_idx)
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
        chunks = list(self._stream(messages, stop=stop, run_manager=run_manager, **kwargs))
        text = "".join(c.message.content for c in chunks if isinstance(c.message.content, str))
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])


# ===========================================================================
# Helpers
# ===========================================================================


async def _collect_events(runner: Any, message: str) -> list[dict[str, Any]]:
    return [event async for event in runner.astream_events(message)]


def _accumulated_output(events: list[dict[str, Any]]) -> str:
    """The authoritative per-agent output the ENGINE would compute: joining every
    streamed ``chunk`` event (``agents/execution_engine/engine.py``'s
    ``output = "".join(output_chunks)``, fed straight into the ``streamed_text``
    deliverable resolver via ``ctx.last_streamed``)."""
    return "".join(e["chunk"] for e in events if e["type"] == "chunk")


def _attached_skill() -> list[dict]:
    """One minimal user-attached skill payload (the shape ``stage_skills`` expects:
    ``{"id"/"name", "content"}``); staging this is what flips
    ``exclude_builtin_tools`` False for a text-only agent (spec 011)."""
    return [
        {
            "id": "domain-analysis-procedure",
            "name": "Domain Analysis Procedure",
            "content": "Follow the standard domain-analysis checklist step by step.",
        }
    ]


# ===========================================================================
# Test 1 — good case: text-only agent + attached skill streams a non-empty
# deliverable (the full fs tool grant does not, by itself, break streaming).
# ===========================================================================


@pytest.mark.asyncio
async def test_text_only_agent_with_skill_streams_nonempty_deliverable(tmp_path, monkeypatch) -> None:
    """domain-analyst (``tools: []``) in a run WITH a skill attached: the skill
    staging grants the full native fs tool set (``exclude_builtin_tools=False``)
    and suppresses the anti-fabrication ``_NO_TOOLS_PREAMBLE`` — confirmed via the
    composed system prompt and the tool names offered to the model. The agent
    streams normal text (no tool calls, the realistic good case), and the
    engine-equivalent accumulated output (deliverable) is non-empty.
    """
    monkeypatch.setattr("app.core.config.settings.RUNS_ROOT", str(tmp_path))

    fake = _ScriptedFakeChatModel(
        [_ScriptedTurn(texts=["Fintech is a large, growing market. "], usage=(9, 6))]
    )
    ctx = AgentContext(
        user_request="analyze fintech",
        model=fake,
        user_id="u-skill-text",
        run_id="run-skill-text",
        attached_skills=_attached_skill(),
    )
    runner = create_runner("domain-analyst", ctx)

    # The anti-fabrication preamble is suppressed — skills present ⇒ the agent is
    # never told "you have NO tools" while it actually holds write_file.
    assert "## Tool Availability" not in runner.system_prompt  # _NO_TOOLS_PREAMBLE suppressed

    events = await _collect_events(runner, "go")

    assert [e for e in events if e["type"] == "error"] == []

    # PROOF — the model was offered the native fs tools (write_file included),
    # even though this agent declares tools: [] (text-only).
    assert {"write_file", "read_file", "edit_file", "ls"} <= fake.recorded_tool_names

    # PROOF — the deliverable survives: the streamed text is non-empty.
    output = _accumulated_output(events)
    assert output != ""
    assert output == "Fintech is a large, growing market. "


# ===========================================================================
# Test 2 — failure mode: the model calls write_file and streams nothing.
# ===========================================================================


@pytest.mark.asyncio
async def test_text_only_agent_writing_file_instead_of_streaming_yields_empty_deliverable(
    tmp_path, monkeypatch
) -> None:
    """OBSERVED BEHAVIOR (spec 011 D-02) — run FIRST, assertion written to match.

    Same agent/setup as the good-case test above (domain-analyst, tools: [],
    skill attached ⇒ full fs tool grant), but the scripted model calls
    ``write_file`` on its only turn and streams NO text at all (both the tool
    turn and the model's own message content are empty).

    Observed: ``DeepAgentRunner.astream_events`` never yields a ``chunk`` event
    for this turn (the runner's no-delta fallback only fires when the model's
    end-of-turn message content is non-empty, and a pure tool-call turn's
    message content is empty) — the accumulated output is the empty string.
    Since the engine builds each agent's authoritative deliverable from exactly
    this joined ``chunk`` stream (``streamed_text`` strategy reads
    ``ctx.last_streamed`` == that join), a text-only agent that answers by
    writing a file instead of streaming DOES produce an EMPTY deliverable — the
    run has no error, no gate, no exception, and no non-empty output. This is
    the genuine D-02 regression risk; it is NOT mitigated by anything on this
    path today.
    """
    monkeypatch.setattr("app.core.config.settings.RUNS_ROOT", str(tmp_path))

    fake = _ScriptedFakeChatModel(
        [
            _ScriptedTurn(
                texts=[""],
                tool_calls=[
                    (
                        "write_file",
                        json.dumps({"file_path": "/answer.md", "content": "Fintech is large."}),
                        "call_wf_1",
                    )
                ],
                usage=(9, 6),
            ),
            _ScriptedTurn(texts=[""], usage=(2, 0)),
        ]
    )
    ctx = AgentContext(
        user_request="analyze fintech",
        model=fake,
        user_id="u-skill-text-2",
        run_id="run-skill-text-2",
        attached_skills=_attached_skill(),
    )
    runner = create_runner("domain-analyst", ctx)

    events = await _collect_events(runner, "go")

    assert [e for e in events if e["type"] == "error"] == []

    # The write_file call really fired through the graph (not a no-op stub).
    write_calls = [e for e in events if e["type"] == "tool_call" and e["tool"] == "write_file"]
    assert len(write_calls) == 1

    # THE FINDING: no chunk events were streamed at all, so the engine-equivalent
    # accumulated output — the authoritative deliverable for a streamed_text-class
    # agent — is empty. This is the D-02 regression this test exists to catch.
    output = _accumulated_output(events)
    assert [e for e in events if e["type"] == "chunk"] == []
    assert output == ""
