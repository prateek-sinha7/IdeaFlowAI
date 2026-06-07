"""tests/unit/test_runs_api_events.py — API-05 durable-replay endpoint (Phase 5).

``GET /api/runs/{id}/events?after=<seq>`` returns ONLY ``run_events`` rows with
``seq > after``, ascending by ``seq``, each carrying a unique ``event_id``
(idempotent replay — D-11). ``after`` is int-coerced by FastAPI (non-int → 422;
ASVS V5 — never reaches raw SQL). Every read routes through the single
default-deny ``ScopedStore``; a cross-owner request resolves to 404 (IDOR → 404,
never 403 — Highest-Risk Behavior 2).

Harness mirrors ``test_runs_api.py`` (TestClient + dependency overrides over a
shared in-memory SQLite session); the TestClient drives the ``async def`` handler
on its own loop so the test bodies are plain sync.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.runs import router
from app.core.dependencies import get_current_user
from app.models.database import Base, get_db
from app.models.run_event import RunEvent
from app.models.workflow import WorkflowRun


class _FakeUser:
    def __init__(self, id: str):
        self.id = id


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def api(db_session):
    app = FastAPI()
    app.include_router(router)
    state: dict = {"user": _FakeUser(id="owner")}

    def override_user():
        return state["user"]

    def override_db():
        yield db_session

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db
    return TestClient(app), state


def _seed_run(db, *, run_id="run-1", owner_id="owner", workspace_id="ws-1"):
    db.add(
        WorkflowRun(
            id=run_id,
            user_id=owner_id,
            title="My Run",
            type="prototype",
            status="running",
            input="idea",
            owner_id=owner_id,
            workspace_id=workspace_id,
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()


def _seed_events(db, *, run_id="run-1", n=5, owner_id="owner", workspace_id="ws-1"):
    """Seed contiguous seq 1..n run_events, each with a unique event_id."""
    event_ids = []
    for seq in range(1, n + 1):
        eid = str(uuid.uuid4())
        event_ids.append(eid)
        db.add(
            RunEvent(
                id=str(uuid.uuid4()),
                run_id=run_id,
                owner_id=owner_id,
                workspace_id=workspace_id,
                seq=seq,
                event_id=eid,
                type=f"event_type_{seq}",
                payload_json={"seq": seq},
            )
        )
    db.commit()
    return event_ids


# ---------------------------------------------------------------------------
# API-05 — only seq > after, ascending, each with a unique event_id
# ---------------------------------------------------------------------------


class TestAfterSeqReplay:
    def test_events_after_returns_only_greater_ascending(self, api, db_session):
        client, _ = api
        _seed_run(db_session)
        _seed_events(db_session, n=5)

        body = client.get("/api/runs/run-1/events?after=2").json()
        seqs = [e["seq"] for e in body["events"]]
        assert seqs == [3, 4, 5], "only seq > 2, ascending"
        # Each row carries a unique event_id.
        eids = [e["event_id"] for e in body["events"]]
        assert len(set(eids)) == 3 and all(eids)
        # type + payload surfaced.
        assert body["events"][0]["type"] == "event_type_3"
        assert body["events"][0]["payload_json"] == {"seq": 3}

    def test_after_zero_is_full_replay(self, api, db_session):
        client, _ = api
        _seed_run(db_session)
        _seed_events(db_session, n=5)
        body = client.get("/api/runs/run-1/events?after=0").json()
        assert [e["seq"] for e in body["events"]] == [1, 2, 3, 4, 5]

    def test_after_default_is_zero(self, api, db_session):
        client, _ = api
        _seed_run(db_session)
        _seed_events(db_session, n=3)
        body = client.get("/api/runs/run-1/events").json()  # no ?after
        assert [e["seq"] for e in body["events"]] == [1, 2, 3]

    def test_after_past_last_is_empty(self, api, db_session):
        client, _ = api
        _seed_run(db_session)
        _seed_events(db_session, n=5)
        body = client.get("/api/runs/run-1/events?after=5").json()
        assert body["events"] == []  # idempotent re-replay returns nothing new

    def test_after_non_int_is_rejected(self, api, db_session):
        """ASVS V5 — a non-int ``after`` is rejected by FastAPI int coercion
        (422), never interpolated into SQL."""
        client, _ = api
        _seed_run(db_session)
        _seed_events(db_session, n=3)
        resp = client.get("/api/runs/run-1/events?after=1;DROP TABLE run_events")
        assert resp.status_code == 422, "non-int after must be rejected (int-coerce)"


# ---------------------------------------------------------------------------
# T-5-IDOR — cross-owner request resolves to 404 (never 403)
# ---------------------------------------------------------------------------


class TestCrossOwnerDenied:
    def test_events_cross_owner_is_404(self, api, db_session):
        client, state = api
        _seed_run(db_session, owner_id="owner", workspace_id="ws-1")
        _seed_events(db_session, n=3)

        state["user"] = _FakeUser(id="attacker")
        resp = client.get("/api/runs/run-1/events?after=0")
        assert resp.status_code == 404, "IDOR: attacker read another owner's events"

    def test_missing_run_is_404(self, api, db_session):
        client, _ = api
        resp = client.get("/api/runs/nope/events")
        assert resp.status_code == 404, resp.text
