"""T2/T3/T4 — the pure edit engine.

Everything that can silently corrupt a prompt lives in `prompt_edits.py`, so
everything it can get wrong is pinned here. The rule throughout: an ambiguity
fails loudly. A misplaced edit looks applied, changes agent behaviour, and is
invisible to a skimmed diff review — a failed command costs one re-run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from evals.grading.model import prompt_edits
from evals.grading.model.prompt_edits import EditError, PromptFileError

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "agents" / "prompts"

SAMPLE = """---
id: demo-agent
order: 3
tools: []
---

You are the **Demo Agent**.

## Tools

- `read_file("prototype.html")` — read the current prototype.
- `write_file("prototype.html", content)` — overwrite the entire file.

## Steps

1. Read the spec.
2. Build it.

---

## What to preserve

- Keep the document valid.
"""


def _edit(action, section="", current_text="", proposed_text="", reason="because"):
    return {
        "action": action,
        "section": section,
        "current_text": current_text,
        "proposed_text": proposed_text,
        "reason": reason,
    }


class TestSplitAgentFile:
    """T2 — the frontmatter split. Never round-trips YAML (plan AD-03)."""

    def test_round_trips_byte_for_byte(self):
        prefix, body = prompt_edits.split_agent_file(SAMPLE)

        assert prefix + body == SAMPLE

    def test_prefix_holds_the_frontmatter_and_its_closing_delimiter(self):
        prefix, body = prompt_edits.split_agent_file(SAMPLE)

        assert prefix.startswith("---\n")
        assert prefix.rstrip().endswith("---")
        assert "id: demo-agent" in prefix
        assert "You are the" in body
        assert "id: demo-agent" not in body

    def test_a_horizontal_rule_in_the_body_is_not_a_delimiter(self):
        """`---` as a horizontal rule is common in these prompts — only the FIRST closes."""
        prefix, body = prompt_edits.split_agent_file(SAMPLE)

        assert "What to preserve" in body
        assert body.count("---") == 1  # the surviving horizontal rule

    def test_every_committed_agent_md_round_trips(self):
        """The real corpus, not a fixture — ~91 files with varied frontmatter."""
        files = sorted(PROMPTS_DIR.glob("*/AGENT.md"))
        assert len(files) > 50, "expected the real prompt corpus"

        for path in files:
            text = path.read_text(encoding="utf-8")
            prefix, body = prompt_edits.split_agent_file(text)

            assert prefix + body == text, path
            assert body.strip(), f"{path} produced an empty body"

    def test_missing_frontmatter_raises(self):
        with pytest.raises(PromptFileError):
            prompt_edits.split_agent_file("You are an agent with no frontmatter.\n")

    def test_unterminated_frontmatter_raises(self):
        """Never guess that the whole file is body — that would archive a broken prompt."""
        with pytest.raises(PromptFileError):
            prompt_edits.split_agent_file("---\nid: x\nno closing delimiter\n")

    def test_empty_file_raises(self):
        with pytest.raises(PromptFileError):
            prompt_edits.split_agent_file("")


class TestPurity:
    """T2 — the module must stay pure: no I/O, no package imports."""

    def test_imports_nothing_forbidden(self):
        source = Path(prompt_edits.__file__).read_text(encoding="utf-8")

        for forbidden in ("import os", "from pathlib", "import pathlib", "from evals", "import evals", "from agents", "import agents"):
            assert forbidden not in source, f"prompt_edits must stay pure: found {forbidden!r}"


class TestModify:
    """T3 — exactly-once match or fail."""

    def test_replaces_a_unique_match(self):
        prefix, body = prompt_edits.split_agent_file(SAMPLE)
        edits = [
            _edit(
                "modify",
                section="Tools",
                current_text='`write_file("prototype.html", content)` — overwrite the entire file.',
                proposed_text='`write_file("prototype.html", content)` — create-only.',
            )
        ]

        new_body, refused = prompt_edits.apply_edits(prefix, body, edits)

        assert "create-only." in new_body
        assert "overwrite the entire file." not in new_body
        assert refused == []

    def test_absent_text_raises_naming_the_edit(self):
        prefix, body = prompt_edits.split_agent_file(SAMPLE)
        edits = [_edit("modify", current_text="text that is not there", proposed_text="x")]

        with pytest.raises(EditError) as excinfo:
            prompt_edits.apply_edits(prefix, body, edits)

        message = str(excinfo.value)
        assert "1" in message and "modify" in message
        assert "0" in message  # the occurrence count

    def test_ambiguous_text_raises_with_the_count(self):
        prefix, body = prompt_edits.split_agent_file(SAMPLE)
        edits = [_edit("modify", current_text="prototype.html", proposed_text="x")]

        with pytest.raises(EditError) as excinfo:
            prompt_edits.apply_edits(prefix, body, edits)

        assert "2" in str(excinfo.value)


class TestRemove:
    def test_deletes_a_unique_match(self):
        prefix, body = prompt_edits.split_agent_file(SAMPLE)
        edits = [_edit("remove", current_text="- Keep the document valid.\n")]

        new_body, _ = prompt_edits.apply_edits(prefix, body, edits)

        assert "Keep the document valid." not in new_body

    def test_absent_text_raises(self):
        prefix, body = prompt_edits.split_agent_file(SAMPLE)

        with pytest.raises(EditError):
            prompt_edits.apply_edits(prefix, body, [_edit("remove", current_text="nope")])


class TestAdd:
    """T3 / AD-04 — heading, then substring, then fail. Never end-of-file."""

    def test_inserts_at_the_end_of_a_matched_heading_section(self):
        prefix, body = prompt_edits.split_agent_file(SAMPLE)
        edits = [_edit("add", section="Steps", proposed_text="3. Verify it.")]

        new_body, _ = prompt_edits.apply_edits(prefix, body, edits)

        assert "3. Verify it." in new_body
        # Inside the Steps section, before the next heading.
        steps_at = new_body.index("## Steps")
        next_heading_at = new_body.index("## What to preserve")
        assert steps_at < new_body.index("3. Verify it.") < next_heading_at

    def test_falls_back_to_a_unique_substring_anchor(self):
        """Real AGENT.md files use bold lines, not `##` headings, for steps."""
        prefix, body = prompt_edits.split_agent_file(SAMPLE)
        edits = [_edit("add", section="1. Read the spec.", proposed_text="1b. Check duplicates.")]

        new_body, _ = prompt_edits.apply_edits(prefix, body, edits)

        assert "1b. Check duplicates." in new_body

    def test_unresolvable_anchor_raises_rather_than_appending(self):
        prefix, body = prompt_edits.split_agent_file(SAMPLE)
        edits = [_edit("add", section="A section that does not exist", proposed_text="x")]

        with pytest.raises(EditError):
            prompt_edits.apply_edits(prefix, body, edits)

    def test_never_appends_to_the_end_of_file(self):
        """The anti-requirement: a silent end-of-file append is the worst outcome."""
        prefix, body = prompt_edits.split_agent_file(SAMPLE)

        with pytest.raises(EditError):
            prompt_edits.apply_edits(prefix, body, [_edit("add", section="", proposed_text="x")])

    def test_ambiguous_substring_anchor_raises(self):
        prefix, body = prompt_edits.split_agent_file(SAMPLE)
        edits = [_edit("add", section="prototype.html", proposed_text="x")]

        with pytest.raises(EditError):
            prompt_edits.apply_edits(prefix, body, edits)


class TestFrontmatterRefusal:
    """T3 / R-04 — refused by evidence, not by name."""

    def test_an_edit_whose_text_lives_in_the_frontmatter_is_refused(self):
        prefix, body = prompt_edits.split_agent_file(SAMPLE)
        edits = [_edit("modify", section="order", current_text="order: 3", proposed_text="order: 9")]

        new_body, refused = prompt_edits.apply_edits(prefix, body, edits)

        assert new_body == body
        assert len(refused) == 1
        assert "order" in refused[0]["reason"].lower() or "frontmatter" in refused[0]["reason"].lower()

    def test_a_refusal_does_not_stop_the_other_edits(self):
        prefix, body = prompt_edits.split_agent_file(SAMPLE)
        edits = [
            _edit("modify", section="order", current_text="order: 3", proposed_text="order: 9"),
            _edit("remove", current_text="- Keep the document valid.\n"),
        ]

        new_body, refused = prompt_edits.apply_edits(prefix, body, edits)

        assert len(refused) == 1
        assert "Keep the document valid." not in new_body

    def test_a_body_heading_sharing_a_frontmatter_field_name_is_not_refused(self):
        """`## Tools` is a real body heading and `tools:` is a real field.

        Refusing by name would block a legitimate edit; refusal is by evidence —
        the text has to actually live in the frontmatter.
        """
        prefix, body = prompt_edits.split_agent_file(SAMPLE)
        edits = [
            _edit(
                "modify",
                section="Tools",
                current_text="- `read_file(\"prototype.html\")` — read the current prototype.",
                proposed_text="- `read_file(\"prototype.html\")` — read it first.",
            )
        ]

        new_body, refused = prompt_edits.apply_edits(prefix, body, edits)

        assert refused == []
        assert "read it first." in new_body


class TestSequencing:
    def test_a_later_edit_sees_an_earlier_one(self):
        prefix, body = prompt_edits.split_agent_file(SAMPLE)
        edits = [
            _edit("modify", current_text="Build it.", proposed_text="Build it carefully."),
            _edit("modify", current_text="Build it carefully.", proposed_text="Build it well."),
        ]

        new_body, _ = prompt_edits.apply_edits(prefix, body, edits)

        assert "Build it well." in new_body

    def test_unknown_action_raises(self):
        """A schema addition must fail loudly, never be silently dropped."""
        prefix, body = prompt_edits.split_agent_file(SAMPLE)

        with pytest.raises(EditError):
            prompt_edits.apply_edits(prefix, body, [_edit("reorder", current_text="x")])

    def test_no_edits_returns_the_body_unchanged(self):
        prefix, body = prompt_edits.split_agent_file(SAMPLE)

        new_body, refused = prompt_edits.apply_edits(prefix, body, [])

        assert new_body == body
        assert refused == []


class TestNextArchiveNumber:
    """T4 / C5 — gaps are never filled and numbers never reused."""

    def test_empty_is_one(self):
        assert prompt_edits.next_archive_number([]) == 1

    def test_increments_from_the_maximum(self):
        assert prompt_edits.next_archive_number(["AGENT.v1.md"]) == 2

    def test_a_gap_is_not_filled(self):
        """v2 was deleted by hand; reusing it would make the sequence lie about order."""
        assert prompt_edits.next_archive_number(["AGENT.v1.md", "AGENT.v3.md"]) == 4

    def test_unrelated_filenames_are_ignored(self):
        names = ["AGENT.md", "README.md", "AGENT.vX.md", "AGENT.v2.md.bak", "AGENT.v2.md"]

        assert prompt_edits.next_archive_number(names) == 3

    def test_archive_name_matches_the_parser(self):
        name = prompt_edits.archive_name(7)

        assert name == "AGENT.v7.md"
        assert prompt_edits.next_archive_number([name]) == 8


class TestRenderDiff:
    def test_shows_every_applied_edit_and_every_refusal(self):
        edits = [
            _edit("add", section="Steps", proposed_text="3. Verify it.", reason="rows drifted"),
            _edit("remove", current_text="stale line", reason="obsolete"),
        ]
        refused = [{"index": 3, "action": "modify", "section": "order", "reason": "frontmatter"}]

        out = prompt_edits.render_diff(edits, refused)

        assert "add" in out and "Steps" in out and "3. Verify it." in out
        assert "remove" in out and "stale line" in out
        assert "rows drifted" in out
        assert "refused" in out.lower() and "order" in out

    def test_long_text_is_truncated_for_display(self):
        edits = [_edit("add", section="Steps", proposed_text="x" * 5000)]

        out = prompt_edits.render_diff(edits, [])

        assert len(out) < 2000

    def test_no_edits_renders_without_crashing(self):
        assert isinstance(prompt_edits.render_diff([], []), str)
