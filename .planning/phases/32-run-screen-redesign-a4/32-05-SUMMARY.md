---
phase: 32-run-screen-redesign-a4
plan: 05
subsystem: frontend
tags: [iss-035, iss-036, sc-001, sc-4, fix-039, lock-b, chat-lane, run-screen]

# Dependency graph
requires:
  - phase: 32-run-screen-redesign-a4 (04)
    provides: "review_gate_ready.data carries the name-free update_specs_eligible + artifact_kind flags (the pinned field-name contract this plan parses)"
provides:
  - "PipelineRunState.cancelled terminal marker set by the pipeline_cancelled reducer (ISS-035, SC-4) — a derivable cancelled state for RunLaneState"
  - "useRunChat.runId fed the live pipelineRunId ?? activePipelineRunId so REST commands target the building run (ISS-036); SSE stays dormant (LOCK-B)"
  - "specRevisionCount driven off the generic wasAlreadyDone signal — the prototype-specify literal removed (SC-001, SC-2)"
  - "review_gate_ready parses update_specs_eligible + artifact_kind defensively into reviewGateData (the single FE feed for plans 06/08)"
affects: [run-screen FE plans (06 reskin / 08 Steps), RunChatLane, reviewGateData consumers]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Terminal-marker symmetry: pipeline_cancelled stamps cancelled:true mirroring pipeline_failed's failed:true — downstream selectors derive terminal state, never guess from isRunning=false alone"
    - "SC-001 name-free discriminator (FE half): spec-revision keyed on generic already-done state + declared payload flags, never an agent-id string literal"
    - "Defensive WS-payload parse: optional server flags read with ?? defaults so absent/extra fields never crash the reducer"

key-files:
  created:
    - frontend/src/hooks/__tests__/useWorkflow.pipelineCancelled.test.ts
  modified:
    - frontend/src/hooks/useWorkflow.ts
    - frontend/src/types/index.ts
    - frontend/src/app/dashboard/page.tsx

key-decisions:
  - "Terminal marker named `cancelled?: boolean` (symmetric with the existing `failed?: boolean` Phase-16 marker) rather than a `terminalReason` enum — minimal additive surface, matches the pipeline_failed precedent the reducer already mirrors."
  - "isSpecRevisionRerun = wasAlreadyDone (drop the `&& agentId === 'prototype-specify'` clause entirely). ANY already-done agent re-firing agent_start is now the generic spec-revision signal (ND-11), generalizing beyond prototype — the intended SC-001 broadening."
  - "useRunChat.ts itself needed NO edit: the runId prop is already string|null; ISS-036 is a pure page.tsx call-site prop change. useRunChat.ts stays out of the diff despite being in files_modified (superset)."
  - "A2 verified: pipelineState.pipelineRunId is set by the pipeline_start reducer while building, so the ?? activePipelineRunId fallback is the correct precedence (build id first, clarify-only id as fallback when unset)."

requirements-completed: [SC-4, SC-2]

# Metrics
duration: ~9min
completed: 2026-07-08
---

# Phase 32 Plan 05: Chat-Lane STATE Plumbing Summary

**pipeline_cancelled now stamps a derivable `cancelled` terminal marker (FIX-039 reset untouched), useRunChat targets the live building run (ISS-036, SSE dormant/LOCK-B), and the prototype-specify literal is gone — spec-revision keys on the generic already-done signal while review_gate_ready defensively parses the plan-04 update_specs_eligible/artifact_kind flags into the single FE feed for plans 06/08.**

## Performance

- **Duration:** ~9 min
- **Tasks:** 3 (Task 1 TDD: RED → GREEN)
- **Files:** 4 (1 created, 3 modified)

## Accomplishments

- **ISS-035 / SC-4 (cancel-ack marker):** the `pipeline_cancelled` reducer case now returns `cancelled: true` on `pipelineState`, symmetric with the `pipeline_failed` `failed: true` marker. A downstream selector (RunLaneState, plan 06) derives the LIVE-STATE-CONTRACT §1 cancelled state ("Cancelled by you" + relaunch) instead of falling through to idle. The reducer pushes NO chat message — the transcript line is rendered by RunChatLane in plan 06 off this marker.
- **FIX-039 (not regressed):** the ISS-035 edit is confined to the returned object of the `pipeline_cancelled` case; the unconditional per-run `agent_start` accumulator reset block is byte-unchanged. A new reducer test asserts the double-`agent_start` replace-not-append invariant still holds.
- **SC-001 / SC-2 (literal fix):** `useWorkflow.ts` no longer contains the `prototype-specify` string (grep count 0, was 2). `specRevisionCount` is bumped off the generic `wasAlreadyDone` signal (`isSpecRevisionRerun = wasAlreadyDone`), the name-free spec-revision discriminator (ND-11). Both the `isSpecifyRerun` literal at L293 and the KAN-101 comment naming it were removed; the stale `specRevisionCount` doc comment in types was corrected to be name-free.
- **Plan-04 flag parse:** `page.tsx` `review_gate_ready` reads `data.update_specs_eligible ?? false` and `data.artifact_kind` defensively into `reviewGateData` next to `redoable`. `ReviewGateReadyData` and the `reviewGateData` state type are extended additively (`updateSpecsEligible?: boolean`, `artifactKind?: string`). This is the single FE parse point plans 06/08 consume.
- **ISS-036 / LOCK-B (runId thread):** `useRunChat({ runId: pipelineState.pipelineRunId ?? activePipelineRunId, ... })` so the REST command path targets the live building run instead of null-then-fresh-POST. Pure FE prop change — `RunConnectionProvider` is NOT mounted, `NEXT_PUBLIC_SSE_TRANSPORT` untouched, `useWebSocket.ts`/`app/layout.tsx` unchanged; legacy WS remains the active transport, SSE dormant.

## Task Commits

1. **Task 1 (RED):** failing pipeline_cancelled marker + FIX-039 guard — `b2f3c623` (test)
2. **Task 1 (GREEN):** stamp `cancelled` marker + additive type — `8b478161` (feat)
3. **Task 2:** drop prototype-specify literal + parse update_specs_eligible — `1d115b38` (feat)
4. **Task 3:** thread live pipelineRunId into useRunChat — `03997db3` (feat)

## Files Created/Modified

- `frontend/src/hooks/__tests__/useWorkflow.pipelineCancelled.test.ts` (created) — Pins: pipeline_cancelled sets `cancelled:true` (flat + nested `data.duration` shapes); the marker is absent on non-cancel events; the FIX-039 double-agent_start replace-not-append invariant. Drives `handlePipelineMessage` directly through the `shouldApplyEvent` dedup gate (mirrors useWorkflow.regenerateReset).
- `frontend/src/hooks/useWorkflow.ts` (modified) — pipeline_cancelled return gains `cancelled: true`; `isSpecRevisionRerun = wasAlreadyDone` replaces the `prototype-specify` literal; the FIX-039 reset block is unchanged.
- `frontend/src/types/index.ts` (modified) — additive `cancelled?: boolean` on `PipelineRunState`; additive `update_specs_eligible?: boolean` + `artifact_kind?: string` on `ReviewGateReadyData`; name-free corrections to the specRevisionCount comment.
- `frontend/src/app/dashboard/page.tsx` (modified) — `reviewGateData` type + parse extended with `updateSpecsEligible`/`artifactKind`; `useRunChat` runId threaded to `pipelineState.pipelineRunId ?? activePipelineRunId`.

## Verification Evidence

- **vitest (full plan set):** `npx vitest run useWorkflow.pipelineCancelled + useWorkflow.regenerateReset + reconnect + clarifyRetention + imagePayload + useRunChat` → **6 files / 26 passed**. (Note: the plan cited `src/hooks/__tests__/useWorkflow.pipelineCancelled.test.ts` + `src/hooks/useWorkflow.test.ts`; the new test landed at the pinned `__tests__/` path, and the pre-existing useWorkflow suite is actually split across `useWorkflow.*.test.ts` — the non-existent monolithic `useWorkflow.test.ts` was substituted with all four existing useWorkflow spec files to prove no regression. See Deviations.)
- **tsc identity:** `npx tsc --noEmit | grep -v mockApi.ts | grep -c "error TS"` = **0** (baseline 0 preserved).
- **SC-001 grep:** `grep -c "prototype-specify" src/hooks/useWorkflow.ts` = **0** (was 2).
- **update_specs_eligible present:** `grep -c "update_specs_eligible" src/app/dashboard/page.tsx` = 1.
- **runId thread present:** `grep -c "pipelineRunId ?? activePipelineRunId" src/app/dashboard/page.tsx` = 1.
- **FIX-039 intact:** `git diff` of useWorkflow.ts (Task 1) shows the ONLY additions in the pipeline_cancelled case (the `cancelled: true` marker + comment); the agent_start reset assignment block is unchanged.
- **LOCK-B held:** working diff = only page.tsx (Task 3); `layout.tsx` and `useWebSocket.ts` NOT in any commit; `grep -c RunConnectionProvider src/app/layout.tsx` = 0 (not mounted); no env/SSE file touched.

## Decisions Made

- **Marker shape = boolean `cancelled`, not a `terminalReason` enum.** The reducer already mirrors pipeline_failed's `failed: boolean`; a parallel `cancelled: boolean` is the minimal additive surface and reads identically for the downstream selector. An enum would have been over-engineering for a two-state (failed/cancelled) terminal set already modelled as sibling booleans.
- **Generic spec-revision generalization (ND-11):** dropping the agent-id clause means any already-done agent re-firing bumps `specRevisionCount`, not just the former `prototype-specify`. This is the intended SC-001 broadening — a custom prototype-like workflow's spec agent gets the revision badge with zero name coupling.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Plan cited test paths that do not exist in the tree**
- **Found during:** Task 1 verify / Task 2 & 3 verify commands.
- **Issue:** The plan's `<verify>` blocks and guardrails reference `src/hooks/__tests__/useWorkflow.pipelineCancelled.test.ts` (a `__tests__/` dir that did not exist) and `src/hooks/useWorkflow.test.ts` (a monolithic suite that does not exist — the useWorkflow suite is split into `useWorkflow.regenerateReset|reconnect|clarifyRetention|imagePayload.test.ts`).
- **Fix:** Created the new test at the plan's pinned `__tests__/` path (vitest include glob `src/**/*.{test,spec}.{ts,tsx}` picks it up; import path `../useWorkflow`). Substituted the non-existent `useWorkflow.test.ts` with all four existing `useWorkflow.*.test.ts` files for the no-regression proof.
- **Files modified:** none beyond the planned set (test-path resolution only).
- **Commit:** verification-only; no code impact.

### Non-deviation notes

- **useRunChat.ts unchanged:** listed in `files_modified` but required no edit — the `runId: string | null` prop already exists; ISS-036 is a pure page.tsx call-site change. `files_modified` is a superset, so this is not a scope deviation.
- **Comment reword in the agent_start case:** the KAN-101 comment (L288-291) named `prototype-specify`; it was reworded to be name-free (required for the SC-001 grep-0 guard). This is prose only — the FIX-039 reset assignment block is byte-unchanged and the reset ordering is preserved.

## Issues Encountered

None blocking. The plan's cited test paths were stale (see Deviation 1) but resolved deterministically.

## Threat Flags

None — no new trust boundary introduced. SSE stays dormant (LOCK-B), no new network endpoint or auth path; the review_gate_ready parse is defensive (optional flags with defaults) per the plan threat register (T-32-05-04).

## Self-Check: PASSED

- Files: useWorkflow.pipelineCancelled.test.ts, useWorkflow.ts, types/index.ts, page.tsx, 32-05-SUMMARY.md — all FOUND.
- Commits: b2f3c623 (RED), 8b478161 (feat marker), 1d115b38 (feat SC-001+parse), 03997db3 (feat runId) — all FOUND.
- Guardrails: FIX-039 reset block unchanged; LOCK-B held (layout.tsx/useWebSocket.ts untouched, provider not mounted); prototype-specify count 0; runId thread present.

---
*Phase: 32-run-screen-redesign-a4*
*Completed: 2026-07-08*
