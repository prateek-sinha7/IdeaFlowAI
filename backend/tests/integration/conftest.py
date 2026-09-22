"""Shared fixtures for the integration suite.

Integration tests exercise real PostgreSQL, ORM mappings, migrations, and
router + DB interactions. LLM and third-party HTTP are faked.

Fixture hierarchy:
- `postgres_container` (session) — testcontainers PostgreSQL lifecycle
- `engine` (session) — SQLAlchemy engine bound to the container
- `db_session` (function) — transactional session, rolled back after each test
- `alembic_upgrade` (session) — migration chain applied once per session
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from testcontainers.postgres import PostgresContainer

import app.models  # noqa: F401 — registers all models on Base.metadata


@pytest.fixture(scope="session")
def postgres_container() -> Generator[PostgresContainer, None, None]:
    """Lifecycle: start a PostgreSQL testcontainer at session scope, stop after.

    This is the REAL database for integration tests. Every integration test in
    this worker will use this container. The container is started once per
    pytest session, not once per test, to avoid the ~2-3 second startup cost
    on each test.

    Yields:
        PostgresContainer — running Postgres instance with known credentials.
    """
    container = PostgresContainer(
        image="postgres:17-alpine",
        user="testuser",
        password="testpass",
        dbname="test_db",
    )
    container.start()
    yield container
    container.stop()


@pytest.fixture(scope="session")
def database_url(postgres_container: PostgresContainer) -> str:
    """JDBC URL for the running PostgreSQL container.

    Returns:
        str — sync SQLAlchemy connection string (psycopg2).
    """
    return postgres_container.get_connection_url()


@pytest.fixture(scope="session")
def engine(database_url: str):
    """SQLAlchemy engine bound to the real Postgres testcontainer.

    Scope: session — the engine is expensive to create; one per session is safe
    because it is stateless (the pool is managed by testcontainers).

    Args:
        database_url: Connection string from the running container.

    Yields:
        Engine — SQLAlchemy engine ready for queries.
    """
    eng = create_engine(
        database_url,
        echo=False,  # set to True for SQL debug output
        pool_pre_ping=True,  # test connections before returning from pool
    )

    # Create all tables once per session
    from app.models.database import Base

    Base.metadata.create_all(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture(scope="session")
def alembic_upgrade(engine) -> None:
    """Run Alembic migrations to bring the schema to head.

    Scope: session — migrations run once, after all tables are created via
    ``Base.metadata.create_all()`` above. This ensures the schema matches the
    migration chain.

    In a real integration suite, you might run this BEFORE create_all to validate
    the migration chain in isolation. Here we do both to ensure the test database
    is fully migrated.

    Args:
        engine: The SQLAlchemy engine to run migrations against.
    """
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config(os.path.join(os.path.dirname(__file__), "../../alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", str(engine.url))

    # Run migrations to head
    command.upgrade(alembic_cfg, "head")


@pytest.fixture
def db_session(engine) -> Generator[Session, None, None]:
    """Transactional session for each integration test, rolled back after.

    Scope: function — a fresh session per test, wrapped in a transaction that
    is rolled back after the test. This isolates tests from each other's database
    state without requiring expensive cleanup queries.

    Pattern: Outer transaction wraps each test, SAVEPOINT is created for nested
    transactions. After the test, the outer transaction is rolled back, leaving
    the database clean for the next test.

    Args:
        engine: The SQLAlchemy engine.

    Yields:
        Session — ready for queries, with transaction isolation.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection, class_=Session)()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def session_for_repo(db_session: Session) -> Session:
    """Alias for db_session, named to match repository constructor signatures.

    Many repository tests accept a ``session`` parameter. This fixture provides
    the transactional session under a more conventional name.

    Args:
        db_session: The transactional session.

    Returns:
        Session — the same transactional session, aliased as ``session``.
    """
    return db_session
