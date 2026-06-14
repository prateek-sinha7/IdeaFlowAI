---
phase: 22-capability-surfacing-and-user-empowerment-universal-runtime
plan: 03
subsystem: database
tags: [alembic, sqlalchemy, workflow-run, deliverable, mimetype, reopen, fastapi, react]

# Dependency graph
requires:
  - phase: 18-01
    provides: "engine emits deliverable_mimetype/deliverable_filename on pipeline_complete; both keys added to _VOLATILE_STRIP_KEYS"
  - phase: 18-03
    provides: "shared deriveDeliverableMimetype reopen heuristic + GenericDeliverable channel on both reopen surfaces"
  - phase: 21
    provides: "migration 0021 additive batch_alter shape (the mirror analog); WorkflowRun owner_id/workspace_id scope"
provides:
  - "deliverable_mimetype + deliverable_filename nullable columns persisted on WorkflowRun (D-19)"
  - "additive migration 0022 (down_revision 0021), single-head"
  - "history-reopen drives the deliverable mimetype from the persisted value (binary deliverables re-render true to type)"
  - "resolveReopenMimetype shared FE helper (persisted-first, heuristic fallback)"
affects: [22-07-UXFIX-04-generic-primary-renderer]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Additive nullable column + batch_alter migration mirroring 0021 (owner_id/workspace_id scope already on the row)"
    - "Persisted-value-first reopen resolution with a text-heuristic legacy-NULL fallback (parity)"

key-files:
  created:
    - backend/alembic/versions/0022_workflow_run_deliverable_mimetype.py
  modified:
    - backend/app/models/workflow.py
    - backend/app/api/websocket.py
    - backend/app/api/runs.py
    - backend/tests/unit/test_deliverable_mimetype.py
    - frontend/src/types/index.ts
    - frontend/src/lib/api.ts
    - frontend/src/app/dashboard/page.tsx
    - frontend/src/components/history/WorkflowHistory.tsx
    - frontend/src/types/deriveDeliverableMimetype.test.ts

key-decisions:
  - "Persist the engine-emitted deliverable shape at BOTH websocket finalize sites (bg-task primary + safety fallback), keyed generically on the emitted values — no workflow-name branch (SC-001)"
  - "resolveReopenMimetype treats an empty/whitespace persisted mimetype as absent → heuristic fallback (robust against blank rows)"
  - "Surface the two columns on WorkflowRunResponse (response_model) so both the list and detail endpoints carry them — both reopen entry paths get the field"

patterns-established:
  - "Pattern 1: additive nullable column persisting an already-emitted, already-VOLATILE-stripped engine value → INV-3-safe by construction"
  - "Pattern 2: a single shared resolution helper consumed by both reopen surfaces so they cannot diverge (extends the 18-03 shared-helper invariant)"

requirements-completed: [UXFIX-02]

# Metrics
duration: ~14min
completed: 2026-06-14
---

# Phase 22 Plan 03: Persist Deliverable Mimetype + Persisted-First History-Reopen Summary

**Two additive nullable WorkflowRun columns (`deliverable_mimetype`/`deliverable_filename`) via migration 0022, persisted from the engine-emitted pipeline_complete shape, with history-reopen now driven by the persisted value so a binary deliverable (e.g. `application/zip`) re-renders faithfully instead of being re-sniffed from text.**

## Performance

- **Duration:** ~14 min
- **Completed:** 2026-06-14
- **Tasks:** 2
- **Files modified:** 9 (1 created, 8 modified)

## Accomplishments
- Added `deliverable_mimetype` + `deliverable_filename` nullable columns on `WorkflowRun` (D-19) and the single additive migration `0022` (`down_revision = "0021"`, single-head, `batch_alter_table` add_column) — applied clean to head.
- Persisted the engine-emitted deliverable shape at both websocket finalize sites (bg-task primary + safety fallback), keyed generically on the emitted values (SC-001 — 0 workflow-name branches).
- Surfaced the two columns on `WorkflowRunResponse` and threaded them through the FE `WorkflowRun` type + `normalizeWorkflowRun`.
- Closed the P18 reopen gap: a new `resolveReopenMimetype` shared helper prefers the persisted mimetype and falls back to the `deriveDeliverableMimetype` text heuristic only for legacy NULL rows; both reopen surfaces (page.tsx generic channel + WorkflowHistory detail) call it so they cannot diverge.
- INV-3 held: both keys remain in `_VOLATILE_STRIP_KEYS`; all 5 characterization goldens stayed byte/event-identical (no SNAPSHOT_UPDATE).

## Task Commits

1. **Task 1: WorkflowRun columns + migration 0022 + persist on finalize** - `5b950911` (feat)
2. **Task 2: persisted-first history-reopen resolution** - `7c4a50c5` (feat)

## Files Created/Modified
- `backend/alembic/versions/0022_workflow_run_deliverable_mimetype.py` - additive migration adding the two nullable columns (mirrors 0021)
- `backend/app/models/workflow.py` - `deliverable_mimetype`/`deliverable_filename` nullable columns on `WorkflowRun`
- `backend/app/api/websocket.py` - capture the emitted deliverable shape on pipeline_complete; persist at the bg-task + fallback finalize sites
- `backend/app/api/runs.py` - surface the two columns on `WorkflowRunResponse`
- `backend/tests/unit/test_deliverable_mimetype.py` - column-existence + additive-migration source assertions
- `frontend/src/types/index.ts` - `resolveReopenMimetype` helper + `deliverableMimetype`/`deliverableFilename` on `WorkflowRun`
- `frontend/src/lib/api.ts` - thread the persisted columns through `RawWorkflowRun` + `normalizeWorkflowRun`
- `frontend/src/app/dashboard/page.tsx` - reopen generic channel resolves via `resolveReopenMimetype` (persisted-first)
- `frontend/src/components/history/WorkflowHistory.tsx` - detail-view reopen resolves via `resolveReopenMimetype`
- `frontend/src/types/deriveDeliverableMimetype.test.ts` - persisted-first resolution tests (zip wins; empty-string-as-absent; legacy fallback)

## Decisions Made
- Persisted at both websocket finalize sites (primary bg-task + safety fallback) so the columns are written on every terminal path, not just the happy path.
- `resolveReopenMimetype` treats empty/whitespace persisted values as absent, falling back to the heuristic — defensive against blank rows.
- Both reopen entry paths (list-cached run and `getWorkflow` detail) carry the field because the columns are on the shared `WorkflowRunResponse` used by both endpoints.

## Deviations from Plan

None - plan executed exactly as written. (One additive touch within scope: `runs.py WorkflowRunResponse` was extended so the persisted columns reach the FE — the plan's reopen path requires the FE to read them; this is the necessary serialization seam, not new scope.)

## Issues Encountered
None.

## Verification Evidence
- `tests/unit/test_deliverable_mimetype.py` — 19 passed (incl. new column-existence + additive-migration assertions).
- `WorkflowRun.__table__.columns` includes both columns (nullable); `alembic upgrade head` → `0022 (head)`, single head.
- INV-3: 5 characterization goldens (prototype, od_prototype, prototype_revision, od_ppt, app_builder) + `test_migration_ledger.py` — 33 passed, 7 skipped, byte/event-identical (no SNAPSHOT_UPDATE).
- `lint-imports` — 4 contracts kept, 0 broken.
- FE: `npx tsc --noEmit` clean for all touched files (only the 2 pre-existing `e2e/fixtures/mockApi.ts` TS2352 casts remain — out of scope); `deriveDeliverableMimetype.test.ts` 13 passed; `src/components/history` 17 passed.
- SC-001: grep over the websocket persist site + both reopen surfaces → 0 workflow-name branches gating the deliverable resolution.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The persisted mimetype is now available for UXFIX-04 (22-07) generic-primary renderer to dispatch on the declared/resolved type on reopen.
- No blockers.

## Self-Check: PASSED

- FOUND: backend/alembic/versions/0022_workflow_run_deliverable_mimetype.py
- FOUND: backend/app/models/workflow.py
- FOUND: frontend/src/types/index.ts
- FOUND commit: 5b950911
- FOUND commit: 7c4a50c5

---
*Phase: 22-capability-surfacing-and-user-empowerment-universal-runtime*
*Completed: 2026-06-14*
