"""Workflow run SQLAlchemy model — tracks pipeline executions."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.database import Base


class WorkflowRun(Base):
    """Workflow run model — represents a single pipeline execution."""

    __tablename__ = "workflow_runs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False, default="Untitled")
    type = Column(String, nullable=False)  # "user_stories" | "ppt" | "prototype"
    status = Column(String, nullable=False, default="running")
    # Extended status values (Phase 3):
    # clarifying | waiting_for_user | planning | analyzing | generating |
    # revising | completed | failed | cancelled
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

    # Phase 3 columns (added by migration 0012)
    parent_run_id = Column(String, ForeignKey("workflow_runs.id"), nullable=True)
    session_id = Column(String, nullable=True)           # = user_id (JWT sub)
    pipeline_run_id = Column(String, nullable=True)      # UUID per run
    execution_gate = Column(String, nullable=True)       # PROCEED | CLARIFY_REQUIRED
    execution_strategy = Column(String, nullable=True)   # sequential | parallel | conditional
    planning_context_unavailable = Column(Boolean, nullable=True, default=False)

    user = relationship("User", back_populates="workflow_runs")
    parent_run = relationship("WorkflowRun", remote_side=[id])
    artifacts = relationship("WorkflowArtifact", back_populates="workflow_run", lazy="dynamic")
    clarifications = relationship("WorkflowClarification", back_populates="workflow_run", lazy="dynamic")
