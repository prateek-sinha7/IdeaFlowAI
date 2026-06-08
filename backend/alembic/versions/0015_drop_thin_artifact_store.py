"""0015 — drop the thin-store ``workflow_artifacts`` table (PERSIST-02, D-13 step 5).

The one sanctioned NON-additive migration of this phase. The thin-store
artifact-persistence layer (``agents/artifact_store/store.py`` artifact half + the
``WorkflowArtifact`` model) was deleted in 05-07 once every consumer was migrated
onto the persisted typed ``artifact_refs`` layer (05-06) and 0A characterization
parity was proven GREEN. This migration drops the now-orphaned table LAST (D-03),
after the read-cutover + mirror removal.

``downgrade()`` recreates ``workflow_artifacts`` with its original column shape +
the ``ix_workflow_artifacts_run_type`` index so the DROP is fully reversible (Q3).
The additive ``0014`` remains independently reversible.

Sequenced after 0014 (down_revision="0014"). Works on both SQLite + Postgres
(``op.drop_table`` / ``op.create_table`` need no batch).
"""

from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("workflow_artifacts")


def downgrade() -> None:
    op.create_table(
        "workflow_artifacts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workflow_run_id", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "schema_version",
            sa.String(),
            nullable=False,
            server_default="1.0",
        ),
        sa.Column("producing_agent_id", sa.String(), nullable=False),
        sa.Column("derived_from_artifact_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_runs.id"]),
        sa.ForeignKeyConstraint(["derived_from_artifact_id"], ["workflow_artifacts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workflow_artifacts_run_type",
        "workflow_artifacts",
        ["workflow_run_id", "type"],
        unique=False,
    )
