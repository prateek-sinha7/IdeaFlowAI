---
phase: 14-run-revision-real-revision-loop-f2-end-to-end
reviewed: 2026-06-12T00:00:00Z
depth: standard
files_reviewed: 10
files_reviewed_list:
  - backend/agents/execution_engine/engine.py
  - backend/agents/workflows/od_ppt_revision/workflow.yaml
  - backend/agents/workflows/ppt_revision/workflow.yaml
  - backend/app/api/websocket.py
  - backend/tests/agents/_scripted_model.py
  - backend/tests/agents/test_id_alias_resolver.py
  - backend/tests/agents/test_manifest_parity.py
  - backend/tests/unit/test_revision_intelligence.py
  - backend/tests/unit/test_run_revision_fe_contract.py
  - backend/tests/unit/test_run_revision_ws_dispatch.py
findings:
  critical: 2
  warning: 4
  info: 3
  total: 9
status: issues_found
---

# Phase 14: Code Review Report

**Reviewed:** 2026-06-12
**Depth:** standard (scoped to the `22e10df0^..HEAD` diff; interaction surfaces with surrounding code traced)
**Files Reviewed:** 10
**Status:** issues_found

## Summary

Phase 14 replaces the `_handle_revision` echo stub with real registry-pipeline dispatch through `execute()`, moves the WS `run_revision` branch onto the background-task + per-run-queue + drainer pattern, flips the two run_revision manifests to `planner: skip`, and rewrites the pinning suites to the real-dispatch contract. The core dispatch design is sound: stamping/persistence is correctly single-sourced at the `execute()` chokepoint (verified — `gate_agent_ids=[]` does *not* fall back to the static gate set; engine.py:2928-2941 confirms the `is not None` semantics the comment claims), the pre-dispatch fail-fast and the `final_output and not terminal_failed` lineage guard are correct, and the test suites are unusually rigorous (all 117 affected tests pass offline, verified in this review).

However, the new WS dispatch path has two critical defects: the `run_revision` branch lacks the overlap guard every other dispatch path has (losing the cancel handle and permitting unbounded concurrent revisions per connection), and the unvalidated client-controlled `target_artifact_type` can derive a `planner: run` revision pipeline that hangs **indefinitely** at the clarify `event.wait()` — leaking a permanently stuck background task, queue entry, and a `"revising"` row. Four warnings cover an event-delivery ordering bug (`state_restoration_failed` is now silently dropped), lost degraded-status fidelity, a reconnect frame-contract drift, and a stale authz comment describing deleted behavior.

## Critical Issues

### CR-01: `run_revision` branch has no overlap guard — cancel handle to an in-flight run is silently lost

**File:** `backend/app/api/websocket.py:889-898`
**Issue:** The `run_pipeline` branch rejects overlapping runs (`pipeline_already_running`, websocket.py:530-541) precisely because "a misbehaving client or a double-click race would otherwise spawn parallel WorkflowRuns and stream interleaved events," and the connection-level invariant is documented at websocket.py:497 ("A single connection can run at most one pipeline at a time"). The new `run_revision` branch violates this: it unconditionally assigns `current_pipeline_task = asyncio.create_task(_handle_revision_execution(...))` with no `done()` check. Consequences:
1. A `run_revision` frame while a pipeline (or another revision) is running overwrites `current_pipeline_task` — the only handle `cancel_pipeline` (websocket.py:598-605) uses. The original multi-minute run becomes **uncancellable from its own connection**, while both drainers interleave `send_json` calls on the same WebSocket.
2. A double-click on the revise button spawns two concurrent revision WorkflowRuns (pre-14 this was impossible: the inline `await` serialized the receive loop). Combined with CR-02, a client can loop `run_revision` frames and accumulate unbounded background tasks on a single connection.

This is a Phase-14 regression: pre-14 the inline branch never reassigned `current_pipeline_task`.
**Fix:**
```python
if msg_type == "run_revision":
    if current_pipeline_task is not None and not current_pipeline_task.done():
        await websocket.send_json({
            "type": "error", "chunk": None, "section": None,
            "data": {"error": "Pipeline already running. Cancel the current one first.",
                     "code": "pipeline_already_running", "recoverable": True},
        })
        continue
    ...
```
(Identical to the run_pipeline guard; place it before the ingress validation or after it — before task creation either way.)

### CR-02: Unvalidated `target_artifact_type` dispatches `planner: run` revision pipelines that hang forever at the clarify gate

**File:** `backend/app/api/websocket.py:868-887` (ingress), `backend/agents/execution_engine/engine.py:3832-3843` (dispatch guard)
**Issue:** `target_artifact_type` is client-controlled and validated only for presence at ingress. The derived alias `f"{target.removesuffix('_output')}_revision"` resolves **any** registered `*_revision` pipeline — and `prototype_revision`, `user_stories_revision`, and `app_builder_revision` are all real registry keys (`agents/registry.py:41,83,107`) whose manifests keep `planner: run`. The engine's only pre-dispatch guard is `if not agents` (empty registry membership), which these pipelines pass. Phase 14's own test suite states the consequence explicitly (test_revision_intelligence.py:43-49): "Any other `*_output` target would derive a `planner: run` manifest and **hang at the clarify gate**" — `clarify_engine.py:155 await event.wait()` with "No automatic timeout" (clarify_engine.py:137), waiting for a questionnaire round-trip the revision panel never sends.

The FR-014 artifact guard does **not** block this: chain links 2/3 (deliverable/summary fallback) resolve regardless of the target kind, so any owned completed run (e.g., a prototype run with its `kind="deliverable"` ref) satisfies it. One frame — `{"type": "run_revision", "parent_run_id": <own prototype run>, "target_artifact_type": "prototype_output", "instruction": "x"}` — produces: a background task parked forever at `event.wait()`, permanent `_PIPELINE_TASKS`/`_PIPELINE_QUEUES` entries (`_cleanup_pipeline` only runs in the bg task's `finally`, which is never reached), and a WorkflowRun stuck `"revising"` — defeating this phase's own "no terminal path leaves the row 'revising'" goal. With CR-01, these stuck tasks accumulate without bound on one authenticated connection.
**Fix:** Reject non-dispatchable targets at the seam. Either allow-list at WS ingress, or — better, keeping it data-driven (SC-001) — extend the engine's pre-dispatch guard to check the compiled manifest:
```python
# engine.py, beside the `if not agents` guard:
from agents.workflows.compiler import compile_for_run
plan = compile_for_run(revision_pipeline_type)
if plan.planner != "skip":
    raise ValueError(
        f"target_artifact_type {target_artifact_type!r} is not revision-dispatchable: "
        f"pipeline {revision_pipeline_type!r} requires the planner/clarify flow "
        f"the revision panel cannot drive."
    )
```
This maps to the existing `revision_validation_error` path and keeps the kernel workflow-name-free (the predicate is manifest data, not a name literal).

## Warnings

### WR-01: `state_restoration_failed` is emitted after `pipeline_complete` and is now never delivered to the client

**File:** `backend/agents/execution_engine/engine.py:3888-3936` × `backend/app/api/websocket.py:1976-1980`
**Issue:** Pre-14, the lineage write happened *before* the terminal emit, so a persist failure's `state_restoration_failed` reached the FE. After 14-03 the ordering is inverted: `execute()` yields `pipeline_complete` (forwarded to the queue), the drainer's terminal-break list (`websocket.py:1976-1980`) sees it and **exits the drain loop**, and only then does the engine attempt the exact-kind lineage write. On failure, `state_restoration_failed` is put on a queue nobody is draining; the bg task's `finally` then enqueues the sentinel and `_cleanup_pipeline` discards the queue. Net effect: a failed FR-014 chain-link-1 lineage write is completely invisible to the client — no event, and the row is recorded `"completed"` (`pipeline_complete_seen` is True and `_handle_revision` returns normally). The direct-call engine tests can't catch this because their `websocket_send_fn` captures everything; only the drainer interaction drops it.
**Fix:** Either (a) add `state_restoration_failed` to the drained vocabulary by not breaking until the `None` sentinel arrives after a terminal (the bg task always sends it promptly post-lineage-write), or (b) have the drainer, after a terminal break, drain any residual non-sentinel events from the queue once `revision_bg_task` finishes (it already awaits it with a 5s grace at websocket.py:1991-1994) and forward them before returning.

### WR-02: A degraded revision completion is recorded `"completed"` — terminal-status fidelity gap the run_pipeline path already fixed

**File:** `backend/app/api/websocket.py:1846-1895`
**Issue:** `execute()` emits `pipeline_complete` with `data.status == "degraded"` + `agents_failed` when an agent errored unrecovered (engine.py:1886-1890). `_run_revision_to_queue` keys terminal status only on `pipeline_complete_seen and not pipeline_failed_seen`, so a degraded revision (e.g., `ppt-revision-assembler` errored after the first agent ran) persists `status="completed"`. The run_pipeline handler explicitly distinguishes this case (`websocket.py:1530-1536`, the phase-13 IN-03 fix: degraded → `"degraded"`). This phase's own rationale (RESEARCH Pitfall 4) is that the FE's revision-parent lookup matches `status === "completed"` — a degraded revision whose deliverable may be a prior agent's partial output is therefore offered as a future revision parent, and the engine's lineage write equally proceeds on any truthy `final_output`.
**Fix:** Mirror the run_pipeline mapping in `_queue_send` / the success branch:
```python
if etype == "pipeline_complete":
    pipeline_complete_seen = True
    if event.get("data", {}).get("status") == "degraded":
        degraded_seen = True
...
_persist_terminal_status(
    "degraded" if degraded_seen
    else "completed" if (pipeline_complete_seen and not pipeline_failed_seen)
    else "failed"
)
```

### WR-03: Reconnect drainer breaks the pinned revision frame contract (`section: None` instead of the target artifact type)

**File:** `backend/app/api/websocket.py:800-816` (reconnect drainer) × `1929-1944` (revision drainer)
**Issue:** Phase 14 newly registers revision runs in `_PIPELINE_TASKS`/`_PIPELINE_QUEUES`, making them reconnect-discoverable (an advertised feature of `_handle_revision_execution`'s docstring). But the reconnect drainer wraps every event with `"section": None`, while the revision contract this phase pins (test_run_revision_ws_dispatch.py: "section is the TARGET artifact type, never the pipeline type") requires `section: <target_artifact_type>`. A client that reconnects mid-revision receives the remainder of the stream with a different frame shape than the stream it started on — if the FE revision panel routes frames on `section`, post-reconnect events are mis-routed or dropped.
**Fix:** When the reconnect path attaches to a live run, derive the section for revision runs from the run row (`WorkflowRun.type` ends with `_revision` → reconstruct the target as `f"{type.removesuffix('_revision')}_output"`), or persist the target on the row and use it. At minimum document the divergence and confirm the FE tolerates `section: None` on revision frames.

### WR-04: Stale AUTHZ comment in the revision WorkflowRun creation describes the workspace writeback Phase 14 deleted

**File:** `backend/app/api/websocket.py:1801-1812`
**Issue:** The comment block on `owner_id=user.id` still reads: "The workspace is the PARENT artifact's workspace (only resolvable inside the engine), so `_handle_revision` writes workspace_id back via `ScopedStore.set_run_scope` once `original` is read… the engine writeback completes the scope." That writeback was deleted in 14-03 (the engine diff removes the `store.set_run_scope`/sink-arm block); the actual behavior — proven by `test_revision_run_events_persist_and_resolve_on_real_db` — is that `execute()` mints the revision run's **own** workspace (not the parent's) and stamps it. A future maintainer debugging the (intentional) workspace split between the run row / run_events (minted workspace) and the exact-kind lineage ref (parent's workspace, engine.py write_ref `workspace_id=original.workspace_id`) will be actively misled by this comment in an authz-relevant code path.
**Fix:** Rewrite the comment to match 14-03 reality: row created with a real owner and transiently-null workspace; `execute()` mints the run's own workspace and completes the scope via its chokepoint `set_run_scope`; the lineage ref alone is stamped with the parent artifact's workspace.

## Info

### IN-01: Final bg-task wait swallows `CancelledError` (and lists redundant exception types)

**File:** `backend/app/api/websocket.py:1991-1994`
**Issue:** `except (asyncio.TimeoutError, asyncio.CancelledError, Exception): pass` — `TimeoutError` is already a subclass of `Exception` (3.11+), and explicitly absorbing `CancelledError` here means a cancellation arriving during the 5s grace window is suppressed and the task completes "normally" instead of cancelled. This is a verbatim copy of the run_pipeline pattern (websocket.py:1686-1688), so it is mirrored debt rather than new logic.
**Fix:** `except (TimeoutError, Exception): pass` at minimum; ideally let `CancelledError` propagate (`except asyncio.CancelledError: raise`).

### IN-02: `pipeline_cancelled` frame is typically never delivered on cancel — queued after the drainer is dead, then discarded by cleanup

**File:** `backend/app/api/websocket.py:1902-1910, 1983-1987`
**Issue:** On `cancel_pipeline`, the drainer task is cancelled first, then it cancels `revision_bg_task`, whose `CancelledError` handler enqueues `pipeline_cancelled` — onto a queue with no consumer, which `_cleanup_pipeline` then drops. The client receives no cancellation ack (the `cancel_pipeline` handler deliberately doesn't send one, per its comment at websocket.py:598-604 which assumes the task sends it). `test_cancellation_lands_row_cancelled` explicitly tolerates this ("queued or sent"). Mirrors the run_pipeline gap; flagged so the mirrored contract is a recorded decision, not an accident.
**Fix:** Have the `cancel_pipeline` handler send the ack itself when the cancelled task is a revision/pipeline drainer, or have the drainer's `CancelledError` path best-effort send `pipeline_cancelled` before re-raising.

### IN-03: Engine-raised validation errors changed frame shape (`section: None` → `section: <target_artifact_type>`) while ingress validation kept the old shape

**File:** `backend/app/api/websocket.py:874-887` vs `1896-1901` + `1965-1968`
**Issue:** Pre-14, every `run_revision` error frame carried `section: None`. After 14-02, ingress validation errors (`empty_revision_instruction`, `missing_revision_params`) keep `section: None`, but engine `ValueError`s (`revision_validation_error`) and runtime errors (`revision_error`) now ride the drainer wrapper with `section: <target_artifact_type>`. The new shape is deliberately pinned (test_run_revision_ws_dispatch.py:279-280), but the same error family now has two shapes depending on where validation fired. Worth confirming the FE error handling is section-agnostic.
**Fix:** None required if the FE keys only on `type`/`code`; otherwise normalize error frames to one `section` convention.

---

_Reviewed: 2026-06-12_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
