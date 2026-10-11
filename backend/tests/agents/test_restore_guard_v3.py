"""tests/agents/test_restore_guard_v3.py — restore guard family-scoped (FR-057).

The restore endpoint refuses to proceed when any member of the **revision family**
is non-terminal. Previously, the guard was user-wide (any active run of the same
user blocked restore on any family). This test verifies the fix: the guard now uses
the family-scoped BFS from run_commands._has_active_chain_revision, so an unrelated
active run does NOT block a restore on a different, fully-terminal family.

Coverage:
  * An active run in a different family (unrelated parent_run_id chain) does NOT
    block restore on a terminal family — asserted both at the guard-function level
    and end-to-end through ``POST /api/runs/{run_id}/restore`` (real TestClient,
    real git sandbox): the request completes, it is never a 409.
  * An active run within the same family (same revision root via parent_run_id chain)
    DOES block restore — asserted both at the guard-function level and as an actual
    HTTP 409 from the mounted route (``code == "family_run_active"``).
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Register every table the restore path touches on Base.metadata BEFORE create_all.
import app.models.artifact_ref  # noqa: F401
import app.models.run_capabilities  # noqa: F401
import app.models.run_event  # noqa: F401
import app.models.run_provenance_audit  # noqa: F401
import app.models.workflow  # noqa: F401
import app.models.workspace  # noqa: F401
from app.api.runs import router as runs_router
from app.models.database import Base, get_db
from app.models.user import User
from app.models.workflow import WorkflowRun


class _FakeUser:
    def __init__(self, id: str):
        self.id = id
        self.preferred_model = None
        self.tier = "enterprise"


@pytest.fixture
def env(monkeypatch, tmp_path):
    """Set up TestClient with in-memory DB and user dependency override.

    Mounts ``app.api.runs.router`` — the router that actually defines
    ``POST /{run_id}/restore`` — and overrides the ``get_db`` dependency it
    declares (``Depends(get_db)``), matching the pattern in
    ``tests/unit/test_runs_api.py``. ``run_commands.router`` defines a
    *different* router object under the same ``/api/runs`` prefix and does not
    carry the restore route at all, so mounting it alone (the prior version of
    this fixture) made ``_post_restore`` 404 silently if it had ever been
    called — ``_has_active_family_member``'s own DB session comes from this
    same override, never from ``run_commands._get_db``.
    """
    from app.core.config import settings

    # Mock RUNS_ROOT to use a temporary directory
    runs_root_path = tmp_path / "runs"
    runs_root_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "RUNS_ROOT", str(runs_root_path))

    db_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    Base.metadata.create_all(bind=db_engine)

    def _override_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    from app.core.dependencies import get_current_user

    app = FastAPI()
    app.include_router(runs_router)
    state: dict = {"user": None}
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app)

    yield {
        "client": client,
        "state": state,
        "Session": TestingSession,
        "tmp_path": tmp_path,
    }

    Base.metadata.drop_all(bind=db_engine)
    db_engine.dispose()


def _seed_user(env, tag="u") -> _FakeUser:
    """Create a test user in the database."""
    db = env["Session"]()
    try:
        u = User(
            id=str(uuid.uuid4()),
            email=f"restore-guard-{tag}-{uuid.uuid4().hex[:8]}@example.com",
            cognito_sub=str(uuid.uuid4()),
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return _FakeUser(id=u.id)
    finally:
        db.close()


def _seed_run(
    env,
    run_id: str,
    owner_id: str,
    status: str,
    parent_run_id: str | None = None,
) -> str:
    """Create a WorkflowRun in the database and its sandbox directory with git repo."""
    import os
    import subprocess

    from app.core.config import settings

    db = env["Session"]()
    try:
        db.add(
            WorkflowRun(
                id=run_id,
                user_id=owner_id,
                owner_id=owner_id,
                parent_run_id=parent_run_id,
                title=f"Run {run_id[:8]}",
                type="prototype",
                status=status,
                input="test",
                agent_count=1,
            )
        )
        db.commit()
    finally:
        db.close()

    # Create the sandbox directory structure. For a revision family,
    # the directory is keyed on the root_id, so we need to resolve that.
    # For a root run, use its own id; for a child, we create under parent
    sandbox_root = run_id if parent_run_id is None else parent_run_id
    sandbox_path = Path(settings.RUNS_ROOT) / owner_id / sandbox_root
    sandbox_path.mkdir(parents=True, exist_ok=True)

    # Set git user config globally for this test
    env_with_git = os.environ.copy()
    env_with_git["GIT_AUTHOR_NAME"] = "Test User"
    env_with_git["GIT_AUTHOR_EMAIL"] = "test@example.com"
    env_with_git["GIT_COMMITTER_NAME"] = "Test User"
    env_with_git["GIT_COMMITTER_EMAIL"] = "test@example.com"

    # Initialize a git repository for the sandbox (only if not already initialized)
    git_dir = sandbox_path / ".git"
    if not git_dir.exists():
        subprocess.run(
            ["git", "init"], cwd=sandbox_path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=sandbox_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=sandbox_path,
            check=True,
            capture_output=True,
        )

        # Create a tag for restore tests (only for the root run)
        (sandbox_path / "v1").write_text("tag content")
        subprocess.run(
            ["git", "add", "v1"],
            cwd=sandbox_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=sandbox_path,
            env=env_with_git,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "tag", "v1"],
            cwd=sandbox_path,
            check=True,
            capture_output=True,
        )

    return run_id


def _post_restore(env, run_id: str, tag: str = "v1") -> tuple[int, dict]:
    """Call POST /api/runs/{run_id}/restore and return (status_code, json_body)."""
    resp = env["client"].post(
        f"/api/runs/{run_id}/restore",
        json={"tag": tag, "idempotency_key": str(uuid.uuid4())},
    )
    return resp.status_code, resp.json()


# ────────────────────────────────────────────────────────────────────────────
# Test: unrelated active run does NOT block restore
# ────────────────────────────────────────────────────────────────────────────


def test_unrelated_active_run_does_not_block_restore_v1(env):
    """An unrelated active run does NOT block restore — at the guard-function level
    AND end to end through the real, mounted ``POST /{run_id}/restore`` route."""
    from app.api.runs import _has_active_family_member

    owner = _seed_user(env, "owner")
    env["state"]["user"] = owner

    # Family 1: a completed root run
    family1_root = str(uuid.uuid4())
    _seed_run(env, family1_root, owner.id, "completed")

    # Family 2: an independent root run that is currently active (unrelated to family 1)
    family2_root = str(uuid.uuid4())
    _seed_run(env, family2_root, owner.id, "running")  # active, but unrelated

    db = env["Session"]()
    try:
        # The guard should return False for family1_root (no active family members)
        result = _has_active_family_member(db, family1_root, owner.id)
        assert result is False, (
            f"Unrelated active run should not block restore on different family. "
            f"Expected False, got {result}"
        )
    finally:
        db.close()

    # Route level: the family-2 active run must not trip the 409 guard on the
    # (terminal) family-1 restore. The seeded sandbox is HEAD-at-"v1" already, so
    # ``materialize_tree_at_ref`` legitimately reports "no_change" — the request
    # still has to clear the guard and the rest of the route to get there.
    status_code, body = _post_restore(env, family1_root, tag="v1")
    assert (
        status_code == 200
    ), f"Expected the restore to proceed, got {status_code}: {body}"
    assert body["outcome"] in ("committed", "no_change"), body


# ────────────────────────────────────────────────────────────────────────────
# Test: active family member DOES block restore with 409
# ────────────────────────────────────────────────────────────────────────────


def test_active_family_member_blocks_restore_v1(env):
    """An active family member DOES block restore — at the guard-function level
    AND as a real HTTP 409 from the mounted ``POST /{run_id}/restore`` route."""
    from app.api.runs import _has_active_family_member

    owner = _seed_user(env, "owner")
    env["state"]["user"] = owner

    # Family: root + active revision
    family_root = str(uuid.uuid4())
    _seed_run(env, family_root, owner.id, "completed")

    # Child revision (same family, active)
    family_child = str(uuid.uuid4())
    _seed_run(env, family_child, owner.id, "running", parent_run_id=family_root)

    db = env["Session"]()
    try:
        # The guard should return True for family_root (active child exists)
        result = _has_active_family_member(db, family_root, owner.id)
        assert result is True, (
            f"Expected True when active family member exists. " f"Got {result}"
        )
    finally:
        db.close()

    # Route level: the active child must produce a real 409 from the endpoint,
    # never a silent pass-through.
    status_code, body = _post_restore(env, family_root, tag="v1")
    assert status_code == 409, f"Expected 409, got {status_code}: {body}"
    assert body["detail"]["code"] == "family_run_active", body


def test_terminal_family_members_do_not_block_restore_v1(env):
    """Terminal family members should not block restore via the guard function."""
    from app.api.runs import _has_active_family_member

    owner = _seed_user(env, "owner")
    db = env["Session"]()
    try:
        # Family: root + terminal revisions
        family_root = str(uuid.uuid4())
        _seed_run(env, family_root, owner.id, "completed")

        # Terminal child revisions
        family_child_failed = str(uuid.uuid4())
        _seed_run(
            env, family_child_failed, owner.id, "failed", parent_run_id=family_root
        )

        family_child_cancelled = str(uuid.uuid4())
        _seed_run(
            env,
            family_child_cancelled,
            owner.id,
            "cancelled",
            parent_run_id=family_root,
        )

        family_child_degraded = str(uuid.uuid4())
        _seed_run(
            env, family_child_degraded, owner.id, "degraded", parent_run_id=family_root
        )

        # The guard should return False (no active family members)
        result = _has_active_family_member(db, family_root, owner.id)
        assert result is False, (
            f"Terminal family members should not block. "
            f"Expected False, got {result}"
        )
    finally:
        db.close()


def test_multi_level_family_active_child_blocks_restore_v1(env):
    """Active grandchild in the family chain should block restore via the guard function."""
    from app.api.runs import _has_active_family_member

    owner = _seed_user(env, "owner")
    db = env["Session"]()
    try:
        # Family: root → child → grandchild (active)
        family_root = str(uuid.uuid4())
        _seed_run(env, family_root, owner.id, "completed")

        family_child = str(uuid.uuid4())
        _seed_run(env, family_child, owner.id, "completed", parent_run_id=family_root)

        family_grandchild = str(uuid.uuid4())
        _seed_run(
            env, family_grandchild, owner.id, "running", parent_run_id=family_child
        )

        # The guard should return True (active grandchild exists in the family)
        result = _has_active_family_member(db, family_root, owner.id)
        assert result is True, (
            f"Expected True when active grandchild exists in family. " f"Got {result}"
        )
    finally:
        db.close()
