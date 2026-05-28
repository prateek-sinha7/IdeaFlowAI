"""Add model_id column to workflow_runs

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workflow_runs",
        sa.Column("model_id", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workflow_runs", "model_id")
