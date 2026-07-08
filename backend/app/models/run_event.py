"""RunEvent SQLAlchemy model — durable run event log (Phase 5).

Table ``run_events`` — append-only, one row per emitted engine event.
``seq`` is a monotonic per-run counter stamped by the engine sink (plan 05-04);
``event_id`` is a generated uuid for idempotent replay. Every row carries
``owner_id`` + ``workspace_id`` (AUTHZ-01).

Schema source: specs/003-workflow-engine-decoupling/plan.md §18.
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
    UniqueConstraint,
)
from sqlalchemy.types import JSON

from app.models.database import Base


class RunEvent(Base):
    """One row per engine event. Append-only; ordered by (run_id, seq)."""

    __tablename__ = "run_events"
    __table_args__ = (
        Index("ix_run_events_run_seq", "run_id", "seq"),
        # CR-03 (Phase 29): per-run uniqueness backstops. Phase 29 adds a SECOND,
        # concurrently-scheduled run_events writer per run_id — the chat up-channel
        # (chat_message) + narrator (chat_reply) — alongside the engine's own event
        # sink. A plain read-``max(seq)+1``-then-write races that sink (and a
        # double-submitted message_id races itself); without a DB-level backstop the
        # collision silently persists a duplicate ``seq`` (breaking the Last-Event-ID
        # replay contract) or a duplicate row for a retried ``message_id`` (breaking
        # idempotency). These make a racing insert fail LOUDLY (IntegrityError) so the
        # chat writers can retry/resolve it (``ScopedStore.append_event_next_seq``).
        # ADDITIVE (migration 0024): the engine sink is the sole writer of any given
        # seq within a scope today and event_id is a per-run-unique uuid, so no existing
        # correct run violates them.
        #
        # SCOPE = (run_id, owner_id, workspace_id): ``seq``/``event_id`` are unique
        # WITHIN the owner+workspace scope, mirroring ``ScopedStore.read_events``
        # (``_scope_owner_ws`` filters owner_id + workspace_id). A cross-owner store's
        # default-deny read sees an EMPTY tail and restarts its own seq at 1 under its
        # own principal (T-29-10-1) — that is a DIFFERENT scope, not a collision — so the
        # constraint must not span owners. The CR-03 race is between the run's OWN engine
        # sink and its OWN chat endpoint (identical owner+workspace) — caught here.
        UniqueConstraint(
            "run_id", "owner_id", "workspace_id", "event_id",
            name="uq_run_events_scope_event",
        ),
        UniqueConstraint(
            "run_id", "owner_id", "workspace_id", "seq",
            name="uq_run_events_scope_seq",
        ),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String, ForeignKey("workflow_runs.id"), nullable=False)
    owner_id = Column(String, nullable=False)        # AUTHZ-01
    workspace_id = Column(String, nullable=False)    # AUTHZ-01
    seq = Column(Integer, nullable=False)            # monotonic per run (05-04 sink)
    event_id = Column(String, nullable=False)        # uuid — idempotent replay
    type = Column(String, nullable=False)
    payload_json = Column(JSON, nullable=False)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
