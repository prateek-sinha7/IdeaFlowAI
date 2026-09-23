"""Add run_provenance_audits table (sandbox git versioning task 5.1).

Append-only audit log for git provenance operations (tag, restore, commit)
performed against a run's sandbox. Each row records a single operation with
an optional idempotency key to deduplicate retries.

ADDITIVE ONLY: new table, no existing columns altered.

Columns:
  id               UUID primary key
  owner_id         VARCHAR NOT NULL
  workspace_id     VARCHAR NOT NULL
  run_id           VARCHAR NOT NULL
  operation        VARCHAR NOT NULL  (e.g. "tag", "restore", "commit")
  source_ref       VARCHAR nullable
  idempotency_key  VARCHAR nullable
  commit_sha       VARCHAR nullable
  tag_name         VARCHAR nullable
  detail_json      VARCHAR nullable  (JSON blob)
  created_at       TIMESTAMP nullable

Indexes:
  Partial unique on (owner_id, operation, idempotency_key) WHERE idempotency_key IS NOT NULL
  Regular index on (owner_id, source_ref)
  Regular index on run_id

RE-APPLIABILITY (guarded retroactively): the idempotency ratchet was installed at
0038 and 0041-0050 shipped unguarded, so re-running this against a database that
already holds the table raised ``DuplicateTable`` and crash-looped the container.
The table and its three indexes are guarded independently, so a database that has
the table but lost an index is repaired rather than rejected. The end schema is
identical, and a database already stamped at or past 0046 never re-runs this.
"""

import sqlalchemy as sa
from alembic import op

from migration_helpers import create_index_if_missing, create_table_if_missing

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_table_if_missing(
        "run_provenance_audits",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("operation", sa.String(), nullable=False),
        sa.Column("source_ref", sa.String(), nullable=True),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("commit_sha", sa.String(), nullable=True),
        sa.Column("tag_name", sa.String(), nullable=True),
        sa.Column("detail_json", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    # Partial unique: deduplicate retries when idempotency_key is set
    create_index_if_missing(
        "uq_run_provenance_audits_idem",
        "run_provenance_audits",
        ["owner_id", "operation", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        sqlite_where=sa.text("idempotency_key IS NOT NULL"),
    )
    create_index_if_missing(
        "ix_run_provenance_audits_owner_src",
        "run_provenance_audits",
        ["owner_id", "source_ref"],
    )
    create_index_if_missing(
        "ix_run_provenance_audits_run",
        "run_provenance_audits",
        ["run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_run_provenance_audits_run", table_name="run_provenance_audits")
    op.drop_index("ix_run_provenance_audits_owner_src", table_name="run_provenance_audits")
    op.drop_index("uq_run_provenance_audits_idem", table_name="run_provenance_audits")
    op.drop_table("run_provenance_audits")
