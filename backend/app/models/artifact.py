"""WorkflowArtifact SQLAlchemy model — Artifact_Store (Phase 3)."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.database import Base


class WorkflowArtifact(Base):
    """One row per Artifact version per run. Immutable — no deletes or overwrites."""

    __tablename__ = "workflow_artifacts"
    __table_args__ = (
        Index("ix_workflow_artifacts_run_type", "workflow_run_id", "type"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_run_id = Column(String, ForeignKey("workflow_runs.id"), nullable=False)
    type = Column(String, nullable=False)                    # Artifact_Type string
    name = Column(String, nullable=False)                    # human-readable name or file path
    content = Column(Text, nullable=False)                   # full artifact content
    version = Column(Integer, nullable=False)                # monotonically increasing per type per run
    schema_version = Column(String, nullable=False, default="1.0", server_default="1.0")
    producing_agent_id = Column(String, nullable=False)
    derived_from_artifact_id = Column(
        String, ForeignKey("workflow_artifacts.id"), nullable=True
    )
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    workflow_run = relationship("WorkflowRun", back_populates="artifacts")
    derived_from = relationship("WorkflowArtifact", remote_side=[id])
