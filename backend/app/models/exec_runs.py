"""ExecRun SQLAlchemy model — per-exec-invocation audit row (Phase 10 / EXEC-01).

Table ``exec_runs`` — one row per ``Workspace.exec_command`` invocation recording
the exec outcome (``allowed`` | ``denied`` | ``killed``) at the enforcement point,
so EVERY exec path is audited bypass-proof regardless of caller (T-10-01-07). The
rows are written by ``ScopedStore.record_exec_run`` (the default-deny scoped writer)
via the workspace recorder callback wired in 10-02's host seam.

Mirrors the §18 additive-table precedent (``hook_runs.py``): UUID PK + ``run_id``
FK + ``owner_id`` + ``workspace_id`` (both ``nullable=False``, AUTHZ-01) + payload
cols. ``outcome`` is a free ``String`` (NO ``sa.Enum``, consistent with 0017's
free-String ``provider``). ``output_digest`` carries only a TRUNCATED digest, never
the raw child output (which could carry a secret — T-10-01-03 / T-10-01-06).

Schema source: specs/003-workflow-engine-decoupling/plan.md §18 + 10-SPEC.md.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.types import JSON

from app.models.database import Base


class ExecRun(Base):
    """One row per ``exec_command`` invocation — the outcome the exec resolved to."""

    __tablename__ = "exec_runs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String, ForeignKey("workflow_runs.id"), nullable=False)
    owner_id = Column(String, nullable=False)        # AUTHZ-01
    workspace_id = Column(String, nullable=False)    # AUTHZ-01
    step = Column(String, nullable=False)            # the step/agent id that ran exec
    argv_json = Column(JSON, nullable=False)         # the argv list (never shell str)
    outcome = Column(String, nullable=False)         # allowed|denied|killed (free String)
    exit_code = Column(Integer, nullable=True)       # None for denied/killed
    duration_ms = Column(Integer, nullable=True)     # wall-clock ms for allowed
    policy_snapshot_json = Column(JSON, nullable=True)   # allow/deny + caps snapshot
    output_digest = Column(String, nullable=True)    # TRUNCATED digest, never raw secrets
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    __table_args__ = (
        Index("ix_exec_runs_run", "run_id"),
    )
