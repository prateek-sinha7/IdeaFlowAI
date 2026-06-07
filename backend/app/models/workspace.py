"""Workspace SQLAlchemy model — RuntimeEnvironment substrate (Phase 5).

Table ``workspaces`` — one row per workspace. The default per-run workspace is
created by the engine (and backfilled for historical runs by migration 0014).
``workspace_id`` on the row equals its own ``id`` so the uniform default-deny
filter ``workspace_id = :ws`` holds for workspace reads too (AUTHZ-01).

Schema source: specs/003-workflow-engine-decoupling/plan.md §18.
``repo_id`` is a Phase 9 (repositories) forward field, nullable for now.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String

from app.models.database import Base


class Workspace(Base):
    """A runtime workspace (sandbox). Default runtime is local (ECS later)."""

    __tablename__ = "workspaces"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(String, nullable=False)        # AUTHZ-01
    # self-id carries the AUTHZ-01 pair; set equal to id at creation for the
    # default per-run workspace so the scope filter `workspace_id = :ws` holds.
    workspace_id = Column(String, nullable=False)    # AUTHZ-01
    kind = Column(String, nullable=False, default="sandbox", server_default="sandbox")
    runtime = Column(String, nullable=False, default="local", server_default="local")
    repo_id = Column(String, nullable=True)          # Phase 9 (repositories)
    ttl = Column(String, nullable=True, default="run_ttl", server_default="run_ttl")
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
