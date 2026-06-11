---
phase: 12-wave-scheduler-durable-resume-6
plan: 09
subsystem: api
tags: [websocket, asyncio, resume, sqlalchemy, scoped-store, import-linter]

# Dependency graph
requires:
  - phase: 12-wave-scheduler-durable-resume-6 (12-03)
    provides: resume_run / restore_non_terminal_runs / _recover_workspace_id / the after_seq durable replay branch
  - phase: 12-wave-scheduler-durable-resume-6 (12-05)
    provides: reconnect_pipeline workspace recovery (CR-02) + pipeline_reconnected status report
  - phase: 05-typed-artifacts-persistence-ownership-1b
    provides: ScopedStore default-deny owner+workspace scoping + set_run_scope seam
provides:
  - Injected engine→WS live-task bridge (3 optional ExecutionEngine hooks, wired in app/main.py) so auto-resumed runs register queue+task in _PIPELINE_QUEUES/_PIPELINE_TASKS
  - Reconnect during an auto-resumed run live-attaches (live:true) and receives the resumed tail incl. pipeline_complete
  - workflow_runs.workspace_id stamped consistently with the run_events sink via authz.set_run_scope (pipeline_reconnected.status non-null)
  - _stamp_resume_marker persists run_resuming under the recovered real workspace_id (no NOT NULL IntegrityError)
affects: [12-10, frontend reconnect handler (12-08), milestone live UAT pass]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Engine→app-layer bridge as injected callables set at startup (kernel never imports app.api; import-linter direction held)"
    - "Single workspace-stamping seam: authz.set_run_scope reused for the forward path (revision path already rode it)"

key-files:
  created:
    - backend/tests/agents/test_resume_ws_bridge.py
    - backend/tests/agents/test_resume_marker_workspace.py
  modified:
    - backend/agents/execution_engine/engine.py
    - backend/app/api/websocket.py
    - backend/app/main.py

key-decisions:
  - "Bridge shape = two register callables + one cleanup callable (queue/task/cleanup), all default None — dormant bridge is byte/event-identical for every offline construction path"
  - "Cleanup reuses websocket._cleanup_pipeline injected as _resume_cleanup (no parallel cleanup path)"
  - "Gap 2c fixed by consistent stamping via the EXISTING set_run_scope seam, NOT by widening get_run to owner-only (AUTHZ-01/03 default-deny preserved)"
  - "_stamp_resume_marker prefers _recover_workspace_id (run_events-sourced) over wr.workspace_id even post-fix, so the marker always matches the sink scope"
  - "authz.py needed NO edit — set_run_scope already was the exact seam (plan's files_modified prediction included it; reuse confirmed INV-3/INV-12)"

patterns-established:
  - "Injected-callback bridge: when the kernel must reach an app-layer registry, the app layer injects callables onto the engine instance at startup (single wiring site in app/main.py)"
  - "Best-effort ORM handlers capture row scalars up front so an except never lazy-loads off a flush-poisoned session"

requirements-completed: [RESUME-04, RESUME-03, WAVE-03]

# Metrics
duration: 10min
completed: 2026-06-11
---

# Phase 12 Plan 09: Resume WS Bridge + Workspace Consistency Summary

**Auto-resumed runs now register in the WS pipeline registry via an injected engine→WS bridge (live-attach reconnect delivers the resumed tail incl. pipeline_complete), workflow_runs.workspace_id is stamped consistently with the run_events sink via set_run_scope (pipeline_reconnected.status non-null), and the run_resuming marker persists under the recovered real workspace_id (no NOT NULL IntegrityError).**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-06-11T13:54:06Z
- **Completed:** 2026-06-11T14:04:37Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- **Gap 2a closed:** `ExecutionEngine` gained three optional injected hooks (`_resume_register_queue` / `_resume_register_task` / `_resume_cleanup`, all default `None`). `resume_run` registers the run's live queue before the drive loop, pushes every resumed event onto it (mirroring the `run_pipeline` queue contract), and terminates with the `None` sentinel + `_cleanup_pipeline`. `restore_non_terminal_runs` registers the driver task at the `create_task` site. `app/main.py` is the single wiring site — the kernel never imports `app.api` (import-linter 4 kept / 0 broken).
- **Gap 2c closed:** `_execute_impl` stamps the resolved workspace back onto the `workflow_runs` row via the existing `authz.set_run_scope` seam right after workspace resolution, so the owner+workspace-scoped `get_run` on reconnect resolves and `pipeline_reconnected.status` is non-null. Best-effort with the IN-02 cross-owner `PermissionError` guard intact.
- **Marker NOT NULL fixed:** `_stamp_resume_marker` recovers the run's real workspace_id via `_recover_workspace_id` (the run_events-sourced value) instead of passing the WS-path row's NULL `wr.workspace_id` — the `run_resuming` marker now persists at the contiguous next seq on every in-process auto-resume.
- **Parity proven:** 5 characterization snapshots byte/event-identical (10 passed); resume/replay suites (14 passed); migration-ledger + registry lockstep (107 passed); dormant-bridge parity test pins resume_run unchanged when hooks are unset.

## Task Commits

Each task was committed atomically:

1. **Task 1: Inject engine→WS live-task bridge for auto-resumed runs (Gap 2a)** - `0da2315d` (feat)
2. **Task 2: Consistent workflow_runs.workspace_id + marker workspace recovery (Gap 2c + NOT NULL)** - `a09f7b35` (fix)

## Files Created/Modified

- `backend/agents/execution_engine/engine.py` - 3 injected bridge hooks in `__init__`; queue registration + live push + sentinel/cleanup in `resume_run`; task registration at the `restore_non_terminal_runs` create_task site; `set_run_scope` stamping in `_execute_impl`; `_recover_workspace_id`-sourced marker workspace in `_stamp_resume_marker`
- `backend/app/api/websocket.py` - `_register_resume_queue` / `_register_resume_task` app-layer bridge functions over the existing `_PIPELINE_QUEUES`/`_PIPELINE_TASKS` registry (legacy `run_pipeline` registration path unchanged)
- `backend/app/main.py` - single wiring site: hooks set on the engine instance before `restore_non_terminal_runs`
- `backend/tests/agents/test_resume_ws_bridge.py` - queue registered before drive; full resumed tail incl. pipeline_complete on the live queue; None sentinel; cleanup; task registration; dormant-bridge parity; no-app.api-import source check
- `backend/tests/agents/test_resume_marker_workspace.py` - set_run_scope resolves scoped get_run (IDOR ∅ + IN-02 PermissionError preserved); engine drive stamps workflow_runs.workspace_id == run_events workspace; marker persists under recovered workspace at seq N+1; no-durable-rows path never raises

## Decisions Made

- Bridge cleanup reuses `_cleanup_pipeline` injected as the third hook — no parallel cleanup path (INV-12).
- Gap 2c fixed by consistent stamping (the INV-3 single-source choice), NOT by relaxing `get_run` to owner-only scoping (rejected — would weaken AUTHZ-01/03 default-deny).
- The marker prefers the run_events-sourced workspace (`_recover_workspace_id`) over `wr.workspace_id` even after the forward-path fix ships, so the marker always matches the sink scope exactly.
- `backend/agents/authz.py` required no edit: `set_run_scope` already existed as the exact reuse seam the plan mandated (the plan's `files_modified` listed it predictively; the constraint was "do not add a parallel stamper", which held).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Best-effort marker handler could raise from inside its own except**
- **Found during:** Task 2 (test 3: no-durable-rows path)
- **Issue:** `_stamp_resume_marker`'s except handler logged `wr.id` — a lazy ORM attribute load that itself raises (`PendingRollbackError`) when the session was poisoned by the caught flush failure, defeating the best-effort contract
- **Fix:** Capture the row's scalars (`run_id`, `prior_status`, owner fields) up front so the try body and handler never touch the ORM object after a failure
- **Files modified:** backend/agents/execution_engine/engine.py
- **Verification:** `test_stamp_resume_marker_without_durable_rows_does_not_raise` green
- **Committed in:** a09f7b35 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Necessary for the marker's best-effort correctness contract. No scope creep.

## Issues Encountered

- The plan's suggested engine-source assertion (`"app.api" not in source`) false-positived on the fix's own explanatory comments; narrowed to an import-statement regex (the actual import-linter contract: no `from app.api` / `import app.api` statements).

## Known Stubs

None — no hardcoded empty values, placeholders, or unwired components introduced.

## Threat Flags

None — all new surface (the injected bridge, the workspace stamping, the marker write) is covered by the plan's threat model (T-12-09-BRIDGE / T-12-09-IDOR / T-12-09-DOS); no packages installed (T-12-09-SC accept held).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Backend half of UAT Gap 2 closed; the 12-08 FE reconnect handler can now resolve a restarted run's status and live-attach mid-resume.
- 12-10 (manifest deliverable) is the remaining phase-12 plan.
- Live-environment confirmation of the resumed-run live-attach (real uvicorn restart + browser reconnect) defers to the end-of-milestone live pass per the standing preference.

## Self-Check: PASSED

- Created files exist: test_resume_ws_bridge.py, test_resume_marker_workspace.py, 12-09-SUMMARY.md
- Commits exist: 0da2315d (Task 1), a09f7b35 (Task 2)

---
*Phase: 12-wave-scheduler-durable-resume-6*
*Completed: 2026-06-11*
