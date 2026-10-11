"""tests/unit/test_chain_projection.py — chain-source projection IDOR gate
(Task 11.9, Requirement 21 AC 4, sandbox-git-versioning-v2).

Validates that GET /api/runs/{id} projects `chain_source` correctly:

  1. When the caller owns the source run → `chain_source` is present with
     id, short_id, workflow_id, published_status, visible_tag.
  2. When the source run belongs to a DIFFERENT owner → `chain_source` is
     ABSENT (None) — never partially disclosed (IDOR protection).
  3. When source_run_id is set but the source run does not exist →
     `chain_source` is None.
  4. When source_run_id is absent → `chain_source` is None.
  5. Presence of a RunFinalization row populates chain_context_installed.

Drives a FastAPI TestClient against the runs router with an in-memory SQLite
session (same pattern as test_runs_api.py and test_rest_run_launch.py).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Register every model on Base.metadata before create_all.
import app.models.artifact_ref  # noqa: F401
import app.models.run_capabilities  # noqa: F401
import app.models.run_event  # noqa: F401
import app.models.workflow  # noqa: F401
import app.models.workspace  # noqa: F401
import app.models.run_finalization  # noqa: F401
import app.models.run_provenance_audit  # noqa: F401
import app.models.user  # noqa: F401

from app.api.runs import router
from app.core.dependencies import get_current_user
from app.models.database import Base, get_db
from app.models.workflow import WorkflowRun
from app.models.run_finalization import RunFinalization


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
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def api(db_session):
    """TestClient with auth + db overridden. Returns (client, state)."""
    app = FastAPI()
    app.include_router(router)

    state: dict = {"user": _FakeUser(id="owner")}

    def override_user():
        return state["user"]

    def override_db():
        yield db_session

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db
    return TestClient(app, raise_server_exceptions=True), state


def _make_run(
    db,
    *,
    run_id: str,
    user_id: str,
    source_run_id: str | None = None,
    type: str = "prototype",
    status: str = "completed",
    **kw,
) -> WorkflowRun:
    run = WorkflowRun(
        id=run_id,
        user_id=user_id,
        title=kw.get("title", "Test Run"),
        type=type,
        status=status,
        input="build me something",
        output=kw.get("output", "the output"),
        agent_count=3,
        created_at=datetime.now(timezone.utc),
    )
    if source_run_id is not None:
        run.source_run_id = source_run_id
    if kw.get("git_tag"):
        run.git_tag = kw["git_tag"]
    db.add(run)
    db.commit()
    return run


def _make_finalization(
    db,
    *,
    run_id: str,
    owner_id: str,
    chain_context_installed: bool | None = None,
    payload_chainable: bool | None = None,
) -> RunFinalization:
    fin = RunFinalization(
        owner_id=owner_id,
        workspace_id="ws-1",
        run_id=run_id,
        chain_context_installed=chain_context_installed,
        payload_chainable=payload_chainable,
    )
    db.add(fin)
    db.commit()
    return fin


# ─────────────────────────────────────────────────────────────────────────────
# 1. Same-owner source → chain_source is populated
# ─────────────────────────────────────────────────────────────────────────────


class TestChainSourceSameOwner:
    def test_chain_source_present_for_same_owner(self, api, db_session):
        client, state = api
        state["user"] = _FakeUser(id="owner")
        # Source run owned by same user
        _make_run(
            db_session,
            run_id="src-run-1",
            user_id="owner",
            type="user_stories",
            status="completed",
            git_tag="v1",
        )
        # Receiving run references the source
        _make_run(
            db_session, run_id="recv-run-1", user_id="owner", source_run_id="src-run-1"
        )

        resp = client.get("/api/runs/recv-run-1")
        assert resp.status_code == 200, resp.text
        body = resp.json()

        chain_source = body.get("chain_source")
        assert (
            chain_source is not None
        ), "chain_source should be populated when the caller owns the source run"
        assert chain_source["id"] == "src-run-1"
        assert chain_source["short_id"] == "src-run-"[:8]  # first 8 chars
        assert chain_source["workflow_id"] == "user_stories"
        assert chain_source["published_status"] == "completed"
        assert chain_source["visible_tag"] == "v1"

    def test_chain_source_short_id_is_first_8_chars(self, api, db_session):
        client, state = api
        state["user"] = _FakeUser(id="owner")
        src_id = "abcdef12-3456-7890-abcd-ef1234567890"
        _make_run(
            db_session,
            run_id=src_id,
            user_id="owner",
            type="prototype",
            status="completed",
        )
        _make_run(
            db_session, run_id="recv-run-2", user_id="owner", source_run_id=src_id
        )

        resp = client.get("/api/runs/recv-run-2")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        chain_source = body["chain_source"]
        assert chain_source["short_id"] == src_id[:8]

    def test_chain_source_visible_tag_none_for_untagged(self, api, db_session):
        client, state = api
        state["user"] = _FakeUser(id="owner")
        _make_run(
            db_session,
            run_id="src-untagged",
            user_id="owner",
            type="prototype",
            status="failed",
        )
        _make_run(
            db_session,
            run_id="recv-run-3",
            user_id="owner",
            source_run_id="src-untagged",
        )

        resp = client.get("/api/runs/recv-run-3")
        assert resp.status_code == 200, resp.text
        chain_source = resp.json()["chain_source"]
        assert chain_source["visible_tag"] is None
        assert chain_source["published_status"] == "failed"


# ─────────────────────────────────────────────────────────────────────────────
# 2. Cross-owner source → chain_source is ABSENT (Requirement 21 AC 4 / IDOR)
# ─────────────────────────────────────────────────────────────────────────────


class TestChainSourceCrossOwnerAbsent:
    def test_cross_owner_source_projects_as_absent(self, api, db_session):
        """A source owned by 'other-user' must NOT be disclosed to 'owner'."""
        client, state = api
        state["user"] = _FakeUser(id="owner")
        # Source run owned by a DIFFERENT user
        _make_run(
            db_session,
            run_id="src-other-owner",
            user_id="other-user",
            type="user_stories",
            status="completed",
            git_tag="v2",
        )
        # Receiving run owned by 'owner' references the cross-owner source
        _make_run(
            db_session,
            run_id="recv-cross-owner",
            user_id="owner",
            source_run_id="src-other-owner",
        )

        resp = client.get("/api/runs/recv-cross-owner")
        assert resp.status_code == 200, resp.text
        body = resp.json()

        # chain_source must be absent — never partially disclosed
        assert (
            body.get("chain_source") is None
        ), "IDOR: cross-owner source must project as None, not expose any fields"

    def test_cross_owner_source_does_not_leak_id(self, api, db_session):
        """Confirm no part of the cross-owner source run id leaks."""
        client, state = api
        state["user"] = _FakeUser(id="owner")
        _make_run(
            db_session,
            run_id="super-secret-run",
            user_id="attacker",
            type="prototype",
            status="completed",
        )
        _make_run(
            db_session,
            run_id="my-run",
            user_id="owner",
            source_run_id="super-secret-run",
        )

        resp = client.get("/api/runs/my-run")
        assert resp.status_code == 200, resp.text
        body = resp.json()

        # The attacker's run id must not appear anywhere in the response
        import json

        response_text = json.dumps(body)
        assert (
            "super-secret-run" not in response_text
        ), "IDOR: cross-owner source run id must not appear in response body"

    def test_cross_owner_source_does_not_leak_status(self, api, db_session):
        """chain_source absence is total — workflow_id and status also absent."""
        client, state = api
        state["user"] = _FakeUser(id="owner")
        _make_run(
            db_session,
            run_id="other-src",
            user_id="other",
            type="secret_workflow_type",
            status="degraded",
        )
        _make_run(db_session, run_id="recv", user_id="owner", source_run_id="other-src")

        resp = client.get("/api/runs/recv")
        assert resp.status_code == 200
        chain_source = resp.json().get("chain_source")
        assert chain_source is None


# ─────────────────────────────────────────────────────────────────────────────
# 3. Non-existent source → chain_source is None
# ─────────────────────────────────────────────────────────────────────────────


class TestChainSourceMissing:
    def test_missing_source_run_id_projects_as_none(self, api, db_session):
        client, state = api
        state["user"] = _FakeUser(id="owner")
        # source_run_id references a run that does not exist
        _make_run(
            db_session,
            run_id="recv-orphan",
            user_id="owner",
            source_run_id="does-not-exist",
        )

        resp = client.get("/api/runs/recv-orphan")
        assert resp.status_code == 200
        assert resp.json().get("chain_source") is None


# ─────────────────────────────────────────────────────────────────────────────
# 4. No source_run_id → chain_source is None
# ─────────────────────────────────────────────────────────────────────────────


class TestNoChainSource:
    def test_no_source_run_id_chain_source_is_none(self, api, db_session):
        client, state = api
        state["user"] = _FakeUser(id="owner")
        _make_run(db_session, run_id="plain-run", user_id="owner")

        resp = client.get("/api/runs/plain-run")
        assert resp.status_code == 200
        assert resp.json().get("chain_source") is None


# ─────────────────────────────────────────────────────────────────────────────
# 5. chain_context_installed from RunFinalization row
# ─────────────────────────────────────────────────────────────────────────────


class TestChainContextInstalled:
    def test_chain_context_installed_from_finalization_row(self, api, db_session):
        client, state = api
        state["user"] = _FakeUser(id="owner")
        _make_run(db_session, run_id="run-with-fin", user_id="owner")
        _make_finalization(
            db_session,
            run_id="run-with-fin",
            owner_id="owner",
            chain_context_installed=True,
        )

        resp = client.get("/api/runs/run-with-fin")
        assert resp.status_code == 200
        assert resp.json().get("chain_context_installed") is True

    def test_chain_context_installed_false(self, api, db_session):
        client, state = api
        state["user"] = _FakeUser(id="owner")
        _make_run(db_session, run_id="run-not-installed", user_id="owner")
        _make_finalization(
            db_session,
            run_id="run-not-installed",
            owner_id="owner",
            chain_context_installed=False,
        )

        resp = client.get("/api/runs/run-not-installed")
        assert resp.status_code == 200
        assert resp.json().get("chain_context_installed") is False

    def test_chain_context_installed_none_when_no_finalization_row(
        self, api, db_session
    ):
        client, state = api
        state["user"] = _FakeUser(id="owner")
        _make_run(db_session, run_id="run-no-fin", user_id="owner")

        resp = client.get("/api/runs/run-no-fin")
        assert resp.status_code == 200
        # No finalization row → field is None (unknown state)
        assert resp.json().get("chain_context_installed") is None
