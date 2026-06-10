"""0018 — additive exec_runs audit table (Phase 10 / EXEC-01, AUDIT).

Adds the owner/workspace-scoped ``exec_runs`` table — one row per
``Workspace.exec_command`` invocation, written at the enforcement point so EVERY
exec path (allowed / denied / killed) is audited bypass-proof regardless of caller
(T-10-01-07). The recorder callback wired in 10-02 invokes
``ScopedStore.record_exec_run`` on every outcome.

  * ``exec_runs`` — carries ``owner_id`` + ``workspace_id`` (both NOT NULL,
    AUTHZ-01) so the ``ScopedStore`` default-deny filter scopes every read
    (T-10-01-08). ``outcome`` is a free ``String`` (``allowed`` | ``denied`` |
    ``killed``) — NO ``sa.Enum`` (R-G: additive + reversible, consistent with the
    free-String ``provider`` on 0017's ``repositories``). ``argv_json`` /
    ``policy_snapshot_json`` are ``sa.JSON``; ``output_digest`` carries only a
    TRUNCATED digest, never the raw child output.

ADDITIVE ONLY (Q3, INV-3): no existing table is altered. Sequenced after 0017
(down_revision="0017") — the head chain stays unbroken. ``downgrade()`` drops the
table (fully reversible; mirror of ``0017`` ``op.drop_table``). Proven offline
against in-memory SQLite (upgrade head -> downgrade -1 -> upgrade head).
"""

from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exec_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),       # AUTHZ-01
        sa.Column("workspace_id", sa.String(), nullable=False),   # AUTHZ-01
        sa.Column("step", sa.String(), nullable=False),
        sa.Column("argv_json", sa.JSON(), nullable=False),
        # Free String (NO sa.Enum): 'allowed' | 'denied' | 'killed'.
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("policy_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("output_digest", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_exec_runs_run", "exec_runs", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_exec_runs_run", table_name="exec_runs")
    op.drop_table("exec_runs")
