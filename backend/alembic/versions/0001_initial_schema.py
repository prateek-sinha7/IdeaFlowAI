"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-10

This is the baseline migration captured by ``alembic revision --autogenerate``
against an empty SQLite database. It includes everything the application
expects today:

* ``users`` (with ``password_changed_at`` from blocker A4)
* ``chat_sessions``
* ``messages``
* ``workflow_runs``
* ``revoked_tokens`` (also from A4)

We override alembic's hash-based revision id with the literal ``"0001"`` for
two reasons: (1) deterministic file ordering when alembic lists revisions,
(2) operators can ``alembic upgrade 0001`` from memory. Subsequent migrations
will carry their auto-assigned hashes; only the baseline is hand-numbered.

``downgrade()`` drops every table in reverse FK order so a full rollback to
an empty schema is possible. We intentionally do not lean on
``Base.metadata.drop_all`` here — alembic's per-table ops mirror the upgrade
exactly and survive future model changes (e.g. a column added in a later
revision is not visible to ``Base.metadata`` at the time this migration runs
during a downgrade-to-base, but the per-table ``DROP TABLE`` is unaffected).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the baseline schema.

    Order matters: ``users`` must exist before any FK that points at it
    (``chat_sessions``, ``revoked_tokens``, ``workflow_runs``), and
    ``chat_sessions`` must exist before ``messages``.
    """
    op.create_table(
        "users",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        # Added by blocker A4 (per-token / blanket-revoke support). Nullable
        # because users who never rotate their password have no cutoff.
        sa.Column("password_changed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("last_activity", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("final_output", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # Revoked-tokens table — added by blocker A4.
    op.create_table(
        "revoked_tokens",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("jti", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_revoked_tokens_jti"), "revoked_tokens", ["jti"], unique=True
    )
    op.create_index(
        op.f("ix_revoked_tokens_user_id"),
        "revoked_tokens",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("input", sa.Text(), nullable=False),
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column("agent_outputs", sa.Text(), nullable=True),
        sa.Column("agent_count", sa.Integer(), nullable=False),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("chat_session_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["chat_session_id"], ["chat_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Drop everything ``upgrade()`` created, in reverse FK order.

    A full ``downgrade base`` should leave the database empty (modulo
    alembic's own ``alembic_version`` table, which alembic itself manages).
    """
    op.drop_table("messages")
    op.drop_table("workflow_runs")
    op.drop_index(
        op.f("ix_revoked_tokens_user_id"), table_name="revoked_tokens"
    )
    op.drop_index(op.f("ix_revoked_tokens_jti"), table_name="revoked_tokens")
    op.drop_table("revoked_tokens")
    op.drop_table("chat_sessions")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
