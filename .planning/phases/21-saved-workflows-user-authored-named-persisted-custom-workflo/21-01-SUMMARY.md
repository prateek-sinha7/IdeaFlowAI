---
phase: 21-saved-workflows-user-authored-named-persisted-custom-workflo
plan: 01
subsystem: api
tags: [fastapi, sqlalchemy, alembic, postgres, crud, idor, entitlements]

# Dependency graph
requires:
  - phase: 03/05 (WorkflowDefinition + workflows table)
    provides: the dormant `workflows` table (source="file"/"user") the saved-workflow spine reuses
  - phase: 06 (model policy)
    provides: ModelCatalog().ids() + _validate_model_overrides predicate reused at save time
provides:
  - WorkflowDefinition +base_pipeline_type +model_overrides (2 additive nullable columns)
  - additive migration 0021 (down_revision=0020, batch_alter add_column, ix_workflows_owner_source), reversible
  - owner-scoped /api/user-workflows CRUD router (POST/GET/GET{id}/PATCH{id}/DELETE{id}) with save==launch validation
  - removal of the dead _persist_workflow_definition engine writer (INV-12 completion)
  - backend test suite (CRUD/IDOR-404/validation-422/duplicate-name/schema/migration-reversibility)
affects: [21-02, 21-03, saved-workflows-frontend, catalog]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Reuse the dormant workflows table for source='user' rows (no new table, INV-12)"
    - "Save-time validation reuses the EXACT launch predicates (save == launch, SECURITY-REVALIDATE)"
    - "Owner-scoped CRUD with IDOR->404 (id==:id AND user_id==current_user.id AND source=='user')"
    - "Additive batch_alter_table add_column migration (first batch-add-column in the repo)"

key-files:
  created:
    - backend/alembic/versions/0021_saved_user_workflows.py
    - backend/app/api/user_workflows.py
    - backend/tests/unit/test_user_workflows.py
  modified:
    - backend/app/models/workflow_definition.py
    - backend/app/main.py
    - backend/agents/execution_engine/engine.py

key-decisions:
  - "Persist `description` in the existing `constitution_ref` column (no schema add) since only 2 cols were sanctioned"
  - "Entitlement deny -> 403 (not 422) — fail-fast before any insert, mirroring the launch gate semantics"
  - "Duplicate name -> 409 Conflict (API-level per-user uniqueness, NOT a DB constraint on the shared table)"

patterns-established:
  - "Pattern 1: save==launch — POST/PATCH re-run SUPPORTED_PIPELINE_TYPES + allowed_custom_agent_ids + ModelCatalog two-check + can_run_pipeline so a saved row can never carry something launch rejects"
  - "Pattern 2: owner-stamp on insert — user_id=owner_id=workspace_id=current_user.id, source='user', artifact_edges='[]'"

requirements-completed: [REUSE-MANDATE, REUSE-TABLE-INV12, ADDITIVE-MIGRATION, CRUD-OWNER-SCOPED, SAVE-FROM-BOTH, LAUNCH-EXISTING-PATH, INV-3, SC-001, PORTS-ADAPTERS, SECURITY-REVALIDATE]

# Metrics
duration: ~13min
completed: 2026-06-14
---

# Phase 21 Plan 01: Saved Workflows Backend Spine Summary

**Owner-scoped `/api/user-workflows` CRUD persisting saved workflows as `source="user"` rows in the REUSED `workflows` table (+2 additive nullable cols via migration 0021), with save-time validation mirroring the launch predicates and the dead `_persist_workflow_definition` engine writer removed (INV-12).**

## Performance

- **Duration:** ~13 min
- **Started:** 2026-06-14T12:06:00Z
- **Completed:** 2026-06-14T12:19:30Z
- **Tasks:** 3
- **Files modified:** 6 (3 created, 3 modified)

## Accomplishments
- Added 2 additive nullable columns (`base_pipeline_type`, `model_overrides`) to `WorkflowDefinition` + reversible migration `0021` (`down_revision="0020"`, `batch_alter_table` add_column, `ix_workflows_owner_source`) — proven reversible offline (upgrade→downgrade→upgrade).
- Removed the dead, custom-only `_persist_workflow_definition` engine writer + its only call site (INV-12), with the 5 characterization goldens + manifest parity staying byte-identical (INV-3 proven, SNAPSHOT_UPDATE unset).
- Built the owner-scoped `/api/user-workflows` CRUD router (POST/GET/GET{id}/PATCH{id}/DELETE{id}); every handler `Depends(get_current_user)`, IDOR→404, save-time validation reuses the launch predicates verbatim (SUPPORTED_PIPELINE_TYPES, allowed_custom_agent_ids, ModelCatalog two-check, can_run_pipeline gate), per-user name uniqueness (409); registered in `main.py`; lint-imports 4/0.
- 16 backend tests green: owner-stamped create, 422 validation (bad base/agent/model + non-member override), 403 entitlement, 409 duplicate name, list-scoping (file + other-user excluded), cross-owner GET/PATCH/DELETE→404, 204 delete, schema + offline migration reversibility.

## Task Commits

Each task was committed atomically:

1. **Task 1: 2 nullable cols + migration 0021 + remove dead engine writer (INV-12)** - `014c0959` (feat)
2. **Task 2: owner-scoped /api/user-workflows CRUD + register in main.py** - `9d733d54` (feat)
3. **Task 3: backend CRUD/IDOR/validation/duplicate-name/schema tests + goldens parity** - `d1d2ab3a` (test)

_Note: Task 3 (tdd) produced a single test commit — the router under test was landed in Task 2 (atomic-per-task scheme), so the test gate validated rather than red/green-drove it._

## Files Created/Modified
- `backend/app/models/workflow_definition.py` - +`base_pipeline_type` (String, nullable) +`model_overrides` (JSON, nullable)
- `backend/alembic/versions/0021_saved_user_workflows.py` - additive 2-column migration + owner/source index; reversible; no new table
- `backend/app/api/user_workflows.py` - owner-scoped CRUD router with save==launch validation + self-id stamp
- `backend/app/main.py` - import + include `user_workflows_router`
- `backend/agents/execution_engine/engine.py` - DELETED `_persist_workflow_definition` method + its only call site
- `backend/tests/unit/test_user_workflows.py` - CRUD/IDOR(404)/validation(422)/duplicate-name/schema/migration tests

## Decisions Made
- **`description` stored in `constitution_ref`** — only 2 column adds were sanctioned (REUSE-TABLE-INV12), so the optional user description reuses the existing nullable `constitution_ref` column rather than adding a third column. (The column's prior semantic — a workflow-memory key — is unused for `source="user"` rows.)
- **Entitlement deny → 403**, validation failures → 422, duplicate name → 409 — distinct, fail-fast status codes; the entitlement gate runs before any insert so a denied save never leaves an orphan row.
- **`_validate_model_overrides` replicated locally** in the router (identical two-check logic to `websocket._validate_model_overrides`) rather than importing from `websocket.py` — keeps the app-layer router free of a websocket-module dependency while preserving byte-identical predicate semantics.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `create_table` token in migration docstring tripped the additive gate**
- **Found during:** Task 1 (migration verification)
- **Issue:** The acceptance gate `[ "$(grep -c 'create_table' …0021…)" = "0" ]` matched the literal string `create_table` inside the migration docstring's "no `create_table`" note, failing the robust gate despite the migration genuinely creating no table.
- **Fix:** Reworded the docstring ("no new table" instead of "no `create_table`") so the gate measures actual `op.create_table` usage (0), not prose.
- **Files modified:** backend/alembic/versions/0021_saved_user_workflows.py
- **Verification:** gate re-run → `create_table` count 0; reversibility check `REVERSIBLE_OK`.
- **Committed in:** 014c0959 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Cosmetic docstring wording only; the migration shape is exactly as planned. No scope creep.

## Issues Encountered
None — the router, model, and tests landed as specified; the `_FakeUser` test stub needed a `tier` attribute (the entitlement gate reads `current_user.tier`), added when writing the test harness.

## Known Stubs
None — every endpoint is wired to the real `WorkflowDefinition` ORM + the live registry/catalog/entitlement predicates. No placeholder data paths.

## User Setup Required
None — no external service configuration required. The migration applies via the existing alembic chain on the next `alembic upgrade head`.

## Next Phase Readiness
- Backend spine is complete: saved workflows persist owner-scoped, validate at save with the launch predicates, and the dead writer is gone (INV-12 complete).
- Plan 21-02 / 21-03 (frontend: NameWorkflowModal, "Your workflows" catalog section + kebab, api.ts CRUD fetchers, Save buttons, IdeaInputPage agent-preload) can consume the `/api/user-workflows` contract and the `UserWorkflowResponse` shape directly.
- No blockers. Launch path is unchanged (SC-001) and re-validates at run time (T-21-03).

## Self-Check: PASSED

- Files: `0021_saved_user_workflows.py`, `app/api/user_workflows.py`, `tests/unit/test_user_workflows.py` — all FOUND.
- Commits: `014c0959`, `9d733d54`, `d1d2ab3a` — all FOUND.

---
*Phase: 21-saved-workflows-user-authored-named-persisted-custom-workflo*
*Completed: 2026-06-14*
