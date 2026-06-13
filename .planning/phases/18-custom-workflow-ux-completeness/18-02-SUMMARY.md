---
phase: 18-custom-workflow-ux-completeness
plan: 02
subsystem: ui
tags: [react, tailwind, flexbox, layout, dashboard, vitest]

# Dependency graph
requires:
  - phase: 12-wave-orchestration
    provides: WaveTreePanel mounted unconditionally on the dashboard execution surface (the panel whose heading this plan lifts above the fold)
provides:
  - Flex-budgeted left execution column (CSS-only) so the WaveTreePanel "Wave / Subagent Tree" heading is visible at 1440×950 without scrolling, while the agent panel scrolls its cards internally
affects: [18-custom-workflow-ux-completeness, live-playwright-ui-pass]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Height-owning flex-column parent: a fixed-height column splits its budget between a flex-1 min-h-0 region (flexes + internally scrolls) and a flex-shrink-0 max-h region (stays above the fold), instead of letting the column itself scroll"

key-files:
  created: []
  modified:
    - frontend/src/components/layout/DashboardLayout.tsx
    - frontend/src/components/layout/DashboardLayout.waveMount.test.tsx

key-decisions:
  - "CSS-only fix on the column composition (not a heading y via clipping): column wrapper becomes `flex flex-col overflow-hidden` (dropped column-level `overflow-y-auto`); agent wrapper `flex-1 min-h-0 overflow-hidden`; wave wrapper `flex-shrink-0 max-h-[40%] overflow-y-auto`"
  - "No AgentProgressPanel.tsx / WaveTreePanel.tsx change — each panel already owns its own internal scroll (agent cards `flex-1 overflow-y-auto`:242; wave list `max-h-[260px] overflow-y-auto`:96)"
  - "Offline proof is the structural className assertion (jsdom has no layout engine); the true visual proof (heading bottom ≤ 950 at 1440×950 without scroll) is deferred to the dedicated live Playwright UI pass after this phase"

patterns-established:
  - "Structural-contract test for layout: assert the className contract that PRODUCES the layout (queried via stable DOM anchors), never pixel positions, when the test runtime has no layout engine"

requirements-completed: [ISS-019]

# Metrics
duration: 6min
completed: 2026-06-13
---

# Phase 18 Plan 02: Flex-budget the left execution column (ISS-019) Summary

**CSS-only flex budget of the left dashboard execution column so the WaveTreePanel "Wave / Subagent Tree" heading clears the 1440×950 fold while AgentProgressPanel still scrolls its cards internally — no panel-component change.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-06-13T17:16:00Z (approx)
- **Completed:** 2026-06-13T17:22:31Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Turned the left execution column into a height-owning flex parent so its vertical budget is split between the agent panel (flexes to remaining space) and the wave panel (non-shrinking bottom region) instead of the column itself scrolling and pushing the wave heading below the fold.
- The WaveTreePanel heading is now structurally guaranteed to sit above the agent panel's scroll region; agent cards continue to scroll internally; the non-wave compact "No waves running." empty state is unchanged.
- Pinned the new flex-budget with a structural Vitest assertion in the existing wave-mount test (all 4 tests green); `tsc --noEmit` clean.

## Task Commits

Each task was committed atomically (hooks on, no `--no-verify`):

1. **Task 1: Flex-budget the left execution column (CSS-only)** — `af61f1d3` (fix)
2. **Task 2: Structural test pinning the flex-budget wrappers** — `81ed1719` (test)

**Plan metadata:** see final docs commit.

## Files Created/Modified
- `frontend/src/components/layout/DashboardLayout.tsx` — three className edits on the left execution column (`DashboardLayout.tsx:1175,1177/1200,1209`):
  - column wrapper: added `flex flex-col overflow-hidden`, removed the column-level `overflow-y-auto` (kept `w-full md:w-[340px] lg:w-[360px] flex-shrink-0 h-[45vh] md:h-full` + borders + `bg-white`)
  - new agent wrapper `<div className="flex-1 min-h-0 overflow-hidden">` around the AgentProgressPanel ErrorBoundary child
  - wave wrapper: added `flex-shrink-0 max-h-[40%] overflow-y-auto` (kept `px-3 pt-3 pb-3 border-t border-gray-200` and the unconditional `<WaveTreePanel waves={waves} />` render)
- `frontend/src/components/layout/DashboardLayout.waveMount.test.tsx` — extended with a 4th test asserting: agent wrapper carries `flex-1` + `min-h-0`; wave wrapper carries `flex-shrink-0` + `max-h-[40%]`; column wrapper carries `flex flex-col` + `overflow-hidden` and no longer `overflow-y-auto`. Queried via the existing stable anchors (the `stub-agent-progress` testid and the "Wave / Subagent Tree" heading). A comment records the live-Playwright visual deferral.

## Exact className diffs

| Wrapper | Before | After |
|---------|--------|-------|
| Column (`:1175`) | `… flex-shrink-0 h-[45vh] md:h-full … overflow-y-auto bg-white` | `… flex-shrink-0 h-[45vh] md:h-full … flex flex-col overflow-hidden bg-white` |
| Agent (`:1177`, new) | _(none — panel was a direct child)_ | `flex-1 min-h-0 overflow-hidden` |
| Wave (`:1209`) | `px-3 pt-3 pb-3 border-t border-gray-200` | `flex-shrink-0 max-h-[40%] overflow-y-auto px-3 pt-3 pb-3 border-t border-gray-200` |

## Decisions Made
None beyond the LOCKED CONTEXT fix — plan executed exactly as written. The three rejected hacks (fixed-px clamp of either panel; reordering the wave tree above the agent panel) were avoided; the fix changes the column composition, not the heading's y via clipping.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None. `tsc --noEmit` was clean on the first run; the structural test passed on the first run (agent stub's `parentElement` is the new `flex-1 min-h-0` wrapper; the column is the nearest `div.flex.flex-col` ancestor; the wave wrapper is the nearest `div.flex-shrink-0` ancestor of the heading).

## Known Stubs
None — this is a pure CSS/layout change; no data sources or placeholder values introduced.

## Deferred / Live Verification
- The TRUE visual proof — the "Wave / Subagent Tree" heading bottom ≤ 950 at 1440×950 during an active `sample_wave` run WITHOUT scrolling, plus a long (≥8-card app_builder) agent list still scrolling internally — runs in the dedicated live Playwright UI pass after this phase (CONTEXT deferred item; `/tmp/wave_panel_probe.py` measures the heading y). jsdom has no layout engine, so the offline gate is the className-contract assertion only.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- ISS-019 closed offline (CSS + structural test); ready for the phase's remaining plans and the end-of-phase live Playwright confirmation.
- No backend change; diff is frontend-only (`DashboardLayout.tsx` + its test). No regression to non-wave runs (compact empty state preserved).

## Self-Check: PASSED

- FOUND: frontend/src/components/layout/DashboardLayout.tsx
- FOUND: frontend/src/components/layout/DashboardLayout.waveMount.test.tsx
- FOUND: .planning/phases/18-custom-workflow-ux-completeness/18-02-SUMMARY.md
- FOUND commit: af61f1d3 (Task 1)
- FOUND commit: 81ed1719 (Task 2)

---
*Phase: 18-custom-workflow-ux-completeness*
*Completed: 2026-06-13*
