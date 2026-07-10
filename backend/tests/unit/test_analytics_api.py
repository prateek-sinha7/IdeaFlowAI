"""tests/unit/test_analytics_api.py — SC-1 / SHELL-05 (38-01).

Wave-0 tests for the additive, read-only, owner-scoped analytics summary
endpoint ``GET /api/analytics/summary?range=<today|3d|7d|30d|90d|all>``.

The endpoint aggregates the caller's OWN ``WorkflowRun`` rows server-side
(daily series + per-type / per-model rollups + spend) so the browser stops
downloading up to 500 raw run rows to reduce in JS. It is additive over the
EXISTING columns — no new table, no migration — so the 5 characterization
goldens stay byte-identical by construction (INV-3).

Threat pins:
  * T-38-01 (information disclosure): the base query is owner-scoped on
    ``WorkflowRun.user_id == current_user.id`` (the runs.py:250 idiom, NEVER the
    nullable ``owner_id``); ``test_owner_isolation`` proves B's runs never enter
    A's aggregate, and an unauthenticated call is a 401.
  * T-38-02 (DoS): a malformed ``token_usage`` blob degrades to an empty
    per-run token aggregate via ``json.loads`` in try/except → ``{}``; a bad
    blob is a 200, never a 500 (``test_malformed``).
  * T-38-03 (tampering / enum allow-list): ``range`` is an allow-listed enum;
    an unknown value falls back to the default window, never a crash
    (``test_range``).

Offline — in-memory SQLite (StaticPool) with ``get_db`` overridden on a fresh
FastAPI app mounting ONLY the analytics router; ``get_current_user`` overridden
via a state dict (mirrors ``test_rest_run_launch.py``).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Register the table the aggregation reads on Base.metadata BEFORE create_all.
import app.models.workflow  # noqa: F401
from app.models.database import Base, get_db
from app.models.workflow import WorkflowRun


class _FakeUser:
    def __init__(self, id: str):
        self.id = id
        self.preferred_model = None


def _token_usage(cost: float, inp: int, out: int, cache_read: int = 0, cache_write: int = 0) -> str:
    """The exact blob run_commands.py:1277-1291 persists (the ONLY writer)."""
    return json.dumps(
        {
            "total_input_tokens": inp,
            "total_output_tokens": out,
            "total_tokens": inp + out,
            "total_cache_read_tokens": cache_read,
            "total_cache_write_tokens": cache_write,
            "estimated_cost_usd": cost,
        }
    )


@pytest.fixture
def env(monkeypatch):
    from app.api.analytics import router  # RED: module does not exist yet.
    from app.core.dependencies import get_current_user

    db_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    Base.metadata.create_all(bind=db_engine)

    app = FastAPI()
    app.include_router(router)

    def _override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    state: dict = {"user": None}
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    client = TestClient(app)

    yield {
        "client": client,
        "state": state,
        "Session": TestingSession,
        "app": app,
        "get_current_user": get_current_user,
        "get_db_override": _override_get_db,
    }

    Base.metadata.drop_all(bind=db_engine)
    db_engine.dispose()


def _seed_user(env) -> _FakeUser:
    from app.models.user import User

    db = env["Session"]()
    try:
        u = User(
            id=str(uuid.uuid4()),
            email=f"analytics-{uuid.uuid4().hex[:8]}@example.com",
            password_hash="x",
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return _FakeUser(id=u.id)
    finally:
        db.close()


def _seed_run(
    env,
    user_id: str,
    *,
    type: str = "prototype",
    status: str = "completed",
    model_id: str = "claude-haiku",
    duration: float = 10.0,
    token_usage: str | None = None,
    created_at: datetime | None = None,
) -> str:
    run_id = str(uuid.uuid4())
    db = env["Session"]()
    try:
        db.add(
            WorkflowRun(
                id=run_id,
                user_id=user_id,
                title="t",
                type=type,
                status=status,
                input="i",
                agent_count=1,
                duration=duration,
                token_usage=token_usage,
                model_id=model_id,
                created_at=created_at or datetime.now(timezone.utc),
                session_id=user_id,
            )
        )
        db.commit()
        return run_id
    finally:
        db.close()


def _get(env, **params):
    return env["client"].get("/api/analytics/summary", params=params)


# ────────────────────────────────────────────────────────────────────────────
# owner_isolation — T-38-01: A's aggregate contains ONLY A's runs; a cross-owner
# row never leaks; an unauthenticated call is a 401.
# ────────────────────────────────────────────────────────────────────────────


def test_owner_isolation(env):
    a = _seed_user(env)
    b = _seed_user(env)

    # A: 3 runs, distinct token/cost.
    for _ in range(3):
        _seed_run(env, a.id, token_usage=_token_usage(0.10, 100, 50))
    # B: 2 runs with LARGE token/cost that must never enter A's aggregate.
    for _ in range(2):
        _seed_run(env, b.id, token_usage=_token_usage(99.0, 9999, 9999))

    env["state"]["user"] = a
    resp = _get(env, range="all")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["kpis"]["total"] == 3
    # Spend + tokens sum ONLY A's three runs (B's 99.0/9999 never leak).
    assert body["spend"] == pytest.approx(0.30)
    assert body["token_totals"]["input"] == 300
    assert body["token_totals"]["output"] == 150

    # Unauthenticated call → 401 (inherited Depends(get_current_user)). Mount a
    # fresh app WITHOUT the auth override so the real dependency runs and denies.
    unauth = FastAPI()
    from app.api.analytics import router as analytics_router

    unauth.include_router(analytics_router)
    unauth.dependency_overrides[get_db] = env["get_db_override"]
    unauth_client = TestClient(unauth)
    r401 = unauth_client.get("/api/analytics/summary")
    assert r401.status_code == 401


# ────────────────────────────────────────────────────────────────────────────
# recompute — SC-1: ?range=7d totals == the hand-computed in-window sum only.
# ────────────────────────────────────────────────────────────────────────────


def test_recompute(env):
    a = _seed_user(env)
    now = datetime.now(timezone.utc)

    # Two runs INSIDE the 7d window.
    _seed_run(env, a.id, token_usage=_token_usage(1.00, 200, 100), created_at=now)
    _seed_run(
        env, a.id, token_usage=_token_usage(2.00, 300, 150), created_at=now - timedelta(days=3)
    )
    # One run OUTSIDE the 7d window (must be excluded).
    _seed_run(
        env, a.id, token_usage=_token_usage(50.0, 9000, 9000), created_at=now - timedelta(days=20)
    )

    env["state"]["user"] = a
    resp = _get(env, range="7d")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Only the two in-window runs contribute.
    assert body["kpis"]["total"] == 2
    assert body["spend"] == pytest.approx(3.00)
    assert body["token_totals"]["input"] == 500
    assert body["token_totals"]["output"] == 250


# ────────────────────────────────────────────────────────────────────────────
# malformed — T-38-02: a non-JSON token_usage blob degrades to an empty token
# aggregate (200, never 500); spend is unaffected by the bad blob.
# ────────────────────────────────────────────────────────────────────────────


def test_malformed(env):
    a = _seed_user(env)

    # One good run + one whose token_usage is a non-JSON string.
    _seed_run(env, a.id, token_usage=_token_usage(0.50, 400, 200))
    _seed_run(env, a.id, token_usage="{bad")

    env["state"]["user"] = a
    resp = _get(env, range="all")
    assert resp.status_code == 200, resp.text  # never a 500
    body = resp.json()

    # Both runs are counted...
    assert body["kpis"]["total"] == 2
    # ...but the malformed blob contributes an EMPTY token aggregate: totals ==
    # only the good run, spend unaffected by the bad blob.
    assert body["spend"] == pytest.approx(0.50)
    assert body["token_totals"]["input"] == 400
    assert body["token_totals"]["output"] == 200


# ────────────────────────────────────────────────────────────────────────────
# range — T-38-03: allow-listed enum. all → every run; today → only today's;
# an unknown value falls back to the default window (no 4xx/5xx crash).
# ────────────────────────────────────────────────────────────────────────────


def test_range(env):
    a = _seed_user(env)
    now = datetime.now(timezone.utc)

    _seed_run(env, a.id, created_at=now, token_usage=_token_usage(0.1, 10, 5))
    _seed_run(env, a.id, created_at=now - timedelta(days=2), token_usage=_token_usage(0.1, 10, 5))
    _seed_run(env, a.id, created_at=now - timedelta(days=45), token_usage=_token_usage(0.1, 10, 5))

    env["state"]["user"] = a

    # all → every A run.
    r_all = _get(env, range="all")
    assert r_all.status_code == 200
    assert r_all.json()["kpis"]["total"] == 3

    # today → only the run created today.
    r_today = _get(env, range="today")
    assert r_today.status_code == 200
    assert r_today.json()["kpis"]["total"] == 1

    # unknown → falls back to the default window (30d): the 45-day-old run is
    # excluded, the two recent ones remain — no crash, no 4xx/5xx.
    r_bad = _get(env, range="zzz")
    assert r_bad.status_code == 200
    assert r_bad.json()["kpis"]["total"] == 2
