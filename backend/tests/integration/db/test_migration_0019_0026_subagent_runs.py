"""Reversibility of the ``0019 subagent_runs`` + ``0026`` task-identity migrations.

Phase 11 / FANOUT-10 and RESUME-06. Moved out of
``tests/unit/agents/test_subagent_runs.py`` in Batch 6 — running the Alembic chain is
migration work against a real database. The store behaviour lives in
``tests/integration/repositories/test_subagent_runs_db.py``; the pure fan-out / budget /
compiler seams stayed in the unit suite.

``fresh_db_url`` and ``alembic_config_for`` come from this folder's conftest.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from sqlalchemy import create_engine, inspect

from tests.integration.db.conftest import alembic_config_for as _make_config

# tests/integration/db/<this file> -> backend/
_BACKEND_DIR = Path(__file__).resolve().parents[3]

_EXPECTED_SUBAGENT_COLUMNS = {
    "id",
    "parent_run_id",
    "owner_id",
    "workspace_id",
    "parent_step",
    "worker_agent",
    "depth",
    "isolation",
    "status",
    "tokens",
    "cost",
    "created_at",
}


def test_0019_reversible_offline(fresh_db_url: str) -> None:
    """``upgrade 0019`` -> ``downgrade 0018`` -> ``upgrade 0019`` round-trips clean.

    Pinned to the explicit ``0019``/``0018`` revisions (NOT ``head``/``-1``) so the
    test stays correct as later migrations chain on (12-01 added 0020 after 0019; a
    ``head``/``-1`` round-trip would land on 0019, not 0018, and false-fail).
    """
    cfg = _make_config(fresh_db_url)

    command.upgrade(cfg, "0019")
    engine = create_engine(fresh_db_url)
    inspector = inspect(engine)
    assert inspector.has_table(
        "subagent_runs"
    ), "subagent_runs missing after upgrade 0019"
    cols = {c["name"] for c in inspector.get_columns("subagent_runs")}
    assert _EXPECTED_SUBAGENT_COLUMNS.issubset(
        cols
    ), f"subagent_runs missing columns: {sorted(_EXPECTED_SUBAGENT_COLUMNS - cols)}"
    engine.dispose()

    # downgrade to 0018 drops subagent_runs (the 0018→0019 step is reversible).
    command.downgrade(cfg, "0018")
    engine = create_engine(fresh_db_url)
    inspector = inspect(engine)
    assert not inspector.has_table(
        "subagent_runs"
    ), "downgrade to 0018 must drop subagent_runs"
    engine.dispose()

    # upgrade back to 0019 recreates it.
    command.upgrade(cfg, "0019")
    engine = create_engine(fresh_db_url)
    inspector = inspect(engine)
    assert inspector.has_table(
        "subagent_runs"
    ), "subagent_runs missing after re-upgrade"
    engine.dispose()


def test_0019_migration_uses_free_string_status() -> None:
    """No ``sa.Enum`` on the 0019 migration — status is a free String (Q3/INV-3)."""
    mig = _BACKEND_DIR / "alembic" / "versions" / "0019_subagent_runs.py"
    text = mig.read_text(encoding="utf-8")
    assert "sa.Enum" not in text, "0019 must use a free String status (NO sa.Enum)"
    assert 'revision = "0019"' in text
    assert 'down_revision = "0018"' in text


def test_0026_reversible_offline(fresh_db_url: str) -> None:
    """RESUME-06: ``upgrade 0026`` adds task_id + worker_index; ``downgrade 0025``
    drops them; ``upgrade 0026`` re-adds — a clean additive round-trip.

    Pinned to the explicit ``0026``/``0025`` revisions (NOT ``head``/``-1``): the
    ledger has PRE-EXISTING stale single-head asserts (test_migrations.py) proving
    ``head`` is ambiguous here, and a ``-1`` from 0026 would land on 0025 anyway.
    The existing subagent_runs columns survive the downgrade (only the two new
    columns are dropped — additive-reversible)."""
    cfg = _make_config(fresh_db_url)

    # upgrade to 0026 — the two new nullable columns are present.
    command.upgrade(cfg, "0026")
    engine = create_engine(fresh_db_url)
    inspector = inspect(engine)
    assert inspector.has_table(
        "subagent_runs"
    ), "subagent_runs missing after upgrade 0026"
    cols = {c["name"] for c in inspector.get_columns("subagent_runs")}
    assert "task_id" in cols, "task_id missing after upgrade 0026"
    assert "worker_index" in cols, "worker_index missing after upgrade 0026"
    # The pre-existing columns are untouched (additive, not a rewrite).
    assert _EXPECTED_SUBAGENT_COLUMNS.issubset(cols), (
        f"upgrade 0026 must not drop existing columns: missing "
        f"{sorted(_EXPECTED_SUBAGENT_COLUMNS - cols)}"
    )
    engine.dispose()

    # downgrade to 0025 drops ONLY the two new columns; the table + originals stay.
    command.downgrade(cfg, "0025")
    engine = create_engine(fresh_db_url)
    inspector = inspect(engine)
    assert inspector.has_table(
        "subagent_runs"
    ), "downgrade to 0025 must keep subagent_runs (only the 2 new columns drop)"
    cols = {c["name"] for c in inspector.get_columns("subagent_runs")}
    assert "task_id" not in cols, "downgrade 0025 must drop task_id"
    assert "worker_index" not in cols, "downgrade 0025 must drop worker_index"
    assert _EXPECTED_SUBAGENT_COLUMNS.issubset(
        cols
    ), "downgrade 0025 must keep the pre-0026 columns"
    engine.dispose()

    # upgrade back to 0026 re-adds the two columns (reversible).
    command.upgrade(cfg, "0026")
    engine = create_engine(fresh_db_url)
    inspector = inspect(engine)
    cols = {c["name"] for c in inspector.get_columns("subagent_runs")}
    assert (
        "task_id" in cols and "worker_index" in cols
    ), "re-upgrade 0026 must re-add task_id + worker_index"
    engine.dispose()
