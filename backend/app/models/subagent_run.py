"""SubagentRun SQLAlchemy model — per-fan-out-child audit row (Phase 11 / FANOUT-10).

Table ``subagent_runs`` — ONE row per fan-out child spawned through the single
kernel ``run_fanout`` spawn path. Each row records the worker agent + the parent
step + the nesting depth + the isolation scope + the terminal status, written by
``ScopedStore.record_subagent_run`` (the default-deny scoped writer) and flipped
terminal by ``update_subagent_run``. The row carries ``owner_id`` + ``workspace_id``
(both ``nullable=False``, AUTHZ-01) so a cross-owner read returns nothing
(default-deny, the FANOUT-10 mitigation, T-11-01-03).

Mirrors the additive-table precedent (``exec_runs.py`` / ``hook_runs.py``): UUID PK +
``parent_run_id`` FK + ``owner_id`` + ``workspace_id`` + payload cols. ``isolation``
and ``status`` are free ``String`` columns (NO ``sa.Enum``, consistent with 0018's
free-String ``outcome``). ``cost`` is ``sa.JSON`` (cost_class-weighted; € dormant).

Schema source: specs/003-workflow-engine-decoupling/plan.md §18 + 11-SPEC.md.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.types import JSON

from app.models.database import Base


class SubagentRun(Base):
    """One row per fan-out child — the worker the spawn resolved to + its status."""

    __tablename__ = "subagent_runs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    parent_run_id = Column(String, ForeignKey("workflow_runs.id"), nullable=False)
    owner_id = Column(String, nullable=False)        # AUTHZ-01
    workspace_id = Column(String, nullable=False)    # AUTHZ-01
    parent_step = Column(String, nullable=False)     # the fan-out step id that spawned it
    worker_agent = Column(String, nullable=False)    # resolved worker agent id
    depth = Column(Integer, nullable=False)          # sub-run nesting depth
    isolation = Column(String, nullable=False)       # shared_read|sub_sandbox|worktree (free String)
    status = Column(String, nullable=False)          # running|complete|failed|cancelled (free String)
    tokens = Column(Integer, nullable=True)          # accumulated child tokens
    cost = Column(JSON, nullable=True)               # cost_class-weighted (€ dormant)
    task_id = Column(String, nullable=True)          # RESUME-06: plan-global task id (skip-cursor key)
    worker_index = Column(Integer, nullable=True)    # RESUME-06: wave-local worker position (audit)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    __table_args__ = (
        Index("ix_subagent_runs_parent", "parent_run_id"),
    )
