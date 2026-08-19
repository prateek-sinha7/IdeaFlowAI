"""Collapse the od_prototype run-label onto prototype.

``od_prototype`` was never a pipeline. It was a second LABEL for the ``prototype``
manifest, resolved by an id-alias, and it owned only half the lifecycle: a run
launched as ``od_prototype`` was revised as ``prototype_revision``, because no
``od_prototype_revision`` pipeline ever existed (no manifest, no agents, no tier).
The two halves were bridged by hand-written remap tables in the API layer that
lived in one of the two revision entry points, so revising such a run over REST
returned a 403 the user could not act on.

The label is gone from the code (``agents/registry._OD_ALIAS_BASE`` is now empty).
This migration brings the persisted rows with it — without it, every historical
run keeps the orphaned label and keeps failing exactly as before.

Two columns carry it:
  * ``workflow_runs.type``            — the run's own pipeline label
  * ``workflows.base_pipeline_type``  — saved/composed workflow rows

``od_prototype_revision`` is included for completeness. No such row should exist
(the pipeline was never dispatchable), but the run-label was accepted by the
launch surface, so a stray row must not be left pointing at a type that no longer
resolves.

Reversible: ``downgrade`` restores the label on ``workflow_runs`` only for rows
that would have carried it — but see the note there, the mapping is lossy.

Revision ID: 0032
Revises: 0031
"""

import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


# (old_label, new_label)
_COLLAPSE = [
    ("od_prototype", "prototype"),
    ("od_prototype_revision", "prototype_revision"),
]


# (table, column) pairs carrying a pipeline label.
_LABEL_COLUMNS = [
    ("workflow_runs", "type"),
    ("workflows", "base_pipeline_type"),
]


def upgrade() -> None:
    conn = op.get_bind()
    # sa.text with BOUND params, not exec_driver_sql with %s: the driver paramstyle
    # differs per backend (psycopg2 uses %s, sqlite3 uses ?), and the migration
    # tests run this against SQLite while production is Postgres.
    existing = set(sa.inspect(conn).get_table_names())
    for table, column in _LABEL_COLUMNS:
        if table not in existing:
            continue
        for old, new in _COLLAPSE:
            conn.execute(
                sa.text(
                    f"UPDATE {table} SET {column} = :new WHERE {column} = :old"
                ),
                {"new": new, "old": old},
            )


def downgrade() -> None:
    """Intentionally a no-op.

    The collapse is LOSSY: after upgrade, a row reading ``prototype`` may have
    been minted as ``prototype`` or as ``od_prototype``, and nothing distinguishes
    them. Rewriting every ``prototype`` row back to ``od_prototype`` would
    mislabel the runs that were always ``prototype`` — a worse state than the one
    being restored. Since the application no longer resolves ``od_prototype`` at
    all, re-introducing the label would also produce rows the code cannot route.

    Downgrading the schema is therefore safe; the data stays collapsed.
    """
