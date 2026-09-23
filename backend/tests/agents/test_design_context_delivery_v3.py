"""tests/agents/test_design_context_delivery_v3.py — GAPS T2: does ``.context/``
actually hold the design references, and does a staged skill reach a migrated
(``prompt_policy: body_only``) agent?

WHY THIS FILE EXISTS. A real Bedrock ``prototype`` run showed ``.context/``
missing ``design/craft.md`` and an empty ``skills/`` directory. Investigation
(see the GAPS journal) found both explained by that run's own selections
(no-template mode -> craft is legitimately empty; later steps prune the
per-step skill directory of the one step that declared it) rather than a
delivery defect. This file pins the THREE properties the investigation
confirmed hold, so a real regression in any of them is caught:

  1. When a template AND a design system ARE selected, every file the
     Sandbox Reading Guide promises actually lands under ``.context/design/``.
  2. A migrated (``prompt_policy: body_only``) agent's ``read_file`` tool can
     read those files — the sandbox write path and the runner's tool grant are
     independent of prompt_policy.
  3. A skill staged for a step (``Step.skills`` -> ``ctx.step_skills`` ->
     ``stage_skills``) is discoverable by that SAME agent even though it is
     ``body_only`` — deepagents' ``SkillsMiddleware`` is bound via
     ``create_deep_agent(skills=...)`` independently of the composed
     ``system_prompt`` string ``prompt_policy`` governs, so body_only stripping
     the (already-vestigial, never-populated) "skills" prompt-block slot does
     NOT stop the library's own skills advertisement from reaching the model.

Uses ``prototype-specify`` throughout — the real agent from the observed run
(``prompt_policy: body_only``, ``tools: []``, ``injects: [template,
design_system, images]``, the step commit 77046158e attached
``velocity-design`` to).

Sandbox fixture modeled on ``tests/agents/test_commit_primitive.py::_make_sandbox``.
Scripted-model recipe modeled on ``tests/agents/test_create_runner.py``.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Iterator

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.messages.tool import tool_call_chunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

from agents.factory import AgentContext, create_runner
from agents.loader import load_agent_spec
from app.agents.sandbox import RunSandbox
from app.api.launch_context import write_od_context_to_sandbox

# ---------------------------------------------------------------------------
# Sandbox fixture (modeled on test_commit_primitive.py::_make_sandbox)
# ---------------------------------------------------------------------------


def _run_id() -> str:
    return f"design-ctx-test-{uuid.uuid4().hex[:8]}"


def _make_sandbox(tmp_path: Path, *, run_id: str | None = None) -> RunSandbox:
    """A RunSandbox on real disk, no git (this suite never commits)."""
    sb = RunSandbox("test-user", run_id or _run_id(), runs_root=str(tmp_path), has_git=False)
    sb.ensure()
    return sb


def _od_context_with_template() -> dict:
    """A full selection: a template AND a design system, both non-empty, plus
    a non-empty craft block -- the complement of the observed run's
    no-template selection, which is what makes craft.md absent legitimately."""
    return {
        "template_id": "web-prototype",
        "template_name": "Web Prototype",
        "template_body": "# Web Prototype Template\n\nHero + feature triplet.",
        "ds_id": "apple",
        "ds_name": "Apple",
        "ds_body": "# Apple Design System\n\n--accent: #0071e3;",
        "craft_block": "## craft/motion\n\nUse restrained, purposeful motion.",
        "no_template": False,
        "is_design_system_required": None,
    }


# ---------------------------------------------------------------------------
# Scripted model (proven recipe — tests/agents/test_create_runner.py) plus a
# message-capture hook so the exact SystemMessage a skill's advertisement is
# appended to is inspectable (proves "discoverable", not just "staged").
# ---------------------------------------------------------------------------


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
    model_config = {"arbitrary_types_allowed": True}

    def __init__(self, turns: list[_ScriptedTurn], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        object.__setattr__(self, "_turns", list(turns))
        object.__setattr__(self, "_call_index", 0)
        object.__setattr__(self, "recorded_messages", [])  # one entry per _stream call

    @property
    def _llm_type(self) -> str:
        return "scripted-fake-chat-model"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "_ScriptedFakeChatModel":
        return self

    def _next_turn(self) -> _ScriptedTurn:
        idx: int = self._call_index
        turns: list[_ScriptedTurn] = self._turns
        turn = turns[idx] if idx < len(turns) else turns[-1]
        object.__setattr__(self, "_call_index", idx + 1)
        return turn

    def _stream(
        self, messages: list, stop: list[str] | None = None, run_manager: Any = None, **kwargs: Any
    ) -> Iterator[ChatGenerationChunk]:
        self.recorded_messages.append(list(messages))
        turn = self._next_turn()
        pieces = turn.texts if turn.texts else [""]
        last_i = len(pieces) - 1
        for i, piece in enumerate(pieces):
            extra: dict[str, Any] = {}
            tcc: list = []
            usage = None
            if i == last_i:
                for tc_idx, (name, json_args, call_id) in enumerate(turn.tool_calls):
                    tcc.append(tool_call_chunk(name=name, args=json_args, id=call_id, index=tc_idx))
                if turn.usage is not None:
                    t_in, t_out = turn.usage
                    usage = {"input_tokens": t_in, "output_tokens": t_out, "total_tokens": t_in + t_out}
                extra["chunk_position"] = "last"
            yield ChatGenerationChunk(
                message=AIMessageChunk(content=piece, tool_call_chunks=tcc, usage_metadata=usage, **extra)
            )

    def _generate(
        self, messages: list, stop: list[str] | None = None, run_manager: Any = None, **kwargs: Any
    ) -> ChatResult:
        chunks = list(self._stream(messages, stop=stop, run_manager=run_manager, **kwargs))
        text = "".join(c.message.content for c in chunks if isinstance(c.message.content, str))
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])


async def _collect_events(runner: Any, message: str) -> list[dict[str, Any]]:
    return [event async for event in runner.astream_events(message)]


_READ_FILE_TOOL = "read_file"


# ===========================================================================
# Property 1 — `.context/design/` holds the files the Sandbox Reading Guide
# names, when a template AND a design system are selected.
# ===========================================================================


def test_context_design_holds_template_ds_and_craft_files(tmp_path):
    sb = _make_sandbox(tmp_path)
    od_context = _od_context_with_template()

    write_od_context_to_sandbox(sb, od_context, explicit_selection=True)

    assert json.loads(sb.read(".context/selections.json"))["template_id"] == "web-prototype"
    assert sb.read(".context/design/design-system.md") == od_context["ds_body"]
    assert sb.read(".context/design/craft.md") == od_context["craft_block"]
    assert sb.read(".context/design/template/SKILL.md") == od_context["template_body"]


# ===========================================================================
# Property 2 — a migrated (`prompt_policy: body_only`) agent's `read_file`
# tool can actually read those files back off disk.
# ===========================================================================


@pytest.mark.asyncio
async def test_migrated_body_only_agent_reads_design_context(tmp_path):
    spec = load_agent_spec("prototype-specify")
    assert spec.prompt_policy == "body_only", "fixture assumption: the real observed agent"

    sb = _make_sandbox(tmp_path)
    od_context = _od_context_with_template()
    write_od_context_to_sandbox(sb, od_context, explicit_selection=True)

    fake = _ScriptedFakeChatModel(
        [
            _ScriptedTurn(
                texts=[""],
                tool_calls=[
                    (
                        _READ_FILE_TOOL,
                        json.dumps({"file_path": "/.context/design/design-system.md"}),
                        "call_read_ds",
                    )
                ],
                usage=(5, 3),
            ),
            _ScriptedTurn(texts=["<spec>ok</spec>"], usage=(2, 0)),
        ]
    )
    ctx = AgentContext(user_request="build it", model=fake, user_id="u-ctx", run_id=sb.run_id)

    runner = create_runner("prototype-specify", ctx, run_sandbox=sb)
    events = await _collect_events(runner, "go")

    results = [e for e in events if e["type"] == "tool_result" and e["tool"] == _READ_FILE_TOOL]
    assert len(results) == 1
    # The native read_file tool returns `cat -n`-numbered lines, not the raw
    # bytes back verbatim -- assert the written content is actually IN there.
    assert "Apple Design System" in results[0]["result"]
    assert "--accent: #0071e3;" in results[0]["result"]


# ===========================================================================
# Property 3 — a skill staged for THIS step (Step.skills -> ctx.step_skills,
# the production path commit 77046158e wired for prototype-specify) is
# discoverable by the agent that declared it, even though it is body_only.
# ===========================================================================


@pytest.mark.asyncio
async def test_staged_skill_is_discoverable_by_the_declaring_body_only_agent(tmp_path):
    spec = load_agent_spec("prototype-specify")
    assert spec.prompt_policy == "body_only"

    sb = _make_sandbox(tmp_path)
    # Seed the template SKILL.md the velocity-design skill's {{INJECT_FROM:...}}
    # marker points at, so staging resolves real content (not the empty-fallback
    # comment) -- the full production chain, not just the discoverability half.
    write_od_context_to_sandbox(sb, _od_context_with_template(), explicit_selection=True)

    fake = _ScriptedFakeChatModel([_ScriptedTurn(texts=["<spec>ok</spec>"], usage=(3, 1))])
    ctx = AgentContext(
        user_request="build it",
        model=fake,
        user_id="u-skill",
        run_id=sb.run_id,
        step_skills=["velocity-design"],
    )

    from app.agents import deep_agent_runner as dar

    captured: dict[str, Any] = {}
    original_create_deep_agent = dar.create_deep_agent

    def _spy(*args: Any, **kwargs: Any) -> Any:
        captured.update(kwargs)
        return original_create_deep_agent(*args, **kwargs)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(dar, "create_deep_agent", _spy)
        runner = create_runner("prototype-specify", ctx, run_sandbox=sb)
        await _collect_events(runner, "go")

    # a) the library's SkillsMiddleware was actually constructed for this
    #    body_only agent -- prompt_policy does not gate the `skills=` kwarg.
    assert captured.get("skills") == ["/skills"]

    # b) the skill is staged on disk with resolved (not fallback) content.
    assert ctx.skills_delivery.staged == ["velocity-design"]
    staged_body = sb.read("skills/velocity-design/SKILL.md")
    assert "Hero + feature triplet." in staged_body

    # c) the model's first request actually carries the skill's advertisement
    #    -- proof of "discoverable", not merely "written to disk".
    first_call_messages = fake.recorded_messages[0]
    combined = "\n".join(str(getattr(m, "content", "")) for m in first_call_messages)
    assert "Skills" in combined
    assert "velocity-design" in combined
