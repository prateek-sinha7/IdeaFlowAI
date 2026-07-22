"""tests/unit/test_runs_api_family.py — Workstream A revision-family read surface.

Pins POR §4.2 + §4.3:

  * ``WorkflowRunResponse`` carries ``parent_run_id`` (verbatim column) and the
    server-computed ``root_run_id`` on BOTH list and get (standalone → own id;
    chained child → the family root).
  * ``GET /api/runs/{id}/family`` returns ``{root_id, members[]}`` — members
    ordered ``created_at`` ASC with a 1-based ``revision_index`` and per-member
    ``parent_run_id``; owner-scoped throughout (cross-owner/missing → 404, never
    403); a foreign parent in the chain terminates the walk with zero foreign
    metadata leaked.

Harness: the ``test_runs_api_artifacts.py`` idiom verbatim — a FastAPI
``TestClient`` with ``get_current_user`` + ``get_db`` overridden against a shared
in-memory SQLite session (StaticPool). ``from app.api.runs import router`` imports
every child-table model, so ``Base.metadata.create_all`` covers the real DELETE
endpoint's cleanup — the orphan test can call it for real.
"""

from __future__ import annotations

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
):
    """Seed a WorkflowRun with a controllable parent link + strictly increasing
    created_at (``created_offset`` seconds past a fixed base) so chronological
    ordering is deterministic."""
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
        )
    )
    db.commit()


# ---------------------------------------------------------------------------
# /family — chain order + revision-of-revision depth
# ---------------------------------------------------------------------------


class TestFamilyChainOrder:
    def test_three_deep_chain_from_any_member(self, api, db_session):
        client, _ = api
        _seed_run(db_session, run_id="A", created_offset=0)
        _seed_run(db_session, run_id="B", parent_run_id="A", created_offset=10)
        _seed_run(db_session, run_id="C", parent_run_id="B", created_offset=20)

        # Ask from EVERY member — all resolve to the same family view.
        for member in ("A", "B", "C"):
            resp = client.get(f"/api/runs/{member}/family")
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["root_id"] == "A"
            members = body["members"]
            assert [m["id"] for m in members] == ["A", "B", "C"]
            assert [m["revision_index"] for m in members] == [1, 2, 3]
            # Per-member parent links (root's parent nulled; depth covered).
            assert members[0]["parent_run_id"] is None
            assert members[1]["parent_run_id"] == "A"
            assert members[2]["parent_run_id"] == "B"


class TestFamilyBranching:
    def test_two_children_of_one_root(self, api, db_session):
        client, _ = api
        _seed_run(db_session, run_id="A", created_offset=0)
        _seed_run(db_session, run_id="B", parent_run_id="A", created_offset=5)
        _seed_run(db_session, run_id="C", parent_run_id="A", created_offset=15)

        body = client.get("/api/runs/A/family").json()
        assert body["root_id"] == "A"
        members = body["members"]
        # Chronological order, 1-based index — v-number is chronological (D2).
        assert [m["id"] for m in members] == ["A", "B", "C"]
        assert [m["revision_index"] for m in members] == [1, 2, 3]
        # Both branches carry parent_run_id = A.
        assert members[1]["parent_run_id"] == "A"
        assert members[2]["parent_run_id"] == "A"


class TestFamilyOrphanAfterDelete:
    def test_child_becomes_own_root_after_parent_deleted(self, api, db_session):
        client, _ = api
        _seed_run(db_session, run_id="A", created_offset=0)
        _seed_run(db_session, run_id="B", parent_run_id="A", created_offset=10)

        # The REAL delete endpoint nulls children's parent_run_id (runs.py:334).
        assert client.delete("/api/runs/A").status_code == 204

        body = client.get("/api/runs/B/family").json()
        assert body["root_id"] == "B"
        assert len(body["members"]) == 1
        assert body["members"][0]["id"] == "B"
        assert body["members"][0]["revision_index"] == 1
        assert body["members"][0]["parent_run_id"] is None


class TestFamilyIDOR:
    def test_cross_owner_family_is_404_never_403(self, api, db_session):
        client, state = api
        _seed_run(db_session, run_id="A", owner_id="owner", created_offset=0)

        state["user"] = _FakeUser(id="attacker")
        resp = client.get("/api/runs/A/family")
        assert resp.status_code == 404, "IDOR: attacker read another owner's family"

    def test_missing_run_family_is_404(self, api, db_session):
        client, _ = api
        assert client.get("/api/runs/nope/family").status_code == 404


class TestFamilyForeignParentTerminates:
    def test_foreign_parent_in_chain_terminates_walk_no_leak(self, api, db_session):
        client, _ = api
        # F is owned by someone else; C (ours) points its parent at F.
        _seed_run(db_session, run_id="F", owner_id="stranger",
                  title="STRANGERS SECRET DECK", created_offset=0)
        _seed_run(db_session, run_id="C", owner_id="owner",
                  parent_run_id="F", created_offset=10)

        resp = client.get("/api/runs/C/family")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # The walk terminates at the foreign link → C is its own root.
        assert body["root_id"] == "C"
        assert [m["id"] for m in body["members"]] == ["C"]
        # The root member's dangling foreign pointer is nulled.
        assert body["members"][0]["parent_run_id"] is None
        # NO foreign metadata (id or title) leaks anywhere in the response.
        blob = resp.text
        assert "F" not in [m["id"] for m in body["members"]]
        assert "STRANGERS SECRET DECK" not in blob
        assert "stranger" not in blob

        # get_run on C computes root_run_id = C (foreign parent terminated).
        got = client.get("/api/runs/C").json()
        assert got["root_run_id"] == "C"


# ---------------------------------------------------------------------------
# list + get — parent_run_id (verbatim) + root_run_id (computed) on BOTH
# ---------------------------------------------------------------------------


class TestListGetFamilyFields:
    def test_standalone_run_roots_to_own_id_on_list_and_get(self, api, db_session):
        client, _ = api
        _seed_run(db_session, run_id="solo", created_offset=0)

        got = client.get("/api/runs/solo").json()
        assert got["parent_run_id"] is None
        assert got["root_run_id"] == "solo"

        listed = client.get("/api/runs").json()
        row = next(r for r in listed if r["id"] == "solo")
        assert row["parent_run_id"] is None
        assert row["root_run_id"] == "solo"

    def test_chained_child_roots_to_chain_root_on_list_and_get(self, api, db_session):
        client, _ = api
        _seed_run(db_session, run_id="A", created_offset=0)
        _seed_run(db_session, run_id="B", parent_run_id="A", created_offset=10)
        _seed_run(db_session, run_id="C", parent_run_id="B", created_offset=20)

        got = client.get("/api/runs/C").json()
        assert got["parent_run_id"] == "B"
        assert got["root_run_id"] == "A"

        listed = client.get("/api/runs").json()
        by_id = {r["id"]: r for r in listed}
        assert by_id["B"]["root_run_id"] == "A"
        assert by_id["C"]["root_run_id"] == "A"
        assert by_id["A"]["root_run_id"] == "A"
