---
phase: 16-terminal-state-integrity-and-reconnect-frame-contract
plan: 02
subsystem: api
tags: [websocket, asyncio, cancellation, execution-engine, cooperative-cancel]

# Dependency graph
requires:
  - phase: 16-01
    provides: engine error-arm (pipeline_failed on runner error) — same engine consume/terminal region this plan extends with the pre-agent cancel terminal
  - phase: 14
    provides: _handle_revision real revision dispatch + the per-run-queue + drainer pattern the cooperative cancel wires into
provides:
  - "cancel_pipeline delivers pipeline_cancelled on the live wire via a cooperative per-run cancel_event (FE clears in-flight cards; DB row cancelled)"
  - "engine pre-agent cancel break emits pipeline_cancelled instead of falling through to pipeline_complete"
  - "per-run _CANCEL_EVENTS map + run_id_sink connection handle (owner/connection-scoped Stop)"
  - "asyncio.timeout() at the 3 queue-get drainers (CPython-3.11 primitive, no result-vs-cancel swallow)"
  - "deterministic cancel tests asserting live-wire pipeline_cancelled delivery (main + revision)"
affects: [reconnect-replay, terminal-state-fidelity, frontend-card-clearing]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Cooperative cancel: set a per-run asyncio.Event the engine observes per-chunk/pre-agent; the bg task survives and emits the terminal through the normal persisted+drained path (vs destructive task.cancel() that kills the drainer before the terminal drains)"
    - "Destructive cancel kept ONLY on the WebSocketDisconnect path (no socket to ack; durable replay covers reconnect)"
    - "asyncio.timeout() over asyncio.wait_for() for queue-get drainers"

key-files:
  created: []
  modified:
    - backend/agents/execution_engine/engine.py
    - backend/app/api/websocket.py
    - backend/tests/unit/test_pipeline_cancel.py
    - backend/tests/unit/test_run_revision_ws_dispatch.py

key-decisions:
  - "Single mechanism per drainer: the cooperative cancel_event is the sole cancel fix for BOTH the main and revision drainers — the WR-01 residual-drain stays a documented fallback only (no dual mechanism per path)"
  - "cancel_pipeline resolves the per-run event via a connection-scoped run_id_sink (single-element list the handler republishes into) — preserving owner/connection scoping (T-16-02-TENANT); no cross-connection client-supplied-run-id lookup"
  - "A defensive destructive-cancel fallback remains inside cancel_pipeline ONLY for the (rare) case where no cooperative event is resolvable; the primary path is cancel_event.set()"

patterns-established:
  - "Cooperative-cancel-event wiring: create per run, register in a module map keyed by run_id, publish run_id to the connection, set() on Stop, clean up in _cleanup_pipeline"

requirements-completed: [ISS-007, ISS-002]

# Metrics
duration: ~30min
completed: 2026-06-13
---

# Phase 16 Plan 02: Cooperative Cancel Delivery (ISS-007 + ISS-002) Summary

**cancel_pipeline now sets a per-run cooperative asyncio.Event the engine observes per-chunk/pre-agent so pipeline_cancelled reaches the live wire (FE clears in-flight cards, DB row cancelled) — replacing the destructive task.cancel() that killed the drainer before the terminal drained.**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-06-13T12:55Z
- **Completed:** 2026-06-13T13:10Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- **ISS-007 closed:** a real Stop delivers `pipeline_cancelled` on the live wire. The cooperative `cancel_event` is set instead of `current_pipeline_task.cancel()`; the bg task survives, the engine emits `pipeline_cancelled` through the normal persisted+drained path, and the still-alive drainer forwards it before breaking on the terminal.
- **ISS-002 closed:** `test_pipeline_cancel.py` passes deterministically (3× run, no result-vs-cancel race) — the ack is no longer race-dependent.
- **Engine pre-agent cancel gap closed:** the `engine.py:1509` step-boundary break now transitions to `cancelled` and yields `pipeline_cancelled` (mirroring the outer cooperative terminal :1670-1678 and the WR-03 gate-reject precedent), instead of falling through to `pipeline_complete`.
- **Defense-in-depth:** the 3 queue-get drainers (reconnect / main / revision) use `asyncio.timeout()` in place of `asyncio.wait_for()`.
- **DB fidelity:** the cooperative `pipeline_cancelled` normal-yield now persists `cancelled` on both drainers (a Rule 2 addition — without it the clean async-for completion would mis-mark the run `completed`).
- **WebSocketDisconnect path unchanged** — keeps destructive `task.cancel()`; `test_disconnect_path_cancels_running_task` stays green.

## Task Commits

1. **Task 1: Wire the cooperative cancel_event (engine pre-agent gap + websocket cancel/drainer/timeout)** — `edd975f1` (fix)
2. **Task 2: Cancel-delivery tests — main ack + revision row 'cancelled' tightening** — `2256ccd8` (test)

_Note: both tasks are tdd="true"; the cooperative-stub + test changes were committed alongside the production change they pin (Task 1's test_pipeline_cancel.py update is the RED→GREEN for the cooperative path)._

## Files Created/Modified
- `backend/agents/execution_engine/engine.py` — pre-agent cancel break emits `pipeline_cancelled` (transition→cancelled + persist-budget-if-active + yield + return); `_handle_revision` accepts + threads `cancel_event` into `self.execute(...)`.
- `backend/app/api/websocket.py` — `_CANCEL_EVENTS` per-run map + `_cleanup_pipeline` pop; per-connection `_run_id_sink`; `cancel_pipeline` sets the cooperative event (destructive fallback only when no event resolvable); both handlers create+register+publish the event and pass `cancel_event` to the engine; `pipeline_cancelled`-seen tracking → persist `cancelled` (main + revision); 3 queue-get drainers → `asyncio.timeout()`.
- `backend/tests/unit/test_pipeline_cancel.py` — stub engine observes `cancel_event` per-chunk and emits `pipeline_cancelled`; main ack test drives the cooperative path (`_CANCEL_EVENTS[run_id].set()`), asserts exactly one live-wire ack + row `cancelled`, handler completes normally (no CancelledError).
- `backend/tests/unit/test_run_revision_ws_dispatch.py` — `test_cancellation_lands_row_cancelled` rewritten to the cooperative path, requires `pipeline_cancelled` in `ws.sent` (live wire) riding the drainer wrapper (section = target_artifact_type); one stub-signature fix (`run_id_sink=None`) for the overlap-guard test.

## Decisions Made
- **No dual mechanism per path:** the cooperative `cancel_event` is the single cancel fix for BOTH the main and revision drainers; the WR-01 residual-drain stays a documented fallback and is NOT wired on the cancel path.
- **Owner/connection scoping preserved (T-16-02-TENANT):** the cancel handler resolves the event via the connection-scoped `_run_id_sink` the handler republishes into — only the connection that started the run can Stop it; no client-supplied-run-id cross-connection lookup was introduced.
- **No sync ack in the cancel handler** (a REJECTED hack): the bg task owns the ack; the cooperative event is precisely what removes the ack-vs-DB-write race.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Persist `cancelled` on the cooperative `pipeline_cancelled` normal-yield**
- **Found during:** Task 1
- **Issue:** On the cooperative path the engine emits `pipeline_cancelled` as a NORMAL yield (not via CancelledError), so the bg task's async-for completes cleanly and falls into the success-persist block — which would mis-mark a cooperatively-cancelled run `completed` (the existing CancelledError handler only covers the destructive path).
- **Fix:** Added `pipeline_cancelled_seen` tracking in both `_run_pipeline_to_queue` and the revision `_queue_send`, with a `cancelled` arm in the persist/terminal-status logic (parity with the CancelledError handler).
- **Files modified:** backend/app/api/websocket.py
- **Verification:** `test_pipeline_cancel.py` + `test_cancellation_lands_row_cancelled` assert `row.status == "cancelled"`; pass deterministically.
- **Committed in:** `edd975f1` / `2256ccd8`

**2. [Rule 1 - Bug] Stub-signature fix for the overlap-guard test**
- **Found during:** Task 1 (regression check)
- **Issue:** `test_overlap_guard_rejects_second_run_revision` monkeypatches `_handle_revision_execution` with a stub that did not accept the new `run_id_sink` kwarg → `unexpected keyword argument`.
- **Fix:** Added `run_id_sink=None` to the test stub signature.
- **Files modified:** backend/tests/unit/test_run_revision_ws_dispatch.py
- **Verification:** the full `test_run_revision_ws_dispatch.py` suite passes (19→ green).
- **Committed in:** `edd975f1`

---

**Total deviations:** 2 auto-fixed (1 missing-critical, 1 blocking-bug)
**Impact on plan:** Both auto-fixes are correctness requirements directly caused by the Task-1 cooperative wiring. No scope creep — both stay within the named files.

## Issues Encountered
None beyond the two auto-fixed deviations above.

## INV-3 Parity Proof
- 5 characterization goldens (prototype / od_prototype / prototype_revision / od_ppt / app_builder) + `test_banned_patterns` + `test_migration_ledger`: **44 passed, 7 skipped** (SNAPSHOT_UPDATE unset; byte/event-identical — the scripted model never cancels, so the new cooperative/pre-agent arms are dormant on goldens).
- `lint-imports`: **4 kept / 0 broken.**
- SC-001: `grep -nE 'if pipeline_type ==|spec.id =='` in engine.py → **0** (every cancel branch keys on the generic cancel signal; no workflow/model/provider literal).
- Zero new tables / migrations (`git status --porcelain` shows no alembic file).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- ISS-007 + ISS-002 closed offline. Live-Bedrock re-check of pipeline_cancelled delivery is deferred to the next live pass per the defer-live-verification convention.
- The cooperative cancel_event + run_id_sink pattern is available for any future Stop-driven path.

## Self-Check: PASSED
- SUMMARY.md present on disk.
- Commits `edd975f1` (Task 1) + `2256ccd8` (Task 2) verified in git log.

---
*Phase: 16-terminal-state-integrity-and-reconnect-frame-contract*
*Completed: 2026-06-13*
