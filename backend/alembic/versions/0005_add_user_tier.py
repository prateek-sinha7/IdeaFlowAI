"""Add tier column to users

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("tier", sa.String(), nullable=False, server_default="basic"),
    )


def downgrade() -> None:
    op.drop_column("users", "tier")
