"""Reversibility + shape of the additive ``0020 wave_runs`` migration (Phase 12 / WAVE-02).

Moved out of ``tests/unit/agents/test_wave_runs.py`` in Batch 6 — running the Alembic
chain is migration work against a real database. ``ScopedStore.record_wave_run`` /
``update_wave_run`` live in ``tests/integration/repositories/test_wave_runs_db.py``.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from sqlalchemy import create_engine, inspect

from tests.integration.db.conftest import alembic_config_for

# tests/integration/db/<this file> -> backend/
_BACKEND_DIR = Path(__file__).resolve().parents[3]

_EXPECTED_WAVE_COLUMNS = {
    "id",
    "run_id",
    "owner_id",
    "workspace_id",
    "step",
    "wave_index",
    "task_ids",
    "status",
    "created_at",
}


def test_0020_reversible_offline(fresh_db_url: str) -> None:
    """``upgrade 0020`` -> ``downgrade 0019`` -> ``upgrade 0020`` round-trips clean.

    Pinned to the explicit ``0020``/``0019`` revisions (NOT ``head``/``-1``) so the
    test stays correct as later migrations chain on (a future 0021 would make a
    ``head``/``-1`` round-trip land on 0020, not 0019, and false-fail). 0020 is the
    single head at this plan; the pinning proves the 0019→0020 step is reversible.
    """
    cfg = alembic_config_for(fresh_db_url)

    command.upgrade(cfg, "0020")
    engine = create_engine(fresh_db_url)
    inspector = inspect(engine)
    assert inspector.has_table("wave_runs"), "wave_runs missing after upgrade 0020"
    cols = {c["name"] for c in inspector.get_columns("wave_runs")}
    assert _EXPECTED_WAVE_COLUMNS.issubset(
        cols
    ), f"wave_runs missing columns: {sorted(_EXPECTED_WAVE_COLUMNS - cols)}"
    engine.dispose()

    # downgrade to 0019 drops wave_runs (the 0019→0020 step is reversible).
    command.downgrade(cfg, "0019")
    engine = create_engine(fresh_db_url)
    inspector = inspect(engine)
    assert not inspector.has_table("wave_runs"), "downgrade to 0019 must drop wave_runs"
    engine.dispose()

    # upgrade back to 0020 recreates it.
    command.upgrade(cfg, "0020")
    engine = create_engine(fresh_db_url)
    inspector = inspect(engine)
    assert inspector.has_table("wave_runs"), "wave_runs missing after re-upgrade"
    engine.dispose()


def test_0020_migration_uses_free_string_status() -> None:
    """No ``sa.Enum`` on the 0020 migration — status is a free String (Q3/INV-3)."""
    mig = _BACKEND_DIR / "alembic" / "versions" / "0020_wave_runs.py"
    text = mig.read_text(encoding="utf-8")
    assert "sa.Enum" not in text, "0020 must use a free String status (NO sa.Enum)"
    assert 'revision = "0020"' in text
    assert 'down_revision = "0019"' in text
