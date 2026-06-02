"""Create workflow_clarifications, workflow_memory, workflows tables

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-29

Creates three new tables per data-model.md Section 1:
  - workflow_clarifications: per-run Q&A pairs from the Clarify_Engine
  - workflow_memory: per-user key/value store (Constitution + domain knowledge)
  - workflows: persisted Workflow DAG definitions
"""

from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # workflow_clarifications — structured Q&A pairs per run
    op.create_table(
        "workflow_clarifications",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workflow_run_id", sa.String(), sa.ForeignKey("workflow_runs.id"), nullable=False),
        sa.Column("question_id", sa.String(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("impact_level", sa.String(), nullable=False),   # "high" | "medium" | "low"
        sa.Column("answer_type", sa.String(), nullable=False),    # "free_text" | "single_choice" | ...
        sa.Column("options", sa.Text(), nullable=True),           # JSON array of strings
        sa.Column("answer", sa.Text(), nullable=True),            # user's answer (NULL until answered)
        sa.Column("recommended_answer", sa.Text(), nullable=True),
        sa.Column("round", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("answered_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workflow_clarifications_run", "workflow_clarifications", ["workflow_run_id"])

    # workflow_memory — per-user key/value store
    op.create_table(
        "workflow_memory",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),            # up to 1,048,576 chars
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "key", name="uq_workflow_memory_user_key"),
    )

    # workflows — persisted Workflow DAG definitions
    op.create_table(
        "workflows",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("agents", sa.Text(), nullable=False),           # JSON: ordered list of agent IDs
        sa.Column("artifact_edges", sa.Text(), nullable=False),   # JSON: [{from_agent, to_agent, artifact_type}]
        sa.Column("constitution_ref", sa.String(), nullable=True),# key in workflow_memory
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workflows_user", "workflows", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_workflows_user", table_name="workflows")
    op.drop_table("workflows")
    op.drop_table("workflow_memory")
    op.drop_index("ix_workflow_clarifications_run", table_name="workflow_clarifications")
    op.drop_table("workflow_clarifications")
