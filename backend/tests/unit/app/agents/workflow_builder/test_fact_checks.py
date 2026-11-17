"""Unit tests for ``app/agents/workflow_builder/fact_checks.py``."""

from __future__ import annotations

from typing import Any

import pytest

from app.agents.workflow_builder.fact_checks import (
    PLACEHOLDER_RULE,
    PROPAGATION_RULE,
    check_facts,
    check_placeholders,
    concrete_facts,
)


def _slot(value: str, source: str = "user") -> dict[str, Any]:
    return {"value": value, "source": source, "criticality": "blocking"}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Post to #release-notes", ["#release-notes"]),
        ("Comment on ENG-42", ["ENG-42"]),
        ("Jira project ENG", ["ENG"]),
        ("Send to team-lead@example.com", ["team-lead@example.com"]),
        ("Read the GitHub repo acme/billing", ["acme/billing"]),
        ("Link https://example.com/notes.", ["https://example.com/notes"]),
        ("Write converted.md", ["converted.md"]),
        ("One fixed channel, named now", []),
        ("PDF/DOCX uploads", []),
    ],
)
def test_concrete_facts_extracts_identifiers_when_slot_is_given(
    value: str, expected: list[str]
) -> None:
    assert [
        token for _, token in concrete_facts({"write_destinations": _slot(value)})
    ] == expected


def test_concrete_facts_ignores_assumed_slots() -> None:
    assert concrete_facts({"write_destinations": _slot("#releases", "assumed")}) == []


def _manifest(prompt: str) -> dict[str, Any]:
    return {
        "steps": [{"agent": "custom-agent", "instance_id": "post", "prompt": prompt}],
        "deliverable": {"strategy": "single_file", "name": "report.md"},
    }


def test_check_facts_passes_when_every_identifier_appears_in_a_step() -> None:
    assert (
        check_facts(
            _manifest("Post to #releases."), [("write_destinations", "#releases")]
        )
        == []
    )


def test_check_facts_counts_the_deliverable_name() -> None:
    assert check_facts(_manifest("Write it."), [("deliverable", "report.md")]) == []


def test_check_facts_reports_each_missing_identifier() -> None:
    issues = check_facts(
        _manifest("Post to the channel."), [("write_destinations", "#releases")]
    )

    assert [(i.rule, i.path) for i in issues] == [(PROPAGATION_RULE, "steps")]
    assert (
        "the write_destinations value '#releases' that the user gave appears in no step"
        in issues[0].message
    )


# --- placeholders for missing facts ------------------------------------------------------


def test_check_placeholders_rejects_bracket_for_a_missing_fact() -> None:
    manifest = _manifest(
        "If the brief has no link, write [release-notes link] in the email."
    )

    issues = check_placeholders(manifest, ["the release-notes link URL"])

    assert [(i.rule, i.path) for i in issues] == [(PLACEHOLDER_RULE, "steps[0].prompt")]
    assert "missing fact 'the release-notes link URL'" in issues[0].message


def test_check_placeholders_ignores_a_never_write_placeholder_sentence() -> None:
    manifest = _manifest("Never write a placeholder such as [release-notes link].")

    assert check_placeholders(manifest, ["release-notes link"]) == []


def test_check_placeholders_ignores_brackets_unrelated_to_missing_facts() -> None:
    manifest = _manifest("Use the heading [Summary] for the first part.")

    assert check_placeholders(manifest, ["release-notes link"]) == []
    assert check_placeholders(_manifest("write [release-notes link]"), []) == []
