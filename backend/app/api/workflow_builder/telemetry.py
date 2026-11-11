"""Builder telemetry: turn, script-call and gate-rejection metrics as log records.

Every record is one INFO line on the ``app.api.workflow_builder.telemetry``
logger. The message is ``builder_metric <json>`` so the app's JSON formatter,
which writes only the message, still ships every field. The same fields are
also attached to the record as ``builder_event`` and ``builder_fields`` for
handlers that read record attributes.

Every record carries the Session id and the Turn id (Req 44.2). Fields are
built from an allow-list of numbers, enums, hashes and booleans. Message text,
prompts, manifests, tool output, ``canvas_state`` and secrets are never
accepted as arguments, so they cannot reach a record (Req 42.4, 44.2).

The repository has no OpenTelemetry setup under ``backend/app/``, so this
module adds no exporter. Connecting these records to OpenTelemetry is a
separate decision (task 15.3).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping, MutableMapping
from typing import Any, Final

from app.agents.workflow_builder.adherence import AdherenceRecord
from app.agents.workflow_builder.events import StopReason, TokenUsage, TurnStatus

__all__ = [
    "EVENT_GATE_REJECTION",
    "EVENT_SCRIPT_CALL",
    "EVENT_TURN",
    "LOGGER_NAME",
    "TurnLogAdapter",
    "emit_gate_rejection",
    "emit_script_call",
    "emit_turn_metrics",
    "turn_logger",
]

LOGGER_NAME: Final = "app.api.workflow_builder.telemetry"

EVENT_TURN: Final = "builder.turn"
EVENT_SCRIPT_CALL: Final = "builder.script_call"
EVENT_GATE_REJECTION: Final = "builder.gate_rejection"

_FINAL_STATUSES: Final = frozenset(
    {"completed", "failed", "cancelled", "timed_out", "interrupted"}
)
_MAX_NAME_LENGTH: Final = 80
_UNSAFE_NAME_CHARS: Final = re.compile(r"[^A-Za-z0-9._-]")

_logger = logging.getLogger(LOGGER_NAME)


class TurnLogAdapter(logging.LoggerAdapter[logging.Logger]):
    """Logger adapter that stamps the Session id and Turn id on every entry."""

    def process(
        self, msg: Any, kwargs: MutableMapping[str, Any]
    ) -> tuple[Any, MutableMapping[str, Any]]:
        """Prefix ``msg`` with the ids and add them to the record attributes."""
        extra: Mapping[str, Any] = self.extra or {}
        kwargs["extra"] = {**extra, **kwargs.get("extra", {})}
        prefix = (
            f"session={extra['builder_session_id']} turn={extra['builder_turn_id']} "
        )
        return f"{prefix}{msg}", kwargs


def turn_logger(
    session_id: str, turn_id: str, *, name: str | None = None
) -> TurnLogAdapter:
    """Return a logger whose every entry carries the Session id and Turn id.

    Args:
        session_id: Builder Session id.
        turn_id: Turn id.
        name: Logger name. Defaults to the telemetry logger. Pass
            ``__name__`` from the calling module to keep its own logger name.

    Returns:
        An adapter. Log ids and counts only, never message text, prompts,
        tool output or ``canvas_state`` (Req 42.4, 44.2).
    """
    return TurnLogAdapter(
        logging.getLogger(name or LOGGER_NAME),
        {"builder_session_id": session_id, "builder_turn_id": turn_id},
    )


def _safe_name(value: str) -> str:
    """Return ``value`` reduced to a short, log-safe token."""
    return _UNSAFE_NAME_CHARS.sub("_", value)[:_MAX_NAME_LENGTH]


def _seconds(value: float) -> float:
    """Return ``value`` rounded to milliseconds, never negative."""
    return round(max(value, 0.0), 3)


def _emit(event: str, session_id: str, turn_id: str, fields: dict[str, Any]) -> None:
    """Write one structured metric record at INFO."""
    payload: dict[str, Any] = {
        "event": event,
        "session_id": session_id,
        "turn_id": turn_id,
        **fields,
    }
    _logger.info(
        "builder_metric %s",
        json.dumps(payload, default=str, ensure_ascii=False, sort_keys=True),
        extra={"builder_event": event, "builder_fields": payload},
    )


def emit_turn_metrics(
    *,
    session_id: str,
    turn_id: str,
    status: TurnStatus,
    latency_seconds: float,
    stage_seconds: Mapping[str, float],
    usage: TokenUsage,
    adherence: AdherenceRecord | None,
    skill_hash: str | None,
    stop_reason: StopReason | None = None,
    model_id: str | None = None,
    prompt_version: str | None = None,
) -> None:
    """Emit the metrics of one finished Turn (Req 44.3).

    Args:
        session_id: Builder Session id.
        turn_id: Turn id.
        status: Final status: ``completed``, ``failed``, ``cancelled``,
            ``timed_out`` or ``interrupted``.
        latency_seconds: Wall-clock time from admission to the end of the Turn.
        stage_seconds: Seconds spent in each Stage, keyed by Stage value.
        usage: Token usage of the Turn, including the summary call.
        adherence: The Turn's adherence record, or ``None`` when none exists.
        skill_hash: Skill hash of the Turn's assistant message.
        stop_reason: Why the Turn was stopped, if it was.
        model_id: Model id used for the Turn.
        prompt_version: Prompt version used for the Turn.

    Raises:
        ValueError: ``status`` is not a final Turn status.
    """
    if status not in _FINAL_STATUSES:
        raise ValueError(f"turn metrics need a final status, got {status!r}")
    _emit(
        EVENT_TURN,
        session_id,
        turn_id,
        {
            "status": status,
            "stop_reason": stop_reason,
            "latency_seconds": _seconds(latency_seconds),
            "stage_seconds": {
                _safe_name(str(stage)): _seconds(seconds)
                for stage, seconds in stage_seconds.items()
            },
            "tokens": usage.model_dump(),
            "adherence": adherence.as_dict() if adherence is not None else None,
            "skill_hash": skill_hash,
            "model_id": model_id,
            "prompt_version": prompt_version,
        },
    )


def emit_script_call(
    *,
    session_id: str,
    turn_id: str,
    script: str,
    duration_seconds: float,
    exit_code: int | None,
    refused: bool,
) -> None:
    """Emit the metric of one finished Script_Runner call (Req 44.4).

    Args:
        session_id: Builder Session id.
        turn_id: Turn id.
        script: Script file name. Reduced to a short log-safe token.
        duration_seconds: Time the call took.
        exit_code: Exit code, or ``None`` when the call was refused, timed out
            or was stopped before it exited.
        refused: The runner refused the call.
    """
    _emit(
        EVENT_SCRIPT_CALL,
        session_id,
        turn_id,
        {
            "script": _safe_name(script),
            "duration_seconds": _seconds(duration_seconds),
            "exit_code": exit_code,
            "refused": refused,
        },
    )


def emit_gate_rejection(
    *,
    session_id: str,
    turn_id: str,
    rejection_count: int,
    check_count: int = 0,
) -> None:
    """Emit the metric for a Draft the Server_Gate rejected (Req 44.5).

    Call it for a rejected ``propose_draft`` only. Dry_Runs are not rejections.

    Args:
        session_id: Builder Session id.
        turn_id: Turn id.
        rejection_count: Rejections so far in this Turn, including this one.
        check_count: Number of failed checks the gate returned. Their text is
            not logged.
    """
    _emit(
        EVENT_GATE_REJECTION,
        session_id,
        turn_id,
        {"rejection_count": rejection_count, "check_count": check_count},
    )
