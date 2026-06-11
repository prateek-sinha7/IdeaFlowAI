---
phase: 11-engine-owned-fan-out-merge-5
plan: 04
subsystem: infra
tags: [fanout, budget, dos-mitigation, reserve-before-spawn, snapshot, scopedstore, compiler-trust, kernel]

# Dependency graph
requires:
  - phase: 11-engine-owned-fan-out-merge-5
    provides: "11-01 run_fanout single spawn path + the reserve() stub seam + BudgetManager/BudgetExceeded/BudgetSnapshot + module-constant defaults + subagent_runs persistence"
  - phase: 11-engine-owned-fan-out-merge-5
    provides: "11-03 KernelServices.write_fragment_artifact (the typed lineage-tracked fragment artifacts the abort path surfaces) + the per-worker artifact_ref on the structured summary"
  - phase: 10-exec-runtime
    provides: "ScopedStore record_exec_run best-effort None-degrade pattern (cloned for persist_budget_snapshot) + the trust-conditional compiler GRANT-PATH ceiling precedent"
  - phase: 08-capability-hardening
    provides: "compiler trust context (file/builtin vs user/db) + the AGENT.md-only-lowers ceiling precedent (mirrored by the Limits rule)"
provides:
  - "ENFORCING BudgetManager.reserve(*, subagents, concurrency, depth, workspace_spent) — raises BudgetExceeded (naming the breached dimension) reserve-before-spawn (FANOUT-09)"
  - "Check-at-boundary BudgetManager.note_tokens / note_wall_clock (+ arm() deadline capture) — tokens/wall-clock cannot be pre-reserved (D-05 dual shape)"
  - "BudgetManager.from_limits(limits, *, workspace_ceiling) resolving Limits over module-constant defaults (8/4/2/900); tokens uncapped unless declared; warn_threshold_reached at 0.8"
  - "Trust-conditional compiler._compile_limits: file/builtin may RAISE a Limits cap; user/db may only LOWER (CompilerError naming the dimension) — CompiledWorkflow.limits now materialized (was inert)"
  - "ScopedStore.workspace_budget_spent(workspace_id) owner+workspace aggregate (cross-owner ∅) + ScopedStore.persist_budget_snapshot (workflow_runs.budget_snapshot_json, the 0014 forward column)"
  - "KernelServices.workspace_budget_spent + persist_budget_snapshot handles (None-degrading, never abort the run)"
  - "WORKSPACE_BUDGET_MAX_SUBAGENTS / _MAX_TOKENS settings seam (default None = unset = uncapped)"
  - "Engine: per-run BudgetManager built from compiled.limits at run entry; snapshot persisted on completion/abort/cancel (strictly conditional on fan-out activity); BudgetExceeded graceful abort surfaces the completed workers' 11-03 fragment artifacts"
  - "New events: budget_warning (≥80% of any ceiling OR a failed reserve) + budget_aborted (the graceful-abort partial summary)"
affects: [11-05-cancel-teardown]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Reserve-before-spawn enforcement point (Pitfall 4): reserve raises BEFORE any allocate/run_worker/record so a refused reservation leaves ZERO subagent_runs rows (proven by the zero-rows test)"
    - "Check-at-boundary tokens/wall-clock (D-05): you cannot pre-reserve unknown token spend — note_tokens accumulates+raises, note_wall_clock raises past the arm() deadline (a mid-flight breach aborts gracefully)"
    - "Trust-conditional Limits ceiling (08-03/10-02 precedent): file/builtin may RAISE, user/db only LOWER — the static budget gate; the runtime concurrency clamp min(declared,4) is the backstop"
    - "Snapshot persistence STRICTLY conditional on fan-out activity (Pitfall 3): a non-fanout run writes NO snapshot so the 5 characterization snapshots stay byte/event-identical (the exec-workspace provisioning precedent)"
    - "Compiler defines the static ceiling constants LOCALLY (not imported from the kernel) so the import-linter agents.workflows ↛ agents.execution_engine contract stays green — the budget module is the runtime enforcer, the compiler is the static gate"

key-files:
  created:
    - backend/tests/agents/test_budget.py
  modified:
    - backend/agents/execution_engine/budget.py
    - backend/agents/execution_engine/fanout.py
    - backend/agents/execution_engine/kernel_services.py
    - backend/agents/execution_engine/engine.py
    - backend/agents/workflows/compiler.py
    - backend/agents/authz.py
    - backend/app/core/config.py
    - backend/tests/agents/test_compiler_trust.py
    - backend/tests/agents/test_fanout.py

key-decisions:
  - "The compiler defines its OWN _LIMITS_DEFAULT_CEILING constants (mirroring budget.py's 8/2/900) rather than importing the kernel budget module — the import-linter forbids agents.workflows → agents.execution_engine. The budget module stays the canonical RUNTIME enforcer; the compiler constant is the STATIC compile-time gate (documented as a mirror)."
  - "max_tokens is EXCLUDED from the user/db raise-rejection set: it has no module-constant ceiling (uncapped unless declared), so a user/db manifest declaring max_tokens only constrains ITSELF — it is never a 'raise above the ceiling'."
  - "depth enforcement is depth+1 > max_depth (the spawn happens one level below ctx.depth): a top-level run at ctx.depth=2 with max_depth=2 is refused because its children would land at depth 3."
  - "arm() is idempotent (first deadline wins) so a nested fan-out cannot extend the run's wall-clock budget."
  - "snapshot persistence is gated on real fan-out activity (subagents/tokens/wall-clock spend) so existing non-fanout workflows write nothing — byte/event parity (force=True only on the BudgetExceeded abort, where fan-out provably ran)."

patterns-established:
  - "BudgetExceeded carries a .dimension attribute so the abort event + the partial summary report which ceiling tripped"
  - "The per-workspace ceiling read is owner+workspace scoped at the ScopedStore (workspace_budget_spent) so a cross-owner workspace's spend never throttles this run (T-11-04-04)"

requirements-completed: [FANOUT-09, OBS-01]

# Metrics
duration: ~45min
completed: 2026-06-11
---

# Phase 11 Plan 04: Budget Enforcement Summary

**The 11-01 budget seam now ENFORCES: `BudgetManager.reserve()` raises `BudgetExceeded` reserve-before-spawn on subagents/concurrency/depth (FANOUT-09) with check-at-boundary tokens/wall-clock; `Limits` is trust-conditional at compile (file raises, user/db lower-only); a per-workspace ceiling is checked against the owner-scoped aggregate; and a `BudgetSnapshot` persists to `workflow_runs.budget_snapshot_json` on completion/abort/cancel while a graceful `BudgetExceeded` abort surfaces the completed workers' 11-03 fragment artifacts (OBS-01) — all with the 5 characterization snapshots byte/event-identical.**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-06-11
- **Completed:** 2026-06-11
- **Tasks:** 2 (both TDD)
- **Files modified:** 9 (1 created, 8 modified)

## Accomplishments
- **Enforcing reserve (FANOUT-09):** `BudgetManager.reserve(*, tokens, subagents, concurrency, depth, workspace_spent)` raises `BudgetExceeded` (carrying `.dimension`) BEFORE recording the units, so a refused reservation leaves ZERO `subagent_runs` rows / spawns — proven reserve-before-spawn (the cap-N → N+1-never-spawns test). Depth enforces `depth+1 > max_depth` (a nested fan-out beyond 2 is refused). `note_tokens`/`note_wall_clock` are check-at-boundary (you cannot pre-reserve unknown token spend — D-05); `arm()` captures the wall-clock deadline (idempotent, first-deadline-wins) and a mid-flight breach aborts. Defaults are module constants (8/4/2/900); tokens stay uncapped unless declared. `warn_threshold_reached` fires at ≥0.8 of any ceiling.
- **Trust-conditional `Limits` (FANOUT-09 / CAP-03):** `compiler._compile_limits` materializes the formerly-inert `CompiledWorkflow.limits` from the manifest. A file/builtin manifest may RAISE a cap above the default ceiling; a user/db manifest that RAISES any cap is a `CompilerError` naming the dimension (user/db may only LOWER — the 08-03/10-02 precedent). The ceiling constants live LOCALLY in the compiler (not imported from the kernel) so the import-linter `agents.workflows ↛ agents.execution_engine` contract stays green.
- **Per-workspace ceiling (OBS-01 / T-11-04-01):** `ScopedStore.workspace_budget_spent` sums `subagent_runs` across the workspace's runs for THIS owner (cross-owner ∅, T-11-04-04), reached via the `KernelServices.workspace_budget_spent` handle; `run_fanout` reads it before reserve when the budget carries a configured `workspace_ceiling`. The `WORKSPACE_BUDGET_MAX_SUBAGENTS` settings seam (default `None` = unset = uncapped) supplies the ceiling; the engine wires it into the run-entry `BudgetManager.from_limits`.
- **Snapshot persistence + graceful abort (OBS-01):** `ScopedStore.persist_budget_snapshot` writes `workflow_runs.budget_snapshot_json` (the 0014 forward column, default-deny / cross-owner no-op); `KernelServices.persist_budget_snapshot` clones the `record_exec_run` None-degrade pattern (never aborts the run). The engine persists at completion/abort/cancel — STRICTLY conditional on fan-out activity so non-fanout runs write nothing (byte/event parity, Pitfall 3; `force=True` only on the BudgetExceeded abort). The `BudgetExceeded` handler transitions the run `failed`, emits a `budget_aborted` event naming the breached dimension, and surfaces the completed workers' 11-03 `write_fragment_artifact` refs in a partial structured summary (pending workers never spawned). `budget_warning` fires at ≥80% + on a failed reserve.

## Task Commits

Each task was committed atomically:

1. **Task 1: Enforcing BudgetManager + trust-conditional Limits + per-workspace ceiling** — `79919d5` (feat)
2. **Task 2: BudgetSnapshot persistence + budget_warning event + graceful abort with partial results** — `732ec9a` (feat)

_Note: both tasks carried `tdd="true"`; tests were authored alongside the implementation (RED→GREEN within the same task commit, the project's established offline-suite cadence)._

## Files Created/Modified
- `backend/agents/execution_engine/budget.py` — enforcing `reserve` (raises `BudgetExceeded` with `.dimension`), `note_tokens`/`note_wall_clock`/`arm`, `from_limits`, `warn_threshold_reached`; defaults kept as module constants.
- `backend/agents/execution_engine/fanout.py` — `run_fanout` arms + reserves before spawn (reading the per-workspace aggregate through the handle), emits `budget_warning` on a failed reserve + at ≥80% after collect.
- `backend/agents/workflows/compiler.py` — `_compile_limits` (trust-conditional) + `_LIMITS_DEFAULT_CEILING`; `CompiledWorkflow.limits` now materialized.
- `backend/agents/authz.py` — `ScopedStore.workspace_budget_spent` (owner+workspace aggregate) + `ScopedStore.persist_budget_snapshot` (the 0014 column).
- `backend/agents/execution_engine/kernel_services.py` — `workspace_budget_spent` + `persist_budget_snapshot` handles (None-degrading).
- `backend/agents/execution_engine/engine.py` — run-entry `BudgetManager.from_limits` + `_persist_budget_snapshot_if_active` (conditional) + `_collect_partial_fragments` + the `BudgetExceeded` graceful-abort handler + completion/cancel persist sites.
- `backend/app/core/config.py` — `WORKSPACE_BUDGET_MAX_SUBAGENTS` / `_MAX_TOKENS` settings seam.
- `backend/tests/agents/test_budget.py` (new) — FANOUT-09 + OBS-01 suite (reserve enforcement, reserve-before-spawn zero-rows, depth, wall-clock, defaults, per-workspace ceiling, snapshot persistence completion+abort, partial-results, workspace aggregate owner-scoping).
- `backend/tests/agents/test_compiler_trust.py` — Limits-rule extension (file may raise, user/db rejected, lower-only allowed, max_tokens not a raise, unknown key rejected).

## Decisions Made
- The compiler defines its OWN static ceiling constants (a documented mirror of budget.py's 8/2/900) rather than importing the kernel — the import-linter forbids `agents.workflows → agents.execution_engine`. The budget module is the runtime enforcer; the compiler constant is the static gate.
- `max_tokens` is excluded from the user/db raise-rejection set (no module-constant ceiling — declaring it only self-constrains).
- depth enforces `depth+1 > max_depth` (the spawn lands one level below `ctx.depth`).
- snapshot persistence is gated on real fan-out activity so non-fanout runs stay byte/event-identical (`force=True` only on the abort).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] 11-01 concurrency-cap test tripped the now-ENFORCED subagent cap**
- **Found during:** Task 1 (`tests/agents/test_fanout.py::test_parallel_mode_observes_concurrency_cap`)
- **Issue:** The 11-01 test spawns 10 self×N workers to assert the CONCURRENCY cap (≤4 live). It was written when `reserve()` was a no-op stub; once 11-04's reserve ENFORCES, 10 subagents > the default 8-subagent cap raises `BudgetExceeded` before the concurrency assertion can run. The test's INTENT (concurrency, not total-count) was unaffected by the enforcement — only its fixture needed the headroom.
- **Fix:** Raised the test's subagent budget to `max_subagents=10` (via `BudgetManager.from_limits(Limits(max_subagents=10))`) so the concurrency cap (still 4) is what the test exercises; added a `budget` kwarg to the test's `_make_ctx` helper. No production behavior change — the enforcement is correct; the legacy test fixture is updated to reflect it.
- **Files modified:** `backend/tests/agents/test_fanout.py`
- **Committed in:** `79919d5` (Task 1 commit)

**Total deviations:** 1 auto-fixed (1 test-fixture bug). **Impact:** none on production behavior — the deviation is a legacy-test fixture update made necessary BY the (correct) enforcement landing.

## Issues Encountered
- The user/db Limits-trust tests initially failed because `single_shot` is not a `user_allowed` strategy, so the step-level strategy-trust check fired before the Limits check. Resolved by registering a throwaway `user_allowed=True` strategy in the test (the existing `_register_user_allowed_exec_palette` precedent) so the test isolates the Limits rule.

## Known Stubs
None — `reserve()` now ENFORCES (the 11-01 stub seam is closed); the snapshot persists through the real `_dual_write`-adjacent ScopedStore path; the partial-results surfacing reads the real per-run `ArtifactGraph`. The token + wall-clock check-at-boundary `note_*` methods are wired and tested at the manager level; their per-worker invocation on the live path is the natural 11-05 cancel/teardown extension (the abort path already aborts on a reserve breach — the primary fork-bomb vector).

## Threat Flags
None — the only new surface is the per-workspace aggregate read (`workspace_budget_spent`, owner+workspace-scoped default-deny — already in the plan's `<threat_model>` T-11-04-04) and the `budget_snapshot_json` write (the already-allowed 0014 column, default-deny / cross-owner no-op — T-11-04-05). Both are tested.

## User Setup Required
None — no external service configuration (zero new packages this phase; T-11-04-SC accept). The `WORKSPACE_BUDGET_*` env vars are an OPTIONAL operator seam (default unset = uncapped).

## Next Phase Readiness
- The budget spine is live behind ONE enforcement point (INV-12): `run_fanout` calls `ctx.budget.reserve` first; `BudgetExceeded` aborts gracefully with the 11-03 fragments surfaced.
- 11-05 (cancel teardown) preserves "completed fragments' artifacts" on a mid-flight cancel — the SAME `write_fragment_artifact` provenance + the SAME `_collect_partial_fragments` surfacing this plan added on the abort path; the snapshot already persists on cancel.

## Self-Check: PASSED

`backend/tests/agents/test_budget.py` exists on disk; both task commits (`79919d5`, `732ec9a`) are present in git history. Plan verification suite green: 83 passed (test_budget + test_compiler_trust + test_fanout + test_characterization_prototype + test_characterization_prototype_revision + test_banned_patterns); the wider parity set 158 passed / 6 skipped (5 characterization snapshots byte/event-identical with SNAPSHOT_UPDATE unset, migration-ledger + registry_capabilities + merge + subagent_runs green); lint-imports 4 kept / 0 broken. Acceptance greps: `raise BudgetExceeded`=6, defaults=4, `_compile_limits` present, `workspace_budget_spent` present, `budget_snapshot` in engine=6, `persist_budget_snapshot` in kernel_services=1.

---
*Phase: 11-engine-owned-fan-out-merge-5*
*Completed: 2026-06-11*
