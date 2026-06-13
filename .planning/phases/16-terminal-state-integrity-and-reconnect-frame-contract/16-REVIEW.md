---
phase: 16-terminal-state-integrity-and-reconnect-frame-contract
reviewed: 2026-06-13T00:00:00Z
depth: standard
files_reviewed: 13
files_reviewed_list:
  - backend/agents/execution_engine/engine.py
  - backend/app/api/websocket.py
  - backend/tests/agents/test_engine_runner_error_arm.py
  - backend/tests/agents/test_model_fallback.py
  - backend/tests/agents/test_ws_reconnect_replay.py
  - backend/tests/unit/test_pipeline_cancel.py
  - backend/tests/unit/test_run_revision_ws_dispatch.py
  - frontend/src/app/dashboard/page.tsx
  - frontend/src/components/layout/DashboardLayout.tsx
  - frontend/src/components/preview/PreviewPanel.degraded.test.tsx
  - frontend/src/components/preview/PreviewPanel.tsx
  - frontend/src/hooks/useWorkflow.ts
  - frontend/src/types/index.ts
findings:
  critical: 0
  warning: 3
  info: 4
  total: 7
status: issues_found
---

# Phase 16: Code Review Report

**Reviewed:** 2026-06-13
**Depth:** standard
**Files Reviewed:** 13
**Status:** issues_found

## Summary

Phase 16 implements clusters A+B (terminal-state integrity + reconnect frame-contract) against the locked CONTEXT.md design. The core backend mechanics are correct and match the intended contract:

- **ISS-016 (engine error arm):** the new `elif etype == "error":` arm (engine.py:2408) records `agent_errored`, breaks the stream, and the post-loop block (engine.py:2539) emits a recoverable `agent_error` and `return`s WITHOUT appending a result or emitting `agent_complete`. This correctly feeds `_failed_agent_ids` → F3 `pipeline_failed` (all-fail) / `status:degraded` (partial). Branch keys on the generic event type only (SC-001-clean). The arm is dormant on goldens (the scripted model never raises). Test coverage (`test_engine_runner_error_arm.py`, `test_model_fallback.py::test_non_transient_propagates`) is genuine and the previously-bug-encoding test was correctly flipped.
- **ISS-007/002 (cooperative cancel):** `cancel_pipeline` now `cancel_event.set()`s (websocket.py:641) instead of destructively cancelling the drainer; destructive `task.cancel()` is correctly preserved ONLY on the disconnect path (websocket.py:1268) and as a defensive fallback when the run-id sink is empty (websocket.py:647). The engine's pre-agent cancel gap is closed (engine.py:1509-1533) with a normal `pipeline_cancelled` yield + `return`. The 3 drainer sites use `asyncio.timeout()`. The persist blocks track `pipeline_cancelled_seen` so a cooperatively-cancelled run records "cancelled". Owner/connection scoping holds (the cancel resolves only via the connection-local `_run_id_sink`).
- **ISS-008/009 (reconnect frame-contract):** `_replay_section` is derived ONCE before the replay loop from the owner-scoped run row's `type` via the WR-06 inverse (websocket.py:794-818), behind the `owner_id == user.id` filter — no cross-owner section leak. The live-attach ack now carries `live: True` (websocket.py:871). Tests pin both.

The defects below are real but none are correctness-breaking on the primary live paths. The most consequential is the **history-reopen `degraded` gap** (WR-01): a run that ISS-016 newly produces as `status:degraded` renders neither its partial deliverable nor the failure affordance when reopened from history.

## Warnings

### WR-01: `degraded` history-reopen renders neither deliverable nor failure affordance

**File:** `frontend/src/app/dashboard/page.tsx:1015,1030-1034`
**Issue:** ISS-016 newly persists `wr.status = "degraded"` for partially-failed runs (websocket.py:1699), and `getWorkflow` casts the raw status through (`api.ts:288` — `raw.status as WorkflowRun["status"]`), so a reopened degraded run carries `fullRun.status === "degraded"`. On the history-reopen path:
- The content gate at `page.tsx:1015` is `fullRun.output && fullRun.status === "completed"` — a degraded run has real (partial) `output` but `status !== "completed"`, so its deliverable is NOT set.
- The affordance gate at `page.tsx:1030-1034` only maps `"failed" | "cancelled"` into `reopenedRunStatus` — `"degraded"` falls through to `undefined`.

Net: a degraded run reopened from history shows the neutral "Output will appear here" empty-state — neither its partial deliverable nor the ISS-017 degraded affordance. CONTEXT A2 explicitly requires the affordance "on BOTH the live path and the history-reopen path." The live path handles degraded (useWorkflow.ts:348); only the history path regresses.
**Fix:** Treat `"degraded"` on both gates. Either render the partial deliverable (preferred — it exists), or at minimum surface the affordance:
```ts
// content: include degraded so the partial deliverable still renders
if (fullRun.output && (fullRun.status === "completed" || fullRun.status === "degraded")) { ... }

// affordance: degraded with no content should also flag
setReopenedRunStatus(
  fullRun.status === "failed" || fullRun.status === "cancelled" || fullRun.status === "degraded"
    ? fullRun.status
    : undefined,
);
```
Also widen `WorkflowStatus` (types/index.ts:248) to include `"degraded"` (and `"revising"`) so the cast at api.ts:288 is honest and the comparisons type-check.

### WR-02: Raw runner/exception text forwarded to the client unsanitized

**File:** `backend/agents/execution_engine/engine.py:2423,2551`
**Issue:** The ISS-016 error arm captures `agent_error_message = str(event.get("error", "") or "")[:500]` (engine.py:2423) — the runner's raw `str(exc)` (deep_agent_runner.py:527) — and emits it verbatim in the `agent_error` event `data.error` (engine.py:2551). The WS drainer forwards that data to the browser (websocket.py:1599 → 1826) and also persists it to `wr.error` (websocket.py:1709). CONTEXT A1 / T-16-01-ID calls for a "bounded/sanitized" message with "no stack frames/secrets." It is bounded (500 chars) and `str(exc)` is not a traceback, but for a non-throttle exception other than the benign `ValidationException` ("Operation not allowed"), `str(exc)` can carry ARNs, region, model-id, or internal config detail straight to the end user. The chat path deliberately routes through `_map_llm_exception` to produce a sanitized `{message, code}` triple (websocket.py:1216); this new path does not.
**Fix:** Map the runner error through the existing `app.agents.llm_errors.map_exception` (or a small sanitizer) before placing it on the `agent_error` event, mirroring the chat path. At minimum, emit a generic client-facing message (e.g. "The model rejected this request.") and log the raw `str(exc)` server-side only.

### WR-03: Stale comment in the runner asserts the engine ignores `error` events

**File:** `backend/app/agents/deep_agent_runner.py:514-516`
**Issue:** The non-throttle swallow comment states: "so non-throttle behavior is byte/semantically identical to today (the engine ignores `error` events) — INV-3 parity for the non-throttle path is preserved." After Phase 16 the engine NO LONGER ignores `error` events — it consumes them (engine.py:2408) and surfaces `agent_error` / `pipeline_failed`. The runner output is unchanged, but the rationale is now false and will mislead the next maintainer into thinking the error event is inert. (Flagged because CONTEXT names deep_agent_runner.py:507-527 as a behavior anchor and the comment is load-bearing documentation of the contract.)
**Fix:** Update the comment to state that the engine's ISS-016 (Phase 16) consume-arm now turns this `error` yield into a recoverable `agent_error`; INV-3 parity holds only because the scripted golden model never raises (the arm is dormant on goldens), not because the engine ignores the event.

## Info

### IN-01: `reopenedFailedAgents` prop is declared and consumed but never wired

**File:** `frontend/src/components/preview/PreviewPanel.tsx:184,291`
**Issue:** `PreviewPanel` declares and reads `reopenedFailedAgents` (used in the `failedAgentNames` fallback chain at line 291), but neither `DashboardLayout` (no such prop in `DashboardLayoutProps`) nor `dashboard/page.tsx` ever passes it. The only place it receives a value is `PreviewPanel.degraded.test.tsx:158`. On the real history-reopen path the affordance always renders with an empty failed-agent list. Dead wiring — the test gives false confidence that failed-agent names appear on reopen.
**Fix:** Either thread the reopened run's `agents_failed` (from the run detail payload / `wr.error` parse) through `DashboardLayout` → `PreviewPanel`, or drop the unused prop to avoid implying functionality that does not exist.

### IN-02: Affordance lists raw agent IDs, not display names

**File:** `frontend/src/components/preview/PreviewPanel.tsx:222-226`
**Issue:** `DegradedRunAffordance` renders `failedAgents` (sourced from `pipelineState.failedAgents` / `agents_failed`, which are agent IDs like `domain-analyst`) directly as the user-facing "Failed agents" list. Users see kebab-case internal IDs rather than the human-readable `name` field. Cosmetic only.
**Fix:** Resolve IDs to display names via the agent registry / `pipelineState.agents` before rendering, or label the block "Failed steps (ids)".

### IN-03: `cancelled` reopen labelled "failed or degraded"

**File:** `frontend/src/components/preview/PreviewPanel.tsx:206-207`
**Issue:** The affordance copy reads "The run ended in a failed or degraded state," but `reopenFailureSignal` also fires for `reopenedRunStatus === "cancelled"` (a deliberate user Stop, not a failure). Minor mislabel; the test `reopen+cancelled` (degraded.test.tsx:167) asserts the affordance shows but does not check the wording.
**Fix:** Branch the copy on the cancelled vs failed/degraded distinction (e.g. "This run was cancelled before producing a deliverable.").

### IN-04: Per-chunk cooperative cancel still double-emits `pipeline_cancelled` (pre-existing)

**File:** `backend/agents/execution_engine/engine.py:2357-2358,1699` + `backend/app/api/websocket.py:1742`
**Issue:** The per-chunk cooperative check raises `asyncio.CancelledError()` (engine.py:2358), which the dispatch-loop handler turns into a yielded `pipeline_cancelled` AND re-raises (engine.py:1699-1700); the WS bg task's `except asyncio.CancelledError` then queues a SECOND `pipeline_cancelled` (websocket.py:1742). The client sees only one because the drainer breaks on the first terminal and the duplicate is discarded by cleanup — so it is client-invisible. This is pre-existing (predates Phase 16) and the new pre-agent path (engine.py:1533) correctly avoids it by returning instead of raising. Noted for completeness; not a Phase-16 regression and no client-visible impact.
**Fix:** None required for this phase. If revisited, make the per-chunk path mirror the pre-agent path (yield `pipeline_cancelled` + `return` cooperatively rather than raising) so the two cancel paths are symmetric and the duplicate frame is eliminated at the source.

---

_Reviewed: 2026-06-13_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
