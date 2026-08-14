"""tests/unit/test_rest_revisions.py — CHAT-07 / D-13 (29-04).

The up-channel REST twin of ``POST /api/runs/{id}/revisions`` (child-run dispatch),
ported from ``test_run_revision_ws_dispatch.py`` + ``test_ws_parent_link_ownership.py``
(the WS ``run_revision`` dispatch + parent-link ownership suites) against the REST
endpoint. The endpoint mints a FAMILY CHILD WorkflowRun (parent_run_id + owner_id)
of type ``<base>_revision`` and spawns the WS-agnostic revision driver onto the
per-run queue (the SSE stream then attaches) — LOCK-B: ``websocket.py`` is untouched;
the engine dispatch is reused via ``engine._handle_revision`` and the drive loop is a
sanctioned duplication.

Terminology: this is D-02's family "revision run", NOT the intra-run KAN-101
spec-revision loop.

Coverage:
  * Endpoint parent-link ownership (T-29-04-1): owned parent → 200 + linked child;
    cross-owner / unknown parent → 404 (IDOR → 404, never 403; stricter than the WS
    path, which drops the link but still dispatches).
  * Endpoint mint: child row carries parent_run_id + owner_id + ``<base>_revision``
    type + registry-derived agent_count (Pitfall 6 — never a hardcoded 1).
  * The 6 revision-dispatch scenarios at the driver seam (deterministic — no
    TestClient task-timing race): happy → completed; pipeline_failed → failed;
    ValueError → revision_validation_error + failed; runtime → revision_error +
    failed; degraded completion → degraded; cancellation → cancelled.

Offline — in-memory SQLite (StaticPool) on ``ws_module._get_db`` +
``run_commands._get_db``; stub engine via ``engine_mod.get_execution_engine``.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Register every table the revision path touches on Base.metadata BEFORE create_all.
import app.models.artifact_ref  # noqa: F401
import app.models.run_capabilities  # noqa: F401
import app.models.run_event  # noqa: F401
import app.models.workflow  # noqa: F401
import app.models.workspace  # noqa: F401
import agents.execution_engine.engine as engine_mod
from agents.registry import get_pipeline_agents
from app.models.database import Base
from app.models.user import User
from app.models.workflow import WorkflowRun


# ════════════════════════════════════════════════════════════════════════════
# Harness
# ════════════════════════════════════════════════════════════════════════════


class _FakeUser:
    def __init__(self, id: str, tier: str = "enterprise"):
        self.id = id
        self.preferred_model = None
        self.tier = tier


class _StubEngine:
    def __init__(self, behavior) -> None:
        self._behavior = behavior
        self.calls: list[dict] = []

    async def _handle_revision(self, **kwargs) -> None:
        self.calls.append(kwargs)
        await self._behavior(kwargs)


@pytest.fixture
def env(monkeypatch):
    from app.api import run_engine as ws_module
    import app.api.run_commands as rc_module

    db_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    Base.metadata.create_all(bind=db_engine)
    monkeypatch.setattr(ws_module, "_get_db", lambda: TestingSession())
    monkeypatch.setattr(rc_module, "_get_db", lambda: TestingSession())

    from app.api.run_commands import router
    from app.core.dependencies import get_current_user

    app = FastAPI()
    app.include_router(router)
    state: dict = {"user": None}
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    client = TestClient(app)

    yield {
        "ws": ws_module, "rc": rc_module, "client": client,
        "state": state, "Session": TestingSession,
    }

    Base.metadata.drop_all(bind=db_engine)
    db_engine.dispose()


def _seed_user(env, tag="u") -> _FakeUser:
    db = env["Session"]()
    try:
        u = User(
            id=str(uuid.uuid4()),
            email=f"rev04-{tag}-{uuid.uuid4().hex[:8]}@example.com",
            password_hash="x",
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return _FakeUser(id=u.id)
    finally:
        db.close()


def _seed_parent(env, owner_id: str, run_type="ppt") -> str:
    parent_id = str(uuid.uuid4())
    db = env["Session"]()
    try:
        db.add(WorkflowRun(
            id=parent_id, user_id=owner_id, owner_id=owner_id,
            title="parent deck", type=run_type, status="completed",
            input="make a deck", agent_count=3,
        ))
        db.commit()
    finally:
        db.close()
    return parent_id


def _seed_child(env, owner_id: str, *, run_type="ppt_revision") -> str:
    """Seed a child revision row for a direct driver-level dispatch test."""
    run_id = str(uuid.uuid4())
    db = env["Session"]()
    try:
        db.add(WorkflowRun(
            id=run_id, user_id=owner_id, owner_id=owner_id,
            title="Revision: x", type=run_type, status="revising", input="x",
            agent_count=1,
        ))
        db.commit()
    finally:
        db.close()
    return run_id


def _row(env, run_id: str) -> WorkflowRun | None:
    db = env["Session"]()
    try:
        return db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    finally:
        db.close()


def _install_stub(env, monkeypatch, behavior) -> _StubEngine:
    stub = _StubEngine(behavior)
    monkeypatch.setattr(engine_mod, "get_execution_engine", lambda: stub)
    return stub


def _post_revision(env, parent_id, target, instruction):
    return env["client"].post(
        f"/api/runs/{parent_id}/revisions",
        json={"target_artifact_type": target, "instruction": instruction},
    )


async def _drive(env, *, run_id, parent_run_id, target, instruction, user):
    """Drive the revision driver directly against a fresh queue; return the queue."""
    queue: asyncio.Queue = asyncio.Queue()
    await env["rc"]._drive_revision_to_queue(
        workflow_run_id=run_id,
        parent_run_id=parent_run_id,
        target_artifact_type=target,
        instruction=instruction,
        user=user,
        cancel_event=asyncio.Event(),
        event_queue=queue,
    )
    drained = []
    while True:
        item = queue.get_nowait()
        if item is None:
            break
        drained.append(item)
    return drained


# ════════════════════════════════════════════════════════════════════════════
# Endpoint — parent-link ownership (T-29-04-1) + child mint
# ════════════════════════════════════════════════════════════════════════════


def test_owned_parent_mints_linked_child(env, monkeypatch):
    _install_stub(env, monkeypatch, lambda k: _noop_complete(k))
    owner = _seed_user(env, "owner")
    parent_id = _seed_parent(env, owner.id)
    env["state"]["user"] = owner

    resp = _post_revision(env, parent_id, "ppt_output", "Make slide 1 a CTA.")
    assert resp.status_code == 200, resp.text
    child_id = resp.json()["run_id"]

    child = _row(env, child_id)
    assert child is not None
    assert child.parent_run_id == parent_id
    assert child.owner_id == owner.id
    assert child.user_id == owner.id
    assert child.type == "ppt_revision"
    # agent_count derives from the LIVE registry membership (Pitfall 6).
    assert child.agent_count == (len(get_pipeline_agents("ppt_revision")) or 1)


def test_cross_owner_parent_returns_404(env, monkeypatch):
    _install_stub(env, monkeypatch, lambda k: _noop_complete(k))
    owner = _seed_user(env, "owner")
    attacker = _seed_user(env, "attacker")
    parent_id = _seed_parent(env, owner.id)
    env["state"]["user"] = attacker

    resp = _post_revision(env, parent_id, "ppt_output", "Steal the deck.")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Unknown run"
    # No child row was minted for the attacker.
    db = env["Session"]()
    try:
        assert db.query(WorkflowRun).filter(WorkflowRun.user_id == attacker.id).count() == 0
    finally:
        db.close()


def test_unknown_parent_returns_404(env, monkeypatch):
    _install_stub(env, monkeypatch, lambda k: _noop_complete(k))
    caller = _seed_user(env, "caller")
    env["state"]["user"] = caller
    resp = _post_revision(env, str(uuid.uuid4()), "ppt_output", "Fix it.")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Unknown run"


def test_agent_count_derives_for_ppt_revision(env, monkeypatch):
    """ppt_output → ppt_revision derives agent_count from the LIVE registry
    membership, never a hardcoded literal (Pitfall 6). ppt_revision is a
    single-agent pipeline (formerly od_ppt_revision — see
    agents/registry.py); this pins the derivation, not a specific count."""
    _install_stub(env, monkeypatch, lambda k: _noop_complete(k))
    owner = _seed_user(env, "owner")
    parent_id = _seed_parent(env, owner.id, run_type="ppt")
    env["state"]["user"] = owner
    expected = len(get_pipeline_agents("ppt_revision"))
    assert expected >= 1, "ppt_revision lost its agent membership?"

    resp = _post_revision(env, parent_id, "ppt_output", "Revise the deck.")
    assert resp.status_code == 200, resp.text
    child = _row(env, resp.json()["run_id"])
    assert child.type == "ppt_revision"
    assert child.agent_count == expected


# ════════════════════════════════════════════════════════════════════════════
# Driver — the 6 dispatch scenarios (deterministic direct drive)
# ════════════════════════════════════════════════════════════════════════════


async def _noop_complete(kwargs):
    await kwargs["websocket_send_fn"]({"type": "pipeline_complete", "data": {"final_output": "x"}})


@pytest.mark.asyncio
async def test_driver_happy_path_completed(env, monkeypatch):
    async def _happy(kwargs):
        send = kwargs["websocket_send_fn"]
        await send({"type": "pipeline_start", "data": {"agents": []}})
        await send({"type": "pipeline_complete", "data": {"final_output": "<html>revised</html>"}})

    _install_stub(env, monkeypatch, _happy)
    owner = _seed_user(env, "owner")
    run_id = _seed_child(env, owner.id)
    drained = await _drive(env, run_id=run_id, parent_run_id="parent",
                           target="ppt_output", instruction="x", user=owner)
    assert [e["type"] for e in drained].count("pipeline_complete") == 1
    assert _row(env, run_id).status == "completed"
    assert _row(env, run_id).completed_at is not None


@pytest.mark.asyncio
async def test_driver_happy_path_persists_output_columns(env, monkeypatch):
    """ISS-152: the revision driver is a fourth caller of the shared
    ``_apply_terminal_output_columns`` mapping that BUG-R03 never wired — its
    ``_persist_terminal_status`` writes ONLY ``status``/``completed_at``. Drives the
    full ``agent_start``→``agent_chunk``→``agent_complete``→``pipeline_complete``
    vocabulary (mirrors ``test_driver_persists_model_id_and_prices_non_circular`` in
    ``test_rest_run_launch.py``) and asserts all 7 output columns land. RED today —
    every assertion below fails against the unpatched driver."""
    import json

    async def _rich(kwargs):
        send = kwargs["websocket_send_fn"]
        await send({"type": "pipeline_start", "data": {"agents": []}})
        await send({"type": "agent_start", "data": {
            "agent_id": "user-stories-revision-agent", "name": "Reviser",
            "role": "r", "icon": "i"}})
        await send({"type": "agent_chunk", "data": {"chunk": "<html>revised</html>"}})
        await send({"type": "agent_complete", "data": {
            "duration": 2.1, "input_tokens": 3944, "output_tokens": 297,
            "total_tokens": 4241}})
        await send({"type": "pipeline_complete", "data": {
            "final_output": "<html>revised</html>",
            "deliverable_mimetype": "text/markdown",
            "deliverable_filename": "user_stories.md",
        }})

    _install_stub(env, monkeypatch, _rich)
    owner = _seed_user(env, "owner")
    owner.preferred_model = "claude-sonnet-test"
    run_id = _seed_child(env, owner.id)
    await _drive(env, run_id=run_id, parent_run_id="parent",
                 target="od_ppt_output", instruction="x", user=owner)

    row = _row(env, run_id)
    assert row.status == "completed"
    assert row.output == "<html>revised</html>"
    outputs = json.loads(row.agent_outputs)
    assert len(outputs) == 1
    assert outputs[0]["agent_id"] == "user-stories-revision-agent"
    usage = json.loads(row.token_usage)
    assert usage["total_input_tokens"] == 3944
    assert usage["total_output_tokens"] == 297
    assert usage["total_tokens"] == 4241
    assert row.duration is not None
    assert row.model_id == "claude-sonnet-test"
    assert row.deliverable_mimetype == "text/markdown"
    assert row.deliverable_filename == "user_stories.md"


@pytest.mark.asyncio
async def test_driver_pipeline_failed_records_failed(env, monkeypatch):
    async def _fails(kwargs):
        send = kwargs["websocket_send_fn"]
        await send({"type": "pipeline_failed", "data": {"error": "no agent completed"}})

    _install_stub(env, monkeypatch, _fails)
    owner = _seed_user(env, "owner")
    run_id = _seed_child(env, owner.id)
    drained = await _drive(env, run_id=run_id, parent_run_id="parent",
                           target="ppt_output", instruction="x", user=owner)
    assert [e["type"] for e in drained].count("pipeline_failed") == 1
    row = _row(env, run_id)
    assert row.status == "failed"
    assert row.status != "completed"


@pytest.mark.asyncio
async def test_driver_value_error_maps_to_validation_error(env, monkeypatch):
    async def _raises(kwargs):
        raise ValueError("boom")

    _install_stub(env, monkeypatch, _raises)
    owner = _seed_user(env, "owner")
    run_id = _seed_child(env, owner.id)
    drained = await _drive(env, run_id=run_id, parent_run_id="parent",
                           target="ppt_output", instruction="x", user=owner)
    errors = [e for e in drained if e["type"] == "error"]
    assert len(errors) == 1
    assert errors[0]["data"]["code"] == "revision_validation_error"
    assert errors[0]["data"]["recoverable"] is False
    assert errors[0]["data"]["error"] == "boom"
    assert _row(env, run_id).status == "failed"


@pytest.mark.asyncio
async def test_driver_runtime_error_maps_to_revision_error(env, monkeypatch):
    async def _raises(kwargs):
        raise RuntimeError("engine exploded")

    _install_stub(env, monkeypatch, _raises)
    owner = _seed_user(env, "owner")
    run_id = _seed_child(env, owner.id)
    drained = await _drive(env, run_id=run_id, parent_run_id="parent",
                           target="ppt_output", instruction="x", user=owner)
    errors = [e for e in drained if e["type"] == "error"]
    assert len(errors) == 1
    assert errors[0]["data"]["code"] == "revision_error"
    assert errors[0]["data"]["recoverable"] is True
    assert "engine exploded" in errors[0]["data"]["error"]
    assert _row(env, run_id).status == "failed"


@pytest.mark.asyncio
async def test_driver_degraded_completion_records_degraded(env, monkeypatch):
    async def _degraded(kwargs):
        await kwargs["websocket_send_fn"]({
            "type": "pipeline_complete",
            "data": {"final_output": "<html>partial</html>", "status": "degraded",
                     "agents_failed": ["ppt-revision-assembler"]},
        })

    _install_stub(env, monkeypatch, _degraded)
    owner = _seed_user(env, "owner")
    run_id = _seed_child(env, owner.id)
    await _drive(env, run_id=run_id, parent_run_id="parent",
                 target="ppt_output", instruction="x", user=owner)
    row = _row(env, run_id)
    assert row.status == "degraded"
    assert row.status != "completed"


@pytest.mark.asyncio
async def test_driver_cancellation_records_cancelled(env, monkeypatch):
    async def _cooperative(kwargs):
        send = kwargs["websocket_send_fn"]
        await send({"type": "pipeline_start", "data": {"agents": []}})
        # The engine observes the cooperative cancel and emits pipeline_cancelled.
        kwargs["cancel_event"].set()
        await send({"type": "pipeline_cancelled", "data": {"message": "stopped"}})

    _install_stub(env, monkeypatch, _cooperative)
    owner = _seed_user(env, "owner")
    run_id = _seed_child(env, owner.id)
    drained = await _drive(env, run_id=run_id, parent_run_id="parent",
                           target="ppt_output", instruction="x", user=owner)
    assert "pipeline_cancelled" in [e["type"] for e in drained]
    row = _row(env, run_id)
    assert row.status == "cancelled"
    assert row.status not in ("revising", "completed")


# ════════════════════════════════════════════════════════════════════════════
# Parent-link resolver — the owner-checked resolver directly (T-44-08-01)
#
# Migrated from ``test_ws_parent_link_ownership.py::TestResolverDirect`` (44-08):
# the WS suite drove the resolver + both WS ingress sites; the sites are now the
# REST ``/revisions`` endpoint (cross-owner → 404, above) and ``POST /api/runs``
# (``test_rest_run_launch.py``). The resolver itself is the transport-neutral seam
# (relocated to ``app.api.run_engine`` in 44-03) both REST sites route through —
# these pins keep its exact contract (owned → id; foreign/missing → None; a falsy
# candidate short-circuits with NO query) so no cross-owner parent edge can be
# persisted as a family link.
# ════════════════════════════════════════════════════════════════════════════


class TestResolverDirect:
    def test_owned_candidate_returns_id(self, env):
        owner = _seed_user(env, "owner")
        parent_id = _seed_parent(env, owner.id)
        db = env["Session"]()
        try:
            assert env["ws"]._resolve_owned_parent_run_id(db, parent_id, owner.id) == parent_id
        finally:
            db.close()

    def test_foreign_owned_candidate_returns_none(self, env):
        owner = _seed_user(env, "owner")
        attacker = _seed_user(env, "attacker")
        parent_id = _seed_parent(env, owner.id)
        db = env["Session"]()
        try:
            # The attacker names a real run id — but it is not theirs → dropped.
            assert env["ws"]._resolve_owned_parent_run_id(db, parent_id, attacker.id) is None
        finally:
            db.close()

    def test_missing_candidate_returns_none(self, env):
        owner = _seed_user(env, "owner")
        db = env["Session"]()
        try:
            assert env["ws"]._resolve_owned_parent_run_id(
                db, "does-not-exist", owner.id
            ) is None
        finally:
            db.close()

    def test_falsy_candidate_returns_none_without_query(self, env):
        owner = _seed_user(env, "owner")

        class _ExplodingDb:
            def query(self, *a, **k):  # pragma: no cover - must never be called
                raise AssertionError("a falsy candidate must not issue a query")

        for falsy in (None, ""):
            assert env["ws"]._resolve_owned_parent_run_id(
                _ExplodingDb(), falsy, owner.id
            ) is None
