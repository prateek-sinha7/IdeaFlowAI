"""tests/unit/test_runs_api_artifacts.py — API-04 lineage-tree endpoint (Phase 5).

``GET /api/runs/{id}/artifacts`` returns the run's typed ``ArtifactRef`` lineage
TREE (D-10): each node carries the ref fields (producer step/agent/task +
parents/derived_from) plus ``children: []`` assembled by walking
``parents``/``derived_from`` from the roots. Inline ``content`` is EXCLUDED by
default and only present under ``?include=content``. Every read routes through the
single default-deny ``ScopedStore``; a cross-owner request resolves to 404 (IDOR
→ 404, never 403 — Highest-Risk Behavior 2).

Harness: a FastAPI ``TestClient`` with ``get_current_user`` + ``get_db``
overridden against a shared in-memory SQLite session (the same dependency-override
pattern as ``test_runs_api.py`` / ``test_run_events.py``), so no Postgres is
needed. The FastAPI TestClient drives the ``async def`` handlers on its own loop,
so the test bodies are plain sync functions.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.runs import router
from app.core.dependencies import get_current_user
from app.models.artifact_ref import ArtifactRef
from app.models.database import Base, get_db
from app.models.workflow import WorkflowRun


class _FakeUser:
    """Stand-in for ``app.models.user.User`` — only ``id`` is read by the API."""

    def __init__(self, id: str):
        self.id = id


@pytest.fixture
def db_session():
    """In-memory SQLite session with all Phase-5 tables (StaticPool so the
    override and the test body share one connection)."""
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


def _seed_run(db, *, run_id="run-1", owner_id="owner", workspace_id="ws-1"):
    db.add(
        WorkflowRun(
            id=run_id,
            user_id=owner_id,
            title="My Run",
            type="prototype",
            status="completed",
            input="build me a thing",
            owner_id=owner_id,
            workspace_id=workspace_id,
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()


def _seed_ref(db, *, ref_id, run_id, kind, version, content, derived_from=None,
              owner_id="owner", workspace_id="ws-1", producer_step="step",
              producer_agent="agent", task_id=None):
    db.add(
        ArtifactRef(
            id=ref_id,
            run_id=run_id,
            owner_id=owner_id,
            workspace_id=workspace_id,
            kind=kind,
            producer_step=producer_step,
            producer_agent=producer_agent,
            task_id=task_id,
            content=content,
            content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            location=f"inline://{ref_id}",
            version=version,
            parents=[],
            derived_from=derived_from,
            visibility="private",
            retention="run_ttl",
        )
    )
    db.commit()


# ---------------------------------------------------------------------------
# API-04 — walkable lineage tree (root A, child B derived_from A)
# ---------------------------------------------------------------------------


class TestLineageTree:
    def test_artifacts_returns_walkable_tree(self, api, db_session):
        client, _ = api
        _seed_run(db_session)
        _seed_ref(db_session, ref_id="A", run_id="run-1", kind="spec",
                  version=1, content="SPEC", producer_step="specify",
                  producer_agent="prototype-specify", task_id="t1")
        _seed_ref(db_session, ref_id="B", run_id="run-1", kind="design",
                  version=1, content="DESIGN", derived_from="A",
                  producer_step="plan", producer_agent="prototype-plan",
                  task_id="t2")

        resp = client.get("/api/runs/run-1/artifacts")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        tree = body["artifacts"]

        # Exactly one root (A); B is nested under it as a child.
        assert len(tree) == 1
        root = tree[0]
        assert root["id"] == "A"
        # Each node carries producer step/agent/task + lineage edges.
        assert root["producer_step"] == "specify"
        assert root["producer_agent"] == "prototype-specify"
        assert root["task_id"] == "t1"
        assert root["kind"] == "spec"
        assert "version" in root and "content_hash" in root
        assert "visibility" in root and "retention" in root and "location" in root

        assert len(root["children"]) == 1
        child = root["children"][0]
        assert child["id"] == "B"
        assert child["derived_from"] == "A"
        assert child["producer_step"] == "plan"
        assert child["children"] == []

    def test_content_excluded_by_default_present_with_include(self, api, db_session):
        client, _ = api
        _seed_run(db_session)
        _seed_ref(db_session, ref_id="A", run_id="run-1", kind="spec",
                  version=1, content="SECRET SPEC BODY")

        # Default: content absent.
        default = client.get("/api/runs/run-1/artifacts").json()["artifacts"][0]
        assert "content" not in default, "inline content leaked by default (D-10)"

        # ?include=content: content present for the same owner.
        with_content = (
            client.get("/api/runs/run-1/artifacts?include=content")
            .json()["artifacts"][0]
        )
        assert with_content["content"] == "SECRET SPEC BODY"

    def test_empty_run_returns_empty_tree(self, api, db_session):
        client, _ = api
        _seed_run(db_session)
        resp = client.get("/api/runs/run-1/artifacts")
        assert resp.status_code == 200, resp.text
        assert resp.json()["artifacts"] == []


# ---------------------------------------------------------------------------
# T-5-IDOR — cross-owner request resolves to 404 (never 403, no existence leak)
# ---------------------------------------------------------------------------


class TestCrossOwnerDenied:
    def test_artifacts_cross_owner_is_404(self, api, db_session):
        client, state = api
        _seed_run(db_session, owner_id="owner", workspace_id="ws-1")
        _seed_ref(db_session, ref_id="A", run_id="run-1", kind="spec",
                  version=1, content="SPEC")

        state["user"] = _FakeUser(id="attacker")
        resp = client.get("/api/runs/run-1/artifacts")
        assert resp.status_code == 404, "IDOR: attacker read another owner's artifacts"

    def test_missing_run_is_404(self, api, db_session):
        client, _ = api
        resp = client.get("/api/runs/does-not-exist/artifacts")
        assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# Workstream A (D-8) — ?kind= exact-kind filter applied BEFORE tree-building.
# ---------------------------------------------------------------------------


class TestKindFilter:
    def _seed_three_kinds(self, db):
        # A(spec) ← B(design, derived_from=A); C(clarifications) standalone.
        _seed_run(db)
        _seed_ref(db, ref_id="A", run_id="run-1", kind="spec",
                  version=1, content="SPEC")
        _seed_ref(db, ref_id="B", run_id="run-1", kind="design",
                  version=1, content="DESIGN", derived_from="A")
        _seed_ref(db, ref_id="C", run_id="run-1", kind="clarifications",
                  version=1, content="Q&A ROUNDS")

    def test_kind_filters_and_filtered_child_surfaces_as_root(self, api, db_session):
        client, _ = api
        self._seed_three_kinds(db_session)

        tree = client.get("/api/runs/run-1/artifacts?kind=design").json()["artifacts"]
        # A (the parent) is filtered out, so B surfaces as a root with no
        # children — the in-set parent restriction guarantees this (PINS it).
        assert len(tree) == 1
        assert tree[0]["id"] == "B"
        assert tree[0]["kind"] == "design"
        assert tree[0]["children"] == []

    def test_kind_composes_with_include_content(self, api, db_session):
        client, _ = api
        self._seed_three_kinds(db_session)

        node = (
            client.get("/api/runs/run-1/artifacts?kind=clarifications&include=content")
            .json()["artifacts"][0]
        )
        assert node["kind"] == "clarifications"
        assert node["content"] == "Q&A ROUNDS"

    def test_unknown_kind_returns_empty_list_not_422(self, api, db_session):
        client, _ = api
        self._seed_three_kinds(db_session)

        resp = client.get("/api/runs/run-1/artifacts?kind=nonexistent")
        assert resp.status_code == 200, resp.text
        assert resp.json()["artifacts"] == []
