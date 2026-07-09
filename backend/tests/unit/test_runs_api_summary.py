"""tests/unit/test_runs_api_summary.py — the additive read-only run summary.

Pins ``GET /api/runs/{id}/summary`` (SHELL-03):

  * Owner → 200 aggregating ONLY existing ``WorkflowRun`` columns + the owned
    family walk: KPI stats (``duration`` / ``agent_count`` / ``token_usage``),
    failure banner (``status`` / ``error``), per-agent breakdown (``agent_outputs``
    projected to summary-safe fields — the raw ``output`` / secret NEVER echoed),
    and the version/revision timeline (``members`` with 1-based ``revision_index``,
    root parent nulled).
  * Cross-owner run id → 404 (IDOR → 404, never 403, never foreign data).
  * Missing run id → 404.
  * Malformed stored ``agent_outputs`` / ``token_usage`` → 200 with ``[]`` / ``{}``
    fallback (DoS guard — never a 500).

Harness: the ``test_runs_api_family.py`` idiom verbatim — a FastAPI ``TestClient``
with ``get_current_user`` + ``get_db`` overridden against a shared in-memory
SQLite session (StaticPool); mutate ``state["user"]`` to switch the principal for
the cross-owner IDOR assertion. Targeted file only (full pytest hangs offline).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.runs import router
from app.core.dependencies import get_current_user
from app.models.database import Base, get_db
from app.models.workflow import WorkflowRun


class _FakeUser:
    """Stand-in for ``app.models.user.User`` — only ``id`` is read by the API."""

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
    """TestClient for the runs router; mutate ``state["user"]`` to switch the
    authenticated principal (for the cross-owner IDOR assertion)."""
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


_BASE_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _seed_run(
    db,
    *,
    run_id,
    owner_id="owner",
    parent_run_id=None,
    created_offset=0,
    type="prototype",
    status="completed",
    title="My Run",
    agent_outputs=None,
    token_usage=None,
    duration=None,
    agent_count=0,
    error=None,
):
    """Seed a WorkflowRun with the summary-relevant columns. ``agent_outputs`` /
    ``token_usage`` accept a list/dict (JSON-encoded here) OR a raw str (to seed a
    MALFORMED blob for the fallback test)."""

    def _enc(v):
        if v is None or isinstance(v, str):
            return v
        return json.dumps(v)

    db.add(
        WorkflowRun(
            id=run_id,
            user_id=owner_id,
            title=title,
            type=type,
            status=status,
            input="build me a thing",
            owner_id=owner_id,
            workspace_id="ws-1",
            parent_run_id=parent_run_id,
            created_at=_BASE_TS + timedelta(seconds=created_offset),
            agent_outputs=_enc(agent_outputs),
            token_usage=_enc(token_usage),
            duration=duration,
            agent_count=agent_count,
            error=error,
        )
    )
    db.commit()


# ---------------------------------------------------------------------------
# 200-for-owner — KPI + per-agent + failure fields off the seeded columns
# ---------------------------------------------------------------------------


class TestSummaryOwnerAggregation:
    def test_owner_gets_200_aggregating_existing_columns(self, api, db_session):
        client, _ = api
        _seed_run(
            db_session,
            run_id="R1",
            status="degraded",
            duration=42.5,
            agent_count=2,
            error="one agent failed",
            agent_outputs=[
                {
                    "agent_id": "domain-analyst",
                    "name": "Domain Analyst",
                    "role": "Analyst",
                    "icon": "🧠",
                    "duration": 12.0,
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "total_tokens": 150,
                    "cache_read_tokens": 10,
                    "cache_write_tokens": 5,
                    # Raw content fields that MUST NOT be echoed (secret risk, V7).
                    "output": "SUPER SECRET API KEY sk-abc123",
                    "input_prompt": "PRIVATE PROMPT BODY",
                    "thinking_text": "internal chain of thought",
                    "tool_calls": [{"tool": "read_file", "args": {"path": "/etc/passwd"}}],
                },
                {
                    "agent_id": "prototype-build",
                    "name": "Prototype Build",
                    "role": "Builder",
                    "icon": "🛠️",
                    "duration": 30.5,
                    "input_tokens": 200,
                    "output_tokens": 80,
                    "total_tokens": 280,
                    "error": "build agent failed",
                    "output": "another secret blob",
                },
            ],
            token_usage={
                "total_input_tokens": 300,
                "total_output_tokens": 130,
                "total_tokens": 430,
                "estimated_cost_usd": 0.0021,
            },
        )

        resp = client.get("/api/runs/R1/summary")
        assert resp.status_code == 200, resp.text
        body = resp.json()

        # KPI stats + failure banner map 1:1 to the seeded columns.
        assert body["id"] == "R1"
        assert body["type"] == "prototype"
        assert body["status"] == "degraded"
        assert body["duration"] == 42.5
        assert body["agent_count"] == 2
        assert body["error"] == "one agent failed"
        assert body["token_usage"]["total_tokens"] == 430
        assert body["token_usage"]["estimated_cost_usd"] == 0.0021

        # Per-agent breakdown reflects the seeded rows, safe fields only.
        agents = body["agents"]
        assert [a["agent_id"] for a in agents] == ["domain-analyst", "prototype-build"]
        assert agents[0]["total_tokens"] == 150
        assert agents[0]["duration"] == 12.0
        assert agents[1]["error"] == "build agent failed"

    def test_raw_agent_content_is_never_echoed(self, api, db_session):
        """The summary projects identity + KPI fields only; raw output /
        input_prompt / thinking_text / tool_calls (secret-bearing) never leak."""
        client, _ = api
        _seed_run(
            db_session,
            run_id="R2",
            agent_count=1,
            agent_outputs=[
                {
                    "agent_id": "domain-analyst",
                    "output": "SUPER SECRET API KEY sk-abc123",
                    "input_prompt": "PRIVATE PROMPT BODY",
                    "thinking_text": "internal chain of thought",
                    "tool_calls": [{"tool": "read_file", "args": {"path": "/etc/passwd"}}],
                }
            ],
        )

        resp = client.get("/api/runs/R2/summary")
        assert resp.status_code == 200, resp.text
        blob = resp.text
        assert "SUPER SECRET API KEY" not in blob
        assert "PRIVATE PROMPT BODY" not in blob
        assert "internal chain of thought" not in blob
        assert "/etc/passwd" not in blob
        # But the safe identity field is present.
        assert resp.json()["agents"][0]["agent_id"] == "domain-analyst"


# ---------------------------------------------------------------------------
# owner gate — cross-owner + missing → 404 (IDOR → 404, never 403)
# ---------------------------------------------------------------------------


class TestSummaryIDOR:
    def test_cross_owner_summary_is_404_never_403(self, api, db_session):
        client, state = api
        _seed_run(db_session, run_id="R1", owner_id="owner")

        state["user"] = _FakeUser(id="attacker")
        resp = client.get("/api/runs/R1/summary")
        assert resp.status_code == 404, "IDOR: attacker read another owner's summary"
        assert resp.status_code != 403

    def test_missing_run_summary_is_404(self, api, db_session):
        client, _ = api
        assert client.get("/api/runs/nope/summary").status_code == 404


# ---------------------------------------------------------------------------
# DoS guard — malformed stored JSON degrades to []/{} (never a 500)
# ---------------------------------------------------------------------------


class TestSummaryMalformedJsonFallback:
    def test_malformed_blobs_return_200_with_empty_fallback(self, api, db_session):
        client, _ = api
        # Raw, un-parseable strings in both JSON columns.
        _seed_run(
            db_session,
            run_id="R1",
            agent_outputs="{not valid json at all",
            token_usage="also </not> json",
        )

        resp = client.get("/api/runs/R1/summary")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["agents"] == []
        assert body["token_usage"] == {}

    def test_agent_outputs_non_list_json_falls_back_to_empty(self, api, db_session):
        client, _ = api
        # Well-formed JSON but the WRONG shape (dict, not the expected array).
        _seed_run(
            db_session,
            run_id="R1",
            agent_outputs={"unexpected": "object"},
            token_usage=[1, 2, 3],
        )

        resp = client.get("/api/runs/R1/summary")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["agents"] == []
        assert body["token_usage"] == {}


# ---------------------------------------------------------------------------
# version/revision timeline — the owned family walk (reused)
# ---------------------------------------------------------------------------


class TestSummaryFamilyTimeline:
    def test_revision_family_members_carry_index_and_nulled_root_parent(
        self, api, db_session
    ):
        client, _ = api
        _seed_run(db_session, run_id="A", created_offset=0)
        _seed_run(db_session, run_id="B", parent_run_id="A", created_offset=10)

        # Ask from EITHER member — both resolve to the same family view.
        for member in ("A", "B"):
            resp = client.get(f"/api/runs/{member}/summary")
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["root_id"] == "A"
            members = body["members"]
            assert [m["id"] for m in members] == ["A", "B"]
            assert [m["revision_index"] for m in members] == [1, 2]
            # Root's out-of-family parent nulled; child keeps its in-family link.
            assert members[0]["parent_run_id"] is None
            assert members[1]["parent_run_id"] == "A"

    def test_foreign_parent_terminates_walk_no_leak(self, api, db_session):
        client, _ = api
        _seed_run(
            db_session,
            run_id="F",
            owner_id="stranger",
            title="STRANGERS SECRET RUN",
            created_offset=0,
        )
        _seed_run(
            db_session,
            run_id="C",
            owner_id="owner",
            parent_run_id="F",
            created_offset=10,
        )

        resp = client.get("/api/runs/C/summary")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["root_id"] == "C"
        assert [m["id"] for m in body["members"]] == ["C"]
        assert body["members"][0]["parent_run_id"] is None
        # No foreign run metadata leaks anywhere.
        assert "STRANGERS SECRET RUN" not in resp.text
        assert "stranger" not in resp.text
