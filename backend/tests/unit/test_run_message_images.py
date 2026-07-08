"""tests/unit/test_run_message_images.py — UPLD-02 residue (30-03): per-turn images.

Images attached to an in-flight chat turn ride the ALREADY-BUILT Phase-29
``POST /api/runs/{id}/messages`` path into the NEXT dispatch's ``HumanMessage``
content blocks — exactly where run-entry ``run_images`` already flow. Proven OFFLINE
(TestClient + in-memory SQLite scoped store; no live Bedrock / uvicorn):

  (a) a RUNNING-phase turn with a valid image → 200 + channel ``steering``; the seam
      end-to-end — ``apply_turn_images`` queues it → the engine drain moves it to
      ``ectx.run_images`` → an ``injects:[images]`` dispatch's ``_compose_input_blocks``
      carries the base64 image content-block (the ``RunImagesProvider`` shape).
  (b) an image violating the shared caps (bad mime / oversized / count / aggregate /
      non-vision) → 400 ``invalid_image_input`` from the SAME ``_validate_images`` path;
      nothing persisted, nothing queued (the endpoint is NOT rebuilt).
  (c) ND-10 / LOCK-E lock: after a turn with images, NO image bytes exist in the DB /
      run_events, and the persisted ``chat_message`` row's attachment refs are stamped
      ``retained:false`` with NO ``data`` field — images do not survive replay/reopen.
  (d) INV-3 dormancy: a turn with NO images leaves ``run_images`` empty → the drain is a
      no-op → the dispatch payload is byte-identical to the no-image baseline.

LOCK-B / additive: drives the REAL endpoint + the REAL engine seams; touches NO
production file beyond the 30-03 allow-list.
"""

from __future__ import annotations

import asyncio
import base64
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# A short, obviously-image base64 marker so the ND-10 "no base64 anywhere" assertion
# has a concrete needle (mirrors test_image_ws_ingress._IMG_B64).
_IMG_B64 = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode("ascii")


def _valid_image() -> dict:
    return {"name": "shot.png", "mime_type": "image/png", "data": _IMG_B64}


class _FakeUser:
    def __init__(self, id: str):
        self.id = id


# ════════════════════════════════════════════════════════════════════════════
# Offline endpoint harness (mirrors test_chat_messages_endpoint.env)
# ════════════════════════════════════════════════════════════════════════════
@pytest.fixture
def env(monkeypatch):
    from app.api import run_commands as rc_module
    from app.api import websocket as ws_module
    from app.models import database as db_module
    from app.models.database import Base

    db_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    Base.metadata.create_all(bind=db_engine)

    # run_commands binds its OWN _get_db reference at import — patch both modules.
    monkeypatch.setattr(ws_module, "_get_db", lambda: TestingSession())
    monkeypatch.setattr(rc_module, "_get_db", lambda: TestingSession())
    monkeypatch.setattr(db_module, "SessionLocal", TestingSession)

    import agents.artifact_store.store as store_mod
    store_mod._STORE = None
    store = store_mod.get_artifact_store()

    from app.api.run_commands import router
    from app.core.dependencies import get_current_user

    app = FastAPI()
    app.include_router(router)
    state: dict = {"user": None}
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    client = TestClient(app)

    yield {"store": store, "client": client, "state": state, "Session": TestingSession}

    Base.metadata.drop_all(bind=db_engine)
    db_engine.dispose()
    store_mod._STORE = None


def _seed_user(env, tag: str) -> _FakeUser:
    from app.models.user import User

    db = env["Session"]()
    try:
        u = User(id=str(uuid.uuid4()),
                 email=f"img30-{tag}-{uuid.uuid4().hex[:8]}@example.com",
                 password_hash="x")
        db.add(u)
        db.commit()
        db.refresh(u)
        return _FakeUser(id=u.id)
    finally:
        db.close()


def _seed_run(env, user_id: str, *, status: str = "running",
              workspace_id: str = "ws-1") -> str:
    from app.models.workflow import WorkflowRun

    run_id = str(uuid.uuid4())
    db = env["Session"]()
    try:
        db.add(WorkflowRun(
            id=run_id, user_id=user_id, owner_id=user_id, workspace_id=workspace_id,
            title="t", type="prototype", status=status, input="i",
            agent_count=1, session_id=user_id, created_at=datetime.now(timezone.utc),
        ))
        db.commit()
        return run_id
    finally:
        db.close()


def _seed_events(env, run_id, rows, *, owner_id, workspace_id="ws-1"):
    from app.models.run_event import RunEvent

    db = env["Session"]()
    try:
        for seq, etype, payload in rows:
            db.add(RunEvent(
                id=str(uuid.uuid4()), run_id=run_id, owner_id=owner_id,
                workspace_id=workspace_id, seq=seq, event_id=str(uuid.uuid4()),
                type=etype, payload_json=payload,
            ))
        db.commit()
    finally:
        db.close()


def _all_events(env, run_id):
    from app.models.run_event import RunEvent

    db = env["Session"]()
    try:
        return (
            db.query(RunEvent)
            .filter(RunEvent.run_id == run_id)
            .order_by(RunEvent.seq.asc())
            .all()
        )
    finally:
        db.close()


def _chat_rows(env, run_id):
    return [e for e in _all_events(env, run_id) if e.type == "chat_message"]


def _post(env, run_id, **body):
    body.setdefault("message_id", uuid.uuid4().hex)
    return env["client"].post(f"/api/runs/{run_id}/messages", json=body)


# ════════════════════════════════════════════════════════════════════════════
# Shared engine-seam helper: apply_turn_images → drain → _compose_input_blocks
# ════════════════════════════════════════════════════════════════════════════
def _compose_blocks_for_images(images: list) -> list:
    """Drive the REAL seam: enqueue per-turn images on a fresh ExecutionContext, run the
    engine drain, and compose the input blocks for an ``injects:[images]`` agent."""
    # Import the provider module so @register lands ``run_images`` in the registry.
    import agents.capabilities.input_providers.run_images  # noqa: F401
    from agents.execution_engine.context import ExecutionContext
    from agents.execution_engine.engine import (
        _drain_turn_images,
        get_execution_engine,
    )

    from app.api.chat_router import apply_turn_images

    ectx = ExecutionContext(run_id="r", owner_id="o")
    ectx.compiled_input_providers = ["run_images"]  # the declared capability
    apply_turn_images(ectx, images)               # router seam → pending_turn_images
    _drain_turn_images(ectx)                       # engine drain → run_images
    assert ectx.pending_turn_images == []          # consume-once
    spec = SimpleNamespace(id="prototype-specify", injects=["images"])
    engine = get_execution_engine()
    return asyncio.get_event_loop().run_until_complete(
        engine._compose_input_blocks(spec, ectx)
    ), ectx


# ════════════════════════════════════════════════════════════════════════════
# (a) delivery end-to-end — endpoint + seam + drain + provider block
# ════════════════════════════════════════════════════════════════════════════
class TestPerTurnImageDelivery:
    def test_running_turn_with_valid_image_is_accepted_and_steers(self, env):
        owner = _seed_user(env, "owner")
        run_id = _seed_run(env, owner.id, status="running")
        env["state"]["user"] = owner

        resp = _post(env, run_id, text="match this look", images=[_valid_image()],
                     message_id="m-img")
        assert resp.status_code == 200, resp.text
        assert resp.json()["channel"] == "steering"  # RUNNING → steering path
        # The turn is durably recorded (the chat_message record, ND-9).
        assert len(_chat_rows(env, run_id)) == 1

    def test_seam_drains_image_into_next_dispatch_content_block(self, env):
        blocks, ectx = _compose_blocks_for_images([_valid_image()])
        # The engine drain moved the image onto the transient run_images carrier …
        assert ectx.run_images == [{"mime_type": "image/png", "data": _IMG_B64}]
        # … and _compose_input_blocks emitted exactly the RunImagesProvider block shape.
        assert blocks == [{
            "type": "image",
            "source_type": "base64",
            "mime_type": "image/png",
            "data": _IMG_B64,
        }]

    def test_non_injecting_agent_gets_no_image_block(self, env):
        """The image only reaches an agent that declared ``injects:[images]`` — a
        non-opted agent's dispatch stays image-free (the F1 leak guard)."""
        import agents.capabilities.input_providers.run_images  # noqa: F401
        from agents.execution_engine.context import ExecutionContext
        from agents.execution_engine.engine import _drain_turn_images, get_execution_engine

        from app.api.chat_router import apply_turn_images

        ectx = ExecutionContext(run_id="r", owner_id="o")
        ectx.compiled_input_providers = ["run_images"]
        apply_turn_images(ectx, [_valid_image()])
        _drain_turn_images(ectx)
        spec = SimpleNamespace(id="plain-agent", injects=[])  # NOT opted in
        engine = get_execution_engine()
        blocks = asyncio.get_event_loop().run_until_complete(
            engine._compose_input_blocks(spec, ectx)
        )
        assert blocks == []


# ════════════════════════════════════════════════════════════════════════════
# (b) cap violation → 400, nothing persisted, nothing queued
# ════════════════════════════════════════════════════════════════════════════
class TestPerTurnImageCaps:
    def test_bad_mime_is_rejected_400_nothing_persisted(self, env):
        owner = _seed_user(env, "owner")
        run_id = _seed_run(env, owner.id, status="running")
        env["state"]["user"] = owner

        bad = {"mime_type": "image/tiff", "data": _IMG_B64}  # not in the allow-list
        resp = _post(env, run_id, text="bad pic", images=[bad], message_id="m-bad")
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_image_input"
        # Rejected BEFORE persist/queue — no chat_message row exists.
        assert _chat_rows(env, run_id) == []

    def test_too_many_images_is_rejected_400(self, env):
        owner = _seed_user(env, "owner")
        run_id = _seed_run(env, owner.id, status="running")
        env["state"]["user"] = owner

        flood = [_valid_image() for _ in range(21)]  # cap is 20
        resp = _post(env, run_id, text="flood", images=flood, message_id="m-flood")
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "invalid_image_input"
        assert _chat_rows(env, run_id) == []

    def test_flag_off_ignores_images_no_rejection(self, env, monkeypatch):
        from app.api import run_commands as rc_module

        monkeypatch.setattr(rc_module.settings, "IMAGE_INPUT_ENABLED", False)
        owner = _seed_user(env, "owner")
        run_id = _seed_run(env, owner.id, status="running")
        env["state"]["user"] = owner

        # Flag OFF → images are ignored (not validated, not rejected); the turn still
        # persists and routes normally.
        resp = _post(env, run_id, text="hi", images=[_valid_image()], message_id="m-off")
        assert resp.status_code == 200, resp.text
        assert resp.json()["channel"] == "steering"


# ════════════════════════════════════════════════════════════════════════════
# (c) ND-10 / LOCK-E — payload-transient: no bytes in DB/run_events; retained:false
# ════════════════════════════════════════════════════════════════════════════
class TestNoPersistenceLock:
    def test_image_refs_stamped_retained_false_no_bytes(self, env):
        owner = _seed_user(env, "owner")
        run_id = _seed_run(env, owner.id, status="running")
        env["state"]["user"] = owner

        resp = _post(env, run_id, text="see this", images=[_valid_image()],
                     message_id="m-nd10")
        assert resp.status_code == 200, resp.text

        row = _chat_rows(env, run_id)[0]
        refs = row.payload_json["attachments"]
        # The image is stamped as a retained:false ref with NO data/bytes field.
        assert refs == [{"kind": "image", "retained": False}]
        for ref in refs:
            assert "data" not in ref
            assert ref["retained"] is False

    def test_no_base64_bytes_anywhere_in_run_events(self, env):
        owner = _seed_user(env, "owner")
        run_id = _seed_run(env, owner.id, status="running")
        env["state"]["user"] = owner

        _post(env, run_id, text="pic", images=[_valid_image()], message_id="m-scan")
        # The base64 image payload must NEVER appear in ANY persisted run_events row —
        # images are payload-transient (no DB / run_events / sandbox retention).
        import json as _json
        for ev in _all_events(env, run_id):
            assert _IMG_B64 not in _json.dumps(ev.payload_json or {})

    def test_image_does_not_survive_replay(self, env):
        """A replayed turn (same message_id) is a no-op and never resurrects bytes —
        the durable record is a retained:false ref only (images gone on reopen)."""
        owner = _seed_user(env, "owner")
        run_id = _seed_run(env, owner.id, status="running")
        env["state"]["user"] = owner

        r1 = _post(env, run_id, text="pic", images=[_valid_image()], message_id="dup")
        r2 = _post(env, run_id, text="pic", images=[_valid_image()], message_id="dup")
        assert r1.json()["persisted"] is True and r2.json()["persisted"] is False
        rows = _chat_rows(env, run_id)
        assert len(rows) == 1  # exactly one durable row
        assert rows[0].payload_json["attachments"] == [{"kind": "image", "retained": False}]


# ════════════════════════════════════════════════════════════════════════════
# (d) INV-3 dormancy — no images → run_images empty → dispatch byte-identical
# ════════════════════════════════════════════════════════════════════════════
class TestDormancy:
    def test_no_image_turn_leaves_carrier_empty(self, env):
        owner = _seed_user(env, "owner")
        run_id = _seed_run(env, owner.id, status="running")
        env["state"]["user"] = owner

        resp = _post(env, run_id, text="just text", message_id="m-plain")
        assert resp.status_code == 200, resp.text
        # No image refs on the persisted row (attachments empty).
        assert _chat_rows(env, run_id)[0].payload_json["attachments"] == []

    def test_drain_is_noop_and_dispatch_payload_byte_identical(self, env):
        from agents.execution_engine.context import ExecutionContext
        from agents.execution_engine.engine import _dispatch_payload, _drain_turn_images

        ectx = ExecutionContext(run_id="r", owner_id="o")
        # Empty pending queue → drain touches nothing → run_images unchanged (None).
        _drain_turn_images(ectx)
        assert ectx.run_images is None
        assert ectx.pending_turn_images == []
        # No blocks → _dispatch_payload returns the BARE context_message str (the dormant
        # split-transport default — agent_input + the 5 goldens stay byte-identical).
        ctx_msg = "=== CONTEXT ===\nbuild it"
        assert _dispatch_payload(ctx_msg, []) == ctx_msg
        assert _dispatch_payload(ctx_msg, []) is ctx_msg  # same object, zero re-wrap
