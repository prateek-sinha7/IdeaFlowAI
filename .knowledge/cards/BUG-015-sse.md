---
id: BUG-015-sse
type: bug
status: done
area: [backend, sse, agents, runtime]
files:
  - backend/app/api/run_stream.py
summary: >-
  Completed run's SSE stream reconnects FOREVER ("Reconnecting…" banner flaps
  constantly after a run finishes)
source: .planning/SSE-QA-BUG-LOG.md#bug-015
campaign: sse
severity: "🟠 major"
---

### BUG-015 — Completed run's SSE stream reconnects FOREVER ("Reconnecting…" banner flaps constantly after a run finishes)  [🟠 major] [FIXED ✅]
- **RESOLVED:** FIXED (quick 260717-1c1, `f60c7bcc`/`43f7f6ab`) — FE: `useRunStream` now tracks `sawNonLiveAttachRef` (set on `stream_attached{live!==true}`, reset at the top of each `connect()`) and on the close branch (`:370-372`) settles `setPhase("disconnected")` WITHOUT `scheduleReconnect()` when the last attach was non-live — so a finished stream stops looping while a genuine live-drop still reconnects; PLUS `RunConnectionProvider.detachRun(runId)` called from the `pipeline_complete` handler (via a `detachRunRef` synced through the empty-deps closure) releases the focus so the completed run's `RunStreamConnection` unmounts (no reconnect, no ~14k-event re-replay). RED→GREEN vitest (A1 non-live-close→`disconnected` 2 failed→9 passed; A2 live-close still reconnects; detachRun test). Plan-checked (0 blockers) + verifier; tsc clean; transport vitest 69, mocked SSE/gate e2e 41/0. FE-only. **Applied** (frontend restarted).
- **Found:** 2026-07-17 (user-reported, live) · after a prototype run COMPLETES + the preview is available, a yellow "Reconnecting…"/"Connection lost." banner flaps over and over.
- **Root cause (deep-investigation agent + orchestrator curl + source spot-check):** the FE keeps a launched-then-completed run's SSE stream ATTACHED and `useRunStream` reconnects on every terminal close. Chain: (1) backend closes a terminal run's stream after replay — `backend/app/api/run_stream.py`: for a finished run `live_queue is None` → replay the durable tail + ONE `stream_attached{live:false}` handshake → `return`/close (curl-verified on `4675daa7`: `"live": false`, NO `event: done`); (2) `frontend/src/hooks/useRunStream.ts:370-372` reconnects on ANY close — sole guard `!stoppedRef && !aborted` (both false), NO terminal check — and IGNORES the `stream_attached{live:false}` (`:267` reacts only to `live===true`); (3) the launch `attachRun(launchedRunId)` (`frontend/src/app/dashboard/page.tsx:1521`) pins the run as the sticky focus UNGATED (only the r7d REOPEN attach was terminal-gated, `page.tsx:1262`), and nothing releases it on `pipeline_complete` (`page.tsx:537-554`). → reconnect → re-replay ~13,928 events + close → LOOP → the phase-driven banner (`DashboardLayout.tsx:1448-1457`) flaps each backoff. **PRE-EXISTING** (reconnect-on-close + live-only stream_attached gate from Phase 29-07 `0429faef`, dormant behind WS, activated by 44-06 cutover); **NEWLY VISIBLE post-BUG-014-B** (before, the run never reached "completed" on the live screen — it stuck at "0/0 BUILDING"). The launch-complete sibling of the r7d reopen-gate.
- **Fix (PROPOSED, FE-only, not applied):** (1) PRIMARY — `useRunStream` must NOT `scheduleReconnect()` after a `stream_attached{live:false}`-then-close; settle to a quiescent phase (localized to the hook, protects every terminal-attach path). (2) COMPLEMENTARY — add a `detachRun`/release-focus to `RunConnectionProvider` + call it from the `pipeline_complete` handler for the tracked run (unmounts the dead stream; kills the 14k-event re-replay). Backend is CORRECT — do NOT hold terminal streams open.
