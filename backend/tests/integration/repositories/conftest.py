"""Fixtures for the scoped-store / repository persistence tests.

These tests need a REAL engine and REAL ORM mapping — that is the whole point of
them — but not a server: they assert scoped writes, column round-tripping and
default-deny reads, none of which is dialect-specific. So the fixture here is a
hermetic in-memory SQLite engine, which is also the pattern the two pre-existing
files in this folder already build inline (``test_parent_run_ownership_db.py``,
``test_repositories_persistence_db.py`` — worth folding onto this fixture next time
either is touched).

Note this deliberately SHADOWS ``db_session`` from ``tests/integration/conftest.py``
(a Postgres testcontainer) for this folder only. Dialect-specific behaviour belongs in
``tests/integration/db/`` behind the ``requires_postgres`` marker.
"""

from __future__ import annotations

from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Importing app.models registers every model on Base.metadata, so create_all builds
# the full schema for the test database.
import app.models  # noqa: F401
from app.models.database import Base


@pytest.fixture
def db_session() -> Iterator[Session]:
    """A hermetic in-memory SQLite session with the full model schema created.

    ``StaticPool`` + ``check_same_thread=False`` keep every connection pointed at the
    SAME in-memory database, so a write on the test thread is visible to anything the
    store does on another one.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
