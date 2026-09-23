"""Add manifest_json to workflow_runs — resume fidelity for composed runs.

A run launched from a Composer manifest (USER_WORKFLOW_MANIFEST / inline
`manifest`) executes the compiled manifest via `compiled_override`, but nothing
persisted that manifest on the run row. `engine.resume_run` reconstructs the
roster from `get_pipeline_agents(type)` — and for `type="custom"` that is the
GENERIC custom registry roster (Market Research Agent, Strategy Analysis
Agent, …), a completely different pipeline. Observed live: a crashed composed
run auto-resumed as the generic custom pipeline and burned ~597K tokens on
four agents the user never composed.

This migration adds ONE additive nullable JSON column:

  * ``manifest_json`` — the RAW manifest dict the run was launched with.
    Stamped at mint by `run_commands._launch_run_core` for manifest launches;
    NULL for every other run (registry/file pipelines resume exactly as
    before — INV-3). `resume_run` recompiles it (same trust as launch) and
    threads it through `compiled_override`, so a resumed composed run drives
    the SAME steps it was launched with.

ADDITIVE ONLY: no new table, no alter of existing columns.
``batch_alter_table`` for SQLite portability (0027/0038 pattern), reached via
``add_column_if_missing``.

RE-APPLIABILITY (guarded retroactively): the idempotency ratchet in
``tests/integration/db/test_migration_idempotency.py`` was installed at 0038 and
0041-0050 shipped unguarded, so re-running this against a database that already
holds ``manifest_json`` raised ``DuplicateColumn`` and crash-looped the container
(``docker-entrypoint.sh`` runs ``alembic upgrade head`` under ``set -eu``). That
risk is not hypothetical for this revision in particular: it has already been
renumbered twice (see below), which is exactly how one database records the old
ID and another the new one for the same DDL. The guard changes only the branch
that previously raised; the end schema is identical.
"""

from alembic import op
import sqlalchemy as sa

from migration_helpers import add_column_if_missing

# Renumbered 0040 -> 0047 when feat/git-versioning merged in: that branch also
# minted a "0040" (0040_workflow_run_share_token), so both files declared
# revision="0040"/down_revision="0039" and alembic reported two heads, which
# made `upgrade head` fail outright. Theirs keeps 0040 because 0041-0046 chain
# off it; ours moves to the end of the line. Content is unchanged.
revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    add_column_if_missing(
        "workflow_runs", sa.Column("manifest_json", sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    with op.batch_alter_table("workflow_runs") as b:
        b.drop_column("manifest_json")
