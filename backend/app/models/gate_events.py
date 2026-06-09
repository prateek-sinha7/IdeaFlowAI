"""GateEvent SQLAlchemy model — per-gate-firing audit row (Phase 8 / §18).

Table ``gate_events`` — one row per ``GateHandler`` firing recording the gate's
declared outcome (``pass`` | ``block`` | ``wait_human``) at a step boundary
(GATE-01..03 / D-10). Every gate (human/validation/approval/security) writes one
row on each evaluation; the validation gate's residual ``validation_warning`` and
the security gate's ``block`` are auditable here.

Mirrors the §18 additive-table precedent (``run_capabilities.py``): UUID PK +
``run_id`` FK + ``owner_id`` + ``workspace_id`` (both ``nullable=False``,
AUTHZ-01) + payload cols. Writes go through the Phase-5 ``ScopedStore``
(default-deny) so a cross-owner read returns nothing (T-08-02-ID mitigation).

Schema source: specs/003-workflow-engine-decoupling/plan.md §18.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, String
from sqlalchemy.types import JSON

from app.models.database import Base


class GateEvent(Base):
    """One row per gate firing — the outcome a gate evaluated to at a step."""

    __tablename__ = "gate_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String, ForeignKey("workflow_runs.id"), nullable=False)
    owner_id = Column(String, nullable=False)        # AUTHZ-01
    workspace_id = Column(String, nullable=False)    # AUTHZ-01
    step = Column(String, nullable=False)            # the step/agent id gated
    gate = Column(String, nullable=False)            # gate name: human|validation|approval|security
    outcome = Column(String, nullable=False)         # pass|block|wait_human
    detail = Column(JSON, nullable=True)             # gate-specific detail payload
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    __table_args__ = (
        Index("ix_gate_events_run", "run_id"),
    )
