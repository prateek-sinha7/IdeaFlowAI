"""0019 — additive subagent_runs persistence (Phase 11 / FANOUT-10, PERSIST).

Adds the owner/workspace-scoped ``subagent_runs`` table — ONE row per fan-out child
spawned through the single kernel ``run_fanout`` spawn path. Each child row records
the worker agent, the parent step, the nesting depth, the isolation scope, and the
terminal status, so a cross-owner read returns nothing (default-deny via
``ScopedStore._scope_owner_ws``, the FANOUT-10 mitigation, T-11-01-03).

  * ``subagent_runs`` — carries ``owner_id`` + ``workspace_id`` (both NOT NULL,
    AUTHZ-01) so the ``ScopedStore`` default-deny filter scopes every read.
    ``isolation`` is a free ``String`` (``shared_read`` | ``sub_sandbox`` |
    ``worktree``) and ``status`` is a free ``String`` (``running`` | ``complete`` |
    ``failed`` | ``cancelled``) — NO enum type (Q3/INV-3: additive + reversible,
    consistent with the free-String ``outcome`` on 0018's ``exec_runs`` and the
    free-String ``provider`` on 0017's ``repositories``). ``cost`` is ``sa.JSON``
    (cost_class-weighted; the € amount stays dormant this milestone).
    ``ForeignKeyConstraint(["parent_run_id"], ["workflow_runs.id"])`` is NAMED to
    match the ORM so the alembic-check stays drift-free (the 0018/RUNTIME-02
    precedent).

ADDITIVE ONLY (Q3, INV-3): no existing table is altered. Sequenced after 0018
(down_revision="0018") — the head chain stays unbroken / single-head. ``downgrade()``
drops the index then the table (fully reversible; mirror of ``0018`` ``op.drop_table``).
Proven offline against in-memory SQLite (upgrade head -> downgrade -1 -> upgrade head).
"""

from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subagent_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("parent_run_id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),       # AUTHZ-01
        sa.Column("workspace_id", sa.String(), nullable=False),   # AUTHZ-01
        sa.Column("parent_step", sa.String(), nullable=False),
        sa.Column("worker_agent", sa.String(), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        # Free String (no enum type): 'shared_read' | 'sub_sandbox' | 'worktree'.
        sa.Column("isolation", sa.String(), nullable=False),
        # Free String (no enum type): 'running' | 'complete' | 'failed' | 'cancelled'.
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("tokens", sa.Integer(), nullable=True),
        sa.Column("cost", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["parent_run_id"], ["workflow_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_subagent_runs_parent", "subagent_runs", ["parent_run_id"])


def downgrade() -> None:
    op.drop_index("ix_subagent_runs_parent", table_name="subagent_runs")
    op.drop_table("subagent_runs")
