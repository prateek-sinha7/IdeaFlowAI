"""app/api/admin_capacity_history.py — GET /api/admin/capacity/history (ADR-0056).

Time series behind the admin Machines tab's history charts. Unlike
``GET /api/admin/capacity`` (``admin_capacity.py``), which only reads the poller's
snapshot, this endpoint reads CloudWatch on demand — the one documented exception
to specs/014's "the request path never touches AWS". It stays safe because:

* it is admin-only (the shared ``require_admin`` guard);
* ``instance_id`` must already be in the poller's current snapshot, so a caller
  can never point a CloudWatch query at an arbitrary id;
* ``range`` is an allow-list and ``period`` is validated against it;
* it never touches the admission decision — ``capacity_state`` is only read for
  the instance allow-list;
* it is a sync ``def``: FastAPI runs it in the threadpool, so the blocking boto3
  call never sits on the event loop. Results are cached for ~60s and AWS failures
  come back as per-series errors (200 with empty charts), never a 5xx.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.api.admin import require_admin
from app.core.config import settings
from app.models.user import User
from app.services.capacity_state import current_snapshot
from app.services.host_metrics_history import (
    ChartGroup,
    HistoryRange,
    HistoryWindowError,
    InstanceHistory,
    MetricUnit,
    allowed_periods,
    get_instance_history,
    resolve_window,
)

router = APIRouter(prefix="/api/admin", tags=["admin-capacity"])

# EC2 instance ids are "i-" + 8 or 17 hex characters; 64 leaves room for any
# override value while bounding what reaches the allow-list comparison.
_INSTANCE_ID_MAX_LENGTH = 64


class SeriesSummaryResponse(BaseModel):
    latest: float | None
    min: float | None
    avg: float | None
    max: float | None


class HistorySeriesResponse(BaseModel):
    key: str
    label: str
    group: ChartGroup
    unit: MetricUnit
    # One entry per period bucket from ``start``; ``None`` = no datapoint.
    values: list[float | None]
    summary: SeriesSummaryResponse
    error: str | None


class CapacityHistoryResponse(BaseModel):
    instance_id: str
    range: HistoryRange
    period_seconds: int
    allowed_periods: list[int]
    start: datetime
    end: datetime
    fetched_at: datetime
    cached: bool
    cpu_threshold_percent: float
    mem_threshold_percent: float
    series: list[HistorySeriesResponse]


def _to_response(history: InstanceHistory, cached: bool) -> CapacityHistoryResponse:
    window = history.window
    return CapacityHistoryResponse(
        instance_id=history.instance_id,
        range=window.range_key,
        period_seconds=window.period_seconds,
        allowed_periods=list(allowed_periods(window.range_key)),
        start=window.start,
        end=window.end,
        fetched_at=history.fetched_at,
        cached=cached,
        cpu_threshold_percent=settings.HOST_CAPACITY_CPU_THRESHOLD_PERCENT,
        mem_threshold_percent=settings.HOST_CAPACITY_MEM_THRESHOLD_PERCENT,
        series=[
            HistorySeriesResponse(
                key=s.metric.key,
                label=s.metric.label,
                group=s.metric.group,
                unit=s.metric.unit,
                values=list(s.values),
                summary=SeriesSummaryResponse(
                    latest=s.summary.latest,
                    min=s.summary.min,
                    avg=s.summary.avg,
                    max=s.summary.max,
                ),
                error=s.error,
            )
            for s in history.series
        ],
    )


@router.get("/capacity/history", response_model=CapacityHistoryResponse)
def get_capacity_history(
    instance_id: str = Query(
        ...,
        min_length=1,
        max_length=_INSTANCE_ID_MAX_LENGTH,
        description="An instance id from GET /api/admin/capacity.",
    ),
    range_key: HistoryRange = Query("3h", alias="range"),
    period: int | None = Query(
        None,
        description=(
            "Bucket size in seconds. Omit for the range default; the response's "
            "allowed_periods lists the valid choices for the range."
        ),
    ),
    admin: User = Depends(require_admin),
) -> CapacityHistoryResponse:
    """CPU, memory, disk, disk I/O, network, swap and status-check history.

    ``404`` when ``instance_id`` is not in the poller's current inventory (including
    before the first poll); ``422`` for an unknown range or a period the range does
    not offer. CloudWatch failures are reported per series, not as an HTTP error.
    """
    try:
        window = resolve_window(range_key, period, datetime.now(timezone.utc))
    except HistoryWindowError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        )

    known_ids = {inst.instance_id for inst in current_snapshot().instances}
    if instance_id not in known_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Unknown instance."
        )

    history, cached = get_instance_history(instance_id, window)
    return _to_response(history, cached)
