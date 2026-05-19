"""Add token_usage column to workflow_runs

Revision ID: 0004
Revises: 0002
Create Date: 2026-05-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workflow_runs",
        sa.Column("token_usage", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workflow_runs", "token_usage")
