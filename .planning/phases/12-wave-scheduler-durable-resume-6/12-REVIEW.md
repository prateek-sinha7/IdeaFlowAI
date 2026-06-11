---
phase: 12-wave-scheduler-durable-resume-6
reviewed: 2026-06-11T11:39:36Z
depth: standard
files_reviewed: 13
files_reviewed_list:
  - backend/agents/capabilities/strategies/wave_scheduler.py
  - backend/agents/capabilities/task_parsers/json_tasks.py
  - backend/agents/execution_engine/engine.py
  - backend/app/api/websocket.py
  - backend/tests/agents/test_json_tasks.py
  - backend/tests/agents/test_restart_resume.py
  - backend/tests/agents/test_wave_scheduler.py
  - backend/tests/agents/test_ws_reconnect_replay.py
  - frontend/src/app/dashboard/page.tsx
  - frontend/src/components/workflow/WaveTreePanel.tsx
  - frontend/src/lib/wsReplayState.test.ts
  - frontend/src/lib/wsReplayState.ts
  - frontend/src/types/index.ts
findings:
  critical: 0
  warning: 11
  info: 6
  total: 17
status: issues_found
---

# Phase 12: Code Review Report (Re-Review After Gap Closure)

**Reviewed:** 2026-06-11T11:39:36Z
**Depth:** standard (re-review; diff base f8a0c9c2)
**Files Reviewed:** 13
**Status:** issues_found

## Summary

This is the re-review after gap-closure plans 12-05/12-06/12-07. **All six prior Criticals (CR-01..CR-06) are verified fixed in code, each with a regression test that fails on the pre-fix shape.** The in-scope warnings (WR-01, WR-03, WR-05) and infos (IN-05, IN-06) are also fixed — with one significant residue: the WR-01 fix landed only its strategy half. The new `superseded` status the strategy writes is recognized **nowhere else** — `_first_incomplete_step` still buckets any non-`completed` wave row as "running", so the permanent-incomplete classification WR-01 was meant to cure persists across a second restart (WR-09 below).

The new-issue hunt around the gap fixes surfaced six new Warnings, all in the resume tier: the `is_resuming`/planner-skip predicates are keyed on `_resume_from > 0` while the workspace-recovery predicate was correctly widened to `_is_resume` — so an offset-0 resume re-runs the planner into a forced clarify gate with no client and leaves the wave mid-wave skip dormant (WR-10); `resume_run`'s failure paths leave the run non-terminal forever, producing an infinite resume-attempt loop across restarts (WR-11); the resume driver task is created without holding a reference and can be garbage-collected mid-drive (WR-12); the resumed run's re-emitted `pipeline_start` makes the FE wipe its just-replayed dedup/wave state mid-replay (WR-13); and a wave step that declares `retry` re-runs already-completed waves on a transient retry because the durable skip is gated on `is_resuming` (WR-14). No new Criticals: none of these lose data — they waste model spend, strand runs in recoverable states, or degrade the reconnect UX.

Five prior Warnings (WR-02, WR-04, WR-06, WR-07, WR-08) and four prior Infos (IN-01..IN-04) were deliberately deferred (the CR-03-followup per-task-skip deferral is recorded in 12-CONTEXT.md:176, Deferred Ideas) and are carried forward unchanged at their original severities.

## Narrative Findings (AI reviewer)

## Prior-Finding Verification

### Criticals — all fixed

| ID | Verdict | Evidence |
|----|---------|----------|
| CR-01 (resume seq restarts at 1) | **FIXED** | `engine.py:4049-4067` — `resume_run` recovers the original workspace, reads the durable tail, and seeds `counter = itertools.count(start)` with `start = max(seq)+1`. Regression: `test_restart_resume.py::test_resumed_events_seq_continues_past_durable_tail` (asserts min resumed seq == N+1 and that `read_events(after_seq=N)` is non-empty). |
| CR-02 (WS replay scoped to `workspace_id IS NULL`) | **FIXED** | `websocket.py:608-638` — the handler recovers the run's workspace from a RunEvent row filtered by `owner_id == user.id` (never from client input), then builds `ScopedStore(owner_id=user.id, workspace_id=_recovered_ws)`. Regression: `test_ws_reconnect_replay.py::test_production_shaped_replay_recovers_workspace_and_returns_rows` (also proves the pre-fix construction returns 0 rows) and `::test_cross_owner_workspace_recovery_yields_empty_replay` (IDOR boundary holds). |
| CR-03 (leading-N prefix skip drops parallel tasks) | **FIXED** | `wave_scheduler.py:222-224` — the first incomplete wave re-runs in its **entirety** (`task_ids = [t.id for t in wave]`, no slice; `_completed_worker_count` deleted). Regression: `test_restart_resume.py::test_midwave_resume_reruns_whole_inflight_wave_no_parallel_dropout` (terminal workers ≠ leading tasks; asserts wave 1 re-runs `{t3, t4}` whole). The per-task skip is the recorded CR-03-followup deferral (12-CONTEXT.md:176). |
| CR-04 (cross-step wave-index contamination) | **FIXED** | `wave_scheduler.py:200-206` — `_completed_wave_indices` is step-filtered (`getattr(r, "step", None) == step_id`). Regression: `test_restart_resume.py::test_cross_step_does_not_skip_second_steps_waves`. |
| CR-05 (FE dedupes only wave events) | **FIXED** | `page.tsx:200-214` — `shouldApplyEvent` runs at the **top** of `handleWebSocketMessage` before any routing; cursor advance (`page.tsx:216-221`) happens only after the dedup passes, so a duplicate never re-advances `after_seq`. Pure helper + tests: `wsReplayState.ts:32-40`, `wsReplayState.test.ts`. |
| CR-06 (worker leaves never render / same-agent collapse) | **FIXED** | Backend half: `wave_scheduler.py:262-266` stamps `wave_index` + `step` onto `subagent_spawned`/`subagent_result` at the strategy re-yield boundary (copy-on-stamp, non-subagent events pass through unstamped). FE half: `page.tsx:283-294` keys worker leaves by the numeric `worker` index with agent-name fallback. Regression: `test_wave_scheduler.py::test_subagent_events_carry_wave_index_and_step`. `fanout.py` confirmed to emit `worker` as a number (`fanout.py:469,509,523`). |

### In-scope Warnings/Infos — fixed

- **WR-01 — FIXED (strategy half; see WR-09 for the engine-half residue):** `wave_scheduler.py:229-241` flips stale `running` rows for the re-entered `(step, wave_index)` to `superseded` before recording the re-entry row. Regression: `test_restart_resume.py::test_stale_running_wave_row_is_flipped_terminal_on_resume`.
- **WR-03 — FIXED:** `page.tsx:336-345` resets seen-set/`lastSeqRef`/`waveGroups` on `pipeline_start` (re-recording `pipeline_start`'s own event_id post-reset); pure `resetReplayState` + tests (`wsReplayState.ts:60-64`, `wsReplayState.test.ts:36-75`). See WR-13 for a new interaction with resumed runs.
- **WR-05 — FIXED:** `json_tasks.py:120-129` raises a named ValueError on a duplicate id (primary gate); `wave_scheduler.py:79-85` raises `WaveBuildError` defense-in-depth. Regressions: `test_json_tasks.py::test_duplicate_task_id_raises_named_valueerror`, `test_wave_scheduler.py::test_build_waves_rejects_duplicate_task_id_before_any_wave`.
- **IN-05 — FIXED:** `WaveTreePanel.tsx:36-38` buckets `cancel*` as terminal (failed).
- **IN-06 — FIXED:** wave groups keyed by `(step, waveIndex)` — `page.tsx:241-248`, React keys `WaveTreePanel.tsx:99` and `:121`.

## Critical Issues

None found in this pass.

## Warnings

### WR-09 (NEW): `_first_incomplete_step` does not recognize `superseded` as terminal — the WR-01 permanent-incomplete classification survives the fix

**File:** `backend/agents/execution_engine/engine.py:3917-3920`; writer `backend/agents/capabilities/strategies/wave_scheduler.py:229-241`
**Issue:** The strategy's WR-01 comment claims flipping the stale row to `superseded` prevents `_first_incomplete_step` from reading the wave step as permanently incomplete — but `_first_incomplete_step` was never updated: it buckets every row with `status != "completed"` into `running_wave_steps` (`else: running_wave_steps.add(sid)`). `superseded` appears nowhere in `engine.py`/`kernel_services.py`/`wave_run.py` (grep-verified). So after any resume that superseded a row, a **second** restart still classifies the wave step incomplete, the resume offset lands on the wave step, and the dispatch loop re-runs **every downstream step** from there (the loop only skips `i < _resume_from`; downstream steps get no content-hash reuse unless they declare `retry`) — including downstream steps whose durable evidence shows them complete, re-spending models and potentially overwriting a finished deliverable with different bytes. `failed` rows from a retried wave attempt poison the classification the same way.
**Fix:**
```python
if status == "completed":
    terminal_wave_indices_by_step.setdefault(sid, set()).add(int(widx))
elif status in ("superseded", "cancelled", "failed_superseded"):
    pass  # terminal/replaced — not evidence of an in-flight wave
else:
    running_wave_steps.add(sid)
```
and/or have `_first_incomplete_step` only treat a wave row as "running" when no later row for the same `(step, wave_index)` is terminal. Add a restart-after-resume regression test (two consecutive resumes over the same durable DB).

### WR-10 (NEW): offset-0 resume — `is_resuming` and the planner-skip are keyed on `_resume_from > 0`, not `_is_resume`

**File:** `backend/agents/execution_engine/engine.py:699, 1117, 1130` (contrast the correctly-widened predicate at `:741`)
**Issue:** The CR-01 gap fix deliberately widened the workspace-recovery predicate to `(_is_resume or _resume_from > 0)`, but the two other resume-sensitive switches still key on the offset alone. A resume whose offset computes to 0 — `_compute_resume_offset` failure (returns 0, `engine.py:4137-4142`), or a crash before any step completed — therefore runs as if it were a fresh run: (a) `skip_planner` stays False, so the planner **re-runs** and the manifest-default `clarify.mode: auto` forces `CLARIFY_REQUIRED` → the resumed run parks in `waiting_for_user` with **no connected client and no way to deliver the questions** (it already cleared clarify once before the crash); (b) `ectx.is_resuming` stays False, so a wave step reached at offset 0 skips the durable wave read entirely — completed waves are re-fanned-out (duplicate worker spawns/cost, duplicate `wave_runs` rows, and the WR-01 supersede flip never fires because `_resuming` is False in the strategy).
**Fix:** Key both off the resume flag: `ectx.is_resuming = _is_resume or _resume_from > 0` and `_resuming = _is_resume or _resume_from > 0` at `engine.py:1117`. Decide clarify behavior for resumed runs explicitly (skip, or re-park via branch (a) semantics) rather than inheriting the fresh-run auto-clarify.

### WR-11 (NEW): `resume_run` failure paths leave the run non-terminal forever — infinite resume-attempt loop across restarts

**File:** `backend/agents/execution_engine/engine.py:3995-4018, 4093-4094`; classifier `engine.py:3036-3068`
**Issue:** When `resume_run` bails (no `workflow_runs` row, empty/unresolvable agent list — e.g. a `custom` workflow with no static registry membership — or a mid-drive exception caught at `:4093`), it only logs and returns; the run keeps its non-terminal status. On the **next** restart `_is_resumable_in_flight` classifies it resumable again (the durable `run_events` evidence persists — and each attempt's `run_resuming` marker row itself is evidence), so the system stamps another marker and re-attempts the same doomed resume on **every** restart, forever. This is exactly the phantom-live-row condition the WR-05 branch (c) abandoned→failed path exists to prevent — branch (b)'s failure mode bypasses it.
**Fix:** On a permanent resume failure (no agents / compile failure / non-transient drive exception), flip the run to `failed` with an explanatory error, mirroring branch (c). Optionally cap resume attempts by counting prior `run_resuming` markers before re-attempting.

### WR-12 (NEW): the resume driver task is fire-and-forget — `asyncio.create_task` result is dropped and the task can be garbage-collected mid-drive

**File:** `backend/agents/execution_engine/engine.py:3004-3006`
**Issue:** `_asyncio.create_task(self.resume_run(pipeline_run_id))` keeps no reference to the returned task. The event loop holds only a weak reference to tasks (documented CPython asyncio pitfall, ruff RUF006): a resume mid-drive can be silently collected, halting the run with no log, no status flip, and no retry — the run then sits non-terminal until the next restart (compounding WR-11).
**Fix:**
```python
task = _asyncio.create_task(self.resume_run(pipeline_run_id))
self._resume_tasks.add(task)          # engine-level set
task.add_done_callback(self._resume_tasks.discard)
```

### WR-13 (NEW): the resumed run re-emits `pipeline_start` mid-seq — the FE per-run reset wipes the just-replayed dedup/wave state during a durable reconnect

**File:** `frontend/src/app/dashboard/page.tsx:336-345`; emitter `backend/agents/execution_engine/engine.py:1280-1292`
**Issue:** `_execute_impl` yields `pipeline_start` unconditionally, so a resumed run's durable tail contains a **second** `pipeline_start` (seq continuing past the pre-crash tail). The FE resets all replay state on **every** `pipeline_start` without checking run identity, so when a reconnecting client replays a resumed run's tail in order, the second `pipeline_start` (a) empties `waveGroups` mid-replay — and because the strategy skips completed waves silently (no re-emitted `wave_*` events), the pre-crash waves **never come back**: the §22 tree shows only the re-run waves after a restart; (b) clears the seen-event_id set and zeroes `lastSeqRef`; the cursor recovers from subsequent events, but if `pipeline_start` happens to be the last replayed event the next reconnect sends `after_seq=0` and re-applies the entire pre-crash tail **undeduped** (the seen-set was just cleared) — duplicated streamed text. Also, the reset never re-applies the resetting event's own `seq`, leaving the cursor one short until the next event.
**Fix:** Reset only on a run-identity change (`data.pipeline_run_id !== activeRunIdRef.current`), not on every `pipeline_start`; after a reset, re-apply the triggering event's own `seq` to `lastSeqRef` alongside its event_id.

### WR-14 (NEW): a wave step that declares `retry` re-runs already-completed waves on a transient retry — the durable wave skip is gated on `is_resuming`

**File:** `backend/agents/capabilities/strategies/wave_scheduler.py:198-206`; wrapper `backend/agents/execution_engine/engine.py:3638-3662`
**Issue:** `_dispatch_step_with_retry` re-invokes `strategy.run(step, ectx)` on a transient mid-wave failure. Within the same process `ectx.is_resuming` is False, so attempt 2 skips the `read_wave_runs()` consult entirely and re-dispatches from wave 0 — re-spawning every worker of every already-completed wave (amplified up to `max_attempts`), inserting duplicate `wave_runs` rows per index, and leaving attempt 1's `failed` row to poison `_first_incomplete_step` (WR-09). The `wave_scheduler` is `user_allowed=True` and `retry` is an open manifest knob, so a user-composed workflow hits this without any engine change. No shipped manifest declares retry on a wave step today, which is why no test catches it.
**Fix:** Read the step-filtered completed wave indices unconditionally (the read is cheap and `None`-degrading offline) instead of gating on `is_resuming` — a normal first run has no completed rows, so behavior stays byte-identical; alternatively have the retry wrapper set `ectx.is_resuming = True` for re-attempts of a wave step, or document that wave steps must not declare `retry`.

### WR-02 (CARRIED, deferred): `_first_incomplete_step` misclassifies a wave step as complete when the crash lands between waves

**File:** `backend/agents/execution_engine/engine.py:3947-3957`
**Issue:** Unchanged from the prior review: a wave step is "complete" with ≥1 terminal wave row and none running; a crash in the window after `update_wave_run(completed)` for wave k and before `record_wave_run` for wave k+1 leaves only terminal rows, so waves k+1..n are never executed and the run finalizes with a partial deliverable. Deliberately deferred.
**Fix:** Persist/derive the expected wave count (re-run `build_waves` over the persisted plan, or persist `total_waves`) and treat the step incomplete unless all indices are terminal.

### WR-04 (CARRIED, deferred): `_is_resumable_in_flight`'s `run_events`/`wave_runs` evidence reads are dead in production

**File:** `backend/agents/execution_engine/engine.py:3055-3065`
**Issue:** Unchanged: the classifier builds `ScopedStore(owner_id=..., workspace_id=wr.workspace_id)`; normal pipeline runs never write `workflow_runs.workspace_id`, so the strict scope filters to `workspace_id IS NULL` → ∅, and classification hinges solely on the artifact `tree()` visibility OR-branch. A run that crashed before its first typed artifact is force-failed instead of resumed. Note `resume_run` itself now recovers the workspace correctly (`engine.py:4052`) — only the classifier still has the dead reads. No test drives `restore_non_terminal_runs` end-to-end into a TRUE branch (b) (the mid-wave test calls `resume_run` directly). Deliberately deferred.
**Fix:** Reuse `_recover_workspace_id(owner_id, wr.id)` before constructing the classifier's store; add an end-to-end branch (b) test.

### WR-06 (CARRIED, deferred): cancellation mid-wave leaves the `wave_runs` row stuck `running`

**File:** `backend/agents/capabilities/strategies/wave_scheduler.py:268-274`
**Issue:** Unchanged: `except Exception` does not catch `asyncio.CancelledError`; a Stop mid-wave skips the terminal flip and the documented `cancelled` status is never written — the stuck `running` row then feeds the WR-09 classification poison. Deliberately deferred.
**Fix:** `except asyncio.CancelledError: await runner.update_wave_run(row_id, status="cancelled"); raise` before the generic handler.

### WR-07 (CARRIED, deferred): a resumed run cannot be cancelled (and never streams live)

**File:** `backend/agents/execution_engine/engine.py:4066-4092`
**Issue:** Unchanged: `resume_run` passes no `cancel_event` and registers nothing in `_PIPELINE_TASKS`/`_PIPELINE_QUEUES`, so the WS stop path has no handle on a resumed run and a connected client receives resumed events only by repeated reconnect-replays (no live drain). A runaway resumed run can only be stopped by killing the process — which auto-resumes it again (see WR-11). Deliberately deferred.
**Fix:** Create + register an `asyncio.Event` and the driver task under the run id in the WS registries.

### WR-08 (CARRIED, deferred — behavior shifted, see WR-10): planning/clarify-crashed runs are auto-resumed with planner state unreconciled

**File:** `backend/agents/execution_engine/engine.py:1112-1136, 3036-3068`
**Issue:** The original finding (planner force-skipped for runs that died in planning) has shifted shape: offset-0 resumes now **re-run** the planner (and hit the WR-10 forced-clarify hang), while offset>0 resumes still force-skip it without restoring the original run's planner overlay/clarify answers — the resumed run can execute under a different effective plan than the original. Deliberately deferred.
**Fix:** Persist/restore the planning outcome (planning_context + clarify answers) before forcing the planner skip; gate branch (b) on durable evidence of build progress.

## Info

### IN-01 (CARRIED, deferred): `_did_replay` is assigned but never read

**File:** `backend/app/api/websocket.py:593, 657`
**Issue:** Unchanged dead variable.
**Fix:** Remove it.

### IN-02 (CARRIED, deferred): `replayed_through_seq` reports the requested `after_seq`, not the last replayed seq

**File:** `backend/app/api/websocket.py:668`
**Issue:** Unchanged: a client persisting this as its cursor would re-request the same tail.
**Fix:** Report `_missed[-1].seq if _missed else _after_seq`.

### IN-03 (CARRIED, deferred): the fence regex extracts the first fenced block, not the JSON one

**File:** `backend/agents/capabilities/task_parsers/json_tasks.py:37`
**Issue:** Unchanged: `_FENCE_RE.search` picks the first ``` block anywhere in the prose; an unrelated fenced example before the ```json plan parses the wrong block. (Same family: a plain-JSON payload whose task `body` contains a ``` sequence gets the inner segment extracted and fails parse — error is clean, not a crash.)
**Fix:** Prefer an explicitly `json`-tagged fence first, then fall back.

### IN-04 (CARRIED, deferred): `_compute_resume_offset` fallback comment overclaims content-hash reuse, and mints orphan workspace rows

**File:** `backend/agents/execution_engine/engine.py:4104-4119`
**Issue:** Unchanged: the docstring still says re-driving from 0 reuses completed steps via the content-hash key, but reuse activates only for steps declaring `retry.max_attempts > 0` (no shipped manifest does) — an offset-0 resume re-invokes every model (and now also hits WR-10). The `create_workspace(run_id)` fallback still mints a workspace row just to compute an offset.
**Fix:** Correct the comment; drop the `create_workspace` fallback (a `None` workspace yields no durable evidence → offset 0 anyway).

### IN-07 (NEW): the `run_resuming` marker's payload lacks `seq`/`event_id` — invisible to the FE cursor and dedup on replay

**File:** `backend/agents/execution_engine/engine.py:3087-3097`
**Issue:** Every sink-persisted event carries `seq`/`event_id` **inside** `payload_json` (the wrapper stamps `data` before persisting), and the WS replay forwards `payload_json` as the frame's `data`. The marker is appended with `seq`/`event_id` only on the row columns, not in the payload — so a replayed marker never advances `lastSeqRef` and is never deduped (legacy passthrough). A reconnect whose tail ends at the marker re-replays it on every subsequent reconnect (harmless no-op, but inconsistent with the contiguous-cursor contract).
**Fix:** Include `"seq": next_seq, "event_id": <uuid>` in the marker's `payload_json`.

### IN-08 (NEW): the websocket replay branch is still never executed by a test — the suite mirrors its logic instead of driving it

**File:** `backend/tests/agents/test_ws_reconnect_replay.py:158-199`; subject `backend/app/api/websocket.py:560-672`
**Issue:** The prior CR-02 was masked by exactly this pattern (tests constructed the store differently than the handler). The new tests now faithfully **mirror** the handler's construction (including the owner-scoped workspace-recovery query, `:184-199`), which closes today's gap — but the handler code itself (predicate, int-coercion, recovery, send loop, status frame) still has zero direct coverage, so the mirror and the handler can silently drift again.
**Fix:** Extract the replay branch into a small testable function (e.g. `replay_durable_tail(websocket, user_id, run_id, after_seq, has_live_task, session)`) and call it from both the handler and the tests.

---

_Reviewed: 2026-06-11T11:39:36Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard (re-review of gap-closure plans 12-05/12-06/12-07)_
