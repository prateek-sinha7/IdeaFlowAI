# Phase 38: Analytics, Estimates & Notifications [B4] — Research

**Researched:** 2026-07-10
**Domain:** Additive read-only aggregation endpoints (FastAPI/SQLAlchemy) + self-contained SVG charts / estimates / notifications feed (Next.js/React FE). LAST offline phase of Flowin v2.0.
**Confidence:** HIGH (every claim below is anchored to a file:line verified this session; the few unverifiable items are tagged UNVERIFIED)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions (38-CONTEXT.md §decisions L22–31; POR §3 LOCK-B/-E, §88, §96)
- **Analytics aggregations power the dashboard — filters RECOMPUTE (SC-1).** Date-scoped: daily series, per-pipeline/model rollups, spend. Real endpoints, not the mock's static numbers.
- **Charts self-contained** — token-styled SVG donut/bar; NO heavy external chart lib (CSP-safe; consume the Phase-32 `@theme` tokens; the governance status-palette exception does NOT apply — **one-chroma unless a datum is a run-status**).
- **Estimates from real data** — manifest step count + analytics history averages (NOT hardcoded).
- **Notifications feed** — kinds gate/running/done/failed, wired from existing run-state; the Phase-35 panel is the chrome. Live push confirmation → Phase 34 if it needs the live connection.
- **Additive READ-only backend** — aggregate EXISTING run/token/cost data; NO new tables.

### Invariants (locked, do not re-open)
- **SC-001/INV-1** — analytics/estimates/feed keyed on GENERIC run data, NEVER a workflow-name branch.
- **INV-3** — the 5 characterization goldens byte/event-identical (aggregations are additive read-only → untouched by construction).
- **Owner-scoped** — two-layer `WorkflowRun.user_id == principal` → 404, NOT the nullable `owner_id`; import-linter stays 4/0.
- **Q3** — additive migrations only; aggregate existing columns, NO new tables.
- **Token gate** — per touched/new FE file: retired-palette (`#1B2A4A` / `#2563eb` / `#f5f5f0` / Inter / Fraunces / JetBrains) = 0; positive `@theme` / `ui/` usage.
- **a11y** — charts have text alternatives; feed keyboard-navigable + aria.
- **LOCK-B** — NO transport touch (SSE/WS untouched).

### Claude's Discretion
- Chart component placement (`components/ui/` vs a new `components/analytics/charts/` dir).
- Exact endpoint shape/URL for the aggregation route(s) (single vs split), provided it is additive, owner-scoped, and date-parameterised.
- Whether the analytics endpoint also serves the per-type average-duration the Home estimate needs, vs. a dedicated field.

### Deferred Ideas (OUT OF SCOPE — 38-CONTEXT.md §deferred)
- Live notification PUSH over the real connection (build the feed logic offline; live push confirmation → Phase 34 if connection-dependent).
- Compliance-PDF / advanced analytics exports.
- The Concierge live-wiring (Phase 34).
- Handoff screen (post-v2.0).
- Team/org-scoped analytics (LOCK-E deferred sharing).
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **SHELL-05** | Date-scoped analytics aggregations + chart components + per-deliverable estimates + notifications feed | This is the sole Phase-38 REQ (`.planning/REQUIREMENTS.md:252`, traceability `:474`). It decomposes into the four deliverables below. Backend: clone `_owner_gate_or_404` (`runs.py:1206`) + aggregate `WorkflowRun` columns (`workflow.py:36`). FE: reskin `AnalyticsPage.tsx` + extract SVG charts, add estimate line to `HomeLaunchGrid.tsx` (`step_count` from `/api/workflows`), add `gate` kind + wire `markFailed`/`markCancelled` in `useNotifications.ts`/`DashboardLayout.tsx`. |
</phase_requirements>

---

## Summary

Phase 38 is the data-backed tail of the shell convergence. It has four deliverables, and the single most important framing fact — **verified this session** — is that the product's `AnalyticsPage.tsx` is **already fully data-driven**: it fetches `getWorkflows(token, {limit: 500})` and computes every KPI, the daily bar chart, the success donut, the pipeline breakdown, the token split, and spend **client-side in React** (`AnalyticsPage.tsx:195–299`). The "static snapshot" problem in the evidence docs is about the **mock HTML**, not the product. So the SC-1 "filters RECOMPUTE" mandate is *already met client-side*; the real, honest work of this phase is: (1) move the rollup to **server-side date-scoped aggregation endpoints** so the browser stops downloading up-to-500 full run rows to reduce in JS, and wire the date filter to re-query; (2) **reskin** `AnalyticsPage.tsx` — it is riddled with the retired navy palette (100 grep hits of `#1B2A4A`/`bg-gray`/`bg-white`) and extract its two **already-hand-rolled SVG charts** (`BarChart` `AnalyticsPage.tsx:96`, the donut `:432–444`) into reusable, token-styled `charts/` components; (3) add a per-deliverable estimate line to the Home cards from `step_count` (already on `/api/workflows`, `workflows.py:78`) + a history-average duration from the new endpoint; (4) extend the notifications feed with a **`gate` kind** and **wire the missing `markFailed`/`markCancelled` calls** — verified this session that `DashboardLayout.tsx` destructures them (`:365–366`) but **never calls them** (only `markCompleted` fires, `:456`), so failed/cancelled runs produce no notification today.

The backend is trivially safe: an owner-scoped, read-only aggregation over columns that already exist on `WorkflowRun` (`token_usage` JSON text `workflow.py:36`, `duration` `:34`, `type` `:22`, `status` `:23`, `created_at` `:38`). The exact owner-gate idiom to clone is `_owner_gate_or_404(db, workflow_id, user_id)` (`runs.py:1206`) — but note that an **aggregation is a collection endpoint** (no `{id}` path param unless you add a pipeline drill-down), so its owner-scoping is the `WHERE user_id == current_user.id` filter (the `list_runs` idiom, `runs.py:250`), and the "IDOR→404" clause only bites if a per-run/per-pipeline path variant is added. No new tables, no migrations, no engine/transport touch → INV-3 holds by construction.

**Primary recommendation:** Add one additive read-only `GET /api/analytics/summary?range=<7d|30d|…>` on a NEW `backend/app/api/analytics.py` router, owner-scoped via the `list_runs`/`_owner_gate_or_404` idiom, returning the exact aggregate shape `AnalyticsPage.tsx` already computes (KPIs, daily series, pipeline rollup, model rollup, spend, **+ per-type avg duration for the Home estimate**). Wire `AnalyticsPage` date filter → refetch → re-render. Reskin `AnalyticsPage` onto Phase-32 tokens and extract `DonutChart`/`BarChart` token-styled SVG components. Add the estimate line to `HomeLaunchGrid`. Add a `gate` kind to `PipelineNotification` and wire `markFailed`/`markCancelled`/gate transitions in `DashboardLayout`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Date-scoped analytics rollups (daily/pipeline/model/spend) | API / Backend (new `analytics.py`) | Database (aggregate `workflow_runs`) | Aggregation over owned run rows belongs server-side; today it leaks 500 rows to the browser to reduce in JS. Owner-scope must be enforced server-side. |
| Chart rendering (donut/bar SVG) | Browser / Client | — | Pure presentation; self-contained SVG, no lib, consumes `@theme` tokens. |
| Per-deliverable estimate (agents + time) | Browser / Client (compose) | API (both feeds) | `step_count` from `/api/workflows` (`workflows.py:78`) + avg-duration from the new analytics endpoint; the FE composes the "~N agents · ~Xm" line. |
| Notifications feed (gate/running/done/failed) | Browser / Client (`useNotifications`) | (Phase 34: live push) | Feed logic is client state driven off `pipelineState`; live PUSH over the real connection is the ONLY deferrable (LOCK-E → Phase 34). |

---

## Standard Stack

This phase adds **zero** new runtime dependencies. Everything is built from the existing stack.

### Core (existing — reuse, do not add)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI + SQLAlchemy | (in `backend/`) | The new `analytics.py` router + `WorkflowRun` query | `[VERIFIED: codebase]` every existing read endpoint (`runs.py`) uses this exact stack. |
| Pydantic `BaseModel` | (in `backend/`) | Response schema for the aggregation | `[VERIFIED: codebase]` `RunSummaryResponse` `runs.py:1010` is the template. |
| React + Next.js + `motion/react` | (in `frontend/`) | Chart components, page reskin, feed | `[VERIFIED: codebase]` `AnalyticsPage.tsx:4` already imports `motion/react`; charts already animate with it. |
| `lucide-react` | (in `frontend/`) | Icons (already used in AnalyticsPage/NotificationPanel) | `[VERIFIED: codebase]` `AnalyticsPage.tsx:5`, `NotificationPanel.tsx:5`. |

### Charts — build, do not install
| Approach | Purpose | Why |
|----------|---------|-----|
| Hand-rolled inline SVG (`<svg><circle/><path/>` for donut, flexbox `<div>` bars) | Donut + bar charts | `[VERIFIED: codebase]` The product ALREADY does this — `AnalyticsPage.tsx:96` `BarChart` (flexbox divs) and `:432–444` (SVG `<circle>` donut with `strokeDasharray`). The phase EXTRACTS + tokenises these; it does not introduce a charting library. LOCKED: "NO heavy external chart lib (CSP-safe)". |

### Alternatives Considered — REJECTED (locked)
| Instead of | Could Use | Why REJECTED |
|------------|-----------|--------------|
| Self-contained SVG | recharts / visx / chart.js / nivo | LOCKED decision: CSP-safe, no heavy chart lib. `[CITED: 38-CONTEXT.md L25]` |
| New aggregation table | denormalised analytics rollup table | LOCKED: Q3 additive-only, NO new tables. Aggregate existing columns live. `[CITED: 38-CONTEXT.md L28]` |

**Installation:** None. `[VERIFIED: codebase]` No `npm install` / `pip install` in this phase.

## Package Legitimacy Audit

**Not applicable — this phase installs ZERO external packages** (charts are hand-rolled SVG per the locked decision; backend reuses FastAPI/SQLAlchemy/Pydantic already vendored). No slopcheck/registry audit required. If a future planner attempts to add a chart library, that is a **locked-decision violation** and must be rejected, not audited.

---

## Architecture Patterns

### System Architecture Diagram (data flow)

```
                          ┌─────────────────────────────────────────┐
  Analytics dashboard     │  AnalyticsPage.tsx (reskinned, tokens)   │
  date filter change ─────▶  onFilter(range) ─┐                      │
                          │                    ▼                      │
                          │   getAnalyticsSummary(token, range) ──────┼──▶ GET /api/analytics/summary?range=30d
                          │        (new client in api.ts)             │        │  (NEW analytics.py router)
                          │                                           │        ▼
                          │   ◀── AnalyticsSummary {kpis, daily[],    │   WorkflowRun query
                          │        pipelines[], models[], spend,      │   WHERE user_id == principal   ← owner scope
                          │        typeAvgDurationSec{} } ────────────┼──      AND created_at >= cutoff(range)
                          │                    │                      │        │
                          │        ┌───────────┴──────────┐           │        ▼
                          │        ▼                      ▼           │   aggregate in-Python:
                          │   <DonutChart/>          <BarChart/>      │     - daily series
                          │   (token SVG, a11y)      (token SVG)      │     - per-type/{model} rollup
                          └─────────────────────────────────────────┘     - sum(estimated_cost)=spend
                                                                           - avg(duration) per type
  Home cards                ┌──────────────────────────────────────┐
  (HomeLaunchGrid) ─────────▶ GET /api/workflows  → step_count      │  (existing workflows.py:78)
                            │ GET /api/analytics/summary → avg dur   │  → "~{step_count} agents · ~{Xm}"
                            └──────────────────────────────────────┘

  Live run events           ┌──────────────────────────────────────┐
  (pipelineState in ────────▶ useNotifications: addRunning / update  │  (existing hook; ADD `gate` kind +
   DashboardLayout)         │  Progress / markCompleted / markFailed │   WIRE markFailed/markCancelled +
                            │  / markCancelled / (NEW) markGatePaused │   gate transition — see Pitfall 4)
                            │            │                           │
                            │            ▼                           │
                            │   <NotificationPanel/> (chrome, P35)   │  (existing ui/NotificationPanel.tsx)
                            └──────────────────────────────────────┘
```

### Recommended Project Structure (additive)
```
backend/app/api/
└── analytics.py            # NEW — GET /api/analytics/summary (owner-scoped, read-only)
backend/tests/unit/
└── test_analytics_api.py   # NEW — owner→200 / cross-owner isolation / recompute correctness

frontend/src/components/analytics/
├── AnalyticsPage.tsx       # RESKIN onto @theme tokens; wire filter→refetch
└── charts/                 # NEW dir (Claude's discretion: or components/ui/)
    ├── DonutChart.tsx      # extracted from AnalyticsPage:432 (token SVG, a11y text alt)
    └── BarChart.tsx        # extracted from AnalyticsPage:96 (token SVG/flex, a11y)
frontend/src/lib/api.ts     # ADD getAnalyticsSummary(token, range) + AnalyticsSummary type
frontend/src/components/catalog/HomeLaunchGrid.tsx  # ADD estimate line
frontend/src/hooks/useNotifications.ts              # ADD "gate" kind + markGatePaused
frontend/src/components/layout/DashboardLayout.tsx  # WIRE markFailed/markCancelled/gate
```

### Pattern 1: Owner-scoped read-only aggregation endpoint
**What:** New router that aggregates the caller's own runs. No new table.
**When to use:** All Phase-38 backend work.
**Example (clone the verified idiom):**
```python
# Source: backend/app/api/runs.py:236 (list_runs collection owner-scope)
#         backend/app/api/runs.py:1206 (_owner_gate_or_404 — for any {id} drill-down variant)
# NEW: backend/app/api/analytics.py
router = APIRouter(prefix="/api/analytics", tags=["analytics"])

@router.get("/summary", response_model=AnalyticsSummary)
def get_analytics_summary(
    range: str = "30d",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cutoff = _cutoff_for(range)                      # today|3d|7d|30d|90d|all → datetime
    q = db.query(WorkflowRun).filter(WorkflowRun.user_id == current_user.id)   # ← owner scope
    if cutoff:
        q = q.filter(WorkflowRun.created_at >= cutoff)
    runs = q.all()
    # aggregate token_usage (json.loads in try/except → {} fallback, DoS guard —
    # mirror runs.py:1116-1123), duration, type, status IN PYTHON. Zero new fields.
    return _aggregate(runs)
```
**Critical:** `WorkflowRun.token_usage` is a JSON **Text** column (`workflow.py:36`) — `json.loads` each inside `try/except` with a `{}` fallback exactly like the summary endpoint (`runs.py:1116–1123`) so a malformed blob degrades to an empty aggregate, never a 500 (threat T-36-02-DoS).

### Pattern 2: Self-contained token-styled SVG chart (extract, don't add a lib)
**What:** A donut is an SVG `<circle>` with `strokeDasharray`/`strokeDashoffset`; a bar chart is flex `<div>`s or SVG `<rect>`s.
**Example (the EXISTING donut to tokenise + extract):**
```tsx
// Source: frontend/src/components/analytics/AnalyticsPage.tsx:431-444 (VERIFIED — already in repo)
<svg width="88" height="88" viewBox="0 0 88 88" role="img"
     aria-label={`Success rate ${successRate}% — ${completed} completed, ${failed} failed`}>
  <circle cx="44" cy="44" r="36" fill="none" stroke="var(--color-status-queued-fill)" strokeWidth="10" />
  <motion.circle cx="44" cy="44" r="36" fill="none"
    stroke="var(--color-brand)"                              {/* ← was hardcoded #1B2A4A */}
    strokeWidth="10" strokeLinecap="round"
    strokeDasharray={`${2 * Math.PI * 36}`}
    animate={{ strokeDashoffset: 2 * Math.PI * 36 * (1 - successRate / 100) }} />
</svg>
```
Replace every hardcoded hex (`#1B2A4A`, `#8AAEC8`, `#F3F4F6`, `bg-gray-*`, `bg-white`) with the Phase-32 token vars (see **Phase-32 Token Reference** below). **One-chroma rule:** all chart series use `--color-brand`/tints EXCEPT where a datum IS a run status (completed/failed) — then and ONLY then use the status ramp (`--color-status-done` / `--color-status-failed`). This is the governance-exception carve-out named in the locked decisions.

### Pattern 3: Estimate line from real data (Home cards)
**What:** `~{agents} agents · ~{minutes}m` derived, not hardcoded.
**How:** `agents = workflow.step_count` (already on `WorkflowSummary`, `api.ts:681` / `workflows.py:78`). `minutes = round(typeAvgDurationSec[workflow.id] / 60)` from the new analytics endpoint; fallback when a type has no history → sum of the manifest agents' `estimated_duration` (AGENT.md field, default 3.0 — **NOTE**: not currently exposed by `WorkflowSummary`; if the manifest-sum fallback is wanted server-side, add an additive `estimated_duration_sec` field to `WorkflowSummary` — read-only, no table). `[VERIFIED: workflows.py:78 step_count exists; estimated_duration is AGENT.md-only, backend/CLAUDE.md AGENT.md schema]`

### Anti-Patterns to Avoid
- **Adding a chart library** (recharts/chart.js/visx) — LOCKED violation.
- **Creating a new analytics/rollup table or migration** — LOCKED Q3 violation.
- **Branching aggregation logic on a workflow name** (`if type == "prototype"`) — SC-001/INV-1 violation. Key everything on the generic `type` string + `status` value; the `PIPELINE_LABELS` map (`AnalyticsPage.tsx:42`) is a *display* lookup, not control flow, which is fine.
- **Gating owner-scope on `owner_id`** — MUST be `user_id` (the nullable `owner_id` is backfilled, `workflow.py:58`). LOCKED.
- **Touching the engine/transport/goldens** — LOCK-B + INV-3.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Owner gate on a `{id}` drill-down | A fresh ownership filter | `_owner_gate_or_404(db, id, user_id)` `runs.py:1206` | Verified idiom; 404-not-403 IDOR posture already correct. |
| Collection owner scope | Ad-hoc filtering | The `list_runs` `WHERE user_id == current_user.id` idiom `runs.py:250` | Same posture, already used by the analytics data source. |
| JSON token_usage parse | Naive `json.loads` (can 500) | try/except → `{}` fallback `runs.py:1116–1123` | DoS guard for malformed stored blobs. |
| Donut / bar chart | recharts et al. | Extract the EXISTING inline SVG (`AnalyticsPage.tsx:96`, `:432`) | Already works; just tokenise + extract. CSP-safe, zero deps. |
| Pipeline-type display labels | New map | Reuse `PIPELINE_LABELS` `AnalyticsPage.tsx:42` / `WORKFLOW_LABELS` `useNotifications.ts:19` | Already maps `od_ppt→Presentation` etc. |
| Notification feed store | A DB/notifications table | Extend the client `useNotifications` hook `useNotifications.ts:38` | Feed is client state off `pipelineState`; LOCK-E defers live push, not the feed. |

**Key insight:** Nearly every "new" thing this phase needs already exists in the repo in almost-final form. The dominant activity is **reskin + extract + wire**, not build. The one genuinely new artifact is the `analytics.py` aggregation router, and even that is a near-clone of `get_run_summary` (`runs.py:1080`).

---

## Common Pitfalls

### Pitfall 1: Believing the product analytics is "static" (evidence-doc trap)
**What goes wrong:** The evidence docs (`02-workspace-shell-teardown.md:294`, POR §9) say "analytics date filters recompute nothing." A planner may write a task to "make analytics dynamic," not realising it already is.
**Why it happens:** Those statements describe the **mock HTML**, not the product. `[VERIFIED: AnalyticsPage.tsx:195–299 computes every metric client-side from getWorkflows(limit:500)]`.
**How to avoid:** Frame the backend task as "**move the client-side rollup to a server endpoint** so we stop shipping 500 rows and reduce in JS," and the FE task as "wire the filter to refetch + **reskin**." Not "build analytics from scratch."
**Warning signs:** A task that re-derives KPI math from zero instead of porting the exact formulas at `AnalyticsPage.tsx:249–297`.

### Pitfall 2: The retired palette is pervasive in AnalyticsPage
**What goes wrong:** The token-gate check (`retired-palette grep = 0`) fails hard.
**Why it happens:** `AnalyticsPage.tsx` has **100 grep hits** of `#1B2A4A` / `bg-gray` / `bg-white` / `#8AAEC8` `[VERIFIED this session]`. It predates the Phase-32 token layer.
**How to avoid:** Budget the reskin as a substantial sweep, not a touch-up. Every hex → a `--color-*` var; `bg-white`→`bg-surface-white`/`bg-surface-card`, `text-gray-*`→`text-ink-*`, `border-gray-*`→`border-line-*`. Follow the exact idiom the 35/36 reskins used (STATE.md logs the token classes).
**Warning signs:** `grep -c "#1B2A4A\|bg-gray\|bg-white\|#8AAEC8\|#2563eb" AnalyticsPage.tsx` > 0 after the reskin.

### Pitfall 3: "IDOR→404" mis-applied to a collection endpoint
**What goes wrong:** A planner writes a "cross-owner → 404" test for `/api/analytics/summary`, but there is no `{id}` to forge, so the test is meaningless / can't be written as stated.
**Why it happens:** The POR §96 "IDOR→404, user_id-keyed" clause is written for per-run endpoints.
**How to avoid:** For the **collection** aggregation endpoint, the correct security test is **owner isolation**: seed two users, each with runs; assert user A's `/summary` totals include ONLY A's runs (B's runs never leak into the aggregate). The "→404" clause applies ONLY if a per-run/per-pipeline path variant (`/summary/{run_id}` or similar) is added — then clone `_owner_gate_or_404`.
**Warning signs:** A test named `test_cross_owner_404` on an endpoint with no path id.

### Pitfall 4: Failed/cancelled runs produce NO notification today (and no `gate` kind exists)
**What goes wrong:** The "kinds gate/running/done/failed" requirement looks done because `useNotifications` has `markFailed`/`markCancelled` — but they're never called, and there is no `gate` kind at all.
**Why it happens:** `[VERIFIED this session]` `DashboardLayout.tsx:365–366` destructures `markFailed, markCancelled` but the only terminal call is `markCompleted(notifId)` at `:456`. `PipelineNotification.status` is `"running" | "completed" | "failed" | "cancelled"` (`useNotifications.ts:11`) — **no `gate`**.
**How to avoid:** (a) Add `"gate"` to the `status` union + a `StatusIcon` branch (`NotificationPanel.tsx:30`) + a `Badge` status (`NotificationPanel.tsx:196`); (b) add a `markGatePaused(id)` transition to the hook; (c) in `DashboardLayout`, wire the terminal-failed / terminal-cancelled branches (the generic markers `pipelineState.failed` / `.cancelled` already exist, `DashboardLayout.tsx:1314`) to call `markFailed`/`markCancelled`, and the `review_gate_ready` / gate-paused state to `markGatePaused`. Key OFF the generic pipelineState markers, NEVER a workflow name (SC-001).
**Warning signs:** A run that fails still shows a "running" notification; no notification ever shows a `gate` state.

### Pitfall 5: Estimate uses a hardcoded number
**What goes wrong:** Copying the mock's `~24m / 5 agents` literals (`02-teardown §2.1(b)`) → violates "estimates from real data."
**How to avoid:** `agents = step_count` (`workflows.py:78`), `time = history avg duration` (new endpoint) with a manifest-`estimated_duration`-sum fallback. Render "~N agents" always (step_count is always available); render "~Xm" only when a history average OR manifest sum is available, else omit the time clause.

### Pitfall 6: Charts unreadable to screen readers
**What goes wrong:** a11y gate fails — SVG charts with no text alternative.
**How to avoid:** Every chart SVG carries `role="img"` + an `aria-label` summarising the data (see Pattern 2), OR an adjacent visually-hidden data table. The existing donut has NO aria today — add it during extraction. Feed a11y already handled by Phase 35 (`NotificationPanel.tsx:81,87–89,103` — `role="menu"`, Escape-close+refocus).

---

## Code Examples

### Aggregation cutoff + owner-scoped query (backend)
```python
# Source: mirrors AnalyticsPage.tsx:212-219 cutoff table + runs.py:250 owner filter
from datetime import datetime, timedelta, timezone
def _cutoff_for(range: str) -> datetime | None:
    now = datetime.now(timezone.utc)
    return {
        "today": now.replace(hour=0, minute=0, second=0, microsecond=0),
        "3d":  now - timedelta(days=2),  "7d":  now - timedelta(days=6),
        "30d": now - timedelta(days=29), "90d": now - timedelta(days=89),
        "all": None,
    }.get(range, now - timedelta(days=29))
```

### Client fetcher (frontend) — mirror getWorkflows
```tsx
// Source: frontend/src/lib/api.ts:316 (getWorkflows) — SAME authHeaders/request idiom
export async function getAnalyticsSummary(
  token: string, range: string
): Promise<AnalyticsSummary> {
  return request<AnalyticsSummary>(`/api/analytics/summary?range=${range}`, {
    method: "GET", headers: authHeaders(token),
  });
}
```

### Notification `gate` kind (frontend)
```tsx
// Source: frontend/src/hooks/useNotifications.ts:11 — ADD "gate"
status: "gate" | "running" | "completed" | "failed" | "cancelled";
// + markGatePaused mirrors markFailed (:78) but sets status:"gate"
// NotificationPanel.tsx:30 StatusIcon — add a gate branch (amber ramp, --color-status-gate/queued)
```

---

## Runtime State Inventory

> This phase is **additive (new endpoint + FE reskin/wiring)** — NOT a rename/refactor/migration. No stored strings are being renamed. This section is included only to explicitly discharge each category.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | **None** — reads existing `workflow_runs` rows/columns; writes nothing. Verified: no new column, no migration (Q3). | None |
| Live service config | **None** — no external service config touched. | None |
| OS-registered state | **None.** | None |
| Secrets/env vars | **None** — no new secret/env. The `MODEL_META` cost-rate table (`AnalyticsPage.tsx:20`) is display-only, in-code. | None |
| Build artifacts | **None** — no package rename, no egg-info/binary impact. | None |

---

## State of the Art

| Old (mock / pre-P32) | Current (product, this phase) | When | Impact |
|--------------|------------------|------|--------|
| Analytics = static mock snapshot | Already client-computed; this phase moves rollup server-side + reskins | Phase 38 | Backend endpoint is the net-new; FE is reskin+wire |
| Charts inline, hardcoded navy | Extracted, token-styled SVG components | Phase 38 | Reusable + CSP-safe + a11y |
| Notif kinds: running/done/failed/cancelled (2 uncalled) | + `gate` kind, all terminal transitions wired | Phase 38 | Feed becomes honest |

**Deprecated/outdated:** The retired palette (`#1B2A4A`, `#2563eb`, `#f5f5f0`, Inter, Fraunces, JetBrains) — replaced by the Phase-32 `@theme` token layer (STATE.md `32-01`).

---

## Phase-32 Token Reference (the exact vars charts/cards MUST consume)

`[VERIFIED: STATE.md 32-01-PLAN summary, L47]` — canonical vars landed in `globals.css` `@theme inline` + `:root`:
- **Brand (one-chroma):** `--color-brand` `#3C2CDA`, `--color-brand-pressed` `#3324C4`, `--color-brand-fill` `#ECEAFC`, `#DED9F7`, `#F4F2FB`, `#8E88E8`.
- **Ink ramp:** `--color-ink-900`…`--color-ink-300` (`#15161A`…`#A0A199`).
- **Surface:** `--color-surface-paper` `#F0EEE7`, `-warm` `#F6F4EE`, `-card`/`-white` `#FCFBF7`, `-near-black` `#111114`, `-ink-black` `#0C0D12`.
- **Line:** `--color-line-border` / `-divider` (`#E6E3DB`…`#C6C3B9`).
- **Status ramp (governance/status-datum ONLY):** `--color-status-running` (blue `#3C2CDA`), `--color-status-done` (green `#1F7A4D`), `--color-status-failed` (red `#A33A32`), `--color-status-queued` (grey `#9A9B92`), gate/cancelled amber `#9A6B1E`; each with a `-fill` variant (e.g. `--status-running-fill`, used at `NotificationPanel.tsx:179`).
- **Radius:** `--radius-button` (10), `--radius-card` (14), `--radius-menu` (12). **Fonts:** `--font-sans` Manrope, `--font-serif` Heebo.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The clean design is to REPLACE client-side aggregation with a server endpoint (not supplement). POR §96 lists "analytics aggregations" as a new endpoint and §88/CONTEXT L24 says filters "RECOMPUTE against them." | Summary / Pattern 1 | If the intent is only to keep client-side compute, the backend endpoint is redundant — but the POR explicitly names the endpoint, so LOW risk. Planner/discuss should confirm the endpoint fully replaces the browser reduce. |
| A2 | Estimate time uses history-avg-duration from the new endpoint, with a manifest `estimated_duration`-sum fallback. CONTEXT L26 says "manifest step count + analytics history averages." | Pattern 3 | If the fallback must be server-computed, add an additive `estimated_duration_sec` to `WorkflowSummary` (read-only, no table). Low risk — both feeds are additive. |
| A3 | The aggregation endpoint is a COLLECTION (no `{id}`), so owner-scope = `WHERE user_id`, and "IDOR→404" applies only to any drill-down variant. | Pitfall 3 | If a per-run analytics variant is added, it MUST clone `_owner_gate_or_404`. Documented. |
| A4 | Adding `"gate"` to `PipelineNotification.status` and a `markGatePaused` transition is the intended way to surface the gate kind. | Pitfall 4 | The exact gate-pause signal in `pipelineState` should be confirmed against the review-gate wiring (`review_gate_ready`); the union-extension approach is low-risk. |

**All four assumptions are additive/reversible and low-risk.** None contradicts a locked decision.

---

## Open Questions

1. **Single endpoint vs split (`/summary` vs `/daily` + `/pipelines` + `/spend`)?**
   - What we know: `AnalyticsPage` needs KPIs, daily series, pipeline rollup, model rollup, spend, and per-type avg-duration in one render.
   - What's unclear: whether one round-trip or several is preferred.
   - Recommendation: **one `GET /api/analytics/summary?range=`** returning the full aggregate (fewer round-trips; the page renders it all together). Claude's discretion per CONTEXT.

2. **Does the Home estimate's avg-duration come from the same `/summary` payload or a lighter call?**
   - Recommendation: include a `typeAvgDurationSec: Record<string,number>` field in `/summary`; the Home page can call `/summary?range=all` once. Alternatively add `estimated_duration_sec` to `/api/workflows` for a pure-manifest estimate with no history dependency (simplest, always-available). Planner picks.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `python3.11` | backend tests | ✓ | (project runtime, no venv) | — `[VERIFIED: memory dev-runtime + backend/CLAUDE.md]` |
| `/opt/homebrew/bin/lint-imports` | import-linter 4/0 gate | ✓ | present, executable | — `[VERIFIED: ls this session]` |
| `vitest` / `tsc` | FE tests + type identity | ✓ | (in frontend/) | — |
| Postgres / Bedrock / Chromium | full pytest / live e2e | ✗ (offline) | — | **Do NOT run full pytest (hangs); mocked Playwright times out → e2e LIVE-DEFERRED to Phase 34** `[VERIFIED: memory offline-test-suite + CONTEXT L36]` |

**Missing dependencies with no fallback:** none blocking — every Phase-38 check is offline-runnable (targeted pytest + vitest + tsc + grep + lint-imports).
**Missing dependencies with fallback:** live-backend round-trip of the analytics endpoint + live notification PUSH → Phase 34.

---

## Validation Architecture

`[VERIFIED: .planning/config.json not read here — nyquist treated as enabled per default; section included]`

### Test Framework
| Property | Value |
|----------|-------|
| Backend framework | pytest (`python3.11 -m pytest`), `backend/tests/unit/` + `tests/agents/` |
| Backend config | `backend/pyproject.toml` (importlinter contracts at `[[tool.importlinter.contracts]]`) |
| Frontend framework | vitest + `tsc --noEmit` (identity), per-file grep |
| Quick run (backend) | `cd backend && python3.11 -m pytest tests/unit/test_analytics_api.py -x` |
| Quick run (frontend) | `cd frontend && npx vitest run src/components/analytics` |
| Import gate | `/opt/homebrew/bin/lint-imports` → **4 kept / 0 broken** |
| Golden gate | `python3.11 -m pytest tests/agents/test_characterization_{prototype,od_prototype,od_ppt,app_builder,prototype_revision}.py` (byte/event-identical) |

### Phase Requirements → Test Map
| Req | Behavior | Test Type | Automated Command | File Exists? |
|-----|----------|-----------|-------------------|-------------|
| SHELL-05 | Owner A's `/summary` includes only A's runs (owner isolation) | unit | `python3.11 -m pytest tests/unit/test_analytics_api.py -k owner_isolation -x` | ❌ Wave 0 |
| SHELL-05 | `/summary?range=7d` totals == recompute of seeded runs in window (recompute correctness) | unit | `python3.11 -m pytest tests/unit/test_analytics_api.py -k recompute -x` | ❌ Wave 0 |
| SHELL-05 | Malformed `token_usage` blob → empty aggregate, not 500 (DoS guard) | unit | `python3.11 -m pytest tests/unit/test_analytics_api.py -k malformed -x` | ❌ Wave 0 |
| SHELL-05 | `range=all` returns all; `range=today` returns only today (date scoping) | unit | `python3.11 -m pytest tests/unit/test_analytics_api.py -k range -x` | ❌ Wave 0 |
| SHELL-05 | Date filter change → getAnalyticsSummary called → chart re-renders with new numbers | component | `npx vitest run src/components/analytics/AnalyticsPage` | ❌ Wave 0 |
| SHELL-05 | DonutChart / BarChart render `role=img` + aria-label (a11y text alt) | component | `npx vitest run src/components/analytics/charts` | ❌ Wave 0 |
| SHELL-05 | AnalyticsPage retired-palette grep = 0 (token gate) | grep | `grep -c "#1B2A4A\|bg-gray\|bg-white\|#8AAEC8\|#2563eb\|Inter\|Fraunces" frontend/src/components/analytics/AnalyticsPage.tsx` → 0 | n/a (command) |
| SHELL-05 | Home card renders "~N agents · ~Xm" from step_count + avg (not hardcoded) | component | `npx vitest run src/components/catalog/HomeLaunchGrid` | exists (extend) |
| SHELL-05 | Notification appears for each of gate/running/done/failed transitions | component | `npx vitest run src/hooks/useNotifications` (+ DashboardLayout wiring test) | ❌ Wave 0 |
| INV-3 | 5 characterization goldens byte/event-identical | characterization | `python3.11 -m pytest tests/agents/test_characterization_*.py` | exists |
| Import gate | capabilities never import kernel/app; 4/0 | lint | `/opt/homebrew/bin/lint-imports` | exists |
| tsc identity | no new type errors vs baseline | type | `cd frontend && npx tsc --noEmit \| grep -v mockApi.ts \| grep -c error` → 0 | n/a |

### Sampling Rate
- **Per task commit:** the targeted `pytest -k` / `vitest run <dir>` for the touched surface + the per-file retired-palette grep.
- **Per wave merge:** `test_analytics_api.py` full + `vitest run src/components/analytics src/components/catalog src/hooks` + `tsc --noEmit` identity + `lint-imports`.
- **Phase gate:** the 5 goldens byte-identical + `lint-imports` 4/0 + all targeted suites green before `/gsd-verify-work`. **NEVER full pytest (hangs offline); mocked Playwright e2e → live-deferred to Phase 34.**

### Wave 0 Gaps
- [ ] `backend/tests/unit/test_analytics_api.py` — owner-isolation + recompute + malformed + range (covers SHELL-05 backend).
- [ ] `frontend/src/components/analytics/charts/DonutChart.test.tsx` + `BarChart.test.tsx` — render + a11y aria-label.
- [ ] `frontend/src/components/analytics/AnalyticsPage.test.tsx` — filter→refetch→re-render + retired-palette-absent.
- [ ] `frontend/src/hooks/useNotifications.test.tsx` — gate kind + failed/cancelled transitions (extend/new).
- [ ] Framework install: none — pytest/vitest/tsc all present.

---

## Security Domain

`[VERIFIED: security_enforcement not disabled → included]`

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V4 Access Control | **yes** | Owner-scope every query by `WorkflowRun.user_id == current_user.id` (`runs.py:250` collection / `:1206` `{id}` gate). NEVER the nullable `owner_id`. Cross-owner data must never enter the aggregate. |
| V5 Input Validation | yes | `range` param is an allow-listed enum (`_cutoff_for` `.get(range, default)`); any drill-down `{id}` is owner-gated (path-traversal/IDOR moot — it's a DB id filter, not a filesystem path). |
| V7/Leak (data exposure) | yes | The aggregate returns numbers only (counts/tokens/cost/durations) — NEVER raw agent output/prompts (the `_SUMMARY_SAFE_AGENT_KEYS` posture, `runs.py:995`). Do not echo `input`/`output`/`agent_outputs` bodies. |
| V6 Cryptography | no | No crypto surface. |
| V2/V3 Auth/Session | inherited | `Depends(get_current_user)` (JWT) on every endpoint — same as all `/api/runs`. |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Cross-owner analytics leak | Information disclosure | `WHERE user_id == current_user.id` on the aggregation query; owner-isolation test seeds two users. |
| Malformed `token_usage` JSON → 500 (DoS) | Denial of service | `json.loads` in try/except → `{}` fallback (`runs.py:1116–1123`). |
| Unbounded scan (`range=all`, huge history) | DoS | Aggregation is over the caller's OWN runs only; the existing `getWorkflows(limit:500)` shows the working set is bounded. Consider a server-side cap if a user can amass >N runs (LOW risk this milestone). |
| Workflow-name branch leaking SC-001 | Tampering/design | Key on generic `type`/`status`; `PIPELINE_LABELS` is display-only. |

---

## Sources

### Primary (HIGH — verified in codebase this session)
- `backend/app/api/runs.py` — `list_runs:236/250` (collection owner-scope), `_owner_gate_or_404:1206`, `get_run_summary:1080` + try/except JSON `:1116–1123`, `RunSummaryResponse:1010`, `_SUMMARY_SAFE_AGENT_KEYS:995`.
- `backend/app/models/workflow.py` — `WorkflowRun` columns: `type:22`, `status:23`, `duration:34`, `token_usage:36` (JSON Text), `model_id:37`, `created_at:38`, `user_id:20`, backfilled `owner_id:58`.
- `backend/app/api/workflows.py` — `WorkflowSummary.step_count:78`, `list_workflows:171`, `_spec_by_id:146` (the estimate agent-count source).
- `frontend/src/components/analytics/AnalyticsPage.tsx` — client-side aggregation `:195–299`, `BarChart:96`, SVG donut `:432–444`, cutoff table `:212–219`, retired palette (100 grep hits).
- `frontend/src/components/ui/NotificationPanel.tsx` — Phase-35 chrome (`role=menu:103`, StatusIcon`:30`, Badge`:196`, status-fill token `:179`, a11y `:81/87–89`).
- `frontend/src/hooks/useNotifications.ts` — `PipelineNotification.status:11` (no `gate`), transitions `:41–108`.
- `frontend/src/components/layout/DashboardLayout.tsx` — `useNotifications` wiring `:361–369`, only `markCompleted:456` fires, generic terminal markers `:1314`.
- `frontend/src/lib/api.ts` — `getWorkflows:316`, `WorkflowSummary.step_count:681`.
- `frontend/src/types/index.ts` — `WorkflowRun.tokenUsage:326–339`.
- `backend/tests/agents/test_characterization_*.py` — the 5 goldens (`prototype`, `od_prototype`, `od_ppt`, `app_builder`, `prototype_revision`).
- `backend/CLAUDE.md` — AGENT.md `estimated_duration` field (estimate fallback source); `PIPELINE_AGENTS` membership.
- `.planning/CHAT-AND-UI-CONVERGENCE-PLAN.md` §88 (Phase-38 brief), §96 (endpoint contract), §3 LOCK-B/-E.
- `.planning/v2.0-evidence/12-coverage-and-backend-map.md` §Part-2 Category-A (date-scoped analytics rollups), §Part-2 (`step_count`/token/cost already exist).
- `.planning/v2.0-evidence/02-workspace-shell-teardown.md` §2.7 Analytics, §2.1 Home cards, §4/§5 mock-fiction.
- `.planning/STATE.md` — Phase-32 token vars (32-01 summary), Phase-35 NotificationPanel reskin (35-01), Phase-36 owner-scoped summary endpoint (36-02 as the analytics endpoint template).

### Secondary (MEDIUM — inference from verified sources)
- Endpoint URL/shape (`/api/analytics/summary?range=`) — inferred from POR §96 + the `list_runs` idiom; exact shape is Claude's discretion.

### Tertiary (LOW)
- None — no WebSearch used; this is a codebase-internal phase.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new deps; every reused module verified at file:line.
- Architecture: HIGH — the endpoint is a near-clone of `get_run_summary`; charts already exist inline.
- Pitfalls: HIGH — each pitfall (static-mock trap, uncalled markFailed, missing gate kind, retired palette) verified directly this session.
- Estimates source: MEDIUM — `step_count` verified; `estimated_duration` is AGENT.md-only (not on `WorkflowSummary`), so the manifest-sum fallback needs an additive field OR pure history-average (A2).

**Research date:** 2026-07-10
**Valid until:** 2026-08-09 (stable brownfield; refresh if the token layer or `WorkflowRun` schema changes)
