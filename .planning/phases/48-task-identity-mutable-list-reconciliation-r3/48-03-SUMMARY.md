---
phase: 48-task-identity-mutable-list-reconciliation-r3
plan: 03
subsystem: infra
tags: [execution-engine, resume, reconciliation, wave-scheduler, orphan-exclusion, sc001, update-specs]

# Dependency graph
requires:
  - phase: 48-01
    provides: "task_identity primitives, _compute_upstream_context_hash single home + runner.upstream_context_hash handle, content-addressed wave requests[].task_id + subagent_runs.task_id keys"
  - phase: 48-02
    provides: "_compute_resume_completed_task_ids (set, completed_ordered) cursor, _compute_cumulative_boundaries, three-state boundary re-materialization relocated to the post-compile resume hook, task_identity.common_prefix_length"
  - phase: 46-per-task-capture-resume
    provides: "_rematerialize_artifacts_to_disk, write_fragment_artifact (kind=file_bundle, task_id=str(worker_index)), read_subagent_runs"
provides:
  - "RESUME-16 independent: wave orphan-fragment exclusion at the re-materialization gate via wave_allow_by_step + the three-way fragment->key join (restore-if-in-allow-set / exclude-if-mappable-but-absent / fail-safe-restore-if-unresolvable-or-ambiguous); merge/assembly impls untouched, no row deleted"
  - "RESUME-16 independent: _compute_wave_orphan_allowsets reconciler (per wave-step current-key set from the max-version list) wired into the _is_resume re-materialization hook"
  - "RESUME-16 rotation proof: update_specs spec-v2 rotates every build task_key -> all build tasks re-run, no v1-key skipped (no new production code; rotation is generic)"
  - "SC-001 proof: a synthetic NON-prototype task_loop workflow drives the full complete->edit->resume reconcile with exact re-run set + orphan exclusion and ZERO engine name-literals"
affects: [resume, reconciliation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Read-side orphan exclusion: a confidently-orphaned (mappable-but-absent) wave fragment is gated out at the single re-materialization upstream point (never merged/assembled) with zero merge-impl edits and zero row mutation"
    - "Three-way durable-join with fail-safe RESTORE on ambiguity (worker_index->key via subagent_runs; unresolvable OR multi-key => keep)"
    - "Composition-by-substrate proof: a spec-v2 write rotates the upstream namespace so every dependent key rotates — proven with real engine primitives, no bespoke branch (INV-12)"

key-files:
  created:
    - backend/tests/agents/test_sc001_reconcile.py
  modified:
    - backend/agents/execution_engine/engine.py
    - backend/tests/agents/test_restart_resume.py

key-decisions:
  - "Orphan gate keyed on the fragment's producer_step (== the wave step agent id), NOT producer_agent (which for a fragment is the worker_agent); the boundary gate stays keyed on producer_agent — the two selectors are orthogonal and coexist"
  - "The fragment->key join reads subagent_runs INSIDE _rematerialize_artifacts_to_disk (it already holds the scoped_store); the reconciler supplies only the current-key allow-set — keeps the join self-contained + directly testable"
  - "EXCLUDE only on an UNAMBIGUOUS worker_index->key resolution whose key is absent from the allow-set; a missing OR multi-key (wave-local ambiguity) resolution folds into fail-safe RESTORE (T-48-05)"
  - "The SC-001 reconcile proof drives the strategy + kernel seams directly (deterministic, offline) over the sc001_task_loop fixture's declared names (app.py / sc001-plan / sc001-build) rather than a full engine.execute resume — the reconcile logic is what is under test and the name-freedom grep is engine-package-wide"

patterns-established:
  - "wave_allow_by_step allow-set on re-materialization (independent) alongside boundary_by_agent (cumulative) — one gate, two orthogonal selectors, both dormant by default"

requirements-completed: [RESUME-16]

# Metrics
duration: 55min
completed: 2026-07-19
---

# Phase 48 Plan 03: Wave Orphan Exclusion + update_specs Compose + SC-001 Reconcile Proof Summary

**Delivered the independent (wave) half of RESUME-16 — orphan-fragment exclusion at the re-materialization gate via a three-way fragment→key join (restore / exclude-if-mappable-but-absent / fail-safe-restore-if-unresolvable), merge & assembly impls untouched and no row mutated — plus the update_specs rotation compose proof and the SC-001 synthetic non-prototype reconcile proof (exact re-run set + orphan exclusion, zero engine name-literals), all byte-neutral on 10/10 goldens.**

## Performance

- **Duration:** ~55 min
- **Started:** 2026-07-19
- **Completed:** 2026-07-19
- **Tasks:** 3 (all TDD; Task 1 RED→GREEN, Tasks 2+3 proof tests GREEN on the landed substrate)
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments
- **RESUME-16 independent (Task 1):** `_rematerialize_artifacts_to_disk` gains an optional `wave_allow_by_step` allow-set; a `file_bundle` fragment whose `producer_step` is a wave step is gated by the three-way join — its `task_id`(==`str(worker_index)`) → the owning worker's `subagent_runs.task_id`(==key): (1) unambiguously in the allow-set → RESTORE, (2) unambiguously absent (confidently orphaned) → EXCLUDE (not restored → never reaches `_merge_fragments` nor `serialized_sandbox`), (3) unresolvable/ambiguous → RESTORE (fail-safe keep). `_compute_wave_orphan_allowsets` computes the per-wave-step current-key set from the max-version list (json_tasks default), emitted only for steps with completed work, and is wired into the `_is_resume` re-materialization hook. Merge/assembly impls untouched; `write_fragment_artifact` (Site C) untouched; no row deleted.
- **RESUME-16 rotation (Task 2):** `test_update_specs_reconcile_composes` proves — with **no new production code** — that a spec-v2 write rotates the build step's `_compute_upstream_context_hash`, so every build `task_key` rotates, `common_prefix_length == 0`, every build task re-runs, and no v1-completed key is skipped. The rotation is generic (no bespoke update_specs branch — INV-12).
- **SC-001 (Task 3):** `test_sc001_reconcile.py` drives the synthetic NON-prototype `task_loop` workflow (deliverable `app.py`; declared `sc001-plan`/`sc001-build`) through complete-2-of-4 → gate-edit (delete-completed Bravo + edit-pending Charlie + add Echo) → resume: the strategy re-runs EXACTLY the divergence suffix `[2,3,4]` and skips the surviving prefix task; the kernel reconciler (`_compute_cumulative_boundaries` → re-materialize) excludes the deleted-completed task's `app.py` version from both the next task's on-disk context basis and the assembled deliverable; and the two-part acceptance holds (registry.is_registered all True + engine-package grep of `sc001`/`pipeline_type ==`/`spec.id ==` all zero).

## Task Commits

1. **Task 1: wave orphan-fragment exclusion (three-way join)** — `81e71732` (feat, TDD RED→GREEN)
2. **Task 2: update_specs rotation composes** — `8501ef54` (test, GREEN on the substrate)
3. **Task 3: SC-001 synthetic reconcile proof** — `e4f0ddaa` (test, GREEN)

_Task 1 TDD RED observed: both wave tests failed with `TypeError: unexpected keyword argument 'wave_allow_by_step'` before the engine param landed. Tasks 2+3 are proof/regression tests the plan specifies as GREEN-on-substrate (the composition + name-freedom fall out of 48-01/48-02); each asserts a non-trivial rotation/exclusion the substrate genuinely provides._

## Files Created/Modified
- `backend/tests/agents/test_sc001_reconcile.py` — SC-001 synthetic non-prototype reconcile proof (exact re-run set over app.py; kernel orphan exclusion; two-part name-freedom acceptance)
- `backend/agents/execution_engine/engine.py` — `_rematerialize_artifacts_to_disk` gains `wave_allow_by_step` + the three-way fragment→key join (subagent_runs worker_index→key map built once, default-deny); `_compute_wave_orphan_allowsets` reconciler; wired into the `_is_resume` hook (fail-safe empty allow-set on failure)
- `backend/tests/agents/test_restart_resume.py` — `test_wave_reconcile_orphan_excluded`, `test_wave_reconcile_unmappable_kept` (the two DISTINCT three-way cases), `test_update_specs_reconcile_composes`

## Decisions Made
- **Orphan gate keyed on `producer_step`.** A fragment's `producer_agent` is the worker_agent (not the wave step), but its `producer_step` IS the wave step agent id — so `wave_allow_by_step` and the join map are keyed on `producer_step`. This is orthogonal to the cumulative `boundary_by_agent` (keyed on `producer_agent` for the task_loop html_file), so both selectors coexist in one loop without interference.
- **Ambiguity folds into fail-safe RESTORE.** A wave-local `worker_index` can (rarely) resolve to >1 key across waves within a step; the join records a `set` and EXCLUDES only on `len==1` with the sole key absent from the allow-set. No mapping OR multi-key → RESTORE (T-48-05: a wasteful-but-correct keep, never a wrong exclude of live work).
- **The join reads subagent_runs inside re-materialization.** The reconciler supplies only the current-key allow-set (its territory: parse + upstream hash); the gate owns the durable worker_index→key join (it already holds `scoped_store`). Only read when an allow-set is supplied → the default path never touches subagent_runs → byte-identical/dormant.

## Deviations from Plan

None — plan executed exactly as written. All three tasks landed with the pinned three-way join, the two DISTINCT wave test cases (`orphan_excluded` vs `unmappable_kept`), the update_specs compose proof with zero new production code, and the SC-001 synthetic proof with zero engine name-literals. `_merge_fragments`, the `serialized_sandbox` resolver, `write_fragment_artifact` (Site C), and the INV-12 single upstream-scan home were all left untouched.

## Known Stubs

None — no placeholder/empty-value stubs introduced. All new code paths are exercised by passing tests.

## Issues Encountered
- None. The `boundary_by_agent`/`wave_allow_by_step` orthogonality (producer_agent vs producer_step keying) was confirmed by reading `write_fragment_artifact` (producer_step = wave step, producer_agent = worker) before wiring, avoiding a mis-keyed gate.

## Verification (verify-by-delta against the 48-VALIDATION baseline)
- RESUME-16 independent: `-k "reconcile_orphan_excluded or reconcile_unmappable or update_specs_reconcile_composes"` — **3 passed**
- SC-001 proof: `test_sc001_reconcile.py` (3) + `test_sc001_nonprototype_task_loop.py` + `test_sc001_fanout.py` + `test_banned_patterns.py` — **20 passed**; `grep -rc sc001 agents/execution_engine/` == **0**
- Delta floor: restart_resume + wave_scheduler + subagent_runs + per_task_capture + json_tasks — **68 passed / 1 failed** (KAN-88 `test_waiting_for_user_run_is_rearmed_not_driven` = SOLE pre-existing red, untouched); wave **10**, subagent **18**, per_task_capture **4**, json **12** all held
- Goldens (5 characterization files, `SNAPSHOT_UPDATE` unset) — **10 passed** (INV-3 dormancy across the wave allow-set wiring)
- redo_gate_safety — **4 passed / 3 failed** (pre-existing scripted-model harness drift, held — not this phase)
- INV-1: `grep -cE 'pipeline_type ==|spec.id ==' engine.py` → **0**; INV-12: `grep -c 'def _compute_upstream_context_hash' engine.py` → **1**, single produces∩consumes scan-token → **1**
- `write_fragment_artifact` still `task_id=str(worker_index)` (Site C untouched); lint-imports → **4 kept / 0 broken**

## Next Phase Readiness
- RESUME-16 is fully delivered across 48-01/48-02/48-03 (skip / run / exclude for both cumulative and independent flows); RESUME-14 and RESUME-15 landed in 48-01/48-02. The SC-001 core-value obligation (SC4 proof) is discharged. KAN-88 (`waiting_for_user` re-arm) remains the sole restart red — the Phase-49 anchor. No blockers.

## Self-Check: PASSED

- Files exist: test_sc001_reconcile.py, 48-03-SUMMARY.md — verified below
- Commits exist: 81e71732, 8501ef54, e4f0ddaa — verified below

---
*Phase: 48-task-identity-mutable-list-reconciliation-r3*
*Completed: 2026-07-19*
