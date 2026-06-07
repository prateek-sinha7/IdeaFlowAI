---
phase: 05-typed-artifacts-persistence-ownership-1b
plan: 02
subsystem: database
tags: [sqlalchemy, alembic, postgres, sqlite, orm, migration, ownership, persistence]

# Dependency graph
requires:
  - phase: 05-01
    provides: typed ArtifactGraph + ArtifactRef dataclass (agents/artifacts) — the in-memory shape this schema persists
provides:
  - artifact_refs / workspaces / run_events / run_capabilities tables (every row owner_id + workspace_id — AUTHZ-01)
  - workflow_runs extended with owner_id/workspace_id/source_run_id/plan_id/budget_snapshot_json
  - existing workflows table (WorkflowDefinition) extended with owner_id/workspace_id/source/manifest_json/version
  - Alembic revision 0014 (additive) + default-workspace backfill for historical runs
  - tests/unit/test_migration_0014.py (up/down/index/scope/backfill assertions)
affects: [05-03, 05-04, 05-05, 05-06]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Every new persistence table carries owner_id + workspace_id (default-deny scope substrate)"
    - "Hand-authored additive Alembic migration with op.batch_alter_table for SQLite/Postgres column-add parity"
    - "Inline data backfill inside the schema migration via op.get_bind() + SQLAlchemy core (works on both dialects)"

key-files:
  created:
    - backend/app/models/artifact_ref.py
    - backend/app/models/workspace.py
    - backend/app/models/run_event.py
    - backend/app/models/run_capabilities.py
    - backend/alembic/versions/0014_typed_artifacts_persistence.py
    - backend/tests/unit/test_migration_0014.py
  modified:
    - backend/app/models/workflow.py
    - backend/app/models/workflow_definition.py
    - backend/app/models/__init__.py

key-decisions:
  - "EXTENDED the existing workflows table (WorkflowDefinition) additively rather than creating a second workflows table (RESEARCH #5 collision)"
  - "Default-workspace backfill implemented INLINE in 0014 (D-03 discretion) rather than a separate 0014b revision"
  - "owner_id/workspace_id are NOT NULL on the 4 new tables (no unscoped row can persist) but nullable+backfilled on extended workflow_runs/workflows"
  - "NO workflow_artifacts DROP here — that destructive op is 0015 (plan 05-06), sequenced LAST"

patterns-established:
  - "owner_id + workspace_id on every new table = the uniform default-deny scope filter substrate"
  - "Workspace.workspace_id == its own id so the scope filter `workspace_id = :ws` holds for workspace reads too"
  - "Additive-only migration provable in isolation: upgrade-from-0013 + downgrade-to-0013 + backfill asserted by a Wave-0 test"

requirements-completed: [PERSIST-01, AUTHZ-01, ART-02, ART-04, PERSIST-03, CAPRUN-01]

# Metrics
duration: 7min
completed: 2026-06-07
---

# Phase 05 Plan 02: Typed Artifacts Persistence + Ownership Schema Summary

**Additive §18 persistence schema: 4 new owner/workspace-scoped tables (artifact_refs, workspaces, run_events, run_capabilities), extended workflow_runs + workflows, and hand-authored Alembic 0014 with a default-workspace backfill that scopes every historical run.**

## Performance

- **Duration:** ~7 min
- **Started:** 2026-06-07T20:06:24Z
- **Completed:** 2026-06-07T20:13:04Z
- **Tasks:** 2
- **Files modified:** 9 (6 created, 3 modified)

## Accomplishments
- Four new ORM models — `ArtifactRef` (`artifact_refs`), `Workspace` (`workspaces`), `RunEvent` (`run_events`), `RunCapabilities` (`run_capabilities`) — each carrying `owner_id` + `workspace_id` (AUTHZ-01), with the required indexes (`artifact_refs (run_id, kind)` + `(content_hash)`; `run_events (run_id, seq)`).
- Extended `workflow_runs` (+`owner_id`, `workspace_id`, `source_run_id`, `plan_id`, `budget_snapshot_json`) and the EXISTING `workflows` table / `WorkflowDefinition` (+`owner_id`, `workspace_id`, `source`, `manifest_json`, `version`) — no second `workflows` table created.
- Hand-authored additive Alembic revision `0014` (chained off `0013`) with an inline default-workspace backfill: one `workspaces` row per existing run, run scoped to `owner_id = user_id` + that workspace. Downgrade reverses cleanly to the `0013` schema.
- Wave-0 test `test_migration_0014.py` proves upgrade-from-0013, the new tables/columns/indexes, `owner_id`+`workspace_id` on every new table, the backfill (every existing run ends non-null scoped), and clean downgrade.

## Task Commits

Each task was committed atomically:

1. **Task 1: 4 new ORM models + extend workflow_runs & workflows + register in __init__** — `ffa1f7a` (feat)
2. **Task 2: 0014 migration + default-workspace backfill + Wave 0 up/down test** — `4cc722c` (feat)

**Plan metadata:** (final docs commit — SUMMARY/STATE/ROADMAP/REQUIREMENTS)

_Note: both TDD-flagged tasks landed as a single feat commit each, per the plan's stated commit message in each `<action>` (Task 1 verify is a structural import assertion; the behavioral test file is owned by Task 2)._

## Files Created/Modified
- `backend/app/models/artifact_ref.py` — `ArtifactRef` ORM model (table `artifact_refs`), inline `content` (D-01), lineage `parents`/`derived_from`, `visibility`/`retention` defaults, two indexes.
- `backend/app/models/workspace.py` — `Workspace` ORM model (table `workspaces`); `workspace_id` equals own `id` so the scope filter holds.
- `backend/app/models/run_event.py` — `RunEvent` ORM model (table `run_events`), `seq` + `event_id` for the engine sink/replay (05-04), `(run_id, seq)` index.
- `backend/app/models/run_capabilities.py` — `RunCapabilities` ORM model (table `run_capabilities`), `runtime` + Phase 6/8/9 forward JSON fields.
- `backend/app/models/workflow.py` — `WorkflowRun` extended with the 5 Phase-5 columns; `artifacts` relationship left pointing at `WorkflowArtifact` (deleted in 05-06).
- `backend/app/models/workflow_definition.py` — `WorkflowDefinition` extended additively (collision-safe, single `__tablename__`).
- `backend/app/models/__init__.py` — registered the four new models (import + `__all__`) for `Base.metadata`/Alembic visibility (Pitfall 5).
- `backend/alembic/versions/0014_typed_artifacts_persistence.py` — additive migration + inline backfill + clean downgrade.
- `backend/tests/unit/test_migration_0014.py` — Wave-0 up/down/index/scope/backfill suite.

## Decisions Made
- **Extend, don't duplicate `workflows`:** `WorkflowDefinition` already owns `__tablename__="workflows"` — added columns additively (RESEARCH #5); a second table would raise in SQLAlchemy and be rejected by Postgres.
- **Inline backfill in 0014 (D-03):** chose the inline data step over a separate `0014b` revision; implemented via `op.get_bind()` + SQLAlchemy core `select`/`insert`/`update` so it runs on SQLite and Postgres, guarded against zero existing rows.
- **NOT NULL scope on new tables, nullable on extended:** new tables forbid unscoped rows; extended `workflow_runs`/`workflows` stay nullable so `upgrade head` applies over existing rows, with the backfill filling them.
- **No destructive op:** the `workflow_artifacts` DROP is deferred to `0015` (05-06) after read-cutover + parity — `WorkflowArtifact` and `ArtifactRef` coexist during dual-write.

## Deviations from Plan

None — plan executed exactly as written. No deviation rules (1–4) triggered; no auth gates.

## Issues Encountered
- The full regression run (`tests/agents/ tests/unit/`) reported **8 pre-existing failures** unrelated to this plan, logged to `deferred-items.md` and left untouched per the SCOPE BOUNDARY rule:
  - `tests/unit/test_logout.py` (7) — registration returns 403 "Self-registration is disabled" (env/config gate).
  - `tests/unit/test_pipeline_cancel.py` (1) — `ExpiredTokenException` from a live Bedrock call (expired AWS token).
  - Scope confirmed: this plan touched only `app/models/*` and `alembic/versions/0014_*`; the 0014 test, the existing `test_alembic.py` drift/`check` suite, and `lint-imports` (3 contracts kept, exit 0) all pass — 918 passed overall.

## Threat Flags

None — no new security surface beyond the threat_model's registered T-5-* entries. The backfill (T-5-BACKFILL), clean downgrade (T-5-MIGRATE-DOWN), and NOT NULL scope columns (T-5-NULLOWNER) are all asserted/implemented as planned.

## Known Stubs

None — all models and the migration are fully wired. Forward-phase fields (`plan_id`, `budget_snapshot_json`, `manifest_json`, capability JSON columns) are nullable schema substrate populated by later phases (4/6/8/9/11), not stubs blocking this plan's goal.

## User Setup Required
None — no external service configuration required.

## Next Phase Readiness
- Schema substrate is live: 05-03 can build the typed store helper (`agents/authz.py`) querying these real tables/columns; 05-04/05-05 can populate them (engine seq sink → `run_events`, capability snapshot → `run_capabilities`, artifact writes → `artifact_refs`).
- 05-06 owns the destructive `0015` `workflow_artifacts` DROP after read-cutover + parity green.

---
*Phase: 05-typed-artifacts-persistence-ownership-1b*
*Completed: 2026-06-07*

## Self-Check: PASSED
- All 6 created files present on disk; both task commits (`ffa1f7a`, `4cc722c`) present in git history.
- `test_migration_0014.py` (2 tests) + `test_alembic.py` (5 tests) green; `lint-imports` exit 0.
