"""``ScopedStore.read_events_page`` type filter against real PostgreSQL.

Covers the ``types`` allow-list and ``exclude_types`` deny-list pushed into SQL,
the owner+workspace default-deny scope, the ``LIMIT`` applied to the filtered
rows, and the sync ``read_events_page_in_session`` twin returning the same rows
as the async method.

Database: real PostgreSQL, never SQLite. The engine comes from one of two sources:

* ``PYTEST_POSTGRES_ADMIN_URL`` — a server-level SQLAlchemy URL. A uniquely named
  throwaway database is created for this module and dropped afterwards.
* otherwise the shared testcontainers-backed ``engine`` fixture from
  ``tests/integration/conftest.py`` (needs Docker, errors loudly without it).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401 — registers all models on Base.metadata
from agents.authz import ScopedStore
from app.models.database import Base
from app.models.run_event import RunEvent
from app.models.user import User
from app.models.workflow import WorkflowRun

OWNER_ID = "owner-evfilter-db"
OTHER_ID = "other-evfilter-db"
RUN_ID = "run-evfilter-db"
WORKSPACE_ID = "ws-evfilter-db"

# seq 1..10, in order.
EVENT_TYPES = [
    "pipeline_start",
    "agent_start",
    "agent_chunk",
    "agent_thinking",
    "agent_chunk",
    "chat_message",
    "agent_complete",
    "chat_reply",
    "agent_chunk",
    "pipeline_complete",
]


@pytest.fixture(scope="module")
def pg_engine(request: pytest.FixtureRequest) -> Generator[Engine, None, None]:
    """Postgres engine with every table created: throwaway DB or shared container."""
    admin_url = os.environ.get("PYTEST_POSTGRES_ADMIN_URL")
    if not admin_url:
        yield request.getfixturevalue("engine")
        return
    db_name = f"evfilter_{uuid.uuid4().hex[:12]}"
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    engine = create_engine(make_url(admin_url).set(database=db_name))
    try:
        Base.metadata.create_all(bind=engine)
        yield engine
    finally:
        engine.dispose()
        with admin_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
        admin_engine.dispose()


@pytest.fixture
def session(pg_engine: Engine) -> Generator[Session, None, None]:
    """Session with one owned run and ``EVENT_TYPES`` seeded; rows deleted afterwards."""
    db = sessionmaker(
        bind=pg_engine, autocommit=False, autoflush=False, expire_on_commit=False
    )()
    db.add_all(
        [
            User(id=owner, email=f"{owner}@example.com", cognito_sub=f"sub-{owner}")
            for owner in (OWNER_ID, OTHER_ID)
        ]
    )
    db.flush()
    db.add(
        WorkflowRun(
            id=RUN_ID,
            user_id=OWNER_ID,
            owner_id=OWNER_ID,
            workspace_id=WORKSPACE_ID,
            title="Filter me",
            type="prototype",
            status="completed",
            input="brief",
            created_at=datetime.now(timezone.utc),
        )
    )
    db.flush()
    db.add_all(
        [
            RunEvent(
                id=str(uuid.uuid4()),
                run_id=RUN_ID,
                owner_id=OWNER_ID,
                workspace_id=WORKSPACE_ID,
                seq=seq,
                event_id=str(uuid.uuid4()),
                type=event_type,
                payload_json={"seq": seq},
            )
            for seq, event_type in enumerate(EVENT_TYPES, start=1)
        ]
    )
    db.commit()
    try:
        yield db
    finally:
        db.rollback()
        db.query(RunEvent).filter(RunEvent.run_id == RUN_ID).delete(
            synchronize_session=False
        )
        db.query(WorkflowRun).filter(WorkflowRun.id == RUN_ID).delete(
            synchronize_session=False
        )
        db.query(User).filter(User.id.in_([OWNER_ID, OTHER_ID])).delete(
            synchronize_session=False
        )
        db.commit()
        db.close()


def _owner_store(session: Session) -> ScopedStore:
    return ScopedStore(owner_id=OWNER_ID, workspace_id=WORKSPACE_ID, session=session)


async def test_read_events_page_returns_only_allowed_types_when_types_given(
    session: Session,
) -> None:
    rows = await _owner_store(session).read_events_page(
        RUN_ID, 0, limit=100, types={"chat_reply", "chat_message"}
    )

    assert [(r.seq, r.type) for r in rows] == [(6, "chat_message"), (8, "chat_reply")]


async def test_read_events_page_drops_excluded_types_when_exclude_types_given(
    session: Session,
) -> None:
    rows = await _owner_store(session).read_events_page(
        RUN_ID, 0, limit=100, exclude_types=("agent_chunk", "agent_thinking")
    )

    assert [r.seq for r in rows] == [1, 2, 6, 7, 8, 10]
    assert {r.type for r in rows}.isdisjoint({"agent_chunk", "agent_thinking"})


async def test_read_events_page_returns_empty_when_owner_differs(
    session: Session,
) -> None:
    store = ScopedStore(owner_id=OTHER_ID, workspace_id=WORKSPACE_ID, session=session)

    rows = await store.read_events_page(
        RUN_ID, 0, limit=100, types=("chat_message", "chat_reply")
    )

    assert rows == []


async def test_read_events_page_bounds_filtered_rows_when_limit_given(
    session: Session,
) -> None:
    store = _owner_store(session)
    excluded = ("agent_chunk", "agent_thinking")

    first = await store.read_events_page(RUN_ID, 0, limit=2, exclude_types=excluded)
    second = await store.read_events_page(
        RUN_ID, first[-1].seq, limit=2, exclude_types=excluded
    )

    assert [r.seq for r in first] == [1, 2]
    assert [r.seq for r in second] == [6, 7]


async def test_read_events_page_in_session_matches_async_rows_when_same_args(
    session: Session,
) -> None:
    store = _owner_store(session)

    async_rows = await store.read_events_page(
        RUN_ID, 1, limit=4, exclude_types=("agent_chunk",)
    )
    sync_rows = store.read_events_page_in_session(
        RUN_ID, 1, limit=4, exclude_types=("agent_chunk",)
    )

    assert [r.event_id for r in sync_rows] == [r.event_id for r in async_rows]
    assert [r.seq for r in sync_rows] == [2, 4, 6, 7]
