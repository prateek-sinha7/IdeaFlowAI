---
phase: 32-run-screen-redesign-a4
plan: 03
subsystem: api
tags: [fastapi, sqlalchemy, audit, idor, owner-scoping, read-only]

# Dependency graph
requires:
  - phase: 08-*/10-* (workflow-engine-decoupling)
    provides: engine-populated gate_events / validation_results / exec_runs tables (alembic 0016/0018) with owner_id + workspace_id + run_id
provides:
  - GET /api/runs/{id}/gate-events — owner-scoped governance-gate audit rows
  - GET /api/runs/{id}/validation-results — owner-scoped validator-run audit rows
  - GET /api/runs/{id}/exec-runs — owner-scoped exec-invocation audit rows (truncated output_digest only)
  - Shared _owner_gate_or_404 Layer-1 gate helper on the /api/runs router
affects: [32-09 (Audit tab FE repoint off hook_runs onto these 3 endpoints)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Two-layer owner gate: Layer 1 WorkflowRun.user_id==principal ->404, Layer 2 child owner_id re-filter (defense-in-depth)"
    - "IDOR resolves to 404 (never 403, never 200 with foreign rows) — P13/P25"
    - "Additive read-only audit reads: app-side ORM query, inline-dict projection per table (mirrors get_hook_runs), no new reader seam"

key-files:
  created:
    - backend/tests/agents/test_audit_endpoints.py
  modified:
    - backend/app/api/runs.py

key-decisions:
  - "Queried the child ORM directly app-side (like get_hook_runs) instead of adding an unused ScopedStore.read_validation_results reader — an unused reader would be dead code (INV-3). gate_events/exec_runs readers already exist in authz.py but get_hook_runs's precedent reads ORM directly, so no authz.py change."
  - "Owner gate keys on WorkflowRun.user_id (the principal), NEVER the nullable owner_id."
  - "exec-runs projection surfaces output_digest as-stored (truncated) and no raw-output field of any name."

patterns-established:
  - "Pattern: _owner_gate_or_404(db, workflow_id, user_id) shared helper for owner-scoped run reads on the /api/runs router"

requirements-completed: [SC-3]

# Metrics
duration: ~15min
completed: 2026-07-08
---

# Phase 32 Plan 03: Audit-Tab Read Endpoints Summary

**Three additive, read-only, owner-scoped audit endpoints (gate-events / validation-results / exec-runs) on the /api/runs router that repoint the Audit tab onto real governance/validation/exec data with an IDOR->404 two-layer owner gate and exec-digest-only projection.**

## Performance

- **Duration:** ~15 min
- **Completed:** 2026-07-08
- **Tasks:** 2 (TDD RED scaffold + GREEN implementation)
- **Files modified:** 2 (1 created, 1 modified)

## Accomplishments
- `GET /api/runs/{id}/gate-events`, `/validation-results`, `/exec-runs` — 3 endpoints on the existing `/api/runs` router (no new registration; mounted at main.py).
- Two-layer owner gate cloned from `get_hook_runs`: Layer 1 gates the run by `WorkflowRun.user_id == current_user.id` → 404; Layer 2 re-filters child rows by `owner_id`.
- `exec-runs` surfaces only the truncated `output_digest` column — asserted to leak no raw-output field (ASVS V7).
- 17-case owner-scope / IDOR-404 / projection / auth-required test suite, RED-then-GREEN.

## Task Commits

1. **Task 1: Owner-scope + IDOR→404 test suite (Wave-0 RED scaffold)** — `d106940e` (test)
2. **Task 2: Implement the 3 read-only owner-scoped audit endpoints** — `f0f96ea2` (feat)

_TDD: RED (test) committed first observed failing 11/17; GREEN (feat) committed with 17/17 passing._

## Files Created/Modified
- `backend/tests/agents/test_audit_endpoints.py` — created; TestClient + in-memory-SQLite harness (cloned from tests/unit/test_runs_api_artifacts.py); owner-rows/ordering/projection, cross-owner→404, missing→404, own-rows-not-foreign, exec-digest-only, and unauth→401/403 cases.
- `backend/app/api/runs.py` — added `_owner_gate_or_404` helper + `get_gate_events` / `get_validation_results` / `get_exec_runs` handlers after `get_hook_runs` (L1065). GateEvent/ValidationResult/ExecRun already imported (L34-41).

## Decisions Made
- **No authz.py change / no new reader seam.** The plan allowed EITHER adding `ScopedStore.read_validation_results` for symmetry OR querying `ValidationResult` directly app-side. The handlers mirror `get_hook_runs`, which reads its ORM model directly (it does NOT use the existing `read_gate_events`/`read_exec_runs` scoped readers). Adding a `read_validation_results` reader that no handler calls would be dead code, violating INV-3 (no dual implementations / no dead code). Chose the direct app-side ORM query for all three — fully additive and import-linter-safe (`app.api` is the legal caller; `agents.*→app` never introduced).
- **Owner gate keys on `user_id`, never the nullable `owner_id`** (P13/P25) — the run gate uses the authenticated principal.

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
- The trivial cross-owner/missing-404 cases pass even against a not-yet-implemented route (FastAPI returns 404 for an unknown path), so RED showed 11/17 failing rather than all. The load-bearing security proofs — `test_owner_sees_only_own_rows_not_foreign` (foreign-row leak) and `test_unauthenticated_is_rejected` — DID fail in RED and pass in GREEN, so the owner-scope contract is genuinely exercised, not vacuously satisfied.

## Verification

- `cd backend && python3.11 -m pytest tests/agents/test_audit_endpoints.py -q` → **17 passed, 1 warning in 0.40s**.
- `/opt/homebrew/bin/lint-imports` → **Contracts: 4 kept, 0 broken.**
- `git diff --name-only` (code) → `backend/app/api/runs.py` only (test file already committed); **NO alembic/migration file, NO new table.**
- Owner gate confirmed keyed on `WorkflowRun.user_id` (not `owner_id`).

## Next Phase Readiness
- Endpoint half of SC-3 complete. Plan 32-09 (Audit tab) can repoint the FE off `hook_runs` onto these three endpoints (envelope keys `gate_events` / `validation_results` / `exec_runs`).
- No blockers. Live-server verification not required (offline TestClient covers the owner-scope/IDOR/projection contract).

---
*Phase: 32-run-screen-redesign-a4*
*Completed: 2026-07-08*

## Self-Check: PASSED

- test_audit_endpoints.py, runs.py, 32-03-SUMMARY.md all present on disk
- Task commits d106940e (test) + f0f96ea2 (feat) present in git log
