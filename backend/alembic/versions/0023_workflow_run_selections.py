"""0023 — additive launch-time selections map on workflow_runs (Phase 22, WR-02).

The composer persists a launch-time per-step ``selections`` map —
``{agent_id: {validators, gates, model, retry, ...}}`` (the EXACT shape
``ExecutionEngine._apply_selections`` overlays, engine.py:4519). Persist it on
the ``WorkflowRun`` row at run CREATION so a backend-restart resume
(``resume_run``) can re-apply the same user-composed levers — re-validated
``trust="user"`` at overlay time, so the resume overlay can only ever carry
user-allowed levers (privilege-bounded by construction).

Add exactly one nullable JSON column the launch path writes:

  * ``selections_json`` (JSON, nullable) — the launch-validated per-step
    selections map, ``None`` for every legacy/non-composed run.

ADDITIVE ONLY (Q3, INV-3): no new table, no alter of existing columns or
constraints. The run row already carries ``owner_id``/``workspace_id`` scope
(workflow.py) so no new authz surface (D-12). Sequenced after 0022
(``down_revision="0022"``) — the head chain stays single-head. Existing rows
stay NULL → ``_apply_selections(None)`` is a no-op → byte/event parity (INV-3).
``downgrade()`` drops the column inside a ``batch_alter_table`` (fully
reversible, SQLite-portable via the 0017/0021/0022 batch idiom).
"""

from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("workflow_runs") as b:
        b.add_column(sa.Column("selections_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("workflow_runs") as b:
        b.drop_column("selections_json")
