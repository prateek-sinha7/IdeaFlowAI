---
phase: 44-sse-only-hard-cutoff-run-revision-retirement-and-part-b-auto
plan: 01
subsystem: ui
tags: [sse, websocket, react, transport, pipeline, launch-attach, flag-selected]

# Dependency graph
requires:
  - phase: 43-06
    provides: RunConnectionProvider (app-level SSE connection) + useRunStream (WS twin)
  - phase: 29
    provides: REST/SSE twin backend (GET /api/runs/{id}/events/stream, POST /api/runs)
provides:
  - "SSE-sourced pipeline/questionnaire/review-gate down-channel (flag-selected): when NEXT_PUBLIC_SSE_TRANSPORT is ON, runConnection.subscribe feeds handleWebSocketMessage; the WS onMessage is gated off so the reducer sees one transport"
  - "launch->attach bootstrap (R4): sendCommand returns the created run_id and the dashboard calls runConnection.attachRun so a post-boot run streams live without waiting for the next refreshLiveRuns poll"
  - "connectionStatus/reconnect handed to DashboardLayout sourced from runConnection.phase under SSE; the WS reconnect_pipeline frame dormant under SSE"
affects: [W2 (rewire WS commands to REST), W3 (run_revision retirement), W4 (delete /ws/chat + remove the flag), W5 (e2e harness -> SSE)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Flag-selected down-channel: the SSE subscribe feeds the SAME reducer the WS onMessage did; WS is gated off when SSE is active (mirrors the existing chatSubscribe flag-select), so exactly one transport feeds the reducer (idempotent by event_id regardless)"
    - "launch->attach: capture the run_id the POST /api/runs create returns, attach its SSE stream imperatively (attachRun, idempotent set-diff)"
    - "Boundary enum mapping: RunConnectionPhase -> ConnectionStatus mapped at the prop boundary, no global-enum widening (that migration is W4)"

key-files:
  created: []
  modified:
    - "frontend/src/providers/RunConnectionProvider.tsx - sendCommand returns run_id; new attachRun imperative single-run attach"
    - "frontend/src/app/dashboard/page.tsx - SSE subscribe -> handleWebSocketMessage adapter (flag-selected); WS onMessage gated under SSE; launch->attach wiring; connectionStatus/reconnect re-sourced from runConnection.phase"
    - "frontend/src/hooks/useWorkflow.ts - startPipeline returns the launched run_id (SSE path) for launch->attach"
    - "frontend/src/components/layout/DashboardLayout.tsx - the WS reconnect_pipeline effect guarded to a no-op under SSE"

key-decisions:
  - "Kept the pipeline down-channel FLAG-SELECTED (SSE when the flag is ON, WS when OFF) rather than the plan's unconditional enabled={true} + dual-listen — the NEXT_PUBLIC_SSE_TRANSPORT flag is not removed until 44-06, and unconditional SSE would break the flag-OFF path + the mocked e2e suite (orchestrator guardrail = the load-bearing intermediate-state rule)"
  - "Gated the WS onMessage off while SSE is active (exact mirror of chatSubscribe) so the reducer is fed from exactly one transport, instead of dual-listen"
  - "startPipeline returns Promise<string|null>|null (non-async): the WS path returns null SYNCHRONOUSLY so existing sync act(() => startPipeline(...)) test callers stay byte-identical; only the SSE path returns the POST /api/runs promise"

patterns-established:
  - "Pattern: flag-selected transport for the pipeline down-channel — one reducer, transport chosen by runConnection.enabled"
  - "Pattern: imperative single-run SSE attach (attachRun) for launch->attach, de-duped against liveRunIds so it never remounts an existing stream"

requirements-completed: [W1]

# Metrics
duration: 40min
completed: 2026-07-15
---

# Phase 44 Plan 01: Re-source the pipeline down-channel from SSE + launch->attach Summary

**Flag-selected SSE pipeline/questionnaire/review-gate down-channel with a launch->attach bootstrap and phase-sourced connection status — the enabler that lets everything else in Phase 44 verify over SSE-only, while the WS path stays byte-identical when the flag is OFF.**

## Performance

- **Duration:** ~40 min
- **Started:** 2026-07-15T19:44:00Z
- **Completed:** 2026-07-15T20:00:00Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- The pipeline reducer (`handlePipelineMsg` via `handleWebSocketMessage`), the questionnaire panel, and the review-gate panel all update from the per-run SSE fan-out (`runConnection.subscribe`) when the flag is ON — the WS copy is gated off so exactly one transport feeds the reducer.
- launch->attach (R4) wired end-to-end: `sendCommand` now parses `POST /api/runs` and returns the created `run_id`; `startPipeline` surfaces it; the dashboard calls `runConnection.attachRun(run_id)` so a run launched after boot streams live immediately (no wait for the next `refreshLiveRuns` poll). `reattach()` is now also reachable via the reconnect UI under SSE.
- `connectionStatus`/`reconnect` handed to `DashboardLayout` are derived from `runConnection.phase` under SSE (mapped to `ConnectionStatus` at the boundary), and the redundant WS `reconnect_pipeline` frame is dormant under SSE.
- The flag-OFF (WS) path is byte-identical: verified by the mocked Playwright suite staying green.

## Task Commits

Each task was committed atomically:

1. **Task 1: RunConnectionProvider launch-aware (sendCommand returns run_id + attachRun)** - `b2d95be1` (feat)
2. **Task 2: feed the pipeline/questionnaire/review reducer from SSE + launch->attach** - `7d46dc64` (feat)
3. **Task 3: source connectionStatus/reconnect from runConnection.phase under SSE** - `77867f83` (feat)

## Files Created/Modified
- `frontend/src/providers/RunConnectionProvider.tsx` - `sendCommand` parses `POST /api/runs` and resolves the created `run_id` (null for per-run messages / non-2xx create); new `attachRun(runId)` imperative, idempotent single-run attach; context value/DEFAULT_VALUE/memo updated.
- `frontend/src/app/dashboard/page.tsx` - `runConnection.subscribe` -> `handleWebSocketMessage` adapter (subscribed when `sseEnabled`); WS `onMessage` gated off under SSE; launch->attach at the `onStartPipeline` site; `effectiveConnectionStatus`/`effectiveReconnect` derived from `runConnection.phase`/`reattach`; a small `phaseToConnectionStatus` boundary mapper; `useRunChat` `sendCommand` consumer adapted to the new return type.
- `frontend/src/hooks/useWorkflow.ts` - `startPipeline` returns `Promise<string|null>|null` — the POST-create promise (→ run_id) on the SSE path, `null` synchronously on the WS path.
- `frontend/src/components/layout/DashboardLayout.tsx` - imports `useRunConnection`; the WS `reconnect_pipeline` effect early-returns (no-op) while SSE is the active transport.

## Decisions Made
- Kept the down-channel FLAG-SELECTED and left `layout.tsx` flag-gated (see Deviations) — the load-bearing intermediate-state rule for this wave.
- Chose gating the WS `onMessage` off under SSE (exact mirror of `chatSubscribe`) over dual-listen, so exactly one transport feeds the reducer.
- `startPipeline` kept non-async (returns `null` synchronously on the WS path) to preserve the existing sync `act()` test callers.

## Deviations from Plan

### Auto-fixed Issues

**1. [Orchestrator guardrail override] Kept layout.tsx flag-gated instead of `enabled={true}`; down-channel flag-selected, not dual-listen**
- **Found during:** Task 2 (feed pipeline from SSE)
- **Issue:** Plan Task 2 says pass `enabled={true}` to the mounted `RunConnectionProvider` (unconditional SSE) and keep the WS `onMessage` dual-listening. The spawning orchestrator's guardrail explicitly overrides this: the `NEXT_PUBLIC_SSE_TRANSPORT` flag is NOT removed until 44-06, so this wave must stay FLAG-SELECTED (SSE when ON, WS when OFF, mirroring `chatSubscribe`). Unconditional SSE would break the flag-OFF path and the entire mocked e2e suite.
- **Fix:** Left `layout.tsx` unchanged (the provider self-gates on `ENV.SSE_TRANSPORT`); gated the WS `onMessage` off only when `sseEnabled`, and subscribed the SSE fan-out to the reducer only when `sseEnabled`. flag-OFF is byte-identical.
- **Files modified:** frontend/src/app/dashboard/page.tsx (layout.tsx intentionally NOT modified)
- **Verification:** mocked Playwright pipeline/questionnaire/review/cancel/reconnect specs green (flag OFF, WS path); `npx tsc --noEmit` clean.
- **Committed in:** 7d46dc64 (Task 2 commit)

**2. [Rule 3 - Blocking] Modified useWorkflow.ts (not in the plan's files list) to surface the launch run_id**
- **Found during:** Task 2 (launch->attach wiring)
- **Issue:** The launch actually flows through `useWorkflow.startPipeline` -> `runConnection.sendCommand`, not the dashboard directly. The plan text names "the run_id returned by sendCommand/startPipeline", which requires `startPipeline` to return it — but `useWorkflow.ts` was not in `files_modified`.
- **Fix:** `startPipeline` returns `Promise<string|null>|null` (SSE path returns the POST-create promise → run_id; WS path returns `null` synchronously to keep sync `act()` callers byte-identical). The dashboard `onStartPipeline` awaits it via `Promise.resolve(...).then` and calls `runConnection.attachRun`.
- **Files modified:** frontend/src/hooks/useWorkflow.ts, frontend/src/app/dashboard/page.tsx
- **Verification:** `useWorkflow.imagePayload` + `useWorkflow.clarifyRetention` vitest 3/3 green; `npx tsc --noEmit` clean.
- **Committed in:** 7d46dc64 (Task 2 commit)

**3. [Rule 3 - Blocking] Adapted the useRunChat sendCommand consumer to the new return type**
- **Found during:** Task 1 (sendCommand signature change)
- **Issue:** Changing `sendCommand` to `Promise<string|null>` broke the `useRunChat` prop type (`Promise<void> | void`) at `dashboard/page.tsx`.
- **Fix:** Wrapped the consumer to drop the return value (`(runId, payload) => { void runConnection.sendCommand(runId, payload); }`) — no `useRunChat.ts` change needed.
- **Files modified:** frontend/src/app/dashboard/page.tsx
- **Verification:** `npx tsc --noEmit` clean.
- **Committed in:** b2d95be1 (Task 1 commit)

---

**Total deviations:** 3 (1 orchestrator-guardrail override, 2 blocking).
**Impact on plan:** The guardrail override is the intended intermediate-state behavior (flag-selected, not unconditional SSE). The two blocking fixes were mechanical consequences of the required signature changes. No scope creep; the SSE-active behavior the plan specifies is fully delivered — the only difference is it is flag-SELECTED rather than force-on this wave (44-06 removes the flag).

## Issues Encountered
- An initial pass made `startPipeline` an `async` function; that returned a thenable into the existing sync `act(() => startPipeline(...))` test callers and broke 2 previously-passing `useWorkflow` tests. Reworked to a non-async function returning `Promise<string|null>|null` (WS path returns `null` synchronously) — both test files green again (3/3). Caught before committing Task 2.

## Known Stubs
None — all wiring is live (SSE subscribe feeds the real reducer; attachRun mounts a real RunStreamConnection; connection status maps the real phase).

## User Setup Required
None - no external service configuration required. To exercise the SSE path locally set `NEXT_PUBLIC_SSE_TRANSPORT=1`; unset (default) keeps the WS path.

## Next Phase Readiness
- W1 lands: the pipeline down-channel, questionnaire, and review-gate UI now flow from SSE when the flag is ON, and a post-boot run streams live via launch->attach. This is the prerequisite W2/W3/W4 needed.
- W2 (rewire the un-flagged WS commands — gate/cancel/questionnaire — to REST) and W3 (`run_revision` retirement + confirm chip) can now proceed; the returned run_id from launched runs streams over SSE with no extra wiring.
- The flag (`NEXT_PUBLIC_SSE_TRANSPORT`), the WS `onMessage` gate, `chatWsSubscribe`/`legacyChatSend`/`sseEnabled`, and the dormant `reconnect_pipeline` effect are all still present for W4's wholesale de-flagging + `useWebSocket` deletion.

## Self-Check: PASSED
- All 4 modified files present on disk.
- All 3 task commits present in git history (b2d95be1, 7d46dc64, 77867f83).
- `npx tsc --noEmit` clean; mocked pipeline/questionnaire/review/cancel/reconnect specs green (flag OFF).

---
*Phase: 44-sse-only-hard-cutoff-run-revision-retirement-and-part-b-auto*
*Completed: 2026-07-15*
