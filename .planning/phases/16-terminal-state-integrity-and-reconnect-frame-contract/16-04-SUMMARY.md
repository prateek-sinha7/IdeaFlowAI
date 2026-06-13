---
phase: 16-terminal-state-integrity-and-reconnect-frame-contract
plan: 04
subsystem: ui
tags: [react, typescript, preview-panel, useworkflow, terminal-state, degraded-affordance, vitest]

# Dependency graph
requires:
  - phase: 16-terminal-state-integrity-and-reconnect-frame-contract (Plan 01, ISS-016, BE)
    provides: "the server failure signal — pipeline_failed / pipeline_complete status:degraded — that this FE plan consumes"
provides:
  - "Additive server `failed`/`failedAgents` flag on PipelineRunState, set by the useWorkflow pipeline_failed handler"
  - "PreviewPanel terminal-empty degraded/failed affordance (DegradedRunAffordance), keyed on the server signal, replacing the neutral 'Output will appear here' on both live and history-reopen"
  - "reopenedRunStatus / reopenedFailedAgents prop threaded page.tsx → DashboardLayout → PreviewPanel for the history-reopen failure path"
  - "PreviewPanel.degraded.test.tsx pinning the server-keyed affordance across 8 cases"
affects: [verification, phase-16-review]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Server-signal-keyed UI affordance: the FE renders failure state from a server-derived flag (pipelineState.failed/.degraded or the reopened run status), never a client-side terminal && !content guess"
    - "Additive-optional state fields mirror the existing degraded/degradedFailedAgents pattern (no required-field break)"

key-files:
  created:
    - frontend/src/components/preview/PreviewPanel.degraded.test.tsx
  modified:
    - frontend/src/hooks/useWorkflow.ts
    - frontend/src/types/index.ts
    - frontend/src/components/preview/PreviewPanel.tsx
    - frontend/src/app/dashboard/page.tsx
    - frontend/src/components/layout/DashboardLayout.tsx

key-decisions:
  - "Affordance condition (showFailureAffordance = !hasContent && isTerminal && terminalFailure) always includes a server-derived flag — no client empty==failed guess (CONTEXT A2 REJECTED hack avoided, T-16-04-SPOOF mitigated)"
  - "isTerminal derived as !(isStreaming || pipelineState.isRunning) so a still-streaming empty run keeps the neutral empty-state"
  - "History-reopen failure threaded via a new reopenedRunStatus prop (page state set from fullRun.status failed/cancelled), cleared on fresh runs and successful reopens, rather than inferring failure from missing content"
  - "Reused already-imported lucide AlertTriangle + existing revise handlers for the retry hint — zero new dependencies (T-16-04-SC accept)"

patterns-established:
  - "Pattern: terminal-state UI affordances key on the server's authoritative status, keeping FE and DB in agreement (avoids the IN-03 FE-vs-DB disagreement)"

requirements-completed: [ISS-017]

# Metrics
duration: ~9 min
completed: 2026-06-13
---

# Phase 16 Plan 04: ISS-017 — FE Terminal-Empty Degraded/Failed Affordance Summary

**The Preview pane now shows a server-keyed degraded/failed affordance (failed-agent names + a view-details/retry hint) instead of the neutral "Output will appear here" for a terminal run with no content, on both the live (pipelineState.failed/.degraded) and history-reopen (fullRun.status failed/cancelled) paths.**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-06-13T12:45:00Z (approx)
- **Completed:** 2026-06-13T12:54:40Z
- **Tasks:** 2
- **Files modified:** 5 (4 modified, 1 created)

## Accomplishments

- `useWorkflow.ts` `pipeline_failed` handler now sets an additive `failed: true` + `failedAgents` on `PipelineRunState`, mirroring the existing degraded pattern — the FE face of the ISS-016 server signal.
- `PreviewPanel.tsx` replaces the bare `!hasContent` neutral empty-state with a three-way branch: a `DegradedRunAffordance` when the run is terminal + empty + carries a **server** failure signal; the neutral empty-state for streaming/no-signal; the deliverable when content exists.
- The history-reopen failure is threaded (`reopenedRunStatus`) page.tsx → DashboardLayout → PreviewPanel, so a reopened `failed`/`cancelled` run shows the affordance while a successful/streaming run does not.
- A component test (`PreviewPanel.degraded.test.tsx`, 8 cases) pins the server-keyed behavior, including the explicit "no client empty==failed guess" no-signal case.

## Task Commits

1. **Task 1: Surface the server failed signal + render the terminal-empty affordance (live + reopen)** — `f5dcd4ae` (feat)
2. **Task 2: PreviewPanel degraded/failed affordance component test** — `fee4dbfd` (test)

**Plan metadata:** committed separately with this SUMMARY.

## Files Created/Modified

- `frontend/src/hooks/useWorkflow.ts` — `pipeline_failed` handler sets additive `failed`/`failedAgents` on the run state.
- `frontend/src/types/index.ts` — `PipelineRunState` gains optional `failed?: boolean` + `failedAgents?: string[]` (additive, alongside `degraded?`/`degradedFailedAgents?`).
- `frontend/src/components/preview/PreviewPanel.tsx` — `DegradedRunAffordance` component; derived `isTerminal`/`terminalFailure`/`showFailureAffordance`; `reopenedRunStatus`/`reopenedFailedAgents` props; replaced the neutral-only empty-state branch.
- `frontend/src/app/dashboard/page.tsx` — `reopenedRunStatus` state set from `fullRun.status` (failed/cancelled) in `handleSelectWorkflowRun`, cleared on fresh runs and successful reopens; passed down through DashboardLayout.
- `frontend/src/components/layout/DashboardLayout.tsx` — `reopenedRunStatus` prop added to the interface, destructure, and the `<PreviewPanel>` render.
- `frontend/src/components/preview/PreviewPanel.degraded.test.tsx` — 8-case component test (created).

## Decisions Made

- The affordance is gated on a server-derived flag at every site (`pipelineState.failed`/`.degraded` live; `reopenedRunStatus` on history) — the CONTEXT A2 LOCKED fix. The REJECTED client-side `terminal && !finalOutput` guess is explicitly avoided and pinned by the no-signal test case.
- `isTerminal = !(isStreaming || pipelineState.isRunning)` so an in-flight empty run never prematurely shows failure.
- History failure threaded by a dedicated prop rather than inferred from missing content; cleared on new runs to prevent a stale affordance bleeding across reopens.

## Deviations from Plan

None - plan executed exactly as written.

The plan's two tasks were `tdd="true"`; given Task 1 is the source and Task 2 is the pinning test (the plan's own task split), implementation landed in Task 1's commit and the test in Task 2's commit. Both `tsc --noEmit` and the `PreviewPanel.degraded` suite were run and green at each task gate.

## Issues Encountered

- **Pre-existing unrelated test failure (out of scope, NOT introduced here):** `frontend/src/components/workflow/AgentProgressPanel.test.tsx:176` ("hides the chain panel when every base type is already complete") fails. Verified out of 16-04 scope: the file was not touched (`git diff e6530025 HEAD`), it imports only an additive-optional `type` from `@/types/index`, and the assertion text is unchanged since base commit `a219fade`. Logged to `deferred-items.md`; not fixed per the execute-plan scope boundary (do not auto-fix pre-existing failures in unrelated files). Hand to the phase verifier / a separate fix task.

## Known Stubs

None — the affordance is server-keyed (no hardcoded empty values flow to it), and the existing 4-deliverable content path is unchanged (the affordance is gated on `!hasContent`).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- ISS-017 closed on the FE: the Preview shows a degraded/failed affordance for a terminal empty run on both live and history-reopen, keyed on the server signal (ROADMAP SC3).
- Full end-to-end faithfulness depends on Plan 01 (ISS-016, BE) emitting `pipeline_failed`/`status:degraded` for the model/tool-error path — this plan consumes that signal and adds nothing the BE doesn't already send.
- Carry-forward: the pre-existing `AgentProgressPanel.test.tsx` failure (see `deferred-items.md`) for the phase verifier.

## Verification

- `cd frontend && npx tsc --noEmit` → exit 0 (additive/optional props and fields type-check).
- `cd frontend && npm run test -- PreviewPanel.degraded` → 8/8 passed.
- Acceptance greps: `useWorkflow.ts` sets `failed: true`/`failedAgents`; `types/index.ts` adds `failed?`/`failedAgents?`; `PreviewPanel.tsx` new branch consumes `pipelineState?.failed || pipelineState?.degraded` + the reopened status; no client-only `terminal && !finalOutput` guess exists.

## Self-Check: PASSED

- FOUND: `frontend/src/components/preview/PreviewPanel.degraded.test.tsx`
- FOUND: `.planning/phases/16-terminal-state-integrity-and-reconnect-frame-contract/16-04-SUMMARY.md`
- FOUND commit: `f5dcd4ae` (Task 1, feat)
- FOUND commit: `fee4dbfd` (Task 2, test)

---
*Phase: 16-terminal-state-integrity-and-reconnect-frame-contract*
*Completed: 2026-06-13*
