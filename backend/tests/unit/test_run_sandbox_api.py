"""tests/unit/test_run_sandbox_api.py — the workspace browser (spec 017 phase 2).

``GET /api/runs/{id}/sandbox`` and ``GET /api/runs/{id}/sandbox/file``, proven
OFFLINE (TestClient + in-memory SQLite scoped store + a temp RUNS_ROOT). The
harness is lifted from ``test_run_files_upload.py`` — same two-layer ownership
seam, so the read endpoints are held to the write endpoint's standard.

What is actually at stake here, in order:

  * **Ownership** — a foreign-owner run and a store-denied run BOTH 404. Never
    403: a 403 confirms the id exists, which is the IDOR.
  * **The inline/attachment split** — the security boundary. A sandbox file is
    agent-authored; `.html` served inline from the API origin is stored XSS with
    the caller's session in scope. Only the text whitelist goes out inline, and
    `.html` is deliberately NOT on it.
  * **Traversal** — `..` and an absolute path are rejected by ``path_for``
    before any read.
  * **Reserved subtrees** — `.uploads/` and `.logs/` are neither listed nor
    readable, so the listing is a complete description of what can be fetched.
  * **Caps** — an over-cap file is refused rather than streamed; a runaway
    sandbox is truncated and SAYS so.
  * **Expiry** — a TTL-swept run reports `expired`, so the UI can say
    "workspace expired" instead of showing an empty tree.

Do NOT run the full suite (it hangs offline) — this file only.
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
        "rf": rf_module,
    }

    Base.metadata.drop_all(bind=db_engine)
    db_engine.dispose()


def _seed_user(env, tag: str) -> _FakeUser:
    from app.models.user import User

    db = env["Session"]()
    try:
        u = User(
            id=str(uuid.uuid4()),
            email=f"sbx-{tag}-{uuid.uuid4().hex[:8]}@example.com",
            password_hash="x",
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return _FakeUser(id=u.id)
    finally:
        db.close()


def _seed_run(env, *, user_id, owner_id, workspace_id="ws-1") -> str:
    from app.models.workflow import WorkflowRun

    run_id = str(uuid.uuid4())
    db = env["Session"]()
    try:
        db.add(
            WorkflowRun(
                id=run_id,
                user_id=user_id,
                owner_id=owner_id,
                workspace_id=workspace_id,
                title="t",
                type="ppt_v2",
                status="completed",
                input="i",
                agent_count=4,
                session_id=user_id,
                created_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        return run_id
    finally:
        db.close()


def _owned_run(env, user: _FakeUser) -> str:
    return _seed_run(env, user_id=user.id, owner_id=user.id)


def _sandbox(env, user_id, run_id):
    from app.agents.sandbox import RunSandbox

    return RunSandbox(user_id, run_id, runs_root=env["runs_root"])


def _seed_ppt_v2_workspace(env, user, run_id):
    """The shape a real ppt_v2 run leaves behind, plus both reserved subtrees."""
    sb = _sandbox(env, user.id, run_id)
    sb.ensure()
    sb.write("presentation.html", "<h1>Deck</h1>")
    sb.write("notes.md", "# plan")
    (sb.root / "presentation.pptx").write_bytes(b"PK\x03\x04not-really-a-pptx")
    sb.write(".uploads/brief.txt", "owner upload")
    sb.write(".logs/run-logs.jsonl", '{"event":"start"}')
    return sb


def _list(env, run_id):
    return env["client"].get(f"/api/runs/{run_id}/sandbox")


def _read(env, run_id, path):
    return env["client"].get(f"/api/runs/{run_id}/sandbox/file", params={"path": path})


# ════════════════════════════════════════════════════════════════════════════
# Ownership — both layers, both endpoints, 404 and never 403
# ════════════════════════════════════════════════════════════════════════════


class TestOwnership:
    def test_a_foreign_owners_workspace_is_404_not_403(self, env):
        owner = _seed_user(env, "owner")
        attacker = _seed_user(env, "attacker")
        run_id = _owned_run(env, owner)
        _seed_ppt_v2_workspace(env, owner, run_id)

        env["state"]["user"] = attacker
        assert _list(env, run_id).status_code == 404
        assert _read(env, run_id, "presentation.html").status_code == 404

    def test_a_store_denied_run_is_404_at_layer_two(self, env):
        user = _seed_user(env, "u")
        # Layer 1 passes (user_id matches) but the store scopes on owner_id.
        run_id = _seed_run(env, user_id=user.id, owner_id=str(uuid.uuid4()))
        env["state"]["user"] = user

        assert _list(env, run_id).status_code == 404
        assert _read(env, run_id, "notes.md").status_code == 404

    def test_an_unknown_run_id_is_404(self, env):
        env["state"]["user"] = _seed_user(env, "u")
        assert _list(env, str(uuid.uuid4())).status_code == 404


# ════════════════════════════════════════════════════════════════════════════
# The listing
# ════════════════════════════════════════════════════════════════════════════


class TestListing:
    def test_it_lists_the_run_artifacts(self, env):
        user = _seed_user(env, "u")
        run_id = _owned_run(env, user)
        _seed_ppt_v2_workspace(env, user, run_id)
        env["state"]["user"] = user

        body = _list(env, run_id).json()
        paths = [f["path"] for f in body["files"]]
        assert paths == ["notes.md", "presentation.html", "presentation.pptx"]
        assert body["expired"] is False
        assert body["truncated"] is False

    def test_the_reserved_subtrees_are_never_listed(self, env):
        user = _seed_user(env, "u")
        run_id = _owned_run(env, user)
        _seed_ppt_v2_workspace(env, user, run_id)
        env["state"]["user"] = user

        paths = [f["path"] for f in _list(env, run_id).json()["files"]]
        assert not [p for p in paths if p.startswith(".uploads/")]
        assert not [p for p in paths if p.startswith(".logs/")]

    def test_it_marks_which_files_the_viewer_can_render_as_text(self, env):
        user = _seed_user(env, "u")
        run_id = _owned_run(env, user)
        _seed_ppt_v2_workspace(env, user, run_id)
        env["state"]["user"] = user

        by_path = {f["path"]: f for f in _list(env, run_id).json()["files"]}
        assert by_path["notes.md"]["text"] is True
        # html is viewable as SOURCE (the tab fetches it) even though it is
        # never served inline — see the inline/attachment tests below.
        assert by_path["presentation.html"]["text"] is True
        assert by_path["presentation.pptx"]["text"] is False

    def test_a_swept_run_reports_expired_rather_than_empty(self, env):
        user = _seed_user(env, "u")
        run_id = _owned_run(env, user)  # never ensure()d — the sweeper's end state
        env["state"]["user"] = user

        body = _list(env, run_id).json()
        assert body["expired"] is True
        assert body["files"] == []

    def test_a_runaway_sandbox_is_truncated_and_says_so(self, env):
        from app.agents import sandbox as sb_module

        user = _seed_user(env, "u")
        run_id = _owned_run(env, user)
        sb = _sandbox(env, user.id, run_id)
        sb.ensure()
        for i in range(sb_module._LIST_MAX_FILES + 5):
            sb.write(f"f{i:04d}.md", "x")
        env["state"]["user"] = user

        body = _list(env, run_id).json()
        assert body["truncated"] is True
        assert len(body["files"]) == sb_module._LIST_MAX_FILES


# ════════════════════════════════════════════════════════════════════════════
# The read — inline vs attachment is the security boundary
# ════════════════════════════════════════════════════════════════════════════


class TestRead:
    def test_a_whitelisted_text_file_is_served_inline_as_plain_text(self, env):
        user = _seed_user(env, "u")
        run_id = _owned_run(env, user)
        _seed_ppt_v2_workspace(env, user, run_id)
        env["state"]["user"] = user

        r = _read(env, run_id, "notes.md")
        assert r.status_code == 200
        assert r.text == "# plan"
        assert r.headers["content-type"].startswith("text/plain")
        assert r.headers["content-disposition"].startswith("inline")
        assert r.headers["x-content-type-options"] == "nosniff"

    def test_agent_authored_html_is_never_served_inline(self, env):
        """The whole reason the whitelist exists.

        `presentation.html` is written by an LLM. Serving it inline from the API
        origin with `text/html` would run its script with the caller's session
        cookie in scope — stored XSS. It must come back as an attachment with an
        inert content type, and nosniff must stop the browser re-typing it.
        """
        user = _seed_user(env, "u")
        run_id = _owned_run(env, user)
        _seed_ppt_v2_workspace(env, user, run_id)
        env["state"]["user"] = user

        r = _read(env, run_id, "presentation.html")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/octet-stream"
        assert r.headers["content-disposition"].startswith("attachment")
        assert r.headers["x-content-type-options"] == "nosniff"
        # The body is still readable by a fetch(), which is how the tab shows it.
        assert r.text == "<h1>Deck</h1>"

    def test_a_binary_artifact_comes_back_as_an_attachment(self, env):
        user = _seed_user(env, "u")
        run_id = _owned_run(env, user)
        _seed_ppt_v2_workspace(env, user, run_id)
        env["state"]["user"] = user

        r = _read(env, run_id, "presentation.pptx")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/octet-stream"
        assert 'filename="presentation.pptx"' in r.headers["content-disposition"]

    @pytest.mark.parametrize(
        "path",
        ["../../../etc/passwd", "/etc/passwd", "sub/../../../../etc/passwd"],
    )
    def test_traversal_never_reads_outside_the_run_dir(self, env, path):
        user = _seed_user(env, "u")
        run_id = _owned_run(env, user)
        _seed_ppt_v2_workspace(env, user, run_id)
        env["state"]["user"] = user

        # Either rejected outright (400) or resolved to a non-existent path
        # inside the sandbox (404). Never 200 — that would be the escape.
        assert _read(env, run_id, path).status_code in (400, 404)

    @pytest.mark.parametrize("path", [".uploads/brief.txt", ".logs/run-logs.jsonl"])
    def test_the_reserved_subtrees_are_not_readable_either(self, env, path):
        user = _seed_user(env, "u")
        run_id = _owned_run(env, user)
        _seed_ppt_v2_workspace(env, user, run_id)
        env["state"]["user"] = user

        assert _read(env, run_id, path).status_code == 404

    def test_an_over_cap_file_is_refused_not_streamed(self, env):
        from app.api import run_files as rf

        user = _seed_user(env, "u")
        run_id = _owned_run(env, user)
        sb = _sandbox(env, user.id, run_id)
        sb.ensure()
        (sb.root / "huge.md").write_bytes(b"x" * (rf._SANDBOX_MAX_READ_BYTES + 1))
        env["state"]["user"] = user

        assert _read(env, run_id, "huge.md").status_code == 413

    def test_reading_from_a_swept_workspace_is_404(self, env):
        user = _seed_user(env, "u")
        run_id = _owned_run(env, user)
        env["state"]["user"] = user

        assert _read(env, run_id, "presentation.html").status_code == 404

    def test_a_hostile_filename_cannot_smuggle_a_header(self, env):
        """Response splitting: the Content-Disposition alphabet is bounded."""
        user = _seed_user(env, "u")
        run_id = _owned_run(env, user)
        sb = _sandbox(env, user.id, run_id)
        sb.ensure()
        sb.write('we"ird name.md', "body")
        env["state"]["user"] = user

        r = _read(env, run_id, 'we"ird name.md')
        assert r.status_code == 200
        cd = r.headers["content-disposition"]
        assert "\r" not in cd and "\n" not in cd
        assert 'filename="we_ird_name.md"' in cd


# ════════════════════════════════════════════════════════════════════════════
# Images and PDFs — the gate's evidence has to be LOOKABLE-AT
# ════════════════════════════════════════════════════════════════════════════
#
# `render_pptx` writes its verdict evidence to `.verify/` as PNG screenshots and
# a PDF. Classifying those "binary — use Download" made the one artifact a human
# comes to the workspace to inspect the one artifact the workspace would not
# show. They are still attachments and still nosniff: the viewer fetches them
# with the auth header and renders a `blob:` URL, so nothing is navigated to on
# the API origin. Only the Content-Type changes, because a Blob carries its
# response's type and `<img>` needs a real one.


def _seed_verify_evidence(env, user, run_id):
    sb = _sandbox(env, user.id, run_id)
    sb.ensure()
    (sb.root / ".verify").mkdir(exist_ok=True)
    (sb.root / ".verify" / "slide-01.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    (sb.root / ".verify" / "presentation.pdf").write_bytes(b"%PDF-1.4\n" + b"0" * 32)
    return sb


class TestViewableMedia:
    def test_the_listing_classifies_a_png_and_a_pdf(self, env):
        user = _seed_user(env, "u")
        run_id = _owned_run(env, user)
        _seed_ppt_v2_workspace(env, user, run_id)
        _seed_verify_evidence(env, user, run_id)
        env["state"]["user"] = user

        by_path = {f["path"]: f for f in _list(env, run_id).json()["files"]}
        assert by_path[".verify/slide-01.png"]["kind"] == "image"
        assert by_path[".verify/presentation.pdf"]["kind"] == "pdf"
        assert by_path["notes.md"]["kind"] == "text"
        assert by_path["presentation.pptx"]["kind"] == "binary"
        # `text` keeps meaning exactly what it meant: render the bytes as a string.
        assert by_path[".verify/slide-01.png"]["text"] is False

    def test_an_image_is_served_with_its_real_type_still_as_an_attachment(self, env):
        user = _seed_user(env, "u")
        run_id = _owned_run(env, user)
        _seed_verify_evidence(env, user, run_id)
        env["state"]["user"] = user

        r = _read(env, run_id, ".verify/slide-01.png")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/png"
        # Attachment + nosniff, unchanged: a browser pointed straight here still
        # saves the file rather than rendering it on the API origin.
        assert r.headers["content-disposition"].startswith("attachment")
        assert r.headers["x-content-type-options"] == "nosniff"

    def test_a_pdf_is_served_as_application_pdf(self, env):
        user = _seed_user(env, "u")
        run_id = _owned_run(env, user)
        _seed_verify_evidence(env, user, run_id)
        env["state"]["user"] = user

        r = _read(env, run_id, ".verify/presentation.pdf")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.headers["content-disposition"].startswith("attachment")

    def test_an_svg_stays_text_and_is_never_typed_as_an_image(self, env):
        """An SVG is a script-bearing document, not a picture.

        Classifying it `image` would put agent-authored markup behind an
        `<img src="blob:...">` — harmless there, but one refactor away from an
        `<object>`/`<iframe>`, where it executes. It stays in the text set.
        """
        user = _seed_user(env, "u")
        run_id = _owned_run(env, user)
        sb = _sandbox(env, user.id, run_id)
        sb.ensure()
        sb.write("chart.svg", '<svg xmlns="http://www.w3.org/2000/svg"></svg>')
        env["state"]["user"] = user

        by_path = {f["path"]: f for f in _list(env, run_id).json()["files"]}
        assert by_path["chart.svg"]["kind"] == "text"
        assert _read(env, run_id, "chart.svg").headers["content-type"] == (
            "application/octet-stream"
        )


class TestWorkspaceZip:
    """One archive instead of 36 downloads the browser will block."""

    def test_it_archives_exactly_what_the_workspace_lists(self, env):
        import io
        import zipfile

        user = _seed_user(env, "u")
        run_id = _owned_run(env, user)
        _seed_ppt_v2_workspace(env, user, run_id)
        env["state"]["user"] = user

        r = env["client"].get(f"/api/runs/{run_id}/sandbox/zip")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/zip"
        assert r.headers["content-disposition"].startswith("attachment")
        assert r.headers["x-content-type-options"] == "nosniff"

        names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
        stem = names[0].split("/", 1)[0]
        # One top-level directory, so unzipping does not scatter files.
        assert all(n.startswith(f"{stem}/") for n in names)
        inner = sorted(n.split("/", 1)[1] for n in names)
        assert inner == sorted(f["path"] for f in _list(env, run_id).json()["files"])
        # The reserved subtrees are excluded from the listing and so from here.
        assert not [n for n in inner if n.startswith((".uploads/", ".logs/"))]

    def test_a_foreign_owner_gets_404(self, env):
        owner = _seed_user(env, "owner")
        attacker = _seed_user(env, "attacker")
        run_id = _owned_run(env, owner)
        _seed_ppt_v2_workspace(env, owner, run_id)
        env["state"]["user"] = attacker

        assert env["client"].get(f"/api/runs/{run_id}/sandbox/zip").status_code == 404

    def test_a_swept_workspace_is_404(self, env):
        user = _seed_user(env, "u")
        run_id = _owned_run(env, user)  # never ensure()d
        env["state"]["user"] = user

        assert env["client"].get(f"/api/runs/{run_id}/sandbox/zip").status_code == 404

    def test_an_oversized_workspace_is_refused(self, env, monkeypatch):
        from app.api import run_files

        user = _seed_user(env, "u")
        run_id = _owned_run(env, user)
        _seed_ppt_v2_workspace(env, user, run_id)
        env["state"]["user"] = user
        monkeypatch.setattr(run_files, "_SANDBOX_MAX_ZIP_BYTES", 4)

        r = env["client"].get(f"/api/runs/{run_id}/sandbox/zip")
        assert r.status_code == 413
        assert "too large" in r.json()["detail"].lower()
