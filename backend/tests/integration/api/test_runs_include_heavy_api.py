"""ISS-1213 — ``GET /api/runs/{id}?include_heavy=false`` (history-reopen path).

The frontend reopens a run from history with ``include_heavy=false``.  The
handler then blanks ``input`` and ``agent_outputs`` in the response.  Before
the fix ``WorkflowRunResponse.input`` was a required ``str``, so pydantic
rejected the blanked value and the endpoint returned 500 (the steps page
stayed empty).  A second hazard: the handler blanked the *attached ORM row*,
and ``workflow_runs.input`` is NOT NULL, so any later flush on the shared
session would have raised ``IntegrityError``.

Database: real PostgreSQL, never SQLite (``workflow_runs.user_id`` is an FK to
``users.id``, which SQLite does not enforce by default).  The engine comes from
one of two sources:

* ``PYTEST_POSTGRES_ADMIN_URL`` — a server-level SQLAlchemy URL (any database
  on the server).  A uniquely named throwaway database is created for this
  module and dropped afterwards; the named database itself is never written.
* otherwise the shared testcontainers-backed ``engine`` fixture from
  ``tests/integration/conftest.py`` (needs Docker, errors loudly without it).

LLM and third-party HTTP are not involved in this endpoint.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Generator
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401 — registers all models on Base.metadata
from app.api.runs import router
from app.core.dependencies import get_current_user
from app.models.database import Base, get_db
from app.models.user import User
from app.models.workflow import WorkflowRun

OWNER_ID = "owner-iss1213"
OTHER_ID = "other-iss1213"
BIG_INPUT = "BIG BRIEF " * 50
AGENT_OUTPUTS = '[{"agent_id": "a1", "output": "thinking"}]'


class _FakeUser:
    """Stand-in for ``app.models.user.User`` — only ``id`` is read by the API."""

    def __init__(self, id: str):
        self.id = id


@pytest.fixture(scope="module")
def pg_engine(request: pytest.FixtureRequest) -> Generator[Engine, None, None]:
    """Postgres engine with every table created: throwaway DB or shared container."""
    admin_url = os.environ.get("PYTEST_POSTGRES_ADMIN_URL")
    if not admin_url:
        yield request.getfixturevalue("engine")
        return

    db_name = f"iss1213_{uuid.uuid4().hex[:12]}"
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
        session.query(WorkflowRun).filter(
            WorkflowRun.user_id.in_([OWNER_ID, OTHER_ID])
        ).delete(synchronize_session=False)
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
def seed_run(run_session: Session) -> Callable[..., WorkflowRun]:
    """Factory that persists one ``WorkflowRun`` with heavy columns populated."""

    def _seed(run_id: str = "run-iss1213", user_id: str = OWNER_ID) -> WorkflowRun:
        run = WorkflowRun(
            id=run_id,
            user_id=user_id,
            owner_id=user_id,
            workspace_id=f"ws-{run_id}",
            title="Reopen me",
            type="prototype",
            status="completed",
            input=BIG_INPUT,
            output="the deliverable",
            agent_outputs=AGENT_OUTPUTS,
            agent_count=3,
            created_at=datetime.now(timezone.utc),
        )
        run_session.add(run)
        run_session.commit()
        return run

    return _seed


def test_get_run_returns_200_with_null_heavy_fields_when_include_heavy_false(
    client: TestClient, seed_run: Callable[..., WorkflowRun]
) -> None:
    seed_run()

    resp = client.get("/api/runs/run-iss1213?include_heavy=false")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["input"] is None
    assert body["agent_outputs"] is None
    assert body["output"] == "the deliverable"
    assert body["id"] == "run-iss1213"


def test_get_run_returns_full_heavy_fields_when_include_heavy_omitted(
    client: TestClient, seed_run: Callable[..., WorkflowRun]
) -> None:
    seed_run()

    resp = client.get("/api/runs/run-iss1213")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["input"] == BIG_INPUT
    assert body["agent_outputs"] == AGENT_OUTPUTS


def test_get_run_returns_full_heavy_fields_when_include_heavy_true(
    client: TestClient, seed_run: Callable[..., WorkflowRun]
) -> None:
    seed_run()

    resp = client.get("/api/runs/run-iss1213?include_heavy=true")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["input"] == BIG_INPUT
    assert body["agent_outputs"] == AGENT_OUTPUTS


def test_get_run_leaves_row_unmodified_when_include_heavy_false(
    client: TestClient,
    run_session: Session,
    seed_run: Callable[..., WorkflowRun],
) -> None:
    run = seed_run()

    resp = client.get("/api/runs/run-iss1213?include_heavy=false")

    assert resp.status_code == 200, resp.text
    # The attached instance must not be blanked or marked dirty: ``input`` is
    # NOT NULL, so a flush of a blanked row would raise IntegrityError.
    assert run not in run_session.dirty
    assert run.input == BIG_INPUT
    assert run.agent_outputs == AGENT_OUTPUTS
    run_session.expire_all()
    persisted = run_session.get(WorkflowRun, "run-iss1213")
    assert persisted is not None
    assert persisted.input == BIG_INPUT
    assert persisted.agent_outputs == AGENT_OUTPUTS


def test_get_run_returns_full_input_when_plain_get_follows_include_heavy_false(
    client: TestClient, seed_run: Callable[..., WorkflowRun]
) -> None:
    seed_run()

    first = client.get("/api/runs/run-iss1213?include_heavy=false")
    second = client.get("/api/runs/run-iss1213")

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["input"] == BIG_INPUT
    assert second.json()["agent_outputs"] == AGENT_OUTPUTS


def test_get_run_returns_404_when_include_heavy_false_and_run_not_owned(
    client: TestClient, seed_run: Callable[..., WorkflowRun]
) -> None:
    seed_run(run_id="run-foreign", user_id=OTHER_ID)

    resp = client.get("/api/runs/run-foreign?include_heavy=false")

    assert resp.status_code == 404
