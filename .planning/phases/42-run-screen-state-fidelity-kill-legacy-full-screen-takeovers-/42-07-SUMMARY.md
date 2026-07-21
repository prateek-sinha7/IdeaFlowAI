---
phase: 42-run-screen-state-fidelity-kill-legacy-full-screen-takeovers-
plan: 07
subsystem: ui
tags: [react, files-tab, audit-tab, run-screen, live-state, tailwind, pipelineState]

# Dependency graph
requires:
  - phase: 42-02
    provides: reachable Steps clarify/live surfaces + the live pipelineState.isRunning signal threaded to PreviewPanel
provides:
  - Building-variant Files hero (indeterminate progress bar + spinner + live "task N of M · not yet validated", Download/Download-All suppressed) gated on pipelineState.isRunning
  - Live Audit affordances (pulsing "live" badge + "Elapsed … · in progress" marker + violet "monitoring live" banner) gated on the running signal
affects: [42-run-screen live-tabs, run-screen fidelity]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Component-scoped keyframe injection (<style> tag with a uniquely-named @keyframes) for an indeterminate progress bar — reused from PreviewChrome.tsx (INV-12), globals.css untouched"
    - "Live/settled variant split keyed on a generic isRunning boolean prop (SC-001) — settled surfaces kept intact, live surfaces additive"

key-files:
  created: []
  modified:
    - frontend/src/components/results/FilesTab.tsx
    - frontend/src/components/results/AuditTab.tsx
    - frontend/src/components/preview/PreviewPanel.tsx

key-decisions:
  - "Reused PreviewPanel's already-computed buildStepIndex/buildStepTotal (INV-12 — no new task-count derivation) for the Files 'task N of M' subline; clause elided when counts absent (ND-D)"
  - "Building hero renders even when totalCount===0 while running (skip the empty-state early-return only when isRunning) so a fresh live run still reads as building"
  - "Live Audit 'Elapsed' reuses the existing row-derived duration (no new ticking clock in scope), labelled '· in progress'; elided when absent"
  - "While running the violet 'monitoring live' banner REPLACES the settled/failed verdict banner (settled verdict banner kept byte-unchanged when not running — KEEP §4)"

patterns-established:
  - "Live-state variant gating: a single generic isRunning prop swaps settled↔live sub-surfaces without any workflow-name branch (SC-001)"

requirements-completed: [RUNUI-06]

# Metrics
duration: ~20min
completed: 2026-07-15
---

# Phase 42 Plan 07: Live Files-building hero + live-Audit badge/monitoring banner Summary

**Files hero gains a BUILDING variant (indeterminate bar + spinner + live "task N of M · not yet validated", Download suppressed) and the Audit tab gains a pulsing "live" badge + "in progress" elapsed + a violet "monitoring live" banner — both keyed generically on pipelineState.isRunning, with every settled/failed KEEP surface intact.**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-07-15
- **Tasks:** 2
- **Files modified:** 3 (2 planned + 1 wiring — see Deviations)

## Accomplishments
- Files deliverable hero renders a dark BUILDING variant while the run is live: a component-scoped indeterminate top progress bar, a spinner, a "Final output · building" eyebrow, the live in-progress filename, and a live "task N of M · not yet validated" subline (counts from PreviewPanel's existing live derivation — never the mock's fixed literal). Download + Download-All are suppressed while building.
- Audit tab renders live affordances while running: a pulsing "live" badge beside the records pill, an "Elapsed … · in progress" marker replacing the settled "Duration", and a violet "monitoring live" banner replacing the settled/failed verdict banner.
- Settled Files hero, the failed "Build incomplete" banner, the settled/failed Audit verdict banner + attribution card + taxonomy rows, and the audit fetchers/export menu are all unchanged (KEEP §4 / INV-12 — presentation only).

## Task Commits

Each task was committed atomically:

1. **Task 1: Files hero — building variant while running** - `150d58de` (feat)
2. **Task 2: Live Audit — badge + in-progress + monitoring banner** - `6c9d563d` (feat)

## Files Created/Modified
- `frontend/src/components/results/FilesTab.tsx` - Added the BUILDING hero variant + 4 optional live props (isRunning, buildingTaskIndex, buildingTaskTotal, buildingFilename); suppressed Download/Download-All while running; skip empty-state early-return while running.
- `frontend/src/components/results/AuditTab.tsx` - Added the isRunning prop + pulsing live badge, live "Elapsed · in progress" marker, and violet "monitoring live" banner; settled/failed verdict banner preserved.
- `frontend/src/components/preview/PreviewPanel.tsx` - Threaded the live signals into the FilesTab + AuditTab call sites (isRunning from the existing `isStillRunning`; buildingTaskIndex/Total from the existing `buildStepIndex`/`buildStepTotal`; buildingFilename from `pipelineState.deliverableFilename`).

## Decisions Made
- See key-decisions in frontmatter. Notably: reused existing live derivations (INV-12, no dual logic), kept globals.css out of scope by injecting a component-scoped `@keyframes files-hero-bar` (mirroring PreviewChrome's idiom), and made the violet monitoring banner a running-only replacement for the verdict banner so the settled/failed verdict stays byte-unchanged.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Threaded the live props through PreviewPanel (not in files_modified)**
- **Found during:** Task 1 (and again Task 2)
- **Issue:** The plan's `files_modified` listed only FilesTab.tsx + AuditTab.tsx, but the new building/live variants are gated on an `isRunning` prop that neither component currently receives. Without wiring the props at the PreviewPanel call sites the building hero + live Audit affordances would be dead code (they could never render in the real app), failing the plan's key_link and human-checks.
- **Fix:** Added the props to the FilesTab and AuditTab call sites in `PreviewPanel.tsx`, sourcing them entirely from values PreviewPanel already computes (`isStillRunning`, `buildStepIndex`, `buildStepTotal`, `pipelineState.deliverableFilename`) — no new derivation, no backend/useWorkflow/useRunStream/transport change (frontend-only, within the user's constraints).
- **Files modified:** frontend/src/components/preview/PreviewPanel.tsx
- **Verification:** tsc clean; full vitest holds the exact 8-failure baseline (zero net-new); fidelity capture 8/8 pass.
- **Committed in:** `150d58de` (FilesTab wiring, Task 1) + `6c9d563d` (AuditTab wiring, Task 2)

---

**Total deviations:** 1 auto-fixed (1 blocking-wiring)
**Impact on plan:** The single deviation is the minimal wiring required for the two planned components to function; it reuses only pre-existing live values and stays within the frontend-only constraint. No scope creep.

## Issues Encountered
- A `grep -Ec "task 4 of 7|4 of 7"` acceptance briefly matched a literal in one of my own explanatory code comments (not runtime text). Rephrased the comment to drop the literal so the "no mock literal" guard returns 0. No behavior impact.

## Verification Evidence
- `npx tsc --noEmit` — clean (0 `error TS`, excluding pre-existing mockApi noise).
- `npx vitest run` — **8 failed | 679 passed**, identical to the pre-change baseline (the same `PreviewPanel.switcher`×3, `PreviewPanel.degraded`×1, `HomeLaunchGrid.inspect`×2, `FilesTab.runInput`×2). Zero net-new; no new FilesTab/AuditTab failures. `AuditTab` suite: 15/15 green. `FilesTab` suites: 21 passed / 2 pre-existing runInput failures.
- Acceptance greps: `isRunning` in FilesTab.tsx = 7 (≥1); mock literal in FilesTab.tsx = 0; live affordances in AuditTab.tsx = 21 (≥1).
- `FIDELITY_CAPTURE=1 npx playwright test --project=mocked zzz-baseline` — **8 passed** (no crashes).

## Next Phase Readiness
- Live Files + Audit tabs now render distinct in-progress variants matching the Live mock, joining the already-reachable Steps live surface (42-02). KEEP settled/failed surfaces intact.
- No blockers.

## Self-Check: PASSED

- Commits `150d58de`, `6c9d563d` present in git history.
- All modified files + SUMMARY.md present on disk.

---
*Phase: 42-run-screen-state-fidelity-kill-legacy-full-screen-takeovers-*
*Completed: 2026-07-15*
