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
  * ``TestAgent.analyse`` / ``ComplianceAgent.review`` → parse + default their reports.

The ``CodingAgent.propose_edits`` cases were DELETED in 09-06 (D-09) — the bypass it
exercised (``build_model().ainvoke``) was removed; its successor ``HandoffCoder`` runs on
the deepagents runtime and is covered at the pipeline level by ``test_handoff_contract.py``.
  * JSON-extraction edge cases (fenced ```` ```json ````, leading prose) and
    block-list ``content`` (Bedrock) decoding.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage

from app.agents.handoff import classifier as classifier_mod
from app.agents.handoff import compliance_agent as compliance_mod
from app.agents.handoff import test_agent as test_mod
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
# CodingAgent.propose_edits — DELETED in 09-06 (D-09).
#
# The ``CodingAgent`` ``build_model().ainvoke`` bypass (the INV-13 gap) was deleted in
# 09-06: its successor ``HandoffCoder`` (``app/agents/handoff/coder.py``) produces the same
# JSON edit-plan but routes the model invocation through the sanctioned deepagents runtime
# (``DeepAgentRunner`` → ``create_deep_agent``), NOT a ``build_model``-patchable one-shot, so
# these ``_patch_build_model``-driven coding cases no longer apply. The pipeline-level contract
# (the coding step's events + edit-plan shape) is covered by
# ``tests/integration/test_handoff_contract.py`` under its mock seam. See the migration-ledger
# row D9 (the bypass-class deletion grep gate).
# ---------------------------------------------------------------------------


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
