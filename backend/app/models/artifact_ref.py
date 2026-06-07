"""ArtifactRef SQLAlchemy model — typed artifact persistence (Phase 5).

Table ``artifact_refs`` REPLACES the Phase 3 ``workflow_artifacts`` table
(``app/models/artifact.py``). The thin-store ``WorkflowArtifact`` model is
dropped LAST in migration 0015 (plan 05-06) after the read-cutover lands; both
models coexist during the dual-write window.

Schema source: specs/003-workflow-engine-decoupling/plan.md §6 (ArtifactRef
fields) + §18 (persistence schema). Every row carries ``owner_id`` +
``workspace_id`` (AUTHZ-01) so the default-deny scope filter applies uniformly.
``content`` is stored INLINE (D-01).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.types import JSON

from app.models.database import Base


class ArtifactRef(Base):
    """One row per Artifact version per run. Immutable — no deletes or overwrites."""

    __tablename__ = "artifact_refs"
    __table_args__ = (
        Index("ix_artifact_refs_run_kind", "run_id", "kind"),
        Index("ix_artifact_refs_content_hash", "content_hash"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String, ForeignKey("workflow_runs.id"), nullable=False)
    owner_id = Column(String, nullable=False)        # AUTHZ-01
    workspace_id = Column(String, nullable=False)    # AUTHZ-01
    kind = Column(String, nullable=False)            # typed artifact kind
    producer_step = Column(String, nullable=False)
    producer_agent = Column(String, nullable=False)
    task_id = Column(String, nullable=True)
    content = Column(Text, nullable=False)           # inline content (D-01)
    content_hash = Column(String, nullable=False)    # sha256 hexdigest of content
    location = Column(String, nullable=False)
    version = Column(Integer, nullable=False)        # monotonic per (run, kind)
    parents = Column(JSON, nullable=True, default=list)  # lineage parent ids
    derived_from = Column(
        String, ForeignKey("artifact_refs.id"), nullable=True
    )
    visibility = Column(
        String, nullable=False, default="private", server_default="private"
    )
    retention = Column(
        String, nullable=False, default="run_ttl", server_default="run_ttl"
    )
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
