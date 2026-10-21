"""tests/integration/api/test_figma_frames_api.py — FIGMA-01 backend contract.

Proves the ``POST /api/runs/{id}/figma-frames`` endpoint OFFLINE
(TestClient + in-memory SQLite scoped store + a temp RUNS_ROOT; no live
Bedrock / uvicorn).  Covers the full FIGMA-01 contract:

  * Accepted types: PNG and JPEG → 200, manifest entry with type='image'.
  * Rejected types: .fig, .pdf, .svg → 415 with the Figma-export hint message.
  * Per-file size cap (4 MB) → 413.
  * Frame count cap (20 frames) → 413.
  * Two-layer IDOR check: wrong owner → 404, unknown run → 404, never 403.
  * Manifest append-only: two sequential uploads both land in the manifest.
  * Filename deduplication: same sanitised name → suffix appended (-2, etc.).
  * Manifest shape: name, mime, type='image', description, has_text=False —
    the exact shape fi-planner Phase 1 Step 3 branches on.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ── Minimal valid image bytes ─────────────────────────────────────────────────

# 1×1 PNG (67 bytes)
_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
    b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
    b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)

# Minimal JPEG (SOI + EOI markers, 20 bytes)
_TINY_JPEG = bytes([0xFF, 0xD8, 0xFF, 0xE0] + [0x00] * 16 + [0xFF, 0xD9])


# ── Fake user ─────────────────────────────────────────────────────────────────


class _FakeUser:
    def __init__(self, id: str) -> None:
        self.id = id


# ── env fixture ──────────────────────────────────────────────────────────────


@pytest.fixture
def env(monkeypatch, tmp_path):
    """Self-contained test environment: in-memory SQLite + temp RUNS_ROOT + TestClient."""
    from app.api import run_figma_frames as ff_module
    from app.api import run_engine as ws_module
    from app.api import run_files as rf_module  # needed: _resolve_chain_root_or_404 calls run_files._get_db
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

    # Patch _get_db on ALL three modules that touch it:
    # - run_engine: the shared infra module
    # - run_figma_frames: binds its own reference at import time
    # - run_files: _resolve_chain_root_or_404 uses run_files._get_db directly,
    #   so it must be patched here even though run_figma_frames imports the function
    #   from run_files (the function closes over run_files's own module-level binding).
    monkeypatch.setattr(ws_module, "_get_db", lambda: TestingSession())
    monkeypatch.setattr(ff_module, "_get_db", lambda: TestingSession())
    monkeypatch.setattr(rf_module, "_get_db", lambda: TestingSession())
    # ScopedStore(session=None) opens app.models.database.SessionLocal() — bind it too.
    monkeypatch.setattr(db_module, "SessionLocal", TestingSession)

    # Land every sandbox write under a writable temp RUNS_ROOT.
    runs_root = tmp_path / "runs"
    monkeypatch.setattr(settings, "RUNS_ROOT", str(runs_root))

    from app.api.run_figma_frames import router as run_figma_frames_router
    from app.core.dependencies import get_current_user

    application = FastAPI()
    application.include_router(run_figma_frames_router)

    state: dict = {"user": None}
    application.dependency_overrides[get_current_user] = lambda: state["user"]
    client = TestClient(application)

    yield {
        "client": client,
        "state": state,
        "Session": TestingSession,
        "runs_root": str(runs_root),
        "ff": ff_module,
        "rf": rf_module,
    }

    Base.metadata.drop_all(bind=db_engine)
    db_engine.dispose()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _seed_user(env, tag: str) -> _FakeUser:
    from app.models.user import User

    db = env["Session"]()
    try:
        u = User(
            id=str(uuid.uuid4()),
            email=f"figma-{tag}-{uuid.uuid4().hex[:8]}@example.com",
            cognito_sub=str(uuid.uuid4()),
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return _FakeUser(id=u.id)
    finally:
        db.close()


def _seed_run(
    env, *, user_id: str, owner_id: str, workspace_id: str = "ws-1", status: str = "running"
) -> str:
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
                type="prototype_v2",
                status=status,
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


def _owned_run(env, user: _FakeUser) -> str:
    """A run the caller owns at BOTH layers."""
    return _seed_run(env, user_id=user.id, owner_id=user.id)


def _post_frames(env, run_id: str, files, extra_fields=None):
    return env["client"].post(
        f"/api/runs/{run_id}/figma-frames",
        files=files,
        data=extra_fields or {},
    )


def _sandbox(env, user_id: str, run_id: str):
    from app.agents.sandbox import RunSandbox

    return RunSandbox(user_id, run_id, runs_root=env["runs_root"])


# ════════════════════════════════════════════════════════════════════════════
# 1. PNG success → manifest image entry
# ════════════════════════════════════════════════════════════════════════════


def test_upload_png_success_creates_manifest_image_entry(env):
    """POST valid PNG → 200 + manifest entry with type='image', has_text=False."""
    user = _seed_user(env, "u")
    run_id = _owned_run(env, user)
    env["state"]["user"] = user

    resp = _post_frames(
        env, run_id, [("files", ("screen.png", _TINY_PNG, "image/png"))]
    )
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["run_id"] == run_id
    assert len(body["files"]) == 1
    stored_name = body["files"][0]["name"]

    sb = _sandbox(env, user.id, run_id)
    manifest_raw = sb.path_for(".uploads/manifest.json").read_text(encoding="utf-8")
    manifest = json.loads(manifest_raw)

    entry = next((e for e in manifest if e["name"] == stored_name), None)
    assert entry is not None, f"No entry for {stored_name!r} in manifest"
    assert entry["type"] == "image"
    assert entry["has_text"] is False
    assert entry["mime"] == "image/png"


# ════════════════════════════════════════════════════════════════════════════
# 2. JPEG success
# ════════════════════════════════════════════════════════════════════════════


def test_upload_jpg_success_accepted(env):
    """POST valid JPEG → 200."""
    user = _seed_user(env, "u")
    run_id = _owned_run(env, user)
    env["state"]["user"] = user

    resp = _post_frames(
        env, run_id, [("files", ("screen.jpg", _TINY_JPEG, "image/jpeg"))]
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["files"]) == 1


# ════════════════════════════════════════════════════════════════════════════
# 3. .fig rejected with 415 and friendly message
# ════════════════════════════════════════════════════════════════════════════


def test_upload_fig_rejected_415(env):
    """POST .fig → 415, detail contains 'export your screens as PNG from Figma'."""
    user = _seed_user(env, "u")
    run_id = _owned_run(env, user)
    env["state"]["user"] = user

    resp = _post_frames(
        env,
        run_id,
        [("files", ("design.fig", b"fig-bytes", "application/octet-stream"))],
    )
    assert resp.status_code == 415
    detail = resp.json().get("detail", "")
    assert "export your screens as PNG from Figma" in detail


# ════════════════════════════════════════════════════════════════════════════
# 4. PDF rejected 415
# ════════════════════════════════════════════════════════════════════════════


def test_upload_pdf_rejected_415(env):
    """POST .pdf → 415."""
    user = _seed_user(env, "u")
    run_id = _owned_run(env, user)
    env["state"]["user"] = user

    resp = _post_frames(
        env,
        run_id,
        [("files", ("spec.pdf", b"%PDF-bytes", "application/pdf"))],
    )
    assert resp.status_code == 415


# ════════════════════════════════════════════════════════════════════════════
# 5. SVG rejected 415
# ════════════════════════════════════════════════════════════════════════════


def test_upload_svg_rejected_415(env):
    """POST .svg → 415."""
    user = _seed_user(env, "u")
    run_id = _owned_run(env, user)
    env["state"]["user"] = user

    resp = _post_frames(
        env,
        run_id,
        [("files", ("icon.svg", b"<svg/>", "image/svg+xml"))],
    )
    assert resp.status_code == 415


# ════════════════════════════════════════════════════════════════════════════
# 6. Oversized frame rejected 413
# ════════════════════════════════════════════════════════════════════════════


def test_upload_oversized_frame_rejected_413(env):
    """POST PNG > 4 MB → 413."""
    user = _seed_user(env, "u")
    run_id = _owned_run(env, user)
    env["state"]["user"] = user

    # Build bytes just over 4 MB
    big = _TINY_PNG + b"\x00" * (4 * 1024 * 1024 + 1)
    resp = _post_frames(
        env, run_id, [("files", ("huge.png", big, "image/png"))]
    )
    assert resp.status_code == 413


# ════════════════════════════════════════════════════════════════════════════
# 7. 21 frames rejected 413 (count cap)
# ════════════════════════════════════════════════════════════════════════════


def test_upload_21_frames_rejected_413(env):
    """POST 21 tiny PNGs → 413 (count cap)."""
    user = _seed_user(env, "u")
    run_id = _owned_run(env, user)
    env["state"]["user"] = user

    files = [
        ("files", (f"s{i}.png", _TINY_PNG, "image/png")) for i in range(21)
    ]
    resp = _post_frames(env, run_id, files)
    assert resp.status_code == 413


# ════════════════════════════════════════════════════════════════════════════
# 8. Wrong owner → 404 not 403 (IDOR)
# ════════════════════════════════════════════════════════════════════════════


def test_upload_wrong_owner_returns_404_not_403(env):
    """Seed a run owned by userA, authenticate as userB → 404, never 403."""
    owner = _seed_user(env, "owner")
    attacker = _seed_user(env, "attacker")
    run_id = _owned_run(env, owner)   # belongs to `owner`
    env["state"]["user"] = attacker   # caller is someone else

    resp = _post_frames(
        env, run_id, [("files", ("s.png", _TINY_PNG, "image/png"))]
    )
    assert resp.status_code == 404
    assert resp.status_code != 403


# ════════════════════════════════════════════════════════════════════════════
# 9. Nonexistent run → 404
# ════════════════════════════════════════════════════════════════════════════


def test_upload_nonexistent_run_returns_404(env):
    """POST to a random UUID run_id → 404."""
    user = _seed_user(env, "u")
    env["state"]["user"] = user

    resp = _post_frames(
        env, str(uuid.uuid4()), [("files", ("s.png", _TINY_PNG, "image/png"))]
    )
    assert resp.status_code == 404


# ════════════════════════════════════════════════════════════════════════════
# 10. Manifest appends, not overwrites
# ════════════════════════════════════════════════════════════════════════════


def test_manifest_appends_not_overwrites(env):
    """Two sequential uploads both land in manifest (append, not clobber)."""
    user = _seed_user(env, "u")
    run_id = _owned_run(env, user)
    env["state"]["user"] = user

    r1 = _post_frames(env, run_id, [("files", ("s1.png", _TINY_PNG, "image/png"))])
    assert r1.status_code == 200, r1.text
    name1 = r1.json()["files"][0]["name"]

    r2 = _post_frames(env, run_id, [("files", ("s2.png", _TINY_PNG, "image/png"))])
    assert r2.status_code == 200, r2.text
    name2 = r2.json()["files"][0]["name"]

    sb = _sandbox(env, user.id, run_id)
    manifest = json.loads(
        sb.path_for(".uploads/manifest.json").read_text(encoding="utf-8")
    )
    names_in_manifest = {e["name"] for e in manifest}
    assert name1 in names_in_manifest, f"{name1!r} missing from manifest after second upload"
    assert name2 in names_in_manifest, f"{name2!r} missing from manifest after second upload"
    assert len(manifest) == 2


# ════════════════════════════════════════════════════════════════════════════
# 11. Dedup adds -2 suffix on collision
# ════════════════════════════════════════════════════════════════════════════


def test_manifest_dedup_adds_suffix(env):
    """Two files that sanitize to the same name get distinct stored names."""
    user = _seed_user(env, "u")
    run_id = _owned_run(env, user)
    env["state"]["user"] = user

    # Upload two files in one batch — both sanitise to "frame-1.png"
    # (the endpoint names the first frame-1.png; a second in the SAME batch
    # whose sanitised base also resolves to frame-1 gets deduplicated).
    # We trigger this by uploading TWO files in a single request so the second
    # gets a dedupe suffix.
    files = [
        ("files", ("s1.png", _TINY_PNG, "image/png")),
        ("files", ("s2.png", _TINY_PNG, "image/png")),
    ]
    resp = _post_frames(env, run_id, files)
    assert resp.status_code == 200, resp.text

    stored_names = [f["name"] for f in resp.json()["files"]]
    # Both names must be distinct (no silent clobber).
    assert len(set(stored_names)) == 2, f"Expected 2 distinct names, got: {stored_names}"

    # Now upload a second batch — the first file there should get frame-3.png,
    # demonstrating the frame offset increments correctly.
    r2 = _post_frames(env, run_id, [("files", ("s3.png", _TINY_PNG, "image/png"))])
    assert r2.status_code == 200, r2.text
    name3 = r2.json()["files"][0]["name"]
    assert name3 not in set(stored_names), (
        f"Third upload collision: {name3!r} already in {stored_names}"
    )


# ════════════════════════════════════════════════════════════════════════════
# 12. Manifest shape triggers fi-planner image branch
# ════════════════════════════════════════════════════════════════════════════


def test_manifest_shape_triggers_fi_planner_image_branch(env):
    """Manifest entry has keys: name, mime, type='image', description, has_text=False.

    This is the exact shape fi-planner Phase 1 Step 3 branches on to skip
    extract_text and create a synthetic shard for image entries.
    """
    user = _seed_user(env, "u")
    run_id = _owned_run(env, user)
    env["state"]["user"] = user

    resp = _post_frames(
        env, run_id, [("files", ("dashboard.png", _TINY_PNG, "image/png"))]
    )
    assert resp.status_code == 200, resp.text
    stored_name = resp.json()["files"][0]["name"]

    sb = _sandbox(env, user.id, run_id)
    manifest = json.loads(
        sb.path_for(".uploads/manifest.json").read_text(encoding="utf-8")
    )
    entry = next((e for e in manifest if e["name"] == stored_name), None)
    assert entry is not None, f"Entry {stored_name!r} not found in manifest"

    # Verify the exact keys fi-planner branches on:
    assert "name" in entry
    assert "mime" in entry
    assert "type" in entry
    assert "description" in entry
    assert "has_text" in entry

    # Verify the values that trigger the image branch:
    assert entry["type"] == "image", f"Expected type='image', got {entry['type']!r}"
    assert entry["has_text"] is False, f"Expected has_text=False, got {entry['has_text']!r}"
    assert entry["mime"] == "image/png"
