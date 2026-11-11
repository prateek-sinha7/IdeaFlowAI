"""Add ``steps`` to ``workflow_builder_messages``.

The builder panel shows a turn as thinking, tool calls and checks in the order they
happened. While a turn runs the browser builds that order from the event stream. This
column keeps it for the finished reply: a JSON list of steps, each
``{"kind": "thinking", "text": ...}``, ``{"kind": "tools", "call_ids": [...]}`` or
``{"kind": "check", "check": {...}}``. A tools step names the tool rows of the same
turn by ``call_id``.

ADDITIVE ONLY: one nullable column on an existing table, no data touched. Rows from
before this migration keep NULL and the reader falls back to the ``thinking`` column and
the tool rows. ``owner_id`` / ``workspace_id`` are already on the table.

RE-APPLIABILITY: ``add_column_if_missing`` skips the add when the column exists, and goes
through ``batch_alter_table`` for SQLite (the 0041 pattern), so the idempotency ratchet
(``tests/integration/db/test_migration_idempotency.py``) passes;
``docker-entrypoint.sh`` runs ``alembic upgrade head`` under ``set -eu``.

The model in ``app/models/workflow_builder.py`` must mirror this exactly.
"""

import sqlalchemy as sa

from migration_helpers import add_column_if_missing, drop_column_if_present

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    add_column_if_missing(
        "workflow_builder_messages", sa.Column("steps", sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    drop_column_if_present("workflow_builder_messages", "steps")
