"""Workflow run SQLAlchemy model — tracks pipeline executions."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.types import JSON

from app.models.database import Base


class WorkflowRun(Base):
    """Workflow run model — represents a single pipeline execution."""

    __tablename__ = "workflow_runs"
    __table_args__ = (Index("ix_workflow_runs_parent", "parent_run_id"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False, default="Untitled")
    type = Column(String, nullable=False)  # "user_stories" | "ppt" | "prototype"
    status = Column(String, nullable=False, default="running")
    # Extended status values (Phase 3):
    # clarifying | waiting_for_user | planning | analyzing | generating |
    # revising | completed | failed | cancelled
    # Phase 13 (IN-03): degraded — the run COMPLETED with a deliverable but
    # one or more agents failed and never completed (WR-05 terminal payload
    # status: "degraded"). Distinct from "failed" (no deliverable at all).
    input = Column(Text, nullable=False)  # The user's idea/prompt
    output = Column(Text, nullable=True)  # JSON string of final output
    agent_outputs = Column(Text, nullable=True)  # JSON array of per-agent thinking/output
    agent_count = Column(Integer, nullable=False, default=0)
    duration = Column(Float, nullable=True)  # Total execution time in seconds
    error = Column(Text, nullable=True)  # Error message if failed
    token_usage = Column(Text, nullable=True)  # JSON: {total_input, total_output, ...}
    model_id = Column(String, nullable=True)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    completed_at = Column(DateTime, nullable=True)

    # Phase 3 columns (added by migration 0012). NOTE: pipeline_run_id was dropped
    # in migration 0013 — WorkflowRun.id is now the single run identifier used
    # end-to-end by the engine, state machine, and artifact store.
    parent_run_id = Column(String, ForeignKey("workflow_runs.id"), nullable=True)
    session_id = Column(String, nullable=True)           # = user_id (JWT sub)
    execution_gate = Column(String, nullable=True)       # PROCEED | CLARIFY_REQUIRED
    execution_strategy = Column(String, nullable=True)   # sequential | parallel | conditional
    planning_context_unavailable = Column(
        Boolean, nullable=True, default=False, server_default="0"
    )

    # Phase 5 columns (added additively by migration 0014). owner_id/workspace_id
    # are backfilled for existing rows (owner_id = user_id, a default per-run
    # workspace) — see migration 0014. plan_id (Phase 4) and budget_snapshot_json
    # (Phase 11) are forward fields, nullable until those phases populate them.
    owner_id = Column(String, nullable=True)             # AUTHZ-01 (backfilled)
    workspace_id = Column(String, nullable=True)         # AUTHZ-01 (backfilled)
    source_run_id = Column(String, nullable=True)
    plan_id = Column(String, nullable=True)              # Phase 4 forward field
    budget_snapshot_json = Column(JSON, nullable=True)   # Phase 11 forward field

    # Phase 22 columns (added additively by migration 0022 — UXFIX-02 / D-19).
    # The engine ALREADY emits deliverable_mimetype/deliverable_filename on every
    # pipeline_complete (engine.py:2117-2128) and both keys are in
    # _VOLATILE_STRIP_KEYS (INV-3-safe by construction). Persist them on the run
    # row so history-reopen drives the deliverable mimetype from the DECLARED/
    # resolved value, not the text-sniff heuristic — so a binary deliverable
    # (e.g. application/zip) re-renders faithfully. Nullable: legacy rows stay
    # NULL and fall back to the FE deriveDeliverableMimetype heuristic (parity).
    deliverable_mimetype = Column(String, nullable=True)
    deliverable_filename = Column(String, nullable=True)

    user = relationship("User", back_populates="workflow_runs")
    parent_run = relationship("WorkflowRun", remote_side=[id])
    # (The legacy ``artifacts`` -> WorkflowArtifact relationship was removed in 05-07
    #  when the thin ``workflow_artifacts`` table was dropped; artifacts now live in
    #  the persisted ``artifact_refs`` table — see app/models/artifact_ref.py.)
    clarifications = relationship("WorkflowClarification", back_populates="workflow_run", lazy="dynamic")
