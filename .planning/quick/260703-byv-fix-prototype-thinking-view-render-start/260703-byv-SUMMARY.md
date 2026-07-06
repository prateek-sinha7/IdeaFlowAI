---
phase: quick-260703-byv
plan: 01
subsystem: frontend/results-thinking-view
tags: [frontend, prototype-pipeline, thinking-view, react, vitest]
requires:
  - StartingPointCard (existing, reused verbatim)
  - ClarificationsCard (existing, reused verbatim)
  - PrototypePipelineView terminal signals (buildStatus / validateStatus / pipelineState.isRunning)
provides:
  - Prototype Thinking view preamble (StartingPoint + Clarifications above the phase view)
  - buildTrulyDone gate that suppresses the between-task all-complete flash
affects:
  - frontend/src/components/results/AgentThinkingTab.tsx
  - frontend/src/components/results/PrototypePipelineView.tsx
tech-stack:
  added: []
  patterns:
    - Reuse-first placement (no new hex/radius/font); one boolean terminal gate
    - Real rendered-DOM vitest specs (render + screen, DOM-order assertions)
key-files:
  created:
    - frontend/src/components/results/AgentThinkingTab.prototypePreamble.test.tsx
    - frontend/src/components/results/PrototypePipelineView.buildGate.test.tsx
  modified:
    - frontend/src/components/results/AgentThinkingTab.tsx
    - frontend/src/components/results/PrototypePipelineView.tsx
decisions:
  - "currentTaskIndex falls back to realtimeCompletedCount (never -1) during the transient between-task done window, so already-done tasks stay checked."
  - "Phase-4 live per-task block widened to (buildIsRunning || (buildStatus===done && !buildTrulyDone)) && tasksData — precise over the plan's tasksData && !buildTrulyDone, to avoid rendering the live block when build is idle."
  - "Removed the now-unused buildIsDone local to keep the tsc-identity gate at exactly 3 errors."
metrics:
  duration: ~10m
  completed: 2026-07-03
---

# Phase quick-260703 byv: Fix prototype Thinking-view render (start-preamble + build-flash gate) Summary

Two FE-only prototype Thinking-view defects fixed with reuse-first placement plus a single boolean terminal gate: the run's StartingPoint + Clarifications now render as a preamble above `PrototypePipelineView`, and a `buildTrulyDone` gate stops the build checklist from flashing all-complete at every between-task transition. Backend byte-identical (INV-3 by construction).

## What was built

### FIX 1 — prototype preamble (Task 1, `AgentThinkingTab.tsx`)
The `isPrototypePipeline` early-return previously returned `<PrototypePipelineView/>` alone, skipping the main-render StartingPointCard/ClarificationsCard. Replaced it with a branch that renders the two already-authored cards as a timeline preamble (`flex-shrink-0 px-4 py-4 space-y-3`) above the pipeline view (`flex-1 min-h-0`), inside a `flex flex-col h-full overflow-hidden` wrapper so scroll/height is preserved. Prop expressions copied verbatim from the main render (`input=runInput`, `originalBriefRootRunId`, `revisionParentVersion`, `clarifications=resolvedClarifications`, `loading=clarificationsLoading`). The `isPrototypePipeline` agent-id check (SC-001) and both upstream mounts (PreviewPanel / WorkflowHistory) are untouched. `ClarificationsCard` returns null for a PROCEED run, so a clarify-less prototype correctly shows StartingPoint only — no code needed.

### FIX 2 — buildTrulyDone gate (Task 2, `PrototypePipelineView.tsx`)
Reordered `getStatus` + status derivations above `currentTaskIndex`, then derived:
`buildTrulyDone = buildStatus === "done" && (validateStatus !== "idle" || pipelineState?.isRunning === false)`.
Substituted `buildTrulyDone` at the terminal sites: `currentTaskIndex` all-done branch, `TaskListVisualization allDone`, and the Phase-4 "All N tasks completed" block. `currentTaskIndex` now falls back to `realtimeCompletedCount` during the transient-done window (`buildIsRunning || (buildStatus === "done" && !buildTrulyDone)`), never -1, so completed tasks stay checked. The Phase-4 live per-task block was widened to cover that window so the card never goes blank nor flashes all-complete mid-loop. `protoCompletedTaskCount` and the backend `agent_complete{prototype-build}` emit are untouched (INV-3 parity-locked).

### Tests (Task 3)
Two new real rendered-DOM specs, both passing:
- `AgentThinkingTab.prototypePreamble.test.tsx` — prototype run with runInput+clarifications renders StartingPoint → Clarifications → Prototype Pipeline in DOM order; clarify-less run shows StartingPoint, no Clarifications, plus the view.
- `PrototypePipelineView.buildGate.test.tsx` — mid-loop (build done, run running, 1/3) shows "1/3 done" and NOT all-complete; terminal (run ended) shows "3/3 done" + "All 3 tasks completed".

## Gates

- **tsc-identity:** `GATE_OK total=3 unexpected=0` (identity check; the 3 errors are the pre-existing mockApi/IdeaInputPage baseline).
- **Backend clean:** `git status --porcelain backend` empty → `BACKEND_CLEAN`.
- **Regression guard (20 audited suites):** 19 GREEN + both new specs GREEN (99 tests, 98 passed). One suite red: `AgentProgressPanel.test.tsx` (`:133` "Presentation" filtering) — see Deferred Issues.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Removed now-unused `buildIsDone` local**
- **Found during:** Task 2
- **Issue:** After rewriting `currentTaskIndex` to use `buildTrulyDone`, the `buildIsDone` local became unused, which would add a TS6133 and break the exactly-3 tsc-identity gate.
- **Fix:** Deleted the `buildIsDone` declaration (its only use was the replaced `currentTaskIndex`). `buildStatus === "done"` remains available where needed.
- **Files modified:** `frontend/src/components/results/PrototypePipelineView.tsx`
- **Commit:** 5db41ba3

**2. [Refinement] Precise live-block gate instead of the plan's example expression**
- **Found during:** Task 2
- **Detail:** The plan suggested gating the Phase-4 live block on `tasksData && !buildTrulyDone`. Used the more precise `(buildIsRunning || (buildStatus === "done" && !buildTrulyDone)) && tasksData` so the live "Building…" block is not eligible to render when build is idle (not started). Behaviorally equivalent at the terminal sites; strictly more correct at the idle boundary. Both new specs and the regression guard pass.
- **Commit:** 5db41ba3

## Deferred Issues

**`AgentProgressPanel.test.tsx` — pre-existing baseline red (NOT a regression from byv).**
- Reproduced at base HEAD `03e5e0ae` by reverting both changed source files and re-running the suite → identical `1 failed | 6 passed`. Zero import linkage to the two changed files.
- Same workflow-catalog "Presentation" filtering family as the known-red WorkflowCatalog×5 baseline exclusion. Not chased (scope fence: prototype Thinking-view FE only).
- Logged to `deferred-items.md` in this phase directory.

## Known Stubs

None — both fixes wire real data (existing props + parsed task counts); no placeholders introduced.

## Commits

- b1397bfd — fix(quick-260703-byv): hoist StartingPoint + Clarifications preamble above prototype view (Task 1)
- 5db41ba3 — fix(quick-260703-byv): buildTrulyDone gate so transient between-task done never flashes all-complete (Task 2)
- 7e65d2ce — test(quick-260703-byv): rendered-DOM specs for prototype preamble + build gate (Task 3)

## Self-Check: PASSED
All 4 changed/created source files present; all 3 task commits present in git history.
