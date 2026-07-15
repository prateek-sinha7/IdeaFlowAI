---
phase: 44-sse-only-hard-cutoff-run-revision-retirement-and-part-b-auto
plan: 09
subsystem: testing
tags: [playwright, e2e, sse, rest, mock-harness, transport, frontend]

# Dependency graph
requires:
  - phase: 44-06
    provides: SSE made the sole, unconditional run transport (useWebSocket / /ws/chat deleted)
  - phase: 44-04/44-05
    provides: the REST up-channel command rewires (gate/cancel/answers/revisions/messages)
provides:
  - Mocked Playwright harness re-pointed from WS to SSE — mockSse is the sole run driver
  - mockSse.ts grown to full pipeline-emit parity + a REST up-channel command mock (waitForCommand)
  - dashboard.ts + test.ts re-pointed to SSE/REST; mockWs.ts deleted (routeWebSocket retired)
  - ts-sse.spec.ts drives the MOUNTED app; the ~132-spec mocked suite is green over SSE
affects: [44-10, e2e, frontend-run-screen, sse-transport]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Mocked SSE down-channel via page.route text/event-stream + durable frame tail"
    - "REST up-channel command capture (normalized {type,...}) replacing WS outbound-frame asserts"
    - "Lazy per-run SSE attach (live-run registry surfaced on GET /api/runs + page 'online' nudge)"
    - "Discrete-commit delivery: serve terminal frames in a separate response so isRunning commits first"

key-files:
  created: []
  modified:
    - frontend/e2e/fixtures/mockSse.ts
    - frontend/e2e/fixtures/dashboard.ts
    - frontend/e2e/fixtures/test.ts
    - frontend/e2e/fixtures/constants.ts
    - frontend/e2e/fixtures/scenarios.ts
    - frontend/e2e/tests/ts-sse.spec.ts
    - frontend/e2e/tests/ts-sse-resilience.spec.ts
    - frontend/e2e/tests/ts-s.reconnect.spec.ts
    - frontend/e2e/tests/ts-q.terminal-states.spec.ts
    - frontend/e2e/tests/ts-l.token-usage.spec.ts
    - frontend/e2e/tests/ts-j.streaming.spec.ts
    - frontend/e2e/tests/ts-x.timing.spec.ts
    - frontend/e2e/tests/ts-y.resilience.spec.ts
  deleted:
    - frontend/e2e/fixtures/mockWs.ts

key-decisions:
  - "mockSse owns the whole run harness (SSE stream + REST command mock + live-run registry); mockWs.ts deleted"
  - "Serve terminal frames (complete/failed/cancelled) in a SEPARATE SSE response so the app commits isRunning=true + its pipeline_type/tab sync before the terminal (faithful discrete-frame delivery)"
  - "Reconcile retired WS-transport specs to SSE-native equivalents (reconnect_pipeline handshake -> Last-Event-ID reattach; client keepalive ping -> fixme) rather than deleting them"

patterns-established:
  - "waitForCommand(kind) is the SSE/REST heir of waitForClientFrame — assert the recorded REST command, not a WS frame"
  - "Wait for a content-completion's auto-tab (Preview selected) before reading a Steps surface — SSE delivers pipeline_complete asynchronously"

requirements-completed: [W5]

# Metrics
duration: ~2h 30m
completed: 2026-07-15
---

# Phase 44 Plan 09: W5a — Re-point the Mocked e2e Harness from WS to SSE Summary

**The mocked Playwright harness now drives the app over a mocked SSE down-channel + a REST up-channel command mock (mockSse); the ~132-spec suite is green over SSE (132 passed / 0 failed / 43 skipped), with mockWs / routeWebSocket(/ws/chat) fully retired.**

## Performance

- **Duration:** ~2h 30m
- **Completed:** 2026-07-15
- **Tasks:** 3 (+ stabilisation + docs)
- **Files modified:** 32 modified, 1 deleted (33 total)

## Accomplishments
- Grew `MockSse` into the sole run-harness driver: full pipeline-emit parity (`start`/`planner*`/`agent*`/`wave*`/`subagent*`/`questionnaire*`/`reviewGate*`/`complete`/`failed`/`cancelled`/`reconnected` + chat helpers) served over the mocked SSE stream, plus a REST up-channel command mock (`POST /api/runs` + `/{id}/{answers,cancel,gate,revisions,messages}`) with `waitForCommand`.
- Re-pointed the page-object (`dashboard.ts`) and the auto-fixture (`test.ts`) onto SSE/REST; deleted `mockWs.ts`; re-pointed every mocked spec off the `mockWs` fixture onto `mockSse`.
- Upgraded `ts-sse.spec.ts` to drive the MOUNTED app (launch renders from the SSE emit; gate/cancel asserted on the recorded REST commands) — dropped the synthetic `fetchSse` consumer.
- Restored the full mocked Playwright suite to green: **132 passed / 0 failed / 43 skipped** (two consecutive clean runs at default parallelism), back to the pre-Phase-44 baseline.

## Task Commits

1. **Task 1: grow mockSse to pipeline parity + REST command mock** — `47e5ba87` (test)
2. **Task 2: re-point dashboard page-object + fixture to SSE** — `c790221d` (test)
3. **Task 3: upgrade ts-sse to drive the mounted app + reconcile SSE cutover** — `d5ab4f3c` (test)
4. **Stabilise the SSE-driven suite to a clean mocked gate** — `10456205` (test)
5. **Re-point e2e README + FIXTURE-CONTRACT to the SSE/REST harness** — `d69cc2ac` (docs)

## Files Created/Modified
- `frontend/e2e/fixtures/mockSse.ts` — the sole run driver: mocked SSE down-channel (pipeline + chat emit helpers, long-poll serve, drop/expire), REST up-channel command mock (`waitForCommand`), lazy per-run attach, discrete-commit terminal split.
- `frontend/e2e/fixtures/dashboard.ts` — drop `ws.ready()`; `runWith` waits on the recorded `POST /api/runs`; `openSteps()` re-clicks past a raced auto-tab; add `waitForRunSettled()`.
- `frontend/e2e/fixtures/test.ts` — `mockSse` is the auto-fixture (depends on `mockApi` so its route wins).
- `frontend/e2e/fixtures/constants.ts` — drop `WS_URL_RE` / the `/ws/chat` reference.
- `frontend/e2e/fixtures/scenarios.ts` — retype the run players against `MockSse`.
- `frontend/e2e/fixtures/mockWs.ts` — **deleted** (routeWebSocket(/ws/chat) retired).
- `frontend/e2e/tests/*.spec.ts` — re-pointed off `mockWs`; `waitForClientFrame("run_pipeline")` -> `waitForCommand`; SSE reconciliations (see Deviations).
- `frontend/e2e/{README.md,FIXTURE-CONTRACT.md}` — re-pointed the harness docs to SSE/REST.

## Decisions Made
- **mockSse is the whole harness** (SSE stream + REST command mock + live-run registry), replacing mockWs entirely — the plan's "grow mockSse to parity + delete mockWs" path.
- **Discrete-commit delivery via a terminal-frame split.** A single buffered SSE body batches `pipeline_start`+`pipeline_complete` into one React commit, so the `isRunning`-gated `workflowType`/tab syncs never fire. Serving any terminal frame in a separate response restores the WS path's discrete-commit behaviour (needed for ts-o/ts-p deliverable rendering + the 42-02 state-keyed tab).
- **Reconcile, never delete, retired WS behaviours.** The WS `reconnect_pipeline` handshake and the 20s client keepalive ping do not exist under SSE (native `Last-Event-ID` reattach + server heartbeat). ts-s was reconciled to assert the SSE reattach; TS-X-01 was converted to a documented `test.fixme` (SSE liveness is covered by ts-sse-resilience + TS-Y-01).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] SSE buffered delivery batched start+complete into one commit**
- **Found during:** Task 3 (running the mocked suite)
- **Issue:** ts-o/ts-p deliverable-render specs went red — the `isRunning`-gated `workflowType` sync (PreviewPanel/DashboardLayout) never fired because a single buffered SSE body committed `pipeline_start`→`pipeline_complete` in one React batch.
- **Fix:** `mockSse.handleStream` serves any terminal frame (`pipeline_complete`/`failed`/`cancelled`) in a SEPARATE response, so the live-run state commits first (faithful to the retired WS discrete-frame delivery).
- **Files modified:** frontend/e2e/fixtures/mockSse.ts
- **Verification:** ts-o + ts-p (14 tests) green.
- **Committed in:** d5ab4f3c

**2. [Rule 1 - Bug] TS-Q-05 asserted the neutral empty-state on the wrong (auto-tabbed) tab**
- **Found during:** Task 3 (deterministic failure at workers=1)
- **Issue:** With discrete delivery, an empty completion is terminal-idle and auto-tabs to Steps (42-02), so the Preview empty-state is not on the selected tab — matching the real app, exposing a stale test assumption.
- **Fix:** open the Preview tab before asserting `previewEmpty()` (mirrors TS-R-03's established pattern).
- **Files modified:** frontend/e2e/tests/ts-q.terminal-states.spec.ts
- **Committed in:** d5ab4f3c

**3. [Rule 1 - Bug] TS-J/TS-L raced the async completion's auto-tab-to-Preview**
- **Found during:** Task 3 stabilisation (parallel-load failures)
- **Issue:** `complete()` then `openSteps()`/read-Steps assumed synchronous completion; over SSE the `pipeline_complete` lands ~1s later and its auto-tab clobbers the Steps click.
- **Fix:** wait for the content-completion auto-tab (`previewTab` aria-selected) before opening Steps; `openSteps()` re-clicks until Steps is selected.
- **Files modified:** frontend/e2e/tests/ts-j.streaming.spec.ts, frontend/e2e/tests/ts-l.token-usage.spec.ts, frontend/e2e/fixtures/dashboard.ts
- **Committed in:** d5ab4f3c, 10456205

**4. [Rule 3 - Blocking] Retired WS-transport specs (reconnect handshake, keepalive ping, connectionCount==1)**
- **Found during:** Task 3
- **Issue:** ts-s asserted the WS `reconnect_pipeline` frame; TS-X-01 the 20s client ping; TS-Y-01 `connectionCount===1` — none exist under SSE (native reattach, server heartbeat, per-serve re-attach).
- **Fix:** reconcile ts-s to the SSE `Last-Event-ID` reattach; TS-X-01 -> documented `test.fixme`; TS-Y-01 asserts the attach counter advances past the drop baseline.
- **Files modified:** ts-s.reconnect.spec.ts, ts-x.timing.spec.ts, ts-y.resilience.spec.ts
- **Committed in:** d5ab4f3c, 10456205

**5. [Rule 3 - Blocking] ts-sse-resilience/ts-sse referenced the deleted mockWs fixture**
- **Found during:** Task 2 (typecheck)
- **Issue:** both imported `mockWs`/`installMockSse(page, mockWs)`/`sse.handle` — would not compile after the fixture rename + MockSse rewrite.
- **Fix:** ts-sse rewritten to drive the mounted app; ts-sse-resilience adapted to the `mockSse` fixture with `autoAttach=false` (hand-driven transport, no competing app stream).
- **Files modified:** ts-sse.spec.ts, ts-sse-resilience.spec.ts
- **Committed in:** c790221d, d5ab4f3c

---

**Total deviations:** 5 auto-fixed (3 bugs, 2 blocking). All within the e2e harness scope (T-44-09-01: every red classified as selector/behaviour-drift and reconciled, never silently skipped).
**Impact on plan:** No scope creep — all changes under `frontend/e2e/`; the plan's W5a intent (SSE re-point + green suite) is fully met.

## Issues Encountered
- **Parallel-load flakiness.** The SSE mock reconnects after every serve (Playwright `route.fulfill` cannot stream), so under full-parallel dev-server load a few timing-sensitive specs intermittently timed out. Mitigated by (a) holding an idle stream open past the test timeout instead of empty-serving every ~10s (kills the "Reconnecting…" reconnect churn), and (b) the settle-before-read fixes above. Result: two consecutive clean full runs (132/0/43) at default parallelism.

## Known Harness Limitations
- **Per-serve reconnect artifact.** Because `route.fulfill` closes after each serve, the app treats each stream-close as a drop and reconnects (1s backoff) — a real backend keeps one long-lived SSE stream. This is invisible functionally (no spec asserts its absence) but means `connectionCount` is monotonic (not a single persistent socket) and a transient "Reconnecting…" phase can appear after each frame batch. Documented so a future harness (e.g. a streaming test server) can remove it.

## Threat Flags
None — the harness edits introduce no new production trust boundaries (T-44-09-SC: no package installs; test-harness edits only).

## Next Phase Readiness
- The mocked suite is SSE-driven and green — ready for 44-10's banned-pattern gate (no `routeWebSocket` / `/ws/chat` / `waitForClientFrame("run_pipeline")` / `ws.ready()` remain under `frontend/e2e`).
- No `frontend/src` or backend files were touched (e2e harness only).

## Self-Check: PASSED
- FOUND: 44-09-SUMMARY.md
- FOUND: frontend/e2e/fixtures/mockSse.ts
- CONFIRMED: frontend/e2e/fixtures/mockWs.ts deleted
- FOUND commits: 47e5ba87, c790221d, d5ab4f3c, 10456205, d69cc2ac
- Gate: `playwright test --project=mocked` → 132 passed / 0 failed / 43 skipped (two consecutive clean runs)
- Banned-pattern grep (routeWebSocket / /ws/chat / waitForClientFrame("run_pipeline") / ws.ready()) under frontend/e2e → 0 matches

---
*Phase: 44-sse-only-hard-cutoff-run-revision-retirement-and-part-b-auto*
*Completed: 2026-07-15*
