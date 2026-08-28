"""Add share_token + share_expires_at to workflow_runs (Option B public share).

Adds two nullable columns so run owners can mint a short-lived public share
token that lets anyone view the deliverable without authenticating:

  * ``share_token``      (String, nullable, unique) — a cryptographically
    random token (32 URL-safe bytes, 43 base64url chars).  NULL means the
    run has never been shared.  The owner can revoke the share by clearing it.

  * ``share_expires_at`` (DateTime, nullable) — optional expiry; NULL means
    the share is permanent until revoked.  The /s/{token} route checks this
    and returns 410 Gone when expired.

SECURITY NOTES:
  - The token is opaque and carries no user or run id — it is a pure lookup
    key.  Cross-ownership is impossible: the /s/ route only echoes the
    ``output`` + ``deliverable_mimetype`` columns (not input, agent_outputs,
    token_usage, or any PII).
  - The unique index lets the /s/ route resolve in O(log n) without scanning
    the whole table.
  - Revoke by DELETE /api/runs/{id}/share sets share_token = NULL.

ADDITIVE ONLY: no existing column is altered, no existing data is affected.
``batch_alter_table`` for SQLite portability (the 0027/0038/0039 pattern).
"""

import sqlalchemy as sa
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("workflow_runs") as b:
        b.add_column(sa.Column("share_token", sa.String(), nullable=True))
        b.add_column(sa.Column("share_expires_at", sa.DateTime(), nullable=True))

    # Sparse unique index — only one row per token value; NULLs are excluded
    # (both SQLite and Postgres treat NULLs as distinct in a unique index, but
    # the WHERE clause makes the intent explicit and avoids vendor surprises).
    op.create_index(
        "uq_workflow_runs_share_token",
        "workflow_runs",
        ["share_token"],
        unique=True,
        sqlite_where=sa.text("share_token IS NOT NULL"),
        postgresql_where=sa.text("share_token IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_workflow_runs_share_token", table_name="workflow_runs")
    with op.batch_alter_table("workflow_runs") as b:
        b.drop_column("share_expires_at")
        b.drop_column("share_token")
