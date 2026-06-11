"""tests/agents/test_json_tasks.py — the structured ``json_tasks`` parser (12-01 / WAVE-02).

Covers the JsonTasksParser: plain array / fenced ```json block / ``{"tasks": [...]}``
wrapper acceptance; malformed-JSON and unknown-``depends_on`` named ValueErrors
(T-12-01-INPUT — untrusted agent JSON crossing into the scheduler); and registration.

Offline / pure (no DB / network / API key).
"""

from __future__ import annotations

import json

import pytest

from agents.capabilities.registry import CapabilityRegistry, discover
from agents.capabilities.task_parsers.json_tasks import JsonTasksParser


def _parse(text: str):
    return JsonTasksParser().parse(text)


def test_parses_plain_json_array():
    out = _parse(json.dumps([
        {"id": "a", "title": "A", "body": "do a", "targets": ["f1"]},
        {"id": "b", "body": "do b", "depends_on": ["a"], "conflict_keys": ["k1"]},
    ]))
    assert [t.id for t in out] == ["a", "b"]
    assert out[0].title == "A"
    assert out[0].targets == ["f1"]
    assert out[1].depends_on == ["a"]
    assert out[1].conflict_keys == ["k1"]


def test_tolerates_fenced_json_block():
    fenced = "```json\n" + json.dumps([{"id": "x", "body": "bx"}]) + "\n```"
    out = _parse(fenced)
    assert [t.id for t in out] == ["x"]
    assert out[0].body == "bx"


def test_tolerates_bare_fence():
    fenced = "```\n" + json.dumps([{"id": "y"}]) + "\n```"
    out = _parse(fenced)
    assert [t.id for t in out] == ["y"]


def test_tolerates_tasks_wrapper_object():
    wrapped = json.dumps({"tasks": [{"id": "t1"}, {"id": "t2", "depends_on": ["t1"]}]})
    out = _parse(wrapped)
    assert [t.id for t in out] == ["t1", "t2"]


def test_empty_payload_yields_empty_list():
    assert _parse("") == []
    assert _parse("   ") == []


def test_malformed_json_raises_clear_valueerror():
    with pytest.raises(ValueError) as exc:
        _parse("{not: valid json,,,}")
    assert "json_tasks" in str(exc.value)


def test_object_without_tasks_key_raises():
    with pytest.raises(ValueError) as exc:
        _parse(json.dumps({"items": []}))
    assert "tasks" in str(exc.value)


def test_unknown_depends_on_ref_raises_named_valueerror():
    payload = json.dumps([
        {"id": "a"},
        {"id": "b", "depends_on": ["ghost"]},
    ])
    with pytest.raises(ValueError) as exc:
        _parse(payload)
    msg = str(exc.value)
    assert "b" in msg and "ghost" in msg


def test_task_missing_id_raises():
    with pytest.raises(ValueError):
        _parse(json.dumps([{"title": "no id"}]))


def test_id_is_stringified():
    out = _parse(json.dumps([{"id": 7}]))
    assert out[0].id == "7"


def test_duplicate_task_id_raises_named_valueerror():
    """WR-05: a duplicate task id raises a named ValueError before returning any task.

    FAILS on the pre-fix parser (last-wins ``by_id`` silently drops the earlier task).
    """
    payload = json.dumps([
        {"id": "a", "body": "first a"},
        {"id": "b", "body": "b"},
        {"id": "a", "body": "second a"},
    ])
    with pytest.raises(ValueError) as exc:
        _parse(payload)
    msg = str(exc.value)
    assert "duplicate" in msg.lower() and "a" in msg, f"unexpected message: {msg!r}"


def test_json_tasks_is_registered():
    discover()
    reg = CapabilityRegistry()
    assert reg.is_registered("task_parser", "json_tasks")
