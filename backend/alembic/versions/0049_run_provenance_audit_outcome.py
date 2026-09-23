"""Add outcome column to run_provenance_audits (sandbox git versioning task 8.2).

``outcome`` is a bounded classifier that records the typed result of a git
provenance operation — e.g. "committed", "no_change", "blocked", "degraded".
It is set for every row so the restore idempotency lookup (task 8.2) can read
a typed column rather than having to decode the ``detail_json`` blob.

ADDITIVE ONLY: new column only, no existing data altered.
Uses ``batch_alter_table`` for SQLite portability (same pattern as 0044/0045),
reached via ``add_column_if_missing``.

RE-APPLIABILITY (guarded retroactively): the idempotency ratchet was installed at
0038 and 0041-0050 shipped unguarded, so re-running this against a database that
already holds ``outcome`` raised ``DuplicateColumn`` and crash-looped the
container. The guard changes only that branch; the end schema is identical.
"""

import sqlalchemy as sa
from alembic import op

from migration_helpers import add_column_if_missing

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    add_column_if_missing(
        "run_provenance_audits", sa.Column("outcome", sa.String(), nullable=True)
    )


def downgrade() -> None:
    with op.batch_alter_table("run_provenance_audits") as b:
        b.drop_column("outcome")
