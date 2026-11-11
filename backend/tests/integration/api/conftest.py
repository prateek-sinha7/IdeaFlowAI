"""Fixtures shared by the builder API integration tests.

``builder_pg_engine`` is built on ``throwaway_database`` from
``tests/integration/db/conftest.py``. The server comes from
``PYTEST_POSTGRES_ADMIN_URL`` or the testcontainers server (needs Docker, errors at
setup without it). The fixture is module scoped, so each test module gets its own
database.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from alembic import command
from tests.integration.db.conftest import (
    alembic_config_for,
    postgres_admin_url,
    throwaway_database,
)


@pytest.fixture(scope="module")
def builder_pg_engine(request: pytest.FixtureRequest) -> Generator[Engine, None, None]:
    """Engine on a throwaway PostgreSQL database migrated to Alembic head."""
    with throwaway_database(postgres_admin_url(request), "wbapi") as url:
        command.upgrade(alembic_config_for(url), "head")
        engine = create_engine(url, pool_pre_ping=True)
        try:
            yield engine
        finally:
            engine.dispose()
