"""app/api/admin_capacity.py — GET /api/admin/capacity (specs/014).

Admin-only, read-only surface over the host capacity matrix. Reuses the
existing ``require_admin`` dependency (``app/api/admin.py``) rather than
inventing a second admin guard, and reads exclusively from the process-local
``capacity_state`` holder — this endpoint never calls AWS itself (specs/014
§4: "the request path never touches AWS"). The background poller
(``main.py``'s lifespan) is the only writer to that holder.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.admin import require_admin
from app.core.config import settings
from app.models.user import User
from app.services.capacity_state import (
    AdmissionState,
    CapacitySnapshot,
    InstanceCapacity,
    current_decision,
    current_snapshot,
)

router = APIRouter(prefix="/api/admin", tags=["admin-capacity"])


class InstanceCapacityResponse(BaseModel):
    instance_id: str
    instance_type: str | None
    is_self: bool
    cpu_used_percent: float | None
    mem_used_percent: float | None
    cpu_user_percent: float | None
    cpu_system_percent: float | None
    cpu_iowait_percent: float | None
    reading_age_seconds: float | None
    stale: bool


class SignalResponse(BaseModel):
    name: str
    value: float
    threshold: float


class CapacityGateResponse(BaseModel):
    enabled: bool
    state: str  # "allowing" | "blocking" | "blind"
    blind_reason: str | None
    cpu_threshold_percent: float
    mem_threshold_percent: float
    signals: list[SignalResponse]
    engaged_at: datetime | None
    evaluated_at: datetime


class CapacityMatrixResponse(BaseModel):
    collected_at: datetime
    self_instance_id: str | None
    instance_source: str  # "override" | "discovery" | "none"
    instances: list[InstanceCapacityResponse]
    gate: CapacityGateResponse


def _to_instance_response(
    inst: InstanceCapacity, snapshot: CapacitySnapshot, now: datetime
) -> InstanceCapacityResponse:
    return InstanceCapacityResponse(
        instance_id=inst.instance_id,
        instance_type=inst.instance_type,
        is_self=(inst.instance_id == snapshot.self_instance_id),
        cpu_used_percent=inst.cpu_used_percent,
        mem_used_percent=inst.mem_used_percent,
        cpu_user_percent=inst.cpu_user_percent,
        cpu_system_percent=inst.cpu_system_percent,
        cpu_iowait_percent=inst.cpu_iowait_percent,
        reading_age_seconds=inst.age_seconds(now),
        stale=inst.is_stale(now, settings.HOST_CAPACITY_MAX_STALENESS_SECONDS),
    )


def _to_gate_response(decision: AdmissionState) -> CapacityGateResponse:
    return CapacityGateResponse(
        enabled=settings.HOST_CAPACITY_GATE_ENABLED,
        state=decision.state_label,
        blind_reason=decision.blind_reason,
        cpu_threshold_percent=settings.HOST_CAPACITY_CPU_THRESHOLD_PERCENT,
        mem_threshold_percent=settings.HOST_CAPACITY_MEM_THRESHOLD_PERCENT,
        signals=[
            SignalResponse(name=s.name, value=s.value, threshold=s.threshold)
            for s in decision.signals
        ],
        engaged_at=decision.engaged_at,
        evaluated_at=decision.evaluated_at,
    )


@router.get("/capacity", response_model=CapacityMatrixResponse)
def get_capacity_matrix(
    admin: User = Depends(require_admin),
) -> CapacityMatrixResponse:
    """The per-instance CPU/memory matrix plus the current gate state.

    Read-only over the last snapshot the background poller collected — never
    calls AWS on the request path. Before the first successful poll this
    returns an empty instance list and a blind gate, which is the honest
    answer ("no data yet"), not an error.
    """
    snapshot = current_snapshot()
    decision = current_decision()
    now = datetime.now(timezone.utc)

    return CapacityMatrixResponse(
        collected_at=snapshot.collected_at,
        self_instance_id=snapshot.self_instance_id,
        instance_source=snapshot.instance_source,
        instances=[
            _to_instance_response(inst, snapshot, now) for inst in snapshot.instances
        ],
        gate=_to_gate_response(decision),
    )
