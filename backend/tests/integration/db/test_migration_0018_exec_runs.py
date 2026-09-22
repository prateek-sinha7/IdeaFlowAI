"""Reversibility of the additive ``0018 exec_runs`` migration (Phase 10 / EXEC-01).

Moved out of ``tests/unit/agents/test_exec_runs.py`` in Batch 6: running the real
Alembic chain (``upgrade`` -> ``downgrade`` -> ``upgrade head``) is migration work
against a real database, not a unit test. The behaviour of
``ScopedStore.record_exec_run`` lives in
``tests/integration/repositories/test_exec_runs_db.py``; the best-effort degrade of
``KernelServices.record_exec_run`` stayed in the unit suite.
"""

from __future__ import annotations

from alembic import command
from sqlalchemy import create_engine, inspect

from tests.integration.db.conftest import alembic_config_for

_EXPECTED_EXEC_COLUMNS = {
    "id",
    "run_id",
    "owner_id",
    "workspace_id",
    "step",
    "argv_json",
    "outcome",
    "exit_code",
    "duration_ms",
    "policy_snapshot_json",
    "output_digest",
    "created_at",
}


def test_0018_reversible_offline(fresh_db_url: str) -> None:
    """``upgrade 0018`` -> ``downgrade -1`` -> ``upgrade head`` round-trips clean.

    After ``upgrade 0018`` the ``exec_runs`` table exists with the expected
    columns; ``downgrade -1`` (0018 -> 0017) drops it; an ``upgrade head``
    recreates it (mirror of the 0017 reversibility proof). Pinned to revision
    0018 (not ``head``) so later additive migrations (0019+) don't shift what
    one downgrade step removes.
    """
    cfg = alembic_config_for(fresh_db_url)

    command.upgrade(cfg, "0018")
    engine = create_engine(fresh_db_url)
    inspector = inspect(engine)
    assert inspector.has_table("exec_runs"), "exec_runs missing after upgrade 0018"
    cols = {c["name"] for c in inspector.get_columns("exec_runs")}
    assert _EXPECTED_EXEC_COLUMNS.issubset(
        cols
    ), f"exec_runs missing columns: {sorted(_EXPECTED_EXEC_COLUMNS - cols)}"
    engine.dispose()

    # downgrade -1 drops exec_runs (pinned at 0018; -1 lands on 0017).
    command.downgrade(cfg, "-1")
    engine = create_engine(fresh_db_url)
    inspector = inspect(engine)
    assert not inspector.has_table("exec_runs"), "downgrade -1 must drop exec_runs"
    engine.dispose()

    # upgrade head recreates it.
    command.upgrade(cfg, "head")
    engine = create_engine(fresh_db_url)
    inspector = inspect(engine)
    assert inspector.has_table("exec_runs"), "exec_runs missing after re-upgrade"
    engine.dispose()
