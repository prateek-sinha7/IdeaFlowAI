"""0022 — additive deliverable mimetype/filename on workflow_runs (Phase 22, UXFIX-02 / D-19).

The engine already EMITS ``deliverable_mimetype`` + ``deliverable_filename`` on
every ``pipeline_complete`` (engine.py:2117-2128) and both keys are in
``_VOLATILE_STRIP_KEYS`` (INV-3-safe by construction). Persist them on the
``WorkflowRun`` row so history-reopen drives the deliverable mimetype from the
DECLARED/resolved value — not the FE text-sniff heuristic — so a custom BINARY
deliverable (e.g. ``application/zip``) re-renders faithfully on reopen.

Add exactly two nullable columns the pipeline-complete persistence writes:

  * ``deliverable_mimetype`` (String, nullable) — the declared-or-resolved
    deliverable mimetype emitted on pipeline_complete.
  * ``deliverable_filename`` (String, nullable) — the resolved deliverable
    filename emitted on pipeline_complete.

ADDITIVE ONLY (Q3, INV-3): no new table, no alter of existing columns or
constraints. The run row already carries ``owner_id``/``workspace_id`` scope
(workflow.py:58-59) so no new authz surface. Sequenced after 0021
(``down_revision="0021"``) — the head chain stays single-head. Existing rows
stay NULL → reopen falls back to the heuristic (parity). ``downgrade()`` drops
both columns inside a ``batch_alter_table`` (fully reversible, SQLite-portable
via the 0017/0021 batch idiom).
"""

from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("workflow_runs") as b:
        b.add_column(sa.Column("deliverable_mimetype", sa.String(), nullable=True))
        b.add_column(sa.Column("deliverable_filename", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("workflow_runs") as b:
        b.drop_column("deliverable_filename")
        b.drop_column("deliverable_mimetype")
