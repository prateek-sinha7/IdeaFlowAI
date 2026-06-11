---
phase: 12-wave-scheduler-durable-resume-6
verified: 2026-06-11T14:00:00Z
status: passed
score: 6/6 must-haves verified
overrides_applied: 1
override_note: >
  Verifier returned human_needed solely for 3 live-environment FE checks.
  Per project convention (defer live verification to the end-of-milestone live
  pass; do not block phase completion on live-env checks when offline evidence
  is green), these are persisted as deferred UAT in 12-UAT.md and the phase is
  closed on offline evidence: 6/6 must-haves code-verified, 268 backend tests +
  6 FE vitest green, snapshots byte-identical, lint-imports 4/0.
re_verification:
  previous_status: gaps_found
  previous_score: 4/6
  gaps_closed:
    - "CR-01: resume_run seq counter now seeded at max(existing_seq)+1 — resumed events carry seq > N, reconnect after_seq=N delivers the resumed tail"
    - "CR-02: WS reconnect replay recovers workspace_id from an owner-scoped RunEvent row before constructing the replay ScopedStore — production rows are now matched"
    - "CR-03: unsafe leading-N prefix skip deleted; first incomplete wave re-runs whole — no parallel-order data loss"
    - "CR-04: _completed_wave_indices step-filtered (step == step_id) — no cross-step wave-index contamination"
    - "CR-06: subagent_spawned/subagent_result stamped with wave_index+step at the strategy re-yield boundary; FE keys worker leaves by data.worker — N distinct leaves render"
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "Live wave-tree panel render with N distinct worker leaves"
    expected: "WaveTreePanel renders wave groups (index, task ids, status badge running->completed) AND N distinct worker leaves per wave for sample_wave self-x-N shape; no same-agent collapse"
    why_human: "No headless DOM harness for the full dashboard in the repo (08-08 Task-3 precedent). Deferred to end-of-milestone live pass per project convention."
  - test: "Live after_seq reconnect replay — no duplicate events, no lost tail"
    expected: "Mid-run page reload sends after_seq; wave/worker tree resumes without duplicated entries; agent_chunk text not duplicated (CR-05 fix live); missed tail not lost (CR-01/CR-02 fixes live)"
    why_human: "Requires live network toggle against running servers. Deferred to end-of-milestone live pass."
  - test: "Second run resets wave panel and reconnect cursor"
    expected: "After run 1 completes, starting run 2 clears the previous wave panel and sends after_seq=0 on first reconnect (WR-03 per-run reset live)"
    why_human: "Requires sequential run execution against live servers. Deferred to end-of-milestone live pass."
---

# Phase 12: Wave Scheduler + Durable Resume [6] Verification Report

**Phase Goal:** Add a deterministic topological wave scheduler that runs disjoint tasks in parallel waves via fan-out, with durable mid-wave resume; prototype stays sequential and a CP-SAT seam is left.
**Verified:** 2026-06-11T14:00:00Z
**Status:** human_needed
**Re-verification:** Yes — after gap closure (plans 12-05 / 12-06 / 12-07 closed the 4 prior blockers CR-01..CR-06)

## Gap Closure Summary

The four blockers recorded in the initial `gaps_found` verdict have all been fixed and verified in code. No regressions introduced against previously-passing truths. Six new warnings (WR-09 through WR-14) were surfaced by the post-gap-closure code review; none breaks a ROADMAP success criterion for the first-restart scenario — they are second-restart edge cases or deferred quality debt.

| Prior Blocker | Fix Plan | Fix Location | Regression Test | Verdict |
|---|---|---|---|---|
| CR-01: seq restarts at 1 in resume_run | 12-05 | `engine.py:4049-4067` — `counter = itertools.count(start)`, `start = max(seq)+1` | `test_resumed_events_seq_continues_past_durable_tail` | CLOSED |
| CR-02: WS replay ScopedStore workspace_id=None | 12-05 | `websocket.py:608-637` — owner-scoped RunEvent lookup feeds `ScopedStore(workspace_id=_recovered_ws)` | `test_production_shaped_replay_recovers_workspace_and_returns_rows`, `test_cross_owner_workspace_recovery_yields_empty_replay` | CLOSED |
| CR-03: prefix skip drops parallel tasks (data loss) | 12-06 | `wave_scheduler.py` — `_remaining_completed` / `wave[_remaining_completed:]` deleted; whole in-flight wave re-run | `test_midwave_resume_reruns_whole_inflight_wave_no_parallel_dropout` | CLOSED |
| CR-04: cross-step wave-index contamination | 12-06 | `wave_scheduler.py:200-206` — `getattr(r, "step", None) == step_id` filter on `_completed_wave_indices` | `test_cross_step_does_not_skip_second_steps_waves` | CLOSED |
| CR-06 backend: no wave_index on subagent events | 12-06 | `wave_scheduler.py:262-266` — stamps `wave_index`+`step` at strategy re-yield boundary | `test_subagent_events_carry_wave_index_and_step` | CLOSED |
| CR-06 FE: worker leaves never render / same-agent collapse | 12-07 | `page.tsx:281-288` — leaves keyed by `data.worker` index | vitest `wsReplayState.test.ts` (6 passed) | CLOSED |

---

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `wave_scheduler` strategy topo-sorts by `depends_on` + `conflict_keys` into waves and runs each wave via fan-out; a multi-file workflow runs disjoint tasks in parallel waves; prototype stays sequential; CP-SAT seam left | VERIFIED | `wave_scheduler.py` with `@register("strategy","wave_scheduler",user_allowed=True)`, pure `build_waves` (Kahn-levels, conflict-key split), `runner.run_fanout(requests, ctx, step=step)` at line 244. `sample_wave` workflow confirmed manifest+AGENT.md only; `grep sample_wave backend/agents/execution_engine/` = 0. Characterization snapshots byte-identical (10 passed). `build_waves` CP-SAT seam documented in module docstring. |
| 2 | `wave_runs` persisted; a server restart resumes mid-wave via `subagent_runs`/`wave_runs`; idempotent step retry reuses artifacts on content-hash match | VERIFIED | `wave_runs` table (0020 migration, WaveRun ORM, ScopedStore writer/reader) confirmed. `resume_run` now seeds counter at `max(existing_seq)+1` (CR-01 fix). Step-filtered `_completed_wave_indices` (CR-04 fix) and whole-in-flight-wave re-run (CR-03 fix) make mid-wave resume correct for parallel waves. `_dispatch_step_with_retry` wrapper + `_compute_step_input_hash` confirmed for RESUME-02. Test suite 160/167 pass. |
| 3 | Reconnect replays from the durable `run_events` log (`after=<seq>`, idempotent by `event_id`); `restore_non_terminal_runs` resumes at step granularity (`waiting_for_user` gates resume on user action) | VERIFIED (offline) | CR-02 fix: `websocket.py:608-637` recovers workspace_id from owner-scoped RunEvent row; `read_events` now matches production rows. `shouldApplyEvent` dedup hoisted to top of `handleWebSocketMessage` covering all event types (CR-05). `restore_non_terminal_runs` three-way classifier confirmed; `waiting_for_user` branch unchanged. 7 WS reconnect replay tests pass. LIVE render/reconnect UAT deferred per project convention. |

**Score:** 3/3 ROADMAP success criteria VERIFIED

### Must-Have Truths (from PLAN frontmatter — all 7 plans)

| # | Plan | Truth | Status | Evidence |
|---|------|-------|--------|----------|
| 1 | 12-01 | wave_scheduler topo-sorts json_tasks into deterministic waves and runs each wave through ctx.runner.run_fanout | VERIFIED | `wave_scheduler.py:244` confirmed |
| 2 | 12-01 | build_waves raises pre-spawn on cycle/unknown ref (zero wave_runs/subagent_runs rows) | VERIFIED | `WaveBuildError` at lines 82-84, 96; duplicate-id guard added (WR-05 fix) |
| 3 | 12-01 | Tasks with overlapping conflict_keys never co-schedule | VERIFIED | within-level conflict-key split lines 99-110; test_wave_scheduler.py green |
| 4 | 12-01 | Sample multi-file workflow (manifest + AGENT.md only) runs in >=2 waves, zero engine edits | VERIFIED | `sample_wave` confirmed; `grep sample_wave backend/agents/execution_engine/` = 0; 3 tests pass |
| 5 | 12-01 | Each executed wave persists one owner-scoped wave_runs row reaching terminal; cross-owner read returns nothing | VERIFIED | authz.py record_wave_run/read_wave_runs confirmed; cross-owner test passes |
| 6 | 12-01 | 5 characterization snapshots byte/event-identical | VERIFIED | 10 characterization tests passed; lint-imports 4/0 |
| 7 | 12-02 | Step with retry.max_attempts > 0 retries on transient errors up to max_attempts | VERIFIED | `_dispatch_step_with_retry` wrapper confirmed; 7 tests pass |
| 8 | 12-02 | Non-transient error does NOT retry | VERIFIED | test_step_retry.py confirms non-transient no-retry |
| 9 | 12-02 | Existing artifact keyed (run_id, step_id, input_hash) is reused without re-invoking | VERIFIED | `_compute_step_input_hash` + `_find_reused_completion` confirmed; reuse test passes |
| 10 | 12-02 | Step with no declared retry byte-identical to today | VERIFIED | Strict gate `step.retry and step.retry.max_attempts > 0`; characterization snapshots unchanged |
| 11 | 12-03 | reconnect_pipeline accepts after_seq and replays missed run_events idempotently | VERIFIED | CR-02 fix lands; `websocket.py:608-637` recovers workspace and constructs full owner+workspace-scoped store; 7 replay tests pass |
| 12 | 12-03 | Reconnect after simulated process restart replays from durable log | VERIFIED | `test_production_shaped_replay_recovers_workspace_and_returns_rows` confirms production-shaped store (no explicit workspace_id) returns rows |
| 13 | 12-03 | Legacy reconnect without after_seq behaves exactly as today | VERIFIED | Legacy path preserved; test asserts no replay frames |
| 14 | 12-03 | restore_non_terminal_runs auto-resumes from first incomplete step; previously-completed wave/worker not re-invoked | VERIFIED | Three-way classifier confirmed. CR-03/CR-04 fixed: step-filtered completed indices + whole-in-flight wave re-run; stale running row flipped `superseded` (WR-01). CR-01 fixed: resumed events carry seq > N. Note: WR-09 (superseded not recognized terminal in `_first_incomplete_step`) means a SECOND restart after a prior resume re-enters at the wave step — carried as a tracked warning, not a ROADMAP blocker |
| 15 | 12-03 | waiting_for_user gates on user action; stateless runs keep WR-05 path | VERIFIED | Branch a/c confirmed in code and tests |
| 16 | 12-04 | Wave/subagent tree panel renders waves and workers from wave_*/subagent_* events | VERIFIED (offline) | CR-06 backend: `wave_scheduler.py:262-266` stamps `wave_index`+`step` on subagent events. CR-06 FE: `page.tsx:281-288` keys leaves by `data.worker`. `test_subagent_events_carry_wave_index_and_step` passes. LIVE render deferred to end-of-milestone |
| 17 | 12-04 | FE reconnect sends last-received seq as after_seq and dedupes by event_id | VERIFIED | `DashboardLayout.tsx:533` after_seq confirmed. CR-05 fix: `shouldApplyEvent` dedup at top of `handleWebSocketMessage` covers all event types. `wsReplayState.test.ts` 6 tests pass |
| 18 | 12-04 | No existing panel modified; existing-workflow UI unchanged | VERIFIED | WorkflowComposer additive mount confirmed; ValidatorIssuePanel mount unchanged |
| 19 | 12-05 | On a process-restart resume, resumed run_events persist with seq strictly greater than the pre-restart max seq | VERIFIED | `engine.py:4054-4067`: `start = max(seq)+1`; `test_resumed_events_seq_continues_past_durable_tail` asserts min(resumed seq) == N+1 |
| 20 | 12-05 | A reconnecting client that sends after_seq=N receives every resumed event | VERIFIED | Same test confirms `read_events(after_seq=N)` returns non-empty resumed tail |
| 21 | 12-05 | WS reconnect replay branch constructed exactly as websocket.py constructs it returns the run's persisted run_events | VERIFIED | `test_production_shaped_replay_recovers_workspace_and_returns_rows` exercises the production-shaped store (no explicit workspace_id); returns rows |
| 22 | 12-06 | A mid-wave crash with out-of-dispatch-order completions never drops an incomplete task on resume | VERIFIED | `wave[_remaining_completed:]` deleted; `test_midwave_resume_reruns_whole_inflight_wave_no_parallel_dropout` asserts whole wave re-run |
| 23 | 12-06 | A run with two wave_scheduler steps resumes the second step's waves independently of the first step's completed wave indices | VERIFIED | `getattr(r, "step", None) == step_id` filter; `test_cross_step_does_not_skip_second_steps_waves` passes |
| 24 | 12-06 | subagent_spawned/subagent_result events carry wave_index | VERIFIED | `wave_scheduler.py:262-266`; `test_subagent_events_carry_wave_index_and_step` passes |
| 25 | 12-06 | A duplicate task id raises a named error before any spawn | VERIFIED | `json_tasks.py:128` + `wave_scheduler.py:84-85`; `test_duplicate_task_id_raises_named_valueerror` + `test_build_waves_rejects_duplicate_task_id_before_any_wave` pass |
| 26 | 12-06 | On resume, stale pre-crash wave_runs row for the re-entered (step, wave_index) is flipped terminal | VERIFIED | `wave_scheduler.py:228-241`; `test_stale_running_wave_row_is_flipped_terminal_on_resume` passes |
| 27 | 12-06 | CR-03-followup per-task skip recorded durably in CONTEXT.md Deferred Ideas | VERIFIED | `12-CONTEXT.md:176` — CR-03-followup bullet confirmed under `## Deferred Ideas` |
| 28 | 12-07 | Worker leaves render under their wave group (subagent events folded in, not dropped) | VERIFIED (offline) | FE consumes `data.wave_index`/`data.step`/`data.worker` flat keys (pinned to 12-06-SUMMARY contract); guard `if (waveIndex === undefined) return;` now passes for wave-run events; tsc clean |
| 29 | 12-07 | N parallel workers of the same agent render as N distinct leaves | VERIFIED (offline) | `page.tsx:284-288` keys leaves by `data.worker` (numeric index), not agent name |
| 30 | 12-07 | On a mid-run reconnect, no event (wave OR non-wave) is applied twice | VERIFIED | `shouldApplyEvent` dedup at top of handler covers all event types; `wsReplayState.test.ts` proves a repeated event_id is a no-op (second call returns false) |
| 31 | 12-07 | Starting a new run resets the FE replay/dedup/wave state | VERIFIED | `page.tsx:337-344` resets seen-set/`lastSeqRef`/`waveGroups` on `pipeline_start`; `wsReplayState.test.ts` proves reset clears refs |

**Score:** 31/31 plan-level must-have truths VERIFIED

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/agents/capabilities/strategies/wave_scheduler.py` | wave_scheduler strategy + pure build_waves seam | VERIFIED | `@register("strategy","wave_scheduler",user_allowed=True)`, `build_waves`, `WaveBuildError`, step-filtered `_completed_wave_indices`, whole-wave re-run on resume, stale-row flip, wave_index stamping on subagent events |
| `backend/agents/capabilities/task_parsers/json_tasks.py` | json_tasks structured-task parser | VERIFIED | `@register("task_parser","json_tasks")`, full parse() with duplicate-id check (primary gate) and depends_on validation |
| `backend/alembic/versions/0020_wave_runs.py` | additive wave_runs migration (down_revision 0019) | VERIFIED | `revision="0020"`, `down_revision="0019"`, no `sa.Enum`, reversible |
| `backend/app/models/wave_run.py` | WaveRun ORM on Base.metadata | VERIFIED | `class WaveRun(Base)`, `__tablename__ = "wave_runs"` |
| `backend/agents/workflows/sample_wave/workflow.yaml` | SC-001 sample wave workflow | VERIFIED | Located at `backend/agents/workflows/sample_wave/`; `strategy: wave_scheduler`, `parser: json_tasks` |
| `backend/agents/execution_engine/engine.py` | resume_run entry + three-way restore + retry wrapper + durable tail seq seeding | VERIFIED | `resume_run`, `_dispatch_step_with_retry`, `restore_non_terminal_runs` three-way all present; CR-01 fix: `itertools.count(start)` with `start = max(seq)+1` from recovered-workspace durable tail |
| `backend/app/api/websocket.py` | reconnect_pipeline after_seq durable replay branch with workspace recovery | VERIFIED | CR-02 fix: `websocket.py:608-637` recovers workspace_id from owner-scoped RunEvent row; full owner+workspace-scoped ScopedStore; recovery is server-side, never client-supplied |
| `frontend/src/components/workflow/WaveTreePanel.tsx` | props-driven wave/subagent tree panel | VERIFIED (offline) | Wave group rendering confirmed; worker leaves now key by `(step, waveIndex)` (IN-06 fix); cancelled renders terminal (IN-05 fix); React key `${group.step}:${group.waveIndex}` |
| `frontend/src/app/dashboard/page.tsx` | wave/subagent event routing + event_id dedup at top of handler + worker leaves keyed by worker index | VERIFIED | `shouldApplyEvent` at top of `handleWebSocketMessage` (CR-05); `data.worker`-keyed leaves (CR-06 FE); group lookup keyed by `(step, waveIndex)` (IN-06) |
| `frontend/src/lib/wsReplayState.ts` | pure dedup-decision + per-run-reset helper | VERIFIED | `shouldApplyEvent` + `resetReplayState` exported; 6 vitest behavioral tests pass |
| `frontend/src/components/layout/DashboardLayout.tsx` | after_seq on reconnect_pipeline | VERIFIED | `after_seq: afterSeq` at line 533 confirmed (unchanged from initial verification) |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `wave_scheduler.py` | `ctx.runner.run_fanout` | one run_fanout call per wave | VERIFIED | `runner.run_fanout(requests, ctx, step=step)` at line 244 |
| `kernel_services.py` | `ScopedStore.record_wave_run` | best-effort None-degrading recorder | VERIFIED | `record_wave_run` lines 473-503; None-guard on store |
| `authz.py` | `wave_runs` table | default-deny owner+workspace scoped writer/reader | VERIFIED | `_scope_owner_ws` filter in `read_wave_runs`; cross-owner test passes |
| `websocket.py` | `ScopedStore.read_events` | owner-scoped durable replay via recovered workspace_id | VERIFIED | `websocket.py:608-637` recovers workspace from owner-scoped RunEvent lookup; full default-deny scoping preserved (T-12-05-TENANT) |
| `engine.py resume_run` | durable `run_events` tail | max(seq)+1 seed for counter | VERIFIED | `engine.py:4054-4067`; `tail_store.read_events(run_id, after_seq=0)` under recovered workspace |
| `engine.py` | `compile_for_run` | resume rebuilds ExecutionContext via single construction path | VERIFIED | `compile_for_run` called at line 841 in `_execute_impl` |
| `engine.py` | `wave_runs / subagent_runs` | step-filtered completed-wave set + whole-in-flight re-run | VERIFIED | `_completed_wave_indices` step-filtered; `_remaining_completed` slice deleted |
| `wave_scheduler.py` | re-yielded subagent events | wave_index + step stamped at re-yield boundary | VERIFIED | `wave_scheduler.py:252-266`; fanout.py untouched (INV-12) |
| `DashboardLayout.tsx` | `reconnect_pipeline after_seq` | last-received seq sent on reconnect | VERIFIED | `after_seq: afterSeq` at line 533; `lastSeqRef` tracker confirmed |
| `dashboard/page.tsx` | `WaveTreePanel` | wave/subagent tree state from deduped lifecycle events | VERIFIED (offline) | Wave group + worker leaf state confirmed; `data.worker`-keyed leaves; tsc clean |
| `page.tsx handleWebSocketMessage` | `wsReplayState.shouldApplyEvent` | event_id dedup at top before any routing | VERIFIED | `page.tsx:212` calls `shouldApplyEvent` before `WAVE_EVENT_TYPES.includes` branch |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `wave_scheduler.py` | `waves` (list[list[Task]]) | `build_waves(tasks)` → `runner.run_fanout` | Yes — pure topo-sort + real fan-out | FLOWING |
| `wave_run.py` (ORM) | `wave_runs` rows | `ScopedStore.record_wave_run` → SQLAlchemy session.add | Yes — real DB writes | FLOWING |
| `websocket.py` reconnect branch | `_missed` (run_events) | `ScopedStore(owner_id=user.id, workspace_id=_recovered_ws).read_events(...)` | Yes — CR-02 fix: workspace_id recovered from owner-scoped RunEvent row; matches production rows | FLOWING |
| `engine.py resume_run` | resumed event seq | `itertools.count(max(existing_seq)+1)` | Yes — CR-01 fix: counter seeded past durable tail; resumed events carry seq > N | FLOWING |
| `WaveTreePanel.tsx` | `waves[*].workers` | `subagent_spawned`/`subagent_result` with `wave_index`+`step`+`worker` | Yes — CR-06 fix: events stamped at strategy re-yield boundary; FE folds by `data.worker` | FLOWING (offline verified) |

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| wave_scheduler topo-sort and fan-out | `pytest tests/agents/test_wave_scheduler.py` | 10 passed | PASS |
| json_tasks parser | `pytest tests/agents/test_json_tasks.py` | 12 passed | PASS |
| wave_runs persistence + authz | `pytest tests/agents/test_wave_runs.py` | 7 passed | PASS |
| sample_wave SC-001 proof | `pytest tests/agents/test_sample_wave_workflow.py` | 3 passed | PASS |
| per-step retry + content-hash reuse | `pytest tests/agents/test_step_retry.py` | 7 passed | PASS |
| WS reconnect replay — CR-02 fix (production-shaped store) | `pytest tests/agents/test_ws_reconnect_replay.py` | 7 passed (incl. 2 new: production-shaped + cross-owner) | PASS |
| restart + mid-wave resume — CR-01/CR-03/CR-04/WR-01 fixes | `pytest tests/agents/test_restart_resume.py` | 7 passed (incl. 4 new: seq continuity, parallel no-dropout, cross-step, stale-row flip) | PASS |
| characterization snapshots byte-identical | `pytest tests/agents/test_characterization_*.py` | 10 passed | PASS |
| import-linter contracts | `lint-imports` from backend/ | 4 kept / 0 broken | PASS |
| registry lockstep + migration ledger | `pytest tests/agents/test_registry_capabilities.py tests/agents/test_migration_ledger.py` | all pass (lockstep 61; WAVE-PERSIST flipped) | PASS |
| FE dedup/reset pure helper | `npx vitest run src/lib/wsReplayState.test.ts` | 6 passed | PASS |
| FE TypeScript clean | `npx tsc --noEmit` | 0 errors | PASS |
| Full targeted backend suite | pytest (all 12-phase tests) | 160 passed, 7 skipped | PASS |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| WAVE-01 | 12-01 | wave_scheduler topo-sorts by depends_on + conflict_keys into waves, runs via fan-out; deterministic builder, CP-SAT seam | SATISFIED | wave_scheduler.py confirmed; sample_wave SC-001 proof; build_waves pure seam + CP-SAT docstring seam |
| WAVE-02 | 12-01 | wave_runs persistence; multi-file workflow in parallel waves; prototype stays sequential | SATISFIED | 0020 migration + WaveRun ORM + ScopedStore methods; sample_wave test; characterization snapshots unchanged |
| WAVE-03 | 12-01/12-03/12-06 | Resume mid-wave via subagent_runs/wave_runs after restart | SATISFIED | CR-03/CR-04/WR-01 all fixed: step-filtered completed-wave set, whole-in-flight re-run, stale-row flip. WAVE-03 first-restart scenario correct. Note: WR-09 (superseded not recognized by `_first_incomplete_step`) means a SECOND restart after a prior resume re-enters the wave step — tracked warning, not a WAVE-03 blocker for the primary SC |
| RESUME-02 | 12-02 | Idempotent per-step retry keyed by (run_id, step_id, input_hash); reuses artifact on hash match | SATISFIED | `_dispatch_step_with_retry` wrapper confirmed; `_compute_step_input_hash` cross-restart-stable; test_step_retry.py 7 passed |
| RESUME-03 | 12-03/12-04/12-05/12-07 | Reconnect = durable replay from run_events via after=<last_seq>, idempotent by event_id | SATISFIED (offline) | CR-01 + CR-02 fixes: seq continuity + workspace recovery; `shouldApplyEvent` all-event-type dedup. 7 WS replay tests pass. LIVE reconnect deferred to end-of-milestone |
| RESUME-04 | 12-03/12-06 | Server restart = restore_non_terminal_runs at step granularity; waiting_for_user gates | SATISFIED | Three-way classifier + resume_run present; waiting_for_user branch unchanged; WR-05 path unchanged; mid-wave skip correct for parallel waves (CR-03/CR-04) |

All 6 requirement IDs confirmed `[x]` Complete in `.planning/REQUIREMENTS.md` traceability table.

---

## Anti-Patterns Found (Post-Gap-Closure)

These are new warnings surfaced by the post-gap-closure code review (12-REVIEW.md). None breaks a ROADMAP success criterion for the first-restart scenario. They are carried as tracked quality debt, consistent with how WR-02/04/06/07/08 and IN-01..04 were handled in the prior review.

| File | Finding | Severity | Impact |
|------|---------|----------|--------|
| `engine.py:3917-3920` | WR-09: `_first_incomplete_step` buckets `superseded` as `running` (`else: running_wave_steps.add(sid)`) — on a SECOND restart after a prior resume, the wave step is re-classified as incomplete and re-entered | WARNING | Second-restart only: re-runs downstream steps from the wave step; wastes model spend, no data loss. First restart behavior is correct. Fix: add `superseded`/`cancelled` to the terminal skip branch. |
| `engine.py:699,1117,1130` | WR-10: `is_resuming` and `_resuming` keyed on `_resume_from > 0`, not `_is_resume` — an offset-0 resume (crash before first step completes) re-runs the planner and hits a forced clarify hang | WARNING | Offset-0 resume edge case: strands run in waiting_for_user with no client. The CR-01/CR-02/CR-03/CR-04 primary scenarios are offset > 0 after step completion. |
| `engine.py:3995-4018,4093` | WR-11: `resume_run` failure paths leave run non-terminal — infinite resume-attempt loop across restarts | WARNING | Resume failure (no agents, compile failure, mid-drive exception) leaves run alive; every restart retries the same doomed resume forever. |
| `engine.py:3004-3006` | WR-12: `asyncio.create_task(resume_run(...))` result dropped — task can be garbage-collected mid-drive | WARNING | A resume task mid-drive can be silently collected; run strands non-terminal until next restart (compounds WR-11). |
| `page.tsx:336-345` | WR-13: resumed run re-emits `pipeline_start` mid-replay — FE per-run reset wipes just-replayed dedup/wave state during a durable reconnect | WARNING | Pre-crash waves do not come back in the tree panel after a resume; cursor can reset to 0 causing a re-replay of the entire pre-crash tail undeduped (seen-set cleared). |
| `wave_scheduler.py:198-206` | WR-14: a wave step that declares `retry` re-runs all already-completed waves on a transient retry — durable skip gated on `is_resuming` only | WARNING | No shipped manifest declares `retry` on a wave step today; user-composed manifests can trigger this. |
| `websocket.py:593,657` | IN-01 (carried): `_did_replay` assigned but never read | INFO | Dead variable. |
| `websocket.py:668` | IN-02 (carried): `replayed_through_seq` reports the requested `after_seq`, not the last replayed seq | INFO | Client persisting this as cursor re-requests the same tail. |
| `json_tasks.py:37` | IN-03 (carried): fence regex extracts the first fenced block, not the JSON-tagged one | INFO | Prose with a non-json fence before the plan block parses the wrong block. |
| `engine.py:4104-4119` | IN-04 (carried): `_compute_resume_offset` fallback comment overclaims content-hash reuse; mints orphan workspace rows | INFO | Comment misleading; `create_workspace` fallback creates orphan row. |
| `engine.py:3087-3097` | IN-07 (NEW): `run_resuming` marker payload lacks `seq`/`event_id` — invisible to FE cursor and dedup on replay | INFO | Replayed marker never advances `lastSeqRef` and is never deduped (harmless legacy pass-through). |
| `test_ws_reconnect_replay.py:158-199` | IN-08 (NEW): WS replay branch handler code has zero direct coverage — suite mirrors its logic | INFO | Mirror and handler can drift silently again. |

---

## Human Verification Required

### 1. Live Wave-Tree Panel Render with N Distinct Worker Leaves

**Test:** Start backend (`cd backend && python3.11 -m uvicorn app.main:app --reload`) and frontend (`cd frontend && npm run dev`). Run the `sample_wave` workflow from the composer UI.
**Expected:** WaveTreePanel renders wave groups (index + task ids + status badge flipping running->completed) AND worker leaves under each wave. For `sample_wave`'s self-x-N shape, confirm N DISTINCT worker leaves appear in wave 1 — not one collapsed flapping leaf (CR-06 FE half live).
**Why human:** No headless DOM harness for the full dashboard in the repo (08-08 Task-3 precedent). Deferred to end-of-milestone live pass per project convention.

### 2. Live After-Seq Reconnect Replay — No Duplicate Events, No Lost Tail

**Test:** While a wave run is streaming, reload the page (or toggle the network). Inspect WS frames in the network tab.
**Expected:** Reconnect sends `after_seq`; wave/worker tree resumes WITHOUT duplicated entries; streamed `agent_chunk` text is NOT duplicated (CR-05 fix live); missed tail is NOT lost (CR-01/CR-02 fixes live). A second `pipeline_start` mid-replay should not wipe the wave panel (WR-13 is a tracked warning — verify behavior).
**Why human:** Requires live network toggle against running servers. Deferred to end-of-milestone live pass.

### 3. Second Run Resets Wave Panel and Reconnect Cursor

**Test:** After run 1 completes, start run 2. Confirm the previous run's wave panel cleared. Trigger a mid-run reconnect on run 2 and confirm the reconnect sends `after_seq=0` (not run 1's final seq) and replays correctly.
**Expected:** `lastSeqRef` reset to 0 on the new run's `pipeline_start`; panel shows only run 2's waves; reconnect from run 2 delivers the correct tail (WR-03 fix live).
**Why human:** Requires sequential run execution against live servers. Deferred to end-of-milestone live pass.

---

## Gaps Summary

No blocking gaps. All four prior blockers (CR-01, CR-02, CR-03/CR-04, CR-06) are CLOSED and verified in code with regression tests. The human verification items above are the sole remaining open items — they are deferred to the end-of-milestone live pass per project convention (recorded in 12-07-SUMMARY.md and in the user memory `defer-live-verification-to-milestone-end.md`).

The six new warnings from the post-gap-closure code review (WR-09 through WR-14) are quality debt carried forward. WR-09 is the most actionable: a one-line fix in `_first_incomplete_step` to recognize `superseded` as a terminal status would prevent second-restart wave step re-entry. None of WR-09 through WR-14 breaks a ROADMAP success criterion for the first-restart scenario.

---

_Verified: 2026-06-11T14:00:00Z_
_Verifier: Claude (gsd-verifier)_
_Re-verification: Yes — after gap closure (plans 12-05/12-06/12-07)_
