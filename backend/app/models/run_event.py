"""RunEvent SQLAlchemy model — durable run event log (Phase 5).

Table ``run_events`` — append-only, one row per emitted engine event.
``seq`` is a monotonic per-run counter stamped by the engine sink (plan 05-04);
``event_id`` is a generated uuid for idempotent replay. Every row carries
``owner_id`` + ``workspace_id`` (AUTHZ-01).

Schema source: specs/003-workflow-engine-decoupling/plan.md §18.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.types import JSON

from app.models.database import Base


class RunEvent(Base):
    """One row per engine event. Append-only; ordered by (run_id, seq)."""

    __tablename__ = "run_events"
    __table_args__ = (
        Index("ix_run_events_run_seq", "run_id", "seq"),
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
