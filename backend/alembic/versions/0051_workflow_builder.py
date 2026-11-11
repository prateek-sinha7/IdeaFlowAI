"""Add the AI Workflow Builder tables (design §4.2 to §4.4).

Three new tables back a builder session:

  * ``workflow_builder_sessions``: one row per builder conversation.
  * ``workflow_builder_messages``: user, assistant (one per turn) and tool rows.
  * ``workflow_builder_drafts``: numbered manifest revisions of a session.

ADDITIVE ONLY: three new tables, no existing table or column altered.
Every table carries ``owner_id`` + ``workspace_id`` (Q3) and ``user_id``; the
builder authorises on ``user_id`` (Req 24.6), never on ``owner_id``.

Foreign keys mirror ``app/models/workflow_builder.py`` exactly:

  * ``sessions.user_id`` -> ``users.id`` (plain, no cascade).
  * ``sessions.workflow_id`` -> ``workflows.id`` ``ON DELETE SET NULL``, so
    deleting the saved workflow unlinks the session in the database (Req 20.16).
  * ``messages.session_id`` / ``drafts.session_id`` ->
    ``workflow_builder_sessions.id`` (plain, no cascade).
  * ``messages.user_id`` / ``drafts.user_id`` have no FK (account deletion
    removes builder rows explicitly).

Constraints and indexes (Req 21.8, 21.10, 24.6, 24.8, 48.7):

  * ``uq_wb_messages_session_seq``: unique (session_id, seq).
  * ``uq_wb_messages_client_id``: partial unique (session_id,
    client_message_id) WHERE client_message_id IS NOT NULL (Req 21.10).
  * ``uq_wb_messages_one_running``: partial unique (session_id) WHERE
    role = 'assistant' AND status = 'running' (Req 21.8, at most one running
    turn per session even in a race).
  * ``ix_wb_messages_user_role_created``: (user_id, role, created_at).
  * ``ix_wb_messages_turn``: (turn_id).
  * ``uq_wb_drafts_session_revision``: unique (session_id, revision).
  * ``ix_wb_sessions_user_updated``: (user_id, updated_at DESC, id), the
    keyset pagination order of the session list.

RE-APPLIABILITY: the idempotency ratchet in
``tests/integration/db/test_migration_idempotency.py`` requires every new
revision to be safe to re-run over a database that already holds its objects
(``docker-entrypoint.sh`` runs ``alembic upgrade head`` under ``set -eu``).
Each table and each index is guarded independently with ``migration_helpers``.
Partial indexes declare both ``postgresql_where`` and ``sqlite_where`` (the
0046 pattern) so the ratchet's throwaway SQLite database builds the same shape.
"""

import sqlalchemy as sa
from alembic import op

from migration_helpers import (
    create_index_if_missing,
    create_table_if_missing,
    drop_table_if_present,
    index_exists,
)

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_table_if_missing(
        "workflow_builder_sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(length=80), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("workflow_id", sa.String(), nullable=True),
        sa.Column("linked_manifest_hash", sa.String(), nullable=True),
        sa.Column("model_id", sa.String(), nullable=True),
        sa.Column("effort", sa.String(), nullable=True),
        sa.Column("target_trust", sa.String(), nullable=False, server_default="user"),
        sa.Column("skill_hash", sa.String(), nullable=False),
        sa.Column("next_seq", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("turn_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "clarify_turns_without_draft",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("first_accepted_revision", sa.Integer(), nullable=True),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column("summary_through_seq", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="SET NULL"),
    )
    # Keyset pagination of the session list; the DESC key matches the ORM Index.
    if not index_exists("workflow_builder_sessions", "ix_wb_sessions_user_updated"):
        op.create_index(
            "ix_wb_sessions_user_updated",
            "workflow_builder_sessions",
            ["user_id", sa.text("updated_at DESC"), "id"],
        )

    create_table_if_missing(
        "workflow_builder_messages",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("turn_id", sa.String(), nullable=False),
        sa.Column("reply_to_message_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=True),
        sa.Column("stop_reason", sa.String(), nullable=True),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("thinking", sa.Text(), nullable=True),
        sa.Column("canvas_state", sa.JSON(), nullable=True),
        sa.Column("client_message_id", sa.String(), nullable=True),
        sa.Column("model_id", sa.String(), nullable=True),
        sa.Column("effort", sa.String(), nullable=True),
        sa.Column("skill_hash", sa.String(), nullable=True),
        sa.Column("prompt_version", sa.String(), nullable=True),
        sa.Column("usage", sa.JSON(), nullable=True),
        sa.Column("adherence", sa.JSON(), nullable=True),
        sa.Column("tool", sa.JSON(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["session_id"], ["workflow_builder_sessions.id"]),
        sa.UniqueConstraint("session_id", "seq", name="uq_wb_messages_session_seq"),
    )
    # Req 21.10: one row per (session, client_message_id) when it is set.
    create_index_if_missing(
        "uq_wb_messages_client_id",
        "workflow_builder_messages",
        ["session_id", "client_message_id"],
        unique=True,
        postgresql_where=sa.text("client_message_id IS NOT NULL"),
        sqlite_where=sa.text("client_message_id IS NOT NULL"),
    )
    # Req 21.8: at most one running assistant row per session.
    create_index_if_missing(
        "uq_wb_messages_one_running",
        "workflow_builder_messages",
        ["session_id"],
        unique=True,
        postgresql_where=sa.text("role = 'assistant' AND status = 'running'"),
        sqlite_where=sa.text("role = 'assistant' AND status = 'running'"),
    )
    # Rate limit and running-turn count.
    create_index_if_missing(
        "ix_wb_messages_user_role_created",
        "workflow_builder_messages",
        ["user_id", "role", "created_at"],
    )
    # Loading a turn's tool rows.
    create_index_if_missing(
        "ix_wb_messages_turn",
        "workflow_builder_messages",
        ["turn_id"],
    )

    create_table_if_missing(
        "workflow_builder_drafts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("target_trust", sa.String(), nullable=True),
        sa.Column("change_summary", sa.JSON(), nullable=True),
        sa.Column("launch_needs", sa.JSON(), nullable=True),
        sa.Column("source_turn_id", sa.String(), nullable=True),
        sa.Column("source_file", sa.String(), nullable=True),
        sa.Column("undo_of_revision", sa.Integer(), nullable=True),
        sa.Column("manifest_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["session_id"], ["workflow_builder_sessions.id"]),
        sa.UniqueConstraint(
            "session_id", "revision", name="uq_wb_drafts_session_revision"
        ),
    )


def downgrade() -> None:
    # Reverse creation order: children reference the sessions table.
    drop_table_if_present("workflow_builder_drafts")
    drop_table_if_present("workflow_builder_messages")
    drop_table_if_present("workflow_builder_sessions")
