"""Unit tests for ``app.agents.workflow_builder.agent``.

Covers the versioned system prompt (file content per Req 19.3 to 19.9, hash and
``prompt_version`` format) and the runner factory: the tools the model is offered
(``task`` and ``execute`` are absent), the pinned-message check, and one scripted
turn that runs a read tool through the observer middleware. The model is a
``FakeChatModel``; no network, no real gate.

Requirements: 19.1 to 19.9, 27.9, 28.3, 48.1, 49.2.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import HumanMessage

from app.agents.workflow_builder.skill_package import SKILLS_ROOT
from app.agents.deep_agent_runner import DeepAgentRunner
from app.agents.workflow_builder.agent import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_SHA256,
    BuilderPorts,
    BuilderTurnInputs,
    build_builder_runner,
)
from app.agents.workflow_builder.events import ToolFinished, ToolStarted
from app.agents.workflow_builder.read_tools import PlaceholderReadPort
from app.agents.workflow_builder.sandbox import BuilderSandbox
from app.agents.workflow_builder.stages import READ_TOOL_NAMES
from tests.fakes.builder_gate import FakeGate
from tests.fakes.builder_turn import FakeTurnPort
from tests.fakes.scripted_chat_model import FakeChatModel, ModelTurn, ScriptedToolCall

_BACKEND_DIR = Path(__file__).resolve().parents[5]
_PROMPT_FILE = (
    _BACKEND_DIR
    / "app"
    / "agents"
    / "workflow_builder"
    / "prompts"
    / "system_prompt.v1.md"
)
_SKILLS_ROOT = SKILLS_ROOT
_TURN_ID = "t-1"


def _prompt_text() -> str:
    return _PROMPT_FILE.read_bytes().decode("utf-8").replace("\r\n", "\n")


# --- System prompt and version ------------------------------------------------------


def test_system_prompt_equals_versioned_file_text_when_module_is_loaded() -> None:
    assert SYSTEM_PROMPT == _prompt_text()


def test_system_prompt_sha256_matches_file_hash_when_line_endings_are_normalised() -> (
    None
):
    expected = hashlib.sha256(_prompt_text().encode("utf-8")).hexdigest()

    assert SYSTEM_PROMPT_SHA256 == expected
    assert re.fullmatch(r"[0-9a-f]{64}", SYSTEM_PROMPT_SHA256)


def test_prompt_version_has_label_and_twelve_hex_when_built() -> None:
    assert re.fullmatch(r"v1:[0-9a-f]{12}", PROMPT_VERSION)
    assert PROMPT_VERSION == f"v1:{SYSTEM_PROMPT_SHA256[:12]}"


def test_system_prompt_has_exactly_six_numbered_parts_when_read() -> None:
    headings = re.findall(r"^## (\d+)\. (.+)$", SYSTEM_PROMPT, flags=re.MULTILINE)

    assert [number for number, _ in headings] == ["1", "2", "3", "4", "5", "6"]
    assert len(re.findall(r"^## ", SYSTEM_PROMPT, flags=re.MULTILINE)) == 6


def test_system_prompt_states_product_context_when_part_one_is_read() -> None:
    part = _part(1).lower()

    assert "chat panel" in part
    assert "canvas" in part
    assert "saves the workflow from the canvas" in part
    assert "never receives a file" in part


def test_system_prompt_explains_script_tool_when_part_two_is_read() -> None:
    part = _part(2)

    assert "run_skill_script" in part
    assert "`<skill>` stands for `/skills/velocity-workflow-creator`" in part
    assert "validate_manifest.py" in part
    assert "--compiler" in part


def test_system_prompt_restates_reactivation_rule_when_part_three_is_read() -> None:
    part = _part(3).lower()

    assert "every message that creates or changes a workflow" in part
    assert "from step 1" in part


def test_system_prompt_line_limit_covers_longest_skill_markdown_when_part_four_is_read() -> (
    None
):
    limits = [int(n) for n in re.findall(r"limit=(\d+)", _part(4))]
    longest = max(
        len(path.read_text(encoding="utf-8").splitlines())
        for path in _SKILLS_ROOT.rglob("*.md")
    )

    assert limits, "part 4 must state a read limit"
    assert min(limits) >= longest
    assert "one `read_file` call" in _part(4)


def test_system_prompt_warns_against_whole_reads_when_part_four_lists_large_files() -> (
    None
):
    part = _part(4)

    for name in (
        "docs/catalog.md",
        "schema/workflow-manifest.schema.json",
        "references/catalog.json",
        "examples/",
    ):
        assert name in part


def test_system_prompt_names_the_four_mandatory_files_when_part_four_is_read() -> None:
    part = _part(4)

    for name in (
        "SKILL.md",
        "docs/problem-decomposition.md",
        "docs/quick-reference.md",
        "docs/prompt-writing.md",
    ):
        assert f"/skills/velocity-workflow-creator/{name}" in part
        assert (_SKILLS_ROOT / "velocity-workflow-creator" / name).is_file()


def test_system_prompt_tells_agent_to_write_then_propose_when_part_five_is_read() -> (
    None
):
    part = _part(5)

    assert "/workflows/" in part
    assert ".workflow.json" in part
    assert part.index("Write the finished manifest") < part.index("`propose_draft`")


def test_system_prompt_replaces_run_it_section_when_part_five_is_read() -> None:
    part = _part(5)

    assert '"Run it" section' in part
    assert "Save the workflow from the canvas, then use Run once" in part
    assert "what a launch needs" in part


def test_system_prompt_states_builder_rules_when_part_six_is_read() -> None:
    part = _part(6)

    assert "`step_models`" in part
    assert "`forbidden_features`" in part
    assert "`db` trust" in part
    assert "target_trust" in part
    assert "trust_reason" in part


def _part(number: int) -> str:
    """Return the text of numbered part ``number`` of the prompt."""
    match = re.search(
        rf"^## {number}\. .*?(?=^## \d+\. |\Z)", SYSTEM_PROMPT, re.MULTILINE | re.DOTALL
    )
    assert match is not None, f"part {number} not found"
    return match.group(0)


# --- Runner factory -----------------------------------------------------------------


def _build(
    tmp_path: Path, model: FakeChatModel, *, message_id: str = f"turn:{_TURN_ID}"
) -> tuple[DeepAgentRunner, HumanMessage, FakeTurnPort]:
    sandbox = BuilderSandbox("user-1", "session-1", root=tmp_path / "builder")
    sandbox.ensure()
    turn = FakeTurnPort(turn_id=_TURN_ID)
    message = HumanMessage(content="Build me a review workflow.", id=message_id)
    inputs = BuilderTurnInputs(
        session_id="session-1",
        turn_id=_TURN_ID,
        user_id="user-1",
        tier="enterprise",
        model_id="unused",
        effort=None,
        message=message,
        chat_model=model,
    )
    ports = BuilderPorts(turn=turn, gate=FakeGate(), reads=PlaceholderReadPort())
    runner = build_builder_runner(inputs, sandbox, ports, skills_root=_SKILLS_ROOT)
    return runner, message, turn


def _text_of(content: str | list[str | dict[str, Any]]) -> str:
    """Join the text of a message ``content`` (a string or a list of blocks)."""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    return "".join(parts)


async def _drain(runner: DeepAgentRunner, message: HumanMessage) -> None:
    async for _ in runner.astream_events(message):
        pass


async def test_build_builder_runner_binds_builder_tools_and_not_task_or_execute_when_run(
    tmp_path: Path,
) -> None:
    model = FakeChatModel(turns=(ModelTurn(text=("done",)),))
    runner, message, _turn = _build(tmp_path, model)

    await _drain(runner, message)

    bound = set(model.bound_tool_names)
    assert {"run_skill_script", "propose_draft"} <= bound
    # The placeholder read port serves only get_builder_models until Q-18 adds data.
    assert "get_builder_models" in bound
    assert not (READ_TOOL_NAMES - {"get_builder_models"}) & bound
    assert {"ls", "read_file", "write_file", "edit_file", "glob", "grep"} <= bound
    assert "task" not in bound
    assert "execute" not in bound


async def test_build_builder_runner_sends_system_prompt_and_pinned_message_when_run(
    tmp_path: Path,
) -> None:
    model = FakeChatModel(turns=(ModelTurn(text=("done",)),))
    runner, message, _turn = _build(tmp_path, model)

    await _drain(runner, message)

    first_call = model.calls[0]
    assert sum(1 for m in first_call if m.id == f"turn:{_TURN_ID}") == 1
    system_text = "".join(_text_of(m.content) for m in first_call if m.type == "system")
    assert SYSTEM_PROMPT in system_text


async def test_build_builder_runner_runs_read_tool_through_observer_when_model_calls_it(
    tmp_path: Path,
) -> None:
    model = FakeChatModel(
        turns=(
            ModelTurn(
                tool_calls=(ScriptedToolCall("get_builder_models", {}, "call-a"),)
            ),
            ModelTurn(text=("done",)),
        )
    )
    runner, message, turn = _build(tmp_path, model)

    await _drain(runner, message)

    started = [e for e in turn.events if isinstance(e, ToolStarted)]
    finished = [e for e in turn.events if isinstance(e, ToolFinished)]
    assert [(e.call_id, e.tool, e.kind) for e in started] == [
        ("call-a", "get_builder_models", "lookup")
    ]
    assert [(e.call_id, e.status) for e in finished] == [("call-a", "ok")]
    assert len(turn.finished) == 1
    assert '"available":true' in turn.finished[0].result


def test_build_builder_runner_raises_when_message_id_is_not_the_turn_id(
    tmp_path: Path,
) -> None:
    model = FakeChatModel(turns=())

    with pytest.raises(ValueError, match="turn:t-1"):
        _build(tmp_path, model, message_id="turn:other")


async def test_build_builder_runner_logs_no_model_output_when_run(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    model = FakeChatModel(turns=(ModelTurn(text=("assistant-text-marker",)),))
    runner, message, _turn = _build(tmp_path, model)

    with caplog.at_level("DEBUG"):
        await _drain(runner, message)

    assert not [r for r in caplog.records if r.name == "app.agents.model_output"]
    assert "assistant-text-marker" not in caplog.text
