"""0031 — Cognito identity mapping + generalized token-validity revocation.

Part of the Cognito Authentication & Authorization Migration
(``.planning/COGNITO-MIGRATION-PLAN.md`` §6.1). Additive-only (Q3, INV-3): no
table is dropped, no existing column is removed. ``password_hash`` becomes
NULLABLE because Cognito-native users legitimately have no local bcrypt hash
— only the single break-glass local-admin account (Decision 12) retains one.

Columns added to ``users``:

  * ``cognito_sub`` (String, nullable, UNIQUE, indexed) — Cognito ``sub``
    claim. Never the primary identity key (``users.id`` stays the local UUID
    every foreign key references — see the plan §3.3); this is a mapping
    column only.
  * ``auth_provider`` (String, NOT NULL, default ``"local"``) — ``"cognito"``
    or ``"local"`` (break-glass). Existing rows backfill to ``"local"`` via
    the column default, which is the correct historical value (every
    pre-migration user authenticated locally).
  * ``tokens_valid_from`` (DateTime, nullable) — generalizes the existing
    ``password_changed_at`` blanket-revocation check to
    ``max(password_changed_at, tokens_valid_from)`` (plan §5.3), so a role/tier
    change can force re-authentication the same way a password change already
    does. Backfilled from ``password_changed_at`` so the generalized check is
    provably a superset of the current behaviour on day one.
  * ``roles_synced_at`` (DateTime, nullable) — observability only: when the
    ``tier``/``is_admin`` projection was last refreshed from
    ``cognito:groups``. Never read by an authorization decision.

``password_hash`` nullable=True (was NOT NULL) — see plan §6.1. The downgrade
path restores NOT NULL, but only after asserting every row still has a
non-null hash; a Cognito-native user (inserted after this migration ships)
would make the downgrade unsafe, so it fails loudly rather than silently
truncating data.

Revision ID: 0031
Revises: 0030
Create Date: 2026-08-05 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("cognito_sub", sa.String(), nullable=True))
        b.add_column(
            sa.Column(
                "auth_provider",
                sa.String(),
                nullable=False,
                server_default="local",
            )
        )
        b.add_column(sa.Column("tokens_valid_from", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("roles_synced_at", sa.DateTime(), nullable=True))
        b.alter_column("password_hash", existing_type=sa.String(), nullable=True)
        b.create_unique_constraint("uq_users_cognito_sub", ["cognito_sub"])

    op.create_index(
        "ix_users_cognito_sub",
        "users",
        ["cognito_sub"],
        unique=False,
        if_not_exists=True,
    )

    # Backfill: every pre-migration blanket-revocation trigger was a password
    # change, so tokens_valid_from starts equal to password_changed_at. Rows
    # with no prior password change (tokens_valid_from stays NULL) are
    # unaffected — max(NULL, NULL) is NULL, i.e. "no blanket revocation",
    # which is exactly today's behaviour for such a row.
    op.execute(
        "UPDATE users SET tokens_valid_from = password_changed_at "
        "WHERE password_changed_at IS NOT NULL"
    )


def downgrade() -> None:
    # Refuse to silently drop data: a Cognito-native user (password_hash IS
    # NULL) cannot survive restoring the NOT NULL constraint. Fail loudly so
    # an operator investigates instead of the downgrade corrupting rows.
    bind = op.get_bind()
    orphaned = bind.execute(
        sa.text("SELECT COUNT(*) FROM users WHERE password_hash IS NULL")
    ).scalar()
    if orphaned:
        raise RuntimeError(
            f"Cannot downgrade 0031: {orphaned} user row(s) have a NULL "
            "password_hash (Cognito-native accounts with no local password). "
            "Restoring password_hash NOT NULL would corrupt them. Migrate "
            "those users to a local password first, or accept the data loss "
            "explicitly before retrying."
        )

    op.drop_index("ix_users_cognito_sub", table_name="users", if_exists=True)

    with op.batch_alter_table("users") as b:
        b.drop_constraint("uq_users_cognito_sub", type_="unique")
        b.alter_column("password_hash", existing_type=sa.String(), nullable=False)
        b.drop_column("roles_synced_at")
        b.drop_column("tokens_valid_from")
        b.drop_column("auth_provider")
        b.drop_column("cognito_sub")
