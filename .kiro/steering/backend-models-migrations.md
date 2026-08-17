---
inclusion: fileMatch
fileMatchPattern: "backend/app/models/**,backend/alembic/**"
---

# Backend — Models & Migrations Domain

> Loaded when editing files under `backend/app/models/` or `backend/alembic/`. See `invariants.md` for hard constraints.

---

## Migration Chain (Q3 — additive only)

Head: **0030** (`0030_workflow_runs_user_created_index.py`, verified 2026-08-12). This number
drifts — read it, don't trust it: `ls backend/alembic/versions/ | sort | tail -1`.

| Migration | What it adds | Phase |
|-----------|-------------|-------|
| 0014 | `artifact_refs`, `workspaces`, `run_events`, `run_capabilities`; extends `workflow_runs` + `workflows` | Phase 5 |
| 0015 | DROP `workflow_artifacts` (sanctioned destructive change) | Phase 5 |
| 0016 | `validation_results`, `gate_events`, `hook_runs` | Phase 8 |
| 0017 | `repositories`, `workspaces.repo_id` FK, `mcp_credentials` | Phase 9 |
| 0018 | `exec_runs` | Phase 10 |
| 0019 | `subagent_runs` | Phase 11 |
| 0020 | `wave_runs` | Phase 12 |
| 0021 | +3 nullable cols on `workflows`: `base_pipeline_type`, `model_overrides`, `description` | Phase 21 |
| 0022 | +2 nullable cols on `workflow_runs`: `deliverable_mimetype`, `deliverable_filename` | Phase 22 |
| 0023 | +1 nullable col on `workflow_runs`: `selections_json` | Quick 260615-dzk |
| 0024 | UNIQUE constraints on `run_events` (`scope_event`, `scope_seq`) | Phase 29 |
| 0025 | `deep_link_nonces` table | Phase 43 |
| 0026 | +2 nullable cols on `subagent_runs`: `task_id`, `worker_index` | Phase 46 |

---

## Migration Rules

1. **Additive only** — add columns, add tables, add indexes. Never ALTER existing columns or DROP (except the sanctioned 0015).
2. Every new table carries `owner_id` + `workspace_id` NOT NULL (Q3).
3. Use `batch_alter_table` for adding columns to existing tables (SQLite compatibility).
4. Free-String `status` columns — **never** `sa.Enum` (breaks reversible down migrations).
5. Every migration must be reversible: `upgrade → downgrade → upgrade` must leave the schema identical.
6. Test reversibility offline against SQLite before shipping.
7. Always verify single-head: `alembic heads` should return exactly one head after your migration.

---

## Key Model Rules

### `WorkflowRun`
- **Owner-scoping key: `user_id`** — NOT the nullable backfilled `owner_id`.
- All API endpoints filter on `user_id == current_user.id`.
- Terminal output columns (`output`, `agent_outputs`, `token_usage`, `duration`, `deliverable_mimetype`, `deliverable_filename`, `completed_at`) are written by the launch driver AND the resume output-persist hook (Phase 43, BUG-R03 fix). If you touch either path, ensure both stay in sync.

### `WorkflowDefinition` (table: `workflows`)
- `source="file"` rows = engineer-authored built-in manifests (read-only from the API).
- `source="user"` rows = user-authored saved workflows (CRUD via `/api/user-workflows`).
- `manifest_json` column = compact per-step selections map for user workflows.
- **Do NOT add a `user_workflows` table** — that is INV-12; the reused `workflows` table is intentional (Phase 21 decision).

### `ArtifactRef`
- Content-addressed via `content_hash = sha256(content.encode()).hexdigest()`.
- `version` = 1-based monotonic per `(run_id, kind)`.
- `derived_from` = lineage link to the prior version (used by Redo, revision).
- `visibility="workspace"` for cross-run-readable producer writes (revision seed, clarifications).
- `_latest_typed_content` in `engine.py` selects by `max(version)` — never by insertion order.

### `RunEvent`
- `seq` is monotonic per run, from a single `itertools.count(1)` at the `execute()` emit boundary.
- `event_id` = UUID, idempotency key for FE dedup.
- `uq_run_events_scope_event` + `uq_run_events_scope_seq` unique constraints (migration 0024).
- `append_event_next_seq` in `authz.py` uses optimistic IntegrityError retry — the safe allocation path.

### `DeepLinkNonce` (table: `deep_link_nonces`, migration 0025)
- Single-use: consumed via atomic conditional UPDATE.
- Owner-scoped IDOR: cross-owner/cross-workspace → 404.
- Replaced the in-memory `_ISSUED_NONCES` set (deleted INV-12, Phase 43).

---

## `ScopedStore` — Default-Deny Pattern

`ScopedStore` in `agents/authz.py` is the SINGLE enforced default-deny read/write path.

```python
store = ScopedStore(owner_id=..., workspace_id=..., session=None)
# session=None → owned=True → connection released in finally (BUG-004 fix)
```

- `_scope_with_visibility` for ArtifactRef reads: `owner_id == :o AND (workspace_id == :ws OR visibility IN ('workspace', 'public'))`
- `_scope_owner_ws` for run/workspace/event/caps reads
- Cross-owner → raises `PermissionError` (never swallowed — `assert_owns` is ABOVE the degrade try)
- `write_ref` rejects a falsy resolved owner

---

## Test Pattern for Migrations

```python
# SQLite reversibility test
def test_0026_reversible_offline(alembic_runner):
    alembic_runner.migrate_up_to("0026")
    alembic_runner.migrate_down_to("0025")
    alembic_runner.migrate_up_to("0026")
```
