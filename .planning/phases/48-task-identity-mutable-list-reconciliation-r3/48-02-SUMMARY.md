---
phase: 48-task-identity-mutable-list-reconciliation-r3
plan: 02
subsystem: infra
tags: [execution-engine, resume, reconciliation, task-identity, gate-edit, derived-from, common-prefix]

# Dependency graph
requires:
  - phase: 48-01
    provides: "task_identity primitives (normalize/ordinal/compute_task_key), _compute_upstream_context_hash single home + runner.upstream_context_hash handle, content-addressed task_key write-path, key-consistent task_loop skip"
  - phase: 46-per-task-capture-resume
    provides: "_compute_resume_completed_task_ids cursor, _rematerialize_artifacts_to_disk, persist_task_html capture seam"
  - phase: 23-durable-resume
    provides: "_dual_write_artifact derived_from param + _latest_typed_content max-version read; redo path derived_from idiom"
provides:
  - "RESUME-15 gate-Edit lineage: derived_from stamped at ALL THREE task_list-minting gate-edit writes (inline KAN-101 re-open + inline main review gate + declared) via the new _latest_typed_ref_id max-version resolver"
  - "RESUME-16 cumulative: _compute_resume_completed_task_ids now returns (set, completed_ordered); task_loop skip is the ORDER-based common-prefix rule (task_identity.common_prefix_length, one home)"
  - "RESUME-16 cumulative: three-state boundary re-materialization (global-max / boundary-version p>0 / restore-nothing p==0) driven by _compute_cumulative_boundaries; re-materialization relocated to the post-compile resume hook"
affects: [48-03-reconciler-waves-sc001, resume, reconciliation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Common-prefix cumulative reconcile: skip the longest matching PREFIX in order, re-run the divergence suffix (never set-membership for task_loop)"
    - "Three-state boundary selector on re-materialization (None/global-max vs p>0 boundary-version vs p==0 restore-nothing) — None never overloaded to mean restore-nothing"
    - "gate-Edit derived_from lineage via a max-version ref-id resolver, mirroring the redo path idiom"

key-files:
  created:
    - backend/tests/agents/test_task_list_gate_lineage.py
  modified:
    - backend/agents/execution_engine/engine.py
    - backend/agents/capabilities/task_identity.py
    - backend/agents/capabilities/strategies/task_loop.py
    - backend/agents/execution_engine/context.py
    - backend/tests/agents/test_restart_resume.py
    - backend/tests/agents/test_task_identity.py

key-decisions:
  - "Stamped derived_from at THREE physical gate-edit writes (not the 2 the plan named): the inline _gate_edited handler exists TWICE in _run_agent (KAN-101 re-open :2968 + main review gate :3805) and the NORMAL inline edit path is :3805 — stamping only the plan's :2968+declared would leave the primary edit path without lineage"
  - "Relocated the _is_resume re-materialization from the pre-compile hydrate hook (:1383) to the post-compile/post-cursor point: the RESUME-16 boundary needs compiled steps + ordered_agents + ectx.runner (upstream hash) + the ordered cursor, none of which exist at :1383 (which precedes compile_for_run :1430)"
  - "Emit a cumulative boundary ONLY on a real divergence (p < len(completed)): for a non-edited resume global-max already equals the boundary version (the last completed task), so the default global-max path stays byte-identical"
  - "One home for the common-prefix rule: task_identity.common_prefix_length, called by BOTH the task_loop skip AND the engine boundary reconciler (no parallel implementation)"

patterns-established:
  - "Cumulative common-prefix reconcile (order-diff), distinct from wave per-key set-membership"
  - "Boundary re-materialization single home threaded from a reconciler; fail-safe = default global-max on any compute failure"

requirements-completed: [RESUME-15, RESUME-16]

# Metrics
duration: 75min
completed: 2026-07-19
---

# Phase 48 Plan 02: Cumulative Reconciler + Gate-Edit Lineage Summary

**Closed the RESUME-15 `derived_from` lineage gap at all three gate-Edit write sites, and delivered the cumulative half of RESUME-16 — an order-based common-prefix `task_loop` skip plus three-state boundary re-materialization (boundary-version for p>0, restore-nothing for p==0) — proven byte-neutral on 10/10 goldens.**

## Performance

- **Duration:** ~75 min
- **Started:** 2026-07-19
- **Completed:** 2026-07-19
- **Tasks:** 3 (all TDD RED→GREEN)
- **Files modified:** 6 (1 created, 5 modified)

## Accomplishments
- **RESUME-15:** new `_latest_typed_ref_id` max-version resolver; `derived_from` stamped at all three task_list-minting gate-edit writes (inline KAN-101 re-open, inline main review gate, declared `_apply_declared_gate_edit`) — resolved BEFORE each write (== prior max). None on a first-ever write ⇒ byte-identical (goldens dormant).
- **RESUME-16 cumulative cursor + skip:** `_compute_resume_completed_task_ids` now returns `(set, completed_ordered)` (ordered by `min(version)` per task_id = build order); `task_identity.common_prefix_length` is the single home of the prefix rule; the `task_loop` skip switched from set-membership to the ORDER-based common-prefix rule (skip index `< p`, re-run the divergence suffix; `p==0` runs every task).
- **RESUME-16 cumulative re-materialization:** three-state `boundary_by_agent` selector on `_rematerialize_artifacts_to_disk` (None→global-max / p>0→boundary task's max-version file / p==0→restore-nothing, never a negative-index restore); `_compute_cumulative_boundaries` reconciler computes it from the ordered cursor + the current parsed list using the strategy's own upstream hash; re-materialization relocated to the post-compile resume hook where that data exists.

## Task Commits

1. **Task 1: RESUME-15 gate-Edit derived_from** — `3681d102` (feat, TDD RED→GREEN)
2. **Task 2: RESUME-16 ordered cursor + common-prefix skip** — `f6e63b1c` (feat, TDD RED→GREEN)
3. **Task 3: RESUME-16 boundary-version re-materialization (incl. p==0)** — `05f59abb` (feat, TDD RED→GREEN)

_TDD RED observed failing before each GREEN: derived_from==None for T1; dispatch [1,2] vs [2] + tuple-unpack AttributeError for T2; `boundary_by_agent` TypeError for T3._

## Files Created/Modified
- `backend/tests/agents/test_task_list_gate_lineage.py` — RESUME-15 lineage proof (declared + inline gate-edit paths; v2.derived_from == v1.id + max-version re-parse)
- `backend/agents/execution_engine/engine.py` — `_latest_typed_ref_id`; derived_from at 3 gate-edit sites; cursor `(set, completed_ordered)` return; three-state `boundary_by_agent` on `_rematerialize_artifacts_to_disk`; `_compute_cumulative_boundaries` reconciler; re-materialization relocated to the post-compile/post-cursor `_is_resume` hook; `task_identity` import
- `backend/agents/capabilities/task_identity.py` — `common_prefix_length` (single home of the cumulative prefix rule)
- `backend/agents/capabilities/strategies/task_loop.py` — common-prefix skip (`_prefix_skip = common_prefix_length(...)`, index-based) replacing set-membership
- `backend/agents/execution_engine/context.py` — `resume_completed_ordered` field
- `backend/tests/agents/test_restart_resume.py` — `test_task_loop_reconcile_common_prefix`, `test_task_loop_reconcile_first_task_divergence_runs_all`, `test_task_loop_reconcile_boundary_version`, `test_task_loop_reconcile_first_task_clean_basis`; existing skip test re-seeded to the ordered cursor; cursor test unpacks the tuple + asserts `completed_ordered`
- `backend/tests/agents/test_task_identity.py` — 5 pure `common_prefix_length` cases

## Decisions Made
- **One home for the prefix rule.** `task_identity.common_prefix_length` is called by BOTH the strategy skip AND the engine boundary reconciler — no parallel implementation (INV-12). The boundary KEY at index `p-1` equals `completed_ordered[p-1]` by the common-prefix definition, and for `p==0` the reconciler emits an explicit `restore_nothing` signal so no caller ever indexes `current_keys[-1]`.
- **Divergence-gated boundary emission.** A boundary is emitted only when `p < len(completed_ordered)` (a completed task exists AFTER the boundary). For a non-edited resume the global-max html_file IS the last completed task's version = the boundary version, so the default path stays byte-identical — the three-state selector's "None → global-max" case covers every non-cumulative / non-edited resume.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Required for correctness] Stamped derived_from at the THIRD (primary) inline gate-edit write, not just the two the plan named**
- **Found during:** Task 1
- **Issue:** The plan/PATTERNS named two gap sites (`_gate_edited` :2971-2979 + declared `_apply_declared_gate_edit` :4566-4575). But the inline `_gate_edited` handler exists TWICE in `_run_agent`: :2968 (the KAN-101 spec-revision gate RE-OPEN, fires only when `spec_revision_pending_output` is set) and :3805 (the NORMAL post-step review gate — the primary inline edit path). RESEARCH's anchor table had flagged the inline handler as "2968-2981 (+ 3805-3807)"; the plan collapsed both into "gap site 1". Stamping only :2968 + declared would leave the primary inline edit path (:3805) without lineage.
- **Fix:** Added `_latest_typed_ref_id` and stamped `derived_from` at all THREE physical writes (:2968, :3805, :4566). The inline behavioral test drives the :3805 handler and was RED until :3805 was stamped — confirming :3805 is the reached path.
- **Files modified:** backend/agents/execution_engine/engine.py, backend/tests/agents/test_task_list_gate_lineage.py
- **Verification:** test_task_list_gate_lineage 2/2 green (declared + inline); redo_gate_safety held 4/3; prototype golden dormant.
- **Committed in:** 3681d102

**2. [Rule 3 - Blocking placement correction] Relocated the _is_resume re-materialization from the pre-compile hydrate hook to the post-compile/post-cursor point**
- **Found during:** Task 3
- **Issue:** The plan said thread the boundary "at the `_is_resume`-gated hook (engine.py:1383)". But at :1383 (inside `_execute_impl`) neither `compile_for_run` (:1430), `ordered_agents` (:1633), `ectx.runner` (:1931, the upstream-hash handle), nor the ordered cursor (:2089) exist yet — so the RESUME-16 boundary (which needs the parsed CURRENT task list + the strategy's upstream hash) is uncomputable there. The plan's line-number assumption predated the actual `_execute_impl` ordering (re-materialization precedes compile).
- **Fix:** Deferred the `_is_resume` `_rematerialize_artifacts_to_disk` call from :1383 to right after the skip-cursor computation (post-compile, post-runner), passing the three-state `boundary_by_agent` from `_compute_cumulative_boundaries`. Verified nothing between the two points reads the re-materialized deliverable (only a `PLANNER.md` write), so the disk is still reconstructed before the dispatch loop (Edge-Case 6 preserved). `_rematerialize_artifacts_to_disk` still receives the three-state selector exactly as specified.
- **Files modified:** backend/agents/execution_engine/engine.py
- **Verification:** goldens 10/10 (`SNAPSHOT_UPDATE` unset — INV-3 byte-identity across the move); restart_resume KAN-88 sole red; test_execution_engine 13/13; test_resumability 7/7.
- **Committed in:** 05f59abb

---

**Total deviations:** 2 auto-fixed (1 correctness/completeness, 1 blocking placement correction). Both necessary for correct RESUME-15/16 behavior. No scope creep — waves (`resume_completed_task_ids` set), the completeness count, `_first_incomplete_step`, `write_fragment_artifact`, and the `.uploads/` fence are untouched.

## Issues Encountered
- The plan/PATTERNS line numbers for the gate-edit sites and the re-materialization hook had drifted vs the live `_execute_impl` structure (re-materialization precedes `compile_for_run`). Root-caused by reading the actual function boundaries + call ordering before editing; both handled as documented deviations, not regressions.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- **48-03** (independent wave reconcile + orphan exclusion + SC-001 synthetic proof + update_specs compose) is unblocked: the ordered cursor + boundary reconciler are in place; the wave path still reads the distinct `resume_completed_task_ids` set (unchanged), ready for the per-key + orphan-exclusion work; `_rematerialize_artifacts_to_disk` already accepts the per-agent `boundary_by_agent` allow-set the orphan-exclusion gate can reuse.
- No blockers.

## Self-Check: PASSED

- Files exist: test_task_list_gate_lineage.py, 48-02-SUMMARY.md — verified below
- Commits exist: 3681d102, f6e63b1c, 05f59abb — verified below

---
*Phase: 48-task-identity-mutable-list-reconciliation-r3*
*Completed: 2026-07-19*
