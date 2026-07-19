---
phase: 46-per-task-substrate-cursor-live-layer-r1
plan: 04
subsystem: execution-engine / capability-strategies
tags: [resume, skip-cursor, task_loop, wave_scheduler, kernel-computed, RESUME-09]

# Dependency graph
requires:
  - phase: 46-per-task-substrate-cursor-live-layer-r1
    provides: "46-01 subagent_runs.task_id stamped at spawn; 46-02 per-task durable capture (distinct task_id artifact_refs); 46-03 durable→disk re-materialization so skipped work is on disk"
  - phase: 45-resume-completeness-bug-fix-r0
    provides: "the distinct-task_id completeness derivation + the seed-durable-then-invoke test idiom"
provides:
  - "ExecutionContext.resume_completed_task_ids: dict[str, set[str]] | None = None — the dormant kernel-computed per-step skip cursor (mirrors is_resuming)"
  - "ExecutionEngine._compute_resume_completed_task_ids(ectx, ordered_agents, compiled) — reads the run's own owner-scoped durable rows and returns {step_agent_id: {task_id,...}} (task_loop: distinct artifact task_id; wave: subagent_runs status==complete task_id)"
  - "task_loop skips completed task_nums on resume (identity-based); wave_scheduler re-runs only the incomplete workers of the in-flight wave (identity-based, the CR-03-followup)"
affects: [46-05 live-layer, RESUME-09]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dormant kernel-computed ectx cursor: compute the per-step completed-identity set from durable rows, stamp on ectx before the dispatch loop, strategies read via getattr(...,None) — None on normal runs ⇒ byte/event-identical (INV-3), the is_resuming idiom"
    - "Identity-based intra-step skip keyed on plan-global task_id (never wave-local worker_index), fail-safe direction = re-run on any read failure/ambiguity"

key-files:
  created: []
  modified:
    - backend/agents/execution_engine/context.py
    - backend/agents/execution_engine/engine.py
    - backend/agents/capabilities/strategies/task_loop.py
    - backend/agents/capabilities/strategies/wave_scheduler.py
    - backend/tests/agents/test_restart_resume.py

key-decisions:
  - "Stamp the cursor at the dispatch-prep site (after _steps_by_agent, before the enumerate loop) — NOT at the :1362 re-materialize hook — because compiled/ordered_agents are only in scope there; still 'before the dispatch loop' per the must_have"
  - "Cursor keyed on the step's agent_id (== spec.id == step.agent_id == subagent_runs.parent_step) so task_loop/wave_scheduler read completed = cursor.get(agent_id)"
  - "Wave filter applies the completed set to every wave's request build (not just a hand-picked in-flight wave): a completed task_id is globally unique to ONE wave, so filtering all waves is equivalent to filtering only the in-flight one and needs no wave-index bookkeeping"
  - "Added a THIRD test (kernel compute) beyond the plan's two, to prove must_have truth #1 (kernel decides the set) + Edge-Case 1 dedup + Edge-Case 5 task_id keying directly"

patterns-established:
  - "Kernel-computed dormant skip cursor threaded into strategies via a declared ExecutionContext field"

requirements-completed: [RESUME-09]

# Metrics
duration: 30min
completed: 2026-07-19
---

# Phase 46 Plan 04: Kernel Skip Cursor (Per-Task + Per-Worker) Summary

**Resume now skips completed work at task/worker granularity via a KERNEL-computed cursor: the engine reads the run's own owner-scoped durable rows, computes the completed-identity set per step (task_loop: distinct `artifact_refs.task_id`; wave: `subagent_runs` `task_id` where `status=="complete"`), and threads it into the strategies through the dormant `ExecutionContext.resume_completed_task_ids` field. `task_loop` skips completed task_nums; `wave_scheduler` re-runs only the incomplete workers of the in-flight wave (the CR-03-followup — identity-based, NOT the deleted prefix-by-count skip). The AGENT never decides the skip set; completed work still arrives as injected context (unchanged); re-invocation of remaining work stays on the same `run_agent`/`run_fanout` paths (INV-13). The cursor is None/dormant on every normal run ⇒ goldens byte/event-identical.**

## Performance
- **Duration:** ~30 min
- **Completed:** 2026-07-19
- **Tasks:** 2 (TDD RED → GREEN)
- **Files modified:** 5 (0 created, 5 modified)

## Accomplishments
- **Dormant ectx field** `resume_completed_task_ids: dict[str, set[str]] | None = None` beside `is_resuming` with the full kernel-computed / INV-1 / INV-2 / INV-3 / fail-safe rationale comment; `None` on every normal run.
- **Kernel compute** `_compute_resume_completed_task_ids` mirrors the `_first_incomplete_step` durable reads: one `store.tree` + one `read_subagent_runs`, both owner-scoped; per-step try/except leaves an unreadable step OUT (re-run, never skip). Keys only on generic identity (`strategy`/`producer_agent`/`task_id`/`status`) — zero name literals.
- **Stamp** on `ectx` gated on `_is_resume`, immediately before the single dispatch loop; wrapped best-effort → `None` on failure.
- **task_loop skip:** reads the cursor via `getattr`, skips the `run_agent`/persist/fix-loop for a completed `str(task_num)` (identity-based); the file is already on disk from 46-03 re-materialization so the next task's skeleton read stays coherent.
- **wave_scheduler skip:** filters `requests`/`task_ids` to workers whose `t.id ∉` the completed set; terminal-wave `_completed_wave_indices` skip + the stale-`running`→`superseded` flip untouched; the deleted prefix-by-count skip is NOT reintroduced.

## Task Commits
1. **Task 1: RED — dormant field + 3 skip/cursor tests** — `c6f7a484` (test)
2. **Task 2: GREEN — kernel compute + stamp + the two strategy skips** — `b2d73500` (feat)

## RED → GREEN Evidence

RED (Task 1, on HEAD before the source change):
```
test_task_loop_skips_completed_tasks_on_resume_cursor
  AssertionError: got task_nums [1, 2, 3]  (expected [3])
test_wave_scheduler_skips_completed_workers_on_resume_cursor
  AssertionError: completed worker 'tb' was RE-DISPATCHED  (dispatched ['ta','tb','tc'])
test_kernel_computes_resume_completed_task_ids_cursor
  AttributeError: 'ExecutionEngine' object has no attribute '_compute_resume_completed_task_ids'
3 failed, 2 passed (the 2 Phase-45 partial/complete build tests stay green)
```
GREEN (Task 2): the 3 tests pass — `5 passed` for `-k "skip or cursor or resume_completed"`.

## Verification (verify-by-delta)
| Gate | Result | Baseline expectation |
|------|--------|----------------------|
| `test_restart_resume.py` | 12 passed / 1 failed | KAN-88 (`test_waiting_for_user_run_is_rearmed_not_driven`) the SOLE fail ✓ |
| `test_wave_scheduler.py` | `10 passed` | terminal-wave skip + stale-flip intact ✓ |
| Goldens `test_characterization_*.py` (SNAPSHOT_UPDATE unset) | `10 passed` | cursor dormant on non-resume ✓ |
| `test_fanout.py` + `test_subagent_runs.py` | `39 passed` | spawn/merge/identity intact ✓ |
| `test_banned_patterns.py` + `test_sc001_fanout.py` | `14 passed` | no name literal added ✓ |
| Consolidated wave gate (6 suites) | `76 passed / 1 failed` | KAN-88 sole fail ✓ |
| `/opt/homebrew/bin/lint-imports` | `4 kept, 0 broken` | 4/0 ✓ |
| INV-1 grep (`pipeline_type ==|spec.id ==` engine.py) | `0` | 0 ✓ |
| INV-12 grep (`for i, spec in enumerate(ordered_agents)`) | `1` | 1 ✓ |
| `grep -c resume_completed_task_ids context.py` | `1` | field declared once ✓ |

## Decisions Made
- **Stamp site.** The plan text says "after the hydrate/re-materialize calls at :1350", but `compiled`/`ordered_agents` are only constructed later (`:1410`/`:1613`). The cursor is computed + stamped right after `_steps_by_agent` (`:2054`), immediately before the `enumerate(ordered_agents)` dispatch loop — the first point where every input is in scope AND still "before the dispatch loop" per the must_have. `_is_resume`-gated, so dormant on normal runs.
- **Key = agent_id.** `spec.id == step.agent_id == subagent_runs.parent_step`, so the cursor is keyed on the step agent id and both strategies read `cursor.get(agent_id)` (task_loop `agent_id`, wave `step_id`).
- **Wave filter is global-set, per-wave.** A completed `task_id` is unique to exactly one wave, so filtering every wave's request build by the completed set is equivalent to filtering only the in-flight wave — no wave-index bookkeeping, and later never-dispatched waves are unaffected (none of their tasks are in the set).
- **Extra kernel-compute test.** Added `test_kernel_computes_resume_completed_task_ids_cursor` (beyond the plan's two) to prove the kernel — not the agent — decides the set, plus the Edge-Case 1 fix-loop dedup (same `task_id` counts once) and Edge-Case 5 `task_id` (not `worker_index`) keying, directly against seeded durable rows.

## Deviations from Plan
None — plan executed as written. The only latitude taken (both pre-authorized by the plan's `<action>` / Claude's-Discretion): the compute+stamp lives at the dispatch-prep site rather than the literal `:1350` line (compiled/ordered_agents scope), and one extra proof test was added. No production behavior differs from the plan's contract.

## Interaction Notes (for downstream plans)
- **All-workers-complete-but-unmerged wave:** if every worker of the in-flight wave is in the completed set, the wave dispatches empty `requests` → `run_fanout([])` is a clean no-op and `_merge_fragments([])` merges nothing — which is correct because 46-03 already re-materialized those fragments onto the base sandbox disk. The wave then flips `completed`. (Not separately tested here; covered by 46-03's re-materialization.)
- **Failed workers re-run:** only `status=="complete"` workers enter the set, so a `failed`/`running`/`cancelled` worker is NOT skipped (fail-safe = re-run).
- **46-05 (live-layer):** the cursor is orthogonal to live-ectx/milestone re-registration; both consume the same `_is_resume` resume tier.

## Threat Flags
None — no new endpoint/auth surface. The completed-set is computed by the KERNEL from the run's own owner-scoped `ScopedStore` rows (`store.tree`/`read_subagent_runs`, default-deny), never widened; the agent receives completed work only as read-only injected context and cannot decide the skip set (T-46-04-01/02 mitigated). Fail-safe direction is re-run; distinct-`task_id` `set` avoids over-counting the fix-loop re-persist; keyed on the globally-unique `task_id`, never the ambiguous `worker_index` (T-46-04-03 mitigated).

## Self-Check: PASSED
- FOUND: backend/agents/execution_engine/context.py (`resume_completed_task_ids`)
- FOUND: backend/agents/execution_engine/engine.py (`_compute_resume_completed_task_ids`)
- FOUND: backend/agents/capabilities/strategies/task_loop.py (per-task skip)
- FOUND: backend/agents/capabilities/strategies/wave_scheduler.py (per-worker filter)
- FOUND: backend/tests/agents/test_restart_resume.py (3 new tests)
- FOUND commit: c6f7a484 (test RED)
- FOUND commit: b2d73500 (feat GREEN)

---
*Phase: 46-per-task-substrate-cursor-live-layer-r1*
*Completed: 2026-07-19*
