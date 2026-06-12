---
phase: 14-run-revision-real-revision-loop-f2-end-to-end
reviewed: 2026-06-12T14:30:00Z
depth: standard
iteration: 2
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
  critical: 0
  warning: 0
  info: 5
  total: 5
status: issues_found
---

# Phase 14: Code Review Report — Iteration 2 (fix verification)

**Reviewed:** 2026-06-12T14:30:00Z
**Depth:** standard (re-review of the `22e10df0^..HEAD` phase diff; fix commits `9ab3f7f2..4e700d15` traced line-by-line against the iteration-1 findings)
**Files Reviewed:** 10
**Status:** issues_found (Info only — no Critical, no Warning; all 6 in-scope iteration-1 findings verified fixed)

## Summary

All 6 Critical/Warning findings from iteration 1 are **correctly and completely fixed**, with no regressions and no new Critical/Warning issues introduced by the fixes. Each fix was verified against the live source (not just the diff), and every fix carries an executable pin. Verified in this review run: `test_run_revision_ws_dispatch` (10), `test_run_revision_fe_contract` (2), `test_revision_intelligence` (18), `test_ws_reconnect_replay` (7), `test_manifest_parity` (32), `test_id_alias_resolver` (60) — 129 passed; the 5 characterization suites + `test_banned_patterns` — 21 passed (INV-3 held with engine.py touched); `/opt/homebrew/bin/lint-imports` — 4 contracts kept, 0 broken.

**Fix-by-fix verification:**

- **CR-01 (overlap guard) — VERIFIED.** `websocket.py:899-910`: the guard is byte-identical to the run_pipeline guard (`pipeline_already_running`, `recoverable: True`), placed before ingress validation and before `current_pipeline_task` assignment (line 934). The cancel handle can no longer be overwritten; `asyncio.create_task` makes the handle not-done immediately, so the guard holds even before the task's first scheduling tick. The pin (`test_overlap_guard_rejects_second_run_revision`) drives the **real** `websocket_chat` receive loop via `_ScriptedLoopWebSocket` and asserts exactly one execution + one rejection — it tests the loop's guard, not a re-implementation. The guard also correctly cross-blocks: a running revision blocks `run_pipeline` (line 530 checks the same handle) and vice versa.
- **CR-02 (planner-flow target rejection) — VERIFIED.** `engine.py:3856-3862`: `compile_for_run(revision_pipeline_type).planner != "skip"` → `ValueError("not revision-dispatchable…")`, placed after the registry membership guard and **before any event emission or dispatch side effect** (the pin asserts `events == []` and zero refs written). The predicate is compiled-manifest data — SC-001 preserved, no workflow-name literal. Coverage check done in this review: all three non-flipped registered revision pipelines (`prototype_revision`, `user_stories_revision`, `app_builder_revision`) carry `planner: run` **and have manifests on disk**, so every escape path hits the clean ValueError (mapped to `revision_validation_error` + row persisted `"failed"` at websocket.py:1956-1962) — never a `FileNotFoundError` and never the clarify-gate hang. The pin seeds a realistic parent whose deliverable ref satisfies FR-014 link 2, proving the rejection comes from the planner guard, not the artifact lookup.
- **WR-01 (post-terminal `state_restoration_failed` delivery) — VERIFIED.** `websocket.py:1995, 2042, 2059-2084`: `terminal_break` is set only on the terminal-event break; the residual drain runs only when `terminal_break and revision_bg_task.done()` (after the existing 5s grace await), forwards non-sentinel events on the pinned wrapper (`section: <target_artifact_type>`), and stops at the sentinel. Queue ordering guarantees correctness: the engine's `state_restoration_failed` rides `_queue_send` before the bg task's `finally` sentinel, so the drain always delivers it before hitting `None`. Scoping is correct: a WS-death break leaves `terminal_break` False and the queue intact for the reconnect drainer; the local `event_queue` reference survives `_cleanup_pipeline`'s map removal. Terminal-vocabulary cross-check done: the engine's mid-stream agent failures emit `agent_error` (engine.py:2687, 2702), not `error` — engine-level `error` (engine.py:1103) is genuinely terminal (returns), so the drainer's break list cannot prematurely truncate a degraded run. Pinned with wrapper-shape, ordering, and row-status assertions.
- **WR-02 (degraded status fidelity) — VERIFIED.** `websocket.py:1896, 1913-1914, 1949-1955`: `degraded_seen` set on `pipeline_complete` with `data.status == "degraded"`; persist precedence `degraded > completed > failed` mirrors the run_pipeline 13 IN-03 mapping. Docstring updated to match (lines 1805-1813). Pinned, including the "not 'failed' — a deliverable DID complete" boundary.
- **WR-03 (reconnect live-attach section contract) — VERIFIED.** `websocket.py:656, 672-676, 807, 822`: `_reattach_section` is derived from the **owner-filtered** AUTHZ-03 gate row (never from client payload — no new tenant surface), via the generic inverse suffix transform (`od_ppt_revision` → `od_ppt_output`, exactly inverting the WR-06 forward transform at engine.py:3819-3821); non-revision runs keep `section: None` byte-identically (legacy reconnect suite green, 7 passed). Both the heartbeat and the event-forward frames in the live-attach drainer use it. Pinned by a real-receive-loop reconnect test against a seeded live revision run. One consciously-scoped residual remains (IN-04 below).
- **WR-04 (stale AUTHZ comment) — VERIFIED.** `websocket.py:1848-1859`: the rewritten comment matches 14-03 reality, cross-checked against the engine in this review: the chokepoint `set_run_scope` (engine.py:~804) mints/stamps the revision run's own workspace; only the exact-kind lineage ref carries the parent's workspace (engine.py:3923, `workspace_id=original.workspace_id`); the in-method writeback is gone. Accurate, including the proving-test pointer.

**Re-classification of the 3 iteration-1 Info findings:** all three remain genuinely Info (carried forward below as IN-01/IN-02/IN-03 — none is more severe than Info; IN-01's blast radius grew marginally but stays bounded). Two new Info-level residuals at the edges of the WR-01/WR-03 fixes are recorded (IN-04, IN-05). Nothing requires another fix iteration.

## Info

### IN-01: Final bg-task wait swallows `CancelledError` (carried from iteration 1 — mirrored run_pipeline debt)

**File:** `backend/app/api/websocket.py:2054-2057`
**Issue:** `except (asyncio.TimeoutError, asyncio.CancelledError, Exception): pass` — `TimeoutError` is redundant (subclass of `Exception` on 3.11+), and a cancellation landing inside the 5s grace window is absorbed. Verbatim copy of the run_pipeline pattern (mirrored debt). Iteration-2 note: the WR-01 residual drain now sits **after** this swallow, so a swallowed cancellation extends post-cancel execution by the residual drain — still bounded (non-blocking `get_nowait` + a handful of `send_json` calls), so this stays Info, but the swallow's blast radius is no longer zero.
**Fix:** `except asyncio.CancelledError: raise` before the broad except, or drop `CancelledError` from the tuple.

### IN-02: `pipeline_cancelled` ack typically never delivered on cancel (carried from iteration 1 — mirrored run_pipeline contract)

**File:** `backend/app/api/websocket.py:2045-2050, 1963-1971`
**Issue:** Unchanged by the fixes: on `cancel_pipeline` the drainer is cancelled first (re-raises at line 2050, so the residual drain is — correctly — never reached), and the bg task's `pipeline_cancelled` lands on a consumerless queue that `_cleanup_pipeline` discards. The test still tolerates "queued or sent". Recorded so the mirrored contract is a decision, not an accident.
**Fix:** Have the `cancel_pipeline` handler send the ack itself, or best-effort send in the drainer's `CancelledError` path before re-raising.

### IN-03: Two `section` shapes for the same revision-error family (carried from iteration 1)

**File:** `backend/app/api/websocket.py:916-929` vs `1956-1961` + `2024-2027`
**Issue:** Unchanged: ingress validation errors (`empty_revision_instruction`, `missing_revision_params`) and the CR-01 rejection carry `section: None`; engine-raised errors (`revision_validation_error` — now also the CR-02 rejection — and `revision_error`) ride the drainer wrapper with `section: <target_artifact_type>`. Deliberately pinned; only matters if the FE routes error frames on `section`.
**Fix:** None required if the FE keys on `type`/`code`; otherwise normalize.

### IN-04: Durable-replay frames for revision runs still carry `section: None` (residual scope of the WR-03 fix)

**File:** `backend/app/api/websocket.py:763-768, 777-786, 792-796`
**Issue:** The WR-03 fix covers the live-attach drainer only (as the finding specified, and as the fixer documented). The durable `run_events` tail replay — entered after a backend restart, or whenever a reconnecting client supplies `after_seq` — and the `pipeline_reconnected` ack still wrap every frame with `section: None`. Since Phase 14 made revision runs replay-discoverable (chokepoint run_events persistence + `_PIPELINE_TASKS` registration), a revision client reconnecting with `after_seq` against a live run receives a mixed-shape stream: replayed tail `section: None`, then live remainder `section: <target>`. Info, not Warning: the primary mis-routing risk (the ongoing live stream) is fixed, the pure-replay case delivers historical frames for a no-longer-live run, and the FE dedupes by `event_id`.
**Fix:** When `_reattach_section` is non-None (already derived from the owner-filtered row before the replay block runs in the live-task case), use it for the replay wrapper too; for the no-live-task case, derive it the same way from the `_replay_store.get_run` row already fetched at line 776. At minimum, confirm the FE revision panel tolerates `section: None` on replayed frames.

### IN-05: Residual drain is skipped when the bg task outlives the 5s grace — post-terminal events still droppable in that window (residual scope of the WR-01 fix)

**File:** `backend/app/api/websocket.py:2054-2057, 2069`
**Issue:** The residual drain requires `revision_bg_task.done()`. If the post-terminal work (the exact-kind lineage write — a DB write — plus `state_restoration_failed` emission on its failure) takes longer than the 5s `wait_for` grace, the drain is skipped, the coroutine returns, and the bg task's eventual `finally` → `_cleanup_pipeline` discards the queued event exactly as pre-fix. A narrow timing edge of an already-degraded diagnostic path (row status is still persisted correctly by the bg task), hence Info.
**Fix:** Loop the residual drain on `await event_queue.get()` until the sentinel instead of gating on `done()` (the sentinel is guaranteed by the bg `finally`), or raise the grace timeout for the terminal-break path.

---

_Reviewed: 2026-06-12T14:30:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
_Iteration: 2 — fix verification for 9ab3f7f2..4e700d15_
