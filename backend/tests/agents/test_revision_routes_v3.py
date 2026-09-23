"""tests/agents/test_revision_routes_v3.py — revision routes FR-002/017/038/043.

Covers verification debt (phase V) for sandbox file routes:

  * **FR-002** — a revision's run_files.py list/read/zip/upload return the root's files;
    the success path is untested (only 404 paths are tested).
  * **FR-017** — `GET …/sandbox/file?path=.chain/summary.md` → 200 (`.chain/` is
    readable, not forbidden as a reserved path).
  * **FR-038/043** — `ref=` parameter on list/read/zip and `/sandbox/refs` at route level.

All tests use TestClient to drive the actual HTTP routes (not re-implementation inline).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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
    """Set up TestClient with in-memory DB and temp RUNS_ROOT."""
    from app.api import run_files as rf_module
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

    # Patch _get_db on both modules
    monkeypatch.setattr(ws_module, "_get_db", lambda: TestingSession())
    monkeypatch.setattr(rf_module, "_get_db", lambda: TestingSession())
    monkeypatch.setattr(db_module, "SessionLocal", TestingSession)

    # Land every sandbox write under a writable temp RUNS_ROOT
    runs_root = tmp_path / "runs"
    monkeypatch.setattr(settings, "RUNS_ROOT", str(runs_root))

    from app.api.run_files import router as run_files_router
    from app.core.dependencies import get_current_user

    app = FastAPI()
    app.include_router(run_files_router)
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


def _seed_user(env, tag: str) -> _FakeUser:
    """Create a user in the test DB."""
    from app.models.user import User

    db = env["Session"]()
    try:
        u = User(
            id=str(uuid.uuid4()),
            email=f"test-{tag}-{uuid.uuid4().hex[:8]}@example.com",
            password_hash="x",
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return _FakeUser(id=u.id)
    finally:
        db.close()


def _seed_run(env, *, user_id, owner_id, parent_run_id=None, status="completed") -> str:
    """Seed a WorkflowRun with optional parent_run_id (for revisions)."""
    from app.models.workflow import WorkflowRun

    run_id = str(uuid.uuid4())
    db = env["Session"]()
    try:
        db.add(WorkflowRun(
            id=run_id,
            user_id=user_id,
            owner_id=owner_id,
            parent_run_id=parent_run_id,
            workspace_id="ws-1",
            title="test run",
            type="custom",
            status=status,
            input="{}",
            agent_count=1,
            session_id=user_id,
            created_at=datetime.now(timezone.utc),
        ))
        db.commit()
        return run_id
    finally:
        db.close()


def _owned_run(env, user: _FakeUser, parent_run_id=None, status="completed") -> str:
    """Create a run owned by the user."""
    return _seed_run(env, user_id=user.id, owner_id=user.id, parent_run_id=parent_run_id, status=status)


def _sandbox(env, user_id, run_id):
    """Get a RunSandbox for the given user and run."""
    from app.agents.sandbox import RunSandbox
    return RunSandbox(user_id, run_id, runs_root=env["runs_root"])


# ════════════════════════════════════════════════════════════════════════════
# FR-002 — revision routes return root's files (success path)
# ════════════════════════════════════════════════════════════════════════════


class TestRevisionRoutesReturnRootFiles:
    """FR-002: a revision's run_files routes return the root's files."""

    def test_list_sandbox_addresses_chain_root(self, env):
        """list_sandbox via a revision run_id returns the root's file list."""
        user = _seed_user(env, "u1")
        root_id = _owned_run(env, user)
        revision_id = _owned_run(env, user, parent_run_id=root_id)

        # Write a file to the root sandbox
        root_sb = _sandbox(env, user.id, root_id)
        root_sb.ensure()
        (root_sb.root / "output.txt").write_text("root output", encoding="utf-8")

        env["state"]["user"] = user

        # List via the root run id
        root_resp = env["client"].get(f"/api/runs/{root_id}/sandbox")
        assert root_resp.status_code == 200
        root_data = root_resp.json()
        root_files = root_data["files"]
        root_paths = {f["path"] for f in root_files}
        assert "output.txt" in root_paths

        # List via the revision run id — should get the same files
        revision_resp = env["client"].get(f"/api/runs/{revision_id}/sandbox")
        assert revision_resp.status_code == 200
        revision_data = revision_resp.json()
        revision_files = revision_data["files"]
        revision_paths = {f["path"] for f in revision_files}
        assert "output.txt" in revision_paths
        # They should be the same
        assert root_paths == revision_paths

    def test_read_sandbox_file_addresses_chain_root(self, env):
        """read_sandbox_file via a revision returns the root's file content."""
        user = _seed_user(env, "u1")
        root_id = _owned_run(env, user)
        revision_id = _owned_run(env, user, parent_run_id=root_id)

        # Write a file to the root sandbox
        root_sb = _sandbox(env, user.id, root_id)
        root_sb.ensure()
        (root_sb.root / "data.txt").write_text("root data", encoding="utf-8")

        env["state"]["user"] = user

        # Read via the revision run id — should get the root's file
        resp = env["client"].get(
            f"/api/runs/{revision_id}/sandbox/file",
            params={"path": "data.txt"}
        )
        assert resp.status_code == 200
        assert resp.text == "root data"

    def test_download_sandbox_zip_addresses_chain_root(self, env):
        """download_sandbox_zip via a revision returns the root's files."""
        user = _seed_user(env, "u1")
        root_id = _owned_run(env, user)
        revision_id = _owned_run(env, user, parent_run_id=root_id)

        # Write files to the root sandbox
        root_sb = _sandbox(env, user.id, root_id)
        root_sb.ensure()
        (root_sb.root / "file1.txt").write_text("content1", encoding="utf-8")
        (root_sb.root / "file2.txt").write_text("content2", encoding="utf-8")

        env["state"]["user"] = user

        # Download zip via the revision run id
        resp = env["client"].get(f"/api/runs/{revision_id}/sandbox/zip")
        assert resp.status_code == 200
        # The response should be a zip file (contains PK header)
        assert resp.content.startswith(b"PK")

    def test_upload_files_via_revision_lands_in_root_sandbox(self, env):
        """POST .../{revision_id}/files resolves to the chain root — the
        uploaded file lands under the ROOT sandbox's .uploads/ prefix, not a
        sandbox keyed by the revision's own run id (run_files.py:277 comment:
        uploads resolve "to the revision root so uploads land in the shared"
        family directory).
        """
        user = _seed_user(env, "u1")
        root_id = _owned_run(env, user)
        revision_id = _owned_run(env, user, parent_run_id=root_id)

        env["state"]["user"] = user

        resp = env["client"].post(
            f"/api/runs/{revision_id}/files",
            files=[("files", ("notes.txt", b"revision upload content", "text/plain"))],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == revision_id
        assert data["files"][0]["name"] == "notes.txt"

        # The file physically landed under the ROOT sandbox's .uploads/ prefix.
        root_sb = _sandbox(env, user.id, root_id)
        assert root_sb.path_for(".uploads/notes.txt").read_bytes() == b"revision upload content"

        # A sandbox keyed by the revision's own run id was never written to.
        revision_sb = _sandbox(env, user.id, revision_id)
        assert not revision_sb.path_for(".uploads/notes.txt").exists()


# ════════════════════════════════════════════════════════════════════════════
# FR-017 — .chain/summary.md is readable (not forbidden)
# ════════════════════════════════════════════════════════════════════════════


class TestChainFilesAreReadable:
    """FR-017: .chain/ files (summary.md, logs.jsonl) are readable."""

    def test_read_chain_summary_md(self, env):
        """GET /sandbox/file?path=.chain/summary.md returns 200."""
        user = _seed_user(env, "u1")
        run_id = _owned_run(env, user)

        # Write .chain/summary.md
        sb = _sandbox(env, user.id, run_id)
        sb.ensure()
        chain_dir = sb.root / ".chain"
        chain_dir.mkdir(exist_ok=True)
        (chain_dir / "summary.md").write_text(
            "# Chain Summary\n\nThis is the summary.",
            encoding="utf-8"
        )

        env["state"]["user"] = user

        # Read the file via the route
        resp = env["client"].get(
            f"/api/runs/{run_id}/sandbox/file",
            params={"path": ".chain/summary.md"}
        )
        assert resp.status_code == 200
        assert "Chain Summary" in resp.text

    def test_read_chain_logs_jsonl(self, env):
        """GET /sandbox/file?path=.chain/logs.jsonl returns 200."""
        user = _seed_user(env, "u1")
        run_id = _owned_run(env, user)

        # Write .chain/logs.jsonl
        sb = _sandbox(env, user.id, run_id)
        sb.ensure()
        chain_dir = sb.root / ".chain"
        chain_dir.mkdir(exist_ok=True)
        logs_content = json.dumps({"event": "test"}) + "\n"
        (chain_dir / "logs.jsonl").write_text(logs_content, encoding="utf-8")

        env["state"]["user"] = user

        # Read the file via the route
        resp = env["client"].get(
            f"/api/runs/{run_id}/sandbox/file",
            params={"path": ".chain/logs.jsonl"}
        )
        assert resp.status_code == 200
        assert '"event"' in resp.text


# ════════════════════════════════════════════════════════════════════════════
# FR-038/043 — ref= parameter on routes
# ════════════════════════════════════════════════════════════════════════════


class TestRefParameterOnRoutes:
    """FR-038/043: ref= parameter works on list/read/zip routes."""

    def test_list_sandbox_with_valid_ref_tag(self, env):
        """list_sandbox with ref=v1 parameter filters to that tag's tree."""
        user = _seed_user(env, "u1")
        run_id = _owned_run(env, user, status="completed")

        sb = _sandbox(env, user.id, run_id)
        sb.ensure()
        (sb.root / "file.txt").write_text("content", encoding="utf-8")

        # Initialize git and create a tag so the ref validation passes
        sb.git_init_sandbox()
        sb.commit_all("initial")
        sb.create_tag("v1")

        env["state"]["user"] = user

        # Call with ref parameter
        resp = env["client"].get(
            f"/api/runs/{run_id}/sandbox",
            params={"ref": "v1"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "files" in data
        assert "ref" in data
        assert data["ref"] == "v1"

    def test_read_sandbox_file_with_ref_parameter(self, env):
        """read_sandbox_file with ref= reads from the tagged tree."""
        user = _seed_user(env, "u1")
        run_id = _owned_run(env, user, status="completed")

        sb = _sandbox(env, user.id, run_id)
        sb.ensure()
        (sb.root / "file.txt").write_text("head content", encoding="utf-8")

        # Set up git and create a tag
        sb.git_init_sandbox()
        sb.commit_all("initial")
        sb.create_tag("v1")

        env["state"]["user"] = user

        # Call with ref parameter
        resp = env["client"].get(
            f"/api/runs/{run_id}/sandbox/file",
            params={"path": "file.txt", "ref": "v1"}
        )
        assert resp.status_code == 200
        assert "head content" in resp.text

    def test_download_sandbox_zip_with_ref_parameter(self, env):
        """download_sandbox_zip with ref= archives the tagged tree, not the live one.

        Real ``git archive`` (no mocking) — the sandbox is tagged, then the
        working tree is dirtied *after* the tag, so a zip that reflected the
        live tree instead of the ref would fail this assertion.
        """
        import io
        import zipfile

        user = _seed_user(env, "u1")
        run_id = _owned_run(env, user, status="completed")

        sb = _sandbox(env, user.id, run_id)
        sb.ensure()
        (sb.root / "file.txt").write_text("tagged content", encoding="utf-8")

        # Set up git and tag the current state.
        sb.git_init_sandbox()
        sb.commit_all("initial")
        sb.create_tag("v1")

        # Dirty the working tree after the tag; the ref-scoped zip must not see this.
        (sb.root / "file.txt").write_text("modified after tag", encoding="utf-8")

        env["state"]["user"] = user

        # Call with ref parameter
        resp = env["client"].get(
            f"/api/runs/{run_id}/sandbox/zip",
            params={"ref": "v1"}
        )
        assert resp.status_code == 200
        assert resp.content.startswith(b"PK")

        archive = zipfile.ZipFile(io.BytesIO(resp.content))
        assert archive.read("file.txt").decode("utf-8") == "tagged content"

    def test_list_sandbox_refs_returns_tags(self, env):
        """GET /sandbox/refs returns the list of available tags."""
        user = _seed_user(env, "u1")
        run_id = _owned_run(env, user, status="completed")

        sb = _sandbox(env, user.id, run_id)
        sb.ensure()

        # Set up git and create tags
        sb.git_init_sandbox()
        sb.commit_all("initial")
        sb.create_tag("v1")
        (sb.root / "file2.txt").write_text("more", encoding="utf-8")
        sb.commit_all("second")
        sb.create_tag("v2")

        env["state"]["user"] = user

        # Call the refs endpoint
        resp = env["client"].get(f"/api/runs/{run_id}/sandbox/refs")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        assert "refs" in data
        assert isinstance(data["refs"], list)
        # We created v1 and v2 tags
        assert "v1" in data["refs"]
        assert "v2" in data["refs"]

    def test_ref_validation_rejects_invalid_ref(self, env):
        """Invalid ref= (shell metachar) is rejected before use."""
        user = _seed_user(env, "u1")
        run_id = _owned_run(env, user)

        sb = _sandbox(env, user.id, run_id)
        sb.ensure()

        env["state"]["user"] = user

        # Call with an invalid ref containing shell metacharacters
        resp = env["client"].get(
            f"/api/runs/{run_id}/sandbox/file",
            params={"path": "file.txt", "ref": "v1; rm -rf /"}
        )
        # Should be rejected (400 or 422)
        assert resp.status_code in (400, 422)


# ════════════════════════════════════════════════════════════════════════════
# Integration: revision + tags + ref parameter
# ════════════════════════════════════════════════════════════════════════════


class TestRevisionWithTagsAndRef:
    """Integration: revision accesses tagged versions of the root."""

    def test_revision_can_read_root_at_specific_tag(self, env):
        """A revision can read a specific tag of the root via ref= parameter."""
        user = _seed_user(env, "u1")
        root_id = _owned_run(env, user, status="completed")
        revision_id = _owned_run(env, user, parent_run_id=root_id)

        sb = _sandbox(env, user.id, root_id)
        sb.ensure()
        (sb.root / "file.txt").write_text("tagged content", encoding="utf-8")

        # Set up git and create a tag
        sb.git_init_sandbox()
        sb.commit_all("initial")
        sb.create_tag("v1")

        env["state"]["user"] = user

        # Revision queries the root at tag v1
        resp = env["client"].get(
            f"/api/runs/{revision_id}/sandbox/file",
            params={"path": "file.txt", "ref": "v1"}
        )
        assert resp.status_code == 200
        assert "tagged content" in resp.text
