"""Unit tests for agents/workflows/artifacts.py — artifact filename helpers.

Tests cover:
  - topic_slug: lowercasing, non-alphanumeric collapsing, leading/trailing strip
  - topic_slug: truncation at 40 chars, never ending on '-'
  - topic_slug: empty/blank/all-punctuation input returns "topic" fallback
  - artifact_name: format '<instance_id>-<topic>.md'
  - artifact_name: output never contains ':' (hostile path guard, F-02)
"""

from __future__ import annotations

import pytest

from agents.workflows.artifacts import artifact_name, topic_slug


# ---------------------------------------------------------------------------
# topic_slug tests
# ---------------------------------------------------------------------------


class TestTopicSlug:
    def test_basic_kebab_case_with_spaces(self):
        """Spaces and mixed case become kebab."""
        assert topic_slug("Build me a CRM") == "build-me-a-crm"

    def test_punctuation_collapsed_to_hyphen(self):
        """Multiple punctuation runs become single '-'."""
        assert topic_slug("Build me a CRM!") == "build-me-a-crm"
        assert topic_slug("Design---API") == "design-api"
        assert topic_slug("Hello...World!!!") == "hello-world"

    def test_leading_trailing_hyphens_stripped(self):
        """Leading/trailing hyphens are removed."""
        assert topic_slug("...hello...") == "hello"
        assert topic_slug("...hello world...") == "hello-world"

    def test_truncation_at_40_chars(self):
        """Slug longer than 40 chars is truncated."""
        long_input = "a" * 50
        result = topic_slug(long_input)
        assert len(result) <= 40
        assert result == "a" * 40

    def test_truncation_never_ends_on_hyphen(self):
        """When truncation would end on '-', strip it."""
        # Create input that, when converted to kebab, will have '-' at position 40
        # "word-word-word..." where hyphens end up at strategic positions
        input_with_hyphens = "a-b-c-d-e-f-g-h-i-j-k-l-m-n-o-p-q-r-s-t-u-v-w-x-y-z-long-tail"
        result = topic_slug(input_with_hyphens)
        assert len(result) <= 40
        assert not result.endswith("-"), f"Result ends on '-': {result}"

    def test_empty_string_fallback(self):
        """Empty input returns fallback 'topic'."""
        assert topic_slug("") == "topic"

    def test_whitespace_only_fallback(self):
        """Whitespace-only input returns fallback 'topic'."""
        assert topic_slug("   ") == "topic"
        assert topic_slug("\t\n") == "topic"

    def test_all_punctuation_fallback(self):
        """All-punctuation input returns fallback 'topic'."""
        assert topic_slug("!!!") == "topic"
        assert topic_slug("---") == "topic"
        assert topic_slug("@#$%") == "topic"

    def test_mixed_case_with_numbers(self):
        """Mixed case + numbers → lowercase + numbers preserved."""
        assert topic_slug("Project 2024-Q1") == "project-2024-q1"

    def test_single_word(self):
        """Single word stays lowercase."""
        assert topic_slug("Research") == "research"


# ---------------------------------------------------------------------------
# artifact_name tests
# ---------------------------------------------------------------------------


class TestArtifactName:
    def test_basic_format(self):
        """artifact_name formats as '<instance_id>-<topic>.md'."""
        assert artifact_name("research-a", "crm-rollout") == "research-a-crm-rollout.md"

    def test_single_char_instance_id(self):
        """Single-char instance_id works."""
        assert artifact_name("a", "topic") == "a-topic.md"

    def test_hyphenated_instance_id(self):
        """Hyphens in instance_id are preserved."""
        assert artifact_name("research-agent-one", "my-topic") == "research-agent-one-my-topic.md"

    def test_numeric_instance_id(self):
        """Numbers in instance_id are preserved."""
        assert artifact_name("agent-1", "v2-design") == "agent-1-v2-design.md"

    def test_hostile_instance_id_is_refused(self):
        """A non-slug instance_id is REFUSED, not sanitized or passed through (F-02).

        artifact_name is the last point before a filename is built. Trusting the
        compiler's R-03 check alone would mean a caller that mistakenly passes an
        agent_id gets ``custom-agent:research-a.topic.md``, and one that passes a
        traversal gets ``../../etc/passwd.topic.md``. Both are F-02 exactly, so
        this function refuses rather than trusts.
        """
        for hostile in (
            "custom-agent:research-a",   # a synthetic agent id, not an instance_id
            "../../etc/passwd",          # traversal
            "a/b",                       # separator
            "Research-A",                # uppercase — not the slug shape
            "-leading",                  # must start alphanumeric
            "",                          # empty
        ):
            with pytest.raises(ValueError, match="instance_id"):
                artifact_name(hostile, "topic")

    def test_valid_instance_id_is_accepted(self):
        """The slug shape the compiler guarantees passes through unchanged."""
        assert artifact_name("research-a", "topic") == "research-a-topic.md"
        assert artifact_name("a1", "t") == "a1-t.md"
