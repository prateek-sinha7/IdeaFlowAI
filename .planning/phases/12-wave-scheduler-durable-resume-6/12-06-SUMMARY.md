---
phase: 12-wave-scheduler-durable-resume-6
plan: 06
subsystem: engine
tags: [wave-scheduler, mid-wave-resume, durable-resume, subagent-events, wave-index, data-loss, cross-step, duplicate-id, gap-closure]

# Dependency graph
requires:
  - phase: 12-wave-scheduler-durable-resume-6
    plan: 01
    provides: "wave_scheduler strategy + build_waves + json_tasks parser + wave_runs/subagent_runs surfaces this plan hardens"
  - phase: 12-wave-scheduler-durable-resume-6
    plan: 05
    provides: "resume_run seq seeding + workspace recovery — this plan's mid-wave resume re-entry rides the same resume path"
provides:
  - "Mid-wave resume is CORRECT for parallel waves: the first incomplete wave is re-run WHOLE (no leading-N prefix skip) so an out-of-dispatch-order parallel completion never drops an incomplete task (CR-03 / no data loss)"
  - "_completed_wave_indices is step-filtered (step == step_id) so a second wave_scheduler step resumes its OWN waves — no cross-step contamination (CR-04)"
  - "The stale pre-crash 'running' wave_runs row for the re-entered (step, wave_index) is flipped to a terminal 'superseded' status on resume, so the wave step is no longer permanently classified incomplete (WR-01)"
  - "subagent_spawned/subagent_result events carry the wave's wave_index + step (flat on event data, stamped at the strategy's run_fanout re-yield boundary) so the FE (12-07) can fold worker leaves into their wave group (CR-06 backend half)"
  - "Duplicate task ids raise a named error pre-spawn in the json_tasks parser (primary) AND in build_waves (defense-in-depth) — zero wave_runs/subagent_runs rows (WR-05)"
  - "The CR-03-followup per-task-skip deferral is recorded durably in 12-CONTEXT.md Deferred Ideas"
affects: [12-07-fe-wave-tree-panel]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Whole-in-flight-wave re-run on resume: until task identity is persisted on subagent_runs (migration 0019 carries parent_step/worker_agent/depth/isolation/status ONLY), a correct per-task skip is not derivable, so the ONLY safe behavior is to skip COMPLETED waves wholesale (step-filtered) and re-run the FIRST incomplete wave in its entirety — re-running a completed file-writer worker is idempotent (deterministic fragment overwrite), skipping an incomplete one is data loss"
    - "Step-symmetric durable reads: the completed-wave-index read filters by step == step_id, matching the sibling subagent read's parent_step == step_id filter — one wave_scheduler step never consumes another step's resume state"
    - "Free-String terminal flip without a schema change: the stale running wave_runs row is flipped to a NEW free-String 'superseded' value (the status column is free String, no sa.Enum) — additive, no migration"
    - "Event enrichment at the strategy's re-yield boundary: the wave strategy stamps wave_index + step onto the subagent_* events it re-yields, keeping run_fanout the generic flat-fanout path with no notion of waves (INV-12 single spawn home); a copy of the data dict is stamped so a shared run_fanout dict is never mutated"
    - "Defense-in-depth pre-spawn validation: untrusted agent JSON is gated at the parser (primary) AND build_waves (any other caller), both raising before any spawn"

key-files:
  created: []
  modified:
    - backend/agents/capabilities/strategies/wave_scheduler.py
    - backend/agents/capabilities/task_parsers/json_tasks.py
    - backend/tests/agents/test_restart_resume.py
    - backend/tests/agents/test_wave_scheduler.py
    - backend/tests/agents/test_json_tasks.py
    - .planning/phases/12-wave-scheduler-durable-resume-6/12-CONTEXT.md

key-decisions:
  - "CR-03 closed by whole-in-flight-wave re-run (NOT a smarter per-task skip): subagent_runs has no task_id/worker_index, so the leading-N prefix skip (wave[_remaining_completed:]) was unsafe for parallel waves where completion order != dispatch order. Deleted the _completed_worker_count tally + the slice + the _workers_seen_in_completed_waves bookkeeping; the per-task skip is the recorded CR-03-followup deferral (additive migration)."
  - "WR-01 stale-row flip uses the new free-String status 'superseded' (no sa.Enum on the status column ⇒ NOT a schema change); the flip runs on resume BEFORE record_wave_run for the re-entry, scanning the already-read _wave_rows for the (step, wave_index, running) row via ctx.runner.update_wave_run (import-pure — no store import)."
  - "CR-06 stamped at the STRATEGY re-yield boundary (preferred approach), NOT via a run_fanout kwarg fallback — run_fanout stays byte-identical for flat fan-out callers, and fanout.py is UNTOUCHED. wave_index is the wave strategy's knowledge."
  - "WR-05 gated at BOTH the parser (primary, T-12-06-INPUT untrusted agent JSON) and build_waves (defense-in-depth via len(by_id) != len(tasks)) — both raise pre-spawn."

patterns-established:
  - "Mid-wave resume safety: skip completed waves wholesale (step-filtered), re-run the in-flight wave WHOLE until task identity is durable"
  - "Strategy-side event enrichment keeps the kernel spawn path generic (INV-12)"

requirements-completed: [WAVE-03, RESUME-04]

# Metrics
duration: ~14min
completed: 2026-06-11
---

# Phase 12 Plan 06: Mid-Wave Resume Correctness + Subagent wave_index + Duplicate-id Guard Summary

**Closed the two mid-wave resume BLOCKERS in wave_scheduler.py — parallel-order data loss (CR-03: the first incomplete wave is now re-run WHOLE instead of an unsafe leading-N prefix skip that dropped incomplete parallel tasks) and cross-step contamination (CR-04: the completed-wave-index read is step-filtered) — plus the backend half of CR-06 (subagent_spawned/subagent_result now carry wave_index + step so the 12-07 FE can key worker leaves), WR-05 (duplicate task ids raise pre-spawn in the parser + build_waves), and WR-01 (the stale pre-crash running wave_runs row is flipped 'superseded' on resume). Characterization byte/event-identical with is_resuming False; lint-imports 4 kept / 0 broken; no new migration.**

## Performance
- **Duration:** ~14 min
- **Started:** 2026-06-11T11:10:00Z (approx)
- **Completed:** 2026-06-11
- **Tasks:** 3 (all TDD: RED → GREEN)
- **Files modified:** 6 (0 created, 6 modified)

## Accomplishments
- **CR-04 (cross-step contamination):** `_completed_wave_indices` now filters `getattr(r, "step", None) == step_id`, so a run with two `wave_scheduler` steps resumes the second step's waves independently of the first step's completed indices — symmetric with the sibling `parent_step == step_id` subagent filter.
- **CR-03 (parallel-order data loss):** deleted the unsafe leading-N prefix skip (`wave[_remaining_completed:]`, the `_completed_worker_count` tally, and the `_workers_seen_in_completed_waves` bookkeeping). The first incomplete wave is now re-run in its ENTIRETY — re-running a completed file-writer worker is idempotent (deterministic fragment overwrite into an isolated workspace); skipping an incomplete one was data loss. The per-task skip is recorded as the CR-03-followup deferral.
- **WR-01 (stale running row):** on resume, before recording the re-entry's `wave_runs` row, any non-terminal (`running`) row for `(step == step_id, wave_index == this index)` is flipped to a terminal `superseded` status (a new free-String value — no schema change), so `_first_incomplete_step` no longer reads the wave step as permanently incomplete.
- **CR-06 backend half:** `subagent_spawned`/`subagent_result` events re-yielded during a wave are stamped with the current `wave_index` + `step` (flat on `data`), with `run_fanout` untouched (the wave_index is stamped at the strategy's re-yield boundary).
- **WR-05 (duplicate ids):** the `json_tasks` parser raises a named `ValueError("json_tasks: duplicate task id '<id>'")` (primary gate for untrusted agent JSON); `build_waves` raises `WaveBuildError("duplicate task id")` (defense-in-depth, `len(by_id) != len(tasks)`) — both pre-spawn.

## Task Commits

Each task was committed atomically (TDD RED → GREEN):

1. **Task 1: Correct mid-wave resume (CR-04 / CR-03 / WR-01)** — `50fc7ff4` (test, RED), `34ea2fc5` (fix, GREEN — includes the CR-03-followup CONTEXT.md deferral)
2. **Task 2: Stamp wave_index + step onto re-yielded subagent_* events (CR-06 backend half)** — `979dd5f3` (test, RED), `25788514` (feat, GREEN)
3. **Task 3: Reject duplicate task ids pre-spawn (WR-05)** — `bdc65ed6` (test, RED), `4a33b83d` (fix, GREEN)

_Note: Task 1's three interlocked changes (CR-04/CR-03/WR-01) edit the same ~80-line mid-wave block and landed in one fix commit, as the plan's SCOPE NOTE sanctioned; the three distinct failing tests keep the regression surface explicit._

## FE Event Contract (for 12-07 Task 2)

The keys this plan stamps onto `subagent_spawned`/`subagent_result` event `data` — these are the EXACT keys 12-07 Task 2 reads, **flat on `data` (not nested)**:

| Key | Type | Source | Notes |
|-----|------|--------|-------|
| `wave_index` | number (int) | stamped by the wave strategy at the run_fanout re-yield boundary | the 0-based wave ordinal the worker belongs to (wave 0's workers → 0, wave 1's → 1) |
| `step` | string | stamped by the wave strategy (= `step_id`, the wave-scheduler step's `agent_id`) | lets the FE key by `step:wave_index` |
| `worker` | number (int) | emitted by `fanout.py` (UNCHANGED) | the per-wave worker index; NOT renamed, NOT nested |

The FE must read these flat off `data` (e.g. `data.wave_index`, `data.step`, `data.worker`). `wave_index` is NOT added to the `subagent_runs` DB row (that is the deferred CR-03-followup task-identity migration) — this plan adds it to the EVENT stream only.

## Files Created/Modified
- `backend/agents/capabilities/strategies/wave_scheduler.py` — step-filtered `_completed_wave_indices` (CR-04); deleted the prefix skip → whole-in-flight-wave re-run (CR-03); stale-row `superseded` flip on resume (WR-01); `wave_index` + `step` stamped onto re-yielded `subagent_*` events (CR-06); `build_waves` duplicate-id guard `len(by_id) != len(tasks)` (WR-05 defense-in-depth).
- `backend/agents/capabilities/task_parsers/json_tasks.py` — named `ValueError` duplicate-id check before the depends_on validation (WR-05 primary gate).
- `backend/tests/agents/test_restart_resume.py` — 3 new tests: `test_midwave_resume_reruns_whole_inflight_wave_no_parallel_dropout` (CR-03, strategy-level whole-wave re-run), `test_cross_step_does_not_skip_second_steps_waves` (CR-04), `test_stale_running_wave_row_is_flipped_terminal_on_resume` (WR-01); + a `plan=` override on `_ResumeHarness`.
- `backend/tests/agents/test_wave_scheduler.py` — `test_subagent_events_carry_wave_index_and_step` (CR-06) + `test_build_waves_rejects_duplicate_task_id_before_any_wave` (WR-05).
- `backend/tests/agents/test_json_tasks.py` — `test_duplicate_task_id_raises_named_valueerror` (WR-05).
- `.planning/phases/12-wave-scheduler-durable-resume-6/12-CONTEXT.md` — CR-03-followup per-task-skip deferral recorded under `## Deferred Ideas`.

## Decisions Made
- **CR-03 = whole-wave re-run, not per-task skip:** `subagent_runs` carries no task identity (migration 0019: `parent_step/worker_agent/depth/isolation/status` only), so the prefix-by-count skip was unsafe for parallel waves. The safe, correct behavior until task identity is durable is to re-run the in-flight wave whole (idempotent for file-writer workers). The per-task skip is the recorded CR-03-followup deferral.
- **WR-01 stale-row flip = free-String `superseded`:** the status column is free String (no `sa.Enum`), so a new terminal value is additive — NOT a schema change. The flip runs on resume before `record_wave_run`, via `ctx.runner.update_wave_run` (import-pure).
- **CR-06 = strategy-side interception (preferred):** the wave strategy stamps `wave_index`/`step` at its re-yield boundary; `run_fanout` and `fanout.py` are untouched, so flat fan-out events stay byte-identical and the kwarg fallback was not needed.

## Deviations from Plan

None — plan executed exactly as written. Task 1's three changes landed in one fix commit, which the plan's SCOPE NOTE explicitly sanctioned (they edit the same mid-wave block and share the same `_wave_rows` read).

## Issues Encountered
- **CR-03 test design:** an initial full-engine attempt to reproduce CR-03 via partial parallel completion was non-deterministic — `run_fanout` yields all `subagent_result` events only AFTER the full parallel gather (so workers cannot be crashed "between" each other), and per-worker failures inside `_run_one` are absorbed (the wave still completes), so neither path leaves a genuinely partial in-flight wave with the right durable shape. Resolved by testing CR-03 at the STRATEGY boundary with a fake runner that reports the exact durable state (wave 0 completed, wave 1 in-flight with terminal subagent rows that — per parallel semantics — are NOT the leading tasks by dispatch order), asserting the WHOLE in-flight wave is re-fanned-out. This mirrors the CR-04/WR-01 strategy-level approach and is deterministic. The existing full-engine `test_midwave_resume_does_not_reinvoke_completed_workers` still passes (completed waves are not re-invoked).

## Verification Evidence
- `pytest test_wave_scheduler.py test_json_tasks.py test_restart_resume.py test_wave_runs.py test_sample_wave_workflow.py test_subagent_runs.py test_characterization_*.py test_banned_patterns.py test_migration_ledger.py` → **96 passed, 7 skipped** (10 characterization snapshots byte/event-identical with `SNAPSHOT_UPDATE` unset).
- `/opt/homebrew/bin/lint-imports` → **4 kept / 0 broken** (strategy stays import-pure — reads/writes via `ctx.runner`, never the store).
- `grep -n "_remaining_completed" wave_scheduler.py` → **no match** (the unsafe prefix skip is removed).
- `grep -n "step.*==.*step_id" wave_scheduler.py` → the `_completed_wave_indices` comprehension is step-filtered.
- `grep -n "superseded" wave_scheduler.py` → the stale-row terminal flip is present.
- `grep -n "CR-03-followup" 12-CONTEXT.md` → **1 match** under `## Deferred Ideas`.
- `grep -ni "duplicate" json_tasks.py` + `grep -n "len(by_id) != len(tasks)" wave_scheduler.py` → both duplicate-id guards present.
- No new alembic migration (`git diff` over the plan commits touches no `alembic/`).

## Threat Model Outcomes
- **T-12-06-INPUT (Tampering, mitigate):** duplicate ids raise pre-spawn in the parser (primary) + build_waves (defense-in-depth) — zero wave_runs/subagent_runs rows; untrusted agent JSON cannot drive negative in-degrees or silently drop a task.
- **T-12-06-DATALOSS (Tampering/Repudiation, mitigate):** the in-flight wave is re-run WHOLE on resume — an incomplete task can never be silently dropped while the wave is marked completed; re-running a completed file-writer worker is idempotent.
- **T-12-06-CROSSSTEP (Information Disclosure, mitigate):** the completed-wave-index read is step-filtered (`step == step_id`), owner+workspace-scoped via ctx.runner.
- **T-12-06-EVENT (Information Disclosure, accept):** `wave_index`/`step` are non-sensitive scheduling ordinals on the existing owner-scoped run stream.
- **T-12-06-SC (Tampering, mitigate):** zero new packages (stdlib only); import-linter 4 kept / 0 broken; banned-pattern unaffected.

## Threat Flags
None — no new security surface beyond the plan's threat model. The only new write is the `update_wave_run(..., status="superseded")` flip, which rides the existing owner+workspace-scoped recorder.

## Next Phase Readiness
- 12-07 (FE wave/subagent tree panel) can now key worker leaves to their wave: the backend emits `data.wave_index` (number) + `data.step` (string) + `data.worker` (number), flat, on `subagent_spawned`/`subagent_result` (the contract table above).
- Mid-wave resume is correct for parallel waves; the WAVE-03 / RESUME-04 mid-wave BLOCKERS (CR-03/CR-04/WR-01) and the CR-06 backend half are closed.

## Self-Check: PASSED

All modified files exist on disk; all 6 task commits (`50fc7ff4`, `34ea2fc5`, `979dd5f3`, `25788514`, `bdc65ed6`, `4a33b83d`) are present in the git log.

---
*Phase: 12-wave-scheduler-durable-resume-6*
*Completed: 2026-06-11*
