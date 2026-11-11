"""Unit tests for builder telemetry (task 15.11, Req 42.4, 49.2)."""

from __future__ import annotations

import json
import logging

import pytest

from app.agents.workflow_builder.adherence import AdherenceRecord
from app.agents.workflow_builder.events import TokenUsage
from app.api.workflow_builder.telemetry import (
    EVENT_GATE_REJECTION,
    EVENT_SCRIPT_CALL,
    EVENT_TURN,
    LOGGER_NAME,
    emit_gate_rejection,
    emit_script_call,
    emit_turn_metrics,
    turn_logger,
)

SECRET_TEXT = "my-private-prompt-text"


def _payload(record: logging.LogRecord) -> dict[str, object]:
    message = record.getMessage()
    assert message.startswith("builder_metric ")
    return json.loads(message[len("builder_metric ") :])


class _LiveRecords:
    """Read ``caplog.records`` at access time; caplog swaps the list per phase."""

    def __init__(self, caplog: pytest.LogCaptureFixture) -> None:
        self._caplog = caplog

    def __len__(self) -> int:
        return len(self._caplog.records)

    def __getitem__(self, index: int) -> logging.LogRecord:
        return self._caplog.records[index]

    def __eq__(self, other: object) -> bool:
        return list(self._caplog.records) == other


@pytest.fixture
def records(caplog: pytest.LogCaptureFixture) -> "_LiveRecords":
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    return _LiveRecords(caplog)


def _adherence() -> AdherenceRecord:
    return AdherenceRecord(
        manifest_turn=True,
        mandatory_read={"SKILL.md": True},
        overview_ran=True,
        example_ran=False,
        validator_ran=True,
        last_validator_verdict=None,
    )


def test_emit_turn_metrics_writes_ids_and_numbers_when_turn_finishes(
    records: list[logging.LogRecord],
) -> None:
    emit_turn_metrics(
        session_id="s1",
        turn_id="t1",
        status="completed",
        latency_seconds=1.23456,
        stage_seconds={"thinking": 0.5, "bad stage/name": -1.0},
        usage=TokenUsage(input=10, output=5),
        adherence=_adherence(),
        skill_hash="sha256:abc",
        model_id="model-x",
        prompt_version="v1:x",
    )

    assert len(records) == 1
    data = _payload(records[0])
    assert data["event"] == EVENT_TURN
    assert (data["session_id"], data["turn_id"]) == ("s1", "t1")
    assert data["latency_seconds"] == 1.235
    assert data["stage_seconds"] == {"thinking": 0.5, "bad_stage_name": 0.0}
    assert data["tokens"]["input"] == 10  # type: ignore[index]
    assert data["adherence"]["manifest_turn"] is True  # type: ignore[index]
    assert records[0].builder_event == EVENT_TURN  # type: ignore[attr-defined]


def test_emit_turn_metrics_raises_when_status_is_not_final(
    records: list[logging.LogRecord],
) -> None:
    with pytest.raises(ValueError):
        emit_turn_metrics(
            session_id="s1",
            turn_id="t1",
            status="running",  # type: ignore[arg-type]
            latency_seconds=0,
            stage_seconds={},
            usage=TokenUsage.zero(),
            adherence=None,
            skill_hash=None,
        )

    assert records == []


def test_emit_turn_metrics_carries_no_message_text_when_ids_look_like_text(
    records: list[logging.LogRecord],
) -> None:
    emit_turn_metrics(
        session_id="s1",
        turn_id="t1",
        status="failed",
        latency_seconds=0.1,
        stage_seconds={},
        usage=TokenUsage.zero(),
        adherence=None,
        skill_hash=None,
        stop_reason="error",
    )

    data = _payload(records[0])
    assert data["adherence"] is None
    assert data["stop_reason"] == "error"
    assert set(data) == {
        "event",
        "session_id",
        "turn_id",
        "status",
        "stop_reason",
        "latency_seconds",
        "stage_seconds",
        "tokens",
        "adherence",
        "skill_hash",
        "model_id",
        "prompt_version",
    }


def test_emit_script_call_sanitises_script_name_when_name_has_unsafe_chars(
    records: list[logging.LogRecord],
) -> None:
    emit_script_call(
        session_id="s1",
        turn_id="t1",
        script=f"a b/{SECRET_TEXT}$.py " + "x" * 200,
        duration_seconds=-2,
        exit_code=None,
        refused=True,
    )

    data = _payload(records[0])
    assert data["event"] == EVENT_SCRIPT_CALL
    script = str(data["script"])
    assert len(script) == 80
    assert " " not in script and "/" not in script and "$" not in script
    assert data["duration_seconds"] == 0.0
    assert data["exit_code"] is None
    assert data["refused"] is True


def test_emit_gate_rejection_logs_counts_only_when_gate_rejects(
    records: list[logging.LogRecord],
) -> None:
    emit_gate_rejection(session_id="s1", turn_id="t1", rejection_count=2, check_count=3)

    data = _payload(records[0])
    assert data == {
        "event": EVENT_GATE_REJECTION,
        "session_id": "s1",
        "turn_id": "t1",
        "rejection_count": 2,
        "check_count": 3,
    }


def test_turn_logger_prefixes_ids_and_sets_attributes_when_logging(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="custom.name")
    log = turn_logger("s9", "t9", name="custom.name")

    log.info("done n=%d", 3)

    record = caplog.records[0]
    assert record.name == "custom.name"
    assert record.getMessage() == "session=s9 turn=t9 done n=3"
    assert record.builder_session_id == "s9"  # type: ignore[attr-defined]
    assert record.builder_turn_id == "t9"  # type: ignore[attr-defined]
