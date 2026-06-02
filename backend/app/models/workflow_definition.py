"""WorkflowDefinition SQLAlchemy model — persisted Workflow DAG (Phase 3)."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from app.models.database import Base


class WorkflowDefinition(Base):
    """Persisted Workflow DAG definition.

    Fields:
    - agents: JSON ordered list of agent IDs
    - artifact_edges: JSON [{from_agent, to_agent, artifact_type}]
    - constitution_ref: key in workflow_memory for per-workflow constitution
    """

    __tablename__ = "workflows"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    agents = Column(Text, nullable=False)                    # JSON: ordered list of agent IDs
    artifact_edges = Column(Text, nullable=False)            # JSON: [{from_agent, to_agent, artifact_type}]
    constitution_ref = Column(String, nullable=True)         # key in workflow_memory
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User")
