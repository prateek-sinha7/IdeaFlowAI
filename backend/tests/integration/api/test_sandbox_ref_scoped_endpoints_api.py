"""ISS-724 / ISS-893 (QA-KB-027) — pinned-ref workspace edge cases against REAL git.

Relocated home of the dead tests/unit/test_sandbox_ref_scoped_endpoints.py (unit I/O guard
refuses DB + git there). In-memory SQLite + real RunSandbox git + TestClient; never the live DB.
The product is correct for ISS-724 cases (plain tests); ISS-893 is fixed (plain test).
The classes at the bottom are that file's tests, moved verbatim apart from the fixture plumbing;
ISS-697 stays a strict-xfail pin.
"""

from __future__ import annotations

import io
import shutil
import uuid
import zipfile
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def env(monkeypatch, tmp_path):
    from app.api import run_engine as ws_module
    from app.api import run_files as rf_module
    from app.api.run_files import router
    from app.core.config import settings
    from app.core.dependencies import get_current_user
    from app.models import database as db_module
    from app.models.database import Base
    from app.models.user import User
    from app.models.workflow import WorkflowRun

    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Session = sessionmaker(autocommit=False, autoflush=False, bind=eng)
    Base.metadata.create_all(bind=eng)
    monkeypatch.setattr(ws_module, "_get_db", lambda: Session())
    monkeypatch.setattr(rf_module, "_get_db", lambda: Session())
    monkeypatch.setattr(db_module, "SessionLocal", Session)
    monkeypatch.setattr(settings, "RUNS_ROOT", str(tmp_path / "runs"))

    uid, run_id = str(uuid.uuid4()), str(uuid.uuid4())
    with Session() as db:
        db.add(
            User(
                id=uid, email=f"u-{uid[:8]}@example.com", cognito_sub=str(uuid.uuid4())
            )
        )
        db.commit()
        db.add(
            WorkflowRun(
                id=run_id,
                user_id=uid,
                owner_id=uid,
                workspace_id="ws-1",
                title="t",
                type="ppt_revision",
                status="completed",
                input="i",
                agent_count=4,
                session_id=uid,
                created_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: type("U", (), {"id": uid})()
    yield {
        "client": TestClient(app),
        "uid": uid,
        "run_id": run_id,
        "root": str(tmp_path / "runs"),
        "Session": Session,
    }
    Base.metadata.drop_all(bind=eng)
    eng.dispose()


def _sandbox(env):
    from app.agents.sandbox import RunSandbox

    sb = RunSandbox(env["uid"], env["run_id"], runs_root=env["root"])
    sb.ensure()
    sb.git_init_sandbox()
    return sb


def _zip(env, ref):
    r = env["client"].get(f"/api/runs/{env['run_id']}/sandbox/zip", params={"ref": ref})
    assert r.status_code == 200, r.text
    return zipfile.ZipFile(io.BytesIO(r.content))


def _make_tagged_sandbox(env, *, versions: list[str]):
    """A real git-backed sandbox: one commit + one tag per entry in ``versions``.

    ``versions`` is the SEQUENCE of file contents written to
    ``presentation.html`` — ``versions[0]`` becomes v1's commit+tag,
    ``versions[1]`` becomes v2's, and so on. Returns ``(run_id, sandbox)``.
    """
    sb = _sandbox(env)
    assert (sb.root / ".git").exists()

    for i, content in enumerate(versions, start=1):
        (sb.root / "presentation.html").write_text(content, encoding="utf-8")
        sb.commit_all(f"write v{i}")
        sb.create_tag(f"v{i}")

    return env["run_id"], sb


def _set_db_git_tag(env, tag: str) -> None:
    from app.models.workflow import WorkflowRun

    db = env["Session"]()
    try:
        row = db.query(WorkflowRun).filter(WorkflowRun.id == env["run_id"]).first()
        row.git_tag = tag
        db.commit()
    finally:
        db.close()


def test_zip_under_two_tags_holds_each_tags_bytes(env):
    """ISS-724 — zip ref=v1 / ref=v2 carry their own bytes; later edits invisible."""
    sb = _sandbox(env)
    (sb.root / "presentation.html").write_text("v1-bytes")
    sb.commit_all("v1")
    sb.create_tag("v1")
    (sb.root / "presentation.html").write_text("v2-bytes")
    (sb.root / "extra.txt").write_text("v2-only")
    sb.commit_all("v2")
    sb.create_tag("v2")
    (sb.root / "presentation.html").write_text("later-edit")

    z1, z2 = _zip(env, "v1"), _zip(env, "v2")
    assert z1.read("presentation.html") == b"v1-bytes"
    assert z2.read("presentation.html") == b"v2-bytes"
    assert "extra.txt" not in z1.namelist() and z2.read("extra.txt") == b"v2-only"


def test_chain_user_stories_md_is_served_per_ref(env):
    """ISS-724 — user_stories_revision deliverable lives at .chain/user_stories.md."""
    sb = _sandbox(env)
    for tag in ("v1", "v2"):
        (sb.root / ".chain").mkdir(exist_ok=True)
        (sb.root / ".chain" / "user_stories.md").write_text(f"{tag}-stories")
        sb.commit_all(tag, force_add=frozenset({".chain/user_stories.md"}))
        sb.create_tag(tag)
    c, rid = env["client"], env["run_id"]
    for tag in ("v1", "v2"):
        r = c.get(
            f"/api/runs/{rid}/sandbox/file",
            params={"path": ".chain/user_stories.md", "ref": tag},
        )
        assert r.status_code == 200 and r.content == f"{tag}-stories".encode()
        r = c.get(
            f"/api/runs/{rid}/sandbox/file",
            params={"path": "user_stories.md", "ref": tag},
        )
        assert r.status_code == 404


def test_valid_tag_missing_path_is_404(env):
    """ISS-724 — fresh parent without presentation.html: 404, never 500."""
    sb = _sandbox(env)
    (sb.root / "other.txt").write_text("x")
    sb.commit_all("v1")
    sb.create_tag("v1")
    r = env["client"].get(
        f"/api/runs/{env['run_id']}/sandbox/file",
        params={"path": "presentation.html", "ref": "v1"},
    )
    assert r.status_code == 404


def test_tagless_git_sandbox_rejects_ref_400(env):
    """ISS-724 — git-initialised but tagless: ref=v1 is 400 on file and zip."""
    sb = _sandbox(env)
    (sb.root / "a.txt").write_text("x")
    sb.commit_all("c")
    c, rid = env["client"], env["run_id"]
    assert (
        c.get(
            f"/api/runs/{rid}/sandbox/file", params={"path": "a.txt", "ref": "v1"}
        ).status_code
        == 400
    )
    assert (
        c.get(f"/api/runs/{rid}/sandbox/zip", params={"ref": "v1"}).status_code == 400
    )


@pytest.mark.issue("ISS-893")
def test_pinned_ref_listing_of_swept_sandbox_is_expired_payload(env):
    """ISS-893 — swept sandbox + ref=v1 listing must be 200 expired:true, not 400."""
    sb = _sandbox(env)
    (sb.root / "presentation.html").write_text("v1")
    sb.commit_all("v1")
    sb.create_tag("v1")
    shutil.rmtree(sb.root)
    r = env["client"].get(f"/api/runs/{env['run_id']}/sandbox", params={"ref": "v1"})
    assert r.status_code == 200 and r.json()["expired"] is True, (r.status_code, r.text)


@pytest.mark.issue("ISS-1072")
def test_empty_husk_sandbox_with_ref_is_expired_not_400(env):
    """ISS-1072 (QA-KB-095) — a swept dir re-created EMPTY must read as expired: no 400 on ?ref=v1."""
    sb = _sandbox(env)
    (sb.root / "presentation.html").write_text("v1")
    sb.commit_all("v1")
    sb.create_tag("v1")
    shutil.rmtree(sb.root)
    sb.root.mkdir(parents=True)  # the husk: directory present, nothing inside
    c, rid = env["client"], env["run_id"]
    r = c.get(f"/api/runs/{rid}/sandbox", params={"ref": "v1"})
    assert r.status_code == 200 and r.json()["expired"] is True, (r.status_code, r.text)
    assert c.get(f"/api/runs/{rid}/sandbox").json()["expired"] is True
    assert (
        c.get(f"/api/runs/{rid}/sandbox/zip", params={"ref": "v1"}).status_code == 404
    )
    assert (
        c.get(
            f"/api/runs/{rid}/sandbox/file", params={"path": "a.txt", "ref": "v1"}
        ).status_code
        == 404
    )


class TestRefScopedFileReadReturnsThatVersionsBytes:
    """A GET with ref=vN must return vN's own committed bytes — never today's."""

    def test_different_refs_return_different_bytes(self, env):
        run_id, _sb = _make_tagged_sandbox(env, versions=["<h1>v1</h1>", "<h1>v2</h1>"])

        r1 = env["client"].get(
            f"/api/runs/{run_id}/sandbox/file",
            params={"path": "presentation.html", "ref": "v1"},
        )
        r2 = env["client"].get(
            f"/api/runs/{run_id}/sandbox/file",
            params={"path": "presentation.html", "ref": "v2"},
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
        run_id, sb = _make_tagged_sandbox(env, versions=["<h1>v1</h1>"])

        # A further, UNTAGGED write past v1 — simulates HEAD having moved on
        # since the last tag (e.g. mid-revision, before the next tag lands).
        (sb.root / "presentation.html").write_text(
            "<h1>working tree</h1>", encoding="utf-8"
        )
        sb.commit_all("write working tree state")

        no_ref = env["client"].get(
            f"/api/runs/{run_id}/sandbox/file", params={"path": "presentation.html"}
        )
        tagged = env["client"].get(
            f"/api/runs/{run_id}/sandbox/file",
            params={"path": "presentation.html", "ref": "v1"},
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
        run_id, _sb = _make_tagged_sandbox(env, versions=["<h1>v1</h1>"])

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
        run_id, sb = _make_tagged_sandbox(env, versions=["<h1>v1</h1>", "<h1>v2</h1>"])
        # Corrupt the DB's belief on purpose — refs must come from git, not this.
        _set_db_git_tag(env, "v-does-not-exist-in-git")

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
    ``test_run_files_ref_family_scope_api.py``'s ``TestVersionDropdownIsScopedToTheSandbox``
    for the same pattern) — this is regression protection, not a red pin.
    """

    @pytest.mark.issue("QA-PS-032")
    def test_ref_scoped_listing_reports_the_real_file_size(self, env):
        content = "<h1>v1</h1>"  # 11 bytes
        run_id, _sb = _make_tagged_sandbox(env, versions=[content])

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
        # DB believes this completed run is tagged v1 (git_tag written eagerly
        # per the normal finalize path)...
        _set_db_git_tag(env, "v1")
        run_id = env["run_id"]

        # ...but the actual tag mint at finalize silently failed (best-effort,
        # per ISS-697's root cause) — the sandbox got its commit, never its tag.
        sb = _sandbox(env)
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
