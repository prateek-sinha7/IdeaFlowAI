"""Add payload_chainable and non_chainable_reason to workflow_runs (sandbox git versioning task 5.1).

Records whether the run's output payload can be chained (used as the input
context for a downstream run).  NULL means "unknown" for rows created before
this migration.

  * ``payload_chainable``     BOOLEAN nullable — NULL = unknown (pre-migration rows)
  * ``non_chainable_reason``  VARCHAR nullable — human-readable reason why the
                               payload cannot be chained; NULL when chainable or
                               unknown.

ADDITIVE ONLY: no existing column is altered, no existing data is affected.
``batch_alter_table`` for SQLite portability (the 0038/0039/0040/0041 pattern),
reached via ``add_column_if_missing``.

RE-APPLIABILITY (guarded retroactively): the idempotency ratchet was installed at
0038 and 0041-0050 shipped unguarded, so re-running this against a database that
already holds ``payload_chainable`` raised ``DuplicateColumn`` and crash-looped
the container. The guards change only that branch; the end schema is identical.
"""

import sqlalchemy as sa
from alembic import op

from migration_helpers import add_column_if_missing

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    add_column_if_missing(
        "workflow_runs", sa.Column("payload_chainable", sa.Boolean(), nullable=True)
    )
    add_column_if_missing(
        "workflow_runs", sa.Column("non_chainable_reason", sa.String(), nullable=True)
    )


def downgrade() -> None:
    with op.batch_alter_table("workflow_runs") as b:
        b.drop_column("non_chainable_reason")
        b.drop_column("payload_chainable")
