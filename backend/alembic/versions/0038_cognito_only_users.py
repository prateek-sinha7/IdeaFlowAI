"""0038 — Cognito-only users: drop local credentials, add status + pending
deletion tracking.

Part of the Cognito-only auth migration (``.kiro/specs/login/prompt.md``
Phase 1). Cognito is now the sole authentication authority: there is no
local bcrypt/HS256 credential path and no break-glass local admin. This
migration removes the columns that existed only to support that removed
path and hardens the remaining Cognito mapping.

PRE-FLIGHT (fails loudly, does not silently drop data): aborts if any
``users`` row has ``cognito_sub IS NULL``, a duplicated ``cognito_sub``, or
(on a database that still carries the pre-migration ``auth_provider``
column) ``auth_provider <> 'cognito'``. Every such row is listed by
``id``/``email`` in the raised error so an operator can run
``scripts/migrate_local_users_to_cognito.py --report`` (and then
``--link``/``--invite``) before retrying this migration. This is the load
-bearing safety net for this deployment: per the brief's Phase 0
verification, ``AUTH_PROVIDER`` is still ``local`` in SSM in every
environment and no environment has cut over yet, so the database may
contain local-auth rows from earlier dev/test runs (e.g.
``seed_test_users.py``) even though there has never been a real production
cutover.

Schema changes:

* ``cognito_sub``: made ``NOT NULL`` (unique constraint/index already exist
  from migration 0031 and are left as-is).
* ``password_hash``: dropped. No password is stored anywhere in this
  application after this migration.
* ``auth_provider``: dropped. There is only one provider now; the column
  would just be a constant "cognito" that nothing reads.
* ``status`` (String(20), NOT NULL, default "active"): new. Distinguishes an
  active account from one an admin has disabled or that
  ``scripts/reconcile_cognito_users.py --fix-disabled`` has confirmed is
  gone/disabled at the provider. The credential verifier rejects
  ``status != 'active'`` regardless of token validity (Phase 2).
* ``pending_cognito_deletions`` (new table): durable retry queue for a user
  delete whose local-DB transaction succeeded but whose ``AdminDeleteUser``
  call failed (network/throttle) after the user was already disabled +
  globally signed out. ``scripts/retry_cognito_deletions.py`` (Phase 3)
  drains this table.

``downgrade()`` restores the SHAPE only (nullable ``cognito_sub``, re-added
``password_hash``/``auth_provider`` columns, dropped ``status``/
``pending_cognito_deletions``) — it cannot restore password data that was
never stored after this migration ran, and does not attempt to. Downgrading
past this revision in an environment that has taken any Cognito-only login
is UNSUPPORTED: every row's ``password_hash`` would come back NULL and
``auth_provider`` would come back to its column default ("local"), which
does not match any user's real state. This mirrors 0031's own downgrade
guard (it already refuses to restore ``password_hash NOT NULL`` over a
Cognito-native row); this migration's downgrade is the far side of the same
one-way door.

Revision ID: 0038
Revises: 0037
Create Date: 2026-09-12 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

from migration_helpers import (
    add_column_if_missing,
    column_exists,
    drop_column_if_present,
    create_table_if_missing,
    create_index_if_missing,
)

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def _preflight(bind) -> None:
    """Abort with a detailed error if any user row is not cleanly Cognito-only.

    Runs three checks and accumulates every violation into one error message
    so an operator sees the full picture in one migration attempt rather
    than fixing one row at a time.
    """
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("users")}

    problems: list[str] = []

    null_sub_rows = bind.execute(
        sa.text("SELECT id, email FROM users WHERE cognito_sub IS NULL")
    ).fetchall()
    if null_sub_rows:
        listing = ", ".join(f"{r.id} ({r.email})" for r in null_sub_rows)
        problems.append(
            f"{len(null_sub_rows)} row(s) have cognito_sub IS NULL — not "
            f"linked to a Cognito pool user: {listing}"
        )

    dup_sub_rows = bind.execute(
        sa.text(
            "SELECT cognito_sub, COUNT(*) AS n FROM users "
            "WHERE cognito_sub IS NOT NULL "
            "GROUP BY cognito_sub HAVING COUNT(*) > 1"
        )
    ).fetchall()
    if dup_sub_rows:
        listing = ", ".join(f"{r.cognito_sub} (x{r.n})" for r in dup_sub_rows)
        problems.append(f"duplicated cognito_sub value(s): {listing}")

    if "auth_provider" in columns:
        non_cognito_rows = bind.execute(
            sa.text(
                "SELECT id, email, auth_provider FROM users "
                "WHERE auth_provider <> 'cognito'"
            )
        ).fetchall()
        if non_cognito_rows:
            listing = ", ".join(
                f"{r.id} ({r.email}, auth_provider={r.auth_provider!r})"
                for r in non_cognito_rows
            )
            problems.append(
                f"{len(non_cognito_rows)} row(s) are not auth_provider='cognito': "
                f"{listing}"
            )

    if problems:
        raise RuntimeError(
            "Cannot apply migration 0038 (Cognito-only users): the following "
            "row(s) are not cleanly Cognito-linked and would be corrupted by "
            "dropping password_hash/auth_provider or by the NOT NULL "
            "cognito_sub constraint:\n  - "
            + "\n  - ".join(problems)
            + "\nRun `python -m scripts.migrate_local_users_to_cognito --report` "
            "to inspect, then `--link`/`--invite` to fix, before retrying this "
            "migration."
        )


def upgrade() -> None:
    bind = op.get_bind()
    _preflight(bind)

    with op.batch_alter_table("users") as b:
        # Only alter cognito_sub if it's still nullable (pre-upgrade state).
        # Use column_exists to check if the NOT NULL constraint already exists
        # by attempting to read the column definition directly.
        inspector = sa.inspect(bind)
        columns = {c["name"]: c for c in inspector.get_columns("users")}
        if "cognito_sub" in columns and columns["cognito_sub"].get("nullable", True):
            b.alter_column("cognito_sub", existing_type=sa.String(), nullable=False)
        
        # Add status column only if it doesn't exist
        add_column_if_missing(
            "users",
            sa.Column(
                "status",
                sa.String(length=20),
                nullable=False,
                server_default="active",
            ),
        )
        
        # Drop columns only if they exist
        drop_column_if_present("users", "password_hash")
        drop_column_if_present("users", "auth_provider")

    # Create the pending_cognito_deletions table only if it doesn't exist
    create_table_if_missing(
        "pending_cognito_deletions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id_snapshot", sa.String(), nullable=False),
        sa.Column("cognito_sub", sa.String(), nullable=False),
        sa.Column("email_hash", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    
    # Create the index only if it doesn't exist
    create_index_if_missing(
        "ix_pending_cognito_deletions_cognito_sub",
        "pending_cognito_deletions",
        ["cognito_sub"],
    )


def downgrade() -> None:
    # Drop the table and index (they are idempotent-safe)
    inspector = sa.inspect(op.get_bind())
    if "pending_cognito_deletions" in set(inspector.get_table_names()):
        op.drop_index(
            "ix_pending_cognito_deletions_cognito_sub",
            table_name="pending_cognito_deletions",
        )
        op.drop_table("pending_cognito_deletions")

    with op.batch_alter_table("users") as b:
        # Add back the columns if they don't exist
        if not column_exists("users", "auth_provider"):
            b.add_column(
                sa.Column(
                    "auth_provider",
                    sa.String(),
                    nullable=False,
                    server_default="local",
                )
            )
        if not column_exists("users", "password_hash"):
            b.add_column(sa.Column("password_hash", sa.String(), nullable=True))
        
        # Drop status column if it exists
        if column_exists("users", "status"):
            b.drop_column("status")
        
        # Restore cognito_sub to nullable only if it's currently NOT NULL
        inspector = sa.inspect(op.get_bind())
        columns = {c["name"]: c for c in inspector.get_columns("users")}
        if "cognito_sub" in columns and not columns["cognito_sub"].get("nullable", False):
            b.alter_column("cognito_sub", existing_type=sa.String(), nullable=True)
