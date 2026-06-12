---
phase: 14-run-revision-real-revision-loop-f2-end-to-end
plan: 02
subsystem: api
tags: [websocket, run_revision, asyncio-queue, background-task, terminal-status, agent_count, pytest]

# Dependency graph
requires:
  - phase: 13-gap-closure
    provides: WR-06 FE-routed revision alias + revision row creation fields the extracted coroutine preserves byte-identically; 13-06 pipeline_failed semantics the status fidelity keys on
  - phase: 12-resumability
    provides: _PIPELINE_QUEUES/_PIPELINE_TASKS registries, _get_or_create_queue/_cleanup_pipeline, owner-gated reconnect live-attach (12-05 CR-01) the revision runs now plug into
provides:
  - "_handle_revision_execution module-level coroutine in websocket.py: revision row creation + per-run event queue + background _run_revision_to_queue + sentinel-terminated drainer (run_pipeline pattern)"
  - "run_revision receive-loop branch dispatches via asyncio.create_task assigned to current_pipeline_task — cancel_pipeline/pings/reconnects processed while a revision runs (Pitfall 3)"
  - "Revision terminal status derived from observed terminal events: pipeline_complete -> completed, pipeline_failed/no terminal -> failed, CancelledError -> cancelled; the unconditional completed flip is deleted (Pitfall 4)"
  - "agent_count = len(get_pipeline_agents(derived revision alias)) or 1 — real registry membership, never hardcoded (Pitfall 6)"
  - "tests/unit/test_run_revision_ws_dispatch.py: 6 handler-level scenarios pinning section stamping, terminal-status fidelity, error vocabulary, agent_count derivation, cancellation, cleanup"
affects: [14-03, 14-04, run_revision, websocket-dispatch, cancel_pipeline, reconnect_pipeline]

# Tech tracking
tech-stack:
  added: []
  patterns: ["Queue-decoupled WS dispatch reuse: a second frame type (run_revision) onto the existing per-run queue + bg task + drainer infrastructure with zero new registry/cleanup mechanisms", "Terminal flags observed from the forwarded stream via the send-fn closure — no engine signature change"]

key-files:
  created:
    - backend/tests/unit/test_run_revision_ws_dispatch.py
  modified:
    - backend/app/api/websocket.py

key-decisions:
  - "CancelledError absorbed inside _run_revision_to_queue (run_pipeline precedent — no re-raise); the outer drainer's CancelledError path cancels the bg task and re-raises, so cancel_pipeline lands the row 'cancelled'"
  - "Error frames from the bg task ride the drainer wrapper -> section = target_artifact_type (previously the inline handlers sent section None); ingress validation frames stay byte-identical with section None"
  - "Drainer mirrors run_pipeline's terminal-type breaks + a bounded post-drain await of the bg task so direct awaiters of the coroutine observe the final row state (deterministic tests, no sleeps)"
  - "No overlap-rejection guard added to the run_revision ingress — plan scope keeps the two ingress validations byte-identical; overlap semantics ride current_pipeline_task like before"

patterns-established:
  - "Stub-engine handler tests capture the minted pipeline_run_id from the recorded _handle_revision kwargs — no DB scanning or id guessing"

requirements-completed: [F2]

# Metrics
duration: ~18min
completed: 2026-06-12
---

# Phase 14 Plan 02: run_revision queue dispatch + terminal-status fidelity Summary

**The WS run_revision branch now dispatches through the proven background-task + per-run-queue + drainer pattern (`_handle_revision_execution`), with terminal status derived from observed terminal events (completed/failed/cancelled — never an unconditional flip), registry-derived agent_count, and a 6-scenario handler-level regression suite.**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-06-12T12:07:06Z
- **Completed:** 2026-06-12T12:25:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- `_handle_revision_execution` extracted as a module-level coroutine mirroring `_handle_workflow_execution`: WorkflowRun row creation (fields byte-identical to the inline branch except the derived agent_count), `_get_or_create_queue`, inner `_run_revision_to_queue` bg task, sentinel-terminated drainer with 10s heartbeat. Revision runs are registered in `_PIPELINE_TASKS`/`_PIPELINE_QUEUES` (cancellable via cancel_pipeline through `current_pipeline_task`, reconnect-discoverable through the existing owner-gated path) and cleaned by `_cleanup_pipeline`.
- The receive-loop branch keeps ONLY the two ingress validations (byte-identical `empty_revision_instruction` / `missing_revision_params` frames) + `current_pipeline_task = asyncio.create_task(...)`. The inline `await _rev_engine._handle_revision(...)`, the unconditional `status = "completed"` flip, `_send_revision_event`, and the inline ValueError/Exception handlers are DELETED (INV-12 — replaced, not bypassed).
- Terminal-status fidelity (Pitfall 4): `_run_revision_to_queue` observes `pipeline_complete`/`pipeline_failed` from the stream it forwards (the `_queue_send` closure — no `_handle_revision` signature change) and persists completed/failed/cancelled accordingly; every exit path writes a terminal status, so no path leaves the row "revising". A failed dispatch can no longer be offered as a revision parent by the FE's `status === "completed"` lookup.
- agent_count derives from `get_pipeline_agents(f"{target.removesuffix('_output')}_revision")` — ppt_revision=2, od_ppt_revision=1, unknown alias → cosmetic 1 with no dispatch implication (Pitfall 6, T-14-02-05).
- New `tests/unit/test_run_revision_ws_dispatch.py` (425 lines, 6 tests): happy-path frame contract (`{type, chunk: None, section: <target_artifact_type>, data}` on every drained frame), pipeline_failed → failed, ValueError → `revision_validation_error` (recoverable False), RuntimeError → `revision_error` (recoverable True), agent_count computed against the live registry at test time, and event-driven cancellation (entered-gate Event, no wall-clock assertions) landing the row "cancelled" with `pipeline_cancelled` observed and registries cleaned.

## Task Commits

Each task was committed atomically:

1. **Task 1: Extract _handle_revision_execution — queue dispatch, terminal-status fidelity, agent_count** - `ec590467` (feat)
2. **Task 2: Handler-level regression suite for the queue dispatch** - `e9a6a2ca` (test)

## Files Created/Modified

- `backend/app/api/websocket.py` - run_revision branch reduced to ingress validation + create_task; new `_handle_revision_execution` coroutine (row creation, queue, `_run_revision_to_queue` bg task with terminal persistence, drainer with heartbeat/sentinel/terminal breaks, cancel propagation)
- `backend/tests/unit/test_run_revision_ws_dispatch.py` - 6-scenario handler-level suite (stub engine recording `_handle_revision` kwargs, FakeWebSocket, in-memory SQLite on the WS module's `_get_db`)

## Decisions Made

- **CancelledError absorbed in the bg task** (run_pipeline `_run_pipeline_to_queue` precedent): the bg task catches it, queues `pipeline_cancelled`, persists "cancelled", and completes normally; the OUTER drainer's CancelledError path does `revision_bg_task.cancel(); raise` — exactly the `_handle_workflow_execution` cancel-propagation shape, no new mechanism.
- **Error frames change section from None to the target artifact type**: bg-task error events now ride the drainer wrapper (plan-sanctioned); the two INGRESS error frames keep section None byte-identically.
- **Bounded post-drain await of the bg task** (5s, mirroring run_pipeline's safety wait) so callers awaiting the coroutine directly observe the final persisted row state — what makes the test suite deterministic without sleeps.
- **No overlap-rejection guard** added at run_revision ingress (out of plan scope; ingress frames must stay byte-identical).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- **Pre-existing, environment-gated failure logged to deferred-items.md:** `tests/unit/test_pipeline_cancel.py::test_cancel_marks_workflow_cancelled_and_sends_ack` fails offline with a live Bedrock `ExpiredTokenException` during title generation. Proven pre-existing (fails byte-identically with websocket.py at HEAD~2); not in any 14-02 verify command (the suite was a read_first style reference only). Out of scope — not fixed.

## Verification Evidence

- Task 1: `_handle_revision_execution` import assert + `test_run_pipeline_validation.py` + `test_pipeline_failure_semantics.py` — 58 passed; `lint-imports` 4 contracts kept, 0 broken.
- Task 1 acceptance greps: `_handle_revision(` appears ONLY inside the bg task (line 1879); `agent_count=1` count 0; `empty_revision_instruction`/`missing_revision_params` each exactly 1; run_revision branch assigns `current_pipeline_task` via `asyncio.create_task`.
- Task 2: `test_run_revision_ws_dispatch.py` — 6 passed; "completed"/"failed"/"cancelled" literals all asserted; `"section"` + target literal asserted; `get_pipeline_agents` computed at test time; 425 lines (>= 120).
- Wave gate: 5 characterization suites + banned_patterns + migration_ledger + ws_dispatch + run_pipeline_validation + failure_semantics + fe_contract — 113 passed, 7 skipped (pre-existing), 1 pre-existing env-gated failure (deferred above); `lint-imports` 4 kept.
- INV-3 scope: `git diff --name-only HEAD~2 HEAD` = `backend/app/api/websocket.py` + the new test only — zero `backend/agents/execution_engine/` edits, zero goldens touched.
- Live cancel/reconnect during a real model run: **DEFERRED** to the milestone-end live pass (SC4 convention) — offline cancellation pinned by scenario (f).

## Next Phase Readiness

- 14-03 (real engine dispatch) plugs in transparently: the stub-compatible `_queue_send` seam forwards whatever `_handle_revision` emits — when 14-03 dispatches `execute()`, the same drainer/status/cancel machinery applies with zero further WS edits.
- 14-04 test rewrites can rely on the queue-dispatch contract pinned here (section stamping, terminal vocabulary, cleanup).
- No blockers.

---
*Phase: 14-run-revision-real-revision-loop-f2-end-to-end*
*Completed: 2026-06-12*

## Self-Check: PASSED

- backend/app/api/websocket.py and backend/tests/unit/test_run_revision_ws_dispatch.py exist on disk
- Task commits ec590467 and e9a6a2ca present in git log

## Self-Check: PASSED

- backend/app/api/websocket.py and backend/tests/unit/test_run_revision_ws_dispatch.py exist on disk
- Task commits ec590467 and e9a6a2ca present in git log
