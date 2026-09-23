"""tests/unit/test_sandbox_ref_scoped_endpoints.py — ref-scoped sandbox endpoints,
against a REAL git-backed sandbox (not mocked, unlike test_phase6_sandbox_versioning.py)
and a REAL FastAPI TestClient (unlike the mocked-subprocess coverage there).

Builds a self-contained temp git sandbox with 2-3 tagged versions of differing
content per test — never depends on the swept-eligible reference family
(runs/c6b9b61f-.../4d55165d-.../) named in the bug brief.

GREEN — lock in correct behaviour:
  - GET /sandbox/file?path=X&ref=vN returns vN's bytes; a different ref returns
    different bytes.
  - The same path with NO ref returns the working tree (HEAD) — intentional,
    see TestOmittingRefServesTheWorkingTree's docstring for why.
  - An invalid/unknown ref is rejected 400, not silently served.
  - GET /sandbox/refs lists exactly the tags git holds, not what the DB believes.
  - QA-PS-032 / ISS-720: ref-scoped listing reports real byte sizes. Found ALREADY
    FIXED (uncommitted, landed concurrently on this branch during authoring) —
    kept as a GREEN `issue`-marked regression test, not xfail. See that test's
    docstring for the observed evidence.

xfail(strict) — pin the bug still open:
  - ISS-697: a COMPLETED run's DB git_tag can point at a tag that was never
    actually minted in the sandbox — tag creation is best-effort at finalize.

Do NOT run the full suite (matches the convention set by
test_run_files_ref_family_scope.py in this directory) — this file only.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

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
    from app.api import run_engine as ws_module
    from app.api import run_files as rf_module
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
        u = User(id=str(uuid.uuid4()), email=f"u-{uuid.uuid4().hex[:8]}@example.com", password_hash="x")
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
                type="ppt_revision",
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


def _make_tagged_sandbox(env, user, *, versions: list[str]):
    """A real git-backed sandbox: one commit + one tag per entry in ``versions``.

    ``versions`` is the SEQUENCE of file contents written to
    ``presentation.html`` — ``versions[0]`` becomes v1's commit+tag,
    ``versions[1]`` becomes v2's, and so on. Returns ``(run_id, sandbox)``.
    """
    from app.agents.sandbox import RunSandbox

    run_id = _seed_run(env, user_id=user.id)
    sb = RunSandbox(user.id, run_id, runs_root=env["runs_root"])
    sb.ensure()
    sb.git_init_sandbox()
    assert (sb.root / ".git").exists()

    for i, content in enumerate(versions, start=1):
        (sb.root / "presentation.html").write_text(content, encoding="utf-8")
        sb.commit_all(f"write v{i}")
        sb.create_tag(f"v{i}")

    return run_id, sb


class TestRefScopedFileReadReturnsThatVersionsBytes:
    """A GET with ref=vN must return vN's own committed bytes — never today's."""

    def test_different_refs_return_different_bytes(self, env):
        user = _seed_user(env)
        env["state"]["user"] = user
        run_id, _sb = _make_tagged_sandbox(
            env, user, versions=["<h1>v1</h1>", "<h1>v2</h1>"]
        )

        r1 = env["client"].get(
            f"/api/runs/{run_id}/sandbox/file", params={"path": "presentation.html", "ref": "v1"}
        )
        r2 = env["client"].get(
            f"/api/runs/{run_id}/sandbox/file", params={"path": "presentation.html", "ref": "v2"}
        )

        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.content == b"<h1>v1</h1>"
        assert r2.content == b"<h1>v2</h1>"
        assert r1.content != r2.content, (
            "ref=v1 and ref=v2 served byte-identical content — this is the FIX-601 "
            "symptom: a write-tool-less revision step never touched the file, so "
            "every tag captured identical stale bytes"
        )


class TestOmittingRefServesTheWorkingTree:
    """No ``ref`` means HEAD/the working tree, by design.

    Every family member shares ONE physical sandbox (``_resolve_chain_root_or_404``),
    so there is no per-version directory to fall back to — "no ref" can only ever
    mean "whatever is on disk right now". This is NOT the QA-PS-054/056 bug: those
    are the frontend failing to PASS a ref it has; the endpoint itself correctly
    treats an absent ref as "give me HEAD".
    """

    def test_no_ref_returns_head_not_a_tagged_version(self, env):
        user = _seed_user(env)
        env["state"]["user"] = user
        run_id, sb = _make_tagged_sandbox(env, user, versions=["<h1>v1</h1>"])

        # A further, UNTAGGED write past v1 — simulates HEAD having moved on
        # since the last tag (e.g. mid-revision, before the next tag lands).
        (sb.root / "presentation.html").write_text("<h1>working tree</h1>", encoding="utf-8")
        sb.commit_all("write working tree state")

        no_ref = env["client"].get(
            f"/api/runs/{run_id}/sandbox/file", params={"path": "presentation.html"}
        )
        tagged = env["client"].get(
            f"/api/runs/{run_id}/sandbox/file", params={"path": "presentation.html", "ref": "v1"}
        )

        assert no_ref.status_code == 200
        assert no_ref.content == b"<h1>working tree</h1>", (
            "omitting ref must serve the CURRENT working tree, not silently pin "
            "the latest tag — by design (all family members share one sandbox, "
            "so there is no other place for 'no ref' to mean)"
        )
        assert tagged.content == b"<h1>v1</h1>"
        assert no_ref.content != tagged.content


class TestInvalidRefIsRejected:
    """An unknown ref string must be a 400, never silently served or 500'd."""

    def test_unknown_ref_is_rejected_400(self, env):
        user = _seed_user(env)
        env["state"]["user"] = user
        run_id, _sb = _make_tagged_sandbox(env, user, versions=["<h1>v1</h1>"])

        resp = env["client"].get(
            f"/api/runs/{run_id}/sandbox/file",
            params={"path": "presentation.html", "ref": "v99-does-not-exist"},
        )

        assert resp.status_code == 400, (
            f"an unknown ref must be rejected with 400 'invalid ref' — got "
            f"{resp.status_code} with body {resp.content[:80]!r}"
        )


class TestSandboxRefsListsExactlyGitsTags:
    """GET /sandbox/refs must reflect git's own tag list, not the DB's belief."""

    def test_refs_matches_git_tags_even_when_db_git_tag_disagrees(self, env):
        user = _seed_user(env)
        env["state"]["user"] = user
        run_id, sb = _make_tagged_sandbox(
            env, user, versions=["<h1>v1</h1>", "<h1>v2</h1>"]
        )
        # Corrupt the DB's belief on purpose — refs must come from git, not this.
        from app.models.workflow import WorkflowRun

        db = env["Session"]()
        try:
            row = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
            row.git_tag = "v-does-not-exist-in-git"
            db.commit()
        finally:
            db.close()

        resp = env["client"].get(f"/api/runs/{run_id}/sandbox/refs")
        assert resp.status_code == 200
        refs = set(resp.json()["refs"])

        assert refs == {"v1", "v2"}, (
            f"GET /sandbox/refs must list exactly git's own tags ({{'v1', 'v2'}}), "
            f"ignoring the (deliberately wrong) WorkflowRun.git_tag column — got {refs!r}"
        )


class TestQAPS032RefScopedListingReportsRealSizes:
    """QA-PS-032 / ISS-720 — ref-scoped listing must report real byte sizes, not 0.

    GREEN, not xfail: observed live during this test's authoring that
    ``run_files.py``'s ref-scoped branch now computes real sizes via
    ``sandbox.file_sizes_at_ref`` (an ``ISS-720`` fix landed on this branch
    while this file was being written — ``git diff --stat`` shows
    ``run_files.py`` / ``sandbox.py`` / ``local.py`` already carry it,
    though the ``ISS-720`` card itself is still ``status: open``). Kept as
    ``issue`` documentation with no ``xfail`` per this suite's convention for
    a bug proven fixed at test-authoring time (see
    ``test_run_files_ref_family_scope.py``'s ``TestVersionDropdownIsScopedToTheSandbox``
    for the same pattern) — this is regression protection, not a red pin.
    """

    @pytest.mark.issue("QA-PS-032")
    def test_ref_scoped_listing_reports_the_real_file_size(self, env):
        user = _seed_user(env)
        env["state"]["user"] = user
        content = "<h1>v1</h1>"  # 11 bytes
        run_id, _sb = _make_tagged_sandbox(env, user, versions=[content])

        resp = env["client"].get(f"/api/runs/{run_id}/sandbox", params={"ref": "v1"})
        assert resp.status_code == 200
        files = {f["path"]: f for f in resp.json()["files"]}

        assert "presentation.html" in files
        assert files["presentation.html"]["size"] == len(content.encode("utf-8")), (
            "ref-scoped listing must report presentation.html's real size "
            f"({len(content.encode('utf-8'))} bytes) — got "
            f"{files['presentation.html']['size']!r} (QA-PS-032: run_files.py:930 "
            "hardcodes \"size\": 0 for every ref-scoped entry)"
        )


class TestISS697CompletedRunAlwaysHasARealTag:
    """ISS-697 — a COMPLETED run's DB-recorded tag must actually exist in the
    sandbox git holds. Tag creation at finalize is best-effort (engine.py
    finalize_terminal_run step 8) and can silently not happen, leaving
    WorkflowRun.git_tag and GET /sandbox/refs (the git-truth source) to drift
    apart — exactly the two-independent-sources split the card documents.
    """

    @pytest.mark.issue("ISS-697")
    @pytest.mark.xfail(reason="ISS-697 unfixed", strict=True)
    def test_a_completed_runs_db_tag_is_present_in_sandbox_refs(self, env):
        from app.agents.sandbox import RunSandbox

        user = _seed_user(env)
        env["state"]["user"] = user
        # DB believes this completed run is tagged v1 (git_tag written eagerly
        # per the normal finalize path)...
        run_id = _seed_run(env, user_id=user.id, git_tag="v1")

        # ...but the actual tag mint at finalize silently failed (best-effort,
        # per ISS-697's root cause) — the sandbox got its commit, never its tag.
        sb = RunSandbox(user.id, run_id, runs_root=env["runs_root"])
        sb.ensure()
        sb.git_init_sandbox()
        (sb.root / "presentation.html").write_text("<h1>v1</h1>", encoding="utf-8")
        sb.commit_all("write v1")
        # sb.create_tag("v1") deliberately NOT called.

        resp = env["client"].get(f"/api/runs/{run_id}/sandbox/refs")
        assert resp.status_code == 200
        refs = resp.json()["refs"]

        assert "v1" in refs, (
            "WorkflowRun.git_tag='v1' and status='completed', but the sandbox's "
            f"own git tags are {refs!r} — a completed run's recorded version must "
            "always be a real, mintable tag (ISS-697: tag creation is best-effort "
            "at finalize, engine.py:2349-2456, and can silently not happen)"
        )
