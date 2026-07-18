"""0026 — additive per-child task identity on subagent_runs (Phase 46, RESUME-06).

The kernel stamps each fan-out / wave worker's ``subagent_runs`` row with its
task identity **at SPAWN** — before the crash window — so a crashed run can, on
resume, tell which workers already completed (the RESUME-09 skip cursor reads
these). Two additive nullable columns:

  * ``task_id`` (String, nullable) — the plan-global task id (``wave.task_ids[idx]``
    / ``t.id``), the skip-cursor key (globally unique across waves).
  * ``worker_index`` (Integer, nullable) — the wave-local worker position (``idx``,
    0-based per ``run_fanout`` call); an audit/ordering aid only (ambiguous across
    waves, so the cursor keys on ``task_id``, never this).

ADDITIVE ONLY (Q3, INV-3 / the pre-authorized CR-03-followup shape): no new table,
no alter of existing columns or constraints, existing FK ``parent_run_id`` +
``Index("ix_subagent_runs_parent")`` untouched. Both columns are nullable →
scripted/legacy rows (and prototype/od_ golden runs, which create no
``subagent_runs`` rows) stay byte/event-identical (the columns are dormant).
Sequenced after 0025 (``down_revision="0025"``) — the head chain stays single-head.
``batch_alter_table.add_column`` on nullable columns is a metadata-only additive op
(no table rewrite, no backfill). ``downgrade()`` drops both columns inside a
``batch_alter_table`` in reverse order (fully reversible, SQLite-portable via the
0022/0023 batch idiom).
"""

from alembic import op
import sqlalchemy as sa

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("subagent_runs") as b:
        b.add_column(sa.Column("task_id", sa.String(), nullable=True))
        b.add_column(sa.Column("worker_index", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("subagent_runs") as b:
        b.drop_column("worker_index")
        b.drop_column("task_id")
