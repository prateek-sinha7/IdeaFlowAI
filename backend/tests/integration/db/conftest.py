"""Shared Alembic plumbing for the migration-reversibility tests.

Every ``upgrade / downgrade / upgrade`` proof needs the same two things: an Alembic
``Config`` pointed at a throwaway database, and that throwaway database's URL. Both
lived inline in each file before; they live here now so a new migration proof is a
test function and nothing else.

The eight pre-existing files in this folder still build their own config inline; fold
them onto ``alembic_config_for`` the next time one is touched.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config

# tests/integration/db/<file> -> backend/
_BACKEND_DIR = Path(__file__).resolve().parents[3]
_ALEMBIC_INI = _BACKEND_DIR / "alembic.ini"


def alembic_config_for(db_url: str) -> Config:
    """An Alembic ``Config`` bound to ``db_url`` and this repo's migration scripts."""
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    return cfg


@pytest.fixture
def fresh_db_url(tmp_path: Path) -> str:
    """URL of an empty, file-backed SQLite database unique to this test.

    A FILE, not ``:memory:``: Alembic opens its own connections, and an in-memory
    SQLite database is per-connection, so the migration would run against a database
    the assertions cannot see.
    """
    return f"sqlite:///{tmp_path / 'alembic_migration_proof.db'}"
