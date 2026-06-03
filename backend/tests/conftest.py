"""Shared pytest fixtures for DB-backed tests.

Provides an FK-enforcing in-memory SQLite engine so foreign-key constraints
behave like production Postgres. Without ``PRAGMA foreign_keys=ON`` SQLite
silently ignores FK violations — which is exactly how the
``workflow_artifacts.workflow_run_id -> workflow_runs.id`` FK bug reached prod
undetected (every artifact test runs the in-memory ``use_db=False`` path, and
the SQLite suites never enforced FKs).

Use the ``fk_session`` fixture for any test that needs the real DB path with
referential integrity enforced. It also redirects
``app.models.database.SessionLocal`` to the test engine, so code that resolves
``SessionLocal`` at call time (e.g. the Artifact_Store) writes through the test
DB rather than dev.db.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — importing the package registers every model on Base.metadata
from app.models.database import Base


def make_fk_sqlite_engine():
    """Build an in-memory SQLite engine with FK enforcement turned ON.

    StaticPool keeps a single underlying connection so the in-memory DB persists
    across the multiple Sessions a test opens (the setup session and the
    Artifact_Store's own ``SessionLocal()``).
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


@pytest.fixture
def fk_session(monkeypatch):
    """Yield a Session bound to an FK-enforcing SQLite engine.

    Also points ``app.models.database.SessionLocal``/``engine`` at this engine so
    the Artifact_Store (which does ``from app.models.database import SessionLocal``
    inside each method) writes through the same DB the test set up.
    """
    import app.models.database as db_module

    engine = make_fk_sqlite_engine()
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(
        autocommit=False, autoflush=False, expire_on_commit=False, bind=engine
    )

    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)

    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()
