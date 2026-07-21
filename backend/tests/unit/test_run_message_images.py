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
    # W4a (44-03): _get_db relocated to app.api.run_engine (INV-12 extract-before
    # -delete); /ws/chat retired in 44-07. Patch the seam at its new home.
    from app.api import run_engine as ws_module
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
    _drain_turn_images(ectx)                       # engine drain → turn_images_once (one-shot)
    assert ectx.pending_turn_images == []          # consume-once (pending cleared)
    spec = SimpleNamespace(id="prototype-specify", injects=["images"])
    engine = get_execution_engine()
    return asyncio.get_event_loop().run_until_complete(
        engine._compose_input_blocks(spec, ectx)
    ), ectx


def _dispatch_blocks(ectx, spec) -> list:
    """Run ONE engine dispatch's image-block seam on a live ectx: drain pending →
    _compose_input_blocks. Mutates ``ectx``, so calling it twice models two SEQUENTIAL
    dispatches (e.g. two gate redos) — the shape the HI-01 consume-once bug needs."""
    from agents.execution_engine.engine import _drain_turn_images, get_execution_engine

    _drain_turn_images(ectx)
    engine = get_execution_engine()
    return asyncio.get_event_loop().run_until_complete(
        engine._compose_input_blocks(spec, ectx)
    )


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
        # HI-01: the per-turn image rides the ONE-SHOT carrier, NOT the sticky
        # run_images. _compose_input_blocks rendered AND consumed it, so run_images
        # stays empty and turn_images_once is cleared after this single dispatch.
        assert not ectx.run_images
        assert ectx.turn_images_once == []
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
# (a2) HI-01 regression — per-turn images are ONE-SHOT; run-entry images are sticky
# ════════════════════════════════════════════════════════════════════════════
_IMG_BLOCK = {
    "type": "image",
    "source_type": "base64",
    "mime_type": "image/png",
    "data": _IMG_B64,
}


class TestPerTurnImageConsumeOnce:
    """A per-turn image must reach EXACTLY the next dispatch and never re-deliver, while
    run-entry images stay sticky across every dispatch (HI-01 — the two channels are
    independent)."""

    @staticmethod
    def _images_spec():
        return SimpleNamespace(id="prototype-specify", injects=["images"])

    def test_per_turn_image_reaches_exactly_one_dispatch(self, env):
        """FAIL-BEFORE / PASS-AFTER: pre-fix the image stuck on run_images re-delivered
        on dispatch #2; the one-shot carrier makes dispatch #2 image-free."""
        import agents.capabilities.input_providers.run_images  # noqa: F401
        from agents.execution_engine.context import ExecutionContext

        from app.api.chat_router import apply_turn_images

        ectx = ExecutionContext(run_id="r", owner_id="o")
        ectx.compiled_input_providers = ["run_images"]
        spec = self._images_spec()

        apply_turn_images(ectx, [_valid_image()])    # image attached on THIS turn
        d1 = _dispatch_blocks(ectx, spec)            # gate redo #1
        d2 = _dispatch_blocks(ectx, spec)            # gate redo #2 — NO new image

        assert d1 == [_IMG_BLOCK]      # delivered to the NEXT dispatch …
        assert d2 == []                # … and NEVER re-delivered (the HI-01 fix)
        assert not ectx.run_images     # never polluted the sticky run-entry carrier

    def test_run_entry_images_are_sticky_across_dispatches(self, env):
        """Preservation guard: run-entry images (set at :1037) render on EVERY dispatch."""
        import agents.capabilities.input_providers.run_images  # noqa: F401
        from agents.execution_engine.context import ExecutionContext

        ectx = ExecutionContext(
            run_id="r", owner_id="o",
            run_images=[{"mime_type": "image/png", "data": _IMG_B64}],  # set at run entry
        )
        ectx.compiled_input_providers = ["run_images"]
        spec = self._images_spec()

        d1 = _dispatch_blocks(ectx, spec)
        d2 = _dispatch_blocks(ectx, spec)
        assert d1 == [_IMG_BLOCK]
        assert d2 == [_IMG_BLOCK]      # sticky — unchanged by the HI-01 fix

    def test_per_turn_and_run_entry_images_coexist_independently(self, env):
        """A per-turn image layered on top of a sticky run-entry image: dispatch #1
        carries both (sticky first, then one-shot); dispatch #2 keeps only the sticky."""
        import agents.capabilities.input_providers.run_images  # noqa: F401
        from agents.execution_engine.context import ExecutionContext

        from app.api.chat_router import apply_turn_images

        entry_block = {
            "type": "image", "source_type": "base64",
            "mime_type": "image/png", "data": "ENTRY",
        }
        ectx = ExecutionContext(
            run_id="r", owner_id="o",
            run_images=[{"mime_type": "image/png", "data": "ENTRY"}],
        )
        ectx.compiled_input_providers = ["run_images"]
        spec = self._images_spec()

        apply_turn_images(ectx, [_valid_image()])
        d1 = _dispatch_blocks(ectx, spec)
        d2 = _dispatch_blocks(ectx, spec)

        assert d1 == [entry_block, _IMG_BLOCK]   # sticky run-entry, then one-shot per-turn
        assert d2 == [entry_block]               # only the sticky one survives


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


# ════════════════════════════════════════════════════════════════════════════
# A.3 (Phase 43) — the LIVE-ECTX REGISTRY: _live_ectx_for_run resolves the running
# in-process ectx (no longer always None), so mid-run steering + per-turn images reach
# the NEXT dispatch. Closes DEF-29-09-1 (steering) + DEF-30-03-1 (per-turn image) — ONE
# registry, ONE seam (INV-12).
# ════════════════════════════════════════════════════════════════════════════
class TestLiveEctxRegistry:
    """The process-local run_id → ExecutionContext registry + _live_ectx_for_run resolver."""

    def _fresh_registry(self):
        """Return the run_commands module with a cleared registry (isolate from other tests)."""
        from app.api import run_commands as rc
        rc._LIVE_ECTX.clear()
        return rc

    def test_register_then_resolve_returns_the_same_ectx(self):
        from agents.execution_engine.context import ExecutionContext
        rc = self._fresh_registry()

        ectx = ExecutionContext(run_id="run-A", owner_id="o")
        assert rc._live_ectx_for_run("run-A") is None  # not live yet
        rc.register_live_ectx("run-A", ectx)
        # The SAME instance the running engine registered is resolved (identity, not a copy).
        assert rc._live_ectx_for_run("run-A") is ectx

    def test_unregister_removes_the_ectx_no_leak(self):
        from agents.execution_engine.context import ExecutionContext
        rc = self._fresh_registry()

        ectx = ExecutionContext(run_id="run-B", owner_id="o")
        rc.register_live_ectx("run-B", ectx)
        assert rc._live_ectx_for_run("run-B") is ectx
        rc.unregister_live_ectx("run-B")
        # After teardown the run is no longer resolvable — the registry does not leak.
        assert rc._live_ectx_for_run("run-B") is None
        assert "run-B" not in rc._LIVE_ECTX

    def test_cross_run_isolation_no_cross_delivery(self):
        """Two concurrent runs each resolve ONLY their own ectx — a steering note applied to
        run-1's handle can never reach run-2 (T-43-05-XINJECT — keyed by run_id only)."""
        from agents.execution_engine.context import ExecutionContext

        from app.api.chat_router import apply_steering
        rc = self._fresh_registry()

        ectx1 = ExecutionContext(run_id="run-1", owner_id="o1")
        ectx2 = ExecutionContext(run_id="run-2", owner_id="o2")
        rc.register_live_ectx("run-1", ectx1)
        rc.register_live_ectx("run-2", ectx2)

        # Each run resolves strictly its own context.
        assert rc._live_ectx_for_run("run-1") is ectx1
        assert rc._live_ectx_for_run("run-2") is ectx2

        # A note steered at run-1 lands ONLY on run-1's queue — run-2 is untouched.
        apply_steering(rc._live_ectx_for_run("run-1"), {"text": "for run 1", "sticky": False})
        assert ectx1.steering_notes == [{"text": "for run 1", "sticky": False}]
        assert ectx2.steering_notes == []

    def test_unregister_unknown_run_is_noop(self):
        rc = self._fresh_registry()
        rc.unregister_live_ectx("never-registered")  # must not raise
        rc.unregister_live_ectx("never-registered")  # double-unregister also safe
        assert rc._LIVE_ECTX == {}

    def test_resolve_unregistered_run_is_none_degrade_safe(self):
        rc = self._fresh_registry()
        # A run not live in THIS process resolves to None → apply_steering / apply_turn_images
        # no-op (the durable chat_message row remains the record).
        assert rc._live_ectx_for_run("some-other-worker-run") is None


# ════════════════════════════════════════════════════════════════════════════
# A.3 — the ENGINE seam: execute() registers the run's live ectx at run start and
# UNREGISTERS it on teardown (no leak), via the INJECTED callback (no engine→app import).
# ════════════════════════════════════════════════════════════════════════════
class TestLiveEctxEngineSeam:
    @pytest.mark.asyncio
    async def test_execute_registers_running_ectx_and_unregisters_on_teardown(self):
        """Drive a REAL scripted run end-to-end with the live-ectx register/unregister pair
        injected. Assert: (1) the engine registered THIS run's ExecutionContext during the run
        (resolvable via the real registry mid-flight), and (2) the wrapper's finally
        unregistered it on completion — the registry is empty (no leak)."""
        from agents.execution_engine.context import ExecutionContext

        from app.api import run_commands as rc
        from tests.agents._scripted_model import _drive

        rc._LIVE_ECTX.clear()
        captured: dict = {}

        def _reg(run_id: str, ectx) -> None:
            # Delegate to the REAL registry, then snapshot what the app layer resolves NOW —
            # proving _live_ectx_for_run resolves the running ectx MID-RUN (not None).
            rc.register_live_ectx(run_id, ectx)
            captured["run_id"] = run_id
            captured["ectx"] = ectx
            captured["resolved_mid_run"] = rc._live_ectx_for_run(run_id)

        events = await _drive(
            "prototype",
            live_ectx_register=_reg,
            live_ectx_unregister=rc.unregister_live_ectx,
        )

        # The run actually ran (produced events) and registered exactly one ectx.
        assert events, "the scripted run yielded no events"
        assert isinstance(captured.get("ectx"), ExecutionContext)
        assert captured["ectx"].run_id == captured["run_id"]
        # Mid-run, the app-layer resolver returned the SAME live context instance.
        assert captured["resolved_mid_run"] is captured["ectx"]
        # Teardown ran the unregister (finally) — the registry leaks nothing.
        assert rc._live_ectx_for_run(captured["run_id"]) is None
        assert captured["run_id"] not in rc._LIVE_ECTX


# ════════════════════════════════════════════════════════════════════════════
# A.3 — END-TO-END through the REST endpoint: a RUNNING-phase steering turn (text +
# per-turn image) posted to POST /messages reaches the REGISTERED live ectx, so BOTH the
# === USER GUIDANCE === note and the per-turn image drain onto the next dispatch.
# ════════════════════════════════════════════════════════════════════════════
class TestSteeringAndImageReachLiveEctx:
    def _register(self, run_id):
        from agents.execution_engine.context import ExecutionContext

        from app.api import run_commands as rc
        ectx = ExecutionContext(run_id=run_id, owner_id="o")
        rc._LIVE_ECTX.clear()
        rc.register_live_ectx(run_id, ectx)
        return rc, ectx

    def test_running_steering_turn_lands_note_and_image_on_live_ectx(self, env):
        owner = _seed_user(env, "owner")
        run_id = _seed_run(env, owner.id, status="running")
        env["state"]["user"] = owner
        rc, ectx = self._register(run_id)
        try:
            resp = _post(env, run_id, text="Use a dark theme",
                         images=[_valid_image()], message_id="m-live")
            assert resp.status_code == 200, resp.text
            assert resp.json()["channel"] == "steering"
            # The steering note reached the LIVE ectx's consume-once queue (=== USER GUIDANCE ===
            # is rendered from here at the next dispatch).
            assert ectx.steering_notes == [{"text": "Use a dark theme", "sticky": False}]
            # The per-turn image reached the SAME live handle's pending queue (drained onto the
            # one-shot turn_images_once carrier at the next dispatch).
            assert ectx.pending_turn_images == [{"mime_type": "image/png", "data": _IMG_B64}]
        finally:
            rc.unregister_live_ectx(run_id)

    def test_not_live_run_is_degrade_safe_no_crash(self, env):
        """When the run is NOT registered (not live in this process), the endpoint still 200s
        and durably records the turn — apply_steering/apply_turn_images no-op on the None handle."""
        from app.api import run_commands as rc
        rc._LIVE_ECTX.clear()  # nothing registered

        owner = _seed_user(env, "owner")
        run_id = _seed_run(env, owner.id, status="running")
        env["state"]["user"] = owner

        resp = _post(env, run_id, text="steer me", message_id="m-nolive")
        assert resp.status_code == 200, resp.text
        assert resp.json()["channel"] == "steering"
        assert resp.json()["persisted"] is True  # the durable record still lands
