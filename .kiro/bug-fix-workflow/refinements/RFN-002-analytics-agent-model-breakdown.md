# RFN-002 — Agent-Based Token Breakdown & Accurate Multi-Model Display in Analytics

**Type:** Feature / Data-flow wiring  
**Status:** OPEN  
**Priority:** High  
**Requested:** 2026-09-07  

---

## User Story

> "In the Analytics page the 'By Model' section only shows 'unknown' even though
> different agents can use different models. We need to see the real model names
> and their actual token usage. We also need a new 'By Agent' breakdown so we
> can see exactly how many tokens each agent consumed — which agents are the most
> expensive in a pipeline."

---

## Current Behaviour (Problems)

### Problem 1 — "By Model" shows only `unknown`

The analytics endpoint (`GET /api/analytics/summary`) rolls up token usage per
`WorkflowRun.model_id`. That column is nullable. The backend maps `NULL →
"unknown"` (the `_UNKNOWN_MODEL` sentinel in `analytics.py`). The frontend
`MODEL_META` table has no entry for the string `"unknown"`, so it falls through
to the raw-id fallback and renders verbatim.

Root causes (two layers):

1. **NULL in the column.** `model_id` starts NULL at run creation. It is only
   written by `_apply_terminal_output_columns` at completion time. Runs that
   were created when no `preferred_model` was set, or runs created before
   migration `0008`, stay NULL forever. Runs interrupted before completion also
   stay NULL.
2. **Run-level model only.** Even when `model_id` is populated on the run row,
   it reflects the *pipeline-level* default model. A pipeline where Agent A runs
   on Haiku and Agent B runs on Opus still counts entirely under the single run
   `model_id` — it never surfaces the per-agent model split.

### Problem 2 — No "By Agent" breakdown

The analytics page has a "By Pipeline Type" section and a "By Model" section,
but no "By Agent" section. There is no way to see which agents consume the most
tokens (e.g. that a "research" agent accounts for 60 % of pipeline spend).

The data already exists: `WorkflowRun.agent_outputs` is a JSON array where every
element already carries `input_tokens`, `output_tokens`, `cache_read_tokens`,
`cache_write_tokens`, `total_tokens`, `model_id`, and a human-readable `name`
for each agent that completed (persisted by `_apply_terminal_output_columns`,
ISS-165). The analytics endpoint simply never parses this column.

---

## Desired Behaviour

### A — "By Model" shows real model names with correct token attribution

Every model that was actually used — even on a per-agent basis — appears in the
"By Model" breakdown with its short label (e.g. "Haiku 4.5"), run count, token
total, and estimated cost. The `unknown` row disappears or is demoted to a
catch-all only when a model truly cannot be resolved.

Runs where the *run-level* `model_id` is NULL but `agent_outputs` carries valid
per-agent `model_id` fields should be attributed to those agent-level models.
Runs where both are NULL continue to fall under `unknown` (legacy rows, runs
cancelled before any agent completed).

### B — New "By Agent" section in the Analytics page

A new breakdown card titled "By Agent" sits below "By Pipeline Type" and "By
Model". It lists every `agent_id` (or `name`, whichever is more human-readable)
that has token data in the current date/pipeline/model filter window, sorted by
total tokens descending, with:

- Agent display name (e.g. "Research", "Writer", "Reviewer")
- Run count (number of runs the agent appeared in)
- Total tokens
- Estimated cost (derived from the agent's own `model_id` + per-agent token
  counts)
- A proportional token bar (same visual language as "By Pipeline Type")

### C — Model dropdown includes all models that actually appear in data

The model filter dropdown at the top of the page currently only lists model IDs
returned by the `models` rollup array. After this change the rollup is per-agent
model (not just per-run model), so more IDs will appear. The `MODEL_META` lookup
must cover all of them, and the dropdown should show readable short names, not
raw IDs.

---

## Root Cause / Gap Analysis

All required data already exists in the database. The only gaps are in how the
analytics backend aggregates it and how the frontend renders the new section.

---

## Backend Changes (analytics.py)

### Gap B-1 — `AgentRollup` Pydantic model missing

Add a new response model:

```python
class AgentRollup(BaseModel):
    agent_id: str
    agent_name: str
    count: int = 0            # number of distinct runs this agent appeared in
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
```

### Gap B-2 — `AnalyticsSummary` missing `agents` field

```python
class AnalyticsSummary(BaseModel):
    kpis: Kpis
    daily: list[DailyBucket]
    pipelines: list[PipelineRollup]
    models: list[ModelRollup]
    agents: list[AgentRollup] = Field(default_factory=list)  # ← ADD
    spend: float = 0.0
    spend_full: float = 0.0
    metered_runs: int = 0
    token_totals: TokenTotals
    type_avg_duration_sec: dict[str, float]
```

> The field carries a default so existing callers (tests, clients) that don't
> read `agents` continue to work without changes — purely additive.

### Gap B-3 — `_aggregate` doesn't parse `agent_outputs`

In `_aggregate`, after the per-model rollup inside the `for r in runs:` loop,
add a second pass that parses `agent_outputs`:

```python
# ── Per-agent rollup ─────────────────────────────────────────────────
agent_list: list[dict] = []
if r.agent_outputs:
    try:
        parsed = json.loads(r.agent_outputs)
        if isinstance(parsed, list):
            agent_list = parsed
    except Exception:
        pass  # malformed blob → skip (T-38-02 idiom)

for ag in agent_list:
    if not isinstance(ag, dict):
        continue
    aid = ag.get("agent_id") or ""
    if not aid:
        continue
    aname = ag.get("name") or aid
    a_in    = int(_num(ag.get("input_tokens")))
    a_out   = int(_num(ag.get("output_tokens")))
    a_total = int(_num(ag.get("total_tokens"))) or (a_in + a_out)
    a_cr    = int(_num(ag.get("cache_read_tokens")))
    a_cw    = int(_num(ag.get("cache_write_tokens")))
    a_model = ag.get("model_id") or key   # fall back to run-level model

    # Per-agent name map — store the latest name seen for this agent_id
    # (in a build loop the same agent_id may repeat; keep the last, as
    # WorkflowHistory.tsx already does for dedup).
    agent_names[aid] = aname

    av = agents_acc[aid]
    av["count"] += 1       # once per run per agent occurrence
    av["total_tokens"] += a_total
    av["input_tokens"]  += a_in
    av["output_tokens"] += a_out
    av["cost"] += estimate_cost_usd(
        a_model,
        input_tokens=max(0, a_in - a_cr - a_cw),
        output_tokens=a_out,
        cache_read_tokens=a_cr,
        cache_write_tokens=a_cw,
        cache_ttl=settings.BEDROCK_PROMPT_CACHE_TTL,
    )

    # ── Per-agent model attribution (fixes "unknown") ──────────────────────
    # When the agent carries its own model_id, attribute those tokens to
    # that model rather than the run-level model bucket. This is the correct
    # attribution when different agents within the same run use different models.
    if ag.get("model_id"):
        agent_model_key = ag["model_id"]
        mm = models_agent[agent_model_key]   # separate accum — merged after loop
        mm["count_agent"] += 1
        mm["total_tokens"] += a_total
        mm["cost"] += estimate_cost_usd(
            agent_model_key,
            input_tokens=max(0, a_in - a_cr - a_cw),
            output_tokens=a_out,
            cache_read_tokens=a_cr,
            cache_write_tokens=a_cw,
            cache_ttl=settings.BEDROCK_PROMPT_CACHE_TTL,
        )
```

> **Two-pass model attribution strategy:**
>
> The existing `models` dict is keyed on `r.model_id or _UNKNOWN_MODEL`
> (run-level). The new `models_agent` dict is keyed on per-agent `model_id`.
> At the end of `_aggregate`, the two are merged: agent-level attribution wins
> (overrides the run-level attribution for the same token volume) when
> `models_agent` is non-empty. This means runs where all agents used the same
> model look identical to before, while runs with mixed models now appear under
> their true model IDs. The `unknown` bucket shrinks to only genuinely
> unresolvable runs (both run-level and all agent-level `model_id` are NULL).

### Gap B-4 — `estimate_cost_usd` must be importable in `analytics.py`

`estimate_cost_usd` currently lives in `backend/app/api/run_commands.py` (used
only there). To call it from `analytics.py` it must be moved to a shared utility
location, or `analytics.py` must import it from `run_commands`. The cleanest
path:

**Option A (preferred):** Move `estimate_cost_usd` to
`backend/agents/capabilities/model_pricing.py` (it already knows the catalog;
the function is catalog-derived). Then `analytics.py` imports from
`agents.capabilities.model_pricing` — an import already made by other API files
(`run_commands.py` already imports from `model_pricing` for the `Pricing`
dataclass).

**Option B (acceptable short-term):** Import `estimate_cost_usd` directly from
`run_commands` in `analytics.py`. No import-linter boundary is violated since
both are under `app.api`. The function is then moved in a follow-up.

> The `settings.BEDROCK_PROMPT_CACHE_TTL` import is also needed; it is already
> imported in `run_commands.py` and can be added to `analytics.py` the same way.

### Gap B-5 — `_aggregate` return block must build `AgentRollup` list

```python
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
```

And the `AnalyticsSummary(...)` instantiation gains `agents=agent_rollups`.

---

## Frontend Changes (AnalyticsPage.tsx + api.ts)

### Gap F-1 — `AnalyticsAgentRollup` TypeScript interface missing

**File:** `frontend/src/lib/api.ts`  
**Location:** Near `AnalyticsModelRollup` (around line 865)

```ts
export interface AnalyticsAgentRollup {
  agent_id: string;
  agent_name: string;
  count: number;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  cost: number;
}
```

### Gap F-2 — `AnalyticsSummary` missing `agents` field

**File:** `frontend/src/lib/api.ts`  
**Location:** `AnalyticsSummary` interface

```ts
export interface AnalyticsSummary {
  kpis: AnalyticsKpis;
  daily: AnalyticsDailyBucket[];
  pipelines: AnalyticsPipelineRollup[];
  models: AnalyticsModelRollup[];
  agents: AnalyticsAgentRollup[];  // ← ADD
  spend: number;
  spend_full: number;
  metered_runs: number;
  token_totals: AnalyticsTokenTotals;
  type_avg_duration_sec: Record<string, number>;
}
```

### Gap F-3 — `AnalyticsPage.tsx` doesn't derive `agentRows`

In the derived display data block (where `pipelineRows` and `modelRows` are
built), add:

```ts
const agentRows = (summary?.agents ?? [])
  .map((a) => ({
    id: a.agent_id,
    name: a.agent_name,
    runs: a.count,
    tokens: a.total_tokens,
    cost: a.cost,
  }));
  // already sorted by total_tokens DESC from the backend

const agentMax = Math.max(...agentRows.map((a) => a.tokens), 1);
const agentHasTokens = agentRows.some((a) => a.tokens > 0);
```

### Gap F-4 — "By Agent" section not rendered

Add a new breakdown card in the JSX, after the existing "By Model" card and
before the closing `</div>`. The card reuses the exact same row structure as
"By Pipeline Type" — proportional token bar, run count, token total, cost — so
no new component is needed.

**Proposed layout (matching existing pipeline card):**

```tsx
{/* ── By Agent ─────────────────────────────────────────────── */}
<div className="bg-surface-card rounded-[14px] border border-line-faint p-5">
  <h3 className="text-[13px] font-semibold text-ink-700 mb-3">By Agent</h3>
  {agentRows.length === 0 ? (
    <p className="text-[12px] text-ink-400">No agent data for this period.</p>
  ) : (
    <div className="space-y-3">
      {agentRows.map((a) => (
        <div key={a.id}>
          <div className="flex items-center justify-between mb-1">
            <span className="text-[11px] font-medium text-ink-700 uppercase tracking-wide">
              {a.name}
            </span>
            <span className="text-[11px] text-ink-400">
              {a.runs} {a.runs === 1 ? "run" : "runs"} · {formatTokens(a.tokens)} · {formatCost(a.cost)}
            </span>
          </div>
          <div className="h-1.5 rounded-full bg-surface-warm overflow-hidden">
            <div
              className="h-full rounded-full bg-brand/70"
              style={{ width: `${agentHasTokens ? Math.round((a.tokens / agentMax) * 100) : 0}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  )}
</div>
```

### Gap F-5 — `MODEL_META` missing the `"unknown"` fallback label

When a run has a truly unresolvable model (both run-level and agent-level
`model_id` are NULL), the backend still emits `model_id: "unknown"`. Add a
graceful display entry so the frontend never renders a raw sentinel:

```ts
const MODEL_META: Record<string, { name: string; short: string; ... }> = {
  // ... existing entries ...
  "unknown": {
    name: "Unknown Model",
    short: "Unknown",
    inputRate: "—",
    outputRate: "—",
    cacheReadRate: "—",
    cacheWriteRate: "—",
    context: "—",
  },
};
```

---

## Fix Sites Summary

| # | File | Change | Blast radius |
|---|------|--------|-------------|
| B-1 | `backend/app/api/analytics.py` | Add `AgentRollup` Pydantic model | New type, no existing model touched |
| B-2 | `backend/app/api/analytics.py` | Add `agents` field to `AnalyticsSummary` with `default_factory=list` | Additive — existing callers unaffected |
| B-3 | `backend/app/api/analytics.py` | `_aggregate`: parse `agent_outputs`, build `agents_acc` + `agent_names` dicts, two-pass model attribution | Core aggregation loop — surgical extension; existing `models` rollup logic stays intact |
| B-4 | `backend/agents/capabilities/model_pricing.py` OR `backend/app/api/run_commands.py` | Move / expose `estimate_cost_usd` for import by `analytics.py` | Single function move; `run_commands.py` import path updated |
| B-5 | `backend/app/api/analytics.py` | Build `agent_rollups` list and pass to `AnalyticsSummary(...)` | Additive field population |
| F-1 | `frontend/src/lib/api.ts` | Add `AnalyticsAgentRollup` interface | Types only — no consumer breaks |
| F-2 | `frontend/src/lib/api.ts` | Add `agents: AnalyticsAgentRollup[]` to `AnalyticsSummary` | Optional field access `summary?.agents ?? []` in FE — safe |
| F-3 | `frontend/src/components/analytics/AnalyticsPage.tsx` | Derive `agentRows` and `agentMax` from `summary.agents` | Additive derived values — no existing state/logic touched |
| F-4 | `frontend/src/components/analytics/AnalyticsPage.tsx` | Render "By Agent" breakdown card JSX | Presentation only — new `<div>` block after existing "By Model" card |
| F-5 | `frontend/src/components/analytics/AnalyticsPage.tsx` | Add `"unknown"` entry to `MODEL_META` map | Fallback label only — no routing or logic |

**No database schema change required. No new migration. No SSE event shape change. No golden files affected (INV-3).**

---

## Constraints & Guardrails

- **SC-001 / INV-1:** No agent name or workflow name used as a control-flow
  branch. Agent rows are keyed on `agent_id` (a data column value), sorted by
  token total — never an `if agentId == "research"` branch.
- **INV-3 goldens:** No backend SSE change. The analytics endpoint is a pure
  GET aggregation over existing columns — goldens are byte-identical by
  construction.
- **Numbers-only posture (T-38-Leak):** `AgentRollup` carries only counts,
  tokens, and cost — never the agent's `output`, `input_prompt`, `thinking_text`,
  or `tool_calls`. The `name` field is the display name only (safe — already
  echoed in run summary via `_SUMMARY_SAFE_AGENT_KEYS`).
- **DoS guard (T-38-02):** `agent_outputs` parse uses the same `try/except → {}`
  pattern already used for `token_usage`. A malformed blob contributes no
  per-agent rows — never a 500.
- **Owner scope (T-38-01):** The existing `WorkflowRun.user_id == current_user.id`
  base query applies before any aggregation; per-agent data is only reachable
  through that scoped set.
- **`model_pricing.py` single-source rule:** `estimate_cost_usd` must be derived
  from `model_catalog.py` pricing entries. Moving it to `model_pricing.py` is the
  correct home — it is already the single-source file for catalog-derived rates.
  Do not duplicate pricing literals.
- **`analytics.py` API layer rule:** `analytics.py` is a pure aggregation
  endpoint. The response shape change is additive — no existing field is renamed
  or removed. The FE `AnalyticsSummary` mirrors it field-for-field.
- **Migration chain (head 0037):** No new table, no new column. `agent_outputs`
  already exists. Verify `alembic heads` still prints exactly one head after any
  unrelated concurrent migration work.

---

## Implementation Order

1. **`model_pricing.py`** — expose `estimate_cost_usd` (or confirm it's already
   importable from there).
2. **`analytics.py`** — add `AgentRollup`, extend `AnalyticsSummary`, extend
   `_aggregate` with agent-outputs parse + two-pass model attribution.
3. **`api.ts`** — add `AnalyticsAgentRollup`, add `agents` field to
   `AnalyticsSummary`.
4. **`AnalyticsPage.tsx`** — derive `agentRows`/`agentMax`, render "By Agent"
   card, add `"unknown"` to `MODEL_META`.

---

## Verification Checklist (for the implementer)

- [ ] `GET /api/analytics/summary` response includes an `agents` array with at
  least one entry after running any pipeline to completion.
- [ ] Each `agents` entry has a human-readable `agent_name`, non-zero
  `total_tokens`, and a valid `cost` (> 0 when the model is known).
- [ ] "By Model" section no longer shows `unknown` for runs completed with the
  current codebase (i.e., runs whose `agent_outputs` carries `model_id`).
- [ ] "By Agent" card renders in the Analytics page below "By Model", with
  proportional bars matching the visual language of "By Pipeline Type".
- [ ] "By Agent" card is empty-state-safe: shows a "No agent data" message when
  `agentRows` is empty (e.g. on a fresh account with no completed runs).
- [ ] The model dropdown filter still works correctly — selecting a specific
  model filters all sections (KPIs, daily, pipeline, agent) to that model.
- [ ] `tsc --noEmit` exits with 0 errors.
- [ ] `pytest tests/app/test_analytics.py` passes with no regressions.
- [ ] `ruff check backend/app/api/analytics.py` clean.
- [ ] INV-3: `pytest tests/agents/test_characterization_*.py` exits with 0
  failures (no golden touched).

---

## Out of Scope (this refinement)

- **Per-agent filtering:** A "filter by agent" dropdown at the top of the page.
  The current server-side filter supports date/pipeline/model only. Adding an
  agent dimension requires a new query parameter and a wider `_aggregate` change.
  Defer to a follow-up.
- **"By Agent" in Daily Activity chart:** Stacking the daily bar by agent would
  require per-day per-agent data in `DailyBucket`. Not part of this change.
- **Backfilling `model_id` on old NULL runs:** A one-off SQL update to backfill
  the run-level `model_id` from `agent_outputs` on completed legacy runs. Safe
  but out of scope — the two-pass attribution in `_aggregate` already handles
  these rows without a backfill.
- **Caching delta per agent:** A per-agent cache-savings breakdown similar to the
  run-level `spend_full`/`spend` delta (ISS-034). Deferred.
