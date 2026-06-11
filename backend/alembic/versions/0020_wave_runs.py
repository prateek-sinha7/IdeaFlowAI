"""0020 — additive wave_runs persistence (Phase 12 / WAVE-02, PERSIST).

Adds the owner/workspace-scoped ``wave_runs`` table — ONE row per executed WAVE the
``wave_scheduler`` strategy dispatches through the single kernel ``run_fanout`` spawn
path. Each row records the producing step, the wave index, the task ids fanned out in
that wave, and the terminal status — so a cross-owner read returns nothing (default-deny
via ``ScopedStore._scope_owner_ws``, the T-12-01-IDOR mitigation). This is the durable
substrate the mid-wave resume (12-03) reads.

  * ``wave_runs`` — carries ``owner_id`` + ``workspace_id`` (both NOT NULL, AUTHZ-01)
    so the ``ScopedStore`` default-deny filter scopes every read. ``status`` is a free
    ``String`` (``running`` | ``completed`` | ``failed`` | ``cancelled``) — NO enum type
    (Q3/INV-3: additive + reversible, consistent with the free-String ``status`` on
    0019's ``subagent_runs`` and ``outcome`` on 0018's ``exec_runs``). ``task_ids`` is
    ``sa.JSON`` (§18 task_ids[]). ``ForeignKeyConstraint(["run_id"], ["workflow_runs.id"])``
    is NAMED to match the ORM so the alembic-check stays drift-free (the 0019 precedent).

ADDITIVE ONLY (Q3, INV-3): no existing table is altered. Sequenced after 0019
(down_revision="0019") — the head chain stays unbroken / single-head. ``downgrade()``
drops the index then the table (fully reversible; mirror of ``0019`` ``op.drop_table``).
Proven offline against in-memory SQLite (upgrade head -> downgrade -1 -> upgrade head).
"""

from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wave_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),       # AUTHZ-01
        sa.Column("workspace_id", sa.String(), nullable=False),   # AUTHZ-01
        sa.Column("step", sa.String(), nullable=False),
        sa.Column("wave_index", sa.Integer(), nullable=False),
        sa.Column("task_ids", sa.JSON(), nullable=False),         # §18 task_ids[]
        # Free String (no enum type): 'running' | 'completed' | 'failed' | 'cancelled'.
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wave_runs_run", "wave_runs", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_wave_runs_run", table_name="wave_runs")
    op.drop_table("wave_runs")
