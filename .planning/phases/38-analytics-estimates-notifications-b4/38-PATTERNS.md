# Phase 38: Analytics, Estimates & Notifications [B4] - Pattern Map

**Mapped:** 2026-07-10
**Files analyzed:** 6 mandatory mappings (2 new BE modules + 4 modified FE surfaces + 2 new FE chart components)
**Analogs found:** 6 / 6 (all anchored to real code)

Additive READ-only over existing run data. NO new tables (Q3). Owner-scoped `user_id`-keyed (IDOR→404, never `owner_id`). Charts self-contained SVG consuming Phase-32 `@theme` tokens.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/app/api/analytics.py` (NEW) | route/controller | request-response (aggregation read) | `backend/app/api/runs.py::get_run_summary` (:1080) + `_owner_gate_or_404` (:1206) | exact (role + owner-scope idiom) |
| aggregation helper (in analytics.py, over `WorkflowRun`) | service/query | batch/transform (read+aggregate) | `run_commands.py` token_usage persistence (:1272) + `model_pricing.estimate_cost_usd` (:116) | role-match (reads the same JSON blob) |
| `frontend/src/components/analytics/AnalyticsPage.tsx` (MODIFY) | component | CRUD-read → recompute | itself (client-agg today) → rewire to new endpoint | exact (same surface) |
| `frontend/src/components/ui/DonutChart.tsx` + `BarChart.tsx` (NEW) | component | transform (data→SVG) | `AnalyticsPage.tsx` inline `BarChart` (:96) + SVG donut (:432) | exact (extract + tokenize) |
| `frontend/src/components/ui/NotificationPanel.tsx` + `hooks/useNotifications.ts` (MODIFY) | component + store/hook | event-driven feed | itself (in-memory session store) | exact (add `gate` kind + owner-scoped source) |
| `frontend/src/components/catalog/HomeLaunchGrid.tsx` (MODIFY) | component | request-response (list) | itself (fetch shell :68) | exact (add estimate line) |

---

## Pattern Assignments

### MAPPING 1 — Existing run/token/cost data to aggregate

**Data source (READ, do NOT invent fields):** `backend/app/models/workflow.py::WorkflowRun` (:13).

**Exact columns the aggregation endpoints read:**
| Field | Line | Type | Notes |
|-------|------|------|-------|
| `id` | :19 | String PK (uuid) | run id |
| `user_id` | :20 | String FK → users.id, **NOT NULL** | THE owner-scope key (never the nullable `owner_id` :58) |
| `type` | :22 | String | pipeline/deliverable type: `user_stories`\|`ppt`\|`prototype` (+ `od_*`, `app_builder`, `_revision`, `custom`) |
| `status` | :23 | String | `completed`\|`failed`\|`cancelled`\|`running`\|`degraded`\|… |
| `agent_count` | :33 | Integer | per-run agent count |
| `duration` | :34 | Float (seconds) | total execution time |
| `token_usage` | :36 | Text (JSON string) | the cost/token blob — see shape below |
| `model_id` | :37 | String nullable | model used |
| `created_at` | :38 | DateTime (UTC), NOT NULL | date-scope bucketing key |
| `completed_at` | :41 | DateTime nullable | finished timestamp |

**`token_usage` JSON shape** — persisted at `backend/app/api/run_commands.py:1277-1291` (this is the ONLY writer):
```python
wr.token_usage = json.dumps({
    "total_input_tokens": total_input,
    "total_output_tokens": total_output,
    "total_tokens": total_input + total_output,
    "total_cache_read_tokens": total_cache_read,
    "total_cache_write_tokens": total_cache_write,
    "estimated_cost_usd": estimate_cost_usd(...),   # agents/capabilities/model_pricing.py:116
})
```
`estimated_cost_usd` is the single shared cost fn (`model_pricing.py:116`) — reuse it, do NOT re-derive cost. Tolerant-parse the blob inside `try/except` with a `{}` fallback (the established idiom at `runs.py:1116-1123`) — a malformed blob must degrade to an empty aggregate, never a 500.

**DELTA:** NEW endpoint(s) group these existing rows by `date(created_at)` (daily series), by normalized `type` (per-pipeline rollup), by `model_id` (per-model rollup), summing `token_usage.*` and `estimated_cost_usd` for spend. Zero new columns, zero migrations.

---

### MAPPING 2 — Owner-scoped read-endpoint analog (P13/P25) → CLONE for analytics

**Analog:** `backend/app/api/runs.py::_owner_gate_or_404` (:1206) + its consumer `get_run_summary` (:1080). Auth dependency = `current_user: User = Depends(get_current_user)` (from `app.core.dependencies`, :31); DB = `db: Session = Depends(get_db)`.

**The idiom to clone (runs.py:1213-1223):**
```python
workflow_run = (
    db.query(WorkflowRun)
    .filter(WorkflowRun.id == workflow_id, WorkflowRun.user_id == user_id)  # user_id, NOT owner_id
    .first()
)
if not workflow_run:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow run not found")
```
Confirmed: the whole runs.py surface filters on `WorkflowRun.user_id == current_user.id` (module docstring :16-17; every endpoint :250/:398/:431/:676/:824/:874/:1215). The nullable backfilled `owner_id` (:58) is NEVER the gate. IDOR → 404, never 403, never a 200 with another owner's rows.

**For a LIST/date-scoped aggregation** (no single `{id}`), the base-query analog is `list_runs` (:250):
```python
query = db.query(WorkflowRun).filter(WorkflowRun.user_id == current_user.id)
```
Add `.filter(WorkflowRun.created_at >= cutoff)` for the date scope. Register the new router in `backend/app/main.py` beside `app.include_router(runs_router)` (:175).

**DELTA:** new `analytics.py` router; each aggregation endpoint opens with the `user_id`-scoped base query, returns rolled-up numbers. Tests: owner 200 / cross-owner 404 / recompute-correctness (per CONTEXT.md verify list).

---

### MAPPING 3 — The dashboard analytics view (SC-1 rewire)

**File:** `frontend/src/components/analytics/AnalyticsPage.tsx` (683 lines).

**Current data source:** client-side aggregation — `getWorkflows(token, { limit: 500 })` (:200) pulls up to 500 raw runs; ALL rollups (`tokenStats` :249, `pipelineBreakdown` :265, `dailyUsage` :282, `successRate` :262) are recomputed in `useMemo` on the client. Date filters live at `dateFilter` state (:190) with the pill row at :324-333; pipeline/model selects at :335-355. So unlike the *mock* (POR §9 "date filters recompute nothing"), THIS product component already recomputes client-side — but by shipping ≤500 runs to the browser.

**DELTA (SC-1):** replace the `getWorkflows(limit:500)` + client `useMemo` rollups with fetches to the new date-scoped aggregation endpoints (Mapping 1/2); the `setDateFilter`/`setPipelineFilter`/`setModelFilter` handlers refetch (server recompute) instead of re-filtering an in-memory array. The KPI tiles, Daily Activity bars, Success donut, By-Pipeline bars, Token Breakdown, Model Details, and spend chip bind to the endpoint response shape.

**RETIRED-PALETTE FLAG (token gate — this file is the worst offender in-phase):** `AnalyticsPage.tsx` is saturated with retired hex `#1B2A4A` (:55,:65,:96,:173,:336,:396,:408,:436,:582,:595,:670-672…), `#8AAEC8`/`#2E4A7A`/`#3D6B9E`/`#5B8DB8` navy-family bars (:54-61), `#E8EDF5`/`#F4F5F7` fills (:172,:307,:670), and Tailwind `gray-*`/`bg-white` throughout. The `PIPELINE_PALETTE` map (:54-62) hardcodes a navy ramp. All must go to Phase-32 tokens (see Shared Patterns). Per CONTEXT §30 the governance status-palette exception does NOT apply — one-chroma (`brand #3C2CDA` / `--status-*`) unless a datum is a run-status.

---

### MAPPING 4 — Phase-35 NotificationPanel → live feed

**File:** `frontend/src/components/ui/NotificationPanel.tsx` (chrome, token-clean already) + its data hook `frontend/src/hooks/useNotifications.ts`.

**Props/shape:** `NotificationPanelProps` (:11-18): `notifications: PipelineNotification[]`, `unreadCount`, `onMarkAllRead`, `onClearAll`, `onGoToPipeline`, `onViewResults`. Item type `PipelineNotification` (useNotifications.ts:6-17): `{ id, workflowRunId?, workflowType, title, status: "running"|"completed"|"failed"|"cancelled", agentsCompleted?, agentsTotal?, createdAt, completedAt?, read }`.

**How an item renders (NotificationPanel.tsx:146-217):** `StatusIcon` (:30) maps status → `text-status-running`/`-done`/`-failed`/`-queued` token icon; running rows show an agent-progress bar (`bg-status-running` :181, `--status-running-fill` :179); each row ends with `<Badge status={n.status} />` (:196, the token primitive) + a "View progress/results" `text-brand` CTA (:202/:209).

**Feed source today:** `useNotifications` is an **in-memory session store** — `useState<PipelineNotification[]>` (:39), mutated by live-run callbacks (`addRunningNotification` :41, `markCompleted` :69, `markFailed` :78, `markCancelled` :87). No persistence, no fetch-on-load, and **no `gate` kind**.

**DELTA:** wire to a LIVE feed with kinds **gate/running/done/failed** sourced from existing run-state, owner-scoped:
- Add `"gate"` (review-gate paused) to the `status` union (useNotifications.ts:11) and a `StatusIcon`/`Badge` branch — the Phase-32 token for gate/review already exists: `--status-amber` (globals.css:103 "cancelled + gate/review"). Map `completed`→Badge `done`.
- Source items from persisted run-state (owner-scoped `user_id` list, e.g. reuse the runs list / a lightweight feed derived from `WorkflowRun.status`) so the feed survives reload — not only session events. Live PUSH over the real connection is DEFERRED to Phase 34 (CONTEXT deferred).

---

### MAPPING 5 — Phase-36 HomeLaunchGrid deliverable cards → estimates

**File:** `frontend/src/components/catalog/HomeLaunchGrid.tsx` (renamed from `WorkflowCatalog`, D-11; token-clean).

**Card structure (:184-231):** one `<button>` row per workflow from the live fetch — `label` = `row.display_name ?? getWorkflowLabel(row.id)` (:172, NEVER raw `name`), `subtitle` = `row.description` (:173), tier lock decoration (`canRunPipeline` :174), trailing `ArrowRight`, sibling Info inspect button (:224). Rows come from `getWorkflowDefinitions(jwt)` filtered by `w.user_launchable` (:80, GATE 1).

**Manifest-step-count source (already on the wire):** `WorkflowSummary` (api.ts:677-684) carries `step_count: number` (:681) and `agent_count: number` (:261/:393). The BE populates them at `backend/app/api/workflows.py:227` `step_count=len(compiled.steps)` and `agent_count` — derived from the compiled manifest steps. So the "~N agents" half of the estimate is a field that already exists; NO invention.

**DELTA:** add an estimate line to each row (near `subtitle` :200) reading `row.step_count`/`agent_count` for the agent count, and derive the time estimate from **manifest step count + analytics history averages** (real data, not the mock's hardcoded "~24m/5 agents"). Time-per-run history comes from Mapping-1 aggregations (avg `duration` per `type`). Consume Phase-32 tokens (`text-ink-500`, no new hex).

---

### MAPPING 6 — Chart component analog + Phase-32 tokens

**Closest existing self-contained SVG primitives to model on:** the inline chart code ALREADY in `AnalyticsPage.tsx` — the `BarChart` fn (:96-130, flex bars + motion height animation + hover tooltip) and the SVG **donut** (:432-448, two `<circle>` + `strokeDasharray`/`strokeDashoffset` + `motion.circle` sweep). These are self-contained (no lib) but hardcode `#1B2A4A`. The `components/ui/` primitive set to sit beside: `Badge.tsx`, `Card.tsx`, `Pill.tsx`, `Button.tsx` (all token-only, no raw hex).

**Bar excerpt to extract + tokenize (AnalyticsPage.tsx:113-120):**
```tsx
<motion.div
  initial={{ height: 0 }}
  animate={{ height: `${Math.max(pct, ...)}%` }}
  className="w-full rounded-t-[3px] cursor-pointer"
  style={{ background: color, opacity: ... }}   // color="#1B2A4A" today → var(--brand)
/>
```
**Donut excerpt (AnalyticsPage.tsx:434-443):**
```tsx
<motion.circle cx="44" cy="44" r="36" fill="none"
  stroke="#1B2A4A"   // → var(--brand) / var(--status-*) when a datum is a run-status
  strokeWidth="10" strokeLinecap="round"
  strokeDasharray={`${2 * Math.PI * 36}`}
  animate={{ strokeDashoffset: 2 * Math.PI * 36 * (1 - successRate / 100) }}
  transform="rotate(-90 44 44)" />
```

**NO external chart library** — confirmed: `package.json` has zero of chart/recharts/d3/victory/nivo/visx. Charts MUST stay self-contained SVG (CSP-safe).

**Exact Phase-32 `@theme` tokens charts/cards MUST consume** (`frontend/src/styles/globals.css`, `@theme inline` :12 + `:root` :61+):
- Brand one-chroma: `--brand: #3C2CDA` (:61) → utility `text-brand` / `bg-brand` / `var(--brand)`; fills `--brand-fill #ECEAFC` (:63), `--brand-border #DED9F7` (:64).
- Fonts: `--font-sans: var(--font-manrope)` (:14, headings/numbers) · `--font-serif: var(--font-heebo)` (:15, italic display). (Manrope/Heebo — matches CONTEXT.)
- Ink ramp: `--ink-900 #15161A` … `--ink-400 #8A8B82` (:69-76) → `text-ink-*`.
- Surfaces: `--surface-paper #F0EEE7` (:79), `--surface-warm #F6F4EE` (:80), `--surface-card #FCFBF7` (:81), `--surface-white` (:82).
- Lines: `--line-border #E6E3DB` (:87), `--line-divider #E2DFD6` (:88).
- Status ramp (ONLY when a datum IS a run-status — success/fail donut segments, feed kinds): `--status-running #3C2CDA` (:94), `--status-done #1F7A4D` (:97), `--status-failed #A33A32` (:100), `--status-amber #9A6B1E` (:103, gate/review + cancelled), `--status-queued #9A9B92` (:106), each with `-fill`/`-border` siblings.
- Radii: `--radius-card 14px` (:122), `--radius-tag 5px` (:117), `--radius-menu 12px` (:121).

**DELTA:** extract `DonutChart.tsx` + `BarChart.tsx` into `components/ui/` (or `components/ui/charts/`), parametrized + token-styled (`var(--brand)` base, `--status-*` only for status data), a11y-labelled (CONTEXT: charts need text alternatives). AnalyticsPage imports them instead of its inline copies (delete the inline versions — INV-3/no-dual-impl).

---

## Shared Patterns

### Owner-scope gate (BE)
**Source:** `backend/app/api/runs.py::_owner_gate_or_404` (:1206) / `list_runs` base query (:250).
**Apply to:** every new analytics aggregation endpoint. `.filter(WorkflowRun.user_id == current_user.id)` — the principal, NEVER `owner_id`. Missing/cross-owner → `HTTPException(404)`.

### Cost derivation (BE)
**Source:** `backend/agents/capabilities/model_pricing.py::estimate_cost_usd` (:116) — the single shared cost fn used by both the engine event and the persisted `token_usage`. Reuse it; do not re-derive spend.

### Tolerant JSON parse (BE)
**Source:** `runs.py:1116-1123` — parse `token_usage` inside `try/except` with `{}` fallback so a malformed blob degrades to an empty aggregate, never a 500.

### Token consumption + Badge (FE)
**Source:** `frontend/src/components/ui/Badge.tsx` (status→`--status-*` token classes, generic `status` prop, no raw hex) + `globals.css` `@theme` (:12). Every new/modified FE surface uses these utilities; per-file retired-palette grep must be 0.

### Fetch-shell idiom (FE)
**Source:** `HomeLaunchGrid.tsx:68-93` — mount `useEffect` with `cancelled` guard + `getToken()` fallback + loading/error/finally triad. The AnalyticsPage rewire and any new fetch follow this shape.

---

## Retired-palette flags (token gate = 0 required)

| File this phase touches | Retired tokens present | Action |
|---|---|---|
| `analytics/AnalyticsPage.tsx` | `#1B2A4A` (pervasive), `#8AAEC8`/`#2E4A7A`/`#3D6B9E`/`#5B8DB8` (navy ramp :54-61), `#E8EDF5`/`#F4F5F7`/`#E8EDF5` fills, `bg-white`/`gray-*` Tailwind | Rewire ALL → Phase-32 tokens (Mapping 6 list) |
| new `ui/DonutChart.tsx` + `BarChart.tsx` | (inherit `#1B2A4A` if copied verbatim from AnalyticsPage) | Tokenize on extraction — `var(--brand)` / `--status-*` |
| `ui/NotificationPanel.tsx` | none (already token-clean) | add `gate` kind via `--status-amber` |
| `catalog/HomeLaunchGrid.tsx` | none (already token-clean) | estimate line in `text-ink-*` |
| `hooks/useNotifications.ts` | n/a (logic only) | add `"gate"` to status union |

Retired set to keep at 0 per file: `#1B2A4A` · `#2563eb` · `#f5f5f0` · `Inter` · `Fraunces` · `JetBrains`. (`#2563eb`/`#f5f5f0`/Inter/Fraunces/JetBrains — none found in the touched files; `#1B2A4A` is confined to `AnalyticsPage.tsx` + whatever the charts copy from it.)

---

## No Analog Found / NOT FOUND

- **Analytics aggregation endpoint** — NOT FOUND in `backend/app/api/` (confirmed no `analytics` route). This is genuinely NEW code — model it on the `runs.py` summary/list owner-scoped read pattern (Mapping 2). This is expected (POR Category-A: "date-scoped analytics rollups — Phase 38, over P26 telemetry").
- **Notifications persistence/derivation source** — the feed logic exists in-memory (`useNotifications`), but a persisted/owner-scoped notification SOURCE is not built (POR Category-B: "Notifications feed store or derivation (Phase 38)"). CONTEXT locks: derive from EXISTING run-state, NO new table. So the source is a derivation over `WorkflowRun.status`, not a new store.

## Metadata

**Analog search scope:** `backend/app/api/` (runs.py, run_commands.py, workflows.py, main.py), `backend/app/models/`, `backend/agents/capabilities/model_pricing.py`, `frontend/src/components/{analytics,ui,catalog}`, `frontend/src/hooks`, `frontend/src/lib/api.ts`, `frontend/src/styles/globals.css`, `frontend/package.json`.
**Pattern extraction date:** 2026-07-10
