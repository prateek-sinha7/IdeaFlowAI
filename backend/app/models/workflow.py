"""Workflow run SQLAlchemy model — tracks pipeline executions."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.database import Base


class WorkflowRun(Base):
    """Workflow run model — represents a single pipeline execution."""

    __tablename__ = "workflow_runs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False, default="Untitled")
    type = Column(String, nullable=False)  # "user_stories" | "ppt" | "prototype"
    status = Column(String, nullable=False, default="running")  # "running" | "completed" | "failed"
    input = Column(Text, nullable=False)  # The user's idea/prompt
    output = Column(Text, nullable=True)  # JSON string of final output
    agent_outputs = Column(Text, nullable=True)  # JSON array of per-agent thinking/output
    agent_count = Column(Integer, nullable=False, default=0)
    duration = Column(Float, nullable=True)  # Total execution time in seconds
    error = Column(Text, nullable=True)  # Error message if failed
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    completed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="workflow_runs")
