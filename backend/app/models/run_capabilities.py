"""RunCapabilities SQLAlchemy model — per-run capability snapshot (Phase 5).

Table ``run_capabilities`` — one row per run recording the capability set the
run executed under (runtime, model overrides, skills, hooks, integrations, MCP
servers, versions). ``runtime`` is populated ``langchain_deepagents`` by the
engine (plan 05-04). Forward fields land in later phases (6/8/9). Every row
carries ``owner_id`` + ``workspace_id`` (AUTHZ-01).

Schema source: specs/003-workflow-engine-decoupling/plan.md §18.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.types import JSON

from app.models.database import Base


class RunCapabilities(Base):
    """One row per run — the capability/runtime snapshot it executed under."""

    __tablename__ = "run_capabilities"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String, ForeignKey("workflow_runs.id"), nullable=False)
    owner_id = Column(String, nullable=False)        # AUTHZ-01
    workspace_id = Column(String, nullable=False)    # AUTHZ-01
    runtime = Column(String, nullable=False)         # e.g. langchain_deepagents (05-04)
    model_overrides = Column(JSON, nullable=True)    # Phase 6
    skills = Column(JSON, nullable=True)             # Phase 8
    hooks = Column(JSON, nullable=True)              # Phase 8
    integrations = Column(JSON, nullable=True)       # Phase 9
    mcp_servers = Column(JSON, nullable=True)        # Phase 9
    versions = Column(JSON, nullable=True)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
