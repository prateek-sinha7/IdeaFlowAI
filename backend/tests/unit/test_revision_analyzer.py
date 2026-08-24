"""Unit tests for ``app.agents.revision_analyzer``.

Covers:
  - ``parse_analyzer_output`` — concrete examples for all error-table conditions
  - AGENT.md smoke tests — frontmatter assertions for prototype-revision-analyzer
  - prototype-revision-agent order smoke test (order == 2 after task 1.3 shift)

Requirements: 1.1–1.5, 2.1–2.6
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
    """Concrete examples covering every row of the error table in the design doc."""

    # ── Well-formed: both sections present with a valid tier ──────────────

    def test_wellformed_small_tier_returns_exact_tier_and_solution(self) -> None:
        """Well-formed output with tier 'small' returns ('small', solution)."""
        solution = "Update the login button label — id=login-btn on #/login route."
        raw = f"## Tier\nsmall\n\n## Solution Plan\n{solution}\n"
        tier, sol = parse_analyzer_output(raw)
        assert tier == "small"
        assert solution in sol

    def test_wellformed_large_tier_returns_exact_tier_and_solution(self) -> None:
        """Well-formed output with tier 'large' returns ('large', solution)."""
        solution = "Redesign the dashboard layout and add sidebar nav."
        raw = f"## Tier\nlarge\n\n## Solution Plan\n{solution}\n"
        tier, sol = parse_analyzer_output(raw)
        assert tier == "large"
        assert solution in sol

    def test_wellformed_feature_tier_returns_exact_tier_and_solution(self) -> None:
        """Well-formed output with tier 'feature' returns ('feature', solution)."""
        solution = "Add an onboarding flow with 3 steps and progress indicator."
        raw = f"## Tier\nfeature\n\n## Solution Plan\n{solution}\n"
        tier, sol = parse_analyzer_output(raw)
        assert tier == "feature"
        assert solution in sol

    def test_wellformed_solution_body_is_preserved_verbatim(self) -> None:
        """Solution body preserves interior whitespace and newlines."""
        solution = dedent("""\
            Update <div id='sidebar'>. Add nav links.
            Modify navigateTo() in routes.js.
            Set --sidebar-width: 240px in :root.
        """)
        raw = f"## Tier\nlarge\n\n## Solution Plan\n{solution}"
        tier, sol = parse_analyzer_output(raw)
        assert tier == "large"
        # Each sentence from the solution is present
        assert "Update <div id='sidebar'>" in sol
        assert "navigateTo()" in sol
        assert "--sidebar-width: 240px" in sol

    # ── Tier section absent → ("large", <solution or "">) + WARNING ──────

    def test_tier_section_absent_returns_large_with_solution(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """If ## Tier is absent, tier defaults to 'large' and solution is extracted."""
        solution = "Fix the login button label."
        raw = f"## Solution Plan\n{solution}\n"
        with caplog.at_level(logging.WARNING, logger="app.agents.revision_analyzer"):
            tier, sol = parse_analyzer_output(raw)
        assert tier == "large"
        assert solution in sol
        assert any("Tier" in record.message for record in caplog.records), (
            "Expected a WARNING mentioning 'Tier' section absence"
        )

    def test_tier_section_absent_no_solution_either_returns_large_empty(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """If ## Tier is absent and no solution, returns ('large', '')."""
        raw = "Some random text without any H2 sections."
        with caplog.at_level(logging.WARNING, logger="app.agents.revision_analyzer"):
            tier, sol = parse_analyzer_output(raw)
        assert tier == "large"
        assert sol == ""

    # ── Unknown tier value → ("large", …) + WARNING with raw[:500] ───────

    def test_unknown_tier_value_defaults_to_large(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """An unrecognized tier value 'unknown_tier' defaults to 'large' + WARNING."""
        raw = "## Tier\nunknown_tier\n\n## Solution Plan\nsome plan"
        with caplog.at_level(logging.WARNING, logger="app.agents.revision_analyzer"):
            tier, sol = parse_analyzer_output(raw)
        assert tier == "large"
        # WARNING must include the raw content (first 500 chars)
        warning_messages = " ".join(r.message for r in caplog.records if r.levelname == "WARNING")
        assert "unknown_tier" in warning_messages or "## Tier" in warning_messages

    def test_unknown_tier_warning_includes_raw_prefix(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The WARNING for an unrecognized tier includes the raw[:500] string."""
        raw = "## Tier\nfoo_bar_baz\n\n## Solution Plan\nsome plan"
        with caplog.at_level(logging.WARNING, logger="app.agents.revision_analyzer"):
            tier, _ = parse_analyzer_output(raw)
        assert tier == "large"
        # At least one WARNING record should reference the unrecognized value
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert warnings, "Expected at least one WARNING for unrecognized tier"

    def test_unknown_tier_solution_still_extracted(self) -> None:
        """Even with an unrecognized tier, the solution plan is still extracted."""
        solution = "Redesign the layout entirely."
        raw = f"## Tier\nxyz\n\n## Solution Plan\n{solution}"
        tier, sol = parse_analyzer_output(raw)
        assert tier == "large"
        assert solution in sol

    # ── ## Solution Plan absent → (tier, "") + WARNING ───────────────────

    def test_solution_plan_absent_returns_tier_empty_solution(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """If ## Solution Plan is absent, solution defaults to '' + WARNING."""
        raw = "## Tier\nsmall\n"
        with caplog.at_level(logging.WARNING, logger="app.agents.revision_analyzer"):
            tier, sol = parse_analyzer_output(raw)
        assert tier == "small"
        assert sol == ""
        assert any("Solution Plan" in r.message for r in caplog.records), (
            "Expected a WARNING mentioning 'Solution Plan' section absence"
        )

    def test_solution_plan_absent_large_tier(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Absent solution with 'large' tier returns ('large', '')."""
        raw = "## Tier\nlarge\n"
        with caplog.at_level(logging.WARNING, logger="app.agents.revision_analyzer"):
            tier, sol = parse_analyzer_output(raw)
        assert tier == "large"
        assert sol == ""

    # ── Both sections absent → ("large", "") + WARNING ───────────────────

    def test_both_sections_absent_returns_large_empty(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When neither ## Tier nor ## Solution Plan is present, returns ('large', '')."""
        raw = "This is plain text output with no H2 sections at all."
        with caplog.at_level(logging.WARNING, logger="app.agents.revision_analyzer"):
            tier, sol = parse_analyzer_output(raw)
        assert tier == "large"
        assert sol == ""
        assert any(r.levelname == "WARNING" for r in caplog.records), (
            "Expected at least one WARNING for both-absent condition"
        )

    def test_both_sections_absent_empty_sections(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Empty raw (only whitespace) returns ('large', '')."""
        raw = "   \n\n   "
        with caplog.at_level(logging.WARNING, logger="app.agents.revision_analyzer"):
            tier, sol = parse_analyzer_output(raw)
        assert tier == "large"
        assert sol == ""

    # ── Empty raw string → ("large", "") ─────────────────────────────────

    def test_empty_raw_string_returns_large_empty(self) -> None:
        """An empty raw string returns ('large', '') without raising."""
        tier, sol = parse_analyzer_output("")
        assert tier == "large"
        assert sol == ""

    # ── Case normalization: "SMALL" → "small" ────────────────────────────

    def test_tier_case_normalization_small_uppercase(self) -> None:
        """'SMALL' under ## Tier is normalized to 'small'."""
        raw = "## Tier\nSMALL\n\n## Solution Plan\nsome plan"
        tier, _ = parse_analyzer_output(raw)
        assert tier == "small"

    def test_tier_case_normalization_large_mixed(self) -> None:
        """'Large' (mixed case) under ## Tier is normalized to 'large'."""
        raw = "## Tier\nLarge\n\n## Solution Plan\nsome plan"
        tier, _ = parse_analyzer_output(raw)
        assert tier == "large"

    def test_tier_case_normalization_feature_uppercase(self) -> None:
        """'FEATURE' under ## Tier is normalized to 'feature'."""
        raw = "## Tier\nFEATURE\n\n## Solution Plan\nsome plan"
        tier, _ = parse_analyzer_output(raw)
        assert tier == "feature"

    def test_tier_case_normalization_small_titlecase(self) -> None:
        """'Small' (title case) under ## Tier is normalized to 'small'."""
        raw = "## Tier\nSmall\n\n## Solution Plan\nsome plan"
        tier, _ = parse_analyzer_output(raw)
        assert tier == "small"

    # ── Additional edge cases ─────────────────────────────────────────────

    def test_tier_with_leading_whitespace_in_body(self) -> None:
        """Leading blank lines before the tier value are skipped correctly."""
        raw = "## Tier\n\n\nsmall\n\n## Solution Plan\nsome plan"
        tier, _ = parse_analyzer_output(raw)
        assert tier == "small"

    def test_tier_with_trailing_whitespace(self) -> None:
        """Trailing whitespace on the tier line is stripped correctly."""
        raw = "## Tier\nlarge   \n\n## Solution Plan\nsome plan"
        tier, _ = parse_analyzer_output(raw)
        assert tier == "large"

    def test_return_type_is_tuple_of_two_strings(self) -> None:
        """parse_analyzer_output always returns a (str, str) tuple."""
        result = parse_analyzer_output("## Tier\nsmall\n\n## Solution Plan\nplan text")
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], str)

    def test_tier_is_always_valid_for_empty_input(self) -> None:
        """Even for empty input, tier is always in the valid set."""
        tier, _ = parse_analyzer_output("")
        assert tier in {"small", "large", "feature"}

    def test_tier_is_always_valid_for_garbage_input(self) -> None:
        """Even for garbage input, tier is always in the valid set."""
        tier, _ = parse_analyzer_output("!!@#$%^&*()_+ garbage text")
        assert tier in {"small", "large", "feature"}


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
