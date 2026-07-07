"""Integration tests for the `run_pipeline` image-input ingress (Wave 2).

Drives the REAL `_handle_workflow_execution` through the offline WS harness
(fake websocket, recording stub engine, in-memory SQLite) and pins:

  (a) a valid `images` list reaches `engine.execute(images=[...])` verbatim;
  (b) the persisted `WorkflowRun.input` is the text brief only — NO base64
      substring anywhere in `input` / `title` (Phase 25 D3);
  (c) with `IMAGE_INPUT_ENABLED=False` the recorded execute kwargs carry
      `images=[]` (clean off-switch — images ignored, run still proceeds);
  (d) a rejecting image set (bad mime OR a non-vision effective model) emits an
      `invalid_image_input` error event and NEVER calls `engine.execute`.

Offline — no Bedrock, no network. Mirrors the harness in
`tests/unit/test_pipeline_failure_semantics.py`.
"""

from __future__ import annotations

import base64
import uuid

import pytest

import agents.execution_engine.engine as engine_mod

# The base64 payload used across the valid-image tests. A short, obviously-image
# marker so the D3 "no base64 in run.input" assertion has a concrete needle.
_IMG_B64 = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode("ascii")


class _FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


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

    from app.api import websocket as ws_module
    from app.models.database import Base

    db_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    Base.metadata.create_all(bind=db_engine)
    monkeypatch.setattr(ws_module, "_get_db", lambda: TestingSession())

    async def _noop_title(**kwargs):
        return None

    monkeypatch.setattr(ws_module, "_generate_workflow_title", _noop_title)

    _RecordingEngine.invoked = False
    _RecordingEngine.last_kwargs = None
    monkeypatch.setattr(
        engine_mod, "get_execution_engine", lambda: _RecordingEngine()
    )

    yield ws_module, TestingSession

    Base.metadata.drop_all(bind=db_engine)
    db_engine.dispose()


@pytest.fixture
def ws_user(ws_env):
    from app.models.user import User

    _ws_module, TestingSession = ws_env
    db = TestingSession()
    try:
        u = User(
            id=str(uuid.uuid4()),
            email=f"img-{uuid.uuid4().hex[:8]}@example.com",
            password_hash="x",
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u
    finally:
        db.close()


def _valid_images() -> list[dict]:
    return [{"name": "shot.png", "mime_type": "image/png", "data": _IMG_B64}]


def _image_errors(ws) -> list[dict]:
    return [
        m for m in ws.sent
        if m.get("type") == "error"
        and m.get("data", {}).get("code") == "invalid_image_input"
    ]


def _latest_run(TestingSession):
    from app.models.workflow import WorkflowRun

    db = TestingSession()
    try:
        return db.query(WorkflowRun).order_by(WorkflowRun.created_at.desc()).first()
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# (a) valid images reach engine.execute(images=[...])
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_valid_images_reach_execute(ws_env, ws_user):
    ws_module, _ = ws_env
    ws = _FakeWebSocket()
    images = _valid_images()
    await ws_module._handle_workflow_execution(
        ws, "build a backlog", "user_stories",
        chat_session_id=None, token="t", user=ws_user,
        images=images,
    )
    assert _RecordingEngine.invoked is True
    assert _image_errors(ws) == [], f"unexpected rejection: {ws.sent}"
    assert _RecordingEngine.last_kwargs is not None
    assert _RecordingEngine.last_kwargs.get("images") == images


# ─────────────────────────────────────────────────────────────────────────────
# (b) D3 — WorkflowRun.input is the brief only; NO base64 in input/title
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_d3_no_base64_in_run_input(ws_env, ws_user):
    ws_module, TestingSession = ws_env
    ws = _FakeWebSocket()
    brief = "build a backlog for a mobile banking app"
    await ws_module._handle_workflow_execution(
        ws, brief, "user_stories",
        chat_session_id=None, token="t", user=ws_user,
        images=_valid_images(),
    )
    run = _latest_run(TestingSession)
    assert run is not None
    assert run.input == brief
    # The base64 image bytes must NEVER leak into the persisted run text (D3).
    assert _IMG_B64 not in (run.input or "")
    assert _IMG_B64 not in (run.title or "")


# ─────────────────────────────────────────────────────────────────────────────
# (c) flag OFF → execute receives images=[]
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_flag_off_ignores_images(ws_env, ws_user, monkeypatch):
    ws_module, _ = ws_env
    monkeypatch.setattr(ws_module.settings, "IMAGE_INPUT_ENABLED", False)
    ws = _FakeWebSocket()
    await ws_module._handle_workflow_execution(
        ws, "build a backlog", "user_stories",
        chat_session_id=None, token="t", user=ws_user,
        images=_valid_images(),
    )
    assert _RecordingEngine.invoked is True
    assert _image_errors(ws) == [], "flag-off must not reject — just ignore"
    assert _RecordingEngine.last_kwargs.get("images") == []


@pytest.mark.asyncio
async def test_no_images_run_passes_empty_list(ws_env, ws_user):
    ws_module, _ = ws_env
    ws = _FakeWebSocket()
    await ws_module._handle_workflow_execution(
        ws, "build a backlog", "user_stories",
        chat_session_id=None, token="t", user=ws_user,
    )
    assert _RecordingEngine.invoked is True
    assert _RecordingEngine.last_kwargs.get("images") == []


# ─────────────────────────────────────────────────────────────────────────────
# (d) rejecting set → invalid_image_input, execute NEVER called
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bad_mime_rejected_no_execute(ws_env, ws_user):
    ws_module, _ = ws_env
    ws = _FakeWebSocket()
    bad = [{"name": "e.svg", "mime_type": "image/svg+xml", "data": _IMG_B64}]
    await ws_module._handle_workflow_execution(
        ws, "build a backlog", "user_stories",
        chat_session_id=None, token="t", user=ws_user,
        images=bad,
    )
    errors = _image_errors(ws)
    assert len(errors) == 1, f"expected one invalid_image_input: {ws.sent}"
    assert errors[0]["data"]["recoverable"] is False
    assert _RecordingEngine.invoked is False


@pytest.mark.asyncio
async def test_non_vision_model_rejected_no_execute(ws_env, ws_user, monkeypatch):
    ws_module, _ = ws_env
    # Force a raw, non-catalog effective run-level model (escape-hatch attempt).
    monkeypatch.setattr(
        ws_user, "preferred_model", "raw.escape/non-catalog-model:latest",
        raising=False,
    )
    ws = _FakeWebSocket()
    await ws_module._handle_workflow_execution(
        ws, "build a backlog", "user_stories",
        chat_session_id=None, token="t", user=ws_user,
        images=_valid_images(),
    )
    errors = _image_errors(ws)
    assert len(errors) == 1, f"expected vision-guard rejection: {ws.sent}"
    assert "vision" in errors[0]["data"]["error"]
    assert _RecordingEngine.invoked is False
