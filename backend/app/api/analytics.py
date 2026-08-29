"""Owner-scoped analytics aggregation — GET /api/analytics/summary (SC-1).

Additive, READ-ONLY aggregation over the caller's OWN ``WorkflowRun`` rows so
the browser stops downloading up to 500 raw run rows to reduce in JS (today's
``AnalyticsPage`` client-side rollup). Reads ONLY existing columns — NO new
table, NO migration, NO schema change — so the 5 characterization goldens stay
byte-identical by construction (INV-3).

Design invariants:
  * Owner scope (T-38-01): the base query is keyed on
    ``WorkflowRun.user_id == current_user.id`` — the principal set at every
    creation site — NEVER the nullable Phase-5 owner column backfill. A
    cross-owner row never enters the aggregate.
  * Enum allow-list (T-38-03): ``range`` is an allow-listed enum
    {today,3d,7d,30d,90d,all}; an unknown value falls back to the default (30d)
    window via ``.get(range, default)`` — never an unbounded scan, never a crash.
  * DoS guard (T-38-02): each run's ``token_usage`` blob is parsed inside a
    try/except → ``{}`` (the runs.py:1116-1123 idiom), so a malformed blob
    degrades to an empty per-run token aggregate — a 200, never a 500.
  * SC-001 / INV-1: rollups key on the GENERIC ``type`` / ``status`` /
    ``model_id`` columns — never a workflow-name branch; display-name maps stay
    on the frontend only.
  * Numbers only (T-38-Leak): the response echoes counts / tokens / cost /
    durations — never the agent bodies, prompts, or outputs.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.models.database import get_db
from app.models.user import User
from app.models.workflow import WorkflowRun

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

# Allow-listed range → cutoff offset. The default (unknown value) is 30d.
_DEFAULT_RANGE = "30d"

#: Bucket key for a run with no ``model_id``. Handed to the caller in the ``models``
#: rollup, so the ``model`` filter has to accept it back (ISS-288).
_UNKNOWN_MODEL = "unknown"


def _cutoff_for(range: str) -> datetime | None:
    """Map the allow-listed enum → an aware-UTC cutoff (``None`` == unbounded).

    Unknown values fall back to the default (30d) window — no exception, no
    unbounded scan (T-38-03).
    """
    now = datetime.now(timezone.utc)
    table: dict[str, datetime | None] = {
        "today": now.replace(hour=0, minute=0, second=0, microsecond=0),
        "3d": now - timedelta(days=2),
        "7d": now - timedelta(days=6),
        "30d": now - timedelta(days=29),
        "90d": now - timedelta(days=89),
        "all": None,
    }
    return table.get(range, table[_DEFAULT_RANGE])


def _parse_token_usage(raw: str | None) -> dict:
    """Tolerant parse of the persisted ``token_usage`` blob (T-38-02).

    A missing / non-JSON / non-dict blob degrades to ``{}`` so the run
    contributes an empty token aggregate — never a 500.
    """
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _num(value: object) -> float:
    """Coerce a stored numeric field to float, tolerating garbage → 0.0."""
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


# ────────────────────────────────────────────────────────────────────────────
# Response schema — the FE ``AnalyticsSummary`` TS type (38-04) mirrors this
# field-for-field. NUMBERS ONLY.
# ────────────────────────────────────────────────────────────────────────────


class Kpis(BaseModel):
    total: int = 0
    completed: int = 0
    failed: int = 0
    success_rate: float = 0.0


class TokenTotals(BaseModel):
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    total: int = 0


class DailyBucket(BaseModel):
    date: str
    total: int = 0
    completed: int = 0
    failed: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class PipelineRollup(BaseModel):
    type: str
    count: int = 0
    total_tokens: int = 0
    cost: float = 0.0
    avg_duration: float = 0.0


class ModelRollup(BaseModel):
    model_id: str
    count: int = 0
    total_tokens: int = 0
    cost: float = 0.0


class AnalyticsSummary(BaseModel):
    kpis: Kpis
    daily: list[DailyBucket] = Field(default_factory=list)
    pipelines: list[PipelineRollup] = Field(default_factory=list)
    models: list[ModelRollup] = Field(default_factory=list)
    spend: float = 0.0
    #: ISS-034 — the same window priced as-if prompt caching had been OFF. The SIGNED
    #: difference ``spend_full - spend`` is what caching actually did: POSITIVE means it
    #: saved money, NEGATIVE means it cost more (a run that writes cache entries it never
    #: re-reads pays the 1.25x cache_write premium for nothing).
    spend_full: float = 0.0
    #: How many runs in the window actually carry the counterfactual. Runs persisted
    #: before ISS-034 landed do not, and contribute a ZERO delta rather than a fabricated
    #: baseline — so the FE must state the coverage instead of implying the whole window.
    metered_runs: int = 0
    token_totals: TokenTotals
    type_avg_duration_sec: dict[str, float] = Field(default_factory=dict)


def _aggregate(runs: list[WorkflowRun]) -> AnalyticsSummary:
    """Pure roll-up over owner-scoped rows — keys on generic type/status/model_id.

    No workflow-name branch anywhere (SC-001 / INV-1): a run is bucketed by its
    stored ``type`` / ``status`` / ``model_id`` values verbatim.
    """
    total = len(runs)
    completed = sum(1 for r in runs if r.status == "completed")
    failed = sum(1 for r in runs if r.status == "failed")

    spend = 0.0
    spend_full = 0.0
    metered_runs = 0
    tok_in = tok_out = tok_cache_read = tok_cache_write = tok_total = 0

    daily: dict[str, dict] = defaultdict(
        lambda: {
            "total": 0,
            "completed": 0,
            "failed": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }
    )
    pipe: dict[str, dict] = defaultdict(
        lambda: {"count": 0, "total_tokens": 0, "cost": 0.0, "dur_sum": 0.0, "dur_n": 0}
    )
    models: dict[str, dict] = defaultdict(lambda: {"count": 0, "total_tokens": 0, "cost": 0.0})

    for r in runs:
        usage = _parse_token_usage(r.token_usage)
        r_in = int(_num(usage.get("total_input_tokens")))
        r_out = int(_num(usage.get("total_output_tokens")))
        r_total = int(_num(usage.get("total_tokens"))) or (r_in + r_out)
        r_cache_read = int(_num(usage.get("total_cache_read_tokens")))
        r_cache_write = int(_num(usage.get("total_cache_write_tokens")))
        r_cost = _num(usage.get("estimated_cost_usd"))
        # ISS-034 — an UNMEASURED run contributes NOTHING to the delta, never a
        # fabricated $0 baseline. ``_num`` coerces an absent key to 0.0, so summing
        # it raw would price every pre-ISS-034 row as if an uncached run were free
        # and render "caching cost you <the entire window> more (-100%)". Falling
        # back to r_cost makes a legacy row's delta exactly zero.
        r_cost_full = _num(usage.get("estimated_cost_full_usd")) or r_cost
        if "estimated_cost_full_usd" in usage:
            metered_runs += 1

        spend += r_cost
        spend_full += r_cost_full
        tok_in += r_in
        tok_out += r_out
        tok_cache_read += r_cache_read
        tok_cache_write += r_cache_write
        tok_total += r_total

        # Daily bucket keyed on date(created_at) (accumulated as a dict to keep
        # numeric fields off attribute access — numbers-only V7 grep posture).
        created = r.created_at or datetime.now(timezone.utc)
        day = created.date().isoformat()
        bucket = daily[day]
        bucket["total"] += 1
        if r.status == "completed":
            bucket["completed"] += 1
        elif r.status == "failed":
            bucket["failed"] += 1
        bucket["input_tokens"] += r_in
        bucket["output_tokens"] += r_out
        bucket["total_tokens"] += r_total

        # Per-type rollup (generic ``type``).
        p = pipe[r.type]
        p["count"] += 1
        p["total_tokens"] += r_total
        p["cost"] += r_cost
        if r.status == "completed":
            p["dur_sum"] += _num(r.duration)
            p["dur_n"] += 1

        # Per-model rollup (generic ``model_id``).
        key = r.model_id or _UNKNOWN_MODEL
        m = models[key]
        m["count"] += 1
        m["total_tokens"] += r_total
        m["cost"] += r_cost

    success_rate = (completed / total) if total else 0.0

    pipelines = [
        PipelineRollup(
            type=t,
            count=v["count"],
            total_tokens=v["total_tokens"],
            cost=v["cost"],
            avg_duration=(v["dur_sum"] / v["dur_n"]) if v["dur_n"] else 0.0,
        )
        for t, v in sorted(pipe.items())
    ]
    model_rollups = [
        ModelRollup(model_id=k, count=v["count"], total_tokens=v["total_tokens"], cost=v["cost"])
        for k, v in sorted(models.items())
    ]
    type_avg_duration_sec = {
        t: (v["dur_sum"] / v["dur_n"]) if v["dur_n"] else 0.0 for t, v in pipe.items()
    }

    return AnalyticsSummary(
        kpis=Kpis(total=total, completed=completed, failed=failed, success_rate=success_rate),
        daily=[DailyBucket(date=d, **daily[d]) for d in sorted(daily)],
        pipelines=pipelines,
        models=model_rollups,
        spend=spend,
        spend_full=spend_full,
        metered_runs=metered_runs,
        token_totals=TokenTotals(
            input=tok_in,
            output=tok_out,
            cache_read=tok_cache_read,
            cache_write=tok_cache_write,
            total=tok_total,
        ),
        type_avg_duration_sec=type_avg_duration_sec,
    )


@router.get("/summary", response_model=AnalyticsSummary)
def get_analytics_summary(
    range: str = _DEFAULT_RANGE,
    pipeline: str | None = None,
    model: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalyticsSummary:
    """Aggregate the caller's OWN runs into a date/pipeline/model-scoped summary.

    Owner-scoped on ``WorkflowRun.user_id`` (T-38-01); ``range`` allow-listed
    (T-38-03); ``token_usage`` tolerant-parsed (T-38-02); rollups on generic
    ``type`` / ``status`` / ``model_id`` (SC-001). Returns numbers only.

    ISS-229/288/289 — ``pipeline`` and ``model`` narrow the run set BEFORE the
    rollup, exactly like ``range`` does, so every figure the caller derives from
    one payload (KPIs, daily buckets, success rate, BOTH breakdowns) describes
    the same population. Filtering either axis in the browser instead can only
    reach the two rollup arrays: ``daily`` has no per-type breakdown and neither
    rollup carries a completed/failed split, so the rest of the page would keep
    reporting the unfiltered window.
    """
    query = db.query(WorkflowRun).filter(WorkflowRun.user_id == current_user.id)

    cutoff = _cutoff_for(range)
    if cutoff is not None:
        query = query.filter(WorkflowRun.created_at >= cutoff)

    if pipeline:
        # Generic column equality, never a workflow-name branch (SC-001): the
        # value is whatever ``type`` the caller was handed back. The revision
        # variant rides along with its base type, mirroring the frontend's
        # ``normalizeType`` so the breakdown keeps listing both rows.
        query = query.filter(WorkflowRun.type.in_((pipeline, f"{pipeline}_revision")))

    if model:
        # ``_aggregate`` buckets a null ``model_id`` under the "unknown" sentinel
        # and offers it as a filter value, so the filter honours it back.
        query = query.filter(
            WorkflowRun.model_id.is_(None)
            if model == _UNKNOWN_MODEL
            else WorkflowRun.model_id == model
        )

    runs = query.all()
    return _aggregate(runs)
