"""Unit tests for ``app.agents.workflow_builder.events``.

Covers the ``type`` discriminator, ``extra="forbid"`` and the wire split that
keeps ``type`` out of ``data``.

Requirements: 38.2 (every event carries ``ts``; the envelope is
``{"type", "data"}``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from app.agents.workflow_builder.events import (
    BuilderEvent,
    DraftRestored,
    ErrorEvent,
    SessionDeleted,
    Snapshot,
    StageChanged,
    Text,
    TurnCompleted,
    TurnStarted,
    event_types,
    from_wire,
    to_wire,
)
from app.agents.workflow_builder.stages import Stage

_TS = datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC)

_EXPECTED_TYPES = {
    "snapshot",
    "turn_started",
    "stage",
    "thinking",
    "tool_started",
    "tool_finished",
    "check_result",
    "draft_applied",
    "text",
    "limit_warning",
    "turn_completed",
    "error",
    "draft_restored",
    "session_deleted",
    "session_revoked",
}


def _one_of_each() -> list[BuilderEvent]:
    """Build one valid instance of every event model."""
    base: dict[str, Any] = {"ts": _TS}
    turn: dict[str, Any] = {**base, "turn_id": "t1", "seq": 1}
    summary: dict[str, Any] = {
        "added": [],
        "removed": [],
        "reordered": False,
        "gates_changed": [],
        "validators_changed": [],
        "models_changed": [],
        "prompts_changed": 0,
    }
    raw: list[tuple[str, dict[str, Any]]] = [
        (
            "snapshot",
            {
                **base,
                "state": "idle",
                "running_turn": None,
                "latest_message_id": None,
                "latest_revision": None,
                "latest_unproposed_revision": None,
            },
        ),
        (
            "turn_started",
            {
                **turn,
                "message_id": "m1",
                "model_id": "model",
                "effort": None,
                "skill_hash": "sha256:x",
            },
        ),
        ("stage", {**turn, "stage": "reading", "label": "Reading"}),
        ("thinking", {**turn, "text": "hmm"}),
        (
            "tool_started",
            {
                **turn,
                "call_id": "c1",
                "tool": "read_file",
                "kind": "read",
                "label": "Reading",
                "command": None,
            },
        ),
        (
            "tool_finished",
            {
                **turn,
                "call_id": "c1",
                "status": "ok",
                "duration_ms": 3,
                "summary": "done",
            },
        ),
        (
            "check_result",
            {
                **turn,
                "source": "server_gate",
                "verdict": "valid",
                "errors": 0,
                "warnings": 0,
                "attempt": None,
                "attempts_left": None,
            },
        ),
        (
            "draft_applied",
            {
                **turn,
                "revision": 2,
                "target_trust": "user",
                "change_summary": summary,
                "launch_needs": [],
                "manifest": {"steps": []},
            },
        ),
        ("text", {**turn, "text": "hello"}),
        ("limit_warning", {**turn, "kind": "time", "used": 8, "limit": 10}),
        (
            "turn_completed",
            {
                **turn,
                "status": "completed",
                "outcome": "reply",
                "stop_reason": None,
                "message_id": "m1",
                "revision": None,
                "usage": {"input": 1, "output": 2},
            },
        ),
        (
            "error",
            {
                **base,
                "turn_id": None,
                "seq": None,
                "code": "boom",
                "message": "Something went wrong.",
                "retryable": False,
            },
        ),
        ("draft_restored", {**base, "revision": 3, "manifest": {}}),
        ("session_deleted", base),
        ("session_revoked", {**base, "session_id": "s1", "reason": "revoked"}),
    ]
    return [from_wire(type_, data) for type_, data in raw]


def test_event_types_lists_every_wire_name_when_called() -> None:
    assert event_types() == _EXPECTED_TYPES


def test_one_of_each_covers_every_event_type_when_fixture_is_built() -> None:
    assert {event.type for event in _one_of_each()} == _EXPECTED_TYPES


@pytest.mark.parametrize("event", _one_of_each(), ids=lambda e: e.type)
def test_to_wire_omits_type_key_from_data_when_event_given(
    event: BuilderEvent,
) -> None:
    type_, data = to_wire(event)

    assert type_ == event.type
    assert "type" not in data
    assert "ts" in data


@pytest.mark.parametrize("event", _one_of_each(), ids=lambda e: e.type)
def test_from_wire_rebuilds_same_event_when_given_to_wire_output(
    event: BuilderEvent,
) -> None:
    type_, data = to_wire(event)

    assert from_wire(type_, data) == event


@pytest.mark.parametrize("event", _one_of_each(), ids=lambda e: e.type)
def test_from_wire_rejects_unknown_key_when_extra_field_present(
    event: BuilderEvent,
) -> None:
    type_, data = to_wire(event)

    with pytest.raises(ValidationError):
        from_wire(type_, {**data, "unexpected": 1})


def test_from_wire_picks_model_by_type_when_discriminator_given() -> None:
    stage = from_wire(
        "stage", {"ts": _TS, "turn_id": "t", "seq": 1, "stage": "writing", "label": "L"}
    )
    text = from_wire("text", {"ts": _TS, "turn_id": "t", "seq": 2, "text": "hi"})
    gone = from_wire("session_deleted", {"ts": _TS})

    assert isinstance(stage, StageChanged)
    assert stage.stage is Stage.WRITING
    assert isinstance(text, Text)
    assert isinstance(gone, SessionDeleted)


def test_from_wire_raises_when_type_is_unknown() -> None:
    with pytest.raises(ValidationError):
        from_wire("not_an_event", {"ts": _TS})


def test_from_wire_raises_value_error_when_data_contains_type_key() -> None:
    with pytest.raises(ValueError, match="'type' key"):
        from_wire("session_deleted", {"ts": _TS, "type": "session_deleted"})


def test_event_construction_raises_when_ts_is_missing() -> None:
    with pytest.raises(ValidationError):
        SessionDeleted()  # type: ignore[call-arg]


def test_event_construction_raises_when_unknown_field_given() -> None:
    with pytest.raises(ValidationError):
        SessionDeleted(ts=_TS, extra_field=1)  # type: ignore[call-arg]


def test_event_construction_raises_when_type_literal_is_wrong() -> None:
    with pytest.raises(ValidationError):
        SessionDeleted(ts=_TS, type="text")  # type: ignore[arg-type]


def test_turn_scoped_event_raises_when_seq_is_zero() -> None:
    with pytest.raises(ValidationError):
        Text(ts=_TS, turn_id="t", seq=0, text="x")


def test_nested_models_reject_unknown_key_when_extra_field_present() -> None:
    _, data = to_wire(
        TurnCompleted(
            ts=_TS,
            turn_id="t",
            seq=1,
            status="completed",
            outcome="reply",
            stop_reason=None,
            message_id="m",
            revision=None,
            usage={"input": 1},  # type: ignore[arg-type]
        )
    )
    data["usage"]["bogus"] = 1

    with pytest.raises(ValidationError):
        from_wire("turn_completed", data)


def test_turn_started_requires_all_fields_when_one_is_missing() -> None:
    with pytest.raises(ValidationError):
        TurnStarted(ts=_TS, turn_id="t", seq=1, message_id="m")  # type: ignore[call-arg]


def test_snapshot_and_error_and_restored_have_distinct_types_when_built() -> None:
    types = {
        Snapshot.model_fields["type"].default,
        ErrorEvent.model_fields["type"].default,
        DraftRestored.model_fields["type"].default,
    }

    assert types == {"snapshot", "error", "draft_restored"}
