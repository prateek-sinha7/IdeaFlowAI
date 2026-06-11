---
phase: 12-wave-scheduler-durable-resume-6
fixed_at: 2026-06-11T14:42:28Z
review_path: .planning/phases/12-wave-scheduler-durable-resume-6/12-REVIEW.md
iteration: 1
findings_in_scope: 4
fixed: 4
skipped: 0
status: all_fixed
---

# Phase 12: Code Review Fix Report

**Fixed at:** 2026-06-11T14:42:28Z
**Source review:** .planning/phases/12-wave-scheduler-durable-resume-6/12-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 4 (fix_scope `critical_warning` — 1 Critical, 3 Warnings; IN-01/IN-02/IN-03 out of scope)
- Fixed: 4
- Skipped: 0

**Verification evidence (post-fix):**
- Targeted backend suite: `test_resume_ws_bridge.py`, `test_resume_marker_workspace.py`, `test_restart_resume.py`, `test_ws_reconnect_replay.py`, `test_characterization_prototype.py` — **24 passed** (same as pre-fix baseline).
- `lint-imports` (from `backend/`): **4 contracts kept, 0 broken** — the kernel still never imports the app layer; the bridge stays injection-based.
- `python ast.parse` clean on both modified Python files after every edit.

## Fixed Issues

### CR-01: `reconnect_pipeline` live-attach has no ownership check

**Files modified:** `backend/app/api/websocket.py`
**Commit:** ccfc596b
**Applied fix:** Inserted an AUTHZ-03 owner gate immediately after the `_has_live_task` computation, before the replay/live branches. The gate recovers the run's `workspace_id` from the `workflow_runs` row filtered by `owner_id == user.id` (never from the client payload — the T-12-05-TENANT precedent; this avoids depending on `run_events` rows existing yet, so a just-launched legacy run still resolves), then resolves the run through the default-deny `ScopedStore.get_run`. A miss demotes `_has_live_task` to `False`, so a non-owner presenting a live run_id falls into the owner-scoped durable-replay branch and receives the same response as for a finished/unknown run (∅ replay + `live: false`, `status: null`) — never the live stream. Adaptation from the review's suggested snippet: the workspace recovery uses an owner-filtered `WorkflowRun` lookup rather than hoisting the replay branch's `RunEvent` recovery, because the `RunEvent`-based recovery would false-negative for a legitimate owner reconnecting before the first durable event row exists; the decision point remains `ScopedStore.get_run` as the review prescribes (enabled by the 12-09 Gap 2c `workspace_id` stamp). **Requires human verification note:** the gate is authorization logic with no dedicated handler-driving regression test (the existing reconnect tests are contract tests); recommend a follow-up test that drives `reconnect_pipeline` with a cross-owner principal against a registered live queue and asserts demotion.

### WR-01: `resume_run` early returns / queue-registration failure leak the registered `_PIPELINE_TASKS` entry

**Files modified:** `backend/agents/execution_engine/engine.py`
**Commit:** 8d8a7a39
**Applied fix:** Added a private `_fire_resume_cleanup(run_id)` helper (guarded on the hook, best-effort, logs on failure) and invoke it on **every** exit path: the three early returns (no `workflow_runs` row, agent-resolution failure, empty agent list) and the drive loop's `finally`, where cleanup is now unconditional on the hook instead of nested inside `if live_queue is not None:`. Adaptation from the review's suggested snippet: the review's `finally`-only restructure would NOT have covered the three early returns — they exit before the `try` at the drive loop is ever entered — so explicit cleanup calls were added at each early return in addition to the un-nested `finally` cleanup. `_cleanup_pipeline`'s `dict.pop(..., None)` is idempotent, so the calls are safe on every path. Bridge test contract preserved (`cleanup_calls == [run_id]` still holds — one cleanup per drive).

### WR-02: Task-registered-before-queue race window reproduces the "running forever" hang

**Files modified:** `backend/agents/execution_engine/engine.py`, `frontend/src/hooks/useWorkflow.ts`
**Commit:** 41c35a69
**Applied fix:** Backend (primary fix, per the review's "close the window at the source"): `restore_non_terminal_runs` now registers the run's live queue via `self._resume_register_queue(pipeline_run_id)` at the same synchronous site as the driver task, immediately before `create_task` — `_get_or_create_queue` is idempotent, so `resume_run`'s later registration returns the same queue. Guarded + best-effort + dormant when the hook is unset (offline parity preserved; dormant-bridge test still passes). A leak from this earlier registration on `resume_run` early returns is covered by the WR-01 fix (unconditional cleanup). Frontend: corrected the factually wrong comment in the `live:false` + non-terminal branch (it claimed heartbeat-driven re-replay; heartbeats are only emitted by an already-attached drainer) — comment-only change, no behavioral edit. The review's **optional** FE hardening (a bounded `reconnect_pipeline` re-send on `live:false` + non-terminal) was deliberately NOT applied: the branch carries an explicit prior design decision against retry loops (`T-12-08-02`), and the backend fix closes the described window at its source. If the residual window (reconnect while the restore scan has not yet reached the run) proves observable in practice, the bounded retry should be added as a follow-up with its own test.

### WR-03: Gap 2c `set_run_scope` call site swallows `PermissionError`

**Files modified:** `backend/agents/execution_engine/engine.py`
**Commit:** 8eb3c880
**Applied fix:** Mirrored the revision seam's narrow degrade exactly (engine.py revision path precedent): the `except` around `scoped_store.set_run_scope(...)` in `execute()` now re-raises any non-`SQLAlchemyError` (including the IN-02 cross-owner `PermissionError` — principal drift is a real bug and fails loud) and degrades with a warning log only for the DB condition (offline harness / missing schema). The preceding comment, which documented the old blanket-swallow contract ("incl. the IN-02 cross-owner PermissionError"), was rewritten to document the new fail-loud contract so the comment and code no longer contradict. Characterization suite confirms no offline path trips the narrowed handler (24/24 pass).

## Skipped Issues

None — all in-scope findings were fixed. (IN-01, IN-02, IN-03 were out of scope for `fix_scope: critical_warning`.)

---

_Fixed: 2026-06-11T14:42:28Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
