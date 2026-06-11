---
phase: 12-wave-scheduler-durable-resume-6
plan: 01
subsystem: api
tags: [wave-scheduler, topological-sort, json-tasks, alembic, scoped-store, fan-out, sc-001]

# Dependency graph
requires:
  - phase: 11-fan-out-merge
    provides: "the single kernel run_fanout spawn path + subagent_runs persistence recipe + ScopedStore default-deny pattern + KernelServices best-effort recorders"
  - phase: 04-manifest-compiler
    provides: "CompiledWorkflow/Step/TaskSource/FanoutSpec typed model + compile_for_run manifest loading"
provides:
  - "wave_scheduler strategy (user_allowed=True) + pure build_waves topological seam (WaveBuildError pre-spawn)"
  - "json_tasks structured task parser (depends_on/conflict_keys/targets) — the wave default parser"
  - "additive 0020 wave_runs persistence (migration + WaveRun ORM + default-deny ScopedStore writer/updater/reader + best-effort KernelServices recorders)"
  - "wave_started/wave_completed/wave_failed lifecycle events (single emit boundary, zero websocket edits)"
  - "sample_wave SC-001 proof workflow (manifest + AGENT.md only, zero engine edits)"
affects: [12-02-retry, 12-03-durable-resume, 12-04-frontend]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure stdlib Kahn-levels wave builder with stable tie-break + within-level conflict-key split (targets default to conflict_keys)"
    - "wave_runs persistence cloned verbatim from the subagent_runs recipe (additive migration + ORM + default-deny ScopedStore + None-degrading KernelServices recorder)"
    - "Migration reversibility tests pinned to explicit revisions (not head/-1) so they survive later additive migrations"

key-files:
  created:
    - backend/agents/capabilities/strategies/wave_scheduler.py
    - backend/agents/capabilities/task_parsers/json_tasks.py
    - backend/alembic/versions/0020_wave_runs.py
    - backend/app/models/wave_run.py
    - backend/agents/workflows/sample_wave/workflow.yaml
    - backend/tests/agents/fixtures/sample_wave/sample-wave-plan/AGENT.md
    - backend/tests/agents/fixtures/sample_wave/sample-wave-worker/AGENT.md
    - backend/tests/agents/test_wave_scheduler.py
    - backend/tests/agents/test_json_tasks.py
    - backend/tests/agents/test_wave_runs.py
    - backend/tests/agents/test_sample_wave_workflow.py
  modified:
    - backend/agents/authz.py
    - backend/agents/execution_engine/kernel_services.py
    - backend/agents/capabilities/registry.py
    - backend/app/models/__init__.py
    - specs/003-workflow-engine-decoupling/migration-ledger.md
    - backend/tests/agents/test_registry_capabilities.py
    - backend/tests/agents/test_migration_ledger.py
    - backend/tests/agents/test_subagent_runs.py

key-decisions:
  - "conflict_keys defaults to targets when empty (documented Pitfall-6 default): disjoint targets => same wave, same target => split"
  - "json_tasks fence extraction finds a fenced json block WITHIN surrounding prose (not just a leading strip), so an agent's prose-wrapped plan still parses"
  - "0019/0020 reversibility tests pinned to explicit revisions so the additive 0020 chain does not false-fail the 0019 head/-1 round-trip (Rule 1 regression fix)"

patterns-established:
  - "Pattern: build_waves(tasks)->list[list[Task]] pure topo-sort seam (the CP-SAT replacement point) — validate refs + cycle pre-spawn, Kahn levels, conflict-key spill"
  - "Pattern: each executed wave funnels through the UNMODIFIED kernel run_fanout (INV-12 single spawn path) so isolation/merge/budget/cancellation are inherited per wave"

requirements-completed: [WAVE-01, WAVE-02, WAVE-03]

# Metrics
duration: ~30min
completed: 2026-06-11
---

# Phase 12 Plan 01: Wave Scheduler Foundation Summary

**A registered wave_scheduler strategy with a pure build_waves topological seam, a json_tasks structured parser, additive 0020 wave_runs persistence, and a manifest-only sample_wave SC-001 proof — all with the 5 characterization snapshots byte/event-identical.**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-06-11T08:58:00Z
- **Completed:** 2026-06-11T09:10:00Z
- **Tasks:** 3
- **Files modified:** 19 (11 created, 8 modified)

## Accomplishments
- `wave_scheduler` strategy (user_allowed=True) topo-sorts a `json_tasks` plan into deterministic waves and runs each wave through one `run_fanout` call; `build_waves` raises `WaveBuildError` pre-spawn on a cycle or unknown `depends_on` ref (zero rows).
- `json_tasks` parser carries the forward scheduling surface (depends_on/conflict_keys/targets); tolerates plain array / fenced ```json (even amid prose) / `{"tasks": [...]}` wrapper; malformed JSON + unknown-dep raise named ValueErrors.
- Additive `0020 wave_runs` (reversible offline, single 0019→0020 head, free-String status, named FK) + `WaveRun` ORM + default-deny `ScopedStore.record_wave_run`/`update_wave_run`/`read_wave_runs` (cross-owner read = ∅, update = no-op; T-12-01-IDOR) + None-degrading `KernelServices.record_wave_run`/`update_wave_run`.
- `sample_wave` SC-001 proof: a brand-new manifest+AGENT.md workflow runs 4 tasks in ≥2 waves (≥2 parallel workers in wave 1), merged `copy_disjoint`, with zero engine edits.
- Registry `_KNOWN` lockstep 59→61; migration-ledger `WAVE-PERSIST` CHECK row added + ratchets flipped; 5 characterization snapshots byte/event-identical (waves dormant for existing workflows).

## Task Commits

Each task was committed atomically:

1. **Task 1: json_tasks parser + wave_scheduler strategy with pure build_waves seam** - `ecdf7e6` (feat, TDD test+impl)
2. **Task 2: 0020 wave_runs migration + WaveRun ORM + default-deny ScopedStore + ledger/lockstep ratchets** - `e415d09` (feat)
3. **Task 3: KernelServices wave recorders + wave events + sample_wave SC-001 proof** - `63638f4` (feat)

**Deviation fix:** `13e7b26` (fix: pin migration reversibility tests to explicit revisions)

## Files Created/Modified
- `backend/agents/capabilities/strategies/wave_scheduler.py` - wave_scheduler strategy + pure build_waves + WaveBuildError
- `backend/agents/capabilities/task_parsers/json_tasks.py` - structured JSON task parser (depends_on/conflict_keys/targets)
- `backend/alembic/versions/0020_wave_runs.py` - additive wave_runs migration (down_revision 0019)
- `backend/app/models/wave_run.py` - WaveRun ORM on Base.metadata
- `backend/agents/authz.py` - ScopedStore wave_runs writer/updater/reader (default-deny)
- `backend/agents/execution_engine/kernel_services.py` - best-effort record_wave_run/update_wave_run handles
- `backend/agents/capabilities/registry.py` - _KNOWN + discover() add the two wave capabilities
- `backend/app/models/__init__.py` - register WaveRun on Base.metadata
- `specs/003-workflow-engine-decoupling/migration-ledger.md` - WAVE-PERSIST CHECK row
- `backend/agents/workflows/sample_wave/workflow.yaml` + 2 AGENT.md fixtures - SC-001 sample wave workflow
- `backend/tests/agents/test_wave_scheduler.py`, `test_json_tasks.py`, `test_wave_runs.py`, `test_sample_wave_workflow.py` - new suites
- `backend/tests/agents/test_registry_capabilities.py`, `test_migration_ledger.py`, `test_subagent_runs.py` - ratchet/reversibility updates

## Decisions Made
- `conflict_keys` defaults to `targets` when empty (documented Pitfall-6 default) — keeps two tasks writing the same file out of the same wave without the manifest restating it.
- `json_tasks` fence extraction searches for a fenced block WITHIN surrounding prose (regex), so an agent's "Here is the plan: ```json … ```" output still parses.
- Reversibility tests pinned to explicit revisions instead of `head`/`-1`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Pinned migration reversibility tests to explicit revisions**
- **Found during:** Task 3 (post-Task-2 regression surfaced in the fanout regression sweep)
- **Issue:** `test_subagent_runs.py::test_0019_reversible_offline` used `upgrade head` → `downgrade -1`, which assumed 0019 was the alembic head. The additive 0020 wave_runs migration chains after 0019, so `head`/`-1` now lands on 0019 (subagent_runs still present) and the test false-failed.
- **Fix:** Pinned both the 0019 and 0020 reversibility tests to explicit revisions (0019↔0018, 0020↔0019) so each proves its own additive step is reversible regardless of later migrations.
- **Files modified:** backend/tests/agents/test_subagent_runs.py, backend/tests/agents/test_wave_runs.py
- **Verification:** `pytest test_subagent_runs.py test_wave_runs.py test_exec_runs.py` → 27 passed
- **Committed in:** 13e7b26

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** The fix was a test-only correction of a stale head assumption my own additive migration exposed. No production-code or scope change.

## Issues Encountered
- The Task-3 E2E first failed because the scripted planner wrapped its JSON plan in prose ("Here is the plan:") before the fence — `json_tasks` only stripped a *leading* fence. Resolved by making fence extraction find a fenced block anywhere in the text (also a strict improvement for real prose-wrapping agents). Covered by `test_json_tasks.py::test_tolerates_fenced_json_block`.

## User Setup Required
None - no external service configuration required (stdlib-only build_waves; additive migration; zero new packages).

## Next Phase Readiness
- The durable `wave_runs` substrate is in place for the 12-03 mid-wave resume (read ordered by wave_index).
- `RetryPolicy.on` / engine retry wrapper (12-02) and the FE WaveTreePanel (12-04) can build on the wave lifecycle events.
- No blockers.

## Threat Flags
None - the new surface (wave_runs reads/writes, json_tasks input) is covered by the plan's threat model (T-12-01-IDOR mitigated via owner+workspace scoping; T-12-01-INPUT mitigated via named ValueError/WaveBuildError pre-spawn).

## Self-Check: PASSED

---
*Phase: 12-wave-scheduler-durable-resume-6*
*Completed: 2026-06-11*
