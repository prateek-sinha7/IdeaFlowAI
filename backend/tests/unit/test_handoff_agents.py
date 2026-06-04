"""Agent-level tests for the migrated ``/flowin-handoff`` agents.

Migration Phase 7c-2 (plan ``specs/002-deepagents-migration/plan.md`` §5) rewrote
the four handoff agents off the legacy ``BaseAgent`` onto a direct
``build_model().ainvoke([SystemMessage, HumanMessage])`` one-shot. These tests pin
the behaviour the pipeline depends on, with NO model/graph built: ``build_model``
is patched in each agent module to return a scripted fake whose ``ainvoke``
returns an ``AIMessage`` with known ``content`` (``str`` OR a Bedrock-style
block-list), so we exercise the exact text-extraction + JSON-parse + ``setdefault``
paths.

Covered:
  * ``classify_task`` → "coding" / "test" parse, and the except→"coding" fallback.
  * ``CodingAgent.propose_edits`` → parses the JSON plan, applies ``setdefault``
    defaults, and threads the ``BEDROCK_CODING_MODEL_ID`` override into ``build_model``.
  * ``TestAgent.analyse`` / ``ComplianceAgent.review`` → parse + default their reports.
  * JSON-extraction edge cases (fenced ```` ```json ````, leading prose) and
    block-list ``content`` (Bedrock) decoding.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage

from app.agents.handoff import classifier as classifier_mod
from app.agents.handoff import coding_agent as coding_mod
from app.agents.handoff import compliance_agent as compliance_mod
from app.agents.handoff import test_agent as test_mod
from app.agents.handoff.coding_agent import CodingAgent
from app.agents.handoff.compliance_agent import ComplianceAgent

# Alias the import so pytest's ``python_classes = ["Test*"]`` rule does not try to
# collect the production ``TestAgent`` class (which has an ``__init__``) as a test.
from app.agents.handoff.test_agent import TestAgent as HandoffTestAgent


class _FakeModel:
    """Minimal chat-model stand-in: one scripted ``ainvoke`` response.

    ``content`` may be a ``str`` (Anthropic shape) or a list of content blocks
    (Bedrock shape, e.g. ``[{"type": "text", "text": "..."}]``) so we can exercise
    both ``_extract_text`` branches. Records nothing about construction except via
    the patched ``build_model`` spy.
    """

    def __init__(self, content: Any) -> None:
        self._content = content

    async def ainvoke(self, messages: list) -> AIMessage:  # noqa: D401
        self.last_messages = messages
        return AIMessage(content=self._content)


def _patch_build_model(module, content: Any):
    """Patch ``<module>.build_model`` to return a ``_FakeModel(content)``.

    Returns the ``patch`` object's ``MagicMock`` so a test can assert the args
    ``build_model`` was called with (e.g. the coding model override).
    """
    fake = _FakeModel(content)
    return patch.object(module, "build_model", return_value=fake)


# ---------------------------------------------------------------------------
# classify_task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_classify_task_returns_coding() -> None:
    with _patch_build_model(classifier_mod, "coding") as bm:
        result = await classifier_mod.classify_task("Add a retry to the HTTP client")
    assert result == "coding"
    bm.assert_called_once_with(max_tokens=8)


@pytest.mark.asyncio
async def test_classify_task_returns_test() -> None:
    # The parser lower-cases and uses ``startswith("test")`` — verify a noisy,
    # cased single-word answer still resolves to "test".
    with _patch_build_model(classifier_mod, "  TEST\n"):
        result = await classifier_mod.classify_task("Write the missing unit tests")
    assert result == "test"


@pytest.mark.asyncio
async def test_classify_task_block_list_content_resolves() -> None:
    """Bedrock-style block-list content decodes via ``_extract_text``."""
    with _patch_build_model(classifier_mod, [{"type": "text", "text": "test"}]):
        result = await classifier_mod.classify_task("coverage gaps")
    assert result == "test"


@pytest.mark.asyncio
async def test_classify_task_non_test_answer_defaults_to_coding() -> None:
    # Anything that does not start with "test" → "coding" (the ambiguity default).
    with _patch_build_model(classifier_mod, "something else entirely"):
        result = await classifier_mod.classify_task("ambiguous task")
    assert result == "coding"


@pytest.mark.asyncio
async def test_classify_task_invocation_failure_falls_back_to_coding() -> None:
    """A raise *inside* ``ainvoke`` is swallowed → "coding" (legacy fallback)."""

    class _BoomModel:
        async def ainvoke(self, _messages: list) -> AIMessage:
            raise RuntimeError("bedrock exploded")

    with patch.object(classifier_mod, "build_model", return_value=_BoomModel()):
        result = await classifier_mod.classify_task("anything")
    assert result == "coding"


@pytest.mark.asyncio
async def test_classify_task_includes_transcript_excerpt() -> None:
    """The transcript excerpt is appended to the human message (last 2000 chars)."""
    fake = _FakeModel("coding")
    long_excerpt = "X" * 5000
    with patch.object(classifier_mod, "build_model", return_value=fake):
        await classifier_mod.classify_task("do the thing", transcript_excerpt=long_excerpt)
    human = fake.last_messages[-1]
    assert "Recent IDE conversation context:" in human.content
    # Trimmed to the trailing 2000 chars.
    assert human.content.count("X") == 2000


# ---------------------------------------------------------------------------
# CodingAgent.propose_edits
# ---------------------------------------------------------------------------


_VALID_CODING_JSON = (
    '{"summary": "Add retry", '
    '"rationale": "Network calls flake.", '
    '"edits": [{"path": "a.py", "operation": "modify", '
    '"old_string": "x", "new_string": "y"}], '
    '"tests_added": ["t.py"], "follow_ups": []}'
)


@pytest.mark.asyncio
async def test_coding_agent_parses_plan() -> None:
    with _patch_build_model(coding_mod, _VALID_CODING_JSON):
        plan = await CodingAgent().propose_edits(
            task="add retry",
            repo_tree="src/\n  a.py",
            relevant_files={"a.py": "x = 1"},
        )
    assert plan["summary"] == "Add retry"
    assert plan["edits"][0]["path"] == "a.py"
    assert plan["tests_added"] == ["t.py"]


@pytest.mark.asyncio
async def test_coding_agent_applies_setdefaults() -> None:
    """A plan with only ``edits`` gets the four defaulted keys."""
    minimal = '{"edits": []}'
    with _patch_build_model(coding_mod, minimal):
        plan = await CodingAgent().propose_edits(
            task="t", repo_tree="", relevant_files={}
        )
    assert plan["summary"] == ""
    assert plan["rationale"] == ""
    assert plan["tests_added"] == []
    assert plan["follow_ups"] == []
    assert plan["edits"] == []


@pytest.mark.asyncio
async def test_coding_agent_strips_json_fences() -> None:
    """A fenced ```` ```json ```` block is unwrapped by ``_extract_json``."""
    fenced = "```json\n" + _VALID_CODING_JSON + "\n```"
    with _patch_build_model(coding_mod, fenced):
        plan = await CodingAgent().propose_edits(
            task="t", repo_tree="", relevant_files={}
        )
    assert plan["summary"] == "Add retry"


@pytest.mark.asyncio
async def test_coding_agent_recovers_json_from_prose() -> None:
    """A one-line preamble before the object → largest ``{...}`` span is parsed."""
    noisy = "Here is the plan you asked for:\n" + _VALID_CODING_JSON
    with _patch_build_model(coding_mod, noisy):
        plan = await CodingAgent().propose_edits(
            task="t", repo_tree="", relevant_files={}
        )
    assert plan["edits"][0]["operation"] == "modify"


@pytest.mark.asyncio
async def test_coding_agent_block_list_content() -> None:
    """Bedrock block-list content is concatenated then JSON-parsed."""
    blocks = [
        {"type": "text", "text": "{\"summary\": \"s\", \"edits\": ["},
        {"type": "text", "text": "]}"},
    ]
    with _patch_build_model(coding_mod, blocks):
        plan = await CodingAgent().propose_edits(
            task="t", repo_tree="", relevant_files={}
        )
    assert plan["summary"] == "s"
    assert plan["edits"] == []


@pytest.mark.asyncio
async def test_coding_agent_missing_edits_array_raises() -> None:
    """A JSON object without an ``edits`` *list* is an agent error."""
    with _patch_build_model(coding_mod, '{"summary": "no edits key"}'):
        with pytest.raises(ValueError, match="missing 'edits' array"):
            await CodingAgent().propose_edits(
                task="t", repo_tree="", relevant_files={}
            )


@pytest.mark.asyncio
async def test_coding_agent_non_json_raises() -> None:
    """No JSON object at all → ``ValueError`` (pipeline maps to agent_error)."""
    with _patch_build_model(coding_mod, "I could not produce a plan, sorry."):
        with pytest.raises(ValueError, match="no JSON object"):
            await CodingAgent().propose_edits(
                task="t", repo_tree="", relevant_files={}
            )


@pytest.mark.asyncio
async def test_coding_agent_uses_model_override() -> None:
    """``BEDROCK_CODING_MODEL_ID`` (when set) threads into ``build_model``."""
    override_id = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    with patch.object(coding_mod.settings, "BEDROCK_CODING_MODEL_ID", override_id):
        with _patch_build_model(coding_mod, _VALID_CODING_JSON) as bm:
            await CodingAgent().propose_edits(
                task="t", repo_tree="", relevant_files={}
            )
    bm.assert_called_once_with(model=override_id, max_tokens=16000)


@pytest.mark.asyncio
async def test_coding_agent_no_override_passes_none() -> None:
    """Empty/whitespace ``BEDROCK_CODING_MODEL_ID`` → ``model=None`` (provider default)."""
    with patch.object(coding_mod.settings, "BEDROCK_CODING_MODEL_ID", "   "):
        with _patch_build_model(coding_mod, _VALID_CODING_JSON) as bm:
            await CodingAgent().propose_edits(
                task="t", repo_tree="", relevant_files={}
            )
    bm.assert_called_once_with(model=None, max_tokens=16000)


# ---------------------------------------------------------------------------
# TestAgent.analyse
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_test_agent_parses_and_defaults() -> None:
    """A minimal report gets the six defaulted keys (verdict → "concerns")."""
    with _patch_build_model(test_mod, '{"summary": "ok"}'):
        report = await HandoffTestAgent().analyse(
            task="t", repo_tree="", test_files={}
        )
    assert report["summary"] == "ok"
    assert report["verdict"] == "concerns"
    assert report["tests_present"] == []
    assert report["missing_coverage"] == []
    assert report["quality_issues"] == []
    assert report["recommended_additions"] == []


@pytest.mark.asyncio
async def test_test_agent_full_report_passes_through() -> None:
    full = (
        '{"summary": "good", "verdict": "pass", '
        '"tests_present": [{"path": "t.py", "covers": "happy"}], '
        '"missing_coverage": [], "quality_issues": [], '
        '"recommended_additions": ["add a negative case"]}'
    )
    with _patch_build_model(test_mod, full):
        report = await HandoffTestAgent().analyse(
            task="t", repo_tree="", test_files={"t.py": "def test_x(): ..."}
        )
    assert report["verdict"] == "pass"
    assert report["recommended_additions"] == ["add a negative case"]


@pytest.mark.asyncio
async def test_test_agent_uses_max_tokens_8000() -> None:
    with _patch_build_model(test_mod, '{"summary": "x"}') as bm:
        await HandoffTestAgent().analyse(task="t", repo_tree="", test_files={})
    bm.assert_called_once_with(max_tokens=8000)


@pytest.mark.asyncio
async def test_test_agent_non_json_raises() -> None:
    with _patch_build_model(test_mod, "no json here"):
        with pytest.raises(ValueError, match="no JSON object"):
            await HandoffTestAgent().analyse(task="t", repo_tree="", test_files={})


# ---------------------------------------------------------------------------
# ComplianceAgent.review
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compliance_agent_parses_and_defaults() -> None:
    """A minimal report gets defaulted keys (verdict → "approve_with_changes")."""
    with _patch_build_model(compliance_mod, '{"summary": "fine"}'):
        report = await ComplianceAgent().review(
            task="t", repo_tree="", edited_files={}
        )
    assert report["summary"] == "fine"
    assert report["verdict"] == "approve_with_changes"
    assert report["findings"] == []
    assert report["positives"] == []


@pytest.mark.asyncio
async def test_compliance_agent_full_report_passes_through() -> None:
    full = (
        '{"summary": "looks risky", "verdict": "request_changes", '
        '"findings": [{"category": "security", "severity": "high", '
        '"location": "a.py:1", "issue": "sqli", "recommendation": "parameterise"}], '
        '"positives": ["clean diff"]}'
    )
    with _patch_build_model(compliance_mod, full):
        report = await ComplianceAgent().review(
            task="t", repo_tree="", edited_files={"a.py": "..."}
        )
    assert report["verdict"] == "request_changes"
    assert report["findings"][0]["category"] == "security"
    assert report["positives"] == ["clean diff"]


@pytest.mark.asyncio
async def test_compliance_agent_uses_max_tokens_8000() -> None:
    with _patch_build_model(compliance_mod, '{"summary": "x"}') as bm:
        await ComplianceAgent().review(task="t", repo_tree="", edited_files={})
    bm.assert_called_once_with(max_tokens=8000)


@pytest.mark.asyncio
async def test_compliance_agent_fenced_json() -> None:
    fenced = '```json\n{"summary": "wrapped", "verdict": "approve"}\n```'
    with _patch_build_model(compliance_mod, fenced):
        report = await ComplianceAgent().review(
            task="t", repo_tree="", edited_files={}
        )
    assert report["summary"] == "wrapped"
    assert report["verdict"] == "approve"


@pytest.mark.asyncio
async def test_compliance_agent_non_json_raises() -> None:
    with _patch_build_model(compliance_mod, "sorry, no report"):
        with pytest.raises(ValueError, match="no JSON object"):
            await ComplianceAgent().review(task="t", repo_tree="", edited_files={})
