"""``GET /api/runs/{id}/events`` with ``types`` / ``exclude_types`` against PostgreSQL.

The completed-run page walks the event log with ``exclude_types`` (no stream
deltas) and family members read only chat rows with ``types``. These tests drive
the real router, the real ``ScopedStore`` scope and a real database: paging over
the filtered log, the chat-only allow-list, the cross-owner 404, and the 422 on a
malformed filter. LLM and third-party HTTP are not involved in this endpoint.

Database: real PostgreSQL, never SQLite. The engine comes from one of two sources:

* ``PYTEST_POSTGRES_ADMIN_URL`` — a server-level SQLAlchemy URL. A uniquely named
  throwaway database is created for this module and dropped afterwards.
* otherwise the shared testcontainers-backed ``engine`` fixture from
  ``tests/integration/conftest.py`` (needs Docker, errors loudly without it).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Generator
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401 — registers all models on Base.metadata
from app.api.runs import router
from app.core.dependencies import get_current_user
from app.models.database import Base, get_db
from app.models.run_event import RunEvent
from app.models.user import User
from app.models.workflow import WorkflowRun

OWNER_ID = "owner-evfilter-api"
OTHER_ID = "other-evfilter-api"
DELTA_TYPES = {"agent_chunk", "agent_thinking"}
LIFECYCLE_TYPES = ["agent_start", "agent_complete"]
CHAT_TYPES = {"chat_message", "chat_reply"}


class _FakeUser:
    """Stand-in for ``app.models.user.User``; only ``id`` is read by the API."""

    def __init__(self, id: str):
        self.id = id


@pytest.fixture(scope="module")
def pg_engine(request: pytest.FixtureRequest) -> Generator[Engine, None, None]:
    """Postgres engine with every table created: throwaway DB or shared container."""
    admin_url = os.environ.get("PYTEST_POSTGRES_ADMIN_URL")
    if not admin_url:
        yield request.getfixturevalue("engine")
        return
    db_name = f"evfilterapi_{uuid.uuid4().hex[:12]}"
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
def run_session(pg_engine: Engine) -> Generator[Session, None, None]:
    """Postgres session shared with the app; rows it seeds are deleted afterwards."""
    session = sessionmaker(
        bind=pg_engine, autocommit=False, autoflush=False, expire_on_commit=False
    )()
    session.add_all(
        [
            User(id=owner, email=f"{owner}@example.com", cognito_sub=f"sub-{owner}")
            for owner in (OWNER_ID, OTHER_ID)
        ]
    )
    session.commit()
    try:
        yield session
    finally:
        session.rollback()
        run_ids = [
            r.id
            for r in session.query(WorkflowRun.id).filter(
                WorkflowRun.user_id.in_([OWNER_ID, OTHER_ID])
            )
        ]
        session.query(RunEvent).filter(RunEvent.run_id.in_(run_ids)).delete(
            synchronize_session=False
        )
        session.query(WorkflowRun).filter(WorkflowRun.id.in_(run_ids)).delete(
            synchronize_session=False
        )
        session.query(User).filter(User.id.in_([OWNER_ID, OTHER_ID])).delete(
            synchronize_session=False
        )
        session.commit()
        session.close()


@pytest.fixture
def client(run_session: Session) -> TestClient:
    """TestClient for the runs router; auth is the owner, DB is ``run_session``."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: _FakeUser(id=OWNER_ID)

    def override_db() -> Generator[Session, None, None]:
        yield run_session

    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


@pytest.fixture
def seed_run(run_session: Session) -> Callable[..., str]:
    """Factory that persists one ``WorkflowRun`` plus its ``run_events`` (types in seq order)."""

    def _seed(event_types: list[str], user_id: str = OWNER_ID) -> str:
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        workspace_id = f"ws-{run_id}"
        run_session.add(
            WorkflowRun(
                id=run_id,
                user_id=user_id,
                owner_id=user_id,
                workspace_id=workspace_id,
                title="Filter me",
                type="prototype",
                status="completed",
                input="brief",
                created_at=datetime.now(timezone.utc),
            )
        )
        run_session.flush()
        now = datetime.now(timezone.utc)
        rows = [
            {
                "id": str(uuid.uuid4()),
                "run_id": run_id,
                "owner_id": user_id,
                "workspace_id": workspace_id,
                "seq": seq,
                "event_id": str(uuid.uuid4()),
                "type": event_type,
                "payload_json": {"seq": seq},
                "created_at": now,
            }
            for seq, event_type in enumerate(event_types, start=1)
        ]
        if rows:
            run_session.execute(insert(RunEvent), rows)
        run_session.commit()
        return run_id

    return _seed


def _mixed_log(total: int) -> list[str]:
    """``total`` types: mostly stream deltas, a lifecycle pair and a chat pair every 50 rows."""
    pattern = ["agent_chunk"] * 30 + ["agent_thinking"] * 16
    pattern += LIFECYCLE_TYPES + ["chat_message", "chat_reply"]
    return [pattern[i % len(pattern)] for i in range(total)]


def test_get_run_events_walks_only_non_delta_rows_when_exclude_types_given(
    client: TestClient, seed_run: Callable[..., str]
) -> None:
    log = _mixed_log(7000)
    run_id = seed_run(log)
    expected_seqs = [seq for seq, t in enumerate(log, start=1) if t not in DELTA_TYPES]

    seen: list[dict] = []
    after = 0
    pages = 0
    while True:
        resp = client.get(
            f"/api/runs/{run_id}/events",
            params={
                "after": after,
                "limit": 5000,
                "exclude_types": "agent_chunk,agent_thinking",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        pages += 1
        seen.extend(body["events"])
        assert body["next_after"] == (
            body["events"][-1]["seq"] if body["events"] else after
        )
        if not body["has_more"]:
            break
        after = body["next_after"]
        assert pages < 10

    assert pages == 1  # 560 non-delta rows fit one 5000-row page
    assert [e["seq"] for e in seen] == expected_seqs
    assert {e["type"] for e in seen} == set(LIFECYCLE_TYPES) | CHAT_TYPES


def test_get_run_events_pages_filtered_rows_when_limit_smaller_than_filtered_set(
    client: TestClient, seed_run: Callable[..., str]
) -> None:
    log = _mixed_log(500)
    run_id = seed_run(log)
    expected_seqs = [seq for seq, t in enumerate(log, start=1) if t not in DELTA_TYPES]

    seen: list[int] = []
    after = 0
    has_more = True
    while has_more:
        body = client.get(
            f"/api/runs/{run_id}/events",
            params={
                "after": after,
                "limit": 15,
                "exclude_types": "agent_chunk,agent_thinking",
            },
        ).json()
        seen.extend(e["seq"] for e in body["events"])
        has_more = body["has_more"]
        after = body["next_after"]

    assert seen == expected_seqs


def test_get_run_events_returns_only_chat_rows_when_types_given(
    client: TestClient, seed_run: Callable[..., str]
) -> None:
    log = _mixed_log(200)
    run_id = seed_run(log)

    resp = client.get(
        f"/api/runs/{run_id}/events", params={"types": "chat_message,chat_reply"}
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["has_more"] is False
    assert [e["seq"] for e in body["events"]] == [
        seq for seq, t in enumerate(log, start=1) if t in CHAT_TYPES
    ]
    assert {e["type"] for e in body["events"]} == CHAT_TYPES


def test_get_run_events_returns_404_when_other_owner_filters_by_type(
    client: TestClient, seed_run: Callable[..., str]
) -> None:
    run_id = seed_run(["chat_message", "chat_reply"], user_id=OTHER_ID)

    resp = client.get(
        f"/api/runs/{run_id}/events", params={"types": "chat_message,chat_reply"}
    )

    assert resp.status_code == 404


@pytest.mark.parametrize(
    "params",
    [
        {"types": ""},
        {"types": "Chat_Message"},
        {"exclude_types": "agent_chunk,,agent_thinking"},
        {"types": "chat_message", "exclude_types": "agent_chunk"},
    ],
)
def test_get_run_events_returns_422_when_filter_invalid(
    client: TestClient, seed_run: Callable[..., str], params: dict[str, str]
) -> None:
    run_id = seed_run(["chat_message"])

    resp = client.get(f"/api/runs/{run_id}/events", params=params)

    assert resp.status_code == 422
    assert resp.json() == {"detail": "Invalid event type filter"}
