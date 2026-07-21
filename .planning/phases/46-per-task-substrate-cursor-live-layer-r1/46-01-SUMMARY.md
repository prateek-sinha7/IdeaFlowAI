---
phase: 46-per-task-substrate-cursor-live-layer-r1
plan: 01
subsystem: execution-engine / persistence
status: complete
wave: 1
requirements: [RESUME-06]
commits:
  - bac2a16c: "feat(46-01): migration 0026 + subagent_runs task identity columns (Task 1)"
  - 4440e278: "feat(46-01): thread worker_index/task_id through spawn/record chain (Task 2)"
dependency_graph:
  requires: []
  provides:
    - "subagent_runs.task_id + subagent_runs.worker_index (nullable, stamped at spawn)"
    - "ScopedStore.record_subagent_run(worker_index=, task_id=) kwargs"
    - "KernelServices.record_subagent_run(worker_index=, task_id=) kwargs"
    - "fanout _select_workers preserves task_id; _run_one stamps identity at spawn"
    - "wave_scheduler requests carry task_id=t.id"
  affects:
    - "Plan 46-04 (RESUME-09 skip cursor) reads subagent_runs.task_id"
tech-stack:
  added: []
  patterns:
    - "additive-nullable-column trilogy (migration + ORM + threading), the 0022/0023 precedent"
key-files:
  created:
    - backend/alembic/versions/0026_subagent_task_identity.py
  modified:
    - backend/app/models/subagent_run.py
    - backend/agents/authz.py
    - backend/agents/execution_engine/kernel_services.py
    - backend/agents/execution_engine/fanout.py
    - backend/agents/capabilities/strategies/wave_scheduler.py
    - backend/tests/unit/test_migrations.py
    - backend/tests/agents/test_subagent_runs.py
    - backend/tests/agents/test_fanout.py
    - backend/tests/agents/test_merge_conflict.py
    - backend/tests/agents/test_isolation.py
    - backend/tests/agents/test_budget.py
    - backend/tests/agents/test_fanout_cancel.py
    - backend/tests/agents/test_sc001_fanout.py
metrics:
  duration_min: 6
  completed: 2026-07-19
  tasks: 2
  files_changed: 13
---

# Phase 46 Plan 01: Per-Task Substrate — Migration 0026 + Spawn Identity Stamping Summary

Added per-child task identity (`task_id` + `worker_index`) to `subagent_runs`, stamped at
SPAWN through the fan-out and wave dispatch paths — the durable foundation the RESUME-09
skip cursor (Plan 46-04) reads to know which workers already completed before a crash.

## Accomplishments

- **Migration 0026** (`0026_subagent_task_identity.py`): additive `batch_alter_table.add_column`
  of nullable `task_id` (String) + `worker_index` (Integer) on `subagent_runs`,
  `down_revision="0025"`, reverse-order batch drop in `downgrade()`. No new table, no
  destructive alter; existing FK `parent_run_id` + `Index("ix_subagent_runs_parent")` untouched.
  Proven reversible offline (upgrade 0026 → downgrade 0025 → upgrade 0026).
- **ORM**: `SubagentRun.task_id` + `SubagentRun.worker_index` nullable columns beside `tokens`/`cost`.
- **Threading (four signatures)**: `ScopedStore.record_subagent_run` and
  `KernelServices.record_subagent_run` gain `worker_index: int | None = None, task_id: str | None = None`
  (copying the existing `tokens`/`cost` two-optional-kwarg + ctor-forward pattern exactly).
- **fanout.py**: `_select_workers` now preserves `"task_id": req.get("task_id")` onto each
  selected worker dict (previously dropped at the `selected.append(...)` site); `_run_one`
  stamps `worker_index=idx, task_id=worker.get("task_id")` on the `record_subagent_run(...)`
  call — at spawn, before the crash window.
- **wave_scheduler.py**: the first-incomplete wave's `requests` now carry
  `task_id=t.id` (plan-global id); the `task_ids` list (for the `wave_runs` row) is unchanged.
- **Tests**: `test_migration_0026_is_additive` (source-assertion), `test_0026_reversible_offline`
  (alembic round-trip), and a RED→GREEN spawn-identity split — `_select_workers` preserve (×2),
  direct `ScopedStore.record_subagent_run` threading, and the wave request-dict-shape assertion.

## RED output (Task 2, observed before the change)

```
FAILED test_select_workers_preserves_task_id                        - KeyError: 'task_id'
FAILED test_select_workers_task_id_defaults_none_when_absent        - KeyError: 'task_id'
FAILED test_record_subagent_run_threads_worker_index_and_task_id    - TypeError: ScopedStore.record_subagent_run() got an unexpected keyword argument 'worker_index'
FAILED test_wave_requests_carry_task_id                             - AssertionError: a wave request is missing task_id: [{'agent': 'self', 'input': 'body-ta'}, {'agent': 'self', 'input': 'body-tb'}]
4 failed, 14 deselected
```

The wave-request RED shows the literal pre-change request dicts (no `task_id`), pinning the
`wave_scheduler.py:245` gap. `_select_workers` RED (`KeyError`) proves `:115` dropped the key.

## GREEN output

- The four new spawn-identity tests: `4 passed`.
- Full Task 2 suite + all affected fake-runner suites (`test_subagent_runs` + `test_fanout` +
  `test_wave_scheduler` + `test_merge_conflict` + `test_isolation` + `test_budget` +
  `test_fanout_cancel`): `130 passed`.
- Task 1: `test_subagent_runs.py` `14 passed` (13 prior + reversibility round-trip).

## Gate outputs (verify-by-delta against 46-VALIDATION baseline)

| Gate | Result | Baseline expectation |
|------|--------|----------------------|
| Wave gate (restart_resume + wave_scheduler + subagent_runs + fanout + fanout_cancel + sc001) | `66 passed / 1 failed` | KAN-88 (`test_waiting_for_user_run_is_rearmed_not_driven`) the SOLE fail ✓ |
| `test_restart_resume.py` alone | `8 passed / 1 failed` | 8/1 unchanged (KAN-88) ✓ |
| `test_migrations.py` | `5 passed / 2 failed` | 2 PRE-EXISTING stale-head fails (0016/0023) unchanged — NOT 3; new 0026 test green ✓ |
| Goldens `test_characterization_*.py` (SNAPSHOT_UPDATE unset) | `10 passed` | 10/10 (columns dormant on scripted runs) ✓ |
| `/opt/homebrew/bin/lint-imports` | `4 kept, 0 broken` | 4/0 ✓ |
| INV-1 grep (`pipeline_type ==|spec.id ==` in engine.py) | `0` | 0 (no new name literal) ✓ |

The two `test_migrations` stale-head fails now name head `0026` (was `0025`) because the head
advanced — that is the expected consequence of adding a migration, not a new failure; the fail
COUNT is unchanged at 2.

## Decisions

- **`task_id` keys the cursor, `worker_index` is audit-only.** `worker_index=idx` restarts at 0
  per `run_fanout` call (wave-local, ambiguous across waves); `task_id=t.id` is plan-global and
  unique — so the RESUME-09 cursor keys on `task_id` (per 46-RESEARCH "Worker→task mapping").
- **`_run_one` driven indirectly.** Per the plan's checker note, `_run_one` is a nested async
  closure inside `run_fanout` and cannot be invoked directly; the spawn→row path is pinned by a
  SPLIT — `_select_workers` (module-level) + `ScopedStore.record_subagent_run` (direct) — rather
  than an end-to-end `run_fanout` drive.
- **Left the stale `wave_scheduler.py:208-214` comment untouched.** It describes the CR-03
  whole-wave re-run behavior which this plan does NOT change (the per-task SKIP consumption is
  Plan 46-04); editing it would be scope creep. Still accurate for this plan's runtime behavior.

## Deviations from Plan

**Auto-fixed Issues**

**1. [Rule 3 - Blocking] Six fan-out test-double stubs did not accept the new kwargs.**
- **Found during:** Task 2 (after the `_run_one` call-site change).
- **Issue:** `_run_one` now passes `worker_index=idx, task_id=...` to `runner.record_subagent_run`.
  The fake `record_subagent_run` stubs in `test_fanout.py`, `test_merge_conflict.py`,
  `test_isolation.py`, `test_budget.py`, `test_fanout_cancel.py`, and the `_probe_record`
  monkeypatch wrapper in `test_sc001_fanout.py` had the old signature (no `worker_index`/`task_id`)
  → `TypeError: unexpected keyword argument`.
- **Fix:** Added `worker_index=None, task_id=None` to each fake's signature (additive, matching
  the real port). `_probe_record` also forwards both kwargs to the wrapped real method and records
  them in its probe dict, keeping the SC-001 fan-out audit probe faithful.
- **Files modified:** the six test files above.
- **Commit:** 4440e278 (folded into the Task 2 commit).

No production-code deviations — the plan executed as written for `authz.py`,
`kernel_services.py`, `fanout.py`, `wave_scheduler.py`, `subagent_run.py`, and migration 0026.

## Files

**Created:** `backend/alembic/versions/0026_subagent_task_identity.py`

**Modified (production):** `backend/app/models/subagent_run.py`, `backend/agents/authz.py`,
`backend/agents/execution_engine/kernel_services.py`,
`backend/agents/execution_engine/fanout.py`,
`backend/agents/capabilities/strategies/wave_scheduler.py`

**Modified (tests):** `backend/tests/unit/test_migrations.py`,
`backend/tests/agents/test_subagent_runs.py`, and the six fan-out fake-runner test files
(`test_fanout.py`, `test_merge_conflict.py`, `test_isolation.py`, `test_budget.py`,
`test_fanout_cancel.py`, `test_sc001_fanout.py`).

## Known Stubs

None. The two new columns are intentionally nullable/dormant on scripted and prototype/od_
golden runs (INV-3, byte/event-identical) — that is the designed RESUME-06 behavior, not a stub.
The columns are CONSUMED by Plan 46-04 (RESUME-09 skip cursor); no consumer is required this plan.

## Self-Check: PASSED

- `backend/alembic/versions/0026_subagent_task_identity.py` — FOUND
- `.planning/phases/46-per-task-substrate-cursor-live-layer-r1/46-01-SUMMARY.md` — FOUND
- commit `bac2a16c` (Task 1) — FOUND
- commit `4440e278` (Task 2) — FOUND
