"""Tests for HTML/HTM file upload support (T01 of specs/021-backlog/tasks.md).

Tests verify:
  a. POST a .html and .htm to the run upload endpoint → 200; file lands in .uploads/; manifest.json has_text: false
  b. POST a .html to /api/files/extract-text → 200 with text == ""
  c. A .exe to the run upload endpoint → 415 (unchanged behaviour)
  d. .uploads/x.html is not a deliverable path
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


class _FakeUser:
    def __init__(self, id: str):
        self.id = id


@pytest.fixture
def env(monkeypatch, tmp_path):
    """Set up FastAPI test client with mocked database and RUNS_ROOT."""
    from app.api import run_files as rf_module
    from app.api import file_extract as fe_module
    from app.api import run_engine as ws_module
    from app.core.config import settings
    from app.models import database as db_module
    from app.models.database import Base

    db_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    Base.metadata.create_all(bind=db_engine)

    monkeypatch.setattr(ws_module, "_get_db", lambda: TestingSession())
    monkeypatch.setattr(rf_module, "_get_db", lambda: TestingSession())
    monkeypatch.setattr(db_module, "SessionLocal", TestingSession)

    runs_root = tmp_path / "runs"
    monkeypatch.setattr(settings, "RUNS_ROOT", str(runs_root))

    from app.api.run_files import router as run_files_router
    from app.api.file_extract import router as file_extract_router
    from app.core.dependencies import get_current_user

    app = FastAPI()
    app.include_router(run_files_router)
    app.include_router(file_extract_router)
    state: dict = {"user": None}
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    client = TestClient(app)

    yield {
        "client": client,
        "state": state,
        "Session": TestingSession,
        "runs_root": str(runs_root),
    }

    Base.metadata.drop_all(bind=db_engine)
    db_engine.dispose()


def _seed_user(env) -> _FakeUser:
    """Create a test user in the database."""
    from app.models.user import User

    db = env["Session"]()
    try:
        u = User(
            id=str(uuid.uuid4()),
            email=f"u-{uuid.uuid4().hex[:8]}@example.com",
            cognito_sub=f"sub-{uuid.uuid4().hex[:8]}",
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return _FakeUser(id=u.id)
    finally:
        db.close()


def _seed_run(env, *, user_id, run_id=None) -> str:
    """Create a test workflow run in the database."""
    from app.models.workflow import WorkflowRun

    run_id = run_id or str(uuid.uuid4())
    db = env["Session"]()
    try:
        db.add(
            WorkflowRun(
                id=run_id,
                user_id=user_id,
                owner_id=user_id,
                workspace_id="ws-1",
                title="t",
                type="prototype",
                status="in_progress",
                input="i",
                agent_count=1,
                session_id=user_id,
                created_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        return run_id
    finally:
        db.close()


@pytest.mark.allow_io(
    "tests require in-memory SQLite database and file I/O for upload endpoint"
)
class TestHtmlHtmUploadToRun:
    """Test POST a .html and .htm to the run upload endpoint."""

    def test_html_upload_succeeds_with_has_text_false(self, env):
        """POST a .html file to the run upload endpoint → 200, has_text: false."""
        user = _seed_user(env)
        env["state"]["user"] = user
        run_id = _seed_run(env, user_id=user.id)

        html_content = b"<html><body>Test HTML</body></html>"

        resp = env["client"].post(
            f"/api/runs/{run_id}/files",
            files={"files": ("test.html", html_content, "text/html")},
        )

        assert (
            resp.status_code == 200
        ), f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["run_id"] == run_id
        assert len(data["files"]) == 1
        assert data["files"][0]["name"] == "test.html"
        assert data["files"][0]["bytes"] == len(html_content)
        assert data["files"][0]["extracted_chars"] == 0
        assert data["files"][0]["truncated"] is False

        # Verify file exists on disk
        sandbox_dir = Path(env["runs_root"]) / user.id / run_id / ".uploads"
        assert (sandbox_dir / "test.html").exists()

        # Verify manifest has has_text: false
        manifest_path = sandbox_dir / "manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert len(manifest) == 1
        assert manifest[0]["name"] == "test.html"
        assert manifest[0]["has_text"] is False

    def test_htm_upload_succeeds_with_has_text_false(self, env):
        """POST a .htm file to the run upload endpoint → 200, has_text: false."""
        user = _seed_user(env)
        env["state"]["user"] = user
        run_id = _seed_run(env, user_id=user.id)

        htm_content = b"<html><head><title>Test</title></head></html>"

        resp = env["client"].post(
            f"/api/runs/{run_id}/files",
            files={"files": ("test.htm", htm_content, "text/html")},
        )

        assert (
            resp.status_code == 200
        ), f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["run_id"] == run_id
        assert len(data["files"]) == 1
        assert data["files"][0]["name"] == "test.htm"

        # Verify file exists on disk
        sandbox_dir = Path(env["runs_root"]) / user.id / run_id / ".uploads"
        assert (sandbox_dir / "test.htm").exists()

        # Verify manifest has has_text: false
        manifest_path = sandbox_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        assert manifest[0]["name"] == "test.htm"
        assert manifest[0]["has_text"] is False

    def test_html_and_htm_together(self, env):
        """POST both .html and .htm files in one request."""
        user = _seed_user(env)
        env["state"]["user"] = user
        run_id = _seed_run(env, user_id=user.id)

        html_content = b"<html>HTML</html>"
        htm_content = b"<html>HTM</html>"

        resp = env["client"].post(
            f"/api/runs/{run_id}/files",
            files=[
                ("files", ("test.html", html_content, "text/html")),
                ("files", ("test.htm", htm_content, "text/html")),
            ],
        )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["files"]) == 2
        names = {f["name"] for f in data["files"]}
        assert names == {"test.html", "test.htm"}

        # Verify both files exist
        sandbox_dir = Path(env["runs_root"]) / user.id / run_id / ".uploads"
        assert (sandbox_dir / "test.html").exists()
        assert (sandbox_dir / "test.htm").exists()

        # Verify manifest entries
        manifest_path = sandbox_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        assert len(manifest) == 2
        for entry in manifest:
            assert entry["has_text"] is False


@pytest.mark.allow_io(
    "tests require in-memory SQLite database for extract-text endpoint"
)
class TestHtmlExtractTextEndpoint:
    """Test POST a .html to /api/files/extract-text → 200 with text == ''."""

    def test_html_extract_text_returns_empty_string(self, env):
        """POST .html to extract-text endpoint → 200 with text == ''."""
        user = _seed_user(env)
        env["state"]["user"] = user

        html_content = b"<html><body><h1>Title</h1><p>Content</p></body></html>"

        resp = env["client"].post(
            "/api/files/extract-text",
            files={"file": ("test.html", html_content, "text/html")},
        )

        assert (
            resp.status_code == 200
        ), f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["filename"] == "test.html"
        assert data["text"] == ""
        assert data["truncated"] is False

    def test_htm_extract_text_returns_empty_string(self, env):
        """POST .htm to extract-text endpoint → 200 with text == ''."""
        user = _seed_user(env)
        env["state"]["user"] = user

        htm_content = b"<html></html>"

        resp = env["client"].post(
            "/api/files/extract-text",
            files={"file": ("test.htm", htm_content, "text/html")},
        )

        assert (
            resp.status_code == 200
        ), f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["filename"] == "test.htm"
        assert data["text"] == ""
        assert data["truncated"] is False


@pytest.mark.allow_io(
    "tests require in-memory SQLite database for unsupported type validation"
)
class TestUnsupportedFileTypeReturns415:
    """Test that .exe and other unsupported types return 415."""

    def test_exe_to_run_upload_returns_415(self, env):
        """POST a .exe to the run upload endpoint → 415."""
        user = _seed_user(env)
        env["state"]["user"] = user
        run_id = _seed_run(env, user_id=user.id)

        exe_content = b"MZ\x90\x00"  # PE header stub

        resp = env["client"].post(
            f"/api/runs/{run_id}/files",
            files={"files": ("test.exe", exe_content, "application/octet-stream")},
        )

        assert (
            resp.status_code == 415
        ), f"Expected 415, got {resp.status_code}: {resp.text}"
        assert "Unsupported file type" in resp.json()["detail"]

    def test_exe_to_extract_text_returns_415(self, env):
        """POST a .exe to extract-text endpoint → 415."""
        user = _seed_user(env)
        env["state"]["user"] = user

        exe_content = b"MZ\x90\x00"  # PE header stub

        resp = env["client"].post(
            "/api/files/extract-text",
            files={"file": ("test.exe", exe_content, "application/octet-stream")},
        )

        assert (
            resp.status_code == 415
        ), f"Expected 415, got {resp.status_code}: {resp.text}"
        assert "Unsupported file type" in resp.json()["detail"]


class TestUploadedHtmlIsNotDeliverable:
    """Test that .uploads/x.html is not a deliverable path."""

    def test_uploads_html_is_not_deliverable(self):
        """Verify that .uploads/x.html is excluded from deliverable paths."""
        from app.agents.sandbox import is_deliverable_relpath

        # .uploads/ is a reserved prefix, so any path starting with it is not deliverable
        assert not is_deliverable_relpath(".uploads/test.html")
        assert not is_deliverable_relpath(".uploads/index.html")
        assert not is_deliverable_relpath(".uploads/")

        # Regular html files outside .uploads/ would be deliverable (if they're not
        # excluded by other rules like PLANNER.md)
        assert is_deliverable_relpath("output.html")
        assert is_deliverable_relpath("src/index.html")
