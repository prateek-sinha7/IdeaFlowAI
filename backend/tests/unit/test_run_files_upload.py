"""tests/unit/test_run_files_upload.py — UPLD-01 (30-01).

The owner-scoped document-upload endpoint ``POST /api/runs/{id}/files``, proven
OFFLINE (TestClient + in-memory SQLite scoped store + a temp RUNS_ROOT; no live
Bedrock / uvicorn). Covers the full UPLD-01 contract:

  * **Ownership (T-30-01)** — a foreign-owner run id → 404 (Layer 1 ORM filter);
    an owner-owned but store-denied run id → 404 (Layer 2 default-deny). Both
    assert 404, NEVER 403 (IDOR → 404).
  * **Caps (T-30-02/04) — BEFORE any write** — oversize → 413; disallowed
    ext / image mime → 415; over-count / over-aggregate → 413, asserting NO file
    landed in the sandbox.
  * **Sandbox landing** — an extractable doc writes ``.uploads/<name>`` raw +
    ``.uploads/<name>.txt`` sidecar + a ``manifest.json`` entry (has_text True);
    a ``.txt`` upload lands raw with has_text False.
  * **Deliverable exclusion (T-30-05)** — after an upload,
    ``serialize_sandbox_deliverable`` returns the SAME string as an identical
    sandbox WITHOUT any ``.uploads/`` tree (uploads invisible to the deliverable;
    INV-3 dormancy).
  * **Single-impl guard (INV-12)** — ``extract_upload_text`` returns exactly what
    the ``/api/files/extract-text`` endpoint path returns for the same bytes.

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
    from app.api import websocket as ws_module
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

    # Patch _get_db on BOTH modules: run_files binds its OWN reference at import
    # (``from app.api.websocket import _get_db``).
    monkeypatch.setattr(ws_module, "_get_db", lambda: TestingSession())
    monkeypatch.setattr(rf_module, "_get_db", lambda: TestingSession())
    # ScopedStore(session=None) opens app.models.database.SessionLocal() — bind it too.
    monkeypatch.setattr(db_module, "SessionLocal", TestingSession)

    # Land every sandbox write under a writable temp RUNS_ROOT (per the deepagents
    # test recipe — /app/runs is not writable locally).
    runs_root = tmp_path / "runs"
    monkeypatch.setattr(settings, "RUNS_ROOT", str(runs_root))

    from app.api.file_extract import router as file_extract_router
    from app.api.run_files import router as run_files_router
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
            email=f"upld-{tag}-{uuid.uuid4().hex[:8]}@example.com",
            password_hash="x",
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return _FakeUser(id=u.id)
    finally:
        db.close()


def _seed_run(env, *, user_id, owner_id, workspace_id="ws-1", status="running") -> str:
    """Seed a WorkflowRun. ``owner_id`` distinct from ``user_id`` yields a
    Layer-1-pass / Layer-2-deny run (the store's default-deny scope filters on
    owner_id)."""
    from app.models.workflow import WorkflowRun

    run_id = str(uuid.uuid4())
    db = env["Session"]()
    try:
        db.add(WorkflowRun(
            id=run_id, user_id=user_id, owner_id=owner_id, workspace_id=workspace_id,
            title="t", type="prototype", status=status, input="i",
            agent_count=1, session_id=user_id, created_at=datetime.now(timezone.utc),
        ))
        db.commit()
        return run_id
    finally:
        db.close()


def _owned_run(env, user: _FakeUser) -> str:
    """A fully owner-scoped run the caller owns at BOTH layers."""
    return _seed_run(env, user_id=user.id, owner_id=user.id)


def _post(env, run_id, files):
    return env["client"].post(f"/api/runs/{run_id}/files", files=files)


def _sandbox(env, user_id, run_id):
    from app.agents.sandbox import RunSandbox

    return RunSandbox(user_id, run_id, runs_root=env["runs_root"])


# ════════════════════════════════════════════════════════════════════════════
# Ownership (T-30-01) — both layers → 404, never 403
# ════════════════════════════════════════════════════════════════════════════


class TestOwnership:
    def test_foreign_owner_run_is_404_not_403(self, env):
        owner = _seed_user(env, "owner")
        attacker = _seed_user(env, "attacker")
        run_id = _owned_run(env, owner)  # belongs to `owner`
        env["state"]["user"] = attacker  # caller is someone else
        resp = _post(env, run_id, [("files", ("a.txt", b"hi", "text/plain"))])
        assert resp.status_code == 404
        assert resp.status_code != 403

    def test_missing_run_is_404(self, env):
        user = _seed_user(env, "u")
        env["state"]["user"] = user
        resp = _post(env, str(uuid.uuid4()),
                     [("files", ("a.txt", b"hi", "text/plain"))])
        assert resp.status_code == 404

    def test_store_denied_run_is_404_not_403(self, env):
        """Layer-1 passes (user_id matches) but Layer-2 default-deny denies
        (owner_id differs) → 404, proving the two-layer boundary."""
        user = _seed_user(env, "u")
        # user_id == caller (Layer 1 passes) but owner_id is someone else
        # (Layer 2 ScopedStore.get_run → None).
        run_id = _seed_run(env, user_id=user.id, owner_id="someone-else")
        env["state"]["user"] = user
        resp = _post(env, run_id, [("files", ("a.txt", b"hi", "text/plain"))])
        assert resp.status_code == 404
        assert resp.status_code != 403


# ════════════════════════════════════════════════════════════════════════════
# Caps (T-30-02/04) — rejected BEFORE any sandbox write
# ════════════════════════════════════════════════════════════════════════════


class TestCaps:
    def test_oversize_file_is_413_and_no_write(self, env, monkeypatch):
        user = _seed_user(env, "u")
        run_id = _owned_run(env, user)
        env["state"]["user"] = user
        monkeypatch.setattr(env["rf"], "_MAX_FILE_BYTES", 4)
        resp = _post(env, run_id, [("files", ("big.txt", b"way too big", "text/plain"))])
        assert resp.status_code == 413
        assert not (_sandbox(env, user.id, run_id).path_for(".uploads")).exists()

    def test_disallowed_ext_is_415(self, env):
        user = _seed_user(env, "u")
        run_id = _owned_run(env, user)
        env["state"]["user"] = user
        resp = _post(env, run_id,
                     [("files", ("evil.exe", b"MZ", "application/octet-stream"))])
        assert resp.status_code == 415

    def test_image_mime_is_415(self, env):
        user = _seed_user(env, "u")
        run_id = _owned_run(env, user)
        env["state"]["user"] = user
        # An image ext is off the allow-list; even a spoofed allowed-looking name
        # with an image mime is rejected (documents-only, 30-03).
        resp = _post(env, run_id, [("files", ("pic.png", b"\x89PNG", "image/png"))])
        assert resp.status_code == 415

    def test_over_count_is_413_and_no_write(self, env):
        user = _seed_user(env, "u")
        run_id = _owned_run(env, user)
        env["state"]["user"] = user
        files = [("files", (f"f{i}.txt", b"x", "text/plain")) for i in range(21)]
        resp = _post(env, run_id, files)
        assert resp.status_code == 413
        assert not (_sandbox(env, user.id, run_id).path_for(".uploads")).exists()

    def test_over_aggregate_is_413_and_no_write(self, env, monkeypatch):
        user = _seed_user(env, "u")
        run_id = _owned_run(env, user)
        env["state"]["user"] = user
        monkeypatch.setattr(env["rf"], "_MAX_AGGREGATE_BYTES", 6)
        files = [
            ("files", ("a.txt", b"aaaa", "text/plain")),
            ("files", ("b.txt", b"bbbb", "text/plain")),
        ]
        resp = _post(env, run_id, files)
        assert resp.status_code == 413
        assert not (_sandbox(env, user.id, run_id).path_for(".uploads")).exists()


# ════════════════════════════════════════════════════════════════════════════
# Sandbox landing — raw bytes + extracted sidecar + manifest
# ════════════════════════════════════════════════════════════════════════════


class TestSandboxLanding:
    def test_extractable_doc_lands_raw_plus_sidecar_plus_manifest(self, env, monkeypatch):
        import json

        user = _seed_user(env, "u")
        run_id = _owned_run(env, user)
        env["state"]["user"] = user
        # Monkeypatch the shared extractor so we need no real pdf binary.
        monkeypatch.setattr(env["rf"], "extract_upload_text",
                            lambda name, data: "EXTRACTED DOC TEXT")
        resp = _post(env, run_id, [("files", ("report.pdf", b"%PDF-bytes", "application/pdf"))])
        assert resp.status_code == 200
        body = resp.json()
        assert body["run_id"] == run_id
        assert body["files"][0]["name"] == "report.pdf"
        assert body["files"][0]["extracted_chars"] == len("EXTRACTED DOC TEXT")

        sb = _sandbox(env, user.id, run_id)
        assert sb.path_for(".uploads/report.pdf").read_bytes() == b"%PDF-bytes"
        assert sb.path_for(".uploads/report.pdf.txt").read_text() == "EXTRACTED DOC TEXT"
        manifest = json.loads(sb.path_for(".uploads/manifest.json").read_text())
        entry = next(e for e in manifest if e["name"] == "report.pdf")
        assert entry["has_text"] is True
        assert entry["mime"] == "application/pdf"

    def test_txt_upload_lands_raw_has_text_false(self, env):
        import json

        user = _seed_user(env, "u")
        run_id = _owned_run(env, user)
        env["state"]["user"] = user
        resp = _post(env, run_id, [("files", ("notes.txt", b"plain notes", "text/plain"))])
        assert resp.status_code == 200
        sb = _sandbox(env, user.id, run_id)
        assert sb.path_for(".uploads/notes.txt").read_bytes() == b"plain notes"
        # No extracted sidecar for a non-extractable type.
        assert not sb.path_for(".uploads/notes.txt.txt").exists()
        manifest = json.loads(sb.path_for(".uploads/manifest.json").read_text())
        entry = next(e for e in manifest if e["name"] == "notes.txt")
        assert entry["has_text"] is False


# ════════════════════════════════════════════════════════════════════════════
# Filename-collision disambiguation (WR-01) — no silent overwrite
# ════════════════════════════════════════════════════════════════════════════


class TestFilenameCollision:
    def test_within_batch_collision_is_disambiguated_not_overwritten(self, env):
        import json

        user = _seed_user(env, "u")
        run_id = _owned_run(env, user)
        env["state"]["user"] = user
        # Two DISTINCT originals that sanitize to the SAME safe segment.
        resp = _post(env, run_id, [
            ("files", ("invoice#1.txt", b"FIRST FILE CONTENTS", "text/plain")),
            ("files", ("invoice@1.txt", b"SECOND FILE CONTENTS", "text/plain")),
        ])
        assert resp.status_code == 200, resp.text
        names = [f["name"] for f in resp.json()["files"]]
        # Distinct stored names, reported ACTUAL — first keeps bare, second gets -2.
        assert names == ["invoice_1.txt", "invoice_1-2.txt"]
        assert len(set(names)) == 2
        sb = _sandbox(env, user.id, run_id)
        # BOTH files' bytes survive on disk (no silent clobber).
        assert sb.path_for(".uploads/invoice_1.txt").read_bytes() == b"FIRST FILE CONTENTS"
        assert sb.path_for(".uploads/invoice_1-2.txt").read_bytes() == b"SECOND FILE CONTENTS"
        manifest = json.loads(sb.path_for(".uploads/manifest.json").read_text())
        assert {e["name"] for e in manifest} == {"invoice_1.txt", "invoice_1-2.txt"}

    def test_collision_with_prior_upload_is_disambiguated(self, env):
        import json

        user = _seed_user(env, "u")
        run_id = _owned_run(env, user)
        env["state"]["user"] = user
        r1 = _post(env, run_id, [("files", ("report.txt", b"ORIGINAL", "text/plain"))])
        assert r1.status_code == 200
        # A later request re-using the same name must not clobber the first upload.
        r2 = _post(env, run_id, [("files", ("report.txt", b"SECOND UPLOAD", "text/plain"))])
        assert r2.status_code == 200
        assert r2.json()["files"][0]["name"] == "report-2.txt"
        sb = _sandbox(env, user.id, run_id)
        assert sb.path_for(".uploads/report.txt").read_bytes() == b"ORIGINAL"
        assert sb.path_for(".uploads/report-2.txt").read_bytes() == b"SECOND UPLOAD"
        manifest = json.loads(sb.path_for(".uploads/manifest.json").read_text())
        assert {e["name"] for e in manifest} == {"report.txt", "report-2.txt"}


# ════════════════════════════════════════════════════════════════════════════
# Manifest read-merge-write serialization (WR-02)
# ════════════════════════════════════════════════════════════════════════════


class TestManifestLockSerialization:
    def test_manifest_lock_is_mutually_exclusive(self, env):
        """The per-run advisory lock is genuinely exclusive: while held, a second
        acquirer cannot take it; once released, it is free again."""
        import fcntl
        import os as _os

        user = _seed_user(env, "u")
        run_id = _owned_run(env, user)
        sb = _sandbox(env, user.id, run_id)
        sb.ensure()
        rf = env["rf"]
        lock_path = str(sb.path_for(".uploads/manifest.lock"))

        with rf._manifest_lock(sb):
            fd2 = _os.open(lock_path, _os.O_CREAT | _os.O_RDWR, 0o600)
            try:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(fd2, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                _os.close(fd2)

        # Released → a fresh non-blocking acquire must now succeed.
        fd3 = _os.open(lock_path, _os.O_CREAT | _os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd3, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd3, fcntl.LOCK_UN)
        finally:
            _os.close(fd3)

    def test_upload_acquires_the_lock_and_manifest_lands(self, env):
        """The endpoint path runs the manifest write under the lock (its lock file
        exists) and the manifest still lands correctly."""
        import json

        user = _seed_user(env, "u")
        run_id = _owned_run(env, user)
        env["state"]["user"] = user
        resp = _post(env, run_id, [("files", ("a.txt", b"hi", "text/plain"))])
        assert resp.status_code == 200
        sb = _sandbox(env, user.id, run_id)
        assert sb.path_for(".uploads/manifest.lock").exists()
        manifest = json.loads(sb.path_for(".uploads/manifest.json").read_text())
        assert [e["name"] for e in manifest] == ["a.txt"]


# ════════════════════════════════════════════════════════════════════════════
# Streaming per-file size cap (WR-03) — reject before buffering the whole part
# ════════════════════════════════════════════════════════════════════════════


class TestStreamingSizeCap:
    def test_oversize_file_rejected_413_across_chunks_no_write(self, env, monkeypatch):
        """An over-cap part is rejected with 413 (streamed in small chunks) and nothing
        lands on disk."""
        user = _seed_user(env, "u")
        run_id = _owned_run(env, user)
        env["state"]["user"] = user
        monkeypatch.setattr(env["rf"], "_MAX_FILE_BYTES", 4)
        monkeypatch.setattr(env["rf"], "_UPLOAD_CHUNK", 2)  # force the multi-chunk path
        resp = _post(env, run_id, [("files", ("big.txt", b"way too big", "text/plain"))])
        assert resp.status_code == 413
        assert not (_sandbox(env, user.id, run_id).path_for(".uploads")).exists()

    def test_read_capped_aborts_without_reading_the_whole_part(self, env, monkeypatch):
        """The core WR-03 property: an over-cap part is NOT fully buffered — the read
        aborts after crossing the limit instead of materializing the entire body."""
        import asyncio
        import io

        rf = env["rf"]
        monkeypatch.setattr(rf, "_UPLOAD_CHUNK", 2)

        class _CountingUpload:
            def __init__(self, data: bytes):
                self._buf = io.BytesIO(data)
                self.read_bytes = 0

            async def read(self, size: int = -1) -> bytes:
                chunk = self._buf.read(size)
                self.read_bytes += len(chunk)
                return chunk

        big = _CountingUpload(b"x" * (1024 * 1024))  # 1 MB part, 4-byte cap
        out = asyncio.get_event_loop().run_until_complete(rf._read_capped(big, 4))
        assert out is None
        assert big.read_bytes <= 6  # aborted after crossing the cap, NOT ~1 MB

    def test_read_capped_returns_full_bytes_under_limit(self, env):
        import asyncio
        import io

        rf = env["rf"]

        class _Upload:
            def __init__(self, data: bytes):
                self._buf = io.BytesIO(data)

            async def read(self, size: int = -1) -> bytes:
                return self._buf.read(size)

        out = asyncio.get_event_loop().run_until_complete(
            rf._read_capped(_Upload(b"hello"), 1024)
        )
        assert out == b"hello"


# ════════════════════════════════════════════════════════════════════════════
# Deliverable exclusion (T-30-05 / INV-3)
# ════════════════════════════════════════════════════════════════════════════


class TestDeliverableExclusion:
    def test_uploads_invisible_to_deliverable(self, env):
        from app.agents.sandbox import serialize_sandbox_deliverable

        user = _seed_user(env, "u")
        run_id = _owned_run(env, user)
        env["state"]["user"] = user

        sb = _sandbox(env, user.id, run_id)
        sb.ensure()
        # A genuine deliverable file the walk MUST see.
        sb.write("index.html", "<html>deliverable</html>")
        before = serialize_sandbox_deliverable(sb.root)

        # Upload documents into .uploads/ — must NOT change the deliverable string.
        resp = _post(env, run_id, [("files", ("doc.txt", b"upload body", "text/plain"))])
        assert resp.status_code == 200
        after = serialize_sandbox_deliverable(sb.root)

        assert after == before
        assert ".uploads" not in after
        assert "doc.txt" not in after


# ════════════════════════════════════════════════════════════════════════════
# Single-impl guard (INV-12) — extract_upload_text == the endpoint's extraction
# ════════════════════════════════════════════════════════════════════════════


class TestSingleExtractionImpl:
    def test_non_extractable_ext_returns_empty(self):
        from app.api.file_extract import extract_upload_text

        assert extract_upload_text("x.txt", b"anything") == ""
        assert extract_upload_text("noext", b"anything") == ""

    def test_extract_text_endpoint_uses_the_shared_impl(self, env, monkeypatch):
        """The /extract-text endpoint returns exactly what extract_upload_text
        returns for the same bytes — proving ONE extraction impl (INV-12)."""
        from app.api import file_extract as fe
        from app.api.file_extract import extract_upload_text

        user = _seed_user(env, "u")
        env["state"]["user"] = user
        # Route the shared pdf extractor to a sentinel so no real binary is needed;
        # both the endpoint and the helper dispatch through it.
        monkeypatch.setattr(fe, "_extract_pdf", lambda data: "SHARED-IMPL-TEXT")

        helper_out = extract_upload_text("a.pdf", b"%PDF")
        resp = env["client"].post(
            "/api/files/extract-text",
            files={"file": ("a.pdf", b"%PDF", "application/pdf")},
        )
        assert resp.status_code == 200
        assert resp.json()["text"] == helper_out == "SHARED-IMPL-TEXT"
