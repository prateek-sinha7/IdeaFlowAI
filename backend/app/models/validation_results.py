"""ValidationResult SQLAlchemy model — per-validator-run issue record (Phase 8 / §18).

Table ``validation_results`` — one row per validator run/attempt recording the
issues a registered ``Validator`` produced for a step's deliverable (VALID-04 /
D-10). The rows are CONSUMED in 08-04 (the Validator framework + generic
fix-loop); 08-02 lands the additive table + model only.

Mirrors the §18 additive-table precedent (``run_capabilities.py``): UUID PK +
``run_id`` FK + ``owner_id`` + ``workspace_id`` (both ``nullable=False``,
AUTHZ-01) + payload cols. Writes go through the Phase-5 ``ScopedStore``
(default-deny, owner/workspace-scoped). Severity is the UI label produced by the
single ``map_severity`` (validators/severity.py) — CRITICAL/HIGH/MEDIUM/LOW.

Schema source: specs/003-workflow-engine-decoupling/plan.md §18.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.types import JSON

from app.models.database import Base


class ValidationResult(Base):
    """One row per validator run/attempt — the issues it produced for a step."""

    __tablename__ = "validation_results"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String, ForeignKey("workflow_runs.id"), nullable=False)
    owner_id = Column(String, nullable=False)        # AUTHZ-01
    workspace_id = Column(String, nullable=False)    # AUTHZ-01
    step = Column(String, nullable=False)            # the step/agent id validated
    validator = Column(String, nullable=False)       # registered validator name
    severity = Column(String, nullable=True)         # CRITICAL|HIGH|MEDIUM|LOW (worst issue)
    attempt = Column(Integer, nullable=False, default=0)  # fix-loop attempt number
    issues = Column(JSON, nullable=True)             # list of Issue records
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    __table_args__ = (
        Index("ix_validation_results_run_step", "run_id", "step"),
    )
