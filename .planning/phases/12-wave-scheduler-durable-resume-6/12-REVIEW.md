---
phase: 12-wave-scheduler-durable-resume-6
reviewed: 2026-06-11T10:18:14Z
depth: standard
files_reviewed: 32
files_reviewed_list:
  - backend/agents/artifacts/graph.py
  - backend/agents/authz.py
  - backend/agents/capabilities/registry.py
  - backend/agents/capabilities/strategies/wave_scheduler.py
  - backend/agents/capabilities/task_parsers/json_tasks.py
  - backend/agents/execution_engine/context.py
  - backend/agents/execution_engine/engine.py
  - backend/agents/execution_engine/kernel_services.py
  - backend/agents/workflows/plan.py
  - backend/agents/workflows/sample_wave/workflow.yaml
  - backend/alembic/versions/0020_wave_runs.py
  - backend/app/api/websocket.py
  - backend/app/models/__init__.py
  - backend/app/models/wave_run.py
  - backend/tests/agents/fixtures/sample_wave/sample-wave-plan/AGENT.md
  - backend/tests/agents/fixtures/sample_wave/sample-wave-worker/AGENT.md
  - backend/tests/agents/test_json_tasks.py
  - backend/tests/agents/test_migration_ledger.py
  - backend/tests/agents/test_registry_capabilities.py
  - backend/tests/agents/test_restart_resume.py
  - backend/tests/agents/test_sample_wave_workflow.py
  - backend/tests/agents/test_step_retry.py
  - backend/tests/agents/test_subagent_runs.py
  - backend/tests/agents/test_wave_runs.py
  - backend/tests/agents/test_wave_scheduler.py
  - backend/tests/agents/test_ws_reconnect_replay.py
  - frontend/src/app/dashboard/page.tsx
  - frontend/src/components/layout/DashboardLayout.tsx
  - frontend/src/components/workflow/WaveTreePanel.tsx
  - frontend/src/components/workflow/WorkflowComposer.tsx
  - frontend/src/types/index.ts
  - specs/003-workflow-engine-decoupling/migration-ledger.md
findings:
  critical: 6
  warning: 8
  info: 6
  total: 20
status: issues_found
---

# Phase 12: Code Review Report

**Reviewed:** 2026-06-11T10:18:14Z
**Depth:** standard
**Files Reviewed:** 32
**Status:** issues_found

## Summary

Phase 12 lands four tiers: the `wave_scheduler` strategy + `json_tasks` parser (12-01), the per-step retry/reuse wrapper (12-02), the durable in-process resume + WS `after_seq` replay (12-03), and the wave/subagent FE tree (12-04). The pure `build_waves` topo-sort, the additive `0020 wave_runs` migration, the `ScopedStore` wave helpers, and the retry wrapper are well built and well tested. The durable-resume and replay tiers, however, carry several correctness defects that the test suites do not reach because the tests construct their `ScopedStore` with an explicit `workspace_id` and crash the wave **on entry** (never genuinely mid-wave): the resume seq counter restarts at 1 (duplicate seqs, broken replay), the production WS replay read is scoped to `workspace_id IS NULL` and always returns nothing, the mid-wave worker skip uses a "leading-N prefix" assumption that is wrong for parallel waves, and the FE wave tree can never render worker leaves because the subagent events carry no `wave_index`.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: `resume_run` restarts the seq counter at 1 — duplicate seqs corrupt the durable log and break `after_seq` replay of resumed events

**File:** `backend/agents/execution_engine/engine.py:4029-4046` (vs the correct pattern at `engine.py:3060-3090`)
**Issue:** The pre-restart run already persisted `run_events` rows with seq 1..N (plus the `run_resuming` marker at N+1, which `_stamp_resume_marker` carefully computes as `max(seq)+1`). `resume_run` then clones the public `execute()` wrapper with `counter = itertools.count(1)`, so every resumed event is persisted with seq 1, 2, 3… — colliding with the existing rows (`run_events` has no unique constraint on `(run_id, seq)`, so the duplicates insert silently). Consequences: (a) a reconnecting client that sends `after_seq=N` (its last pre-crash seq — exactly what the FE `lastSeqRef` sends) never receives ANY resumed event, because they all have `seq <= N`; (b) `read_events` ordering by seq interleaves pre-crash and post-resume events arbitrarily within duplicate seqs, garbling full-tail replay; (c) the FE seq cursor (`evSeq > lastSeqRef.current`) never advances on resumed events. The whole RESUME-03 "replay the resumed tail" contract is broken for the runs it exists for. The docstring at `engine.py:518` ("monotonic per-run seq — contiguous") is violated.
**Fix:** Seed the resume counter past the durable tail, reusing the `_stamp_resume_marker` read:
```python
existing = await store.read_events(run_id, after_seq=0)
start = max((r.seq for r in existing), default=0) + 1
counter = itertools.count(start)
```
(thread the scoped store / max-seq into `resume_run` before the drive loop).

### CR-02: WS durable replay reads with `workspace_id IS NULL` scope — returns zero rows in production (RESUME-03 dead on arrival)

**File:** `backend/app/api/websocket.py:607-610`; root cause interaction with `backend/agents/authz.py:119-127`
**Issue:** The replay branch constructs `ScopedStore(owner_id=user.id)` with no `workspace_id`. `read_events` applies `_scope_owner_ws`, which filters `RunEvent.workspace_id == self._workspace_id` — i.e. `workspace_id IS NULL` when the store carries none. Every production `run_events` row is stamped with the run's real (non-null) workspace id by the engine sink (`scoped_store._workspace_id = ectx.workspace_id`). The replay query therefore matches **zero rows** for every real run: a reconnect after a restart replays nothing and the client only gets the `pipeline_reconnected` status frame. `test_ws_reconnect_replay.py` masks this because it constructs the store with `workspace_id="ws-1"` directly instead of exercising the handler's construction.
**Fix:** Recover the run's workspace before reading (the engine already has this exact recovery — `_recover_workspace_id`), e.g.:
```python
_run_row = db.query(RunEvent).filter(RunEvent.run_id == rid, RunEvent.owner_id == user.id).first()
_replay_store = ScopedStore(owner_id=user.id, workspace_id=getattr(_run_row, "workspace_id", None))
```
or add an owner-scoped `read_events_for_owner` that drops the workspace predicate (owner + run_id already pins the rows). Add a handler-level test that uses `ScopedStore(owner_id=...)` exactly as websocket.py does.

### CR-03: Mid-wave resume skips the "leading N" workers — wrong for parallel waves; skips never-completed tasks and re-runs completed ones

**File:** `backend/agents/capabilities/strategies/wave_scheduler.py:188-231`
**Issue:** The resume filter counts terminal `subagent_runs` rows (`_completed_worker_count`) and skips that many workers **from the front** of the first incomplete wave (`wave[_remaining_completed:]`), on the stated assumption that "run_fanout dispatches the requests in task order, so the first N completed workers are the first N tasks". Dispatch order is not completion order: waves run **parallel** (`mode: parallel`, `max_parallel: 4`), so when a crash interrupts a wave of 4 after workers for t2 and t4 completed, the resume skips t1 and t2 — silently **dropping t1 and t3 forever** (data loss: their files are never produced, yet the wave is then marked completed) while re-running t4 (duplicate work/cost). The `subagent_runs` rows carry no task identity (`parent_step`, `worker_agent`, `depth`, `isolation`, `status` only — `kernel_services.py:410-449`), so a correct per-task skip is not derivable from the current schema. Additionally, terminal rows from a previously **failed** wave attempt inflate `_completed_worker_count` without being offset by `_workers_seen_in_completed_waves` (which only tallies completed waves), over-skipping further. The headline test (`test_restart_resume.py`) crashes `run_fanout` **on entry** to wave 1, so zero workers in the interrupted wave ever completed — the prefix assumption is never exercised against a true mid-wave partial completion.
**Fix:** Persist task identity on the child row (e.g. add `task_id`/`worker_index` to `subagent_runs` — additive migration — and stamp it in `run_fanout`), then filter the in-flight wave by `task.id not in completed_task_ids`. Until then, the only safe behavior is to re-run the entire in-flight wave (workers are file-writers into isolated workspaces; re-running a completed worker is wasteful but correct, whereas skipping an incomplete one is not).

### CR-04: Resume reads the whole run's `wave_runs` without filtering by step — cross-step wave-index contamination

**File:** `backend/agents/capabilities/strategies/wave_scheduler.py:181-187`
**Issue:** `_completed_wave_indices` is built from `runner.read_wave_runs()` (all rows for the run) with **no `step == step_id` filter**, while the sibling `subagent_runs` count IS filtered by `parent_step`. A workflow with two `wave_scheduler` steps (nothing forbids this — the strategy is `user_allowed=True`) resuming at the second step would treat the FIRST step's completed wave indices (0, 1, …) as its own and skip its waves wholesale — those tasks are never executed and the step completes with missing output.
**Fix:**
```python
_completed_wave_indices = {
    int(getattr(r, "wave_index", -1))
    for r in _wave_rows
    if getattr(r, "step", None) == step_id
    and getattr(r, "status", None) == "completed"
}
```

### CR-05: Reconnect now replays the durable tail AND re-attaches the live queue, but the FE dedupes only wave events — duplicated `agent_chunk` content on every mid-run reconnect

**File:** `backend/app/api/websocket.py:592-643`; `frontend/src/components/layout/DashboardLayout.tsx:522-533`; `frontend/src/app/dashboard/page.tsx:193-218`
**Issue:** The FE now sends `after_seq` on **every** `reconnect_pipeline` (DashboardLayout always includes it), so the backend replay branch is always entered, even with a live task. Events that are persisted but not yet drained from the live queue satisfy `seq > after_seq`, so they are delivered **twice** — once by the replay loop, once by the re-attached drainer. The backend comment relies on "the FE dedupes by event_id (12-04)", but the FE's `seenEventIdsRef` dedup applies **only** inside the `WAVE_EVENT_TYPES` branch (`page.tsx:215-218`); every other replayed event (`agent_chunk`, `tool_call`, `task_progress`, …) flows undeduped into the legacy handlers — visibly duplicating streamed text and progress on reconnect. This also voids the "pure legacy reconnect skips replay" parity claim in `test_ws_reconnect_replay.py::test_legacy_reconnect_skips_replay_branch`, since no production client sends a reconnect without `after_seq` anymore.
**Fix:** Apply the `event_id` dedup at the TOP of `handleWebSocketMessage` (before routing to any handler), not only for wave events; alternatively, skip the replay branch server-side when a live task exists and the queue is intact (replay only when `not _has_live_task`).

### CR-06: Wave tree worker leaves can never render — `subagent_spawned`/`subagent_result` carry no `wave_index`, and same-agent workers collapse to one row

**File:** `frontend/src/app/dashboard/page.tsx:221-223` (the `waveIndex === undefined → return` guard); event source `backend/agents/execution_engine/fanout.py:507-526`
**Issue:** The FE folds `subagent_spawned`/`subagent_result` into a wave group only when `data.wave_index` is a number — but the kernel `run_fanout` emits these events with `{"worker", "agent", "isolation", "depth"}` / the result dict, **no `wave_index`**. Every subagent event is therefore dropped and `wave.workers` stays empty forever: the §22 "wave groups with their worker leaves" feature renders waves only, never workers (the entire `workers` rendering in `WaveTreePanel.tsx:114-128` is dead in practice). Compounding it, workers are keyed by agent name (`group.workers.find((wk) => wk.agent === agent)`, `page.tsx:~250`): a self×N wave (the only shape `sample_wave` produces — every worker is `sample-wave-worker`) would collapse all N parallel workers into ONE leaf whose status flaps.
**Fix:** Either stamp `wave_index` onto the fan-out lifecycle events (the wave strategy could wrap/augment `run_fanout` events it re-yields with the current `wave_index`), or correlate FE-side by "the currently running wave". Key worker leaves by `worker` index, not agent name:
```ts
const key = typeof data.worker === "number" ? data.worker : agent;
```

## Warnings

### WR-01: Partially-resumed wave leaves the original `running` row stuck and writes a duplicate row for the same `wave_index`

**File:** `backend/agents/capabilities/strategies/wave_scheduler.py:221-237`; consumer `backend/agents/execution_engine/engine.py:3858-3956`
**Issue:** On resume, the strategy records a NEW `wave_runs` row (status=running) for the re-entered wave index; the pre-crash row for that same `(run, step, wave_index)` stays `running` forever (nothing flips it). `_first_incomplete_step` classifies the wave step via "any non-completed row ⇒ running" (`running_wave_steps`), so after a successful resume the step is **permanently classified incomplete**: every subsequent restart re-enters the wave step and re-runs all downstream steps (re-spending models — downstream steps get no content-hash reuse unless they declare `retry`). The table also accumulates duplicate rows per wave index, making `wave_index` non-unique per step.
**Fix:** On resume, flip the stale non-terminal rows for this step terminal (e.g. `superseded`/`failed`) before re-dispatching, or update the existing row in place instead of inserting a second one.

### WR-02: `_first_incomplete_step` misclassifies a wave step as complete when the crash lands between waves

**File:** `backend/agents/execution_engine/engine.py:3920-3935`
**Issue:** A wave step is "complete" when it has ≥1 terminal wave row and none running. But the next wave's `running` row is only written when its dispatch starts (`record_wave_run` in the strategy loop); a crash in the window after `update_wave_run(completed)` for wave k and before `record_wave_run` for wave k+1 leaves only terminal rows. The resume offset then skips the wave step entirely — waves k+1..n are **never executed** and the run finalizes with a partial deliverable that looks complete. The window includes event-yield/persist time, so it is realistic.
**Fix:** Derive expected wave count from the durable plan (re-run `build_waves` over the persisted plan artifact in `_first_incomplete_step`, or persist `total_waves` on the first `wave_runs` row / the `wave_started` payload) and treat the step incomplete unless `len(terminal indices) == expected`. The strategy's own skip logic already makes re-entering a fully-completed wave step cheap, so erring toward "incomplete" is safe.

### WR-03: FE replay/dedup/wave state is never reset per run — stale `after_seq` breaks replay for every run after the first

**File:** `frontend/src/app/dashboard/page.tsx:69-77, 197-200`
**Issue:** `lastSeqRef`, `seenEventIdsRef`, and `waveGroups` are module-lifetime refs/state with no reset on `pipeline_start`/new run. After run 1 reaches seq 500, run 2's events (seq 1..) never advance `lastSeqRef` (`evSeq > lastSeqRef.current` is false), so a reconnect during run 2 sends `after_seq=500` → the backend replays nothing → the user sees a silent hang after a refresh. `waveGroups` from a previous wave run also persist into the next run's panel, and `seenEventIdsRef` grows unboundedly.
**Fix:** Reset all three on `pipeline_start` (or when `activePipelineRunId` changes); ideally key `lastSeqRef`/`seenEventIdsRef` by run id.

### WR-04: `_is_resumable_in_flight`'s `run_events` and `wave_runs` evidence reads are dead in production — classification hinges on the artifact visibility OR-branch only

**File:** `backend/agents/execution_engine/engine.py:3026-3058`
**Issue:** The classifier builds `ScopedStore(owner_id=..., workspace_id=wr.workspace_id)`. For a normal pipeline run `workflow_runs.workspace_id` is never written (only the revision path calls `set_run_scope` — `websocket.py:1249-1265` creates the row without it), so the store carries `workspace_id=None`. `read_events` and `read_wave_runs` use the strict `_scope_owner_ws` filter → `workspace_id IS NULL` → ∅ against the real rows. Only `store.tree()` survives (artifact `visibility="workspace"` OR-branch). Net effect: a run that crashed after emitting events / waves but **before its first typed artifact** is classified branch (c) and force-failed instead of resumed, and the first two evidence checks are unfalsifiable dead code. No test exercises a TRUE return from this classifier (the mid-wave test calls `resume_run` directly; the branch tests assert the false paths).
**Fix:** Recover the workspace id first (reuse `_recover_workspace_id(owner_id, wr.id)`) and construct the store with it; add a test that drives `restore_non_terminal_runs` end-to-end into branch (b).

### WR-05: Duplicate task ids are silently collapsed by `build_waves` and accepted by `json_tasks`

**File:** `backend/agents/capabilities/strategies/wave_scheduler.py:77-89`; `backend/agents/capabilities/task_parsers/json_tasks.py:99-118`
**Issue:** `by_id = {t.id: t for t in tasks}` last-wins on duplicate ids: the earlier task is silently dropped from `remaining`/the waves (its work never dispatched), and the in-degree decrement loop (`for u in tasks: ...`) iterates the original list, so a duplicated dependent decrements `indeg[u.id]` twice — in-degrees can go negative and waves can schedule a task before its (intended) dependency. The parser validates `depends_on` refs but not id uniqueness, so untrusted agent-emitted JSON (the T-12-01-INPUT surface) with `[{"id":"a",...},{"id":"a",...}]` passes straight through.
**Fix:** In `JsonTasksParser.parse`, raise a named `ValueError` on a duplicate id; defense-in-depth in `build_waves`: `if len(by_id) != len(tasks): raise WaveBuildError("duplicate task id")`.

### WR-06: Cancellation mid-wave leaves the `wave_runs` row stuck `running`; the documented `cancelled` status is never written

**File:** `backend/agents/capabilities/strategies/wave_scheduler.py:243-252`
**Issue:** The wave loop's `except Exception` does not catch `asyncio.CancelledError` (a `BaseException` since 3.8). A user Stop / cooperative cancel propagating out of `run_fanout` skips both `update_wave_run(..., "failed")` and any terminal flip — the row stays `running` permanently even though the model/migration document a `cancelled` status (`wave_run.py:40`, `0020_wave_runs.py:43`). A stuck-`running` row then also feeds the WR-01/`_first_incomplete_step` confusion if the run is somehow re-driven.
**Fix:**
```python
except asyncio.CancelledError:
    await runner.update_wave_run(row_id, status="cancelled")
    raise
except Exception:
    ...
```

### WR-07: A resumed run cannot be cancelled

**File:** `backend/agents/execution_engine/engine.py:3958-4055`
**Issue:** `resume_run` calls `_execute_impl` with no `cancel_event` and registers nothing in the WS-layer `_PIPELINE_TASKS`/`_PIPELINE_QUEUES`, so every cooperative-cancel check in the resumed drive (`cancel_event and cancel_event.is_set()`) is permanently false and the WS `stop`/cancel path has no handle on the task. A runaway resumed run (e.g. a large wave fan-out) can only be stopped by killing the process — which would then auto-resume it again at the next startup.
**Fix:** Create and register an `asyncio.Event` + the driver task under the run id (the same registries the WS path uses) so `stop_pipeline` reaches resumed runs.

### WR-08: Runs that crashed during planning/clarify are resumed straight into the build with the planner force-skipped

**File:** `backend/agents/execution_engine/engine.py:1100-1135, 3026-3058`
**Issue:** `_is_resumable_in_flight` accepts any compiled-manifest run with durable evidence; it never checks the run got PAST planning/clarify. A run that died in `planning`/`clarifying` (planner events / clarification artifacts persisted — the clarifications artifact is `visibility`-scoped and satisfies the `tree()` evidence check) is auto-resumed with `skip_planner` forced True: the clarify answers are never collected and any planner agent-overlay that would have shaped the run is not re-applied, so the resumed run executes a different plan than the original would have.
**Fix:** Gate branch (b) on durable evidence of build progress specifically (a produced step artifact or a `wave_runs` row), or persist/restore the planning outcome before forcing the planner skip.

## Info

### IN-01: `_did_replay` is assigned but never read

**File:** `backend/app/api/websocket.py:593, 626`
**Issue:** Dead variable left over from an earlier control-flow shape.
**Fix:** Remove it (or use it to suppress the duplicate-delivery overlap from CR-05).

### IN-02: `replayed_through_seq` reports the REQUESTED `after_seq`, not the last replayed seq

**File:** `backend/app/api/websocket.py:637`
**Issue:** After replaying rows up to seq M, the status frame echoes the client's `after_seq` — a client persisting this as its new cursor would re-request the same tail forever.
**Fix:** Report `_missed[-1].seq if _missed else _after_seq`.

### IN-03: The fence regex extracts the FIRST fenced block, not the JSON one

**File:** `backend/agents/capabilities/task_parsers/json_tasks.py:37-50`
**Issue:** `_FENCE_RE.search` picks the first ``` block anywhere in the prose. A planner reply containing an unrelated fenced example before the ```json plan parses the wrong block and raises (or worse, parses a different array). The `(?:json)?` tag also matches a ```javascript fence's prefix position.
**Fix:** Prefer an explicitly `json`-tagged fence first (`re.compile(r"```json\s*\n(.*?)```", re.DOTALL)`), falling back to the bare-fence / raw-payload paths.

### IN-04: `_compute_resume_offset` fallback claims content-hash reuse makes offset-0 "still correct", and mints orphan workspace rows

**File:** `backend/agents/execution_engine/engine.py:4058-4100`
**Issue:** The docstring says re-driving from 0 reuses completed steps via the content-hash key — but `_dispatch_step_with_retry`'s reuse path only activates for steps declaring `retry.max_attempts > 0` (none of the existing manifests, including `sample_wave`, declare retry), so an offset-0 resume re-invokes every model. Separately, when `_recover_workspace_id` fails the fallback calls `create_workspace(run_id)` just to compute an offset, inserting a workspace row that the subsequent `_execute_impl` recovery may then orphan.
**Fix:** Correct the comment; skip the `create_workspace` fallback in the offset computation (a `None` workspace simply yields no durable evidence → offset 0).

### IN-05: `statusKind` buckets `cancelled` as `pending`

**File:** `frontend/src/components/workflow/WaveTreePanel.tsx:34-42`
**Issue:** `"cancelled"` matches none of the substrings, so a cancelled wave/worker renders as a grey "pending" chip instead of a terminal state.
**Fix:** Add `if (s.includes("cancel")) return "failed";` (or a dedicated bucket).

### IN-06: Wave groups keyed by `waveIndex` alone collide across multiple wave steps

**File:** `frontend/src/components/workflow/WaveTreePanel.tsx:96`; `frontend/src/app/dashboard/page.tsx:226-231`
**Issue:** Both the React `key` and the group-merge lookup use `waveIndex` only. Two `wave_scheduler` steps in one run both emit wave_index 0 — their groups merge/overwrite. The `wave_*` payloads already carry `step`.
**Fix:** Key groups by `` `${data.step}:${waveIndex}` ``.

---

_Reviewed: 2026-06-11T10:18:14Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
