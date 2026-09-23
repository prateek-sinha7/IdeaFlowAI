"""Add run_finalizations table (sandbox git versioning task 5.1).

One row per run, upsertable. Records the final published/candidate status,
payload chainability, git tag assignment outcome, and chain-context install
state for a completed run.

ADDITIVE ONLY: new table, no existing columns altered.
Every non-PK/owner/workspace/run_id column is nullable.

Columns:
  id                       UUID primary key
  owner_id                 VARCHAR NOT NULL
  workspace_id             VARCHAR NOT NULL
  run_id                   VARCHAR NOT NULL UNIQUE (one record per run)
  published_status         VARCHAR nullable
  payload_chainable        BOOLEAN nullable
  non_chainable_reason     VARCHAR nullable
  candidate_status         VARCHAR nullable
  payload_built            BOOLEAN nullable
  payload_materialized     BOOLEAN nullable
  commit_sha               VARCHAR nullable
  internal_ref             VARCHAR nullable
  git_tag                  VARCHAR nullable
  tag_state                VARCHAR nullable  ("created" | "rolled_back")
  chain_context_installed  BOOLEAN nullable
  created_at               TIMESTAMP nullable
  updated_at               TIMESTAMP nullable

Indexes: owner_id, run_id

RE-APPLIABILITY (guarded retroactively): the idempotency ratchet in
``tests/integration/db/test_migration_idempotency.py`` was installed at 0038 and
0041-0050 shipped unguarded, so re-running this against a database that already
holds the table raised ``DuplicateTable`` and crash-looped the container
(``docker-entrypoint.sh`` runs ``alembic upgrade head`` under ``set -eu``). The
table and its two indexes are guarded independently, so a database that has the
table but lost one index is repaired rather than rejected. The end schema is
identical, and a database already stamped at or past 0045 never re-runs this.
"""

import sqlalchemy as sa
from alembic import op

from migration_helpers import create_index_if_missing, create_table_if_missing

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_table_if_missing(
        "run_finalizations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("published_status", sa.String(), nullable=True),
        sa.Column("payload_chainable", sa.Boolean(), nullable=True),
        sa.Column("non_chainable_reason", sa.String(), nullable=True),
        sa.Column("candidate_status", sa.String(), nullable=True),
        sa.Column("payload_built", sa.Boolean(), nullable=True),
        sa.Column("payload_materialized", sa.Boolean(), nullable=True),
        sa.Column("commit_sha", sa.String(), nullable=True),
        sa.Column("internal_ref", sa.String(), nullable=True),
        sa.Column("git_tag", sa.String(), nullable=True),
        sa.Column("tag_state", sa.String(), nullable=True),
        sa.Column("chain_context_installed", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_run_finalizations_run_id"),
    )
    create_index_if_missing(
        "ix_run_finalizations_owner", "run_finalizations", ["owner_id"]
    )
    create_index_if_missing("ix_run_finalizations_run", "run_finalizations", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_run_finalizations_run", table_name="run_finalizations")
    op.drop_index("ix_run_finalizations_owner", table_name="run_finalizations")
    op.drop_table("run_finalizations")
