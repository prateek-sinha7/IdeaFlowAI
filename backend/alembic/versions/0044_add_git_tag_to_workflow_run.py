"""Add git_tag column to workflow_runs (sandbox git versioning, task 6.2).

A completed run receives a git tag (e.g. "v1", "v2") written by the post_run
finalizer in engine.py after create_tag() succeeds.  Runs that terminate as
diverted, cancelled, failed, or degraded, and all runs created before git
versioning was enabled, keep NULL.

  * ``git_tag`` (String, nullable) — the name of the git tag assigned to this
    run's sandbox commit (e.g. "v1").  NULL = not tagged.

Set by engine.py task 6.3 after successful tag creation; read by
FamilyMemberResponse (task 6.4) to surface a "tagged" badge in the UI.

ADDITIVE ONLY: no existing column is altered, no existing data is affected.
``batch_alter_table`` for SQLite portability (the 0038/0039/0040 pattern),
reached via ``add_column_if_missing``.

RE-APPLIABILITY (guarded retroactively): the idempotency ratchet was installed
at 0038 and 0041-0050 shipped unguarded, so re-running this against a database
that already holds ``git_tag`` raised ``DuplicateColumn`` and crash-looped the
container. The guard changes only that branch; the end schema is identical.
"""

import sqlalchemy as sa
from alembic import op

from migration_helpers import add_column_if_missing

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    add_column_if_missing(
        "workflow_runs", sa.Column("git_tag", sa.String(), nullable=True)
    )


def downgrade() -> None:
    with op.batch_alter_table("workflow_runs") as b:
        b.drop_column("git_tag")
