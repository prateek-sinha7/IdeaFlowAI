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
from sqlalchemy import or_
from sqlalchemy.orm import Session

from agents.capabilities.model_pricing import estimate_cost_usd
from app.core.config import settings
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


class AgentRollup(BaseModel):
    """Per-agent token breakdown — derived from ``agent_outputs`` JSON array.

    Numbers only (T-38-Leak): carries counts, tokens, and cost.  The ``agent_name``
    field is the display name already stored in the ``name`` key of each
    ``agent_outputs`` element — it is safe to surface (already echoed by
    ``_SUMMARY_SAFE_AGENT_KEYS`` in ``runs.py``). No output/prompt/thinking text.
    """

    agent_id: str
    agent_name: str
    count: int = 0            # number of agent occurrences across runs in the window
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0


class AnalyticsSummary(BaseModel):
    kpis: Kpis
    daily: list[DailyBucket] = Field(default_factory=list)
    pipelines: list[PipelineRollup] = Field(default_factory=list)
    models: list[ModelRollup] = Field(default_factory=list)
    #: RFN-002 — per-agent token breakdown derived from ``agent_outputs``.
    #: Default empty list so existing callers and tests that don't read this
    #: field continue to work without changes (purely additive).
    agents: list[AgentRollup] = Field(default_factory=list)
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
    # RFN-002 — per-agent accumulators (keyed on agent_id).
    agents_acc: dict[str, dict] = defaultdict(
        lambda: {"count": 0, "total_tokens": 0, "input_tokens": 0, "output_tokens": 0, "cost": 0.0}
    )
    # Human-readable name for each agent_id — keep the last non-empty value seen
    # (a build loop may repeat the same agent_id; name is stable across repeats).
    agent_names: dict[str, str] = {}
    # RFN-002 — per-agent model attribution accumulator (separate from the
    # run-level ``models`` dict).  Merged into ``models`` after the loop; tokens
    # attributed here override the run-level bucket for the same volume so that
    # a run where different agents use different models is split correctly.
    models_agent: dict[str, dict] = defaultdict(
        lambda: {"run_ids": set(), "total_tokens": 0, "cost": 0.0}
    )

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

        # ── RFN-002 — per-agent rollup from ``agent_outputs`` ────────────────
        # Parse the same JSON array that ``run_commands._apply_terminal_output_columns``
        # writes.  A missing/malformed blob degrades to an empty list — same
        # try/except→{} idiom used above for ``token_usage`` (T-38-02).
        agent_list: list[dict] = []
        if r.agent_outputs:
            try:
                parsed_agents = json.loads(r.agent_outputs)
                if isinstance(parsed_agents, list):
                    agent_list = parsed_agents
            except Exception:
                pass  # malformed blob → contribute no per-agent rows

        for ag in agent_list:
            if not isinstance(ag, dict):
                continue
            aid = ag.get("agent_id") or ""
            if not aid:
                continue

            # Keep the latest non-empty display name (stable across build-loop repeats).
            aname = ag.get("name") or ""
            if aname:
                agent_names[aid] = aname

            a_in    = int(_num(ag.get("input_tokens")))
            a_out   = int(_num(ag.get("output_tokens")))
            a_total = int(_num(ag.get("total_tokens"))) or (a_in + a_out)
            a_cr    = int(_num(ag.get("cache_read_tokens")))
            a_cw    = int(_num(ag.get("cache_write_tokens")))
            # Resolve cost against the agent's own model if present; fall back to
            # the run-level model (key) so legacy runs without per-agent model_id
            # still get a cost estimate.
            a_model = ag.get("model_id") or r.model_id or ""
            a_cost  = estimate_cost_usd(
                a_model or None,
                input_tokens=max(0, a_in - a_cr - a_cw),
                output_tokens=a_out,
                cache_read_tokens=a_cr,
                cache_write_tokens=a_cw,
                cache_ttl=settings.BEDROCK_PROMPT_CACHE_TTL,
            )

            av = agents_acc[aid]
            av["count"]        += 1
            av["total_tokens"] += a_total
            av["input_tokens"] += a_in
            av["output_tokens"] += a_out
            av["cost"]         += a_cost

            # ── Two-pass model attribution (fixes "unknown") ─────────────────
            # When the agent carries its own ``model_id``, attribute its tokens
            # to that specific model bucket (``models_agent``) rather than to
            # the run-level bucket.  This is the correct split when different
            # agents within the same run use different models.  Runs where all
            # agents share one model look identical to before.
            agent_model_key = ag.get("model_id")
            if agent_model_key:
                mm = models_agent[agent_model_key]
                mm["run_ids"].add(r.id)       # distinct runs that used this model
                mm["total_tokens"] += a_total
                mm["cost"]         += a_cost

    success_rate = (completed / total) if total else 0.0

    # ── RFN-002 — merge agent-level model attribution into the run-level dict ──
    # For each model that appeared at the per-agent level:
    #   - token/cost: replace with the per-agent totals (more accurate split).
    #   - count (run count): if the model already has a run-level count (meaning
    #     the run row itself carried that model_id), keep it — it is already
    #     correct.  If count is 0 (the model only appeared at the agent level,
    #     e.g. because the run row was NULL → "unknown"), set it to the number
    #     of distinct runs that had at least one agent use this model.  This is
    #     what fixes the "0 runs" display on Haiku / Sonnet when the run-level
    #     model_id was NULL.
    # The ``unknown`` bucket shrinks to only runs whose agent_outputs were empty
    # or whose agents all had NULL model_id.
    for agent_model_key, av in models_agent.items():
        distinct_run_count = len(av["run_ids"])
        if agent_model_key not in models:
            # Model appeared only at agent level — initialise the bucket.
            models[agent_model_key]["count"] = distinct_run_count
        elif models[agent_model_key]["count"] == 0:
            # Run-level bucket existed but count was 0 (should not normally happen,
            # but guard it defensively).
            models[agent_model_key]["count"] = distinct_run_count
        # If the run-level count is already > 0, leave it — it means the run row
        # itself carried this model_id and the count is correct.
        models[agent_model_key]["total_tokens"] = av["total_tokens"]
        models[agent_model_key]["cost"] = av["cost"]
        # Shrink the ``unknown`` bucket by the tokens now attributed to real models.
        if _UNKNOWN_MODEL in models:
            models[_UNKNOWN_MODEL]["total_tokens"] = max(
                0, models[_UNKNOWN_MODEL]["total_tokens"] - av["total_tokens"]
            )
            models[_UNKNOWN_MODEL]["cost"] = max(
                0.0, models[_UNKNOWN_MODEL]["cost"] - av["cost"]
            )

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
        if (v["total_tokens"] > 0 or v["count"] > 0) and k != _UNKNOWN_MODEL
    ]
    # RFN-002 — per-agent rollup, sorted by total_tokens descending so the most
    # expensive agents appear first in the UI.
    agent_rollups = [
        AgentRollup(
            agent_id=aid,
            agent_name=agent_names.get(aid, aid),
            count=v["count"],
            total_tokens=v["total_tokens"],
            input_tokens=v["input_tokens"],
            output_tokens=v["output_tokens"],
            cost=v["cost"],
        )
        for aid, v in sorted(agents_acc.items(), key=lambda kv: -kv[1]["total_tokens"])
    ]
    type_avg_duration_sec = {
        t: (v["dur_sum"] / v["dur_n"]) if v["dur_n"] else 0.0 for t, v in pipe.items()
    }

    return AnalyticsSummary(
        kpis=Kpis(total=total, completed=completed, failed=failed, success_rate=success_rate),
        daily=[DailyBucket(date=d, **daily[d]) for d in sorted(daily)],
        pipelines=pipelines,
        models=model_rollups,
        agents=agent_rollups,
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
        #
        # RFN-002 fix: the model rollup is built from two sources —
        #   1. WorkflowRun.model_id (the run-row column, set only at completion)
        #   2. agent_outputs JSON (per-agent model_id via the two-pass merge)
        # Most historical runs have model_id = NULL on the run row even when
        # their agent_outputs carry a real model_id. Filtering on the run-row
        # column alone would return 0 rows for any agent-sourced model id.
        # Fix: include runs where agent_outputs JSON contains the requested
        # model_id string (a substring match on the serialised JSON blob is
        # safe here because model_id values are unique enough strings that
        # false positives are not a concern, and this avoids a JSON subquery
        # that SQLite/Postgres handle differently).
        if model == _UNKNOWN_MODEL:
            # "unknown" means the run row had no model_id AND no agent carried
            # a real model_id in their outputs.  Match NULL run-row column only;
            # the _aggregate two-pass will exclude tokens attributed to real
            # models from this bucket.
            query = query.filter(WorkflowRun.model_id.is_(None))
        else:
            query = query.filter(
                or_(
                    WorkflowRun.model_id == model,
                    # Runs where the run-row model_id is NULL but agent_outputs
                    # carries this model_id string.
                    (
                        WorkflowRun.model_id.is_(None)
                        & WorkflowRun.agent_outputs.contains(model)
                    ),
                )
            )

    runs = query.all()
    return _aggregate(runs)
