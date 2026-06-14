"""0021 — additive saved user-workflows (Phase 21).

Reuse the dormant ``workflows`` table (``WorkflowDefinition``) for
``source="user"`` rows — NO new table (REUSE-TABLE-INV12). Add exactly three
nullable columns the saved-workflow router persists:

  * ``base_pipeline_type`` (String, nullable) — the saved-workflow base type
    ("custom" in v1).
  * ``model_overrides`` (JSON, nullable) — the persisted per-agent
    ``{agent_id: model_id}`` override map.
  * ``description`` (String, nullable) — the user-supplied free-text blurb. A
    DEDICATED column (WR-03): description was previously overloaded onto
    ``constitution_ref`` (whose semantic is a workflow_memory key), a latent
    footgun for any future cross-source ``constitution_ref`` reader.

Plus ``ix_workflows_owner_source`` backing the owner-scoped GET list query
(``WHERE owner_id … AND source …``).

ADDITIVE ONLY (Q3, INV-3): no new table, no alter of existing columns or
constraints. Sequenced after 0020 (``down_revision="0020"``) — the head chain
stays single-head. ``downgrade()`` drops the index then both columns inside a
``batch_alter_table`` (fully reversible, SQLite-portable via the 0017 batch
idiom). Proven offline against in-memory SQLite (upgrade head → downgrade -1 →
upgrade head).
"""

from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("workflows") as b:
        b.add_column(sa.Column("base_pipeline_type", sa.String(), nullable=True))
        b.add_column(sa.Column("model_overrides", sa.JSON(), nullable=True))
        b.add_column(sa.Column("description", sa.String(), nullable=True))
    op.create_index(
        "ix_workflows_owner_source", "workflows", ["owner_id", "source"]
    )


def downgrade() -> None:
    op.drop_index("ix_workflows_owner_source", table_name="workflows")
    with op.batch_alter_table("workflows") as b:
        b.drop_column("description")
        b.drop_column("model_overrides")
        b.drop_column("base_pipeline_type")
