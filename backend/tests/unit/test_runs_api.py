"""Plan 04-05 Task 1 — the relocated run-history CRUD at /api/runs (D-02).

These tests pin the pure relocation of the WorkflowRun read/delete/export
surface from ``/api/workflows`` to ``/api/runs``. They are the verify gate for
the security carry-overs the threat model (04-05) marks ``mitigate``:

* **T-04-12 (IDOR / ASVS V4):** every relocated query keeps the per-user
  ``.filter(WorkflowRun.user_id == current_user.id)`` ownership filter, so a
  cross-owner ``GET``/``DELETE``/chain-context resolves to 404 — never another
  user's run. Asserted by ``test_get_cross_user_is_404`` et al.
* **T-04-14 (HTTP response splitting):** the export-pptx filename is sanitized
  with the verbatim ``re.sub(r"[^A-Za-z0-9._-]", "_", title)[:40]`` — a title
  carrying CR/LF/quote chars cannot smuggle a header. Asserted by
  ``test_export_pptx_filename_is_sanitized``.

The tests drive a FastAPI ``TestClient`` with ``get_current_user`` + ``get_db``
overridden against an in-memory SQLite session (the same dependency-override
pattern as ``test_agents_api_real_registry.py``), so no Postgres is needed.
"""

from __future__ import annotations

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
from app.models.workflow import WorkflowRun


class _FakeUser:
    """Stand-in for ``app.models.user.User`` — only ``id`` is read by the API."""

    def __init__(self, id: str):
        self.id = id


@pytest.fixture
def db_session():
    """An in-memory SQLite session with the WorkflowRun table created.

    A single shared in-memory connection (StaticPool) so the override and the
    test body see the same rows.
    """
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
    """TestClient for the runs router with auth + db overridden.

    Returns ``(client, state)`` — mutate ``state["user"]`` to switch the
    authenticated principal (for the cross-user IDOR assertions).
    """
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


def _make_run(db, *, run_id="run-1", user_id="owner", type="prototype",
              status="completed", **kw):
    run = WorkflowRun(
        id=run_id,
        user_id=user_id,
        title=kw.get("title", "My Run"),
        type=type,
        status=status,
        input=kw.get("input", "build me a thing"),
        output=kw.get("output", "the output"),
        agent_outputs=kw.get("agent_outputs"),
        agent_count=kw.get("agent_count", 3),
        created_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()
    return run


# ---------------------------------------------------------------------------
# Relocation: routes serve the old shapes under /api/runs
# ---------------------------------------------------------------------------


class TestRelocatedShapes:
    def test_list_returns_owner_runs(self, api, db_session):
        client, _ = api
        _make_run(db_session, run_id="r1")
        _make_run(db_session, run_id="r2", type="ppt")
        resp = client.get("/api/runs")
        assert resp.status_code == 200, resp.text
        ids = {r["id"] for r in resp.json()}
        assert ids == {"r1", "r2"}

    def test_list_type_filter_preserved(self, api, db_session):
        client, _ = api
        _make_run(db_session, run_id="r1", type="prototype")
        _make_run(db_session, run_id="r2", type="ppt")
        resp = client.get("/api/runs?type=ppt&limit=20")
        assert resp.status_code == 200, resp.text
        assert [r["id"] for r in resp.json()] == ["r2"]

    def test_get_returns_full_run(self, api, db_session):
        client, _ = api
        _make_run(db_session, run_id="r1", title="Deck")
        resp = client.get("/api/runs/r1")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == "r1"
        assert body["title"] == "Deck"

    def test_delete_returns_204_and_removes(self, api, db_session):
        client, _ = api
        _make_run(db_session, run_id="r1")
        resp = client.delete("/api/runs/r1")
        assert resp.status_code == 204, resp.text
        assert client.get("/api/runs/r1").status_code == 404

    def test_chain_context_returns_block(self, api, db_session):
        client, _ = api
        _make_run(
            db_session, run_id="r1", type="user_stories", status="completed",
            output="THE BACKLOG TEXT",
        )
        resp = client.get("/api/runs/r1/chain-context")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["workflow_id"] == "r1"
        assert body["pipeline_type"] == "user_stories"
        assert "THE BACKLOG TEXT" in body["structured_summary"]


# ---------------------------------------------------------------------------
# T-04-12 — IDOR: ownership filter preserved on every read/delete path
# ---------------------------------------------------------------------------


class TestOwnershipFilterPreserved:
    def test_get_cross_user_is_404(self, api, db_session):
        client, state = api
        _make_run(db_session, run_id="r1", user_id="owner")
        state["user"] = _FakeUser(id="attacker")
        resp = client.get("/api/runs/r1")
        assert resp.status_code == 404, "IDOR: attacker read another user's run"

    def test_delete_cross_user_is_404(self, api, db_session):
        client, state = api
        _make_run(db_session, run_id="r1", user_id="owner")
        state["user"] = _FakeUser(id="attacker")
        resp = client.delete("/api/runs/r1")
        assert resp.status_code == 404, "IDOR: attacker deleted another user's run"
        # And the row still exists for the owner.
        state["user"] = _FakeUser(id="owner")
        assert client.get("/api/runs/r1").status_code == 200

    def test_chain_context_cross_user_is_404(self, api, db_session):
        client, state = api
        _make_run(db_session, run_id="r1", user_id="owner", status="completed")
        state["user"] = _FakeUser(id="attacker")
        resp = client.get("/api/runs/r1/chain-context")
        assert resp.status_code == 404, "IDOR: attacker read another user's context"

    def test_list_only_returns_own_runs(self, api, db_session):
        client, state = api
        _make_run(db_session, run_id="mine", user_id="owner")
        _make_run(db_session, run_id="theirs", user_id="someone-else")
        resp = client.get("/api/runs")
        assert resp.status_code == 200, resp.text
        assert [r["id"] for r in resp.json()] == ["mine"]


# ---------------------------------------------------------------------------
# T-04-14 — export-pptx filename sanitization carried over verbatim
# ---------------------------------------------------------------------------


class TestExportPptxSanitization:
    def test_export_pptx_filename_is_sanitized(self, api, monkeypatch):
        client, _ = api

        # Stub the heavy pptx generation so the test stays unit-level.
        import app.services.pptx_export as pptx_export
        monkeypatch.setattr(
            pptx_export, "generate_pptx_from_code",
            lambda code, title="Presentation": b"PPTXBYTES",
        )

        malicious = 'evil"\r\nSet-Cookie: x=1'
        resp = client.post(
            "/api/runs/export-pptx",
            json={"js_code": "function generatePresentation(){}", "title": malicious},
        )
        assert resp.status_code == 200, resp.text
        cd = resp.headers["content-disposition"]
        # No CR/LF/quote/colon smuggled into the header — the response-splitting
        # vector (CRLF + the `:` that would start a new header) is stripped; only
        # [A-Za-z0-9._-] survives. The literal word "Set-Cookie" may remain as
        # inert filename text (its `:` and CRLF are gone), so we assert on the
        # injection-bearing characters, not the word.
        assert "\r" not in cd and "\n" not in cd
        assert ":" not in cd.split('filename="', 1)[1]  # no header-injecting colon in the name
        assert '\\"' not in cd and 'evil"' not in cd     # the quote was neutralized
        # The sanitized filename keeps only allow-listed chars.
        assert 'filename="' in cd
        name = cd.split('filename="', 1)[1].rstrip('"')
        assert name.replace(".pptx", "").replace(".", "").replace("_", "").replace("-", "").isalnum() or name == "Presentation.pptx"

    def test_export_pptx_requires_code(self, api):
        client, _ = api
        resp = client.post("/api/runs/export-pptx", json={"title": "Empty"})
        assert resp.status_code == 400, resp.text
