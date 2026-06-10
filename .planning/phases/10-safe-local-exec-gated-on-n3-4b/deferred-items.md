# Phase 10 — Deferred Items (out of scope)

Out-of-scope discoveries logged during execution. NOT fixed here (scope boundary:
only fix issues directly caused by the current task's changes).

## 10-01

- **Pre-existing `alembic check` drift on `workspaces.repo_id` FK** —
  `tests/unit/test_alembic.py::test_upgrade_then_check_reports_no_drift` was
  ALREADY FAILING on clean HEAD (verified via stash) before any 10-01 change.
  `alembic check` reports a `remove_fk` op for `fk_workspaces_repo_id_repositories`
  — the named FK that migration 0017 adds via `batch_alter_table` is not reflected
  in the `Workspace` ORM's `repo_id` column (declared without `ForeignKey(...)`), so
  autogenerate wants to drop it. This is a Phase 9 / migration-0017 artifact,
  unrelated to the exec_runs work. 10-01 confirmed it did NOT introduce a NEW drift:
  the `exec_runs.run_id` FK was added to the 0018 migration so `exec_runs` matches
  its ORM exactly (`test_migration_matches_models` passes; only the pre-existing
  `repo_id` diff remains). Revisit when the Phase 9 FK declaration is reconciled.
