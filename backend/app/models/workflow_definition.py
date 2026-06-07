"""WorkflowDefinition SQLAlchemy model — persisted Workflow DAG (Phase 3)."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.types import JSON

from app.models.database import Base


class WorkflowDefinition(Base):
    """Persisted Workflow DAG definition.

    Fields:
    - agents: JSON ordered list of agent IDs
    - artifact_edges: JSON [{from_agent, to_agent, artifact_type}]
    - constitution_ref: key in workflow_memory for per-workflow constitution
    """

    __tablename__ = "workflows"
    __table_args__ = (Index("ix_workflows_user", "user_id"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    agents = Column(Text, nullable=False)                    # JSON: ordered list of agent IDs
    artifact_edges = Column(Text, nullable=False)            # JSON: [{from_agent, to_agent, artifact_type}]
    constitution_ref = Column(String, nullable=True)         # key in workflow_memory
    # Phase 5 columns (added additively by migration 0014). DB-authored user
    # workflows are v2 — `workflows` lands as file-backed manifest metadata only,
    # so owner_id/workspace_id are nullable (file-backed manifests have no owner
    # yet). `source` defaults to "file"; `manifest_json` holds the declarative
    # manifest; `version` is the manifest revision.
    owner_id = Column(String, nullable=True)                 # AUTHZ-01
    workspace_id = Column(String, nullable=True)             # AUTHZ-01
    source = Column(String, nullable=False, default="file", server_default="file")
    manifest_json = Column(JSON, nullable=True)
    version = Column(Integer, nullable=False, default=1, server_default="1")
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
