"""0039 — ON DELETE CASCADE for the four purely-dependent user FKs.

Part of the Cognito-only auth migration (``.kiro/specs/login/prompt.md``
Phase 1, Decision 6's FK policy). Four tables hold rows that have no
meaning once their owning user is gone and no admin-facing audit value
worth preserving past the delete: ``revoked_tokens``, ``user_api_keys``,
``user_github_credentials``, and ``handoff_sessions`` (via
``issuer_user_id``). None of the four FKs to ``users.id`` currently declare
``ondelete=``, so a real FK-enforcing database (Postgres in every deployed
environment; SQLite in tests, since ``app/models/database.py`` turns on
``PRAGMA foreign_keys=ON``) rejects a user delete outright while any
dependent row survives.

``workflow_runs``, ``workflow_definitions``, ``workflow_memory``,
``user_agents``, and ``chat_sessions``(+``messages``) are deliberately
EXCLUDED from this migration — Decision 6 requires those to be deleted
explicitly, in dependency order, inside the same transaction as the user
delete (with per-table counts in the audit event), not silently cascaded.
That is an application-code change (``api/admin.py::delete_user``, Phase 3),
not a schema change.

Each FK is currently unnamed (relies on the dialect's default constraint
name). This migration looks up that name via reflection, drops it, and
recreates it with an explicit stable name and ``ondelete="CASCADE"`` — so a
future migration can reference the same name without re-reflecting.

Idempotent-safe: every step is guarded by an existence check, so a partial
prior application (or an environment where one of these FKs was already
hand-fixed) does not raise on re-run, consistent with 0028/0029's guard
pattern -- the docker entrypoint runs `alembic upgrade head` under `set
-eu`, so a raising migration crash-loops the container.

Revision ID: 0039
Revises: 0038
Create Date: 2026-09-12 00:05:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


# (table, column, new explicit constraint name)
_TARGETS = [
    ("revoked_tokens", "user_id", "fk_revoked_tokens_user_id"),
    ("user_api_keys", "user_id", "fk_user_api_keys_user_id"),
    ("user_github_credentials", "user_id", "fk_user_github_credentials_user_id"),
    ("handoff_sessions", "issuer_user_id", "fk_handoff_sessions_issuer_user_id"),
]


def _existing_fk_name(inspector, table: str, column: str) -> str | None:
    for fk in inspector.get_foreign_keys(table):
        if fk.get("referred_table") == "users" and column in fk.get(
            "constrained_columns", []
        ):
            return fk.get("name")
    return None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    for table, column, new_name in _TARGETS:
        if table not in existing_tables:
            continue
        inspector = sa.inspect(bind)  # re-inspect: prior iterations altered schema
        already_cascading = any(
            fk.get("name") == new_name for fk in inspector.get_foreign_keys(table)
        )
        if already_cascading:
            continue

        old_name = _existing_fk_name(inspector, table, column)
        with op.batch_alter_table(table) as b:
            if old_name:
                b.drop_constraint(old_name, type_="foreignkey")
            b.create_foreign_key(
                new_name, "users", [column], ["id"], ondelete="CASCADE"
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    for table, column, new_name in _TARGETS:
        if table not in existing_tables:
            continue
        inspector = sa.inspect(bind)
        has_cascade_fk = any(
            fk.get("name") == new_name for fk in inspector.get_foreign_keys(table)
        )
        if not has_cascade_fk:
            continue

        restored_name = f"fk_{table}_{column}_no_cascade"
        with op.batch_alter_table(table) as b:
            b.drop_constraint(new_name, type_="foreignkey")
            b.create_foreign_key(restored_name, "users", [column], ["id"])
