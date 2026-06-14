---
phase: 22-capability-surfacing-and-user-empowerment-universal-runtime
plan: 04
subsystem: api
tags: [compiler, trust-user, cap-03, emp-01, emp-02, emp-03, manifest-json, selections, idor, inv-3, sc-001]

# Dependency graph
requires:
  - phase: 04 (compiler)
    provides: "WorkflowCompiler.compile(trust=...) + the dormant _check_trust (CAP-03) + _compile_limits untrusted ceiling"
  - phase: 06 (model policy)
    provides: "ModelResolver tier-2 step.model precedence"
  - phase: 12 (RESUME-02)
    provides: "the per-step retry wrapper gated on step.retry.max_attempts > 0"
  - phase: 21 (saved workflows)
    provides: "owner-scoped /api/user-workflows CRUD + IDOR->404 (_owned) + the run_pipeline launch replay"
  - phase: 22-01 (WIRE)
    provides: "compiler materializes per-step model/retry/validators onto the typed Step (the EMP-01 lever path)"
  - phase: 22-02 (registry metadata)
    provides: "registry user_allowed flags _check_trust reads"
provides:
  - "agents/workflows/selections.py — the SINGLE synth seam (save + launch share it): {base,agent_ids,selections} -> WorkflowManifest, EMP-04 auto-attaches the validation gate"
  - "First-ever caller of compiler.compile(trust=user): SAVE backstop (user_workflows.py) + LAUNCH re-validation (websocket.py)"
  - "EMP-03 persistence: compact per-step selections map round-trips through the reused manifest_json column (zero migration), owner-scoped, IDOR->404"
  - "EMP-01: ExecutionEngine._apply_selections overlays user-composed validators/gates/model/retry onto the file-compiled plan BY AGENT_ID (generic, name-free) through the existing run path"
  - "single_shot strategy is now user_allowed=True (the safe default per-step strategy)"
affects: [22-05 capability palette, 22-06 FE composer (produces the selections this consumes)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Single synth seam: synthesize_manifest() shared by save + launch (no duplicated synth logic)"
    - "trust=user as the authoritative server gate at BOTH save AND launch (the FE lock is advisory only)"
    - "Generic per-step selections overlay onto the compiled plan by agent_id (SC-001 — never a workflow/agent name)"
    - "Empty/None selections -> pure no-op (every existing run + 5 goldens byte/event-identical, INV-3)"

key-files:
  created:
    - backend/agents/workflows/selections.py
    - backend/tests/unit/test_user_workflows_selections.py
  modified:
    - backend/app/api/user_workflows.py
    - backend/app/api/websocket.py
    - backend/agents/execution_engine/engine.py
    - backend/agents/capabilities/strategies/single_shot.py
    - backend/tests/agents/test_compiler.py

key-decisions:
  - "Compact selections map {agent_id: {validators?, gates?, model?, retry?, ...}} persisted in manifest_json (D-11 settled compact map). Reserved __workflow__ key carries workflow-level levers (limits)."
  - "The synthesized manifest's deliverable is the user-allowed single_file (a synth artifact, NOT a user lever) so a clean map never false-rejects; the real run deliverable still comes from the engine's file-backed plan."
  - "single_shot -> user_allowed=True (Rule 2): the default per-step strategy a user workflow uses on every step; without it a trust=user compile of ANY saved workflow rejected the safe default."
  - "Launch carries selections in the run_pipeline payload (FE-replayed, like model_overrides) AND always re-validates trust=user — so a tampered row is rejected regardless of source (Pitfall 3)."

requirements-completed: [EMP-02, EMP-03, EMP-01]

# Metrics
duration: ~18min
completed: 2026-06-14
---

# Phase 22 Plan 04: Saved-Workflow Capability Selections (EMP-01/02/03) Summary

**Activated the built-but-dormant `trust="user"` compile path as the authoritative server-side gate at BOTH save AND launch (a smuggled/tampered `user_allowed=False` capability is server-rejected at each site — the FE lock is advisory only), persisted the compact per-step selections map in the reused `manifest_json` column (zero migration, owner-scoped, IDOR→404), and proved a user-selected validator + non-default model + retry reaches execution through the EXISTING run path via a generic agent-id-keyed overlay — all with the 5 characterization goldens byte-identical (INV-3) and no kernel workflow-name branch (SC-001).**

## Performance
- **Duration:** ~18 min
- **Tasks:** 2
- **Files modified:** 7 (2 created, 5 modified)

## Accomplishments
- **EMP-02 (save):** `user_workflows.py` save (create + the PATCH-when-selections-change path) synthesizes a `WorkflowManifest` and compiles it with `trust="user"` BEFORE persisting — the CAP-03 server backstop. A smuggled `gate: security`/`approval` (or a ceiling-raising Limits cap) raises `CompilerError` naming the `(kind, name)` → 422, no orphan row.
- **EMP-02 (launch):** `websocket.py` `_revalidate_selections_trust_user` re-compiles the replayed/persisted selections `trust="user"` BEFORE `engine.execute` (Pitfall 3) — a tampered row is rejected at launch (`code: invalid_selection`), not only at save.
- **EMP-03 (persistence):** the compact selections map round-trips through the dormant `manifest_json` column (zero migration, D-11), owner-scoped via the existing `_owned()` IDOR→404. Round-trip proven: save → list → reopen returns identical selections; cross-owner GET → 404.
- **EMP-01 (reaches execution):** `ExecutionEngine._apply_selections` overlays the user-composed validators/gates/model/retry onto the file-compiled plan **by agent_id** (generic, name-free) after re-compiling `trust="user"`. Proven: the validator + its EMP-04 auto-attached `validation` gate land on the compiled step (validators fire), `ModelResolver` resolves the chosen non-default model (tier-2 precedence), and the retry wrapper activates under an injected transient fault. No new run endpoint, no kernel branch.
- **New synth seam:** `agents/workflows/selections.py` — `synthesize_manifest()` shared by save + launch (no duplicated synth logic); `has_selections()` keeps the empty path a pure no-op.

## Task Commits
1. **Task 1 — save-side trust=user backstop + manifest_json selections + single_shot user_allowed + compiler trust tests** — `80473fa5` (feat)
2. **Task 2 — launch trust=user re-validation + EMP-01 selection-reaches-execution overlay + tests** — `53f9cfd6` (feat)

## Files Created/Modified
- `backend/agents/workflows/selections.py` (created) — the synth seam (manifest from selections; EMP-04 validation-gate auto-attach; reserved `__workflow__` limits key).
- `backend/tests/unit/test_user_workflows_selections.py` (created) — round-trip, IDOR→404, save-reject (security/approval/ceiling), launch-reject (tampered), EMP-01 proof (validator+gate / model / retry).
- `backend/app/api/user_workflows.py` — `selections` on save/update bodies; `_compile_selections_trust_user` backstop on create + PATCH; persist into `manifest_json`; round-trip via `_project`.
- `backend/app/api/websocket.py` — run_pipeline extracts `selections`; `_revalidate_selections_trust_user` (launch CAP-03); threaded through `_handle_workflow_execution` → `engine.execute`.
- `backend/agents/execution_engine/engine.py` — `execute`/`_execute_impl` gain `selections=`; `_apply_selections` overlay applied right after `compile_for_run`.
- `backend/agents/capabilities/strategies/single_shot.py` — `user_allowed=True`.
- `backend/tests/agents/test_compiler.py` — trust=user rejection cases (security/approval gate, exec/spawn grant, ceiling Limits) + clean-user-caps acceptance.

## Decisions Made
- **Compact selections map** stored verbatim in `manifest_json`; the FE composer + both server sites read the same shape. Workflow-level levers (Limits) ride the reserved `__workflow__` key so they share the same trust=user ceiling backstop.
- **Synth deliverable = `single_file`** (user-allowed) — a synth artifact only, so a clean per-step selections map never false-rejects on the deliverable trust check; the actual run deliverable comes from the engine's own file-backed plan (the synthesized manifest never runs).
- **Launch always re-validates** whatever selections arrive (payload-replayed or DB-loaded), so a tampered row is caught regardless of source — the WS layer is the authoritative rejection site; `_apply_selections` degrades to the unmodified plan on any compile failure (defense in depth, never crashes the run).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] `single_shot` strategy was not `user_allowed`**
- **Found during:** Task 1 (first trust=user compile of a synthesized user workflow)
- **Issue:** `single_shot` (the default per-step strategy every custom/user workflow uses on each step) was registered without `user_allowed=True` (22-02 authored metadata but did not flag it). A `compile(trust="user")` of ANY saved workflow's steps therefore rejected `single_shot` — EMP-01/02 could not function at all. Likewise the synth manifest's deliverable trust check surfaced that `streamed_text` is not user-allowed, addressed by using the user-allowed `single_file` as the synth-only deliverable.
- **Fix:** `single_shot` → `user_allowed=True` (running one agent once carries no privilege — consistent with `task_loop`/`fanout_batch`/`wave_scheduler`). The synth helper uses `single_file` for its (non-running) deliverable.
- **Files modified:** backend/agents/capabilities/strategies/single_shot.py, backend/agents/workflows/selections.py
- **Verification:** `test_capabilities_api.py` 12/12 still green (derived `security_gated == not user_allowed` invariant holds); the clean-user-caps compiler test + the EMP-01 overlay tests pass; 5 goldens byte-identical (trust defaults to file for every golden — the flag is inert there).
- **Committed in:** `80473fa5`

**Total deviations:** 1 auto-fixed (1 missing-critical, required for EMP-01/02 to function at all).

## Issues Encountered
- `tests/unit/test_user_workflows.py::test_migration_adds_then_drops_columns` FAILS **pre-existing** (proven via `git stash` on clean HEAD). The P21 `0021`-down assertion no longer holds after migration `0022` (P22-03) layered on top; the columns persist across the `0021` downgrade. Unrelated to 22-04 (no migration touched). Logged to `deferred-items.md` — SCOPE BOUNDARY, not fixed here.

## Known Stubs
None — selections round-trip through `manifest_json` and reach execution via the overlay; no empty/placeholder data flows to any UI. (The FE composer that *authors* the selections is 22-06; this is the backend half that consumes them, per the plan.)

## Threat Flags
None — no new network endpoint, auth path, or schema change was introduced (the launch is the existing `run_pipeline` path extended with pure data; persistence reuses the existing `manifest_json` column). The threat register's `mitigate` rows (T-22-04-01..06) are all covered by tests.

## Verification Evidence
- `test_user_workflows_selections.py` 14/14; `test_compiler.py` 32/32 (incl. 7 new trust=user cases).
- INV-3: 5 characterization goldens byte/event-identical (42 passed incl. step_retry + model_resolver; NO SNAPSHOT_UPDATE).
- SC-001: `test_banned_patterns.py` 11/11; grep for `if pipeline_type ==`/`spec.id ==` over the routed launch path (engine.py, compiler.py, selections.py) = 0 (the 3 websocket.py od_* hits are the documented display-routing reservation, not the kernel).
- `lint-imports` 4 kept / 0 broken; `test_run_pipeline_validation.py` 50/50; `test_capabilities_api.py` 12/12.
- Zero new migrations (manifest_json reuse, D-11).

## Self-Check: PASSED
- FOUND: backend/agents/workflows/selections.py
- FOUND: backend/tests/unit/test_user_workflows_selections.py
- FOUND commit: 80473fa5 (Task 1)
- FOUND commit: 53f9cfd6 (Task 2)

---
*Phase: 22-capability-surfacing-and-user-empowerment-universal-runtime-*
*Completed: 2026-06-14*
