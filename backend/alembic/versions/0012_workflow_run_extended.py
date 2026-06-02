"""Extend workflow_runs with Phase 3 columns

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-29

Adds Phase 3 columns to workflow_runs per data-model.md Section 2:
  - parent_run_id: FK to workflow_runs.id (for revision/chained runs)
  - session_id: = user_id (JWT sub) for cross-session continuity
  - pipeline_run_id: UUID per run (in-memory Phase 1-2, DB Phase 3)
  - execution_gate: PROCEED | CLARIFY_REQUIRED
  - execution_strategy: sequential (Phase 2); parallel/conditional (future)
  - planning_context_unavailable: for pre-Phase3 revisions

Also extends the status column to support the full lifecycle:
  clarifying | waiting_for_user | planning | analyzing | generating |
  revising | completed | failed | cancelled
  (The existing "running" value is preserved for backward compat.)
"""

from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("workflow_runs") as batch_op:
        batch_op.add_column(sa.Column("parent_run_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("session_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("pipeline_run_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("execution_gate", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("execution_strategy", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column("planning_context_unavailable", sa.Boolean(), nullable=True, server_default="0")
        )

    # Add FK index for parent_run_id (self-referential)
    op.create_index("ix_workflow_runs_parent", "workflow_runs", ["parent_run_id"])
    op.create_index("ix_workflow_runs_pipeline_run_id", "workflow_runs", ["pipeline_run_id"])


def downgrade() -> None:
    op.drop_index("ix_workflow_runs_pipeline_run_id", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_parent", table_name="workflow_runs")
    with op.batch_alter_table("workflow_runs") as batch_op:
        batch_op.drop_column("planning_context_unavailable")
        batch_op.drop_column("execution_strategy")
        batch_op.drop_column("execution_gate")
        batch_op.drop_column("pipeline_run_id")
        batch_op.drop_column("session_id")
        batch_op.drop_column("parent_run_id")
