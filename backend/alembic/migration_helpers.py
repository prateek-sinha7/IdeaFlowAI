"""Idempotent DDL helpers for Alembic revisions.

WHY THIS MODULE EXISTS
----------------------
``backend/docker-entrypoint.sh`` runs ``alembic upgrade head`` under ``set -eu``
immediately before ``exec uvicorn``. A migration that raises therefore does not
produce a failed deploy step — it produces a **crash-looping container**, because
the process aborts before uvicorn ever binds the port. The single most common way
for an additive migration to raise is attempting to create an object that already
exists (``DuplicateColumn`` / ``DuplicateTable`` / ``DuplicateObject``), which
happens whenever a database is partially ahead of its stamped revision:

* a revision was applied but the ``alembic_version`` bump was lost (the
  0024/0025 incident repaired by revision 0028),
* an operator applied DDL by hand as a hotfix and the migration landed later,
* a revision was re-homed to a new ID (0031 -> 0036, 0032 -> 0037) and one
  database recorded the old ID while another recorded the new one,
* a downgrade left objects behind that the next upgrade tries to recreate.

Revision 0028 solved this inline with ``sa.inspect(bind)`` guards and documented
the rule as "additive migrations must be defensive against partial application".
0029, 0036 and 0037 then re-implemented the same reflection logic by hand. This
module is that pattern extracted once, so a new revision gets it by importing
rather than by remembering.

WHAT THIS MODULE IS *NOT* FOR
-----------------------------
These helpers do **not** protect against a developer editing an
already-applied revision. Alembic keys off the revision ID recorded in
``alembic_version``, so an edited revision that is already stamped is never
executed at all — idempotency is irrelevant because the code does not run.
That failure mode is caught at the source level by
``scripts/migration_guard.py`` (see its module docstring).

IMPORT CONTRACT
---------------
This module lives beside the Alembic environment and is imported from revision
files as::

    from migration_helpers import add_column_if_missing

``alembic/env.py`` inserts both the backend root and its own directory onto
``sys.path`` before revisions are loaded. This keeps the helper in the migration
subsystem while avoiding ``alembic.migration_helpers``: that package name belongs
to the installed Alembic distribution, not this repository's migration folder.

It depends only on SQLAlchemy reflection and ``alembic.op``. It must never
import ``app.*``: revisions are historical artifacts and must keep running even
after the ORM models they were written against have changed.

DIALECT SUPPORT
---------------
Every check goes through the dialect-neutral SQLAlchemy ``Inspector``, so the
helpers behave identically on PostgreSQL (deployed) and SQLite (the offline
migration tests in ``tests/unit/test_alembic.py``). No raw
``information_schema`` queries, no ``pg_catalog``.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op

__all__ = [
    "table_exists",
    "column_exists",
    "index_exists",
    "unique_constraint_exists",
    "foreign_key_exists",
    "create_table_if_missing",
    "add_column_if_missing",
    "create_index_if_missing",
    "create_unique_constraint_if_missing",
    "drop_table_if_present",
    "drop_column_if_present",
    "drop_index_if_present",
    "drop_constraint_if_present",
]


# ---------------------------------------------------------------------------
# Existence predicates
#
# Each predicate builds a FRESH Inspector on every call rather than caching one
# at module or function scope. This is not redundant: an Inspector memoises its
# view of the schema, so a guard that reuses one after an intervening
# ``op.create_table`` reads a stale answer and skips the follow-up index. That
# exact trap is called out in revision 0028's inline comment ("Re-inspect: the
# table may have just been created above, and an inspector caches its view").
# ---------------------------------------------------------------------------


def _inspector() -> Any:
    """Return a fresh :class:`~sqlalchemy.engine.Inspector` for the live migration bind."""
    return sa.inspect(op.get_bind())


def table_exists(table: str) -> bool:
    """Return True when ``table`` is present in the connected database."""
    return table in set(_inspector().get_table_names())


def column_exists(table: str, column: str) -> bool:
    """Return True when ``table.column`` is present.

    Returns False when the table itself is absent, rather than raising, so a
    caller can write ``if not column_exists(...)`` without first checking the
    table. There is no ``ADD COLUMN IF NOT EXISTS`` in Alembic's op API — that
    kwarg exists only for ``create_table``/``create_index`` — so reflection is
    the only portable way to guard a column add.
    """
    if not table_exists(table):
        return False
    return column in {col["name"] for col in _inspector().get_columns(table)}


def index_exists(table: str, index: str) -> bool:
    """Return True when index ``index`` exists on ``table`` (False if no such table)."""
    if not table_exists(table):
        return False
    return index in {ix["name"] for ix in _inspector().get_indexes(table)}


def unique_constraint_exists(table: str, constraint: str) -> bool:
    """Return True when named UNIQUE constraint ``constraint`` exists on ``table``.

    Note the dialect asymmetry this papers over: PostgreSQL backs a UNIQUE
    constraint with an index of the same name, so a constraint may surface via
    ``get_indexes`` as well. Both are consulted, because a database repaired by
    hand may have only the index.
    """
    if not table_exists(table):
        return False
    inspector = _inspector()
    names = {uc["name"] for uc in inspector.get_unique_constraints(table)}
    names |= {ix["name"] for ix in inspector.get_indexes(table) if ix.get("unique")}
    return constraint in names


def foreign_key_exists(table: str, constraint: str) -> bool:
    """Return True when named FOREIGN KEY constraint ``constraint`` exists on ``table``.

    SQLite does not name inline foreign keys, so reflection returns ``None`` for
    those; such keys are invisible here by construction. That is acceptable —
    the deployed database is PostgreSQL, and the SQLite path only needs the
    guard not to raise.
    """
    if not table_exists(table):
        return False
    return constraint in {fk.get("name") for fk in _inspector().get_foreign_keys(table)}


# ---------------------------------------------------------------------------
# Guarded DDL — upgrade direction
#
# Each wrapper returns True when it performed the DDL and False when it skipped
# because the object was already present. Returning the outcome (rather than
# ``None``) lets a revision log or branch on what it actually did, which is what
# makes a repair revision auditable after the fact.
# ---------------------------------------------------------------------------


def create_table_if_missing(table: str, *columns: Any, **kwargs: Any) -> bool:
    """``op.create_table`` unless ``table`` already exists."""
    if table_exists(table):
        return False
    op.create_table(table, *columns, **kwargs)
    return True


def add_column_if_missing(table: str, column: sa.Column[Any]) -> bool:
    """``ADD COLUMN`` unless the column already exists.

    Routed through ``batch_alter_table`` per the project's migration rules
    (rule 3: batch mode for column adds, for SQLite compatibility). The column
    must be nullable or carry a server default — the additive-only rule (Q3)
    means an existing populated table can never accept a NOT NULL column
    without one.
    """
    if column_exists(table, column.name):
        return False
    with op.batch_alter_table(table) as batch:
        batch.add_column(column)
    return True


def create_index_if_missing(
    index: str,
    table: str,
    columns: list[str],
    *,
    unique: bool = False,
    **kwargs: Any,
) -> bool:
    """``op.create_index`` unless the index already exists.

    Reflection is used rather than the native ``if_not_exists=True`` kwarg
    (available on this Alembic version and used by revision 0030) so the return
    value reports whether the index was actually created. ``IF NOT EXISTS``
    cannot report that, and the skip is worth logging in a repair revision.
    """
    if index_exists(table, index):
        return False
    op.create_index(index, table, columns, unique=unique, **kwargs)
    return True


def create_unique_constraint_if_missing(
    constraint: str, table: str, columns: list[str]
) -> bool:
    """``ADD CONSTRAINT ... UNIQUE`` unless it already exists.

    IMPORTANT — this does not check for pre-existing duplicate rows. Adding a
    UNIQUE constraint to a table that violates it raises, which crash-loops the
    container. When the target table may hold duplicates, count them first and
    skip loudly instead; revision 0028 is the reference implementation of that
    pattern (``_duplicate_group_count`` plus a printed SKIPPING warning).
    """
    if unique_constraint_exists(table, constraint):
        return False
    with op.batch_alter_table(table) as batch:
        batch.create_unique_constraint(constraint, columns)
    return True


# ---------------------------------------------------------------------------
# Guarded DDL — downgrade direction
#
# Downgrades need the mirror-image guard for the same reason: a downgrade run
# against a database that never received the object must not raise, or the
# rollback path is itself broken. Note that the project's own precedent (0028)
# shows a downgrade should sometimes be a deliberate no-op instead — dropping an
# object owned by an EARLIER, already-stamped revision recreates the drift the
# repair existed to fix.
# ---------------------------------------------------------------------------


def drop_table_if_present(table: str) -> bool:
    """``op.drop_table`` only when the table exists."""
    if not table_exists(table):
        return False
    op.drop_table(table)
    return True


def drop_column_if_present(table: str, column: str) -> bool:
    """``DROP COLUMN`` only when the column exists."""
    if not column_exists(table, column):
        return False
    with op.batch_alter_table(table) as batch:
        batch.drop_column(column)
    return True


def drop_index_if_present(index: str, table: str) -> bool:
    """``op.drop_index`` only when the index exists."""
    if not index_exists(table, index):
        return False
    op.drop_index(index, table_name=table)
    return True


def drop_constraint_if_present(
    constraint: str, table: str, type_: str = "unique"
) -> bool:
    """``DROP CONSTRAINT`` only when the constraint exists.

    ``type_`` is forwarded to ``batch_alter_table.drop_constraint`` and is
    required for SQLite batch mode to rebuild the table correctly.
    """
    exists = (
        unique_constraint_exists(table, constraint)
        if type_ == "unique"
        else foreign_key_exists(table, constraint)
    )
    if not exists:
        return False
    with op.batch_alter_table(table) as batch:
        batch.drop_constraint(constraint, type_=type_)
    return True
