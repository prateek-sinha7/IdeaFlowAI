---
phase: 20-workflow-catalog-data-driven-browse-and-launch-gallery-reali
plan: 02
subsystem: ui
tags: [workflow-catalog, react, nextjs, playwright, vitest, entitlements, sc-001, reuse-mandate]

# Dependency graph
requires:
  - phase: 20-01
    provides: "GET /api/workflows user_launchable + display_name/icon/launch_surface (WorkflowSummary fields the FE consumes)"
provides:
  - "frontend getWorkflowDefinitions(token) fetcher + WorkflowSummary type (api.ts) — analog getCapabilities"
  - "WorkflowCatalog.tsx — data-driven CreationHub (two-analog graft: AgentModelPicker fetch shell + CreationHub rows/launch/gating); two-gate filter (user_launchable ∧ canRunPipeline), friendly labels, no hardcoded WORKFLOWS const (SC-001)"
  - "'catalog' in-dashboard view (DashboardLayout MainView + view block + handleNavigate + headerPage) and the Catalog nav button (AppHeader)"
  - "ts-z.catalog.spec.ts mocked Playwright + WorkflowCatalog.test.tsx vitest — two-gate filter proven at two levels"
affects: [workflow-catalog-followups, library-page-merge, catalog-search-categories]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Two-analog component graft: AgentModelPicker fetch/loading/error/empty triad + CreationHub row JSX/launch/gating, verbatim classes (net-new styling is a defect)"
    - "Data-driven palette via a declared per-row flag (user_launchable) — never a hardcoded workflow-name array (SC-001)"
    - "Per-spec page.route('**/api/workflows*') registered AFTER dashboard.goto() to win over the fixtures' **/api/** catch-all by Playwright reverse-registration precedence (no fixture edit)"

key-files:
  created:
    - "frontend/src/components/catalog/WorkflowCatalog.tsx"
    - "frontend/src/components/catalog/WorkflowCatalog.test.tsx"
    - "frontend/e2e/tests/ts-z.catalog.spec.ts"
  modified:
    - "frontend/src/lib/api.ts"
    - "frontend/src/components/layout/DashboardLayout.tsx"
    - "frontend/src/components/layout/AppHeader.tsx"

key-decisions:
  - "Friendly label sourced via the EXPORTED getWorkflowLabel(id) helper (useNotifications) — WORKFLOW_LABELS itself is module-private; TYPE_META (WorkflowHistory) is private too, so the row uses no leading icon (CreationHub rows have none either). Fallback is display_name ?? getWorkflowLabel(id), never the raw API name."
  - "Verify commands adapted: the plan cited `npm run -s typecheck` but no `typecheck` script exists — used `npx tsc --noEmit` (tsconfig has noEmit:true). vitest is `npx vitest --run src/`."
  - "e2e transition hardening: under AnimatePresence mode='wait' the exiting home CreationHub briefly co-renders with the entering catalog, so assertions pin the catalog's exact 2-row count before asserting gating (the only fix beyond the plan's literal text-assertions)."

patterns-established:
  - "Data-driven CreationHub: rows from getWorkflowDefinitions, two-gate filtered (user_launchable ∧ canRunPipeline), gated rows shown-locked not hidden, launch via CHAIN_OPTIONS wizard fork + onSelectFeature."
  - "Reverse-registration page.route override of a fixture catch-all (no fixture edit) — the canonical way to mock a new endpoint per-spec."

requirements-completed: [REUSE-MANDATE, SC-001, INV-3, ADDITIVE-ONLY]

# Metrics
duration: ~9min
completed: 2026-06-14
---

# Phase 20 Plan 02: Workflow Catalog Data-Driven Frontend Summary

**A data-driven in-dashboard Catalog view that fetches the live `GET /api/workflows` list and renders a CreationHub-styled, two-gate-filtered (`user_launchable` ∧ `canRunPipeline`) gallery with zero hardcoded workflow-name array (SC-001) — reusing the CreationHub rows + AgentModelPicker fetch shell + DashboardLayout home block + AppHeader Library button verbatim, with the launch reaching the existing run/wizard paths.**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-06-14T09:33:03Z
- **Completed:** 2026-06-14T09:41:28Z
- **Tasks:** 3
- **Files modified:** 6 (3 created, 3 modified)

## Accomplishments
- `getWorkflowDefinitions(token)` + `WorkflowSummary` type in api.ts (copied from `getCapabilities`; path `/api/workflows`; `getWorkflows` run-history fetcher untouched).
- `WorkflowCatalog.tsx` — a two-analog graft: AgentModelPicker mount-effect + loading/error/empty triad, CreationHub row `<button>` + per-row lock/"Requires {tier} plan" decoration verbatim, gate 1 `user_launchable` fetch filter + gate 2 `canRunPipeline`, friendly label (`display_name ?? getWorkflowLabel(id)` — never the raw `name`), CHAIN_OPTIONS wizard fork. The `WORKFLOWS` module-const is GONE (rows come from the live fetch — SC-001).
- `'catalog'` wired end-to-end: DashboardLayout MainView union + a `key="catalog"` view block (copy of the HOME block) mounting WorkflowCatalog via the existing `handleSelectFeature`, `handleNavigate` union + `headerPage` mapping; AppHeader `LayoutGrid` import + `'catalog'` on both closed unions + a Catalog nav button (copy of the Library button).
- Two-gate filter proven at two levels: a deterministic `WorkflowCatalog.test.tsx` vitest (non-launchable hidden, gated shown-locked, `*_revision`/`od_*` never rendered, friendly-label fallback) AND a mocked `ts-z.catalog.spec.ts` Playwright spec (filter + a launch reaching IdeaInputPage; enterprise tier un-gates app_builder).

## Task Commits

Each task was committed atomically:

1. **Task 1: getWorkflowDefinitions + WorkflowSummary + WorkflowCatalog.tsx + two-gate vitest** - `c96173d0` (feat) — TDD: failing test written first (RED, module-missing), then the fetcher + component (GREEN); committed together as the task is atomic.
2. **Task 2: wire 'catalog' view into DashboardLayout + Catalog nav button into AppHeader** - `e5a4b419` (feat)
3. **Task 3: mocked Playwright catalog spec** - `ce62d96f` (test)

**Plan metadata:** (this docs commit)

## Files Created/Modified
- `frontend/src/lib/api.ts` - Added `getWorkflowDefinitions(token)` fetcher + `WorkflowSummary` interface (mirrors the BE 20-01 shape).
- `frontend/src/components/catalog/WorkflowCatalog.tsx` - Data-driven CreationHub (two-analog graft); two-gate filter; friendly labels; existing launch fork.
- `frontend/src/components/catalog/WorkflowCatalog.test.tsx` - Vitest pinning the two-gate filter + friendly-label fallback (mocked `@/lib/api`).
- `frontend/src/components/layout/DashboardLayout.tsx` - `'catalog'` MainView member, WorkflowCatalog import + view block, handleNavigate union, headerPage mapping.
- `frontend/src/components/layout/AppHeader.tsx` - `LayoutGrid` import, `'catalog'` on both unions, Catalog nav button.
- `frontend/e2e/tests/ts-z.catalog.spec.ts` - Mocked Playwright: filter + launch + tier parametrization via a per-spec `/api/workflows` route that wins over the fixture catch-all.

## Verification Evidence
- `npx tsc --noEmit` → CLEAN across all 6 files (the only remaining errors are pre-existing TS2352 readonly-cast errors in `e2e/fixtures/mockApi.ts`, a fixture forbidden to edit — logged to `deferred-items.md`).
- `npx vitest --run src/` → **118 passed (15 files)**, including the new `WorkflowCatalog.test.tsx`.
- `npx playwright test --project=mocked --workers=1 --reporter=line e2e/tests/ts-z.catalog.spec.ts` → **3 passed** (no `test.fixme` on the load-bearing assertions).
- SC-001 grep: `grep -c "const WORKFLOWS" WorkflowCatalog.tsx` → **0** (no hardcoded array); `filter((w) => w.user_launchable)` present.
- `git status frontend/e2e/fixtures/` → clean (no fixture modified); `frontend/src/app/catalog/page.tsx` → absent (no new Next route — it is an in-dashboard view).

## Decisions Made
- Friendly label via the **exported** `getWorkflowLabel(id)` (useNotifications) — `WORKFLOW_LABELS`/`TYPE_META` are both module-private, so importing them was not possible without editing analogs; `getWorkflowLabel` returns the WORKFLOW_LABELS value or the raw id as a deterministic fallback, satisfying the "friendly label, never raw `name`" rule. Rows carry no leading icon (CreationHub rows don't either).
- Used `npx tsc --noEmit` for the typecheck (the plan's `npm run -s typecheck` script does not exist in package.json; tsconfig already sets `noEmit:true`).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] e2e assertions hardened for the view transition**
- **Found during:** Task 3 (mocked Playwright spec)
- **Issue:** Under `AnimatePresence mode="wait"`, the exiting home CreationHub (6 rows, 2 of them tier-gated) briefly co-renders with the entering catalog, so a bare `getByText(/Requires Pro plan/i).toBeVisible()` hit a strict-mode violation (2 matches) and the catalog's single gated row could not be asserted reliably.
- **Fix:** Pin the catalog's exact launchable-row count (`getByRole("button").filter({ has: heading level 2 })` → `toHaveCount(2)`) before the gating assertions, and assert `toHaveCount(1)` on the "Requires Pro plan" affordance + that home-only labels ("Pitch an idea"/"Platform workflows") are absent. No production code changed; the catalog itself renders exactly one locked row.
- **Files modified:** frontend/e2e/tests/ts-z.catalog.spec.ts
- **Verification:** `ts-z.catalog.spec.ts` → 3 passed.
- **Committed in:** ce62d96f (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking — test-only transition hardening).
**Impact on plan:** Test-robustness only; no production-code or scope change. The two-gate/launch assertions remain fully mockable and are NOT `test.fixme`.

## Issues Encountered
- A transient `git stash push -- src/lib/api.ts` (used to confirm the pre-existing mockApi tsc errors are independent of my change) briefly reverted the api.ts edit; immediately restored via `git stash pop`. The api.ts change is intact and committed in `c96173d0`.

## Known Stubs
None — the catalog is wired end-to-end (manifest YAML → 20-01 API → `getWorkflowDefinitions` → two-gate render → existing launch). The empty-state copy ("No workflows available for your plan yet.") is a real loading-triad branch, not a stub.

## Threat Flags
None — no new network endpoint, auth path, or trust boundary. The catalog is a read-only consumer of the existing authenticated `GET /api/workflows`; launches cross the EXISTING tier-gated `run_pipeline`/wizard boundaries. Rows render as auto-escaped React text (no `dangerouslySetInnerHTML`); no new npm dependency. Consistent with the plan's `<threat_model>` (T-20-05..T-20-SC).

## Next Phase Readiness
- The data-driven catalog is live and reuse-pure; a brand-new manifest setting `user_launchable: true` appears with zero FE edit (SC-001). The catalog ships as the simple data-driven CreationHub list (not the richer LibraryPage search/category page) per the CONTEXT discretion — a future plan can merge/extend if desired.
- Pre-existing `e2e/fixtures/mockApi.ts` TS2352 readonly-cast errors remain (out of scope, fixture-forbidden) — logged in `deferred-items.md` for a future fixture-owning pass.

## Self-Check: PASSED

All created files exist on disk (WorkflowCatalog.tsx, WorkflowCatalog.test.tsx, ts-z.catalog.spec.ts, 20-02-SUMMARY.md) and all three task commits (c96173d0, e5a4b419, ce62d96f) are present in git history.

---
*Phase: 20-workflow-catalog-data-driven-browse-and-launch-gallery-reali*
*Completed: 2026-06-14*
