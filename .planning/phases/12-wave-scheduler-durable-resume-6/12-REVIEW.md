---
phase: 12-wave-scheduler-durable-resume-6
reviewed: 2026-06-11T14:29:47Z
depth: standard
files_reviewed: 12
files_reviewed_list:
  - backend/agents/execution_engine/engine.py
  - backend/agents/workflows/sample_wave/workflow.yaml
  - backend/app/api/websocket.py
  - backend/app/main.py
  - backend/tests/agents/test_resume_marker_workspace.py
  - backend/tests/agents/test_resume_ws_bridge.py
  - backend/tests/agents/test_sample_wave_workflow.py
  - frontend/src/app/dashboard/page.tsx
  - frontend/src/components/layout/DashboardLayout.tsx
  - frontend/src/components/layout/DashboardLayout.waveMount.test.tsx
  - frontend/src/hooks/useWorkflow.reconnect.test.ts
  - frontend/src/hooks/useWorkflow.ts
findings:
  critical: 1
  warning: 3
  info: 3
  total: 7
status: issues_found
---

# Phase 12: Code Review Report (UAT Gap-Closure Delta — 12-08 / 12-09 / 12-10)

**Reviewed:** 2026-06-11T14:29:47Z
**Depth:** standard (delta review; diff base 274d4209)
**Files Reviewed:** 12
**Status:** issues_found

## Summary

Reviewed the gap-closure delta for plans 12-08 (FE wave panel + `pipeline_reconnected` handling), 12-09 (engine→WS live-task bridge, `workflow_runs.workspace_id` stamping, resume-marker workspace recovery), and 12-10 (sample_wave deliverable → `serialized_sandbox`).

Verification evidence gathered during review:
- All new tests pass offline: `test_resume_ws_bridge.py` + `test_resume_marker_workspace.py` (8 passed), `test_sample_wave_workflow.py` (3 passed), the two new vitest suites (9 passed).
- `lint-imports`: 4 contracts kept, 0 broken — the kernel does not import `app.api`; the bridge is injected callables, wired only in `app/main.py`.
- SC-001 holds: `grep sample_wave backend/agents/execution_engine/` is empty; the manifest change is pure data; `serialized_sandbox` is a registered capability (`agents/capabilities/deliverables/serialized_sandbox.py`), no kernel edit.
- The deepagents runtime mandate is untouched by this delta.

The architecture of the bridge (three optional injected callables, dormant-by-default, app-layer wiring) is sound and well-tested for the happy path. However, the adversarial pass found one authorization gap the bridge newly exposes (CR-01), a registry-entry leak on `resume_run`'s early-return paths (WR-01), a liveness race window that can reproduce the exact "running forever" hang 12-08 set out to fix (WR-02), and an error-handling inconsistency that silently swallows the AUTHZ fail-loud signal (WR-03).

## Critical Issues

### CR-01: `reconnect_pipeline` live-attach has no ownership check — the 12-09 bridge newly exposes auto-resumed runs' live event streams to any authenticated user with the run_id

**File:** `backend/app/api/websocket.py:594-744` (live-attach branch 708-744; bridge registration 68-84)
**Issue:** The `reconnect_pipeline` handler takes `pipeline_run_id` from the untrusted client payload (line 595) and computes `_has_live_task` directly from the process-global `_PIPELINE_TASKS`/`_PIPELINE_QUEUES` registries (lines 597-603). The durable-replay path is meticulously owner-scoped (`RunEvent.owner_id == user.id` at 663, `ScopedStore(owner_id=user.id, ...)` at 670 — a cross-owner replay resolves to ∅, per T-12-03-IDOR). The **live-attach drainer is not**: lines 708-744 attach the authenticated WebSocket to the run's live queue and stream every event (agent output, deliverable content, `pipeline_complete` with `final_output`) with **no check that `user.id` owns the run**.

This hole pre-exists for `run_pipeline`-launched runs, but those runs' queues are registered only for the launching connection's lifetime and the launcher is by construction the owner. The 12-09 bridge changes the exposure: `_register_resume_queue`/`_register_resume_task` now place **auto-resumed runs** — runs whose owner is by definition *not currently connected* (the backend restarted) — into the same registries for the full duration of the resumed drive. Any other authenticated user who presents that run_id during the resume window live-attaches and receives the victim's full resumed tail. Run IDs are UUIDv4 (not guessable), which bounds practical exploitability, but the project's own AUTHZ-03 default-deny invariant ("a cross-owner read resolves to ∅") is violated at this seam, and run IDs do leak into client sessionStorage, logs, and history payloads.

**Fix:** Owner-gate the live attach the same way the replay is gated — before entering the `_has_live_task` branch, resolve the run through the owner-scoped store and treat a miss as "no live task":
```python
if _has_live_task:
    # AUTHZ-03: live attach is owner-gated — a run this principal does not
    # own behaves exactly like a finished/unknown run (∅, never the stream).
    _own_store = ScopedStore(owner_id=user.id, workspace_id=_recovered_ws)
    if await _own_store.get_run(_reconnect_run_id) is None:
        _has_live_task = False
```
(The `_recovered_ws` recovery at lines 657-672 already runs in the replay branch; hoist it or recompute it for the live branch. Note `get_run` now resolves for live runs because 12-09 Gap 2c stamps `workflow_runs.workspace_id` — the fix is enabled by this same delta.)

## Warnings

### WR-01: `resume_run` early returns and queue-registration failure leak the registered `_PIPELINE_TASKS` entry — cleanup is gated on `live_queue is not None`

**File:** `backend/agents/execution_engine/engine.py:4071-4094, 4144-4153, 4195-4212`
**Issue:** `restore_non_terminal_runs` registers the driver task in `_PIPELINE_TASKS` synchronously at the `create_task` site (lines 3049-3061). But `resume_run` has three early-return paths *before* queue registration — no `workflow_runs` row (4073), agent-resolution failure (4091), empty agent list (4094) — plus the path where `self._resume_register_queue(...)` itself raises (4148-4153, `live_queue = None`). In all of these, the `finally` block's cleanup never fires because `self._resume_cleanup(run_id)` is nested *inside* `if live_queue is not None:` (4200-4212). Result: a permanently stale (done) task entry in the process-global `_PIPELINE_TASKS` for each such run — a slow registry leak in a long-lived process, and a violation of the bridge's own stated contract ("a completed resume never leaves a stale live registration").
**Fix:** Make cleanup unconditional on the hook, not on the queue:
```python
finally:
    if live_queue is not None:
        try:
            live_queue.put_nowait(None)
        except Exception:
            pass
    if self._resume_cleanup is not None:   # ← no longer nested under live_queue
        try:
            self._resume_cleanup(run_id)
        except Exception as _cl_exc:
            logger.warning("resume_run(%s): bridge cleanup failed: %s", run_id, _cl_exc)
```
`_cleanup_pipeline` is idempotent (`dict.pop(..., None)`), so this is safe on every path.

### WR-02: Task-registered-before-queue race window reproduces the "running forever" hang — and the FE's `live:false` + non-terminal branch has no recovery on a healthy connection

**File:** `backend/agents/execution_engine/engine.py:3049-3061, 4068-4147`; `frontend/src/hooks/useWorkflow.ts:432-439`; `frontend/src/components/layout/DashboardLayout.tsx:520-549`
**Issue:** The driver task is registered in `_PIPELINE_TASKS` synchronously at `create_task` (engine.py:3057), but the live queue is registered only *inside* `resume_run`, after multiple awaited DB round-trips (workflow_runs read, agent resolution, `_compute_resume_offset`, durable-tail seq read — lines 4068-4137). A client that reconnects in that window hits `_has_live_task == False` (websocket.py:599-603 requires `running_queue is not None`), gets `pipeline_reconnected {live: false, status: "generating"}`, and the FE branch at useWorkflow.ts:432-439 keeps `isRunning` true with **no retry**. The code comment claims "re-replay is driven by the existing reconnect effect on the next connection cycle / heartbeat" — but heartbeats are only emitted by an *attached* drainer (websocket.py:723-732), and the reconnect effect (DashboardLayout.tsx:520-549) fires only on a `connectionStatus` transition to "connected". On a healthy connection neither ever fires again, so the client never receives the resumed tail or the terminal event — the exact UAT Gap 2 hang, now confined to a race window but unrecoverable without a manual refresh when it hits. This window is most likely precisely after a backend restart, when every open client reconnects immediately and simultaneously with the restore scan.
**Fix:** Close the window at the source — register the queue at the same synchronous site as the task in `restore_non_terminal_runs` (the bridge's `_get_or_create_queue` is idempotent, so `resume_run`'s later registration returns the same queue):
```python
if self._resume_register_queue is not None:
    try:
        self._resume_register_queue(pipeline_run_id)
    except Exception: ...
_resume_task = _asyncio.create_task(self.resume_run(pipeline_run_id))
if self._resume_register_task is not None: ...
```
Optionally also harden the FE: on `live:false` + non-terminal, schedule one bounded re-send of `reconnect_pipeline` (e.g., a single 5s `setTimeout`), which also covers any future backend path that produces this shape.

### WR-03: The new `set_run_scope` call site swallows `PermissionError` — inconsistent with the revision seam's fail-loud contract, masking AUTHZ violations and silently regressing the very bug being fixed

**File:** `backend/agents/execution_engine/engine.py:781-791`
**Issue:** The Gap 2c stamp wraps `scoped_store.set_run_scope(...)` in a blanket `except Exception` that logs a warning and proceeds — the comment explicitly includes "the IN-02 cross-owner PermissionError" in the swallowed set. The *other* caller of this exact seam (the revision path, engine.py:3380-3392) deliberately re-raises any non-`SQLAlchemyError` — `PermissionError` included — on the documented grounds that "a non-DB exception is a real bug." A `PermissionError` here means the WS layer created the `workflow_runs` row under a different principal than the engine derived (`owner_id = user_id or f"anon:..."`, line 696) — real principal drift. Swallowing it (a) hides the drift behind a warning log, and (b) leaves `workflow_runs.workspace_id` NULL, silently reinstating the null-`status` reconnect bug this stamp exists to fix, with no test or alert tripping. Same seam, two contradictory error contracts.
**Fix:** Mirror the revision site's narrow degrade:
```python
except Exception as _stamp_exc:
    from sqlalchemy.exc import SQLAlchemyError
    if not isinstance(_stamp_exc, SQLAlchemyError):
        raise  # PermissionError / principal drift is a real bug — fail loud
    logger.warning("execute(): workflow_runs scope stamping failed for %s (%s) — proceeding",
                   pipeline_run_id, _stamp_exc)
```
If best-effort-on-everything is genuinely intended for this site, at minimum log `PermissionError` at `error` level with an explicit "principal drift" message and document why this site diverges from engine.py:3386-3387.

## Info

### IN-01: `live: true` is documented and tested but never sent by any backend path

**File:** `frontend/src/hooks/useWorkflow.ts:390-393`; `frontend/src/hooks/useWorkflow.reconnect.test.ts:128-140`; `backend/app/api/websocket.py:712-716`; `backend/tests/agents/test_resume_ws_bridge.py` (module docstring)
**Issue:** The FE comment ("the 12-09 bridge adds `live: true` for an engine-attached resumed run") and the dedicated `live:true` test case describe a payload the backend never produces: the live-attach branch (websocket.py:712-716) sends `pipeline_reconnected` *without* a `live` key for both legacy and resumed runs. Behavior is correct (`live !== false` treats absent and true identically), but the documented contract is fictional — a future reader may rely on `live: true` to distinguish the bridge path.
**Fix:** Either add `"live": True` to the live-attach payload (making the documented contract real and the branches symmetric), or correct the comments/docstrings to say the live path omits the key.

### IN-02: `_stamp_resume_marker` derives its owner from `wr.owner_id or wr.user_id` while every other resume read derives it from `user_id` — latent principal divergence loses the marker silently

**File:** `backend/agents/execution_engine/engine.py:3156` vs `4127, 4227`
**Issue:** The marker's recovery call is `_recover_workspace_id(owner_id, run_id)` with `owner_id = wr.owner_id or wr.user_id or f"anon:..."`, but `resume_run`/`_compute_resume_offset` (and the sink that wrote the durable rows) use `user_id or f"anon:..."`. Today `workflow_runs.owner_id == user_id` for all writers so the values coincide, but if they ever diverge the owner-scoped recovery returns `None`, the marker hits the documented best-effort except, and the double-drive audit marker is silently lost — with no signal beyond a warning log.
**Fix:** Derive the marker's principal identically to the resume drive (`wr.user_id or f"anon:{wr.session_id or run_id}"`), or add a code comment asserting the `owner_id == user_id` invariant this relies on.

### IN-03: Bridge wiring shares the restore scan's try block — a wiring import failure now also skips run restoration entirely

**File:** `backend/app/main.py:117-131`
**Issue:** `from app.api import websocket as _ws_bridge` and the three hook assignments sit inside the same `try` as `await engine_instance.restore_non_terminal_runs()`. If the bridge import/assignment ever raises (circular-import drift, refactor), the blanket `except` logs "Startup restoration failed" and the pre-existing restore feature — which previously ran unconditionally — is silently skipped along with the bridge. Low likelihood today (the module is already imported by the app router), but the failure coupling is unnecessary.
**Fix:** Wrap the bridge wiring in its own narrow try/except (log "bridge wiring failed — resumes will be durable-replay-only") so a wiring failure degrades to the pre-12-09 behavior instead of cancelling restoration.

---

_Reviewed: 2026-06-11T14:29:47Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
