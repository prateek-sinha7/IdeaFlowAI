"""REST tests for the `run_pipeline` image-input ingress (Wave 2; 44-08 cutover).

Originally drove the REAL WS ``_handle_workflow_execution`` (fake websocket) AND
the REST launch endpoint. After the ``/ws/chat`` retirement (44-07) the WS driver
is gone, so the WS half is DELETED and the coverage is carried entirely over the
REST launch endpoint (``app/api/run_commands.py::launch_run``), which reuses the
read-only ``_validate_images`` import identically. Pins:

  (a) a valid `images` list reaches `engine.execute(images=[...])` verbatim —
      proven at the driver seam (deterministic, no task-timing race);
  (b) the persisted `WorkflowRun.input` is the text brief only — NO base64
      substring anywhere in `input` / `title` (Phase 25 D3);
  (c) with `IMAGE_INPUT_ENABLED=False` the run still mints (clean off-switch —
      images ignored, not rejected);
  (d) a rejecting image set (bad mime OR a non-vision effective model) denies
      pre-mint (400 `invalid_image_input`, NO WorkflowRun).

Offline — no Bedrock, no network. The DB/engine harness (`ws_env`) is shared with
the REST TestClient env (`rest_env`).
"""

from __future__ import annotations

import base64
import uuid

import pytest

import agents.execution_engine.engine as engine_mod

# The base64 payload used across the valid-image tests. A short, obviously-image
# marker so the D3 "no base64 in run.input" assertion has a concrete needle.
_IMG_B64 = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode("ascii")


class _RecordingEngine:
    """Stub engine recording the execute() kwargs (incl. images)."""

    last_kwargs: dict | None = None
    invoked = False

    async def execute(self, **kwargs):
        _RecordingEngine.invoked = True
        _RecordingEngine.last_kwargs = kwargs
        yield {"type": "pipeline_start", "data": {"agents": []}}
        yield {"type": "pipeline_complete", "data": {"final_output": "done"}}


@pytest.fixture
def ws_env(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    # W4a (44-03): _get_db relocated to app.api.run_engine (INV-12 extract-before
    # -delete). Patch the seam at its new home; the REST endpoints bind their own
    # _get_db ref from run_engine, patched on rc_module in rest_env below.
    from app.api import run_engine as ws_module
    from app.models.database import Base

    db_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    Base.metadata.create_all(bind=db_engine)
    monkeypatch.setattr(ws_module, "_get_db", lambda: TestingSession())

    _RecordingEngine.invoked = False
    _RecordingEngine.last_kwargs = None
    monkeypatch.setattr(
        engine_mod, "get_execution_engine", lambda: _RecordingEngine()
    )

    yield ws_module, TestingSession

    Base.metadata.drop_all(bind=db_engine)
    db_engine.dispose()


def _valid_images() -> list[dict]:
    return [{"name": "shot.png", "mime_type": "image/png", "data": _IMG_B64}]


def _latest_run(TestingSession):
    from app.models.workflow import WorkflowRun

    db = TestingSession()
    try:
        return db.query(WorkflowRun).order_by(WorkflowRun.created_at.desc()).first()
    finally:
        db.close()


# ═════════════════════════════════════════════════════════════════════════════
# REST launch image ingress (29-04) — the image caps enforced on POST /api/runs.
#
# A rejecting set denies pre-mint (400, NO WorkflowRun); the driver-level "images
# reach execute verbatim" is proven by driving `_drive_launch_to_queue` directly
# (deterministic — no task-timing race).
# ═════════════════════════════════════════════════════════════════════════════


class _FakeUser:
    def __init__(self, id: str, tier: str = "enterprise"):
        self.id = id
        self.preferred_model = None
        self.tier = tier


@pytest.fixture
def rest_env(ws_env, monkeypatch):
    """A TestClient over the run_commands router sharing ws_env's in-memory DB +
    recording engine (patches ``run_commands._get_db``, which binds its own ref)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    ws_module, TestingSession = ws_env
    import app.api.run_commands as rc_module

    monkeypatch.setattr(rc_module, "_get_db", lambda: TestingSession())

    from app.api.run_commands import router
    from app.core.dependencies import get_current_user

    app = FastAPI()
    app.include_router(router)
    state: dict = {"user": None}
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    client = TestClient(app)
    return {"client": client, "state": state, "Session": TestingSession, "rc": rc_module}


def _rest_user(rest_env) -> _FakeUser:
    return _FakeUser(id=str(uuid.uuid4()))


def _rest_run_count(rest_env) -> int:
    from app.models.workflow import WorkflowRun

    db = rest_env["Session"]()
    try:
        return db.query(WorkflowRun).count()
    finally:
        db.close()


def _post_launch(rest_env, user, **body):
    rest_env["state"]["user"] = user
    return rest_env["client"].post(
        "/api/runs", json={"message": "build a backlog", "pipeline_type": "user_stories", **body}
    )


@pytest.mark.asyncio
async def test_rest_bad_mime_rejected_pre_mint(rest_env):
    """(d)/REST: a bad-mime image set denies with 400 invalid_image_input and NO
    WorkflowRun is minted (rejected pre-mint, mirrors the WS error path)."""
    user = _rest_user(rest_env)
    bad = [{"name": "e.svg", "mime_type": "image/svg+xml", "data": _IMG_B64}]
    resp = _post_launch(rest_env, user, images=bad)
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "invalid_image_input"
    assert _rest_run_count(rest_env) == 0


@pytest.mark.asyncio
async def test_rest_non_vision_model_rejected_pre_mint(rest_env):
    """(d)/REST: a non-vision effective run model denies pre-mint (escape hatch)."""
    user = _rest_user(rest_env)
    user.preferred_model = "raw.escape/non-catalog-model:latest"
    resp = _post_launch(rest_env, user, images=_valid_images())
    assert resp.status_code == 400
    data = resp.json()["detail"]
    assert data["code"] == "invalid_image_input"
    assert "vision" in data["error"]
    assert _rest_run_count(rest_env) == 0


@pytest.mark.asyncio
async def test_rest_flag_off_accepts_images(rest_env, monkeypatch):
    """(c)/REST: flag OFF → images ignored (not rejected); the run still mints."""
    from app.core.config import settings as _settings

    monkeypatch.setattr(_settings, "IMAGE_INPUT_ENABLED", False)
    user = _rest_user(rest_env)
    resp = _post_launch(rest_env, user, images=_valid_images())
    assert resp.status_code == 200, resp.text
    assert _rest_run_count(rest_env) == 1


@pytest.mark.asyncio
async def test_rest_valid_images_reach_execute_via_driver(rest_env):
    """(a)/REST: a valid image set reaches ``engine.execute(images=[...])`` verbatim
    — proven at the driver seam (deterministic)."""
    user = _rest_user(rest_env)
    images = _valid_images()
    queue = __import__("asyncio").Queue()
    await rest_env["rc"]._drive_launch_to_queue(
        workflow_run_id=None,  # no row finalize — we only assert the execute kwargs
        pipeline_run_id=str(uuid.uuid4()),
        agents=[object()],
        content="build a backlog",
        pipeline_type="user_stories",
        cancel_event=__import__("asyncio").Event(),
        user=user,
        attached_skills=[],
        attached_hooks=[],
        od_context=None,
        validated_images=images,
        gate_agent_ids=None,
        parent_run_id=None,
        model_overrides={},
        selections=None,
        event_queue=queue,
    )
    assert _RecordingEngine.invoked is True
    assert _RecordingEngine.last_kwargs.get("images") == images


@pytest.mark.asyncio
async def test_rest_d3_no_base64_in_run_input(rest_env):
    """(b)/REST D3: a valid image launch persists the text brief only — the base64
    image bytes must NEVER leak into ``WorkflowRun.input`` / ``title`` (Phase 25 D3).
    Migrated from the deleted WS ``test_d3_no_base64_in_run_input``."""
    user = _rest_user(rest_env)
    brief = "build a backlog for a mobile banking app"
    rest_env["state"]["user"] = user
    resp = rest_env["client"].post(
        "/api/runs",
        json={"message": brief, "pipeline_type": "user_stories",
              "images": _valid_images()},
    )
    assert resp.status_code == 200, resp.text
    run = _latest_run(rest_env["Session"])
    assert run is not None
    assert run.input == brief
    assert _IMG_B64 not in (run.input or "")
    assert _IMG_B64 not in (run.title or "")
