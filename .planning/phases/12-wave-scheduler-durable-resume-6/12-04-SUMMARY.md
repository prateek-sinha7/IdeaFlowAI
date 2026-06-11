---
phase: 12-wave-scheduler-durable-resume-6
plan: 04
subsystem: ui
tags: [react, nextjs, websocket, typescript, wave-scheduler, durable-resume]

# Dependency graph
requires:
  - phase: 12-wave-scheduler-durable-resume-6 (12-01)
    provides: backend wave_*/subagent_* lifecycle events with seq + event_id on the run stream
  - phase: 12-wave-scheduler-durable-resume-6 (12-03)
    provides: reconnect_pipeline after_seq durable-replay branch (owner-scoped tail replay)
provides:
  - WaveTreePanel — additive props-driven sibling panel rendering wave groups -> worker leaves from wave_*/subagent_* lifecycle events (statuses only, D-14)
  - additive StreamMessage.type entries wave_started/wave_completed/wave_failed/subagent_spawned/subagent_result
  - wave/subagent event routing + event_id dedup (per-run seen-set) in dashboard WS handler
  - last-received-seq tracker + after_seq field on the reconnect_pipeline send (RESUME-03 FE half)
affects: [end-of-milestone live UAT pass, future wave-UI iterations]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "08-08 D-11 sibling-panel: additive props-driven panel; parent routes WS events down (no WS plumbing inside the panel)"
    - "RESUME-03 FE idempotent replay: per-run seen-event_id set + max-seen seq, after_seq on reconnect"

key-files:
  created:
    - frontend/src/components/workflow/WaveTreePanel.tsx
  modified:
    - frontend/src/types/index.ts
    - frontend/src/app/dashboard/page.tsx
    - frontend/src/components/workflow/WorkflowComposer.tsx
    - frontend/src/components/layout/DashboardLayout.tsx

key-decisions:
  - "WaveTreePanel is pure render off a waves prop — parent (dashboard/page.tsx) routes wave_*/subagent_* events down; no WS plumbing inside the panel (08-08 decoupling)"
  - "Lifecycle statuses ONLY in the tree — no subagent_chunk live token stream (D-14)"
  - "after_seq defaults to 0 when no seq recorded (fresh load / legacy client) — backend replays the full tail; on mid-stream reconnect it is the last-seen seq so only the missed tail replays (parity)"
  - "Task 3 live-render/reconnect checkpoint auto-approved (auto-mode); live verification deferred to the end-of-milestone live pass per project convention"

patterns-established:
  - "Wave-tree state shape: { waveIndex, taskIds, status, workers: [{ agent, status }] } assembled from deduped lifecycle events"
  - "event_id seen-set per run makes durable replay idempotent (RESUME-03 FE half) — applies each event at most once"

requirements-completed: [RESUME-03]

# Metrics
duration: ~12min
completed: 2026-06-11
---

# Phase 12 Plan 04: FE Wave/Subagent Tree Panel + Durable Reconnect Summary

**Additive props-driven WaveTreePanel rendering wave groups -> worker leaves from wave_*/subagent_* lifecycle events, plus FE after_seq reconnect with event_id-deduped idempotent replay (RESUME-03 client half) — zero new dependencies, existing-workflow UI untouched.**

## Performance

- **Duration:** ~12 min
- **Tasks:** 3 (2 auto + 1 human-verify checkpoint, auto-approved)
- **Files modified:** 5 (1 created, 4 modified)

## Accomplishments

- `WaveTreePanel.tsx` — additive props-driven sibling panel (cloning the 08-08 ValidatorIssuePanel/AgentProgressPanel shape): renders each wave group (index, task ids, status badge) with its worker leaves (agent + status), lifecycle statuses only (D-14). Pure render off the `waves` prop; mounted additively in `WorkflowComposer.tsx` next to the existing `<ValidatorIssuePanel>` (no existing panel modified).
- Additive `StreamMessage.type` union entries `wave_started | wave_completed | wave_failed | subagent_spawned | subagent_result` (extends the union; renames/removes nothing — mirrors the existing `validator_result`/`validation_warning` additive precedent).
- Wave/subagent event routing in `dashboard/page.tsx` `handleWebSocketMessage`: dedupes by `msg.data.event_id` (per-run seen-set) FIRST, then updates the wave-tree state (`wave_started` adds/updates a group; `wave_completed`/`wave_failed` flip status; `subagent_spawned`/`subagent_result` add/update the matching worker leaf).
- RESUME-03 FE half: the dashboard tracks the max-seen `seq` per run and `DashboardLayout.tsx` sends it as `after_seq` on the `reconnect_pipeline` message so the 12-03 durable replay delivers exactly the missed tail; the shared `event_id` seen-set makes replayed events apply at most once (idempotent — no double-apply).

## Task Commits

1. **Task 1: WaveTreePanel + additive StreamMessage event types + wave/subagent event routing/dedup** - `8733438` (feat)
2. **Task 2: FE reconnect sends after_seq (last-received seq) + idempotent replay** - `a289810` (feat)
3. **Task 3: Human-verify live wave/subagent tree render + reconnect replay** - checkpoint (auto-approved, no code)

**Plan metadata:** (this docs commit)

## Files Created/Modified

- `frontend/src/components/workflow/WaveTreePanel.tsx` - **created** — props-driven wave/subagent tree sibling panel (exports `WaveTreePanelProps`; `"use client"`)
- `frontend/src/types/index.ts` - additive five wave/subagent `StreamMessage.type` entries
- `frontend/src/app/dashboard/page.tsx` - wave/subagent event routing + `event_id` dedup + max-seen `seq` tracker
- `frontend/src/components/workflow/WorkflowComposer.tsx` - additive `<WaveTreePanel>` mount (existing `<ValidatorIssuePanel>` mount unchanged)
- `frontend/src/components/layout/DashboardLayout.tsx` - `after_seq` field on the `reconnect_pipeline` send (existing `type`/`pipeline_run_id` fields unchanged)

## Decisions Made

- WaveTreePanel is pure render off the `waves` prop; the parent routes events down (08-08 decoupling) — no WS plumbing inside the panel.
- Lifecycle statuses only (D-14) — no `subagent_chunk` live token stream in the tree.
- `after_seq` defaults to 0 (fresh load / legacy client) → backend replays the full tail; on a mid-stream reconnect it is the last-seen seq so only the missed tail replays (parity preserved for still-running pipelines).

## Deviations from Plan

None - plan executed exactly as written. Both auto tasks landed their files as specified; the human-verify checkpoint (Task 3) wrote no code.

## Issues Encountered

None.

## Checkpoint Handling — Task 3 (human-verify), auto-approved

Task 3 is a `checkpoint:human-verify` (live visual render + reconnect replay; no headless DOM harness in the repo — 08-08 Task-3 precedent). It was **auto-approved by the orchestrator (auto-mode active)**. Per project convention, live-environment verification is deferred to the end-of-milestone live pass; the offline evidence was green at checkpoint time (full-project `npx tsc --noEmit` clean; eslint on touched files 0 errors).

**Honest record:** no human visually verified the panel for this plan. The following 5 live-verification steps (from the plan's `how-to-verify`) are carried forward as **deferred UAT items** for the end-of-milestone live pass:

1. Start the backend (`cd backend && python3.11 -m uvicorn app.main:app --reload`) and the frontend dev server (`cd frontend && npm run dev`).
2. Run the sample wave workflow (`sample_wave`) — or any workflow whose step uses strategy `wave_scheduler` — from the composer UI.
3. Confirm the WaveTreePanel renders: wave groups appear with index + task ids + a status badge that flips running → completed as each wave finishes; worker leaves appear under their wave with agent + status (statuses only, no live token stream).
4. Confirm NO existing panel (AgentProgressPanel / ValidatorIssuePanel / preview) changed appearance for an existing workflow that declares no waves (the tree is empty/absent).
5. Reconnect test: while a wave run is streaming, reload the page (or toggle the network). Confirm the reconnect sends `after_seq` (visible in the WS frames / network tab) and the tree resumes WITHOUT duplicated wave/worker entries (event_id dedup) and without losing the missed tail.

## User Setup Required

None - no external service configuration required. Zero new FE dependencies (reuses `motion/react` + lucide already present).

## Next Phase Readiness

- Phase 12 (Wave Scheduler + Durable Resume [6]) is the final mapped phase — 4 of 4 plans complete.
- The wave/subagent FE surface (§22 / API-03) and the RESUME-03 client half (after_seq + event_id dedup) are landed; backend wave events (12-01) + durable replay (12-03) are wired through.
- One blocker/carry-forward: the live wave-render + reconnect UAT (5 steps above) is owed to the end-of-milestone live pass.

## Self-Check: PASSED

- FOUND: frontend/src/components/workflow/WaveTreePanel.tsx (created)
- FOUND: .planning/phases/12-wave-scheduler-durable-resume-6/12-04-SUMMARY.md
- FOUND: commit 8733438 (Task 1)
- FOUND: commit a289810 (Task 2)

---
*Phase: 12-wave-scheduler-durable-resume-6*
*Completed: 2026-06-11*
