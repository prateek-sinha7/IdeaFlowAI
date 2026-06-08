---
phase: 06-model-policy-1c
plan: 04
subsystem: api
tags: [model-policy, model_overrides, allow-list, websocket, run_capabilities, security, MODEL-03]

# Dependency graph
requires:
  - phase: 06-01
    provides: ModelCatalog (kernel-pure authoritative model-id allow-list, ids())
  - phase: 06-03
    provides: ModelResolver + ExecutionContext.model_overrides (override tier reads this map)
provides:
  - run_pipeline accepts an optional per-agent model_overrides {agent_id → model_id} map
  - Ingress allow-list validation (model_id ∈ ModelCatalog.ids() AND agent_id ∈ run agents) rejecting unknown values before execute
  - model_overrides threaded into execute()/_execute_impl() and seeded onto ExecutionContext
  - Validated map persisted to run_capabilities.model_overrides at run entry ({} → SQL NULL)
affects: [phase-08-model-picker-ui, phase-11-budget-enforcement]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Ingress allow-list validation as a pure module-level predicate (_validate_model_overrides) — directly unit-testable without the async WS stack, mirroring the agent_ids predicate-test split"
    - "{} → None ('or None') persistence to keep nullable JSON columns NULL for the default case (INV-3 row parity)"

key-files:
  created: []
  modified:
    - backend/app/api/websocket.py
    - backend/agents/execution_engine/engine.py
    - backend/tests/unit/test_run_pipeline_validation.py
    - backend/tests/unit/test_run_capabilities.py

key-decisions:
  - "Validation lives in _handle_workflow_execution after the run's agent set is resolved (not in the message loop) — agent-membership check needs the resolved `agents`; still BEFORE engine.execute and WorkflowRun creation, so a bad payload starts no run"
  - "Reused the existing {\"type\":\"error\", ..., \"code\":\"invalid_model_override\"} event shape; no new error vocabulary invented"
  - "Threaded model_overrides into the main run_pipeline execute only, not the revision path (_handle_revision) — per RESEARCH Open Q2"
  - "Persist (ectx.model_overrides or None) so empty {} → SQL NULL (INV-3 parity); never a spurious non-null {} write"
  - "No new migration — run_capabilities.model_overrides column already exists (migration 0014); authz.record_capabilities already accepts it via **deferred (no signature change)"

patterns-established:
  - "Pure validation predicate + thin handler wrapper: the WS handler calls _validate_model_overrides(map, {spec.id for spec in agents}) and the unit suite drives the same predicate directly"

requirements-completed: [MODEL-03]

# Metrics
duration: 18min
completed: 2026-06-08
---

# Phase 6 Plan 04: model_overrides Ingress Validation + Persistence Summary

**Per-agent `model_overrides {agent_id → model_id}` accepted in the run_pipeline payload, allow-list-validated at ingress against `ModelCatalog.ids()` AND the run's agent set (rejecting unknown values before any run starts), threaded into `execute()`, and persisted to `run_capabilities.model_overrides` with `{}`→NULL parity — the phase's HIGH-threat security chokepoint.**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-06-08
- **Completed:** 2026-06-08
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Added `_validate_model_overrides` — the load-bearing allow-list mitigation (T-06-06 [HIGH] unknown model id + T-06-07 [MED] unknown agent id), rejecting with the existing `invalid_model_override` error event BEFORE `engine.execute` (no WorkflowRun created on rejection).
- Wired the `model_overrides` payload read in the `run_pipeline` handler (absent → `{}`, the only kind until Phase 8) and threaded it through `_handle_workflow_execution` → `engine.execute(model_overrides=…)`.
- Added the `model_overrides` param to `execute()`/`_execute_impl()` + forward, seeded `ectx.model_overrides` so the 06-03 resolver's override tier consumes the validated map.
- Persisted the validated map at run entry via the existing `ScopedStore.record_capabilities(model_overrides=(ectx.model_overrides or None))` — `{}`→SQL NULL for INV-3 row parity. No new migration.

## Task Commits

Each task was committed atomically:

1. **Task 1: model_overrides ingress + allow-list validation + error event** - `ac9d3a9` (feat)
2. **Task 2: execute() param + ctx seed + persist model_overrides at entry ({}→NULL)** - `bcc0103` (feat)

## Files Created/Modified
- `backend/app/api/websocket.py` - `_validate_model_overrides` helper; payload read; ingress validation block (after agent-set resolution, before WorkflowRun/execute); `model_overrides` arg on `_handle_workflow_execution` + the `engine.execute` call.
- `backend/agents/execution_engine/engine.py` - `model_overrides` param on `execute()` + `_execute_impl()` + the forward; `ectx.model_overrides` seed at ctx construction; `record_capabilities(model_overrides=(ectx.model_overrides or None))` at entry.
- `backend/tests/unit/test_run_pipeline_validation.py` - `TestModelOverrideValidation`: empty-noop, valid-pass, unknown-model-id reject, unknown-agent-id reject, model-id reject for valid agent, multi-bad fail-fast.
- `backend/tests/unit/test_run_capabilities.py` - override map persisted; `{}`→NULL row parity.

## Decisions Made
- **Validation placement:** inside `_handle_workflow_execution` immediately after the run's `agents` are resolved — the agent-membership check requires the resolved spec list; placement is still strictly before WorkflowRun creation and `engine.execute`, so a rejected payload starts no run.
- **Error shape reuse:** the existing `{"type":"error","chunk":None,"section":None,"data":{"error":…,"code":"invalid_model_override","recoverable":False}}` shape, not a new one.
- **Scope:** main `run_pipeline` execute only (not the revision path), per RESEARCH Open Q2.
- **Persistence:** `(ectx.model_overrides or None)` so the no-override default writes SQL NULL.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- The plan's `tests/agents/characterization/` path holds golden fixtures, not test functions (0 collected). The actual INV-3 characterization runners are `tests/agents/test_characterization_*.py` (prototype, app_builder, od_ppt, od_prototype, prototype_revision) — ran those instead: 10 passed, snapshots unchanged. No code impact.

## Verification Evidence
- `tests/unit/test_run_pipeline_validation.py -k override` → 6 passed (unknown model id AND unknown agent id both rejected; valid override passes).
- `tests/unit/test_run_capabilities.py -k model_overrides` → 2 passed (map persisted; `{}`→NULL).
- `tests/agents/test_characterization_*.py` → 10 passed (INV-3 parity, snapshots unchanged).
- `tests/agents/test_migration_ledger.py` → 6 passed / 1 skipped; `ls alembic/versions | grep -c 001[6-9]` → 0 (no new migration).
- `lint-imports` → 3 kept / 0 broken.
- `tests/unit/` → 491 passed, 8 failed — exactly the pre-existing environmental failures (`test_logout.py` ×7 + `test_pipeline_cancel.py` ×1, "Self-registration is disabled"); NO new failures introduced.

## Next Phase Readiness
- 06-05 (model fallback) is independent of this plan and unblocked.
- Phase 8 wires the frontend model picker to send `model_overrides`; the ingress contract + allow-list are ready.
- `cost_class` remains metadata-only — no budget enforcement until Phase 11 (intentionally out of scope here).

## Self-Check: PASSED

- FOUND: `.planning/phases/06-model-policy-1c/06-04-SUMMARY.md`
- FOUND commit: `ac9d3a9` (Task 1)
- FOUND commit: `bcc0103` (Task 2)

---
*Phase: 06-model-policy-1c*
*Completed: 2026-06-08*
