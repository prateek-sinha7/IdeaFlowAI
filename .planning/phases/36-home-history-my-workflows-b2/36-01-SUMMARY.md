---
phase: 36-home-history-my-workflows-b2
plan: 01
subsystem: ui
tags: [react, nextjs, typescript, vitest, tokens, motion, home-launcher, rename]

# Dependency graph
requires:
  - phase: 32-run-screen-token-layer
    provides: "@theme Phase-32 token layer (brand/ink/surface/line/status ramps, font-serif=Heebo)"
  - phase: 35-shell-chrome-reskin-pages-b1
    provides: "nav label 'My Workflows' + saved-workflows page key; D-11 rename deferred to Phase 36"
provides:
  - "HomeLaunchGrid component (renamed from WorkflowCatalog) — the data-driven home launch grid, on Phase-32 tokens"
  - "Fused Home landing: prompt launcher + deliverable grid + recents strip in one view"
  - "grep -rc WorkflowCatalog frontend/src == 0 (D-11 rename complete, all 7 callers repointed)"
affects: [36-02, 36-03, 36-04, 36-05, home, my-workflows, run-detail]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Grep-all-callers component rename with git mv + both vi.mock module-path repoints in lockstep (the trap)"
    - "Fused view-state landing: launcher brief carried into the input view via a pending-brief pass-through (SC-001, generic page-keys)"
    - "D-15 reskin: retired literals -> @theme token classes; status-failed light fill via bg-[var(--status-failed-fill)]"

key-files:
  created: []
  modified:
    - "frontend/src/components/catalog/HomeLaunchGrid.tsx (renamed from WorkflowCatalog.tsx; reskinned to tokens)"
    - "frontend/src/components/catalog/HomeLaunchGrid.test.tsx (renamed from WorkflowCatalog.test.tsx)"
    - "frontend/src/components/layout/DashboardLayout.tsx (repointed import; fused Home view)"
    - "frontend/src/components/layout/DashboardLayout.catalogHome.test.tsx (vi.mock path + stub key)"
    - "frontend/src/components/layout/DashboardLayout.waveMount.test.tsx (vi.mock path + stub key)"
    - "frontend/src/components/savedworkflows/SavedWorkflowsPage.tsx (comment)"
    - "frontend/src/lib/api.ts (2 comments)"

key-decisions:
  - "Kept the component in catalog/ (dev-facing path, not a user label) — minimizes mock-path churn; D-11 'Catalogue reserved' is about user-facing labels only"
  - "Fused-home launcher captures a brief but the deliverable grid remains the launch action; the typed brief rides into the input view via pendingHomeBrief -> initialInput (generic path only), keeping HomeLaunchGrid's API and tests untouched"
  - "Did NOT delete the 5 pre-existing 'Your workflows' dead tests (functionality moved to SavedWorkflowsPage); logged to deferred-items.md per CLAUDE.md (never delete a failing test to go green)"

patterns-established:
  - "Rename-safe vitest: repoint every vi.mock module path + stub export key in lockstep with the file move; a stale mock silently mounts the real component (jsdom getToken failure)"
  - "Fused landing keeps MainView page-keys generic (SC-001); the input view is preserved for the saved-workflow preload path (INV-3)"

requirements-completed: [SHELL-02]

# Metrics
duration: ~20min
completed: 2026-07-09
---

# Phase 36 Plan 01: WorkflowCatalog→HomeLaunchGrid rename + fused Home landing Summary

**Renamed the data-driven `WorkflowCatalog` to `HomeLaunchGrid` across all 7 callers (grep 0), reskinned it onto the Phase-32 token layer, and fused the Home landing into one prompt launcher + deliverable grid + recents strip — with the `input` view and wizard fork preserved and page-keys kept generic.**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-07-09
- **Tasks:** 3
- **Files modified:** 7 (+ deferred-items.md)

## Accomplishments
- D-11 rename landed: `WorkflowCatalog` → `HomeLaunchGrid` (component + `HomeLaunchGridProps` interface + JSDoc), `git mv` of both the component and its test file, all 7 callers repointed — `grep -rc "WorkflowCatalog" frontend/src == 0`. Both `DashboardLayout` `vi.mock` module paths + stub export keys repointed in lockstep (the trap); both mock-path suites stay green.
- HomeLaunchGrid reskinned onto Phase-32 tokens: `#f5f5f0` → `bg-surface-paper`, dead `var(--font-fraunces)` → `font-serif`, `#1B2A4A` → `text-brand`, error chip → `text-status-failed bg-[var(--status-failed-fill)]`, all `text-gray-*`/`divide-gray`/`bg-white/60`/`bg-gray-100` → ink/line/surface tokens. Retired-palette grep = 0, stray-stock grep = 0.
- Fused Home: the `home` view now composes a prompt launcher (folded from the input idiom) + the `HomeLaunchGrid` deliverable grid + a recents strip driven by the already-threaded `recentRuns` prop (no new fetch). Wizard fork preserved; `input` view untouched and still reachable for the saved-workflow preload path.

## Task Commits

Each task was committed atomically:

1. **Task 1: Grep-all-callers rename (D-11)** - `1679d8e3` (refactor)
2. **Task 2: Reskin HomeLaunchGrid onto Phase-32 tokens (D-15)** - `a6778810` (feat)
3. **Task 3: Fuse the Home view — launcher + grid + recents (SHELL-02 SC-1)** - `58f41b50` (feat)

## Files Created/Modified
- `frontend/src/components/catalog/HomeLaunchGrid.tsx` - renamed from WorkflowCatalog.tsx; the data-driven home launch grid, now on Phase-32 tokens
- `frontend/src/components/catalog/HomeLaunchGrid.test.tsx` - renamed from WorkflowCatalog.test.tsx; import/renders/describe strings repointed
- `frontend/src/components/layout/DashboardLayout.tsx` - repointed import + JSX; fused Home view (launcher + grid + recents); `handleHomeSelectFeature` + `pendingHomeBrief` -> `initialInput`
- `frontend/src/components/layout/DashboardLayout.catalogHome.test.tsx` - vi.mock path + stub export key
- `frontend/src/components/layout/DashboardLayout.waveMount.test.tsx` - vi.mock path + stub export key
- `frontend/src/components/savedworkflows/SavedWorkflowsPage.tsx` - comment ref
- `frontend/src/lib/api.ts` - 2 comment refs
- `.planning/phases/36-home-history-my-workflows-b2/deferred-items.md` - logged the 5 pre-existing dead tests

## Verification (literal output)

```
# 1. grep -rc "WorkflowCatalog" src
0 (no file contains WorkflowCatalog)

# 3. retired-palette grep on HomeLaunchGrid.tsx  (#1B2A4A|#2563eb|#f5f5f0|Inter|Fraunces|JetBrains)
NO MATCHES

# 4. tsc --noEmit error count (baseline 0)
0

# 5. input path intact
1370:    mainView === "input" ? "workflow" :
1621:          {mainView === "input" && (

# 2. three vitest suites
 Test Files  1 failed | 2 passed (3)
      Tests  5 failed | 8 passed (13)
```

- catalogHome.test.tsx: 2/2 green; waveMount.test.tsx: 4/4 green; HomeLaunchGrid.test.tsx: 2/2 in-scope green (two-gate filter + friendly-label precedence).
- Stray-stock grep on HomeLaunchGrid.tsx (`text-gray-`/`bg-gray-`/`bg-blue-`/`divide-gray-`/`bg-white/`/raw `#hex`) = 0; positive token usage = 16.

## Decisions Made
- Kept the file in `catalog/` (a developer-facing path, not a user label) rather than moving to `home/` — removes zero user-facing "Catalogue" wording while minimizing `vi.mock` module-path churn.
- The fused launcher captures a brief and the deliverable grid remains the launch action; the brief rides into the input view via a `pendingHomeBrief` string threaded to `initialInput` only. This keeps `HomeLaunchGrid`'s public API and its standalone tests untouched, and leaves generic agent-seeding (`initialAgentIds` undefined) byte-identical. Stale brief is cleared on `handleLaunchSaved` so a saved-workflow launch never inherits it.

## Deviations from Plan

None - plan executed exactly as written. No auto-fixes required (Rules 1-4 not triggered).

## Issues Encountered

**Pre-existing dead tests in HomeLaunchGrid.test.tsx (out of scope — NOT fixed, NOT deleted).**
The `describe("HomeLaunchGrid — 'Your workflows' section + kebab (Phase 21)")` block (5 tests) fails. Proven pre-existing this session: the component's JSDoc states the "Your Workflows" saved-section was **moved to `SavedWorkflowsPage`** — the component imports only `getWorkflowDefinitions, getToken` (never `getUserWorkflows`/`deleteUserWorkflow`) and never renders a "Your workflows" heading, so these 5 tests assert removed behavior. They are red at base `92af09ec` and documented in STATE.md as the `WorkflowCatalog 5` pre-existing failures (part of the 10 pre-existing repo-wide). The pure symbol rename cannot change test-logic outcomes; the 2 in-scope behavior tests pass and both mock-path suites pass. Logged to `deferred-items.md`; retargeting belongs with the future `SavedWorkflowsPage.test.tsx` (RESEARCH Wave-0 gap).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `HomeLaunchGrid` is the stable component name for downstream 36-plans; fused Home is the landing base.
- Mocked Playwright e2e remains live-deferred (offline webServer timeout, Phase-35 precedent) — not run, per plan.
- SavedWorkflowsPage still shows the in-page `<h1>` "Workflow Catalogue" label (36-CONTEXT D-11 relabel to "My Workflows") — that is a later 36-plan's task, not this plan's scope.

## Self-Check: PASSED

- Files verified on disk: HomeLaunchGrid.tsx, HomeLaunchGrid.test.tsx, 36-01-SUMMARY.md, deferred-items.md — all FOUND.
- Commits verified in git log: 1679d8e3, a6778810, 58f41b50 — all FOUND.

---
*Phase: 36-home-history-my-workflows-b2*
*Completed: 2026-07-09*
