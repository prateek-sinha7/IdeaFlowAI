"""0016 — additive capability-hardening tables (Phase 8 / §18, D-10).

Adds the three owner/workspace-scoped audit/result tables the Phase-8 gates
(08-02), validators (08-04), and hooks (08-07) write rows into:

  * ``validation_results`` — one row per validator run/attempt (08-04 consumer);
  * ``gate_events`` — one row per gate firing (08-02 consumer);
  * ``hook_runs`` — one row per hook firing (08-07 consumer).

Each table carries ``owner_id`` + ``workspace_id`` (both NOT NULL, AUTHZ-01) so
the Phase-5 ``ScopedStore`` default-deny filter scopes every read; writes are
owner/workspace-scoped. Indexes per §18: ``validation_results`` (run_id, step);
``gate_events`` (run_id); ``hook_runs`` (run_id).

ADDITIVE ONLY (Q3, INV-3): no existing table is altered destructively. Sequenced
after 0015 (down_revision="0015") — the head chain stays unbroken. ``downgrade()``
drops the three tables (fully reversible). Works on SQLite + Postgres
(``op.create_table`` / ``op.drop_table`` need no batch).
"""

from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "validation_results",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),       # AUTHZ-01
        sa.Column("workspace_id", sa.String(), nullable=False),   # AUTHZ-01
        sa.Column("step", sa.String(), nullable=False),
        sa.Column("validator", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("issues", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_validation_results_run_step",
        "validation_results",
        ["run_id", "step"],
        unique=False,
    )

    op.create_table(
        "gate_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),       # AUTHZ-01
        sa.Column("workspace_id", sa.String(), nullable=False),   # AUTHZ-01
        sa.Column("step", sa.String(), nullable=False),
        sa.Column("gate", sa.String(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_gate_events_run",
        "gate_events",
        ["run_id"],
        unique=False,
    )

    op.create_table(
        "hook_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),       # AUTHZ-01
        sa.Column("workspace_id", sa.String(), nullable=False),   # AUTHZ-01
        sa.Column("hook", sa.String(), nullable=False),
        sa.Column("event", sa.String(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_hook_runs_run",
        "hook_runs",
        ["run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_hook_runs_run", table_name="hook_runs")
    op.drop_table("hook_runs")
    op.drop_index("ix_gate_events_run", table_name="gate_events")
    op.drop_table("gate_events")
    op.drop_index("ix_validation_results_run_step", table_name="validation_results")
    op.drop_table("validation_results")
