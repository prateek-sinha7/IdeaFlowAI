"""KAN-131: Add (user_id, created_at) index for fast history list queries.

Revision ID: 0030
Revises: 0029
Create Date: 2026-07-30 06:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create compound index on (user_id, created_at) for fast history queries (KAN-131).
    
    The list_runs endpoint filters by user_id and orders by created_at descending.
    Without this index, every history load triggers a full table scan + sort on the
    potentially large workflow_runs table. IF NOT EXISTS makes this idempotent — 
    environments that already ran the staging variant (0025) will not fail.
    """
    op.create_index(
        "ix_workflow_runs_user_created",
        "workflow_runs",
        ["user_id", "created_at"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    """Drop the compound index."""
    op.drop_index("ix_workflow_runs_user_created", table_name="workflow_runs", if_exists=True)
