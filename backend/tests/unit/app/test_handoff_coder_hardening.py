"""tests/unit/test_handoff_coder_hardening.py — F4 (13-02) handoff coder hardening.

Live failure: 1 of 2 live runs returned fabricated tool-call XML
(``<function_calls><invoke name=read_file>...``) instead of the JSON edit-plan, so
``_extract_json`` found no ``{...}`` object and ``propose_edits`` raised. Three
defenses are pinned here against a stubbed ``DeepAgentRunner`` (no model, no network):

(a) garbage first attempt + valid second ⇒ parsed plan, exactly 2 attempts;
(b) garbage both attempts ⇒ ValueError after exactly 2 attempts (hard bound);
(c) XML-polluted-but-JSON-bearing response ⇒ parses on the FIRST attempt (no retry);
(d) the corrective suffix is present in the second attempt's user message.

The stub replaces ``DeepAgentRunner`` at its home module
(``app.agents.deep_agent_runner``) because ``propose_edits`` lazy-imports it there
per attempt — a fresh runner per attempt is part of the contract under test.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

import app.agents.deep_agent_runner as runner_mod
from app.agents.handoff.coder import HandoffCoder, _extract_json

# ---------------------------------------------------------------------------
# Fixtures: scripted runner stub
# ---------------------------------------------------------------------------

_VALID_PLAN = {
    "summary": "add greeting",
    "rationale": "minimal change",
    "edits": [
        {
            "path": "src/app.py",
            "operation": "modify",
            "old_string": "x = 1",
            "new_string": "x = 2",
        }
    ],
    "tests_added": [],
    "follow_ups": [],
}
_VALID_JSON = json.dumps(_VALID_PLAN)

_TOOL_XML_GARBAGE = (
    '<function_calls>\n<invoke name="read_file">\n'
    '<parameter name="path">src/app.py</parameter>\n'
    "</invoke>\n</function_calls>"
)

# A response that wraps the VALID JSON object after leading fabricated XML —
# the hardened _extract_json must recover it without a retry.
_XML_WRAPPED_JSON = _TOOL_XML_GARBAGE + "\n" + _VALID_JSON


class _ScriptedRunner:
    """DeepAgentRunner stand-in: each construction pops the next scripted output."""

    constructions: list[dict[str, Any]] = []
    messages: list[str] = []
    script: list[str] = []

    def __init__(self, system_prompt: str, tools: list, **kwargs: Any) -> None:
        type(self).constructions.append(
            {"system_prompt": system_prompt, "tools": tools, **kwargs}
        )
        self._output = type(self).script[len(type(self).constructions) - 1]

    async def astream_events(self, user_message: str):
        type(self).messages.append(user_message)
        yield {"type": "chunk", "chunk": self._output}
        yield {"type": "done", "output": self._output}


@pytest.fixture
def scripted_runner(monkeypatch: pytest.MonkeyPatch) -> type[_ScriptedRunner]:
    """Install the stub at the coder's lazy-import home and reset its tallies."""
    _ScriptedRunner.constructions = []
    _ScriptedRunner.messages = []
    _ScriptedRunner.script = []
    monkeypatch.setattr(runner_mod, "DeepAgentRunner", _ScriptedRunner)
    return _ScriptedRunner


# ---------------------------------------------------------------------------
# (a) garbage then valid ⇒ parsed plan in exactly 2 attempts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_recovers_after_tool_xml_garbage(scripted_runner) -> None:
    scripted_runner.script = [_TOOL_XML_GARBAGE, _VALID_JSON]

    plan = await HandoffCoder().propose_edits(task="t", repo_tree="", relevant_files={})

    assert plan["edits"] == _VALID_PLAN["edits"]
    assert plan["summary"] == "add greeting"
    assert len(scripted_runner.constructions) == 2, "fresh runner per attempt"
    assert len(scripted_runner.messages) == 2


# ---------------------------------------------------------------------------
# (b) garbage twice ⇒ ValueError after exactly 2 attempts (hard bound)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_two_bad_attempts_raise_after_exactly_two(scripted_runner) -> None:
    scripted_runner.script = [_TOOL_XML_GARBAGE, _TOOL_XML_GARBAGE, _VALID_JSON]

    with pytest.raises(ValueError, match="no JSON object"):
        await HandoffCoder().propose_edits(task="t", repo_tree="", relevant_files={})

    # The third scripted (valid) output was never reached: hard 2-attempt bound.
    assert len(scripted_runner.constructions) == 2
    assert len(scripted_runner.messages) == 2


# ---------------------------------------------------------------------------
# (c) XML-polluted-but-JSON-bearing ⇒ FIRST-attempt parse, no retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_xml_wrapped_json_parses_without_retry(scripted_runner) -> None:
    scripted_runner.script = [_XML_WRAPPED_JSON]

    plan = await HandoffCoder().propose_edits(task="t", repo_tree="", relevant_files={})

    assert plan["edits"] == _VALID_PLAN["edits"]
    assert len(scripted_runner.constructions) == 1, "no retry needed"


def test_extract_json_strips_fabricated_xml_directly() -> None:
    """Unit pin on the hardened _extract_json (the strip narrows, never widens)."""
    assert _extract_json(_XML_WRAPPED_JSON) == _VALID_PLAN
    # Clean and fenced inputs keep their existing behavior.
    assert _extract_json(_VALID_JSON) == _VALID_PLAN
    assert _extract_json(f"```json\n{_VALID_JSON}\n```") == _VALID_PLAN


# ---------------------------------------------------------------------------
# (d) the corrective suffix lands in the SECOND attempt's user message
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_corrective_suffix_on_second_attempt_only(scripted_runner) -> None:
    scripted_runner.script = [_TOOL_XML_GARBAGE, _VALID_JSON]

    await HandoffCoder().propose_edits(task="t", repo_tree="", relevant_files={})

    first, second = scripted_runner.messages
    assert "previous response was NOT a valid JSON object" not in first
    assert "previous response was NOT a valid JSON object" in second
    assert second.startswith(first), "the retry augments the SAME user message"


# ---------------------------------------------------------------------------
# RuntimeError (runner ``error`` event) is a runtime fault — NEVER retried
# ---------------------------------------------------------------------------


class _ErrorRunner(_ScriptedRunner):
    async def astream_events(self, user_message: str):
        type(self).messages.append(user_message)
        yield {"type": "error", "error": "boom"}


@pytest.mark.asyncio
async def test_runtime_error_event_is_never_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ErrorRunner.constructions = []
    _ErrorRunner.messages = []
    _ErrorRunner.script = ["unused"]
    monkeypatch.setattr(runner_mod, "DeepAgentRunner", _ErrorRunner)

    with pytest.raises(RuntimeError, match="runtime error"):
        await HandoffCoder().propose_edits(task="t", repo_tree="", relevant_files={})

    assert len(_ErrorRunner.constructions) == 1, "runtime faults never retry"
