"""Add merge state columns to wave_runs (sandbox git versioning task 5.1).

Records the outcome of a merge operation performed during or after a wave
execution.  All columns nullable — pre-migration rows and waves that never
involve a merge keep NULL.

  * ``merge_state``     VARCHAR nullable — "clean" | "conflict" | "partial" | "aborted"
  * ``merge_applied``   VARCHAR nullable — JSON list of applied branch names
  * ``merge_conflicts`` VARCHAR nullable — JSON conflict details
  * ``merge_strategy``  VARCHAR nullable — merge strategy used (e.g. "ours", "theirs")

ADDITIVE ONLY: no existing column is altered, no existing data is affected.
``batch_alter_table`` for SQLite portability (the 0041/0044 pattern), reached via
``add_column_if_missing``.

RE-APPLIABILITY (guarded retroactively): the idempotency ratchet was installed at
0038 and 0041-0050 shipped unguarded, so re-running this against a database that
already holds ``merge_state`` raised ``DuplicateColumn`` and crash-looped the
container. Guarding each add individually also avoids the SQLite table rebuild
that four adds in one ``batch_alter_table`` would otherwise attempt. Column order
is unchanged (same sequence) and the end schema is identical.
"""

import sqlalchemy as sa
from alembic import op

from migration_helpers import add_column_if_missing

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    add_column_if_missing(
        "wave_runs", sa.Column("merge_state", sa.String(), nullable=True)
    )
    add_column_if_missing(
        "wave_runs", sa.Column("merge_applied", sa.String(), nullable=True)
    )
    add_column_if_missing(
        "wave_runs", sa.Column("merge_conflicts", sa.String(), nullable=True)
    )
    add_column_if_missing(
        "wave_runs", sa.Column("merge_strategy", sa.String(), nullable=True)
    )


def downgrade() -> None:
    with op.batch_alter_table("wave_runs") as b:
        b.drop_column("merge_strategy")
        b.drop_column("merge_conflicts")
        b.drop_column("merge_applied")
        b.drop_column("merge_state")
