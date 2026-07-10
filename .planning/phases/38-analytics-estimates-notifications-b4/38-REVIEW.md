---
phase: 38-analytics-estimates-notifications-b4
reviewed: 2026-07-10
depth: deep
files_reviewed: 10
files_reviewed_list:
  - backend/app/api/analytics.py
  - backend/app/main.py
  - frontend/src/components/analytics/AnalyticsPage.tsx
  - frontend/src/components/analytics/charts/DonutChart.tsx
  - frontend/src/components/analytics/charts/BarChart.tsx
  - frontend/src/hooks/useNotifications.ts
  - frontend/src/components/ui/NotificationPanel.tsx
  - frontend/src/components/ui/Badge.tsx
  - frontend/src/components/layout/DashboardLayout.tsx
  - frontend/src/lib/api.ts
  - frontend/src/components/catalog/HomeLaunchGrid.tsx
findings:
  critical: 0
  high: 0
  medium: 3
  low: 3
  nit: 1
  total: 7
status: issues_found
---

# Phase 38: Code Review Report — Analytics, Estimates & Notifications [B4]

**Reviewed:** 2026-07-10
**Depth:** deep (cross-file: FE api client ↔ BE response model ↔ persistence columns)
**Files Reviewed:** 10 source files (+ 3 test files sanity-checked; assertions not weakened)
**Status:** issues_found

## Summary

The security-critical surface — the new `GET /api/analytics/summary` endpoint — is sound.
Owner scope is keyed on the correct non-null principal (`WorkflowRun.user_id == current_user.id`,
never the backfilled nullable `owner_id`), the route is gated by `Depends(get_current_user)`
(401 on missing/expired/tampered/revoked JWT), the response is constrained to a numbers-only
`response_model` (no `output` / `agent_outputs` / `input` / prompt bodies can leak even if the
aggregator returned them), `token_usage` is tolerantly parsed per-run (malformed JSON → `{}` →
200 not 500), and `range` is a hard allow-list that defaults to 30d on any unknown value. The
persisted `token_usage` key names verified against both write sites
(`websocket.py:2194`, `run_commands.py:1277`) match the reader exactly. The two new SVG chart
primitives use no `dangerouslySetInnerHTML`, no external script/CDN — CSP-safe. INV-3 is
satisfied: the old inline BarChart/donut were deleted, no shadow chart implementation remains
in `AnalyticsPage.tsx`.

No CRITICAL or HIGH findings. The issues below are correctness/labeling defects in the derived
display math and the notification state machine, plus one deployment-dependent datetime concern.

## Critical Issues

None.

## High Issues

None.

## Medium Issues

### MD-01: Gate notification status never reverts to "running" after the gate resolves

**File:** `frontend/src/components/layout/DashboardLayout.tsx:489-494`,
`frontend/src/hooks/useNotifications.ts:96-104`, `40-64`
**Issue:** `markGatePaused` sets a run's notification to `status:"gate"` (amber / PauseCircle)
when a review gate opens. Nothing ever sets it back. After the gate resolves and the run
resumes, the only effect that touches the notification during running is `updateProgress`
(`useNotifications.ts:60-64`), which mutates **only** `agentsCompleted` and leaves `status`
untouched. `addRunningNotification` (the sole writer of `status:"running"`) fires only at
run start. So a resumed run's notification is stuck displaying "paused/gate" for the entire
remainder of the run until a terminal `markCompleted`/`markFailed`/`markCancelled` overwrites
it. The notifications UI therefore misrepresents the live run state.
**Fix:** On resume, revert the status. Either add a `markRunning(id)` and call it from the
progress effect when `!reviewGateData && pipelineState.isRunning`, or have `updateProgress`
reset a `"gate"` status back to `"running"`:
```ts
const updateProgress = useCallback((id: string, agentsCompleted: number) => {
  setNotifications(prev =>
    prev.map(n => n.id === id
      ? { ...n, agentsCompleted, status: n.status === "gate" ? "running" : n.status }
      : n)
  );
}, []);
```

### MD-02: "Avg / Run" and "Est. Cost" mix all-run totals with a completed-run denominator/label

**File:** `frontend/src/components/analytics/AnalyticsPage.tsx:183`, `311-315`
**Issue:** The backend sums `spend` and `token_totals` over **all** owner runs in the range
(`analytics.py:182-187` — no status filter), but the frontend labels/derives them as if they
were completed-run figures:
- `avgTokens = Math.round(totalTokens / completedCount)` (line 183) divides **all-run** tokens
  by the **completed-run** count. If any run is `running`/`failed`/`degraded` with token usage,
  this over-states the average, and it is neither "avg per run" nor "avg per completed run".
  The card sub-label even reads "tokens per pipeline" (line 315), implying a per-run metric.
- The Est. Cost card sub-label reads `across ${completedCount} completed runs` (line 312) while
  `spend` includes cost from non-completed runs too.
**Fix:** Pick one basis and make numerator, denominator, and label agree. For a true per-run
average divide by `totalCount`; for a completed-run average the backend must also expose
completed-only token/cost sums. Simplest correct fix:
```ts
const avgTokens = totalCount > 0 ? Math.round(totalTokens / totalCount) : 0;
// ...card sub for cost:
sub={`across ${totalCount} run${totalCount !== 1 ? "s" : ""}`}
```

### MD-03: `type_avg_duration_sec` is keyed on `run.type` but the estimate looks it up by workflow `row.id`

**File:** `backend/app/api/analytics.py:235-237`,
`frontend/src/components/catalog/HomeLaunchGrid.tsx:204-208`
**Issue:** The backend builds `type_avg_duration_sec` keyed on the raw persisted `WorkflowRun.type`
value (e.g. `od_prototype`, `prototype_revision`, `user_stories`). HomeLaunchGrid looks it up as
`avgDurationSec[row.id]`, where `row.id` is the manifest/catalog workflow id (e.g. `prototype`).
Whenever the stored `type` differs from the catalog id — the od_/revision/custom variants — the
lookup misses and the "~Xm" clause silently never renders, so the "real estimate" degrades to
agents-only for exactly the pipelines that have the most history. Additionally, `type_avg_duration_sec`
includes types whose completed count is 0 with value `0.0` (`analytics.py:236`, the `else 0.0`
branch); when such a key *does* match a `row.id`, `Math.round(0/60)` renders a misleading `~0m`.
**Fix:** Align the key space. Either normalise the backend rollup key to the base workflow id
(mirroring the FE `normalizeType`) so od_/revision variants collapse onto the catalog id, or
have the FE resolve the run-type key for each row before lookup. Also omit / guard zero-duration
entries so a `0.0` average does not surface as `~0m`:
```ts
const avgSec = avgDurationSec[row.id];
const minutes = avgSec != null && avgSec >= 30 ? Math.round(avgSec / 60) : null;
```

## Low Issues

### LW-01: Aware-UTC cutoff compared against a timezone-naive `created_at` column

**File:** `backend/app/api/analytics.py:54-63`, `270-272`
**Issue:** `_cutoff_for` returns an aware-UTC `datetime` (`datetime.now(timezone.utc)`), but
`WorkflowRun.created_at` is a plain `DateTime` column (`models/workflow.py:38-40` — Postgres
`timestamp without time zone`, stored as naive UTC). The filter
`WorkflowRun.created_at >= cutoff(aware)` is only guaranteed correct when the DB session TimeZone
is UTC; on a non-UTC Postgres session the implicit naive↔aware cast can shift the window by the
session offset, and under SQLite (local/test) the comparison is lexical against a string that
carries a `+00:00` suffix on one side only, which can mis-filter boundary rows. Not verified to
misbehave in the current UTC deployment, but it is a latent correctness hazard.
**Fix:** Strip tzinfo before filtering so both sides are naive-UTC:
`cutoff = cutoff.replace(tzinfo=None)` before the `.filter(...)`, matching the naive column, or
make the column `DateTime(timezone=True)` project-wide (out of this phase's additive scope).

### LW-02: `markGatePaused` re-clears `read:false` on every `reviewGateData` identity change

**File:** `frontend/src/components/layout/DashboardLayout.tsx:489-494`,
`frontend/src/hooks/useNotifications.ts:96-104`
**Issue:** The gate effect fires whenever `reviewGateData` or `isRunning` changes, and
`markGatePaused` unconditionally sets `read:false`. If `reviewGateData` is re-created (new object
identity) during a single gate — common when gate payloads stream/update — a notification the
user already opened/read is repeatedly forced back to unread, re-surfacing the unread badge.
**Fix:** Only clear `read` on the transition into the gate state, e.g. guard in the reducer
(`n.status === "gate" ? n : { ...n, status: "gate", read: false }`) so re-entrant calls are
idempotent, or gate the effect on a ref that tracks whether the gate notification was already
fired for this run.

### LW-03: `success_rate` counts non-terminal runs in the denominator

**File:** `backend/app/api/analytics.py:219`
**Issue:** `success_rate = completed / total` where `total = len(runs)` includes `running`,
`failed`, `degraded`, `cancelled`. For an `all`/`today` window with in-flight runs, the KPI
under-states success (a currently-running run is scored as a non-success). This is defensible as
a product choice but the "Success Rate" donut can read low purely because runs are still active.
**Fix:** If the intended metric is success among *terminal* runs, divide by
`completed + failed` (terminal denominator): `success_rate = completed / (completed + failed)`
when that sum > 0 else 0.0. Otherwise document the whole-population definition.

## Nit

### NT-01: Sub-minute averages render "~0m"

**File:** `frontend/src/components/catalog/HomeLaunchGrid.tsx:205-208`
**Issue:** `minutes = Math.round(avgSec / 60)` yields `0` for any average under 30s, so the card
shows "~0m", which reads worse than omitting the clause. (Folded into the MD-03 fix suggestion.)
**Fix:** Only render the minutes clause when `avgSec >= 30` (round-to-≥1m), else omit it.

---

## Positive Confirmations (verified, not defects)

- **Owner scope (T-38-01):** base query is `WorkflowRun.user_id == current_user.id`
  (`analytics.py:268`) — the non-null principal, never the nullable `owner_id`. No code path
  admits a cross-owner row. Verified against `models/workflow.py:20` (`user_id nullable=False`)
  vs `:58` (`owner_id nullable=True`).
- **Auth gate:** `Depends(get_current_user)` raises 401 on missing/expired/tampered/revoked JWT
  (`dependencies.py:153-178`).
- **Numbers-only (T-38-Leak):** `response_model=AnalyticsSummary` (counts/tokens/cost/durations
  only) strips any non-schema field FastAPI-side; no `output`/`agent_outputs`/`input`/prompt/
  thinking bodies are reachable.
- **DoS guard (T-38-02):** `_parse_token_usage` is per-run try/except → `{}` on missing/non-JSON/
  non-dict blob (`analytics.py:66-78`); `_num` coerces garbage numerics → 0.0. A poisoned row
  yields a 200 with an empty per-run aggregate, never a 500.
- **Range allow-list (T-38-03):** `_cutoff_for` uses `.get(range, table[_DEFAULT_RANGE])`
  (`analytics.py:63`) — unknown/injected value → 30d default, never an unbounded/injected scan.
- **token_usage key contract:** reader keys (`total_input_tokens`, `total_output_tokens`,
  `total_tokens`, `total_cache_read_tokens`, `total_cache_write_tokens`, `estimated_cost_usd`)
  match both writers (`websocket.py:2195-2210`, `run_commands.py:1278-1289`) exactly.
- **Charts CSP-safe:** `DonutChart`/`BarChart` render pure SVG/flex, no `dangerouslySetInnerHTML`,
  no external script/CDN; `percent` is clamped `0..100` (`DonutChart.tsx:52`); `max` guarded with
  a `,1` floor so empty series never divide by zero (`BarChart.tsx:55`, `AnalyticsPage.tsx:208-221`).
- **INV-3:** no inline chart primitive remains in `AnalyticsPage.tsx` (grep for `function BarChart`/
  `<svg`/`<circle` returns nothing) — the extraction fully superseded the deleted inline code.
- **AnalyticsPage refetch effect:** cancelled-guard + cleanup correctly handle rapid `dateFilter`
  changes; each run's stale closure is neutralised by the prior cleanup's `cancelled = true`
  (`AnalyticsPage.tsx:133-156`). Only the date filter refetches; pipeline/model filters narrow
  the already-fetched arrays in memory (as designed).
- **api.ts client:** `AnalyticsSummary` TS type mirrors the Pydantic model field-for-field;
  `range` is `encodeURIComponent`-escaped in the query string (`api.ts:401-408`).

## Overall Assessment

Ship-blocking security posture is clean — the endpoint's owner-scope, auth gate, numbers-only
contract, tolerant parse, and range allow-list all hold as specified, and the frontend charts
are CSP-safe with INV-3 respected. The remaining work is correctness/labeling polish in the
derived display layer: the notification gate state gets stuck (MD-01), two KPI metrics blend
all-run totals with completed-run framing (MD-02), and the estimate's minutes half likely
won't render for the od_/revision pipelines due to a key-space mismatch (MD-03). None are
data-loss or security issues; MD-01/MD-02 are the most user-visible and should be fixed before
this reaches users. Recommend addressing the three MEDIUMs; LOW/NIT at discretion.

---

_Reviewed: 2026-07-10_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
