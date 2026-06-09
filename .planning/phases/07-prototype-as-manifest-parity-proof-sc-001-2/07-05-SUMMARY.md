---
phase: 07-prototype-as-manifest-parity-proof-sc-001-2
plan: 05
subsystem: infra
tags: [engine-decoupling, leak-deletion, migration-ledger, banned-patterns, inv-1, sc-001, hexagonal, parity, move-dont-copy]

# Dependency graph
requires:
  - phase: 07-04
    provides: "the routed path proven at 5-pipeline parity (per-step strategy dispatch, deliverable resolver routing, generic context injector, KernelServices handle); the L1-L13 leaks left DEAD-not-deleted on the routed path + the vulture orphan list this plan deletes"
  - phase: 07-02
    provides: "the deliverable resolvers (single_file/ppt/streamed_text/serialized_sandbox) + the _artifact transform module (the move-don't-copy HOME of sanitize/unwrap); the relocated OD loaders (od_context.py); previous_run provider"
  - phase: 07-03
    provides: "the html_skeleton compaction capability (the move-don't-copy HOME of the skeleton extraction)"
provides:
  - "Leak-free kernel: L1-L13 DELETED from engine.py; agents/prototype/ package removed (pipeline.py + the emptied context.py); INV-12 move-don't-copy exit gate proven (every per-leak kernel grep returns 0, no dangling imports)"
  - "SC-001 / INV-1 landed: the kernel knows NO workflow by name on the routed path — zero `if pipeline_type ==` / `spec.id ==` branches in agents/execution_engine/ (verified by the kernel-scoped banned-pattern HARD-FAIL gate)"
  - "Migrated parity survivors (move-don't-drop): the L10 single-file disk readback + the L3 mid-stream ppt carousel sanitize now key off the DECLARED compiled.deliverable strategy (single_file / ppt) on ctx, preserving agent_complete.output_length parity (PARITY-07/09); the legacy L10 revision-exclusion preserved via ectx.is_revision_workflow"
  - "Manifest-sourced clarify + revision gating: L6 ALWAYS_CLARIFY behavior re-homed to compiled.clarify.mode == 'auto'; the in-place revision setup + post-revision validation gate key off the declared previous_run provider (ectx.is_revision_workflow), not the prototype_revision name"
  - "Ratchets armed: migration-ledger rows L1-L13 flipped to checked with KERNEL-SCOPED grep gates; the banned-pattern INV-1 gate flipped warn-only -> kernel-scoped HARD-FAIL; L14/L15/L16 re-confirmed closed"
affects: [phase-3-factory-decoupling, future-custom-workflow-composer]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Deliverable-strategy-keyed mid-stream transforms: the per-agent output transforms in _run_agent (single-file disk readback, ppt carousel sanitize) key off ctx.deliverable.strategy (the compiled spec bound at run entry) — NOT a pipeline_type name branch (INV-1). The transform DEFINITIONS live in the capability layer (_artifact.py); the engine call site reads the declared strategy."
    - "Manifest-feature gating over workflow-name gating: revision-specific behavior (in-place edit setup, pre-edit baseline, post-revision validation fix-loop) is gated on the workflow DECLARING the previous_run context provider (ectx.is_revision_workflow), not on `pipeline_type == 'prototype_revision'`. The compiled workflow is compiled at run ENTRY so manifest features are available to the per-run setup."
    - "Kernel-scoped ratchets: INV-1/SC-001 is a property of the runtime kernel's routed path, so the migration-ledger L1-L13 gates + the banned-pattern INV-1 gate grep agents/execution_engine/ only — legit non-kernel references (the move-don't-copy capability homes, registry alias maps, app consumers, tests) survive without false-failing the ratchet."

key-files:
  created: []
  modified:
    - backend/agents/execution_engine/engine.py
    - backend/agents/execution_engine/context.py
    - backend/agents/execution_engine/kernel_services.py
    - specs/003-workflow-engine-decoupling/migration-ledger.md
    - backend/tests/agents/test_banned_patterns.py
    - backend/tests/agents/test_migration_ledger.py
    - backend/tests/agents/test_manifest_parity.py
    - backend/tests/agents/_scripted_model.py
    - backend/tests/agents/test_context_providers.py
    - backend/tests/agents/test_deliverable_resolvers.py
    - backend/tests/agents/test_phase3_compaction.py
    - backend/tests/agents/test_phase3_cutover_verify.py
    - backend/tests/agents/test_phase5_revision_validation.py
    - backend/tests/agents/live_harness.py
    - backend/tests/agents/test_live_harness.py
    - backend/tests/unit/test_agent_input_event.py
    - backend/tests/unit/test_plan_task_parsing.py

key-decisions:
  - "07-05: L4/L8 and L11 ledger patterns REFINED to the leak construct (not the bare token) because the bare token legitimately survives as LIVE behavior — L4/L8 greps `pipeline_type == \"prototype_revision\"` (the inline name-branch, now 0; the agnostic revision setup is manifest-gated and keeps the token only in log/comment strings); L11 greps the four genuinely-deleted symbols and DROPS the retained survivors _run_validation_fix_loop / _load_template_example (LIVE via the KernelServices handle)."
  - "07-05: L1 keeps REVISION_FILE_NAME (still LIVE in the agnostic revision setup _slim_revision_message); only the _PPT_PIPELINE_TYPES/_PROTOTYPE_PIPELINE_TYPES name-sets are deleted (the ledger L1 pattern excludes REVISION_FILE_NAME)."
  - "07-05: the L10 mid-stream single-file readback is EXCLUDED for revision workflows (ectx.is_revision_workflow) to preserve the legacy gate's prototype-only scope — a revision's mid-stream output is the edited streamed text (output_length parity), not a fresh disk file."
  - "07-05: the CompiledWorkflow is now compiled at run ENTRY (before the revision setup) so revision-specific behavior gates on the declared previous_run provider rather than the workflow name (INV-1)."
  - "07-05: the migration-ledger ratchet + banned-pattern INV-1 gate are KERNEL-SCOPED (agents/execution_engine/) — INV-1/SC-001 is a kernel-path property; legit non-kernel refs (capability move-don't-copy homes, registry, app, tests) are retained."

patterns-established:
  - "INV-1 kernel hard-fail: test_banned_patterns.py asserts ZERO `if pipeline_type ==` / `spec.id ==` in the kernel (with a non-vacuity guard); reintroducing a kernel workflow-name/agent-id branch fails CI — the SC-001 core-value ratchet."
  - "Stale-suite retirement on move-don't-copy completion: engine-internal test suites whose target symbols moved to capabilities are retired (their behavior is covered by the capability tests + the 5-pipeline characterization), not left coupled to deleted internals."

requirements-completed: [PARITY-06, PARITY-08]

# Metrics
duration: ~150min
completed: 2026-06-09
---

# Phase 7 Plan 05: Leak Deletion + Ratchet Flip (SC-001 Landing) Summary

**The kernel now knows NO workflow by name: L1-L13 are physically deleted from `engine.py`, the `agents/prototype/` package is removed, the L3/L10 parity survivors are migrated to key off the declared `compiled.deliverable` strategy (preserving `output_length` parity), the migration-ledger L1-L13 rows are flipped to checked with kernel-scoped gates, and the banned-pattern INV-1 reservation is now a kernel-scoped HARD-FAIL — SC-001/INV-1 landed with all 5 pipeline characterization + routing-parity suites green.**

## Performance
- **Duration:** ~150 min
- **Completed:** 2026-06-09
- **Tasks:** 3
- **Files modified:** 17 (3 kernel, 1 spec, 13 tests) + 3 deletions (prototype package, 2 stale test files; 1 unit test deletion)

## Accomplishments
- **L1-L13 deleted from the kernel (PARITY-06):** the L1 ppt/prototype pipeline-type name-sets, L2/L9 `_resolve_final_output`, L3 `_sanitize_carousel_deck_html`/`_unwrap_artifact`, L6 `ALWAYS_CLARIFY`, the L7 dead dispatch predicate, L11 `_run_build_task_loop`/`_write_build_reference_files`/`_count_plan_tasks`/`_extract_task_block`, L12 `_build_context_message`, L13 `_extract_html_skeleton`, plus the dead `_legacy_*` strangler stubs. Every per-leak kernel grep returns 0.
- **agents/prototype/ package removed (INV-12):** `pipeline.py` (dead) + the emptied `context.py` (loaders re-homed to `od_context.py` in 07-02) + `__init__.py` + `README.md`. No dangling imports; the engine imports clean.
- **Parity survivors migrated, not dropped (move-don't-drop, INV-3):** the L10 single-file disk readback + the L3 mid-stream ppt carousel sanitize now key off `ctx.deliverable.strategy` (`single_file` / `ppt`) — bound at run entry from `compiled.deliverable` — so `agent_complete.output_length` parity (PARITY-07/09) holds with NO `pipeline_type` name branch. The legacy L10 revision-exclusion is preserved via `ectx.is_revision_workflow`.
- **L6/revision behavior re-homed to the manifest (INV-1):** the "force CLARIFY_REQUIRED on every run" behavior reads `compiled.clarify.mode == "auto"`; the in-place revision setup + the post-revision validation fix-loop gate key off the declared `previous_run` provider (`ectx.is_revision_workflow`), not the `prototype_revision` name. The positional first-agent check was already `index == 0` (Pitfall 1).
- **SC-001 / INV-1 landed (PARITY-08):** the kernel `if pipeline_type ==` / `spec.id ==` grep returns 0; the banned-pattern gate flipped warn-only -> kernel-scoped HARD-FAIL with a non-vacuity guard.
- **Ratchets armed:** migration-ledger L1-L13 flipped to checked (SHA `1d9234b`) with kernel-scoped patterns (L4/L8 + L11 refined to the leak construct); L14/L15/L16 re-confirmed closed (L16 cross-owner denial test green); D1 stays voided (`_handle_revision` retained).
- **Parity holds after deletion:** all 5 characterization suites + `test_routing_parity.py` + `test_manifest_parity.py` green; full offline `tests/agents/` + `tests/unit/` green except exactly the 8 known pre-existing failures; import-linter contracts kept (exit 0).

## Task Commits

1. **Task 1: Delete L1-L13 from the kernel + drop pipeline.py + remove the prototype package + fix the positional spec.id** — `1d9234b` (refactor)
2. **Task 2: Update the test-coupling sites whose symbols were deleted** — `0bb8bca` (test)
3. **Task 3: Flip ledger L1-L13 (kernel-scoped) + banned-pattern hard-fail + re-verify L14/L15/L16** — `5d141fc` (test)

**Plan metadata:** _(this commit)_

## Files Created/Modified
- `backend/agents/execution_engine/engine.py` — deleted L1-L13 + the `_legacy_*` stubs; migrated the L10/L3 mid-stream transforms to `ctx.deliverable.strategy`; compiled the workflow at run entry; gated revision behavior on the declared `previous_run` provider; rewrote the last `pipeline_type == "prototype_revision"` branch to `ectx.is_revision_workflow`; scrubbed residual deleted-symbol comments; dropped the now-unused sandbox-deliverable imports.
- `backend/agents/execution_engine/context.py` — added `deliverable`, `last_streamed`, `is_revision_workflow` fields (the per-run binding the migrated transforms read).
- `backend/agents/execution_engine/kernel_services.py` — scrubbed deleted-symbol comment references.
- `specs/003-workflow-engine-decoupling/migration-ledger.md` — flipped L1-L13 to checked (SHA `1d9234b`), kernel-scoped + leak-construct-refined patterns, with a 07-05 kernel-scoping note.
- `backend/tests/agents/test_banned_patterns.py` — INV-1 reservation flipped warn-only -> kernel-scoped HARD-FAIL + non-vacuity guard.
- `backend/tests/agents/test_migration_ledger.py` — per-row kernel scoping for L1-L13; re-anchored non-vacuity guard; updated the flipped-set assertion.
- `backend/tests/agents/test_manifest_parity.py`, `_scripted_model.py`, `test_context_providers.py` — test-coupling updates for the deleted L5/L6 symbols + removed prototype package.
- `backend/tests/agents/test_deliverable_resolvers.py`, `test_phase3_compaction.py`, `test_phase3_cutover_verify.py`, `test_phase5_revision_validation.py`, `live_harness.py`, `test_live_harness.py`, `tests/unit/test_agent_input_event.py`, `tests/unit/test_plan_task_parsing.py` — repointed to capability homes / `_compose_context_message` / the `compile_for_run` clarify-disable.
- **Deleted:** `backend/agents/prototype/` (package), `backend/tests/agents/test_phase4_build_loop.py`, `backend/tests/agents/test_pipeline_type_routing.py`, `backend/tests/unit/test_final_output_resolution.py`.

## Decisions Made
See the `key-decisions` frontmatter. Summary: L4/L8 + L11 ledger patterns refined to the leak construct (the bare token survives as LIVE behavior); L1 keeps the live `REVISION_FILE_NAME`; the L10 mid-stream readback excludes revisions to preserve the legacy prototype-only scope; the CompiledWorkflow is compiled at run entry to gate revision behavior on the declared `previous_run` provider; the ledger + banned-pattern ratchets are kernel-scoped.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] L10 mid-stream readback broadened to revisions, breaking output_length parity**
- **Found during:** Task 1 (5-pipeline characterization gate)
- **Issue:** Keying the migrated single-file readback purely off `deliverable.strategy == "single_file"` fired it for `prototype_revision` too (also a single_file workflow), overwriting the per-agent `output` with the disk file (48 chars) instead of the edited streamed text (28 chars) — diverging `agent_complete.output_length` from the committed golden. The legacy L10 gate (`pipeline_type in ("od_prototype","prototype")`) deliberately EXCLUDED revision.
- **Fix:** Added `ectx.is_revision_workflow` (set at run entry from the declared `previous_run` provider) and excluded revision workflows from the mid-stream readback — restoring the legacy prototype-only scope without a name branch.
- **Files modified:** engine.py, context.py
- **Verification:** `test_characterization_prototype_revision` + forward prototype/od_prototype characterization all green.
- **Committed in:** `1d9234b` (Task 1)

**2. [Rule 1 - Bug] A second `pipeline_type == "prototype_revision"` routed-path branch (post-revision validation gate) remained**
- **Found during:** Task 3 (INV-1 kernel grep)
- **Issue:** The post-revision validation fix-loop guard (`if pipeline_type == "prototype_revision" and ...`) was a workflow-name branch on the routed path the plan's Task-1 enumeration did not call out — it would fail the INV-1 kernel hard-fail.
- **Fix:** Rewrote it to `if _is_revision_workflow and ...` (the declared `previous_run` provider gate).
- **Files modified:** engine.py
- **Verification:** kernel `if pipeline_type|spec.id ==` grep = 0; banned-pattern gate green.
- **Committed in:** `5d141fc` (Task 3)

**3. [Rule 3 - Blocking] Third+ test-coupling sites beyond the plan's enumerated two**
- **Found during:** Task 2 / Task 3 (offline suite collection + runtime)
- **Issue:** The plan listed 2 test-coupling sites (test_manifest_parity, _scripted_model). Execution found MANY more coupled to the deleted symbols or to the leaked `ALWAYS_CLARIFY=False` global side-effect: `test_context_providers.py` (imported the deleted package), `test_deliverable_resolvers.py` / `test_agent_input_event.py` / `test_plan_task_parsing.py` (called deleted free functions / staticmethods), `live_harness.py` + `test_live_harness.py` + `test_phase5_revision_validation.py` (read/set the deleted `ALWAYS_CLARIFY` module global), and the engine-internal suites `test_final_output_resolution.py` / `test_phase4_build_loop.py` / `test_pipeline_type_routing.py` / `test_phase3_compaction.py` / `test_phase3_cutover_verify.py` (drove deleted engine methods / pinned the now-false Phase-1A allow-list).
- **Fix:** Retired the fully-superseded suites (behavior covered by capability tests + characterization + the hard-fail gate); repointed the rest to the capability homes / `_compose_context_message` / a `compile_for_run` clarify.mode="off" wrapper (replacing the leaked `ALWAYS_CLARIFY=False` global with a properly-scoped, restored patch). The leaked-global discovery: the old `_scripted_model._drive` set `ALWAYS_CLARIFY=False` and never restored it, so later tests (e.g. `test_phase5_revision_validation`) silently depended on that pollution — the new per-harness wrapper makes each harness self-contained.
- **Files modified:** the 8 repointed test files + 3 retired files (see Files list)
- **Verification:** full offline `tests/agents/` + `tests/unit/` green except the 8 known pre-existing failures.
- **Committed in:** `0bb8bca` (Task 2), `5d141fc` (Task 3)

**4. [Rule 3 - Blocking] Ledger ratchet greps whole-backend; L1-L13 bare tokens survive in legit non-kernel homes**
- **Found during:** Task 3 (ledger ratchet)
- **Issue:** The migration-ledger ratchet greps `backend/ --include=*.py` whole-tree, but the L1-L13 lifted patterns legitimately reappear in the move-don't-copy capability homes (`_artifact.py`, `heading_tasks.py`, `html_skeleton.py`), the registry, app consumers, and tests — a whole-tree assertion would false-fail.
- **Fix:** Made the ratchet per-row kernel-scoped (L1-L13 -> `agents/execution_engine/`, L14/L15 stay tree-wide), refined the L4/L8 + L11 patterns to the leak construct, and re-anchored the non-vacuity guard on `class ExecutionEngine` (the prior anchor `_PROTOTYPE_PIPELINE_TYPES` was a deleted L1 leak). This is the plan's sanctioned kernel-scoping discretion.
- **Files modified:** test_migration_ledger.py, migration-ledger.md
- **Verification:** `test_migration_ledger.py` green (L1-L13 ☑ kernel-scoped, L14/L15/L16 ☑); non-vacuity guard fires.
- **Committed in:** `5d141fc` (Task 3)

---

**Total deviations:** 4 auto-fixed (2 bugs, 2 blocking). **Impact on plan:** All necessary for correctness (output_length parity), the INV-1/SC-001 goal (the second name branch + kernel-scoping), and a green suite (the broader test-coupling). No scope creep — every change is leak deletion, parity-preserving migration, or test alignment to the deletion.

## Issues Encountered
- **Test-ordering hang from a leaked global:** before this plan, the offline `_scripted_model._drive` harness set `engine_mod.ALWAYS_CLARIFY = False` and never restored it, so `test_phase5_revision_validation` (which never disabled clarify itself) silently relied on that leaked global. Deleting `ALWAYS_CLARIFY` exposed the dependency as a hang (the auto-clarify branch awaits a live WS round-trip the offline harness cannot do). Fixed by giving each affected harness its own restored `compile_for_run` clarify.mode="off" wrapper. Verified pre-existing on the base commit (the test hung at base too — it was only green via the leak).
- **`tests/agents/test_live_*` fail in ISOLATION but pass in the full suite:** they snapshot `engine._store.store` (a thin-store method deleted in 05-07/D2 — a PRE-EXISTING breakage, reproduced on the base commit). In the full offline suite they pass (test-ordering provides the attribute); in isolation they error. Out of scope for 07-05 (a 05-07 follow-up) — logged to `deferred-items.md`.

## Known Stubs
None. The `_legacy_*` strangler stubs were the intended deletion targets and are gone.

## Threat Flags
None — no new security surface. T-07-05-01 (kernel name/id re-coupling) is now HARD-FAILED by the kernel-scoped banned-pattern gate. T-07-05-02 (L16 cross-owner denial) re-confirmed green (`test_parent_run_ownership.py`); the revision parent-seed runs through the `previous_run` provider whose `assert_owns` propagates. T-07-05-03 (over-broad ledger grep) mitigated by kernel-scoping + leak-construct refinement (the ratchet stays non-vacuous AND retains legit non-kernel refs). T-07-05-04 (D1 voided handler) — `_handle_revision` retained.

## User Setup Required
None.

## Next Phase Readiness
- **SC-001 proven and ratchet-locked:** the kernel knows no workflow by name; a brand-new custom workflow can replicate `prototype` by manifest + AGENT.md with zero engine edits, and any future kernel name/id branch fails CI (banned-pattern hard-fail + migration-ledger ratchet).
- **Phase 3 (factory decoupling, F1-F5)** is the next leak family: the `agents/factory.py` prompt-assembly / tool-provider / skill-hook / constitution / runtime-adapter leaks remain `☐` in the ledger.
- **Deferred (05-07 follow-up):** `tests/agents/live_harness.py` still snapshots the deleted thin-store `_store.store` — repoint it to the typed `ScopedStore`/`ArtifactGraph` substrate or drop the obsolete stub. Logged in `deferred-items.md`.

## Self-Check: PASSED

- SUMMARY.md exists at `.planning/phases/07-prototype-as-manifest-parity-proof-sc-001-2/07-05-SUMMARY.md`.
- `agents/prototype/` package removed (INV-12 exit gate).
- Commits exist: `1d9234b` (Task 1), `0bb8bca` (Task 2), `5d141fc` (Task 3).

---
*Phase: 07-prototype-as-manifest-parity-proof-sc-001-2*
*Completed: 2026-06-09*
