"""WaveRun SQLAlchemy model — per-executed-wave audit row (Phase 12 / WAVE-02).

Table ``wave_runs`` — ONE row per WAVE the ``wave_scheduler`` strategy dispatches
through the single kernel ``run_fanout`` spawn path. Each row records the producing
step + the wave index + the task ids fanned out in that wave + the terminal status,
written by ``ScopedStore.record_wave_run`` (the default-deny scoped writer) and flipped
terminal by ``update_wave_run``. The row carries ``owner_id`` + ``workspace_id`` (both
``nullable=False``, AUTHZ-01) so a cross-owner read returns nothing (default-deny, the
T-12-01-IDOR mitigation). This is the durable substrate the mid-wave resume (12-03) reads.

Mirrors the additive-table precedent (``subagent_run.py``): UUID PK + ``run_id`` FK +
``owner_id`` + ``workspace_id`` + payload cols. ``status`` is a free ``String`` column
(NO ``sa.Enum``, consistent with 0019's free-String ``status``). ``task_ids`` is
``sa.JSON`` (§18 task_ids[]).

Schema source: specs/003-workflow-engine-decoupling/plan.md §18 + 12-SPEC.md.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.types import JSON

from app.models.database import Base


class WaveRun(Base):
    """One row per executed wave — the step + wave index + task ids + status."""

    __tablename__ = "wave_runs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String, ForeignKey("workflow_runs.id"), nullable=False)
    owner_id = Column(String, nullable=False)        # AUTHZ-01
    workspace_id = Column(String, nullable=False)    # AUTHZ-01
    step = Column(String, nullable=False)            # the wave-scheduler step id
    wave_index = Column(Integer, nullable=False)     # 0-based wave ordinal
    task_ids = Column(JSON, nullable=False)          # §18 — task ids fanned out this wave
    status = Column(String, nullable=False)          # running|completed|failed|cancelled (free String)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    __table_args__ = (
        Index("ix_wave_runs_run", "run_id"),
    )
