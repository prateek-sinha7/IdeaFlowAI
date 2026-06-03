"""Collapse pipeline_run_id into id; add parent_run_id FK

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-02

Identity-model collapse (follow-up to Phase 3):
  - Drop workflow_runs.pipeline_run_id and its index. WorkflowRun.id is now the
    single run identifier used end-to-end by the engine, state machine, and the
    Artifact_Store (workflow_artifacts.workflow_run_id FK -> workflow_runs.id).
  - Add the parent_run_id -> workflow_runs.id foreign key that migration 0012
    declared on the model but only created as a plain column. With the FK in
    place, both SQLite (PRAGMA foreign_keys=ON) and Postgres enforce referential
    integrity for revision/chaining, and `alembic check` matches the models.
"""

from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the now-redundant index first so the SQLite batch-recreate below does
    # not try to carry it over to a column that no longer exists.
    op.drop_index("ix_workflow_runs_pipeline_run_id", table_name="workflow_runs")
    with op.batch_alter_table("workflow_runs") as batch_op:
        batch_op.drop_column("pipeline_run_id")
        # The self-referential FK that migration 0012 omitted (it added
        # parent_run_id as a bare column). Unnamed on the model; we name it here
        # so SQLite batch + Postgres can both DROP it on downgrade.
        batch_op.create_foreign_key(
            "fk_workflow_runs_parent_run_id",
            "workflow_runs",
            ["parent_run_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("workflow_runs") as batch_op:
        batch_op.drop_constraint(
            "fk_workflow_runs_parent_run_id", type_="foreignkey"
        )
        batch_op.add_column(sa.Column("pipeline_run_id", sa.String(), nullable=True))
    op.create_index(
        "ix_workflow_runs_pipeline_run_id", "workflow_runs", ["pipeline_run_id"]
    )
