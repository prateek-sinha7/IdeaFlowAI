"""Shared Alembic plumbing for the migration-reversibility tests.

Every ``upgrade / downgrade / upgrade`` proof needs the same two things: an Alembic
``Config`` pointed at a throwaway database, and that throwaway database's URL. Both
lived inline in each file before; they live here now so a new migration proof is a
test function and nothing else.

The eight pre-existing files in this folder still build their own config inline; fold
them onto ``alembic_config_for`` the next time one is touched.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

# tests/integration/db/<file> -> backend/
_BACKEND_DIR = Path(__file__).resolve().parents[3]
_ALEMBIC_INI = _BACKEND_DIR / "alembic.ini"


def postgres_admin_url(request: pytest.FixtureRequest) -> str:
    """Server-level PostgreSQL URL: the env override, else the testcontainers server.

    ``PYTEST_POSTGRES_ADMIN_URL`` wins when set. Otherwise the shared
    ``database_url`` fixture from ``tests/integration/conftest.py`` is used, which
    needs Docker and errors at setup without it.
    """
    override = os.environ.get("PYTEST_POSTGRES_ADMIN_URL")
    if override:
        return override
    return str(request.getfixturevalue("database_url"))


@contextmanager
def throwaway_database(
    admin_url: str, prefix: str = "tmp"
) -> Generator[str, None, None]:
    """Create an empty, uniquely named PostgreSQL database; drop it afterwards.

    Yields the new database's URL (password included, for the engine to use).
    """
    db_name = f"{prefix}_{uuid.uuid4().hex[:12]}"
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
        try:
            yield (
                make_url(admin_url)
                .set(database=db_name)
                .render_as_string(hide_password=False)
            )
        finally:
            with admin_engine.connect() as conn:
                conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
    finally:
        admin_engine.dispose()


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
