"""Skills catalog hygiene gate — permanent build checks.

All assertions here test currently-passing invariants about the catalog.
They are written as tests so the invariants remain true as the catalog evolves.

Tests:
  1. audit() returns zero violations
  2. list_global_skills() returns exactly 186 entries (parsing gate)
  3. No SKILL.md frontmatter contains retired keys (compatible_agents, source, sourceLabel)
  4. Every description is non-empty and <= 200 characters
  5. PROVENANCE_PATTERNS does NOT contain 'cursor' (false-positive exclusion)
  6. audit() reports zero provenance violations (zero-tolerance, no allowlist)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add scripts to sys.path so we can import skills_audit.
_BACKEND = Path(__file__).resolve().parent.parent.parent
_SCRIPTS_DIR = _BACKEND / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from skills_audit import (
    PROVENANCE_PATTERNS,
    Violation,
    audit,
)
from app.agents.skills_catalog import list_global_skills


class TestSkillsCatalogHygiene:
    """Permanent catalog hygiene gate."""

    def test_audit_zero_violations(self) -> None:
        """audit() returns zero violations across the catalog.

        On failure, the assertion message lists all violations so a future
        reader sees what broke without re-running the script.
        """
        violations = audit()
        assert not violations, (
            f"skills catalog has {len(violations)} violation(s):\n"
            + "\n".join(
                f"  {v.skill_id} [{v.kind}] {v.detail}"
                for v in sorted(violations, key=lambda x: (x.skill_id, x.kind))
            )
        )

    def test_catalog_has_exactly_186_entries(self) -> None:
        """list_global_skills() returns exactly 186 entries.

        This is a parsing gate: a corrupted SKILL.md silently drops out
        of the catalog rather than raising, so a count change signals a
        potential parse failure somewhere.

        Went 185 -> 186 with ``html-deck-to-pptx``, authored alongside the
        ppt_v2 pipeline.
        """
        entries = list_global_skills()
        assert len(entries) == 186, (
            f"catalog changed from 186 to {len(entries)} entries — "
            f"a SKILL.md may have a parse error"
        )

    def test_no_retired_frontmatter_keys(self) -> None:
        """No SKILL.md frontmatter contains retired keys.

        compatible_agents, source, and sourceLabel were removed from the
        skill schema. This test ensures none reappear.
        """
        violations = audit()
        retired_keys = {"compatible_agents", "source", "sourceLabel"}
        retired_violations = [
            v for v in violations
            if v.kind == "frontmatter"
            and any(f"'{key}'" in v.detail for key in retired_keys)
        ]
        assert not retired_violations, (
            f"{len(retired_violations)} skill(s) still have retired frontmatter keys:\n"
            + "\n".join(
                f"  {v.skill_id}: {v.detail}"
                for v in retired_violations
            )
        )

    def test_descriptions_non_empty_and_under_200_chars(self) -> None:
        """Every description is non-empty and <= 200 characters.

        Includes skill id and actual length in failure message.
        """
        entries = list_global_skills()
        bad_descriptions = []
        for entry in entries:
            if not entry.description:
                bad_descriptions.append((entry.id, len(entry.description or ""), "empty"))
            elif len(entry.description) > 200:
                bad_descriptions.append((entry.id, len(entry.description), "exceeds limit"))

        assert not bad_descriptions, (
            f"{len(bad_descriptions)} skill(s) have invalid descriptions:\n"
            + "\n".join(
                f"  {id} (length {length}): {issue}"
                for id, length, issue in bad_descriptions
            )
        )

    def test_provenance_patterns_excludes_cursor(self) -> None:
        """PROVENANCE_PATTERNS does NOT contain 'cursor'.

        Every 'cursor' occurrence in this catalog is a CSS or screen-reader
        cursor (e.g. "visibility of the keyboard/screen reader cursor"),
        never a reference to the Cursor IDE. Including 'cursor' in the
        provenance patterns produces only false positives, so this test
        is what prevents a well-meaning future edit from adding it.
        """
        assert "cursor" not in PROVENANCE_PATTERNS, (
            "PROVENANCE_PATTERNS now contains 'cursor' — this will create "
            "false positives. Every 'cursor' in the catalog refers to CSS or "
            "screen-reader cursors, not the Cursor IDE. Do not add it."
        )

    def test_zero_provenance_violations(self) -> None:
        """audit() reports zero provenance violations, with no allowlist.

        Provenance checking is zero-tolerance: any hit on PROVENANCE_PATTERNS
        (claude, anthropic, openai, gpt-4, chatgpt, copilot, ecc, superpowers,
        obra) in a skill's body or description is a violation. There is no
        allowlist to suppress genuine hits — vendor references must be
        rewritten to be vendor-neutral instead.
        """
        violations = audit()
        provenance_violations = [v for v in violations if v.kind == "provenance"]
        assert not provenance_violations, (
            f"{len(provenance_violations)} provenance violation(s):\n"
            + "\n".join(
                f"  {v.skill_id}: {v.detail}"
                for v in provenance_violations
            )
        )
