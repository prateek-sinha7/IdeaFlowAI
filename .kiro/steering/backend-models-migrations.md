---
inclusion: fileMatch
fileMatchPattern: "backend/app/models/**,backend/alembic/**"
---

# Backend — Models & Migrations Domain

> Loaded when editing files under `backend/app/models/` or `backend/alembic/`. See `invariants.md` for hard constraints.

---

## Migration Chain (Q3 — additive only)

Head: **0037** (`0037_collapse_od_prototype_label.py`, verified 2026-08-24). This number
drifts — read it, don't trust it, and read it from the LEDGER not the directory
listing: `cd backend && alembic heads`. It must print exactly ONE head.

`ls | tail -1` is not a substitute: it cannot see a duplicate revision ID, which
is how this chain has broken twice (see the collision table below).

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
| 0027 | +1 nullable col on `workflow_runs`: OD context | — |
| 0028 | repair of the 0024/0025 `run_events` uniqueness drift | — |
| 0029 | enforce `run_events` seq uniqueness after the 0028 repair | — |
| 0030 | `(user_id, created_at)` index on `workflow_runs` | KAN-131 |
| 0031 | Cognito identity mapping + token-validity revocation | Cognito |
| 0032 | +1 nullable col on `users`: `encrypted_cognito_refresh_token` | Cognito |
| 0033 | user API-key expiry | Cognito |
| 0034 | `users.mfa_verified_at` | Cognito |
| 0035 | make auth timestamp columns timezone-aware | Cognito |
| 0036 | composed workflow execution (saved-agent library, per-run gate selection) | — |
| 0037 | data-only: collapse the `od_prototype` run-label onto `prototype` | — |

### Revision-ID collisions (both already hit us)

Two branches independently took the same revision number off the same parent.
Alembic keeps ONE file under the duplicate name, silently drops the other from
the graph, and the ledger reports two heads — so `alembic upgrade head` fails
with *"Multiple head revisions are present"* and the container crash-loops.

| Collision | Resolution |
|---|---|
| `0031` taken by both the cognito branch and composed-workflow-execution | composed-workflow re-homed to `0036` on top of `0035` |
| `0032` taken by both `cognito_refresh_token_storage` and `collapse_od_prototype_label` | the collapse re-homed to `0037` on top of `0036` |

The rule both resolutions followed: **the revision already recorded in deployed
`alembic_version` rows keeps its ID**; the other one moves to the tip. Re-homing
is only safe for a migration whose effect is order-independent — the collapse
qualified because its `upgrade` is an idempotent `UPDATE ... WHERE col = :old`
and its `downgrade` is a no-op. A schema migration that depends on its parent's
state does NOT qualify; that one needs a real merge revision.

---

## Migration Rules

1. **Additive only** — add columns, add tables, add indexes. Never ALTER existing columns or DROP (except the sanctioned 0015).
2. Every new table carries `owner_id` + `workspace_id` NOT NULL (Q3).
3. Use `batch_alter_table` for adding columns to existing tables (SQLite compatibility).
4. Free-String `status` columns — **never** `sa.Enum` (breaks reversible down migrations).
5. Every migration must be reversible: `upgrade → downgrade → upgrade` must leave the schema identical.
6. Test reversibility offline against SQLite before shipping.
7. Always verify single-head: `alembic heads` should return exactly one head after your migration.
8. **New migrations must be idempotent** — guard every DDL statement so re-running
   against a database that already has the object is a no-op, not an error. Use
   `backend/migration_helpers.py`; enforced by
   `tests/unit/test_migration_idempotency.py`. See "Idempotency" below.
9. **Never edit a released migration.** Add a forward revision instead. Enforced by
   `scripts/migration_guard.py`. See "Why editing a released migration is silent" below.

---

## Idempotency (rule 8)

`docker-entrypoint.sh` runs `alembic upgrade head` under `set -eu` **before**
`exec uvicorn`. A raising migration therefore does not produce a failed deploy
step — it prevents the container from ever binding its port, i.e. a crash-loop.
The commonest cause is creating an object that already exists, which happens on
any database whose objects are present but whose revision is not stamped:

- the DDL applied but the `alembic_version` bump was lost (the 0024/0025 incident
  that 0028 exists to repair),
- an operator applied DDL by hand before the migration shipped,
- a revision was re-homed (0031→0036, 0032→0037) and databases recorded
  different IDs for the same DDL,
- a partial/failed downgrade left objects behind.

Write new migrations with the shared guards:

```python
import sqlalchemy as sa
from migration_helpers import add_column_if_missing, create_table_if_missing

def upgrade() -> None:
    add_column_if_missing("users", sa.Column("x", sa.Text(), nullable=True))
```

Available: `table_exists`, `column_exists`, `index_exists`,
`unique_constraint_exists`, `foreign_key_exists`, `create_table_if_missing`,
`add_column_if_missing`, `create_index_if_missing`,
`create_unique_constraint_if_missing`, and the `*_if_present` drop variants.

Note `if_not_exists=True` works on this Alembic version for
`create_index`/`create_table` only (0030 uses it) — **not** for `add_column` or
constraints, which is why those need reflection.

Adding a UNIQUE constraint additionally needs a duplicate-row precondition check
or it raises on real data; 0028's `_duplicate_group_count` + loud SKIP is the
reference pattern.

**Status: 27 of 35 existing revisions are NOT re-appliable** (verified
2026-08-26). They are frozen in `_LEGACY_NON_IDEMPOTENT` and exempt, because
retrofitting guards into a released migration cannot reach any database already
stamped past it. Re-appliable today: 0009, 0010, 0024, 0028, 0029, 0030, 0035,
0037. The ratchet only exercises revisions outside both frozen sets, so it costs
nothing until a migration is added.

---

## Why editing a released migration is silent (rule 9)

`alembic_version` stores a **revision ID, never a content hash**. So if the
database is at head `0037` and you edit revision `0032`:

- `alembic upgrade head` reads `0037`, concludes there is nothing to do, exits 0.
  **`0032` never executes.** The edit does not reach that database, and nothing
  reports an error.
- A database created *after* the edit (fresh dev box, new environment, CI) runs
  the new `0032` and gets the new schema.

The environments now disagree permanently. Making the DDL idempotent does **not**
help — idempotency protects code that runs, and this code never runs.

Critically, no schema-derived check can catch this: `alembic check`,
`upgrade`-from-scratch, and the populated-migration job all derive the schema by
*running the edited file*, so they agree with each other and disagree only with
production. Detection has to happen at the source level.

`alembic/versions.lock` pins a fingerprint per released revision — a sha256 over
the AST with docstrings stripped, so reformatting, comment and docstring edits do
**not** trip it; only a change to what the migration does.

```bash
cd backend
uv run python scripts/migration_guard.py --verify   # CI: retro-edit + dup-ID + single-head
uv run python scripts/migration_guard.py --update   # after ADDING a migration
```

Commit `alembic/versions.lock` **in the same change as the migration**, or the
guard fails with "new revisions are not pinned yet".

A revision counts as released once it lands on `dev`, because pushing to `dev`
triggers `deploy.yml` and migrations apply on container start.

**When the guard fires, the fix is a forward revision** — a new revision at the
tip that brings existing databases into line, guarded so it no-ops where they are
already correct. Revision 0028 is the worked example. Re-pinning via
`--allow-modified --reason "..."` is only for a revision that never left a local
branch.

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
