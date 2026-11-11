"""Property tests for the workflow builder event models and wire helpers.

# Feature: ai-workflow-builder, Property 22: Events round-trip through JSON

For any instance of any ``BuilderEvent`` type, serialising it to the wire
envelope and parsing it back gives an equal instance. The test pushes the
``(type, data)`` pair of :func:`to_wire` through ``json.dumps`` and
``json.loads`` before :func:`from_wire`, as the SSE transport does.

**Validates: Requirements 38.3, 38.4, 38.5, 38.6, 38.7, 38.8, 38.11, 38.12, 38.13, 38.14**

Generators build each event class explicitly. ``test_event_strategies_cover_
every_wire_type_when_registry_is_read`` fails when a new event type is added
to ``events.py`` without a strategy here.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.agents.workflow_builder.events import (
    BuilderEvent,
    ChangeSummary,
    CheckResult,
    CheckResultEvent,
    DraftApplied,
    DraftRestored,
    ErrorEvent,
    LaunchNeed,
    LimitWarning,
    RunningTurnSnapshot,
    SessionDeleted,
    SessionRevoked,
    Snapshot,
    StageChanged,
    Text,
    Thinking,
    TokenUsage,
    ToolActivity,
    ToolFinished,
    ToolStarted,
    TurnCompleted,
    TurnStarted,
    UsageCounts,
    event_types,
    from_wire,
    to_wire,
)
from app.agents.workflow_builder.stages import Stage

# --- Primitive strategies -----------------------------------------------------------

_TEXT = st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=40)
_IDS = st.text(
    alphabet=st.characters(min_codepoint=33, max_codepoint=126), min_size=1, max_size=24
)
_COUNT = st.integers(min_value=0, max_value=2**31)
_SEQ = st.integers(min_value=1, max_value=2**31)
_OPT_TEXT = st.none() | _TEXT
_OPT_COUNT = st.none() | _COUNT

_OFFSETS = st.sampled_from(
    [UTC, timezone(timedelta(hours=5, minutes=30)), timezone(timedelta(hours=-8))]
)
_TS = st.datetimes(
    min_value=datetime(2000, 1, 1), max_value=datetime(2100, 1, 1), timezones=_OFFSETS
)

_JSON_SCALARS = (
    st.none()
    | st.booleans()
    | st.integers(min_value=-(2**53), max_value=2**53)
    | st.floats(allow_nan=False, allow_infinity=False)
    | _TEXT
)
_MANIFEST = st.dictionaries(
    _TEXT,
    st.recursive(
        _JSON_SCALARS,
        lambda children: st.lists(children, max_size=3)
        | st.dictionaries(_TEXT, children, max_size=3),
        max_leaves=8,
    ),
    max_size=4,
)

_TOOL_KIND = st.sampled_from(["read", "write", "script", "lookup", "propose"])
_TOOL_STATUS = st.sampled_from(["running", "ok", "error", "refused", "timed_out"])
_FINISH_STATUS = st.sampled_from(["ok", "error", "refused", "timed_out"])
_CHECK_SOURCE = st.sampled_from(["skill_validator", "platform_dry_run", "server_gate"])
_CHECK_VERDICT = st.sampled_from(["valid", "invalid", "unknown"])
_STAGE = st.sampled_from(list(Stage))
_STOP_REASON = st.none() | st.sampled_from(
    [
        "time",
        "tool_calls",
        "tokens",
        "recursion",
        "gate_rejections",
        "cancelled",
        "deleted",
        "shutdown",
        "restart",
        "error",
    ]
)

# --- Shared value model strategies --------------------------------------------------

_TOOL_ACTIVITY = st.builds(
    ToolActivity,
    call_id=_IDS,
    tool=_IDS,
    kind=_TOOL_KIND,
    label=_TEXT,
    status=_TOOL_STATUS,
    duration_ms=_OPT_COUNT,
    command=_OPT_TEXT,
    exit_code=st.none() | st.integers(min_value=-255, max_value=255),
    summary=_OPT_TEXT,
)
_CHECK_RESULT = st.builds(
    CheckResult,
    source=_CHECK_SOURCE,
    verdict=_CHECK_VERDICT,
    errors=_COUNT,
    warnings=_COUNT,
    attempt=_OPT_COUNT,
    attempts_left=_OPT_COUNT,
)
_CHANGE_SUMMARY = st.builds(
    ChangeSummary,
    added=st.lists(_TEXT, max_size=3),
    removed=st.lists(_TEXT, max_size=3),
    reordered=st.booleans(),
    gates_changed=st.lists(_TEXT, max_size=3),
    validators_changed=st.lists(_TEXT, max_size=3),
    models_changed=st.lists(_TEXT, max_size=3),
    prompts_changed=_COUNT,
)
_LAUNCH_NEED = st.builds(
    LaunchNeed,
    kind=st.sampled_from(["uploads", "design", "connector", "source_run"]),
    detail=_OPT_TEXT,
)
_RUNNING_TURN = st.builds(
    RunningTurnSnapshot,
    turn_id=_IDS,
    message_id=_IDS,
    stage=_STAGE,
    label=_TEXT,
    started_at=_TS,
    through_seq=_COUNT,
    activity=st.lists(_TOOL_ACTIVITY, max_size=3),
    checks=st.lists(_CHECK_RESULT, max_size=3),
)
_USAGE_COUNTS = st.builds(
    UsageCounts,
    input=_COUNT,
    output=_COUNT,
    cache_read=_COUNT,
    cache_write=_COUNT,
)
_TOKEN_USAGE = st.builds(
    TokenUsage,
    input=_COUNT,
    output=_COUNT,
    cache_read=_COUNT,
    cache_write=_COUNT,
    summary=st.none() | _USAGE_COUNTS,
)

# --- Event strategies, one per wire type --------------------------------------------

_EVENT_STRATEGIES: dict[str, st.SearchStrategy[Any]] = {
    "snapshot": st.builds(
        Snapshot,
        ts=_TS,
        state=st.sampled_from(["idle", "running"]),
        running_turn=st.none() | _RUNNING_TURN,
        latest_message_id=_OPT_TEXT,
        latest_revision=_OPT_COUNT,
        latest_unproposed_revision=_OPT_COUNT,
    ),
    "turn_started": st.builds(
        TurnStarted,
        ts=_TS,
        turn_id=_IDS,
        seq=_SEQ,
        message_id=_IDS,
        model_id=_IDS,
        effort=_OPT_TEXT,
        skill_hash=_TEXT,
    ),
    "stage": st.builds(
        StageChanged, ts=_TS, turn_id=_IDS, seq=_SEQ, stage=_STAGE, label=_TEXT
    ),
    "thinking": st.builds(Thinking, ts=_TS, turn_id=_IDS, seq=_SEQ, text=_TEXT),
    "tool_started": st.builds(
        ToolStarted,
        ts=_TS,
        turn_id=_IDS,
        seq=_SEQ,
        call_id=_IDS,
        tool=_IDS,
        kind=_TOOL_KIND,
        label=_TEXT,
        command=_OPT_TEXT,
    ),
    "tool_finished": st.builds(
        ToolFinished,
        ts=_TS,
        turn_id=_IDS,
        seq=_SEQ,
        call_id=_IDS,
        status=_FINISH_STATUS,
        duration_ms=_COUNT,
        summary=_TEXT,
    ),
    "check_result": st.builds(
        CheckResultEvent,
        ts=_TS,
        turn_id=_IDS,
        seq=_SEQ,
        source=_CHECK_SOURCE,
        verdict=_CHECK_VERDICT,
        errors=_COUNT,
        warnings=_COUNT,
        attempt=_OPT_COUNT,
        attempts_left=_OPT_COUNT,
    ),
    "draft_applied": st.builds(
        DraftApplied,
        ts=_TS,
        turn_id=_IDS,
        seq=_SEQ,
        revision=_COUNT,
        target_trust=st.sampled_from(["user", "db"]),
        change_summary=_CHANGE_SUMMARY,
        launch_needs=st.lists(_LAUNCH_NEED, max_size=3),
        manifest=_MANIFEST,
    ),
    "text": st.builds(Text, ts=_TS, turn_id=_IDS, seq=_SEQ, text=_TEXT),
    "limit_warning": st.builds(
        LimitWarning,
        ts=_TS,
        turn_id=_IDS,
        seq=_SEQ,
        kind=st.sampled_from(["time", "tool_calls", "tokens"]),
        used=_COUNT,
        limit=_COUNT,
    ),
    "turn_completed": st.builds(
        TurnCompleted,
        ts=_TS,
        turn_id=_IDS,
        seq=_SEQ,
        status=st.sampled_from(
            ["completed", "failed", "cancelled", "timed_out", "interrupted"]
        ),
        outcome=st.sampled_from(["draft", "reply", "unfinished"]),
        stop_reason=_STOP_REASON,
        message_id=_IDS,
        revision=_OPT_COUNT,
        usage=_TOKEN_USAGE,
    ),
    "error": st.builds(
        ErrorEvent,
        ts=_TS,
        turn_id=st.none() | _IDS,
        seq=st.none() | _SEQ,
        code=_IDS,
        message=_TEXT,
        retryable=st.booleans(),
    ),
    "draft_restored": st.builds(
        DraftRestored, ts=_TS, revision=_COUNT, manifest=_MANIFEST
    ),
    "session_deleted": st.builds(SessionDeleted, ts=_TS),
    "session_revoked": st.builds(SessionRevoked, ts=_TS, session_id=_IDS, reason=_TEXT),
}

_ANY_EVENT: st.SearchStrategy[BuilderEvent] = st.one_of(*_EVENT_STRATEGIES.values())


def _through_json(type_: str, data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Return the envelope after a real JSON encode and decode."""
    decoded = json.loads(json.dumps({"type": type_, "data": data}))
    return decoded["type"], decoded["data"]


# --- Tests --------------------------------------------------------------------------


def test_event_strategies_cover_every_wire_type_when_registry_is_read() -> None:
    assert set(_EVENT_STRATEGIES) == set(event_types())


# Feature: ai-workflow-builder, Property 22: Events round-trip through JSON
@settings(max_examples=100, deadline=None)
@given(event=_ANY_EVENT)
def test_from_wire_returns_equal_event_when_to_wire_output_is_sent_through_json(
    event: BuilderEvent,
) -> None:
    type_, data = _through_json(*to_wire(event))

    rebuilt = from_wire(type_, data)

    assert type(rebuilt) is type(event)
    assert rebuilt == event


# Feature: ai-workflow-builder, Property 22: Events round-trip through JSON
@settings(max_examples=100, deadline=None)
@given(event=_ANY_EVENT)
def test_to_wire_returns_type_name_and_data_without_type_key_when_event_is_any_type(
    event: BuilderEvent,
) -> None:
    type_, data = to_wire(event)

    assert type_ == event.type
    assert type_ in event_types()
    assert "type" not in data


# Feature: ai-workflow-builder, Property 22: Events round-trip through JSON
@settings(max_examples=100, deadline=None)
@given(event=_ANY_EVENT)
def test_to_wire_is_stable_when_event_is_rebuilt_from_its_own_wire_form(
    event: BuilderEvent,
) -> None:
    wire = to_wire(event)

    assert to_wire(from_wire(*_through_json(*wire))) == wire


# Feature: ai-workflow-builder, Property 22: Events round-trip through JSON
@settings(max_examples=100, deadline=None)
@given(event=_ANY_EVENT)
def test_from_wire_raises_value_error_when_data_holds_a_type_key(
    event: BuilderEvent,
) -> None:
    type_, data = to_wire(event)

    with pytest.raises(ValueError, match="'type' key"):
        from_wire(type_, {**data, "type": type_})


# Feature: ai-workflow-builder, Property 22: Events round-trip through JSON
@settings(max_examples=100, deadline=None)
@given(event=_ANY_EVENT, unknown=_IDS.filter(lambda name: name not in event_types()))
def test_from_wire_raises_value_error_when_type_name_is_unknown(
    event: BuilderEvent, unknown: str
) -> None:
    _, data = to_wire(event)

    with pytest.raises(ValueError):
        from_wire(unknown, data)
