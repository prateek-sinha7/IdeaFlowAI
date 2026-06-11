---
phase: 12-wave-scheduler-durable-resume-6
plan: 07
subsystem: ui
tags: [react, nextjs, websocket, typescript, wave-scheduler, durable-resume, vitest]

# Dependency graph
requires:
  - phase: 12-wave-scheduler-durable-resume-6 (12-06)
    provides: backend stamps wave_index + step + worker (flat on event data) onto subagent_spawned/subagent_result events — the emit contract the FE folds in
  - phase: 12-wave-scheduler-durable-resume-6 (12-04)
    provides: WaveTreePanel + after_seq reconnect + the (now-superseded) deferred live UAT checklist
  - phase: 12-wave-scheduler-durable-resume-6 (12-05)
    provides: CR-01 seq seeding + CR-02 WS replay workspace recovery — makes the durable tail actually replay on reconnect
provides:
  - "frontend/src/lib/wsReplayState.ts — pure, unit-tested dedup-decision (shouldApplyEvent) + per-run-reset (resetReplayState) helper extracted from the dashboard WS handler"
  - "event_id dedup hoisted to the TOP of handleWebSocketMessage covering ALL event types (CR-05) — replayed agent_chunk/tool_call/task_progress apply at most once on reconnect"
  - "per-run reset of lastSeqRef/seenEventIdsRef/waveGroups on a new run (WR-03) — reconnect works for run 2+; no cross-run state bleed"
  - "worker leaves keyed by worker index — N same-agent parallel workers render as N distinct leaves (CR-06 FE half)"
  - "wave groups keyed by step:waveIndex (IN-06) — two wave_scheduler steps no longer merge; cancelled renders terminal (IN-05)"
affects: [end-of-milestone live UAT pass, future wave-UI iterations]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure unit-testable extraction: dedup/reset decision pulled out of the useCallback WS handler closure into wsReplayState.ts so it is testable without rendering the dashboard"
    - "CR-05 idempotent replay: event_id dedup ONCE at the top of the handler before routing (not per-branch) — covers wave AND non-wave event types"
    - "12-06 emit-contract pin: FE consumes EXACTLY data.wave_index / data.step / data.worker (flat) matching the 12-06-SUMMARY recorded contract"

key-files:
  created:
    - frontend/src/lib/wsReplayState.ts
    - frontend/src/lib/wsReplayState.test.ts
  modified:
    - frontend/src/app/dashboard/page.tsx
    - frontend/src/components/workflow/WaveTreePanel.tsx
    - frontend/src/types/index.ts

key-decisions:
  - "Dedup decision + per-run reset extracted into a pure helper (wsReplayState.ts) because handleWebSocketMessage is a useCallback closure not independently importable — unit-tested directly, no full-dashboard render harness invented (08-08 Task-3 precedent)"
  - "event_id dedup is ONE site at the top of the handler (covers all event types), not the former wave-branch-only dedup — the FE now always sends after_seq so the backend replay branch is always entered and non-wave events double-delivered without this"
  - "Worker leaves keyed by data.worker (worker index), not agent name — the sample_wave self×N shape collapsed to one flapping leaf under the old wk.agent === agent keying"
  - "Wave groups keyed by step:waveIndex (not waveIndex alone) so two wave_scheduler steps' wave-index-0 groups stay distinct (IN-06)"
  - "FE consumes the exact flat 12-06 emit-contract keys data.wave_index/data.step/data.worker (pinned against 12-06-SUMMARY) — no rename/nesting that would silently drop every subagent event"
  - "Task 3 live-render/reconnect checkpoint auto-approved (auto-mode); live verification deferred to the end-of-milestone live pass per project convention — no human visually verified for this plan"

patterns-established:
  - "shouldApplyEvent(seen, eventId): undefined/empty id → true (legacy pass-through); present + already-in-set → false (drop); present + new → adds + true"
  - "resetReplayState clears the seen-set, zeroes last-seq, empties wave groups — run 2 is not poisoned by run 1's ids/cursor/panel"
  - "Worker-leaf shape extended with worker:number alongside agent+status; WaveGroup shape extended with step"

requirements-completed: [RESUME-03, WAVE-03]

# Metrics
duration: ~16min
completed: 2026-06-11
---

# Phase 12 Plan 07: FE Wave Worker-Leaf Render + Idempotent Reconnect Gap Closure Summary

**Closes the FE half of CR-06 (worker leaves keyed by worker index → N distinct leaves), CR-05 (event_id dedup hoisted to the top of the WS handler for ALL event types via a unit-tested pure helper), WR-03 (per-run reset of replay/dedup/wave state), IN-06 (wave groups keyed by step:waveIndex) and IN-05 (cancelled renders terminal) — zero new dependencies, no existing panel modified.**

## Performance

- **Duration:** ~16 min
- **Started:** 2026-06-11
- **Completed:** 2026-06-11
- **Tasks:** 3 (2 auto + 1 human-verify checkpoint, auto-approved)
- **Files modified:** 5 (2 created, 3 modified)

## Accomplishments

- **CR-05 (idempotent reconnect):** `event_id` dedup hoisted to the TOP of `handleWebSocketMessage` (before any routing), via the new pure `shouldApplyEvent` helper — covering every event type (wave AND non-wave: `agent_chunk`/`tool_call`/`task_progress`). The former wave-branch-only dedup was removed so dedup happens exactly once. `lastSeqRef` advances only AFTER the dedup check passes, so a duplicate does not re-advance the cursor. Result: a replayed event on reconnect applies at most once (no duplicated streamed agent text).
- **WR-03 (per-run reset):** `resetReplayState` wired to the new-run path resets `lastSeqRef` → 0, clears `seenEventIdsRef`, and empties `waveGroups`. Run 2's events now advance the cursor from 0 (so a mid-run reconnect sends the correct `after_seq`), the previous run's wave panel does not bleed into the next run, and the seen-set does not grow unboundedly.
- **CR-06 FE half (worker leaves):** worker leaves keyed by `data.worker` (worker index) instead of agent name; the leaf shape carries `worker:number` alongside `agent`+`status`. N parallel workers of the same agent (the `sample_wave` self×N shape) render as N distinct leaves instead of one collapsed flapping leaf.
- **IN-06 (cross-step collision):** wave groups keyed by `step:waveIndex` — the page lookup/merge matches on `(step, waveIndex)` and the `WaveTreePanel` React key is `${group.step}:${group.waveIndex}`. Two `wave_scheduler` steps' wave-index-0 groups stay distinct.
- **IN-05 (cancelled terminal):** `statusKind` in `WaveTreePanel.tsx` maps any `cancel`-containing status to the terminal/failed bucket — a cancelled wave/worker shows a terminal chip, not a grey pending one.
- **Pure unit-tested helper:** `wsReplayState.ts` (`shouldApplyEvent` + `resetReplayState`) with a vitest test proving (a) a second delivery of the same `event_id` is a no-op, (b) a distinct/undefined `event_id` returns true, and (c) after reset the seen-set/last-seq/wave-groups are cleared so a previously-seen id applies again.

## Task Commits

Each task was committed atomically:

1. **Task 1: Hoist event_id dedup to top of handler + reset FE state per run (CR-05, WR-03)** - `04fdf61d` (fix) — `frontend/src/lib/wsReplayState.ts`, `frontend/src/lib/wsReplayState.test.ts`, `frontend/src/app/dashboard/page.tsx` (181 insertions, 9 deletions)
2. **Task 2: Render worker leaves by worker index + wave keyed by step:waveIndex + cancelled terminal (CR-06 FE half, IN-06, IN-05)** - `ae06d15d` (fix) — `frontend/src/app/dashboard/page.tsx`, `frontend/src/components/workflow/WaveTreePanel.tsx`, `frontend/src/types/index.ts` (44 insertions, 6 deletions)
3. **Task 3: Human-verify live wave-tree worker-leaf render + idempotent reconnect** - checkpoint (auto-approved, no code)

**Plan metadata:** (this docs commit)

## Files Created/Modified

- `frontend/src/lib/wsReplayState.ts` - **created** — pure dedup-decision (`shouldApplyEvent`) + per-run-reset (`resetReplayState`) helpers, no React/module-level state
- `frontend/src/lib/wsReplayState.test.ts` - **created** — vitest behavioral test (dedup-before-routing no-op + reset-clears-refs)
- `frontend/src/app/dashboard/page.tsx` - `event_id` dedup hoisted to the top of `handleWebSocketMessage` (all event types) via the helper; per-run reset of `lastSeqRef`/`seenEventIdsRef`/`waveGroups`; worker leaves keyed by `data.worker`; wave group lookup keyed by `(step, waveIndex)`
- `frontend/src/components/workflow/WaveTreePanel.tsx` - cancelled → terminal chip in `statusKind`; React key includes `step`
- `frontend/src/types/index.ts` - worker-leaf shape carries `worker:number`; WaveGroup shape carries `step`

## Decisions Made

- The dedup/reset LOGIC was extracted into a pure helper (`wsReplayState.ts`) rather than testing the whole dashboard, because `handleWebSocketMessage` is a `useCallback` closure that is not independently importable (08-08 Task-3 precedent — unit-test the pure decision, do not invent a full-page render harness).
- `event_id` dedup lives at ONE site at the top of the handler covering all event types — the FE now always sends `after_seq` (DashboardLayout always includes it), so the backend replay branch is always entered and persisted-but-not-drained events double-deliver; deduping only the wave branch (the prior state) left every non-wave event undeduped.
- Worker leaves keyed by `data.worker` (worker index), wave groups by `step:waveIndex` — both consume the exact flat 12-06 emit-contract keys (`data.wave_index`, `data.step`, `data.worker`) pinned against `12-06-SUMMARY.md` (no rename/nesting that would silently drop subagent events).

## Contract-Pin Evidence (12-06 emit contract)

The 12-06 emit contract (recorded in `12-06-SUMMARY.md`, Task 2 — CR-06 backend half) stamps `wave_index` (number), `step` (string), `worker` (number) **flat** on the subagent event `data`. This plan's FE consumes EXACTLY those flat keys:

- `data.wave_index` — wave group identity (with `step`)
- `data.step` — wave group + step key (IN-06)
- `data.worker` — worker-leaf key (CR-06 FE half)

No renamed or nested key was consumed; the FE keys match the backend emit contract verbatim, so subagent events fold into the tree rather than being silently dropped. Verified via the acceptance greps (`data.wave_index|data.step|data.worker` present in `page.tsx`).

## Offline Verification Evidence (at checkpoint time)

- `cd frontend && npm test -- --run src/lib/wsReplayState.test.ts` → 6 behavioral tests passed (dedup no-op on repeat id, distinct id true, undefined id pass-through, reset clears seen-set/last-seq/wave-groups, post-reset previously-seen id applies again).
- `cd frontend && npx tsc --noEmit` → clean (full project, extended worker-leaf/WaveGroup shapes typecheck).
- `cd frontend && npx eslint src/lib/wsReplayState.ts src/app/dashboard/page.tsx src/components/workflow/WaveTreePanel.tsx` → 0 errors.
- Emit-contract pin verified against `12-06-SUMMARY.md` (flat `data.wave_index`/`data.step`/`data.worker`).

## Deviations from Plan

None - plan executed exactly as written. Both auto tasks landed their files as specified; the human-verify checkpoint (Task 3) wrote no code.

## Issues Encountered

None.

## Checkpoint Handling — Task 3 (human-verify), auto-approved

Task 3 is a `checkpoint:human-verify` (live visual render + reconnect replay; no headless DOM harness for the FULL dashboard in the repo — 08-08 Task-3 precedent; the vitest unit test covers the dedup/reset decision, live render is human-verified). It was **auto-approved by the orchestrator (auto-mode active)**. Per project convention, live-environment verification is deferred to the end-of-milestone live pass; the offline evidence was green at checkpoint time (6 vitest behavioral tests passed; full-project `tsc --noEmit` clean; eslint 0 errors on touched files; emit-contract pin verified).

**Honest record:** no human visually verified the panel for this plan; the checkpoint was auto-approved under auto-mode and the live render/reconnect verification is deferred to the end-of-milestone live pass.

### Deferred live-UAT checklist (SUPERSEDES the 5 deferred items in 12-04-SUMMARY.md)

These 7 steps SUPERSEDE the 5 deferred items in `12-04-SUMMARY.md` — same surfaces, now **post-fix** (N distinct worker leaves, no duplicate `agent_chunk` on reconnect, per-run reset, no-waves workflow unchanged). The 12-04 items are exercisable now only because 12-05/12-06 closed CR-01/CR-02/CR-06; carry FORWARD this list (not the 12-04 one) to the end-of-milestone live pass:

1. Start the backend: `cd backend && python3.11 -m uvicorn app.main:app --reload`.
2. Start the frontend: `cd frontend && npm run dev`.
3. Run the `sample_wave` workflow (or any workflow whose step uses strategy `wave_scheduler`) from the composer UI.
4. Confirm the `WaveTreePanel` renders wave groups (index + task ids + status badge flipping running→completed) AND worker leaves under each wave — for `sample_wave`'s self×N shape, confirm **N DISTINCT** worker leaves appear in wave 1 (not one collapsed flapping leaf). This is the CR-06 fix made live.
5. Reconnect test: while a wave run is streaming, reload the page (or toggle the network). In the WS frames / network tab confirm the reconnect sends `after_seq`; confirm the tree resumes WITHOUT duplicated wave/worker entries AND the streamed agent text (`agent_chunk`) is NOT duplicated (CR-05 fix). Confirm the missed tail is not lost (CR-01/CR-02 fixes made the durable replay work).
6. Start a SECOND run after the first completes; confirm the previous run's wave panel cleared and a mid-run reconnect on run 2 replays correctly (WR-03 reset).
7. Confirm NO existing panel (AgentProgressPanel / ValidatorIssuePanel / preview) changed for an existing workflow that declares no waves (the tree is empty/absent).

## User Setup Required

None - no external service configuration required. Zero new FE dependencies (reuses the existing vitest harness + `motion/react` + lucide already present).

## Next Phase Readiness

- Phase 12 (Wave Scheduler + Durable Resume [6]) gap-closure plans 12-05/12-06/12-07 are landed — CR-01/CR-02 (durable replay), CR-04/CR-03/WR-01/WR-05/CR-06 backend half (12-06), and the FE CR-05/CR-06/WR-03/IN-05/IN-06 (this plan) are closed.
- RESUME-03 (FE idempotent replay) and WAVE-03 (wave-tree worker-leaf render) requirements satisfied offline.
- One carry-forward: the live wave-render + reconnect UAT (7 steps above) is owed to the end-of-milestone live pass and SUPERSEDES the 5 items previously carried in 12-04-SUMMARY.

## Self-Check: PASSED

- FOUND: frontend/src/lib/wsReplayState.ts (created)
- FOUND: frontend/src/lib/wsReplayState.test.ts (created)
- FOUND: .planning/phases/12-wave-scheduler-durable-resume-6/12-07-SUMMARY.md
- FOUND: commit 04fdf61d (Task 1)
- FOUND: commit ae06d15d (Task 2)

---
*Phase: 12-wave-scheduler-durable-resume-6*
*Completed: 2026-06-11*
