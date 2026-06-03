"""WorkflowClarification SQLAlchemy model — per-run Q&A pairs (Phase 3)."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.database import Base


class WorkflowClarification(Base):
    """Per-run Q&A pairs from the Clarify_Engine. Structured, not a JSON blob."""

    __tablename__ = "workflow_clarifications"
    __table_args__ = (Index("ix_workflow_clarifications_run", "workflow_run_id"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_run_id = Column(String, ForeignKey("workflow_runs.id"), nullable=False)
    question_id = Column(String, nullable=False)
    question_text = Column(Text, nullable=False)
    impact_level = Column(String, nullable=False)            # "high" | "medium" | "low"
    answer_type = Column(String, nullable=False)             # "free_text" | "single_choice" | ...
    options = Column(Text, nullable=True)                    # JSON array of strings
    answer = Column(Text, nullable=True)                     # user's answer (NULL until answered)
    recommended_answer = Column(Text, nullable=True)
    round = Column(Integer, nullable=False, default=1, server_default="1")  # 1, 2, or 3
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    answered_at = Column(DateTime, nullable=True)

    workflow_run = relationship("WorkflowRun", back_populates="clarifications")
