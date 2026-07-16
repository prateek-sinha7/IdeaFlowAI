"""0025 — compound index on workflow_runs(user_id, created_at) for history performance.

The ``GET /api/runs`` history endpoint filters by ``user_id`` and orders by
``created_at DESC``. Without an index the query performs a full table scan
on every history page load, worsening linearly as each user accumulates runs.

This migration adds a single composite index:

  * ``ix_workflow_runs_user_created`` on ``(user_id, created_at)`` — covers
    the exact filter + sort path of ``list_runs()``:
    ``WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?``

ADDITIVE ONLY (Q3, INV-3): no new table, no new column, no alter of existing
columns or constraints. Indexes are safe to add without touching existing rows.
Sequenced after 0024 (``down_revision="0024"``). ``downgrade()`` drops the index
(fully reversible). SQLite-compatible via direct ``op.create_index`` (no
``batch_alter_table`` needed — indexes are created/dropped without rebuilding
the table).
"""

from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_workflow_runs_user_created",
        "workflow_runs",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_workflow_runs_user_created", table_name="workflow_runs")
