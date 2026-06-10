"""Repository SQLAlchemy model — repo-workflow substrate (Phase 9 / RUNTIME-03).

Table ``repositories`` — one row per repo bound to a run. Owner/workspace-scoped
(AUTHZ-01: every row carries ``owner_id`` + ``workspace_id``), mirroring the
``UserGithubCredential`` owner-scoped/encrypted-pointer shape (``handoff.py:40``):
the ``auth_ref`` column is a pointer to the scoped credential (the PAT/MCP-cred
reference), never the secret itself.

A repo run persists exactly ONE ``repositories`` row + ONE ``kind='repo'``
``workspaces`` row, linked by ``workspaces.repo_id`` → ``repositories.id`` (the FK
wired additively in migration 0017). ``provider`` is a free ``String`` holding
``github`` / ``gitlab`` / ``local`` — NO ``sa.Enum``, consistent with the free
``String`` ``kind`` / ``runtime`` columns on ``workspaces`` (keeps the migration
additive + reversible, R-G).

Schema source: specs/003-workflow-engine-decoupling/plan.md §18 + 09-RESEARCH R-G.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String

from app.models.database import Base


class Repository(Base):
    """A repo bound to a run/workspace. Owner/workspace-scoped (AUTHZ-01)."""

    __tablename__ = "repositories"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(String, nullable=False)        # AUTHZ-01
    workspace_id = Column(String, nullable=False)    # AUTHZ-01
    # Free String (NO sa.Enum): 'github' | 'gitlab' | 'local' — additive/reversible.
    provider = Column(String, nullable=False)
    url = Column(String, nullable=False)
    default_branch = Column(String, nullable=False)
    # Scoped-credential pointer (the PAT/MCP-cred reference), never the secret.
    auth_ref = Column(String, nullable=True)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
