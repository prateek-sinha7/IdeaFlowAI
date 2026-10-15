"""tests/integration/api/test_run_files_ref_family_scope_api.py — QA-PS-008 / ISS-671 / ISS-672.

Every sandbox git call in ``LocalWorkspace`` runs with only ``cwd`` set. When the
sandbox directory has NO ``.git`` of its own, git's normal upward repository
search finds whatever checkout encloses ``RUNS_ROOT`` — in QA-PS-008 that was the
Flowin source checkout itself (``RUNS_ROOT=../runs``), so its release/deploy tags
became "versions" (ISS-671, which corrects ISS-652/ISS-663). Three callers are
pinned here:

  * ``GET /{run_id}/sandbox/refs`` — the version dropdown feed lists the
    enclosing repo's tags.
  * ``_validate_ref`` — the gate for ``/sandbox``, ``/sandbox/zip`` and
    ``/sandbox/file`` accepts those tags and serves the enclosing repo's files.
  * The restore write path (ISS-672) — ``commit_all`` runs ``git add -A`` +
    ``git commit`` against the enclosing repo.

Fixture shape (per ISS-671 / ISS-672 "what would confirm this"): a throwaway
outer git repo at ``tmp_path`` tagged ``deploy-prod-leaked``, with ``RUNS_ROOT``
inside it and a chain-root sandbox that was never ``git init``-ed. Every git
call lands in that throwaway repo, never in the real checkout.

Do NOT run the full suite (it hangs offline) — this file only.
"""

from __future__ import annotations

import subprocess
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

    monkeypatch.setattr(ws_module, "_get_db", lambda: TestingSession())
    monkeypatch.setattr(rf_module, "_get_db", lambda: TestingSession())
    monkeypatch.setattr(db_module, "SessionLocal", TestingSession)

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


def _seed_user(env) -> _FakeUser:
    from app.models.user import User

    db = env["Session"]()
    try:
        u = User(
            id=str(uuid.uuid4()),
            email=f"u-{uuid.uuid4().hex[:8]}@example.com",
            cognito_sub=str(uuid.uuid4()),
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return _FakeUser(id=u.id)
    finally:
        db.close()


def _seed_run(env, *, user_id, run_id=None, parent_run_id=None, git_tag=None) -> str:
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
                status="completed",
                input="i",
                agent_count=4,
                session_id=user_id,
                parent_run_id=parent_run_id,
                git_tag=git_tag,
                created_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        return run_id
    finally:
        db.close()


def _outer_git(outer: Path, *args: str) -> str:
    return subprocess.run(
        [
            "git",
            "-c",
            "user.name=Host",
            "-c",
            "user.email=host@example.com",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=str(outer),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _make_tagged_outer_repo(outer: Path) -> str:
    """A throwaway "host checkout": one committed file, tagged ``deploy-prod-leaked``.

    Returns the outer repo's HEAD sha.
    """
    outer.mkdir(parents=True, exist_ok=True)
    _outer_git(outer, "init")
    (outer / "prototype.html").write_text("<h1>host checkout</h1>", encoding="utf-8")
    _outer_git(outer, "add", "prototype.html")
    _outer_git(outer, "commit", "-m", "host commit")
    _outer_git(outer, "tag", "deploy-prod-leaked")
    return _outer_git(outer, "rev-parse", "HEAD")


def _assert_nearest_repo_is(sandbox_root: Path, outer: Path) -> None:
    """Safety guard: git's upward search from the sandbox must reach the throwaway
    outer repo — never the real checkout — before any sandbox git call runs."""
    toplevel = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=str(sandbox_root),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert Path(toplevel).resolve() == outer.resolve()


def _make_family_in_host_checkout(env, user):
    """v1 (root) + v2 (revision) sharing a chain-root sandbox with NO ``.git``,
    nested inside a tagged outer repo — the QA-PS-008 shape (ISS-671).

    Returns (v1_id, v2_id).
    """
    from app.agents.sandbox import RunSandbox

    outer = Path(env["runs_root"]).parent  # tmp_path
    _make_tagged_outer_repo(outer)

    v1_id = _seed_run(env, user_id=user.id)
    v2_id = _seed_run(env, user_id=user.id, parent_run_id=v1_id)

    # Chain root == v1_id. ensure() only creates the dir — never git_init_sandbox().
    sb = RunSandbox(user.id, v1_id, runs_root=env["runs_root"])
    sb.ensure()
    # ISS-1072: an EMPTY run dir is an expired workspace (404 before the ref gate),
    # so give it the payload a live sandbox without its own .git still has.
    (sb.root / "notes.md").write_text("payload", encoding="utf-8")
    assert not (sb.root / ".git").exists()
    _assert_nearest_repo_is(sb.root, outer)

    return v1_id, v2_id


class TestVersionDropdownIsScopedToTheSandbox:
    """ISS-671 — GET /{run_id}/sandbox/refs must not list the enclosing repo's tags."""

    @pytest.mark.issue("ISS-671")
    def test_refs_is_empty_for_a_sandbox_with_no_git_of_its_own(self, env):
        user = _seed_user(env)
        env["state"]["user"] = user
        v1_id, v2_id = _make_family_in_host_checkout(env, user)

        resp = env["client"].get(f"/api/runs/{v2_id}/sandbox/refs")
        assert resp.status_code == 200
        refs = set(resp.json()["refs"])

        assert refs == set(), (
            "a sandbox with no .git of its own has no versions — got "
            f"{refs!r}, the enclosing repo's tags found by git's upward "
            "repository search (ISS-671)"
        )


class TestRefValidationIsScopedToTheSandbox:
    """ISS-671 (ISS-663's mechanism) — _validate_ref must reject the enclosing repo's tag."""

    @pytest.mark.issue("ISS-671")
    def test_an_enclosing_repo_tag_is_rejected(self, env):
        user = _seed_user(env)
        env["state"]["user"] = user
        v1_id, v2_id = _make_family_in_host_checkout(env, user)

        resp = env["client"].get(
            f"/api/runs/{v2_id}/sandbox/file",
            params={"path": "prototype.html", "ref": "deploy-prod-leaked"},
        )

        assert resp.status_code == 400, (
            "a tag that exists only in the repo ENCLOSING the sandbox must be "
            "rejected with 400 'invalid ref' — got "
            f"{resp.status_code} with body {resp.content[:60]!r} (ISS-671: the "
            "enclosing checkout's file was served at its own tag)"
        )


class TestRestoreWritePathStaysInTheSandbox:
    """ISS-672 — the restore write path must not commit into the enclosing repo."""

    @pytest.mark.issue("ISS-672")
    def test_materialize_and_commit_fail_closed_without_touching_the_outer_repo(
        self, tmp_path
    ):
        from app.agents.sandbox import RunSandbox

        outer = tmp_path
        head_before = _make_tagged_outer_repo(outer)
        # An uncommitted change in the "host checkout" that must never be committed.
        (outer / "host-wip.txt").write_text("uncommitted host work", encoding="utf-8")

        sb = RunSandbox("user-1", "run-1", runs_root=str(tmp_path / "runs"))
        sb.ensure()
        assert not (sb.root / ".git").exists()
        _assert_nearest_repo_is(sb.root, outer)

        raised: dict[str, bool] = {}
        for name, call in (
            (
                "materialize_tree_at_ref",
                lambda: sb.materialize_tree_at_ref("deploy-prod-leaked"),
            ),
            ("commit_all", lambda: sb.commit_all("restore to deploy-prod-leaked")),
        ):
            try:
                call()
                raised[name] = False
            except Exception:  # noqa: BLE001 — fail-closed is any raise
                raised[name] = True

        assert _outer_git(outer, "rev-parse", "HEAD") == head_before, (
            "commit_all on a sandbox with no .git committed into the enclosing "
            "repo (ISS-672: git add -A + git commit ran against the host checkout)"
        )
        assert (
            _outer_git(outer, "status", "--porcelain", "--", "host-wip.txt")
            == "?? host-wip.txt"
        )
        assert (
            raised == {"materialize_tree_at_ref": True, "commit_all": True}
        ), f"both write-path calls must fail closed ('not a git repository') — got {raised!r}"
