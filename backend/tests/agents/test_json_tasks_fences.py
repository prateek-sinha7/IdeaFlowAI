"""json_tasks fence selection — every fence is a candidate, not just the first.

`_strip_json_fence` used `_FENCE_RE.search`, which returns the LEADING fenced
block. A planner that opened its reply with any other fence — an echoed example
from its own prompt, a prose snippet, a stray ``` run — handed that block to
`json.loads`, and the run died with a perfect task list sitting further down the
same reply. Observed live: a wave step failed with "could not parse task list as
JSON — Expecting value: line 1 column 1" against a reply that contained a valid
list.
"""

from __future__ import annotations

import pytest

from agents.capabilities.task_parsers.json_tasks import JsonTasksParser

GOOD = (
    '{"tasks": [{"id": "s01", "title": "Shard 1", "targets": ["notes/s01.done"],'
    ' "depends_on": [], "body": "read crimson pages 1-3"}]}'
)


@pytest.fixture
def parser() -> JsonTasksParser:
    return JsonTasksParser()


@pytest.mark.parametrize(
    "label,text",
    [
        (
            "bare array",
            '[{"id": "a", "title": "A", "targets": ["x"], "depends_on": [], "body": "b"}]',
        ),
        ("unfenced object", GOOD),
        ("single fence amid prose", f"here you go\n```json\n{GOOD}\n```"),
        (
            "example fence FIRST",
            f'Format:\n```json\n{{"tasks": [ ... ]}}\n```\nPlan:\n```json\n{GOOD}\n```',
        ),
        (
            "prose fence FIRST",
            f"```\nnot json at all\n```\nPlan:\n```json\n{GOOD}\n```",
        ),
        ("empty fence FIRST", f"```\n```\n```json\n{GOOD}\n```"),
    ],
)
def test_finds_the_parseable_fence_wherever_it_sits(parser, label, text):
    assert len(parser.parse(text)) == 1, label


def test_still_raises_when_no_fence_parses(parser):
    """A reply with nothing parseable must fail loudly, not return []."""
    with pytest.raises(ValueError, match="could not parse task list as JSON"):
        parser.parse("```\nnot json\n```\nand no list anywhere either")


def test_empty_payload_is_still_empty_not_an_error(parser):
    assert parser.parse("") == []


# ── contract.task_count validation (plan incomplete detection) ────


def test_wrapper_with_matching_contract_task_count_parses(parser):
    """contract.task_count equal to actual task count → success."""
    payload = '{"contract": {"task_count": 1}, "tasks": [{"id": "s01", "title": "Shard 1", "targets": ["notes/s01.done"], "depends_on": [], "body": "read crimson pages 1-3"}]}'
    tasks = parser.parse(payload)
    assert len(tasks) == 1
    assert tasks[0].id == "s01"


def test_wrapper_with_mismatched_contract_task_count_raises(parser):
    """contract.task_count=3 but only 1 task present → raises ValueError with 'plan incomplete'."""
    payload = '{"contract": {"task_count": 3}, "tasks": [{"id": "s01", "title": "Shard 1", "targets": ["notes/s01.done"], "depends_on": [], "body": "read"}]}'
    with pytest.raises(ValueError) as exc:
        parser.parse(payload)
    msg = str(exc.value)
    assert "plan incomplete" in msg
    assert "task_count=3" in msg
    assert "1 task" in msg


def test_wrapper_without_contract_still_parses(parser):
    """Wrapper object with no contract key → still parses."""
    payload = '{"metadata": "ignored", "tasks": [{"id": "s01", "title": "Shard 1", "targets": ["notes/s01.done"], "depends_on": [], "body": "read"}]}'
    tasks = parser.parse(payload)
    assert len(tasks) == 1


def test_wrapper_with_contract_but_no_task_count_still_parses(parser):
    """Wrapper with contract dict but no task_count key → still parses."""
    payload = '{"contract": {"other_field": 123}, "tasks": [{"id": "s01", "title": "Shard 1", "targets": ["notes/s01.done"], "depends_on": [], "body": "read"}]}'
    tasks = parser.parse(payload)
    assert len(tasks) == 1


def test_bare_array_ignores_contract_rules(parser):
    """Bare array (no wrapper) → no contract validation, always parses."""
    payload = '[{"id": "s01", "title": "Shard 1", "targets": ["notes/s01.done"], "depends_on": [], "body": "read"}]'
    tasks = parser.parse(payload)
    assert len(tasks) == 1


def test_contract_task_count_as_numeric_string_matches_int(parser):
    """task_count as string "2" with 2 tasks → parses."""
    payload = '{"contract": {"task_count": "2"}, "tasks": [{"id": "a", "body": "first"}, {"id": "b", "body": "second"}]}'
    tasks = parser.parse(payload)
    assert len(tasks) == 2


def test_contract_task_count_as_numeric_string_mismatch_raises(parser):
    """task_count as string "2" with only 1 task → raises ValueError."""
    payload = (
        '{"contract": {"task_count": "2"}, "tasks": [{"id": "a", "body": "first"}]}'
    )
    with pytest.raises(ValueError) as exc:
        parser.parse(payload)
    msg = str(exc.value)
    assert "plan incomplete" in msg
    assert "task_count=2" in msg
    assert "1 task" in msg
