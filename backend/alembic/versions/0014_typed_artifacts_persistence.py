"""Typed artifacts persistence + ownership schema (Phase 5, PERSIST-01)

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-07

Additive §18 persistence schema. This migration ONLY adds tables/columns —
there is NO destructive DROP here (the thin-store ``workflow_artifacts`` DROP is
migration 0015, sequenced LAST in plan 05-06 after the read-cutover lands).

upgrade():
  - create_table: artifact_refs, workspaces, run_events, run_capabilities
    (every new table carries owner_id + workspace_id — AUTHZ-01)
  - indexes: artifact_refs (run_id, kind) + (content_hash); run_events (run_id, seq)
  - batch add_column on workflow_runs: owner_id, workspace_id, source_run_id,
    plan_id, budget_snapshot_json (all nullable/defaulted)
  - batch add_column on the EXISTING workflows table: owner_id, workspace_id,
    source (default "file"), manifest_json, version (default 1)
  - default-workspace backfill: one workspaces row per existing workflow_runs
    row, then set that run's owner_id = user_id and workspace_id = <new ws id>
    so every historical run ends up scoped (Highest-Risk Behavior 3).

downgrade():
  - reverse cleanly to the 0013 schema: drop the added workflows/workflow_runs
    columns (batch), drop the indexes, drop the four new tables. The backfilled
    workspaces rows vanish with the table drop.
"""

import uuid

from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- New tables (additive — no batch needed for create_table) ---------
    op.create_table(
        "artifact_refs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("producer_step", sa.String(), nullable=False),
        sa.Column("producer_agent", sa.String(), nullable=False),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("location", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("parents", sa.JSON(), nullable=True),
        sa.Column("derived_from", sa.String(), nullable=True),
        sa.Column(
            "visibility",
            sa.String(),
            nullable=False,
            server_default="private",
        ),
        sa.Column(
            "retention",
            sa.String(),
            nullable=False,
            server_default="run_ttl",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_runs.id"]),
        sa.ForeignKeyConstraint(["derived_from"], ["artifact_refs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_artifact_refs_run_kind", "artifact_refs", ["run_id", "kind"]
    )
    op.create_index(
        "ix_artifact_refs_content_hash", "artifact_refs", ["content_hash"]
    )

    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column(
            "kind", sa.String(), nullable=False, server_default="sandbox"
        ),
        sa.Column(
            "runtime", sa.String(), nullable=False, server_default="local"
        ),
        sa.Column("repo_id", sa.String(), nullable=True),
        sa.Column(
            "ttl", sa.String(), nullable=True, server_default="run_ttl"
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "run_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_run_events_run_seq", "run_events", ["run_id", "seq"]
    )

    op.create_table(
        "run_capabilities",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("runtime", sa.String(), nullable=False),
        sa.Column("model_overrides", sa.JSON(), nullable=True),
        sa.Column("skills", sa.JSON(), nullable=True),
        sa.Column("hooks", sa.JSON(), nullable=True),
        sa.Column("integrations", sa.JSON(), nullable=True),
        sa.Column("mcp_servers", sa.JSON(), nullable=True),
        sa.Column("versions", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- Extend workflow_runs (batch mandatory for SQLite/Postgres parity) -
    with op.batch_alter_table("workflow_runs") as batch_op:
        batch_op.add_column(sa.Column("owner_id", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column("workspace_id", sa.String(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("source_run_id", sa.String(), nullable=True)
        )
        batch_op.add_column(sa.Column("plan_id", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column("budget_snapshot_json", sa.JSON(), nullable=True)
        )

    # --- Extend the EXISTING workflows table (WorkflowDefinition) ----------
    with op.batch_alter_table("workflows") as batch_op:
        batch_op.add_column(sa.Column("owner_id", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column("workspace_id", sa.String(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "source", sa.String(), nullable=False, server_default="file"
            )
        )
        batch_op.add_column(
            sa.Column("manifest_json", sa.JSON(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "version", sa.Integer(), nullable=False, server_default="1"
            )
        )

    # --- Default-workspace backfill (data step, D-03 inline) ---------------
    # For every existing run create one workspaces row (workspace_id = its own
    # id) owned by the run's user_id, then scope the run to that workspace and
    # owner. Guards against zero existing rows. Works on SQLite + Postgres via
    # SQLAlchemy core over the live connection.
    bind = op.get_bind()
    meta = sa.MetaData()
    workflow_runs = sa.Table("workflow_runs", meta, autoload_with=bind)
    workspaces = sa.Table("workspaces", meta, autoload_with=bind)

    # WR-07: backfill ONLY runs that are not already scoped. Without the
    # ``workspace_id IS NULL`` guard a partial/retried upgrade() would create a
    # SECOND workspace row for runs already backfilled by the first attempt.
    # Additive migrations must be defensive against partial application.
    existing = bind.execute(
        sa.select(workflow_runs.c.id, workflow_runs.c.user_id)
        .where(workflow_runs.c.workspace_id.is_(None))
    ).fetchall()

    for run_id, user_id in existing:
        ws_id = str(uuid.uuid4())
        bind.execute(
            workspaces.insert().values(
                id=ws_id,
                owner_id=user_id,
                workspace_id=ws_id,
                kind="sandbox",
                runtime="local",
                ttl="run_ttl",
                # WR-07: evaluate now() per-row so backfilled workspaces do not all
                # share one identical created_at (which would hide ordering).
                created_at=sa.func.now(),
            )
        )
        bind.execute(
            workflow_runs.update()
            .where(workflow_runs.c.id == run_id)
            .values(owner_id=user_id, workspace_id=ws_id)
        )


def downgrade() -> None:
    # Reverse the column extends (batch), drop indexes, drop the four tables.
    with op.batch_alter_table("workflows") as batch_op:
        batch_op.drop_column("version")
        batch_op.drop_column("manifest_json")
        batch_op.drop_column("source")
        batch_op.drop_column("workspace_id")
        batch_op.drop_column("owner_id")

    with op.batch_alter_table("workflow_runs") as batch_op:
        batch_op.drop_column("budget_snapshot_json")
        batch_op.drop_column("plan_id")
        batch_op.drop_column("source_run_id")
        batch_op.drop_column("workspace_id")
        batch_op.drop_column("owner_id")

    op.drop_index("ix_run_events_run_seq", table_name="run_events")
    op.drop_index(
        "ix_artifact_refs_content_hash", table_name="artifact_refs"
    )
    op.drop_index("ix_artifact_refs_run_kind", table_name="artifact_refs")

    op.drop_table("run_capabilities")
    op.drop_table("run_events")
    op.drop_table("workspaces")
    op.drop_table("artifact_refs")
