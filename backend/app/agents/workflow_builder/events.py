"""Event and shared value models for the workflow builder session stream.

Everything the Turn_Runner publishes on a Session_Stream is one of the
:data:`BuilderEvent` models defined here (design section 3.3.2, Req 38). The
value models that events and API schemas share (:class:`ToolActivity`,
:class:`CheckResult`, :class:`ChangeSummary`, :class:`LaunchNeed`,
:class:`RunningTurnSnapshot`, :class:`TokenUsage`) and the status literals
(:data:`TurnStatus`, :data:`StopReason`, :data:`Outcome`,
:data:`RevisionKind`, :data:`TargetTrust`) live here too, so the agent layer
never imports ``app.api``.

Wire format: each frame is the existing ``{"type": ..., "data": {...}}``
envelope. :func:`to_wire` splits an event into ``(type, data)`` where ``data``
holds no ``type`` key, and :func:`from_wire` rebuilds the event.

Events carry labels and summaries only (Req 38.16, 38.17). The manifest
travels in ``draft_applied`` and ``draft_restored`` alone, and
``ToolStarted.command`` is the only raw tool argument on the wire. Callers
build ``summary`` from a fixed template per tool, at most 280 characters, and
never from raw output.
"""

from datetime import datetime
from typing import Annotated, Any, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from app.agents.workflow_builder.stages import Stage

__all__ = [
    "BuilderEvent",
    "ChangeSummary",
    "CheckResult",
    "CheckResultEvent",
    "CheckSource",
    "CheckVerdict",
    "DraftApplied",
    "DraftRestored",
    "ErrorEvent",
    "EventBase",
    "LaunchNeed",
    "LimitKind",
    "LimitWarning",
    "Outcome",
    "RevisionKind",
    "RunningTurnSnapshot",
    "SessionDeleted",
    "SessionRevoked",
    "Snapshot",
    "StageChanged",
    "StopReason",
    "TargetTrust",
    "Text",
    "Thinking",
    "TokenUsage",
    "ToolActivity",
    "ToolFinishStatus",
    "ToolFinished",
    "ToolKind",
    "ToolStarted",
    "ToolStatus",
    "TurnCompleted",
    "TurnScoped",
    "TurnStarted",
    "TurnStatus",
    "UsageCounts",
    "event_types",
    "from_wire",
    "to_wire",
]

# --- Status literals (design 3.2.2) -------------------------------------------------

TurnStatus = Literal[
    "running", "completed", "failed", "cancelled", "timed_out", "interrupted"
]
StopReason = Literal[
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
Outcome = Literal["draft", "reply", "unfinished"]
RevisionKind = Literal["seed", "accepted", "undo", "unproposed"]
TargetTrust = Literal["user", "db"]

ToolKind = Literal["read", "write", "script", "lookup", "propose"]
ToolStatus = Literal["running", "ok", "error", "refused", "timed_out"]
ToolFinishStatus = Literal["ok", "error", "refused", "timed_out"]
CheckSource = Literal["skill_validator", "platform_dry_run", "server_gate"]
CheckVerdict = Literal["valid", "invalid", "unknown"]
LimitKind = Literal["time", "tool_calls", "tokens"]
LaunchNeedKind = Literal["uploads", "design", "connector", "source_run"]
_FinalTurnStatus = Literal[
    "completed", "failed", "cancelled", "timed_out", "interrupted"
]


class _Model(BaseModel):
    """Base for every model here: unknown keys are rejected."""

    model_config = ConfigDict(extra="forbid")


# --- Shared value models ------------------------------------------------------------


class ToolActivity(_Model):
    """One tool call as the transcript and the live panel show it."""

    call_id: str
    tool: str
    kind: ToolKind
    label: str
    status: ToolStatus
    duration_ms: int | None = None
    command: str | None = None  # script calls only
    exit_code: int | None = None  # script calls only
    summary: str | None = None


class CheckResult(_Model):
    """The verdict of one validator run, dry run or Server_Gate check."""

    source: CheckSource
    verdict: CheckVerdict
    errors: int
    warnings: int
    attempt: int | None = None
    attempts_left: int | None = None


class ChangeSummary(_Model):
    """What a Draft changed compared with the Canvas state it was based on."""

    added: list[str]
    removed: list[str]
    reordered: bool
    gates_changed: list[str]
    validators_changed: list[str]
    models_changed: list[str]
    prompts_changed: int


class LaunchNeed(_Model):
    """Something the user must provide before the workflow can launch."""

    kind: LaunchNeedKind
    detail: str | None = None  # for example a connector server name


class RunningTurnSnapshot(_Model):
    """The running Turn as a connecting client needs to see it (Req 38.3).

    ``through_seq`` is the ``seq`` of the last event this snapshot already
    reflects, so a client drops turn events with ``seq <= through_seq``
    [pending G-14].
    """

    turn_id: str
    message_id: str
    stage: Stage
    label: str
    started_at: datetime
    through_seq: int = Field(ge=0)
    activity: list[ToolActivity]
    checks: list[CheckResult]


class UsageCounts(_Model):
    """Token counts for one group of model calls."""

    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0


class TokenUsage(UsageCounts):
    """Token usage of a Turn, with the transcript-summary call counted apart."""

    summary: UsageCounts | None = None

    @classmethod
    def zero(cls) -> Self:
        """Return a usage record with every count at zero."""
        return cls()


# --- Event models (design 3.3.2) ----------------------------------------------------


class EventBase(_Model):
    """Fields every event carries (Req 38.2)."""

    ts: datetime


class TurnScoped(EventBase):
    """An event that belongs to one Turn."""

    turn_id: str
    seq: int = Field(ge=1)  # strictly increasing within the turn, starts at 1


class Snapshot(EventBase):
    """Sent first on every connection (Req 38.3, pending G-14)."""

    type: Literal["snapshot"] = "snapshot"
    state: Literal["idle", "running"]
    running_turn: RunningTurnSnapshot | None
    latest_message_id: str | None
    latest_revision: int | None
    latest_unproposed_revision: int | None


class TurnStarted(TurnScoped):
    """A Turn was admitted (Req 38.4)."""

    type: Literal["turn_started"] = "turn_started"
    message_id: str
    model_id: str
    effort: str | None
    skill_hash: str


class StageChanged(TurnScoped):
    """The Turn moved to another stage (Req 38.5)."""

    type: Literal["stage"] = "stage"
    stage: Stage
    label: str


class Thinking(TurnScoped):
    """Reasoning text (Req 38.6)."""

    type: Literal["thinking"] = "thinking"
    text: str


class ToolStarted(TurnScoped):
    """A tool call started (Req 38.7)."""

    type: Literal["tool_started"] = "tool_started"
    call_id: str
    tool: str
    kind: ToolKind
    label: str
    command: str | None  # script calls only, after secret-free normalisation


class ToolFinished(TurnScoped):
    """A tool call ended; exactly one per ``tool_started`` (Req 38.8, 38.9)."""

    type: Literal["tool_finished"] = "tool_finished"
    call_id: str
    status: ToolFinishStatus
    duration_ms: int
    summary: str  # at most 280 characters, built from a fixed template


class CheckResultEvent(TurnScoped):
    """One validator, dry-run or gate check returned (Req 38.10)."""

    type: Literal["check_result"] = "check_result"
    source: CheckSource
    verdict: CheckVerdict
    errors: int
    warnings: int
    attempt: int | None
    attempts_left: int | None


class DraftApplied(TurnScoped):
    """The Server_Gate accepted a Draft (Req 38.11)."""

    type: Literal["draft_applied"] = "draft_applied"
    revision: int
    target_trust: TargetTrust
    change_summary: ChangeSummary
    launch_needs: list[LaunchNeed]
    manifest: dict[str, Any]


class Text(TurnScoped):
    """Assistant text (Req 38.12)."""

    type: Literal["text"] = "text"
    text: str


class LimitWarning(TurnScoped):
    """A Turn reached 80 % of a limit (Req 38.13)."""

    type: Literal["limit_warning"] = "limit_warning"
    kind: LimitKind
    used: int
    limit: int


class TurnCompleted(TurnScoped):
    """A Turn ended with any status (Req 38.14)."""

    type: Literal["turn_completed"] = "turn_completed"
    status: _FinalTurnStatus
    outcome: Outcome
    stop_reason: StopReason | None
    message_id: str
    revision: int | None
    usage: TokenUsage


class ErrorEvent(EventBase):
    """A failure the user should see (Req 38.15).

    ``turn_id`` and ``seq`` are set when the error belongs to a Turn.
    ``message`` is generic: never a stack trace, SQL text or path.
    """

    type: Literal["error"] = "error"
    turn_id: str | None
    seq: int | None
    code: str
    message: str
    retryable: bool


class DraftRestored(EventBase):
    """An Undo stored a restored Canvas state as a new revision [pending G-16]."""

    type: Literal["draft_restored"] = "draft_restored"
    revision: int
    manifest: dict[str, Any]


class SessionDeleted(EventBase):
    """The Session was deleted; the stream closes after this event."""

    type: Literal["session_deleted"] = "session_deleted"


class SessionRevoked(EventBase):
    """The caller's token was revoked (existing run-stream name and shape)."""

    type: Literal["session_revoked"] = "session_revoked"
    session_id: str
    reason: str


BuilderEvent = Annotated[
    Snapshot
    | TurnStarted
    | StageChanged
    | Thinking
    | ToolStarted
    | ToolFinished
    | CheckResultEvent
    | DraftApplied
    | Text
    | LimitWarning
    | TurnCompleted
    | ErrorEvent
    | DraftRestored
    | SessionDeleted
    | SessionRevoked,
    Field(discriminator="type"),
]

_EVENT_ADAPTER: Final[TypeAdapter[BuilderEvent]] = TypeAdapter(BuilderEvent)

_EVENT_CLASSES: Final = (
    Snapshot,
    TurnStarted,
    StageChanged,
    Thinking,
    ToolStarted,
    ToolFinished,
    CheckResultEvent,
    DraftApplied,
    Text,
    LimitWarning,
    TurnCompleted,
    ErrorEvent,
    DraftRestored,
    SessionDeleted,
    SessionRevoked,
)


def event_types() -> frozenset[str]:
    """Return the wire type name of every builder event."""
    return frozenset(cls.model_fields["type"].default for cls in _EVENT_CLASSES)


def to_wire(event: BuilderEvent) -> tuple[str, dict[str, Any]]:
    """Split ``event`` into the ``(type, data)`` pair of the SSE envelope.

    ``data`` is JSON-safe and holds no ``type`` key.
    """
    return event.type, event.model_dump(mode="json", exclude={"type"})


def from_wire(type_: str, data: dict[str, Any]) -> BuilderEvent:
    """Rebuild an event from the ``(type, data)`` pair of the SSE envelope.

    Raises:
        ValueError: ``data`` holds a ``type`` key.
        pydantic.ValidationError: ``type_`` is unknown or ``data`` does not
            match that event's fields. It is a ``ValueError`` subclass and
            never echoes the rejected values.
    """
    if "type" in data:
        raise ValueError("event data must not contain a 'type' key")
    return _EVENT_ADAPTER.validate_python({**data, "type": type_})
