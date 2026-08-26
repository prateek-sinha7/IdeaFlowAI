"""WorkflowDefinition SQLAlchemy model — persisted Workflow DAG (Phase 3)."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
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
    __table_args__ = (
        Index("ix_workflows_user", "user_id"),
        # Phase 21 (0021): backs the owner-scoped GET list query.
        Index("ix_workflows_owner_source", "owner_id", "source"),
        # Spec 016 (0039): at most ONE override row per (user, built-in).
        # Partial so the many rows with a NULL overrides_pipeline_type never
        # contend — mirrors the migration's WHERE clause exactly.
        Index(
            "uq_workflows_user_override",
            "user_id",
            "overrides_pipeline_type",
            unique=True,
            sqlite_where=text("overrides_pipeline_type IS NOT NULL"),
            postgresql_where=text("overrides_pipeline_type IS NOT NULL"),
        ),
    )

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
    base_pipeline_type = Column(String, nullable=True)       # Phase 21: saved-workflow base type ("custom" v1)
    model_overrides = Column(JSON, nullable=True)            # Phase 21: persisted per-agent {agent_id: model_id}
    description = Column(String, nullable=True)              # Phase 21 (WR-03): user free-text blurb (dedicated; NOT constitution_ref)
    attached_skills = Column(JSON, nullable=True)             # persisted UI-attached skills (list[dict], same shape as the launch path's attached_skills)
    attached_hooks = Column(JSON, nullable=True)              # persisted UI-attached hooks (list[dict], same shape as the launch path's attached_hooks)
    # Spec 016 (migration 0039) — user override of a BUILT-IN workflow.
    #
    # `overrides_pipeline_type` is the built-in id this row replaces for its
    # owner ("ppt"). NULL for every ordinary saved workflow, which is what keeps
    # the mechanism inert for anyone who has not opted in. Distinct from
    # `base_pipeline_type` above, which means "which entitlement key applies /
    # what did I start from" — a user may hold several ordinary copies with
    # base_pipeline_type="ppt" that are NOT the override, so overloading that
    # column would leave "which one wins" undefined.
    #
    # A partial unique index on (user_id, overrides_pipeline_type) makes "save
    # once, or overwrite always" a database guarantee rather than a racy
    # pre-check.
    #
    # `override_enabled` is the checkbox, read by BOTH the read endpoints and
    # the launch resolve — one flag, so the screen and the run cannot disagree
    # about which plan is in force.
    #
    # `base_version` is the base manifest's `version` at save time, so a later
    # "the original has changed since you customised it" notice has something to
    # compare against. Only meaningful on an override row.
    overrides_pipeline_type = Column(String, nullable=True)
    override_enabled = Column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    base_version = Column(Integer, nullable=True)
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
