"""Add the connector tables (Token Vault, OAuth states, audit log).

Three new tables back the Connectors feature (design section 2.1):

  * ``connector_connections``: one row per (user, connector), tokens Fernet-encrypted.
  * ``oauth_states``: single-use, 10-minute authorization states (hash only).
  * ``connector_audit_log``: connector events; never a secret or a payload.

ADDITIVE ONLY: three new tables, no existing table or column altered.

Q5 exemption: the tables carry ``user_id`` and NO ``owner_id`` / ``workspace_id``.
A connection belongs to a person, not to a run workspace. Every ``user_id`` is a
foreign key to ``users.id`` with ``ON DELETE CASCADE`` (the 0039 policy for purely
dependent per-user rows); account deletion also removes the rows explicitly.
``connector_audit_log.run_id`` has no foreign key: the audit trail outlives a run.

RE-APPLIABILITY: every table and index is guarded with ``migration_helpers`` so the
idempotency ratchet (``tests/integration/db/test_migration_idempotency.py``) passes;
``docker-entrypoint.sh`` runs ``alembic upgrade head`` under ``set -eu``.

The models in ``app/models/connector.py`` must mirror this exactly.
"""

import sqlalchemy as sa

from migration_helpers import (
    create_index_if_missing,
    create_table_if_missing,
    drop_table_if_present,
)

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_table_if_missing(
        "connector_connections",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("connector_key", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("provider_account_id", sa.String(length=128), nullable=False),
        sa.Column("provider_account_login", sa.String(length=255), nullable=True),
        sa.Column("provider_account_name", sa.String(length=255), nullable=True),
        sa.Column("granted_scopes", sa.JSON(), nullable=False),
        sa.Column("provider_metadata", sa.JSON(), nullable=True),
        sa.Column("access_token_ciphertext", sa.Text(), nullable=False),
        sa.Column("refresh_token_ciphertext", sa.Text(), nullable=True),
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "refresh_token_expires_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "user_id", "connector_key", name="uq_connector_connections_user_connector"
        ),
    )
    create_index_if_missing(
        "ix_connector_connections_user", "connector_connections", ["user_id"]
    )

    create_table_if_missing(
        "oauth_states",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("connector_key", sa.String(length=32), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("code_verifier_ciphertext", sa.Text(), nullable=False),
        sa.Column("redirect_uri", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("state_hash", name="uq_oauth_states_state_hash"),
    )
    # Pending-state cap per user, and the bounded sweep of old rows.
    create_index_if_missing(
        "ix_oauth_states_user_expires", "oauth_states", ["user_id", "expires_at"]
    )
    create_index_if_missing("ix_oauth_states_expires", "oauth_states", ["expires_at"])

    create_table_if_missing(
        "connector_audit_log",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("connector_key", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("tool_name", sa.String(length=128), nullable=True),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("agent_ref", sa.String(length=128), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    create_index_if_missing(
        "ix_connector_audit_user_created",
        "connector_audit_log",
        ["user_id", "created_at"],
    )
    create_index_if_missing("ix_connector_audit_run", "connector_audit_log", ["run_id"])


def downgrade() -> None:
    # Audit and states first, then the connections they sit beside.
    drop_table_if_present("connector_audit_log")
    drop_table_if_present("oauth_states")
    drop_table_if_present("connector_connections")
