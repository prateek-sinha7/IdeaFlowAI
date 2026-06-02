"""Create workflow_artifacts table (Artifact_Store)

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-29

Creates the workflow_artifacts table per data-model.md Section 1.
This is the Phase 3 Artifact_Store — one row per Artifact version per run.
Immutable: no deletes or overwrites.
"""

from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_artifacts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workflow_run_id", sa.String(), sa.ForeignKey("workflow_runs.id"), nullable=False),
        sa.Column("type", sa.String(), nullable=False),           # Artifact_Type string
        sa.Column("name", sa.String(), nullable=False),           # human-readable name or file path
        sa.Column("content", sa.Text(), nullable=False),          # full artifact content
        sa.Column("version", sa.Integer(), nullable=False),       # monotonically increasing per type per run
        sa.Column("schema_version", sa.String(), nullable=False, server_default="1.0"),
        sa.Column("producing_agent_id", sa.String(), nullable=False),
        sa.Column("derived_from_artifact_id", sa.String(), sa.ForeignKey("workflow_artifacts.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workflow_artifacts_run_type", "workflow_artifacts", ["workflow_run_id", "type"])


def downgrade() -> None:
    op.drop_index("ix_workflow_artifacts_run_type", table_name="workflow_artifacts")
    op.drop_table("workflow_artifacts")
