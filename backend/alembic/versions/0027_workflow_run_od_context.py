"""0027 — additive od_context_json on workflow_runs (KAN-120 / RESUME-18).

When an od_ppt / od_prototype run is launched the template + design-system
context (``od_context``) is resolved at launch time and passed to ``_execute_impl``
in memory.  The resume tier (Phase 50 ``resume_run`` / ``_drive_resumed_stream``)
has no way to reconstruct it because the WorkflowRun row carried no such column —
so resumed od_ppt/prototype runs ran the PPT agents WITHOUT template or DS context
and produced empty / "Invalid presentation output" results.

This migration adds ONE additive nullable JSON column to ``workflow_runs``:

  * ``od_context_json`` (JSON, nullable) — the serialised launch-time od_context
    dict (keys: ``template_body``, ``design_system``, ``design_system_id``,
    ``template_id``, ``no_template``, etc.).  Written at run creation; read back by
    ``resume_run`` before calling ``_drive_resumed_stream``.

ADDITIVE ONLY (Q3): no new table, no alter of existing columns, no constraint
changes.  Nullable → every legacy row stays NULL (the resume path treats NULL as
``od_context=None``, the pre-fix behavior → byte/event identical for non-OD runs).
Sequenced after 0026 (``down_revision="0026"``).  ``batch_alter_table`` ensures
SQLite portability (mirrors the 0022/0023/0026 pattern).
"""

from alembic import op
import sqlalchemy as sa

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("workflow_runs") as b:
        b.add_column(sa.Column("od_context_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("workflow_runs") as b:
        b.drop_column("od_context_json")
