"""Request and response schemas of the AI Workflow Builder REST API.

Design section 3.2.2. The value models that events and API schemas share
(:class:`ToolActivity`, :class:`CheckResult`, :class:`ChangeSummary`,
:class:`LaunchNeed`, :class:`RunningTurnSnapshot` and the status literals) are
defined once in ``app.agents.workflow_builder.events`` and reused here, so the
wire shape of a tool row is the same in the transcript, the snapshot and the
stream. ``ToolActivityOut``, ``CheckResultOut`` and ``ActivityLine`` are names
for those shared models, not copies.

Request models reject unknown keys. Validation errors go through the
``RequestValidationError`` handler in ``app/main.py``, which never echoes the
rejected value, and the validators here raise generic messages for the same
reason (Req 42.5).
"""

from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.agents.workflow_builder.events import (
    ChangeSummary,
    CheckResult,
    LaunchNeed,
    Outcome,
    RevisionKind,
    RunningTurnSnapshot,
    StopReason,
    TargetTrust,
    ToolActivity,
    TurnStatus,
)
from app.api.capabilities import ModelCatalogEntry
from app.core.config import settings

__all__ = [
    "MAX_ID_CHARS",
    "ActivityLine",
    "ActivitySummary",
    "BuilderModelsResponse",
    "ChangeSummary",
    "CheckResultOut",
    "CreateSessionRequest",
    "DraftRevisionOut",
    "ErrorOut",
    "LaunchNeed",
    "LinkRequest",
    "Outcome",
    "RevisionKind",
    "RunningTurnSnapshot",
    "SendMessageRequest",
    "SessionDetail",
    "SessionPage",
    "SessionSummary",
    "StopReason",
    "TargetTrust",
    "ToolActivityOut",
    "TranscriptMessage",
    "TurnAccepted",
    "TurnStatus",
    "UndoRequest",
]

# --- Names for the shared value models ----------------------------------------------

ToolActivityOut = ToolActivity
CheckResultOut = CheckResult
ActivityLine = ToolActivity  # the frontend's name for one activity row


class _Request(BaseModel):
    """Base for request bodies: unknown keys are rejected."""

    model_config = ConfigDict(extra="forbid")


class _Response(BaseModel):
    """Base for response bodies."""

    model_config = ConfigDict(extra="forbid")


# --- Requests -----------------------------------------------------------------------


# Longest id or effort value a request may carry. Catalog ids and row ids are far
# shorter; the cap refuses an oversized value at the boundary, before any lookup.
MAX_ID_CHARS = 200


class CreateSessionRequest(_Request):
    """Body of ``POST /sessions``. Edit mode names the saved workflow."""

    mode: Literal["create", "edit"]
    # required when mode == "edit"
    workflow_id: str | None = Field(default=None, max_length=MAX_ID_CHARS)
    model_id: str = Field(max_length=MAX_ID_CHARS)
    effort: str | None = Field(default=None, max_length=MAX_ID_CHARS)

    @model_validator(mode="after")
    def _edit_mode_needs_workflow(self) -> Self:
        """Require ``workflow_id`` in edit mode."""
        if self.mode == "edit" and not self.workflow_id:
            raise ValueError("workflow_id is required when mode is 'edit'")
        return self


class SendMessageRequest(_Request):
    """Body of ``POST /sessions/{id}/messages`` (check 5 of design 3.1.2)."""

    content: str  # 1..BUILDER_MAX_MESSAGE_CHARS code points, not whitespace-only
    model_id: str = Field(max_length=MAX_ID_CHARS)
    effort: str | None = Field(max_length=MAX_ID_CHARS)
    canvas_state: dict[str, Any]
    client_message_id: str = Field(pattern=r"^[A-Za-z0-9_-]{8,64}$")

    @field_validator("content")
    @classmethod
    def _content_within_limits(cls, value: str) -> str:
        """Reject whitespace-only content and content over the code-point cap.

        ``len(str)`` counts code points, the same count the panel uses
        (``Array.from(text).length``) [pending G-23]. The message never
        includes the content.
        """
        if not value.strip():
            raise ValueError("content must not be empty")
        if len(value) > settings.BUILDER_MAX_MESSAGE_CHARS:
            raise ValueError("content is too long")
        return value


class UndoRequest(_Request):
    """Body of ``POST /sessions/{id}/undo``."""

    expected_revision: int = Field(ge=0)


class LinkRequest(_Request):
    """Body of ``POST /sessions/{id}/link``."""

    workflow_id: str = Field(min_length=1, max_length=MAX_ID_CHARS)


# --- Responses ----------------------------------------------------------------------


class TurnAccepted(_Response):
    """Answer to an admitted message or retry (202)."""

    turn_id: str
    message_id: str
    replayed: bool = False


class ErrorOut(_Response):
    """A stored turn error as the transcript shows it. Generic text only."""

    code: str
    message: str
    retryable: bool


class ActivitySummary(_Response):
    """Totals behind "14 actions, 2 checks, 1 min 40 s" on a finished turn."""

    actions: int = Field(ge=0)
    checks: int = Field(ge=0)
    duration_ms: int = Field(ge=0)


class DraftRevisionOut(_Response):
    """One stored revision of the session's draft."""

    revision: int
    kind: RevisionKind
    manifest: dict[str, Any]
    target_trust: TargetTrust | None
    change_summary: ChangeSummary | None
    launch_needs: list[LaunchNeed]
    source_turn_id: str | None
    created_at: datetime


class TranscriptMessage(_Response):
    """One user or assistant message of the transcript."""

    id: str
    seq: int
    role: Literal["user", "assistant"]
    turn_id: str
    reply_to_message_id: str | None
    status: TurnStatus | Literal["accepted"]
    outcome: Outcome | None
    stop_reason: StopReason | None
    content: str
    thinking: str | None
    model_id: str
    effort: str | None
    skill_hash: str | None
    skill_updated: bool  # skill_hash differs from the previous assistant message
    error: ErrorOut | None
    revision: int | None  # accepted revision of this turn
    activity: list[ToolActivityOut]  # assistant only
    activity_summary: ActivitySummary | None
    created_at: datetime
    ended_at: datetime | None


class SessionSummary(_Response):
    """A session as the list and the popup show it."""

    id: str
    title: str
    mode: Literal["create", "edit"]
    workflow_id: str | None
    model_id: str
    effort: str | None
    running: bool
    created_at: datetime
    updated_at: datetime


class SessionDetail(SessionSummary):
    """A session with its transcript, drafts and running-turn snapshot."""

    target_trust: TargetTrust
    skill_hash: str
    messages: list[TranscriptMessage]
    latest_draft: DraftRevisionOut | None
    latest_unproposed: DraftRevisionOut | None  # only when newer than latest_draft
    running_turn: RunningTurnSnapshot | None
    linked_row_changed: bool


class SessionPage(_Response):
    """One keyset page of the session list."""

    items: list[SessionSummary]
    next_cursor: str | None


class BuilderModelsResponse(_Response):
    """The builder's Chat_List for this user (design 3.2.1, 3.2.2)."""

    models: list[ModelCatalogEntry]  # app.api.capabilities.ModelCatalogEntry, unchanged
    default_model_id: str
    # Reasoning.default_effort per model id; None for a model without levels [pending G-27].
    default_efforts: dict[str, str | None]
