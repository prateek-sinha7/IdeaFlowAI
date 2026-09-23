"""RunFinalization SQLAlchemy model — per-run finalization state (sandbox git versioning task 5.1).

Table ``run_finalizations`` — ONE row per run, upsertable. Records the final
published/candidate status, payload chainability decision, git tag assignment
outcome, and chain-context install state written by the post-run finalizer.

The row carries ``owner_id`` + ``workspace_id`` (both ``nullable=False``,
AUTHZ-01) so cross-owner reads return nothing (default-deny IDOR gate).
``run_id`` is UNIQUE — one record per run, designed for upsert.

Schema source: specs/sandbox-git-versioning-v2 task 5.1.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Index, String, UniqueConstraint

from app.models.database import Base


class RunFinalization(Base):
    """One row per run — the finalization outcome written after the run completes."""

    __tablename__ = "run_finalizations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(String, nullable=False)        # AUTHZ-01
    workspace_id = Column(String, nullable=False)    # AUTHZ-01
    run_id = Column(String, nullable=False, unique=True)  # one record per run

    # Published / candidate pipeline status written by the finalizer
    published_status = Column(String, nullable=True)
    candidate_status = Column(String, nullable=True)

    # Payload chainability — whether this run's output can feed a downstream run
    payload_chainable = Column(Boolean, nullable=True)
    non_chainable_reason = Column(String, nullable=True)

    # Payload materialization state
    payload_built = Column(Boolean, nullable=True)
    payload_materialized = Column(Boolean, nullable=True)

    # Git versioning state
    commit_sha = Column(String, nullable=True)
    internal_ref = Column(String, nullable=True)
    git_tag = Column(String, nullable=True)
    tag_state = Column(String, nullable=True)        # "created" | "rolled_back"

    # Chain-context installation state
    chain_context_installed = Column(Boolean, nullable=True)

    created_at = Column(DateTime, nullable=True, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_run_finalizations_owner", "owner_id"),
        Index("ix_run_finalizations_run", "run_id"),
    )
