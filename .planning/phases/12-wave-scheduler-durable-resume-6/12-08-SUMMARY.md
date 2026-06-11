---
phase: 12-wave-scheduler-durable-resume-6
plan: 08
subsystem: ui
tags: [react, nextjs, vitest, testing-library, websocket, wave-scheduler]

# Dependency graph
requires:
  - phase: 12-wave-scheduler-durable-resume-6 (plan 06)
    provides: wave_*/subagent_* emit contract + page.tsx waveGroups assembler (flat wave_index/step/worker keys)
  - phase: 12-wave-scheduler-durable-resume-6 (plan 03)
    provides: durable run_events replay + pipeline_reconnected {live, status} payload on the no-live-task path
provides:
  - WaveTreePanel mounted live on the dashboard execution surface (no longer dead UI in unrouted WorkflowComposer)
  - Optional `waves?: WaveGroup[]` prop on DashboardLayout, defaulted to [] (additive, existing callers unaffected)
  - pipeline_reconnected handler in handlePipelineMessage — live:false+terminal resolves the run; live:false+non-terminal and live:true keep running
affects: [12-09 resume bridge (FE consumes its live:true attach + non-null status), 12-10 manifest deliverable, milestone-end live UAT pass]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Execution-surface panels mounted unconditionally in their own ErrorBoundary; the panel owns its empty state (stable panel slot)", "pipeline_reconnected branch logic: live!==false → no-op keep-running; live:false routes on terminal-status set"]

key-files:
  created:
    - frontend/src/components/layout/DashboardLayout.waveMount.test.tsx
    - frontend/src/hooks/useWorkflow.reconnect.test.ts
  modified:
    - frontend/src/components/layout/DashboardLayout.tsx
    - frontend/src/app/dashboard/page.tsx
    - frontend/src/hooks/useWorkflow.ts

key-decisions:
  - "Took the self-contained keep-running option for live:false + non-terminal status (no reconnectPending flag, no shared-type change) — re-replay rides the existing reconnect cycle bounded by useWebSocket backoff (T-12-08-02)"
  - "WaveTreePanel rendered unconditionally (not gated on waves.length) so the panel slot is stable; the panel owns its 'No waves running.' empty state"
  - "Tested the REAL DashboardLayout mount (heavy children stubbed) instead of a thin harness — proves the actual execution-surface wiring"

patterns-established:
  - "FE jsdom tests of layout components: stub heavy children with data-testid markers, keep the assertion-target component real, reuse the motion/react proxy mock"

requirements-completed: [WAVE-03, RESUME-03, RESUME-04]

# Metrics
duration: 8min
completed: 2026-06-11
---

# Phase 12 Plan 08: FE Wave Panel Mount + pipeline_reconnected Handler Summary

**WaveTreePanel now renders live on the dashboard execution surface beside AgentProgressPanel, and pipeline_reconnected (live:false + terminal status) resolves isRunning — ending the post-resume "running forever" hang**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-06-11T13:44:05Z
- **Completed:** 2026-06-11T13:52:30Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Closed UAT Gap 1: threaded `waveGroups` from dashboard/page.tsx into DashboardLayout via a new optional `waves` prop and mounted `<WaveTreePanel waves={waves} />` in its own ErrorBoundary on the execution view's left column — the wave tree assembled by the already-vitest-covered page.tsx handler is no longer dead UI.
- Closed UAT Gap 2 (FE half): added a `pipeline_reconnected` case to `handlePipelineMessage` — live:false + terminal status ("completed"/"failed"/"cancelled"/"error") flips isRunning=false (finalizing agents on "completed", mirroring pipeline_complete) and clears the persisted run id; live:false + non-terminal keeps running with no new retry loop; live:true / absent live keeps running for the live tail (12-09 bridge / legacy path).
- 9 new vitest tests (3 mount + 6 reconnect branches); existing 6 wsReplayState wave-state tests still green; tsc clean.

## Task Commits

Each task was committed atomically:

1. **Task 1: Mount WaveTreePanel on the execution surface** - `a6dc6bc1` (feat)
2. **Task 2: pipeline_reconnected handler in useWorkflow** - `f5ee356f` (feat)

## Files Created/Modified

- `frontend/src/components/layout/DashboardLayout.tsx` - New optional `waves?: WaveGroup[]` prop (default []); WaveTreePanel mounted after AgentProgressPanel's ErrorBoundary inside the execution left column, wrapped in `<ErrorBoundary fallbackLabel="WaveTree">` + a `px-3 pt-3 pb-3 border-t` wrapper
- `frontend/src/app/dashboard/page.tsx` - `waves={waveGroups}` threaded into DashboardLayout (only change)
- `frontend/src/hooks/useWorkflow.ts` - Additive `case "pipeline_reconnected"` in handlePipelineMessage; existing event cases untouched
- `frontend/src/components/layout/DashboardLayout.waveMount.test.tsx` - Renders the real DashboardLayout (router/motion/heavy children stubbed, SkillsHooksProvider real) with isRunning=true: non-empty waves → heading + worker leaf render; waves=[] and omitted prop → empty state
- `frontend/src/hooks/useWorkflow.reconnect.test.ts` - Unit-tests handlePipelineMessage directly with a capturing fake setPipelineState seeded with 2 idle agents: terminal-completed resolves+finalizes, terminal-failed resolves agents-as-is, non-terminal/missing-status/live:true/absent-live all keep running

## Decisions Made

- **Self-contained keep-running for live:false + non-terminal** (the plan's preferred option): no `reconnectPending` flag, no PipelineRunState type change — the run IS still running so the UI is correct; re-replay is driven by the existing connection-cycle effect bounded by useWebSocket's reconnect backoff (T-12-08-02: no unbounded reconnect storm).
- **Unconditional WaveTreePanel render**: the panel slot is stable across wave/non-wave runs; WaveTreePanel owns the "No waves running." empty state, so non-wave workflows render exactly as before plus a harmless empty panel.
- **Real-component mount test over thin harness**: the plan allowed a harness fallback, but mocking the ~12 heavy children proved cheap and the test now asserts the actual DashboardLayout execution-surface wiring (the exact thing Gap 1 was about).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- 12-09 (backend resume bridge) can land independently: the FE now consumes both shapes it will produce — `live: true` (engine→WS attach, FE keeps running for the live tail) and non-null `status` on `live: false` (FE resolves on terminal).
- The live render of the wave tree is re-confirmed at the next milestone-end live UAT pass (per the defer-live-verification convention).
- ValidatorIssuePanel remains a known-unwired panel (phase-8 latent gap, explicitly out of scope here).

---
*Phase: 12-wave-scheduler-durable-resume-6*
*Completed: 2026-06-11*

## Self-Check: PASSED

- All created files exist on disk (waveMount test, reconnect test, SUMMARY)
- Task commits a6dc6bc1 and f5ee356f verified in git log
