"""handoff feature tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-12

Adds three tables for the /flowin-handoff feature:

* ``user_github_credentials`` — one PAT per user, Fernet-encrypted at
  rest (see ``app.core.crypto``).
* ``user_api_keys`` — long-lived bearer tokens for IDE / MCP clients.
* ``handoff_sessions`` — one row per IDE handoff, evolving into a PR.

The migration is additive only: no existing table is touched. A
``downgrade`` to ``0001`` drops the three new tables in reverse-FK order
and leaves the rest of the schema intact.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_github_credentials",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("encrypted_pat", sa.Text(), nullable=False),
        sa.Column("github_username", sa.String(), nullable=True),
        sa.Column("scopes", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_user_github_credentials_user_id"),
        "user_github_credentials",
        ["user_id"],
        unique=True,
    )

    op.create_table(
        "user_api_keys",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("token_prefix", sa.String(length=8), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_user_api_keys_user_id"),
        "user_api_keys",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_api_keys_token_hash"),
        "user_api_keys",
        ["token_hash"],
        unique=True,
    )

    op.create_table(
        "handoff_sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("issuer_user_id", sa.String(), nullable=False),
        sa.Column("task_description", sa.Text(), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=False),
        sa.Column("repo_url", sa.String(), nullable=False),
        sa.Column("repo_default_branch", sa.String(), nullable=True),
        sa.Column("source_branch", sa.String(), nullable=True),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("source_client", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("resolved_mode", sa.String(), nullable=True),
        sa.Column("pr_url", sa.String(), nullable=True),
        sa.Column("pr_number", sa.Integer(), nullable=True),
        sa.Column("branch_name", sa.String(), nullable=True),
        sa.Column("pipeline_output", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["issuer_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_handoff_sessions_token"),
        "handoff_sessions",
        ["token"],
        unique=True,
    )
    op.create_index(
        op.f("ix_handoff_sessions_issuer_user_id"),
        "handoff_sessions",
        ["issuer_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_handoff_sessions_issuer_user_id"), table_name="handoff_sessions"
    )
    op.drop_index(op.f("ix_handoff_sessions_token"), table_name="handoff_sessions")
    op.drop_table("handoff_sessions")

    op.drop_index(op.f("ix_user_api_keys_token_hash"), table_name="user_api_keys")
    op.drop_index(op.f("ix_user_api_keys_user_id"), table_name="user_api_keys")
    op.drop_table("user_api_keys")

    op.drop_index(
        op.f("ix_user_github_credentials_user_id"),
        table_name="user_github_credentials",
    )
    op.drop_table("user_github_credentials")
