---
phase: 12-wave-scheduler-durable-resume-6
verified: 2026-06-11T12:00:00Z
status: gaps_found
score: 4/6 must-haves verified
overrides_applied: 0
gaps:
  - truth: "A server restart resumes mid-wave via subagent_runs/wave_runs; idempotent step retry reuses artifacts on content-hash match (WAVE-03 / RESUME-02 / RESUME-03)"
    status: failed
    reason: "CR-01: resume_run at engine.py:4030 starts counter = itertools.count(1) — the same seq origin as every fresh run. Pre-restart run_events rows already hold seq 1..N. Resumed events persist with seq 1, 2, 3... colliding silently (no unique constraint). A client sending after_seq=N never receives any resumed event because they all carry seq <= N. The _stamp_resume_marker reads max(seq)+1 for its own marker only; the subsequent driver counter is completely independent and uncorrected. RESUME-03 'replay resumed tail via after_seq' is broken for every resumed run."
    artifacts:
      - path: "backend/agents/execution_engine/engine.py"
        issue: "resume_run line 4030: counter = itertools.count(1) must seed past the durable tail max(seq)+1"
    missing:
      - "Seed counter: existing = await store.read_events(run_id, after_seq=0); start = max((r.seq for r in existing), default=0) + 1; counter = itertools.count(start)"

  - truth: "Reconnect replays from the durable run_events log (after=<seq>, idempotent by event_id) (RESUME-03)"
    status: failed
    reason: "CR-02: websocket.py:607 constructs ScopedStore(owner_id=user.id) with no workspace_id. ScopedStore._scope_owner_ws filters workspace_id == self._workspace_id, which is None, i.e. workspace_id IS NULL. Every production run_events row is stamped with a real non-null workspace_id by the engine sink. The replay query returns zero rows for every real run. The test (test_ws_reconnect_replay.py) masks this by constructing ScopedStore(owner_id=..., workspace_id='ws-1') directly, never exercising the handler's no-workspace construction. RESUME-03 durable replay is dead on arrival in production."
    artifacts:
      - path: "backend/app/api/websocket.py"
        issue: "Line 607: _replay_store = ScopedStore(owner_id=user.id) — missing workspace_id recovery. Matches zero production run_events rows."
    missing:
      - "Recover the run's workspace_id before constructing the replay store, e.g. via _recover_workspace_id or a bare owner-scoped lookup: _run_row = db.query(RunEvent).filter(RunEvent.run_id == rid, RunEvent.owner_id == user.id).first(); _replay_store = ScopedStore(owner_id=user.id, workspace_id=getattr(_run_row, 'workspace_id', None))"
      - "Add a handler-level test that constructs ScopedStore exactly as websocket.py does (no explicit workspace_id) and asserts events are returned"

  - truth: "A server restart resumes mid-wave — completed waves not re-invoked (WAVE-03 / CR-03 + CR-04)"
    status: failed
    reason: "Two independent defects in the mid-wave resume path: (CR-03) The completed-worker skip uses a 'leading-N prefix' assumption (wave[_remaining_completed:]) but parallel waves have no completion order guarantee. Workers for t2 and t4 completing before t1 and t3 causes t1 and t3 to be dropped permanently (data loss) while t4 is re-run (duplicate cost). The test crashes run_fanout on wave entry so zero workers ever complete — the prefix assumption is never exercised. (CR-04) _completed_wave_indices is built from ALL wave_runs rows for the run without filtering by step id. A workflow with two wave_scheduler steps would treat the first step's completed wave indices as its own and skip those waves in the second step wholesale — never executing them and producing missing output. Both defects are in wave_scheduler.py lines 182-197."
    artifacts:
      - path: "backend/agents/capabilities/strategies/wave_scheduler.py"
        issue: "Lines 183-186: _completed_wave_indices has no 'step == step_id' filter — cross-step wave-index contamination (CR-04). Lines 221-228: prefix skip is wrong for parallel waves — completed workers are identified by order not identity (CR-03)."
    missing:
      - "CR-04 fix: add step filter: _completed_wave_indices = {int(getattr(r,'wave_index',-1)) for r in _wave_rows if getattr(r,'step',None) == step_id and getattr(r,'status',None) == 'completed'}"
      - "CR-03 safe path: until task_id is stamped on subagent_runs, the only correct behavior is to re-run the entire in-flight wave (idempotent for file-writer workers) rather than risk silently dropping tasks"
deferred: []
human_verification:
  - test: "Live wave-tree panel render"
    expected: "WaveTreePanel renders wave groups with status badges and worker leaves from live wave_*/subagent_* events during a wave run"
    why_human: "No headless DOM harness in repo; visual render requires live dev servers (08-08 Task-3 precedent). Deferred to end-of-milestone live pass per project convention."
  - test: "Live after_seq reconnect replay"
    expected: "After reloading mid-run, reconnect sends after_seq; tree resumes without duplicated entries and without losing missed tail"
    why_human: "Requires live network toggle / page reload against running servers. Deferred to end-of-milestone live pass."
---

# Phase 12: Wave Scheduler + Durable Resume [6] Verification Report

**Phase Goal:** Add a deterministic topological wave scheduler that runs disjoint tasks in parallel waves via fan-out, with durable mid-wave resume; prototype stays sequential and a CP-SAT seam is left.
**Verified:** 2026-06-11T12:00:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (from ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `wave_scheduler` strategy topo-sorts by `depends_on` + `conflict_keys` into waves and runs each wave via fan-out; a multi-file workflow runs disjoint tasks in parallel waves; prototype stays sequential; CP-SAT seam left | VERIFIED | `wave_scheduler.py` exists with `@register("strategy","wave_scheduler",user_allowed=True)` and pure `build_waves` (Kahn-levels, conflict-key split). `sample_wave` manifest + test prove >=2 waves, >=2 parallel workers. No engine name-branch. `_KNOWN` lockstep 61. Characterization snapshots byte-identical. |
| 2 | `wave_runs` persisted; a server restart resumes mid-wave via `subagent_runs`/`wave_runs`; idempotent step retry reuses artifacts on content-hash match | FAILED | `wave_runs` table + ORM + ScopedStore methods confirmed (WAVE-02). Retry wrapper `_dispatch_step_with_retry` confirmed (RESUME-02). BUT: `resume_run` restarts the seq counter at 1 (CR-01) breaking RESUME-03; mid-wave skip has cross-step contamination (CR-04) and parallel-order assumption (CR-03) breaking WAVE-03. |
| 3 | Reconnect replays from the durable `run_events` log (`after=<seq>`, idempotent by `event_id`); `restore_non_terminal_runs` resumes at step granularity (waiting_for_user gates resume on user action) | FAILED | `reconnect_pipeline` `after_seq` branch exists but `ScopedStore(owner_id=user.id)` has no `workspace_id`, so `read_events` matches zero production rows (CR-02). `restore_non_terminal_runs` three-way classification confirmed (branch a/b/c); tests pass but the test ScopedStore masks CR-02. |

**Score:** 1/3 ROADMAP success criteria fully verified (SC1); SC2 partial (WAVE-02/RESUME-02 OK, WAVE-03/RESUME-03 broken); SC3 broken (CR-02).

### Must-Have Truths (from PLAN frontmatter — all plans)

| # | Plan | Truth | Status | Evidence |
|---|------|-------|--------|----------|
| 1 | 12-01 | wave_scheduler topo-sorts json_tasks into deterministic waves and runs each wave through ctx.runner.run_fanout | VERIFIED | Code confirmed at wave_scheduler.py:57-258; `runner.run_fanout(requests, ctx, step=step)` at line 244 |
| 2 | 12-01 | build_waves raises pre-spawn on cycle/unknown ref (zero wave_runs/subagent_runs rows) | VERIFIED | `WaveBuildError` raised before returning any wave (lines 82-84, 96); tests green |
| 3 | 12-01 | Tasks with overlapping conflict_keys never co-schedule | VERIFIED | within-level conflict-key split at lines 99-110; test_wave_scheduler.py green |
| 4 | 12-01 | Sample multi-file workflow (manifest + AGENT.md only) runs in >=2 waves, zero engine edits | VERIFIED | `sample_wave` workflow confirmed; `grep sample_wave backend/agents/execution_engine/` = 0; test_sample_wave_workflow.py 3 passed |
| 5 | 12-01 | Each executed wave persists one owner-scoped wave_runs row reaching terminal; cross-owner read returns nothing | VERIFIED | authz.py record_wave_run/read_wave_runs confirmed; cross-owner test passes |
| 6 | 12-01 | 5 characterization snapshots byte/event-identical | VERIFIED | All characterization tests pass (10 passed); lint-imports 4/0 |
| 7 | 12-02 | Step with retry.max_attempts > 0 retries on transient errors up to max_attempts | VERIFIED | `_dispatch_step_with_retry` wrapper confirmed; test_step_retry.py 7 passed |
| 8 | 12-02 | Non-transient error does NOT retry | VERIFIED | test_step_retry.py confirms non-transient no-retry |
| 9 | 12-02 | Existing artifact keyed (run_id, step_id, input_hash) is reused without re-invoking | VERIFIED | `_compute_step_input_hash` + `_find_reused_completion` confirmed; reuse test passes |
| 10 | 12-02 | Step with no declared retry byte-identical to today | VERIFIED | Strict gate `step.retry and step.retry.max_attempts > 0`; characterization snapshots unchanged |
| 11 | 12-03 | reconnect_pipeline accepts after_seq and replays missed run_events idempotently | FAILED | Code exists but `ScopedStore` constructed without `workspace_id` (CR-02) — returns 0 rows in production |
| 12 | 12-03 | Reconnect after simulated process restart replays from durable log | UNCERTAIN | Test passes with explicit `workspace_id='ws-1'` in `ScopedStore` construction, masking production path |
| 13 | 12-03 | Legacy reconnect without after_seq behaves exactly as today | VERIFIED | Legacy path preserved at websocket.py:589-591; test asserts no replay frames |
| 14 | 12-03 | restore_non_terminal_runs auto-resumes from first incomplete step; previously-completed wave/worker not re-invoked | FAILED | Three-way classifier confirmed but: mid-wave skip uses prefix assumption (wrong for parallel, CR-03) and has cross-step contamination (CR-04); seq counter restarts at 1 (CR-01) meaning resumed events are never seen by reconnecting client |
| 15 | 12-03 | waiting_for_user gates on user action; stateless runs keep WR-05 path | VERIFIED | Branch a/c confirmed in code and tests |
| 16 | 12-04 | Wave/subagent tree panel renders waves and workers from wave_*/subagent_* events | FAILED (code correctness) | `subagent_spawned`/`subagent_result` carry no `wave_index` (fanout.py:508-525). FE guard `if (waveIndex === undefined) return;` at page.tsx:222 drops ALL subagent events — `wave.workers` stays empty forever. Worker leaves NEVER render. (CR-06) |
| 17 | 12-04 | FE reconnect sends last-received seq as after_seq and dedupes by event_id | VERIFIED (code correctness; live render deferred) | DashboardLayout.tsx:533 `after_seq: afterSeq` confirmed; dedup at page.tsx:213-217. Note: dedup applies ONLY inside WAVE_EVENT_TYPES branch — non-wave events (agent_chunk etc.) are NOT deduped on replay (CR-05 duplicate-delivery on reconnect). |
| 18 | 12-04 | No existing panel modified; existing-workflow UI unchanged | VERIFIED | WorkflowComposer additive mount confirmed; ValidatorIssuePanel mount unchanged |

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/agents/capabilities/strategies/wave_scheduler.py` | wave_scheduler strategy + pure build_waves seam | VERIFIED | `@register("strategy","wave_scheduler",user_allowed=True)`, `build_waves`, `WaveBuildError` all present |
| `backend/agents/capabilities/task_parsers/json_tasks.py` | json_tasks structured-task parser | VERIFIED | `@register("task_parser","json_tasks")`, full parse() with depends_on validation |
| `backend/alembic/versions/0020_wave_runs.py` | additive wave_runs migration (down_revision 0019) | VERIFIED | `revision="0020"`, `down_revision="0019"`, no `sa.Enum`, reversible |
| `backend/app/models/wave_run.py` | WaveRun ORM on Base.metadata | VERIFIED | `class WaveRun(Base)`, `__tablename__ = "wave_runs"` |
| `backend/agents/workflows/sample_wave/workflow.yaml` | SC-001 sample wave workflow | VERIFIED | Located at `backend/agents/workflows/sample_wave/` (not `agents/workflows/` as in PLAN — actual location confirmed); `strategy: wave_scheduler`, `parser: json_tasks` |
| `backend/agents/execution_engine/engine.py` | resume_run entry + three-way restore + retry wrapper | PARTIAL | `resume_run`, `_dispatch_step_with_retry`, `restore_non_terminal_runs` three-way all present. CR-01 (seq restart) and CR-03/CR-04 (mid-wave skip defects) are correctness failures in the implementation. |
| `backend/app/api/websocket.py` | reconnect_pipeline after_seq durable replay branch | PARTIAL | Branch exists and is wired. CR-02 (workspace_id missing from ScopedStore) means it returns 0 rows in production. |
| `frontend/src/components/workflow/WaveTreePanel.tsx` | props-driven wave/subagent tree panel | PARTIAL | Component exists, exports `WaveTreePanelProps`, mounted in WorkflowComposer. Wave group rendering correct. Worker leaves NEVER render (CR-06): subagent events carry no wave_index; FE guard drops them all. |
| `frontend/src/app/dashboard/page.tsx` | wave/subagent event routing + event_id dedup | PARTIAL | Wave event routing confirmed. event_id dedup confirmed but scope-limited to WAVE_EVENT_TYPES only — non-wave events duplicated on reconnect (CR-05). |
| `frontend/src/components/layout/DashboardLayout.tsx` | after_seq on reconnect_pipeline | VERIFIED | `after_seq: afterSeq` at line 533 confirmed |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `wave_scheduler.py` | `ctx.runner.run_fanout` | one run_fanout call per wave | VERIFIED | `runner.run_fanout(requests, ctx, step=step)` at line 244 |
| `kernel_services.py` | `ScopedStore.record_wave_run` | best-effort None-degrading recorder | VERIFIED | `record_wave_run` at lines 473-503; None-guard on store |
| `authz.py` | `wave_runs` table | default-deny owner+workspace scoped writer/reader | VERIFIED | `_scope_owner_ws` filter applied in `read_wave_runs`; cross-owner test passes |
| `websocket.py` | `ScopedStore.read_events` | owner-scoped durable replay seq > after_seq | PARTIAL | Call exists at line 609; ScopedStore constructed without workspace_id (CR-02) — zero rows in production |
| `engine.py` | `compile_for_run` | resume rebuilds ExecutionContext via single construction path | VERIFIED | `compile_for_run` called at line 841 in `_execute_impl`; `_resume_from` offset param threads through |
| `engine.py` | `wave_runs / subagent_runs` | first-incomplete-step + mid-wave resume | PARTIAL | `read_wave_runs`/`read_subagent_runs` called; but cross-step contamination (CR-04) and prefix skip (CR-03) make the logic wrong for parallel waves |
| `DashboardLayout.tsx` | `reconnect_pipeline after_seq` | last-received seq sent on reconnect | VERIFIED | `after_seq: afterSeq` at line 533; lastSeqRef tracker confirmed |
| `dashboard/page.tsx` | `WaveTreePanel` | wave/subagent tree state from deduped lifecycle events | PARTIAL | Wave group state confirmed; worker leaves dead (CR-06 no wave_index on subagent events) |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `wave_scheduler.py` | `waves` (list[list[Task]]) | `build_waves(tasks)` → `runner.run_fanout` | Yes — pure topo-sort + real fan-out | FLOWING |
| `wave_run.py` (ORM) | `wave_runs` rows | `ScopedStore.record_wave_run` → SQLAlchemy session.add | Yes — real DB writes | FLOWING |
| `websocket.py` reconnect branch | `_missed` (run_events) | `ScopedStore(owner_id=user.id).read_events(...)` | No — workspace_id IS NULL → 0 rows in production | STATIC (CR-02) |
| `engine.py resume_run` | resumed event seq | `itertools.count(1)` | No — restarts at 1, collides with pre-restart rows | STATIC (CR-01) |
| `WaveTreePanel.tsx` | `waves[*].workers` | `subagent_spawned`/`subagent_result` events | No — events carry no wave_index, guard drops all subagent events | DISCONNECTED (CR-06) |

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| wave_scheduler topo-sort and fan-out | `pytest tests/agents/test_wave_scheduler.py` | 8 passed | PASS |
| json_tasks parser | `pytest tests/agents/test_json_tasks.py` | 11 passed | PASS |
| wave_runs persistence + authz | `pytest tests/agents/test_wave_runs.py` | 7 passed | PASS |
| sample_wave SC-001 proof | `pytest tests/agents/test_sample_wave_workflow.py` | 3 passed | PASS |
| per-step retry + content-hash reuse | `pytest tests/agents/test_step_retry.py` | 7 passed | PASS |
| WS reconnect replay | `pytest tests/agents/test_ws_reconnect_replay.py` | 5 passed (masks CR-02 via explicit workspace_id) | PASS (test-masked) |
| restart + mid-wave resume | `pytest tests/agents/test_restart_resume.py` | 3 passed (crashes wave on entry so prefix logic never exercised, CR-03 not caught) | PASS (test-masked) |
| characterization snapshots byte-identical | `pytest tests/agents/test_characterization_*.py` | 10 passed | PASS |
| import-linter contracts | `lint-imports` from backend/ | 4 kept / 0 broken | PASS |
| registry lockstep | `pytest tests/agents/test_registry_capabilities.py` | 82 passed | PASS |
| migration ledger | `pytest tests/agents/test_migration_ledger.py` | (within above run) passed | PASS |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| WAVE-01 | 12-01 | wave_scheduler topo-sorts by depends_on + conflict_keys into waves, runs via fan-out; deterministic builder, CP-SAT seam | SATISFIED | wave_scheduler.py confirmed; sample_wave SC-001 proof; build_waves pure seam |
| WAVE-02 | 12-01 | wave_runs persistence; multi-file workflow in parallel waves; prototype stays sequential | SATISFIED | 0020 migration + WaveRun ORM + ScopedStore methods; sample_wave test; charaterization snapshots unchanged |
| WAVE-03 | 12-01/12-03 | Resume mid-wave via subagent_runs/wave_runs after restart | BLOCKED | resume_run seq counter (CR-01) means resumed events never visible to reconnecting client; cross-step wave-index contamination (CR-04) and parallel-prefix assumption (CR-03) corrupt task dispatch |
| RESUME-02 | 12-02 | Idempotent per-step retry keyed by (run_id, step_id, input_hash); reuses artifact on hash match | SATISFIED | _dispatch_step_with_retry wrapper confirmed; _compute_step_input_hash cross-restart-stable; test_step_retry.py 7 passed |
| RESUME-03 | 12-03/12-04 | Reconnect = durable replay from run_events via after=<last_seq>, idempotent by event_id | BLOCKED | WS replay store has no workspace_id → 0 rows (CR-02); resume counter restart (CR-01) means resumed events have seq <= N and are never delivered by the replay branch anyway |
| RESUME-04 | 12-03 | Server restart = restore_non_terminal_runs extended to step granularity; waiting_for_user gates | PARTIAL | Three-way classifier and resume_run exist; waiting_for_user branch unchanged; WR-05 path unchanged. But mid-wave skip defects (CR-03, CR-04) mean "completed workers not re-invoked" is incorrect for parallel waves. |

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `backend/agents/execution_engine/engine.py` | 4030 | `counter = itertools.count(1)` in `resume_run` | BLOCKER | Seq collision with pre-restart rows; RESUME-03 broken — reconnecting client never receives resumed events (CR-01) |
| `backend/app/api/websocket.py` | 607 | `ScopedStore(owner_id=user.id)` with no `workspace_id` | BLOCKER | `read_events` returns 0 rows in production (workspace_id IS NULL predicate). RESUME-03 dead on arrival (CR-02) |
| `backend/agents/capabilities/strategies/wave_scheduler.py` | 183-186 | `_completed_wave_indices` not filtered by `step == step_id` | BLOCKER | Cross-step wave-index contamination — two wave_scheduler steps in a run would skip all waves in the second step (CR-04) |
| `backend/agents/capabilities/strategies/wave_scheduler.py` | 221-228 | Prefix skip `wave[_remaining_completed:]` assumes dispatch order == completion order | BLOCKER | Parallel waves have no order guarantee — drops incomplete tasks (data loss) and re-runs completed ones for any truly-mid-wave crash (CR-03) |
| `frontend/src/app/dashboard/page.tsx` | 222 | `if (waveIndex === undefined) return;` — drops all subagent events | BLOCKER | subagent_spawned/subagent_result carry no wave_index; worker leaves NEVER render (CR-06) |
| `frontend/src/app/dashboard/page.tsx` | 211-266 | event_id dedup scoped to WAVE_EVENT_TYPES only | WARNING | Non-wave events (agent_chunk, tool_call, task_progress) not deduped — duplicated on every mid-run reconnect (CR-05) |
| `backend/app/api/websocket.py` | 637 | `replayed_through_seq: _after_seq` echoes requested seq not last-replayed seq | INFO | A client persisting this as new cursor re-requests same tail (IN-02) |
| `backend/app/api/websocket.py` | 593/626 | `_did_replay` assigned but never read | INFO | Dead variable (IN-01) |

---

## Human Verification Required

### 1. Live Wave-Tree Panel Render

**Test:** Start backend + frontend dev servers; run the `sample_wave` workflow from the composer UI.
**Expected:** WaveTreePanel renders wave groups (index, task ids, status badge flips running→completed); worker leaves appear under each wave with agent + status (statuses only).
**Why human:** No headless DOM harness in repo (08-08 Task-3 precedent). Note: CR-06 means worker leaves WILL NOT render until that code defect is fixed.

### 2. Live After-Seq Reconnect Replay

**Test:** While a wave run is streaming, reload the page or toggle the network; observe WS frames in network tab.
**Expected:** Reconnect sends `after_seq`; tree resumes without duplicated entries and without losing missed tail.
**Why human:** Requires live network toggle against running servers. Note: CR-02 means replay will return 0 events until the workspace_id fix is applied.

---

## Gaps Summary

Three independent correctness defects in the durable resume / replay tier prevent WAVE-03 and RESUME-03 from working in production. All three are confirmed by direct code inspection and corroborated by the code review findings (CR-01, CR-02, CR-03/CR-04):

**Gap 1 — CR-01 (BLOCKER): resume_run seq counter restarts at 1**
`resume_run` (engine.py:4030) calls `itertools.count(1)` identically to a fresh run. Pre-restart events have seq 1..N. Resumed events persist with seq 1, 2, 3... silently colliding (no unique constraint). A reconnecting client sending `after_seq=N` receives zero resumed events. The `_stamp_resume_marker` correctly computes `max(seq)+1` for its own marker but has no effect on the counter that follows it. Fix: seed `counter = itertools.count(max_existing_seq + 1)`.

**Gap 2 — CR-02 (BLOCKER): WS replay ScopedStore has no workspace_id**
`websocket.py:607` constructs `ScopedStore(owner_id=user.id)` with `workspace_id=None`. `read_events` applies `_scope_owner_ws` which predicates `workspace_id IS NULL`. Production `run_events` rows carry real non-null workspace ids. The replay returns zero rows. Fix: recover the run's workspace_id before constructing the replay store.

**Gap 3 — CR-03 + CR-04 (BLOCKER): mid-wave resume skip logic is incorrect**
CR-04: `_completed_wave_indices` at wave_scheduler.py:183-186 has no `step == step_id` filter, contaminating resume state across multiple wave_scheduler steps. CR-03: the completed-worker skip uses `wave[_remaining_completed:]` (prefix by count), which is wrong for parallel waves where completion order is not dispatch order — dropping incomplete tasks (data loss) while re-running completed ones. The test suite does not catch either defect because it crashes run_fanout on wave entry (zero workers complete before the crash), so the prefix logic is never exercised against genuine mid-wave state.

One FE correctness defect prevents worker-leaf rendering permanently:

**Gap 4 — CR-06 (BLOCKER for FE worker-leaf feature):** `subagent_spawned`/`subagent_result` events emitted by `fanout.py` carry no `wave_index` field. The FE guard `if (waveIndex === undefined) return;` at page.tsx:222 silently drops ALL subagent events. `wave.workers` stays empty for every wave. The §22 worker-leaf feature is unreachable until `wave_index` is stamped on these events (either by the wave_scheduler wrapping re-yielded fan-out events with the current `wave_index`, or by stamping it in `run_fanout`).

The test suite passes (259 passed, 7 skipped as of the targeted run) because the tests construct their DB contexts with explicit `workspace_id` and crash fan-out on entry — exactly the conditions the review predicted. Test coverage does not reach the production path for CR-02 or the genuine mid-wave partial-completion path for CR-03.

WAVE-01 (topological scheduling), WAVE-02 (wave_runs persistence), and RESUME-02 (per-step retry/reuse) are cleanly implemented and verified. The four gaps above are all in the durable resume and FE rendering tier (WAVE-03, RESUME-03, the FE worker panel).

---

_Verified: 2026-06-11T12:00:00Z_
_Verifier: Claude (gsd-verifier)_
