"""Unit tests for ``app.agents.revision_analyzer``.

Covers:
  - ``parse_analyzer_output`` — concrete examples for the simplified str-return signature
    (task 9.1 simplified the return type from tuple[str, str] to str — tier parsing was
    removed; only the ## Solution Plan section is extracted and returned as a plain str)
  - AGENT.md smoke tests — frontmatter assertions for prototype-revision-analyzer
  - prototype-revision-agent order smoke test (order == 2 after task 1.3 shift)

Requirements: 4.1, 4.5, 9.3, 9.4
"""

from __future__ import annotations

import logging
import pathlib
from textwrap import dedent

import pytest
import yaml

from app.agents.revision_analyzer import parse_analyzer_output

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Resolve backend/ relative to THIS file (backend/tests/unit/)
_BACKEND_DIR = pathlib.Path(__file__).parent.parent.parent

_ANALYZER_AGENT_MD = (
    _BACKEND_DIR / "agents" / "prompts" / "prototype-revision-analyzer" / "AGENT.md"
)
_REVISION_AGENT_MD = (
    _BACKEND_DIR / "agents" / "prompts" / "prototype-revision-agent" / "AGENT.md"
)


def _load_frontmatter(path: pathlib.Path) -> dict:
    """Parse the YAML frontmatter block delimited by ``---`` from an AGENT.md file."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"No YAML frontmatter found in {path}")
    end = next(
        (i for i, line in enumerate(lines[1:], 1) if line.strip() == "---"),
        None,
    )
    if end is None:
        raise ValueError(f"YAML frontmatter is not closed in {path}")
    yaml_block = "\n".join(lines[1:end])
    return yaml.safe_load(yaml_block)


# ---------------------------------------------------------------------------
# parse_analyzer_output — concrete unit tests
# ---------------------------------------------------------------------------


class TestParseAnalyzerOutputConcrete:
    """Concrete examples for the simplified ``parse_analyzer_output`` (returns ``str``).

    As of task 9.1 (revision-pipeline-refactor) ``parse_analyzer_output`` was
    simplified: tier classification was removed and the function now returns only
    the ``## Solution Plan`` section body as a plain ``str`` (empty string when
    the section is absent).  These tests validate the new signature and behaviour.

    **Validates: Requirements 4.1, 4.5, 9.3, 9.4**
    """

    # ── Well-formed: ## Solution Plan section present ─────────────────────

    def test_wellformed_solution_body_extracted(self) -> None:
        """Solution body is extracted verbatim from a well-formed doc."""
        solution = "Update the login button label — id=login-btn on #/login route."
        raw = f"## Solution Plan\n{solution}\n"
        result = parse_analyzer_output(raw)
        assert isinstance(result, str)
        assert solution in result

    def test_wellformed_solution_body_is_preserved_verbatim(self) -> None:
        """Solution body preserves interior whitespace and newlines."""
        solution = dedent("""\
            Update <div id='sidebar'>. Add nav links.
            Modify navigateTo() in routes.js.
            Set --sidebar-width: 240px in :root.
        """)
        raw = f"## Solution Plan\n{solution}"
        result = parse_analyzer_output(raw)
        assert isinstance(result, str)
        assert "Update <div id='sidebar'>" in result
        assert "navigateTo()" in result
        assert "--sidebar-width: 240px" in result

    def test_solution_extracted_when_legacy_tier_section_present(self) -> None:
        """Solution is still extracted even when a legacy ## Tier section precedes it."""
        solution = "Fix the login button label."
        raw = f"## Tier\nlarge\n\n## Solution Plan\n{solution}\n"
        result = parse_analyzer_output(raw)
        assert isinstance(result, str)
        assert solution in result

    def test_multiple_h2_sections_returns_only_solution_plan(self) -> None:
        """Only the ## Solution Plan body is returned, not other H2 sections."""
        raw = "## Context\nsome context\n\n## Solution Plan\nmy plan\n\n## Notes\nfoo"
        result = parse_analyzer_output(raw)
        assert "my plan" in result
        assert "some context" not in result
        assert "foo" not in result

    # ── ## Solution Plan absent → "" + WARNING ───────────────────────────

    def test_solution_plan_absent_returns_empty_string(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """If ## Solution Plan is absent, returns '' and logs a WARNING."""
        raw = "Some random text without any H2 sections."
        with caplog.at_level(logging.WARNING, logger="app.agents.revision_analyzer"):
            result = parse_analyzer_output(raw)
        assert result == ""
        assert any("Solution Plan" in r.message for r in caplog.records), (
            "Expected a WARNING mentioning 'Solution Plan' section absence"
        )

    def test_solution_plan_absent_with_other_h2_sections(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Other H2 sections present but no Solution Plan → '' + WARNING."""
        raw = "## Tier\nlarge\n"
        with caplog.at_level(logging.WARNING, logger="app.agents.revision_analyzer"):
            result = parse_analyzer_output(raw)
        assert result == ""
        assert any("Solution Plan" in r.message for r in caplog.records)

    # ── Empty / garbage input ─────────────────────────────────────────────

    def test_empty_raw_string_returns_empty(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """An empty raw string returns '' without raising (task 9.4 edge case)."""
        with caplog.at_level(logging.WARNING, logger="app.agents.revision_analyzer"):
            result = parse_analyzer_output("")
        assert result == ""

    def test_whitespace_only_raw_returns_empty(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Whitespace-only raw input returns '' without raising."""
        with caplog.at_level(logging.WARNING, logger="app.agents.revision_analyzer"):
            result = parse_analyzer_output("   \n\n   ")
        assert result == ""

    def test_garbage_input_returns_empty_no_raise(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Garbage input returns '' without raising."""
        with caplog.at_level(logging.WARNING, logger="app.agents.revision_analyzer"):
            result = parse_analyzer_output("!!@#$%^&*()_+ garbage text")
        assert result == ""

    # ── ## Solution Plan heading with empty body ──────────────────────────

    def test_solution_plan_heading_only_returns_empty_or_whitespace(self) -> None:
        """## Solution Plan with no following body returns '' or only whitespace.

        The implementation returns the raw section body verbatim (including the
        trailing newline following the heading), so the result may be a newline-only
        string — which is truthy-false for the engine's injection gate (the gate
        strips and checks truthiness). This test verifies no exception is raised
        and the result is a str with no meaningful content.
        """
        result = parse_analyzer_output("## Solution Plan\n")
        assert isinstance(result, str)
        assert result.strip() == ""  # no meaningful content even if whitespace present

    # ── Return type is always str ─────────────────────────────────────────

    def test_return_type_is_str(self) -> None:
        """parse_analyzer_output always returns a str (not a tuple)."""
        result = parse_analyzer_output("## Solution Plan\nplan text")
        assert isinstance(result, str)
        assert not isinstance(result, tuple)

    def test_return_type_is_str_for_empty_input(self) -> None:
        """parse_analyzer_output returns str even for empty input."""
        result = parse_analyzer_output("")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# AGENT.md smoke tests
# ---------------------------------------------------------------------------


class TestAgentMdSmoke:
    """Smoke tests for AGENT.md frontmatter correctness."""

    def test_analyzer_agent_md_exists(self) -> None:
        """prototype-revision-analyzer/AGENT.md must exist on disk."""
        assert _ANALYZER_AGENT_MD.exists(), (
            f"AGENT.md not found at {_ANALYZER_AGENT_MD}"
        )

    def test_analyzer_agent_md_frontmatter_id(self) -> None:
        """prototype-revision-analyzer AGENT.md: id == 'prototype-revision-analyzer'."""
        fm = _load_frontmatter(_ANALYZER_AGENT_MD)
        assert fm["id"] == "prototype-revision-analyzer"

    def test_analyzer_agent_md_frontmatter_order(self) -> None:
        """prototype-revision-analyzer AGENT.md: order == 1."""
        fm = _load_frontmatter(_ANALYZER_AGENT_MD)
        assert fm["order"] == 1

    def test_analyzer_agent_md_frontmatter_pipeline_type(self) -> None:
        """prototype-revision-analyzer AGENT.md: pipeline_type == 'prototype_revision_analyzer'.

        The analyzer is an app-layer pre-pipeline agent. It uses its own unique
        pipeline_type so it is NOT included in PIPELINE_AGENTS['prototype_revision'],
        which would shift engine-side indices and break the INV-3 golden snapshots.
        The agent is still discoverable via load_agent_spec (AC 1.3).
        """
        fm = _load_frontmatter(_ANALYZER_AGENT_MD)
        assert fm["pipeline_type"] == "prototype_revision_analyzer"

    def test_analyzer_agent_md_frontmatter_max_tokens(self) -> None:
        """prototype-revision-analyzer AGENT.md: max_tokens == 4096."""
        fm = _load_frontmatter(_ANALYZER_AGENT_MD)
        assert fm["max_tokens"] == 4096

    def test_analyzer_agent_md_frontmatter_tools_empty(self) -> None:
        """prototype-revision-analyzer AGENT.md: tools == []."""
        fm = _load_frontmatter(_ANALYZER_AGENT_MD)
        assert fm["tools"] == []

    def test_revision_agent_md_exists(self) -> None:
        """prototype-revision-agent/AGENT.md must exist on disk."""
        assert _REVISION_AGENT_MD.exists(), (
            f"AGENT.md not found at {_REVISION_AGENT_MD}"
        )

    def test_revision_agent_order_is_two(self) -> None:
        """prototype-revision-agent AGENT.md: order == 1.

        The prototype-revision-analyzer has pipeline_type='prototype_revision_analyzer'
        (not 'prototype_revision'), so it is NOT a member of the prototype_revision
        pipeline and prototype-revision-agent remains at order=1 (INV-3 safe).
        """
        fm = _load_frontmatter(_REVISION_AGENT_MD)
        assert fm["order"] == 1, (
            f"Expected order=1 (prototype-revision-agent is first pipeline step), got order={fm['order']!r}"
        )
