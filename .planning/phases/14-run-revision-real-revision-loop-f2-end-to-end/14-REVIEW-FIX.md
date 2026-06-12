---
phase: 14-run-revision-real-revision-loop-f2-end-to-end
fixed_at: 2026-06-12T13:19:23Z
review_path: .planning/phases/14-run-revision-real-revision-loop-f2-end-to-end/14-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 6
skipped: 0
status: all_fixed
---

# Phase 14: Code Review Fix Report

**Fixed at:** 2026-06-12T13:19:23Z
**Source review:** .planning/phases/14-run-revision-real-revision-loop-f2-end-to-end/14-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 6 (fix_scope: critical_warning — 2 Critical + 4 Warning; 3 Info findings out of scope)
- Fixed: 6
- Skipped: 0

Every fix carries an executable pinning test (environment-notes requirement); all
verified offline with the targeted suites + the 5 characterization suites +
banned-patterns + `lint-imports` (4 contracts kept). Two endpoint-level tests drive
the REAL `websocket_chat` receive loop via a new `_ScriptedLoopWebSocket` harness,
so the loop's own guards (not just the extracted coroutines) are pinned.

## Fixed Issues

### CR-01: `run_revision` branch has no overlap guard — cancel handle silently lost

**Files modified:** `backend/app/api/websocket.py`, `backend/tests/unit/test_run_revision_ws_dispatch.py`
**Commit:** 9ab3f7f2
**Applied fix:** Added the run_pipeline-identical overlap guard (byte-identical
`pipeline_already_running` error frame) at the top of the `run_revision` branch,
before ingress validation and task creation. `current_pipeline_task` is never
overwritten while a pipeline/revision is in flight. Pinned by
`test_overlap_guard_rejects_second_run_revision`, which drives the real
`websocket_chat` receive loop with two scripted `run_revision` frames and asserts
exactly one execution starts plus one rejection frame.

### CR-02: Unvalidated `target_artifact_type` dispatches `planner: run` pipelines that hang at the clarify gate

**Files modified:** `backend/agents/execution_engine/engine.py`, `backend/tests/unit/test_revision_intelligence.py`
**Commit:** b53d4aca
**Applied fix:** Extended `_handle_revision`'s pre-dispatch guard (beside the
`if not agents` registry guard): `compile_for_run(revision_pipeline_type).planner != "skip"`
raises `ValueError` ("not revision-dispatchable"), mapped to
`revision_validation_error` at the WS seam. The predicate is compiled-manifest DATA
(SC-001 — no workflow-name literal); flipping a manifest to `planner: skip` makes
its target dispatchable with zero engine edits. Adaptation from the review's
suggested snippet: `compile_for_run` lives in `engine.py` itself (line ~212), so no
`agents.workflows.compiler` import was added (none exists there). INV-3 verified:
all 5 characterization suites (53 tests) + banned-patterns + manifest-parity pass,
`lint-imports` 4 contracts kept. Pinned by
`test_planner_run_target_rejected_before_dispatch` (realistic parent whose
deliverable ref satisfies FR-014 link 2, target `prototype_output` → ValueError
before any event; pre-fix this test hangs at the clarify gate).

### WR-01: `state_restoration_failed` emitted after `pipeline_complete` was never delivered

**Files modified:** `backend/app/api/websocket.py`, `backend/tests/unit/test_run_revision_ws_dispatch.py`
**Commit:** ca65d7d4
**Applied fix:** Review's option (b): the revision drainer tracks `terminal_break`;
after a terminal break it already awaits `revision_bg_task` (existing 5s grace),
and now drains residual non-sentinel events from the queue and forwards them on the
same `{type, chunk: None, section: <target>, data}` wrapper. Scoped to the
terminal-break exit only — a dead-WS break still leaves the queue intact for the
reconnect drainer. Pinned by
`test_state_restoration_failed_after_terminal_is_delivered` (stub emits
`pipeline_complete` then `state_restoration_failed`; asserts delivery, wrapper
shape, ordering, and that the row stays "completed").

### WR-02: Degraded revision completion recorded `"completed"`

**Files modified:** `backend/app/api/websocket.py`, `backend/tests/unit/test_run_revision_ws_dispatch.py`
**Commit:** 2a7d6aa2
**Applied fix:** `_queue_send` now sets `degraded_seen` when `pipeline_complete`
carries `data.status == "degraded"` (mirroring the run_pipeline 13 IN-03 mapping),
and the success branch persists `"degraded" if degraded_seen else "completed" if
(pipeline_complete_seen and not pipeline_failed_seen) else "failed"`. The
`_handle_revision_execution` docstring's terminal-fidelity paragraph was updated to
match. Pinned by `test_degraded_completion_records_degraded_not_completed`.

### WR-03: Reconnect drainer broke the pinned revision frame contract (`section: None`)

**Files modified:** `backend/app/api/websocket.py`, `backend/tests/unit/test_run_revision_ws_dispatch.py`
**Commit:** d71c55e6
**Applied fix:** The live-attach path derives `_reattach_section` from the
owner-filtered run row already fetched by the AUTHZ-03 gate: a `*_revision` type
reconstructs the target as `f"{type.removesuffix('_revision')}_output"` (inverse of
the WR-06 alias transform — generic suffix transform, no workflow-name literal).
The live-attach drainer's event-forward and heartbeat frames use it; non-revision
runs keep `section: None` byte-identically (legacy reconnect contract preserved —
`test_ws_reconnect_replay.py` all green). Durable-replay frames are unchanged
(review fix scoped to the live attach). Pinned by
`test_reconnect_drainer_preserves_revision_section`, which drives the real
`websocket_chat` reconnect path against a seeded live revision run.

### WR-04: Stale AUTHZ comment described the deleted workspace writeback

**Files modified:** `backend/app/api/websocket.py`
**Commit:** 4e700d15
**Applied fix:** Rewrote the comment on `owner_id=user.id` in the revision
WorkflowRun creation to match 14-03 reality: row created with a real owner and
transiently-null workspace; `execute()` mints the run's OWN workspace and completes
the scope via its chokepoint `set_run_scope`; only the post-dispatch exact-kind
lineage ref carries the PARENT artifact's workspace. References the proving test
(`test_revision_run_events_persist_and_resolve_on_real_db`). Comment-only — no
pinning test applicable.

## Verification

- `tests/unit/test_run_revision_ws_dispatch.py` — 10 passed (6 original + 4 new pins)
- `tests/unit/test_run_revision_fe_contract.py` — passed
- `tests/unit/test_revision_intelligence.py` — 18 passed (17 + 1 new pin)
- `tests/agents/test_ws_reconnect_replay.py` — 7 passed (legacy reconnect contract intact)
- 5 characterization suites + `test_banned_patterns.py` + `test_manifest_parity.py` — 53 passed (INV-3, engine.py touched by CR-02)
- `/opt/homebrew/bin/lint-imports` — 4 contracts kept, 0 broken
- Final sweep: 94 passed, 1 failed — the single failure
  (`tests/unit/test_pipeline_cancel.py::test_cancel_marks_workflow_cancelled_and_sends_ack`,
  "DID NOT RAISE CancelledError") is **pre-existing**: it fails identically against
  the pre-fix source (d1dff9f4) and on the untouched main working tree. Sleep-based
  timing race in the test's run_pipeline cancel scenario; unrelated to Phase 14
  revision fixes.

## Skipped Issues

None — all in-scope findings were fixed.

---

_Fixed: 2026-06-12T13:19:23Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
