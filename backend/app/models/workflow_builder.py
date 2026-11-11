"""AI Workflow Builder SQLAlchemy models (migration 0051).

Three tables back a builder session (design §4.2 to §4.4):

- ``workflow_builder_sessions``: one row per builder conversation.
- ``workflow_builder_messages``: user, assistant (one per turn) and tool rows.
- ``workflow_builder_drafts``: numbered manifest revisions of a session.

Authorisation key: every row carries ``user_id`` (FK ``users.id``) and queries
filter on it, never on ``owner_id`` (Req 24.6, 24.7). ``owner_id`` and
``workspace_id`` are ``NOT NULL`` and are stamped with the user id on insert,
the convention ``user_workflows.py`` documents ("user_id = owner_id =
workspace_id = current_user.id"). [pending G-37]

Deleting the linked saved workflow sets ``workflow_builder_sessions.workflow_id``
to NULL at the database level (Req 20.16); no application code is involved.

The migration that creates these tables is ``0051_workflow_builder``. Its
indexes and constraints must mirror the declarations here exactly.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.types import JSON

from app.models.database import Base

# --- Value vocabularies (strings stored in the String columns) ---------------

# ``workflow_builder_sessions.mode``
SESSION_MODE_CREATE = "create"
SESSION_MODE_EDIT = "edit"

# ``workflow_builder_messages.role``
MESSAGE_ROLE_USER = "user"
MESSAGE_ROLE_ASSISTANT = "assistant"
MESSAGE_ROLE_TOOL = "tool"

# ``workflow_builder_messages.status``. User rows are always ``accepted``
# [pending G-37]; assistant and tool rows use their own sets.
MESSAGE_STATUS_USER_ACCEPTED = "accepted"
MESSAGE_STATUS_RUNNING = "running"
MESSAGE_STATUS_COMPLETED = "completed"
MESSAGE_STATUS_FAILED = "failed"
MESSAGE_STATUS_CANCELLED = "cancelled"
MESSAGE_STATUS_TIMED_OUT = "timed_out"
MESSAGE_STATUS_INTERRUPTED = "interrupted"
MESSAGE_STATUS_TOOL_OK = "ok"
MESSAGE_STATUS_TOOL_ERROR = "error"
MESSAGE_STATUS_TOOL_REFUSED = "refused"
MESSAGE_STATUS_TOOL_STOPPED = "stopped"

# ``workflow_builder_drafts.kind`` (Req 24.2)
DRAFT_KIND_SEED = "seed"
DRAFT_KIND_ACCEPTED = "accepted"
DRAFT_KIND_UNDO = "undo"
DRAFT_KIND_UNPROPOSED = "unproposed"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


class WorkflowBuilderSession(Base):
    """One builder conversation (design §4.2)."""

    __tablename__ = "workflow_builder_sessions"

    id = Column(String, primary_key=True, default=_new_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    owner_id = Column(String, nullable=False)  # stamped = user_id [pending G-37]
    workspace_id = Column(String, nullable=False)  # stamped = user_id [pending G-37]
    title = Column(String(80), nullable=False)
    mode = Column(String, nullable=False)  # "create" | "edit"
    # Req 20.16: deleting the saved workflow unlinks the session, no code needed.
    workflow_id = Column(
        String, ForeignKey("workflows.id", ondelete="SET NULL"), nullable=True
    )
    linked_manifest_hash = Column(String, nullable=True)
    model_id = Column(String, nullable=True)
    effort = Column(String, nullable=True)
    target_trust = Column(String, nullable=False, default="user", server_default="user")
    skill_hash = Column(String, nullable=False)  # at creation (Req 20.1)
    next_seq = Column(Integer, nullable=False, default=1, server_default="1")
    turn_count = Column(Integer, nullable=False, default=0, server_default="0")
    clarify_turns_without_draft = Column(
        Integer, nullable=False, default=0, server_default="0"
    )
    first_accepted_revision = Column(Integer, nullable=True)
    summary_text = Column(Text, nullable=True)  # Transcript_Summary
    summary_through_seq = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


# Keyset pagination of the session list (design §4.2). Declared after the class
# so it can reference the columns and use a descending sort key.
Index(
    "ix_wb_sessions_user_updated",
    WorkflowBuilderSession.user_id,
    WorkflowBuilderSession.updated_at.desc(),
    WorkflowBuilderSession.id,
)


class WorkflowBuilderMessage(Base):
    """A user, assistant or tool row of a session transcript (design §4.3)."""

    __tablename__ = "workflow_builder_messages"
    __table_args__ = (
        UniqueConstraint("session_id", "seq", name="uq_wb_messages_session_seq"),
        # Req 21.10: one row per (session, client_message_id) when it is set.
        Index(
            "uq_wb_messages_client_id",
            "session_id",
            "client_message_id",
            unique=True,
            sqlite_where=text("client_message_id IS NOT NULL"),
            postgresql_where=text("client_message_id IS NOT NULL"),
        ),
        # Req 21.8 / Property 13: at most one running assistant row per session.
        Index(
            "uq_wb_messages_one_running",
            "session_id",
            unique=True,
            sqlite_where=text("role = 'assistant' AND status = 'running'"),
            postgresql_where=text("role = 'assistant' AND status = 'running'"),
        ),
        # Rate limit and running-turn count.
        Index("ix_wb_messages_user_role_created", "user_id", "role", "created_at"),
        # Loading a turn's tool rows.
        Index("ix_wb_messages_turn", "turn_id"),
    )

    # For an assistant row this is the turn_id.
    id = Column(String, primary_key=True, default=_new_id)
    session_id = Column(
        String, ForeignKey("workflow_builder_sessions.id"), nullable=False
    )
    user_id = Column(String, nullable=False)
    owner_id = Column(String, nullable=False)  # stamped = user_id [pending G-37]
    workspace_id = Column(String, nullable=False)  # stamped = user_id [pending G-37]
    seq = Column(Integer, nullable=False)  # per session, from sessions.next_seq
    role = Column(String, nullable=False)  # "user" | "assistant" | "tool"
    # Assistant row's id; on a user row, the first turn it started.
    turn_id = Column(String, nullable=False)
    reply_to_message_id = Column(String, nullable=True)
    status = Column(String, nullable=False)
    outcome = Column(String, nullable=True)
    stop_reason = Column(String, nullable=True)
    error_code = Column(String, nullable=True)
    content = Column(Text, nullable=False, default="", server_default=text("''"))
    thinking = Column(Text, nullable=True)  # shown to the user, so stored (Req 5.4)
    # Assistant rows: the turn's thinking, tool-call groups and checks in the order
    # they happened (migration 0054). NULL on rows from before it, and on a turn
    # with none of them; the reader then falls back to ``thinking`` and the tool rows.
    steps = Column(JSON, nullable=True)
    canvas_state = Column(JSON, nullable=True)  # user rows: Undo source (Req 8.4)
    client_message_id = Column(String, nullable=True)
    # Req 24.3: what produced the message.
    model_id = Column(String, nullable=True)
    effort = Column(String, nullable=True)
    skill_hash = Column(String, nullable=True)
    prompt_version = Column(String, nullable=True)
    usage = Column(JSON, nullable=True)
    adherence = Column(JSON, nullable=True)  # assistant rows (§3.6.6)
    tool = Column(JSON, nullable=True)  # tool rows
    revision = Column(Integer, nullable=True)  # assistant rows: accepted revision
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)


class WorkflowBuilderDraft(Base):
    """A numbered manifest revision of a session (design §4.4)."""

    __tablename__ = "workflow_builder_drafts"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "revision", name="uq_wb_drafts_session_revision"
        ),
    )

    id = Column(String, primary_key=True, default=_new_id)
    session_id = Column(
        String, ForeignKey("workflow_builder_sessions.id"), nullable=False
    )
    user_id = Column(String, nullable=False)
    owner_id = Column(String, nullable=False)  # stamped = user_id [pending G-37]
    workspace_id = Column(String, nullable=False)  # stamped = user_id [pending G-37]
    revision = Column(Integer, nullable=False)  # 0 is an edit session's seed
    kind = Column(String, nullable=False)  # seed | accepted | undo | unproposed
    manifest = Column(JSON, nullable=False)
    target_trust = Column(String, nullable=True)  # accepted drafts
    change_summary = Column(JSON, nullable=True)  # accepted drafts
    launch_needs = Column(JSON, nullable=True)  # accepted drafts
    source_turn_id = Column(String, nullable=True)
    source_file = Column(String, nullable=True)  # unproposed: virtual sandbox path
    undo_of_revision = Column(Integer, nullable=True)  # undo rows
    manifest_hash = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
