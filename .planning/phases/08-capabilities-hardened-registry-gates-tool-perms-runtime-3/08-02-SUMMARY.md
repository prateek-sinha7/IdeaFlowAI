---
phase: 08-capabilities-hardened-registry-gates-tool-perms-runtime-3
plan: 02
subsystem: gates-persistence
tags: [gates, gate-handler, validation-gate, security-gate, additive-migration, owner-scoped, hexagonal]

# Dependency graph
requires:
  - phase: 08-capabilities-hardened-registry-gates-tool-perms-runtime-3
    plan: 01
    provides: "@register/discover() self-registering registry + user_allowed trust flags + the single canonical map_severity (validators/severity.py)"
  - phase: 05-typed-artifacts-persistence-ownership-1b
    provides: "ScopedStore default-deny owner/workspace-scoped writer + additive-migration pattern (0015 head) + ExecutionContext.scoped_store/owner_id/workspace_id"
  - phase: 07-prototype-as-manifest-parity-proof-sc-001-2
    provides: "KernelServices ctx.runner handle + the engine per-step dispatch loop + _run_review_gate (human gate parity source)"
provides:
  - "GateHandler registry: human/validation/approval/security resolve via CapabilityRegistry().resolve('gate', name)"
  - "GateOutcome contract (pass|block|wait_human + additive events) in gates/base.py"
  - "Real Validation_Gate (GATE-02): runs declared validators, imports the single map_severity, block-critical/warn-non-critical, emits validation_warning"
  - "security gate default-denies exec/network/secrets (T-08-02-EoP); approval gate -> wait_human; human gate delegates to _run_review_gate (GATE-03 parity)"
  - "Engine step-boundary gate seam (_evaluate_gates): pre-step (security/approval/human) before strategy, post-step (validation) after; additive halt"
  - "Additive 0016 migration: validation_results/gate_events/hook_runs (each owner_id+workspace_id NOT NULL); down_revision 0015"
  - "ScopedStore.record_gate_event/read_gate_event (+ record_validation_result/record_hook_run for 08-04/08-07); KernelServices.record_gate_event + run_human_gate handles"
affects: [08-03-tool-perms, 08-04-validators, 08-07-hooks]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "GateHandler returns a GateOutcome value (outcome + additive events); the kernel owns the yield so gate impls stay simple async functions"
    - "Gate phase classification (pre vs post-step) keyed by a frozenset, default pre-step (fail-safe: evaluate before the work)"
    - "gate_events write reached through ctx.runner (KernelServices) -> ScopedStore so the gate impl never imports kernel/app (import-linter)"
    - "Additive owner/workspace table mirrors run_capabilities.py; no server_default on Python-default cols (keeps alembic check drift-clean)"

key-files:
  created:
    - "backend/app/models/validation_results.py"
    - "backend/app/models/gate_events.py"
    - "backend/app/models/hook_runs.py"
    - "backend/alembic/versions/0016_capability_hardening_tables.py"
    - "backend/agents/capabilities/gates/__init__.py"
    - "backend/agents/capabilities/gates/base.py"
    - "backend/agents/capabilities/gates/write.py"
    - "backend/agents/capabilities/gates/human.py"
    - "backend/agents/capabilities/gates/validation.py"
    - "backend/agents/capabilities/gates/approval.py"
    - "backend/agents/capabilities/gates/security.py"
    - "backend/tests/agents/test_gates.py"
    - "backend/tests/unit/test_migrations.py"
  modified:
    - "backend/app/models/__init__.py"
    - "backend/agents/authz.py"
    - "backend/agents/execution_engine/kernel_services.py"
    - "backend/agents/execution_engine/engine.py"
    - "backend/agents/capabilities/registry.py"
    - "backend/tests/agents/test_registry_capabilities.py"

key-decisions:
  - "GateHandler.evaluate returns a GateOutcome (value) not an async generator — the kernel's _evaluate_gates owns the yield, keeping gate impls simple + unit-testable"
  - "gate names approval/security added to the literal _KNOWN in registry.py (impl-free membership) so a manifest can reference them at compiler time; registry count test bumped 16->18 in lockstep (expected, NOT a snapshot re-baseline)"
  - "human gate delegates to the UNCHANGED _run_review_gate via a new KernelServices.run_human_gate handle; the existing inline _should_gate path in _run_agent is untouched (GATE-03 parity, no re-baseline)"
  - "validation_results/hook_runs ScopedStore writers land now (seam complete) though only gate_events is the live writer this plan; 08-04/08-07 are their callers"
  - "dropped server_default='0' from validation_results.attempt in the migration so `alembic check` reports no drift against the Python-side default=0 model column"

requirements-completed: [GATE-01, GATE-02, GATE-03]

# Metrics
duration: ~45min
completed: 2026-06-09
---

# Phase 8 Plan 02: GateHandler Registry + Real Validation_Gate + 0016 Migration Summary

**Stood up the `GateHandler` registry (human/validation/approval/security) evaluated in declared order at the engine step boundary, made the dead `Validation_Gate` real (block-critical / warn-non-critical, single imported `map_severity`), preserved human-gate `review_gate_*` parity by delegating to the unchanged `_run_review_gate`, and landed the additive `0016` migration with the three owner/workspace-scoped §18 tables — all 5 characterization snapshots byte/event-identical.**

## Performance

- **Duration:** ~45 min
- **Completed:** 2026-06-09
- **Tasks:** 3
- **Files modified:** 19 (13 created, 6 modified)

## Accomplishments

- **GATE-01 registry:** four `GateHandler` impls under `agents/capabilities/gates/` (`human`/`validation`/`approval`/`security`), each `@register("gate", …)` and resolvable via `CapabilityRegistry().resolve("gate", name)` after `discover()`. Each returns a `GateOutcome` (`pass | block | wait_human` + additive events) and writes a `gate_events` row via `ctx.runner.record_gate_event` (no kernel/app import).
- **GATE-02 real Validation_Gate:** resolves the step's declared `validators: [...]` from the registry (`resolve("validator", …)`), maps each issue's internal P0–P3 severity through the SHARED `map_severity` IMPORTED from `validators/severity.py` (08-01 single source — not a local table, not a stub), applies block-critical (CRITICAL → `block`) / warn-non-critical (residual → additive `validation_warning`, proceeds).
- **GATE-03 human parity:** the `human` gate delegates to a new `KernelServices.run_human_gate` which routes to the UNCHANGED `engine._run_review_gate`; the existing inline `_should_gate` → `_run_review_gate` path in `_run_agent` is untouched. All 5 characterization snapshots stay byte/event-identical (no re-baseline).
- **security/approval:** the `security` gate default-denies a step requesting `exec`/`network`/`secrets` (all OFF this phase) → `block` (T-08-02-EoP); `approval` → `wait_human`. Both `user_allowed=False` (engineer-only); `human`/`validation` `user_allowed=True`.
- **Engine step-boundary seam (D-03):** `_evaluate_gates` evaluates declared gates in order — pre-step (`security`/`approval`/`human`) before the strategy (a `block`/`wait_human` halts the step additively), post-step (`validation`) after. New `gate_*` events flow through the generic `websocket.py` forward additively; no existing event renamed/removed. A gate that raises is swallowed (a gate failure never aborts the run).
- **0016 additive migration (D-10):** one migration (`revision="0016"`, `down_revision="0015"`) adds `validation_results`/`gate_events`/`hook_runs`, each carrying `owner_id`+`workspace_id` (both NOT NULL, AUTHZ-01), with the §18 indexes. Writes go through the Phase-5 `ScopedStore` (default-deny) — proven by a cross-owner `read_gate_events` returning nothing (T-08-02-ID).

## Task Commits

1. **Task 1: 0016 migration + 3 §18 models + gate_events ScopedStore writer** — `6e458e6` (feat, TDD)
2. **Task 2: four GateHandler impls (human/validation/approval/security)** — `d74578f` (feat, TDD)
3. **Task 3: wire gate evaluation at the engine step boundary (additive; human parity)** — `009576c` (feat)

## Files Created/Modified

- `backend/app/models/{validation_results,gate_events,hook_runs}.py` — the three §18 additive models mirroring `run_capabilities.py` (UUID PK + run_id FK + owner_id/workspace_id NOT NULL + payload cols + §18 indexes).
- `backend/alembic/versions/0016_capability_hardening_tables.py` — additive migration, head chain `0015→0016`, no destructive alter, reversible downgrade.
- `backend/app/models/__init__.py` — register the three models on `Base.metadata`.
- `backend/agents/authz.py` — `ScopedStore.record_gate_event`/`read_gate_events` (live) + `record_validation_result`/`record_hook_run` (08-04/08-07 callers).
- `backend/agents/execution_engine/kernel_services.py` — `record_gate_event` (gates write via the handle) + `run_human_gate` (the GATE-03 delegate to `_run_review_gate`).
- `backend/agents/capabilities/gates/{base,write,human,validation,approval,security,__init__}.py` — the gate contract, the shared `gate_events` write helper, and the four impls.
- `backend/agents/execution_engine/engine.py` — `_evaluate_gates` + the pre/post-step gate evaluation in the dispatch loop.
- `backend/agents/capabilities/registry.py` — `gate` `approval`/`security` added to the literal `_KNOWN` (impl-free membership).
- `backend/tests/agents/test_gates.py` — 13 cases: resolution, security block/pass, approval wait_human, validation P0-block / P2-warn / map_severity / no-validators, + engine-seam pre/post/halt/raise-swallow/no-op.
- `backend/tests/unit/test_migrations.py` — upgrade-head creates the 3 tables, NOT NULL owner/workspace, scoped gate_events write + cross-owner default-deny, `0015→0016` chain.
- `backend/tests/agents/test_registry_capabilities.py` — lockstep `_EXPECTED_NAMES` + count `16→18` bump.

## Decisions Made

- **Gate outcome is a value, not a stream.** `evaluate` returns `GateOutcome(outcome, events)`; the engine's `_evaluate_gates` owns the yield. Keeps the four impls plain async functions, unit-testable without an engine, and the additive events flow through the existing generic forward.
- **`approval`/`security` in the literal `_KNOWN`.** So the compiler's impl-free membership path validates a manifest's `gates:[approval|security]` at compile time (not only after `discover()`); the registry drift-guard count test bumped 16→18 in lockstep (an expected membership growth, not a re-baseline).
- **Human gate delegates; inline path untouched.** The registered `human` gate is the additive registry-driven entry point routing to the SAME `_run_review_gate`; the existing `_run_agent` HITL flow is unchanged, so `review_gate_*` parity holds with zero snapshot edits.
- **Migration `attempt` has no server_default.** The model uses a Python-side `default=0`; emitting `server_default="0"` in the migration tripped `alembic check` drift. Dropping it keeps model↔migration in sync (the existing `test_upgrade_then_check_reports_no_drift` gate green).

## Deviations from Plan

None — all three tasks landed with the planned files, acceptance gates, and locked decisions (D-01/D-02/D-03/D-06/D-10, GATE-01/02/03, VALID-03). No deviation-rule auto-fixes were required.

The one in-plan adjustment (`server_default` drop on `validation_results.attempt`) is a normal model↔migration sync correction surfaced by the existing `alembic check` drift test, not a scope or parity deviation.

## Issues Encountered

- **`alembic check` server-default drift (Task 1).** `env.py` sets `compare_server_default=True`, so a migration `server_default="0"` on a column whose model declares only a Python-side `default=0` reports drift. Resolved by dropping the migration server_default — the model's Python default is the single source for that column. Documented as a pattern for the additive Phase-8 tables.
- **`ScriptDirectory.get_heads()` returns a list, not a tuple.** The 0016 head-chain assertion was adjusted to compare against a list.

## User Setup Required

None — no external service configuration; the migration runs offline against in-memory SQLite (and applies cleanly via `alembic upgrade head` on Postgres — additive only).

## Next Phase Readiness

- **08-03 (tool-perms):** the `security` gate + the `ToolPermissions` grant read are the enforcement seam tool-perms build on; the gate step-boundary seam is live.
- **08-04 (validators):** the real `html_static`/`html_render`/Tier validators register against `("validator", …)` and flow through the SAME `validation` gate path proven here (`resolve("validator", …)` + the imported `map_severity` + the block/warn policy); `ScopedStore.record_validation_result` + the `validation_results` table are ready to write.
- **08-07 (hooks):** `ScopedStore.record_hook_run` + the `hook_runs` table are ready; the additive-event + step-boundary patterns are established.
- All gates resolve, evaluate to `pass|block|wait_human`, and write `gate_events`; lint-imports (3 contracts kept), banned-pattern, migration-ledger, and the 5 characterization snapshots stay green.

## Self-Check: PASSED

- All 13 created + 6 modified files present on disk.
- All three task commits (`6e458e6`, `d74578f`, `009576c`) present in git history.
- Full verification suite (gates + migrations + 5 characterization + registry + alembic) = 73 passed, clean session.
- `lint-imports` 3 kept / 0 broken; `grep -c 'def map_severity'` = 1 (single source); `grep -c 'resolve(.gate.'` engine.py = 1.

---
*Phase: 08-capabilities-hardened-registry-gates-tool-perms-runtime-3*
*Completed: 2026-06-09*
