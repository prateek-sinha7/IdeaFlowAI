"""HookRun SQLAlchemy model — per-hook-firing audit row (Phase 8 / §18).

Table ``hook_runs`` — one row per ``HookHandler`` firing recording the hook's
outcome (``continue`` | ``warn`` | ``block``) at a lifecycle/tool-call event
(HOOK-04 / D-10). The rows are CONSUMED in 08-07 (the executable hook framework +
``secret_scan``/``otel_tracing``); 08-02 lands the additive table + model only.

Mirrors the §18 additive-table precedent (``run_capabilities.py``): UUID PK +
``run_id`` FK + ``owner_id`` + ``workspace_id`` (both ``nullable=False``,
AUTHZ-01) + payload cols. Writes go through the Phase-5 ``ScopedStore``.

Schema source: specs/003-workflow-engine-decoupling/plan.md §18.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, String
from sqlalchemy.types import JSON

from app.models.database import Base


class HookRun(Base):
    """One row per hook firing — the outcome a hook evaluated to for an event."""

    __tablename__ = "hook_runs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String, ForeignKey("workflow_runs.id"), nullable=False)
    owner_id = Column(String, nullable=False)        # AUTHZ-01
    workspace_id = Column(String, nullable=False)    # AUTHZ-01
    hook = Column(String, nullable=False)            # registered hook name
    event = Column(String, nullable=False)           # lifecycle event the hook fired on
    outcome = Column(String, nullable=False)         # continue|warn|block
    detail = Column(JSON, nullable=True)             # hook-specific detail payload
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    __table_args__ = (
        Index("ix_hook_runs_run", "run_id"),
    )
