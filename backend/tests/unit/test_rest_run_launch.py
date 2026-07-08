"""tests/unit/test_rest_run_launch.py — CHAT-07 / D-13 (29-04).

The up-channel REST twin of ``POST /api/runs`` (run launch), ported from
``test_run_pipeline_validation.py`` (the WS ``run_pipeline`` ingress-validation
suite) against the REST endpoint. The endpoint mints the WorkflowRun + spawns the
WS-agnostic background driver onto the per-run queue (the SSE stream then attaches)
— LOCK-B: ``websocket.py`` is untouched; the ingress validators + queue registry
are read-only imports, and the engine-drive loop is a sanctioned duplication.

Coverage:
  * The ported allow-list predicates (``allowed_custom_agent_ids`` /
    ``SUPPORTED_PIPELINE_TYPES`` / ``_validate_model_overrides``) are re-asserted
    at the REST boundary — a bad pipeline_type / bad agent_ids / bad
    model_overrides denies with NO WorkflowRun and NO execute (rejected pre-mint).
  * The happy path mints a WorkflowRun (``user_id`` = caller) + spawns the driver,
    which populates the per-run queue (offline recording engine — no Bedrock).

Offline — in-memory SQLite (StaticPool) monkeypatched onto ``ws_module._get_db``;
a recording stub engine via ``agents.execution_engine.engine.get_execution_engine``.
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

# Register every table the launch path touches on Base.metadata BEFORE create_all.
import app.models.artifact_ref  # noqa: F401
import app.models.run_capabilities  # noqa: F401
import app.models.run_event  # noqa: F401
import app.models.workflow  # noqa: F401
import app.models.workspace  # noqa: F401
import agents.execution_engine.engine as engine_mod


# ════════════════════════════════════════════════════════════════════════════
# Harness — in-memory SQLite + TestClient over the run_commands router
# ════════════════════════════════════════════════════════════════════════════


class _FakeUser:
    def __init__(self, id: str):
        self.id = id
        self.preferred_model = None


class _RecordingEngine:
    """Stub engine recording the execute() kwargs + emitting a minimal stream."""

    last_kwargs: dict | None = None
    invoked = False

    async def execute(self, **kwargs):
        _RecordingEngine.invoked = True
        _RecordingEngine.last_kwargs = kwargs
        yield {"type": "pipeline_start", "data": {"agents": []}}
        yield {"type": "pipeline_complete", "data": {"final_output": "done"}}


@pytest.fixture
def env(monkeypatch):
    from app.api import websocket as ws_module
    from app.models.database import Base

    db_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    Base.metadata.create_all(bind=db_engine)
    # Patch _get_db on BOTH modules: run_commands binds its OWN reference at import
    # (``from app.api.websocket import _get_db``), so patching ws_module alone would
    # miss the REST endpoints' direct calls. The queue registries + validators are
    # shared object references, so they need no patch.
    monkeypatch.setattr(ws_module, "_get_db", lambda: TestingSession())
    import app.api.run_commands as rc_module
    monkeypatch.setattr(rc_module, "_get_db", lambda: TestingSession())

    _RecordingEngine.invoked = False
    _RecordingEngine.last_kwargs = None
    monkeypatch.setattr(engine_mod, "get_execution_engine", lambda: _RecordingEngine())

    from app.api.run_commands import router
    from app.core.dependencies import get_current_user

    app = FastAPI()
    app.include_router(router)
    state: dict = {"user": None}
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    client = TestClient(app)

    yield {"ws": ws_module, "client": client, "state": state, "Session": TestingSession}

    Base.metadata.drop_all(bind=db_engine)
    db_engine.dispose()


def _seed_user(env) -> _FakeUser:
    from app.models.user import User

    db = env["ws"]._get_db()
    try:
        u = User(
            id=str(uuid.uuid4()),
            email=f"launch-{uuid.uuid4().hex[:8]}@example.com",
            password_hash="x",
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return _FakeUser(id=u.id)
    finally:
        db.close()


def _latest_run(env):
    from app.models.workflow import WorkflowRun

    db = env["ws"]._get_db()
    try:
        return db.query(WorkflowRun).order_by(WorkflowRun.created_at.desc()).first()
    finally:
        db.close()


def _run_count(env) -> int:
    from app.models.workflow import WorkflowRun

    db = env["ws"]._get_db()
    try:
        return db.query(WorkflowRun).count()
    finally:
        db.close()


def _post_launch(env, **body):
    return env["client"].post("/api/runs", json=body)


# ────────────────────────────────────────────────────────────────────────────
# 1. Ported ingress validation — rejected PRE-MINT (no WorkflowRun, no execute)
# ────────────────────────────────────────────────────────────────────────────


def test_unsupported_pipeline_type_rejected_pre_mint(env):
    user = _seed_user(env)
    env["state"]["user"] = user
    resp = _post_launch(env, message="build it", pipeline_type="totally_made_up")
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "invalid_pipeline_type"
    assert _run_count(env) == 0
    assert _RecordingEngine.invoked is False


def test_unknown_agent_id_rejected(env):
    """G1-C6: an agent id in NO allow-list (nonexistent / smuggled) is rejected —
    the exact ``allowed_custom_agent_ids`` predicate, now at the REST boundary.

    (The stricter cross-*base*-pipeline rejection is asserted by the registry-level
    suite; on this branch the "custom" pool has widened — see deferred-items.md —
    so this REST pin uses a genuinely-unknown id, which no widening can admit.)"""
    user = _seed_user(env)
    env["state"]["user"] = user
    resp = _post_launch(
        env, message="deck", pipeline_type="ppt",
        agent_ids=["totally-nonexistent-agent-xyz"],
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["code"] == "invalid_agent_ids"
    assert "totally-nonexistent-agent-xyz" in detail["rejected_agent_ids"]
    assert _run_count(env) == 0
    assert _RecordingEngine.invoked is False


def test_unknown_model_override_rejected_pre_mint(env):
    """T-06-06 [HIGH]: an arbitrary model id (not in the catalog) is rejected."""
    user = _seed_user(env)
    env["state"]["user"] = user
    resp = _post_launch(
        env,
        message="build a backlog",
        pipeline_type="user_stories",
        model_overrides={"domain-analyst": "evil.attacker/unknown:latest"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "invalid_model_override"
    assert _run_count(env) == 0
    assert _RecordingEngine.invoked is False


def test_missing_message_is_a_422_bad_payload(env):
    """A launch with no ``message`` is a malformed payload (pydantic 422) — no
    run is minted."""
    user = _seed_user(env)
    env["state"]["user"] = user
    resp = env["client"].post("/api/runs", json={"pipeline_type": "user_stories"})
    assert resp.status_code == 422
    assert _run_count(env) == 0


# ────────────────────────────────────────────────────────────────────────────
# 2. Happy path — the endpoint mints the run (synchronous) + returns {run_id}
# ────────────────────────────────────────────────────────────────────────────


def test_launch_mints_run(env):
    user = _seed_user(env)
    env["state"]["user"] = user
    resp = _post_launch(env, message="build a backlog", pipeline_type="user_stories")
    assert resp.status_code == 200, resp.text
    run_id = resp.json()["run_id"]
    assert run_id

    # The WorkflowRun was minted BEFORE the endpoint returned, owned by the caller
    # (user_id). The background driver + SSE attach are proven at the driver level.
    run = _latest_run(env)
    assert run is not None
    assert run.id == run_id
    assert run.user_id == user.id
    assert run.type == "user_stories"
    assert run.input == "build a backlog"
    assert run.agent_count > 0


# ────────────────────────────────────────────────────────────────────────────
# 3. Driver level — the WS-agnostic background driver populates the per-run queue
#    (deterministic: drive the coroutine directly, no TestClient task-timing race)
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_driver_drives_engine_and_populates_queue(env):
    """The launch driver runs the engine + pushes every event onto the per-run
    queue (the queue the SSE stream drains) and terminates with the None sentinel,
    then persists the terminal status onto the run row."""
    from app.api import run_commands as rc

    user = _seed_user(env)
    # Seed a run row for the driver to finalize.
    from app.models.workflow import WorkflowRun

    run_id = str(uuid.uuid4())
    db = env["ws"]._get_db()
    try:
        db.add(WorkflowRun(
            id=run_id, user_id=user.id, title="t", type="user_stories",
            status="running", input="build a backlog", agent_count=1,
            session_id=user.id,
        ))
        db.commit()
    finally:
        db.close()

    queue: asyncio.Queue = asyncio.Queue()
    await rc._drive_launch_to_queue(
        workflow_run_id=run_id,
        pipeline_run_id=run_id,
        agents=[object()],  # opaque — the recording engine ignores it
        content="build a backlog",
        pipeline_type="user_stories",
        cancel_event=asyncio.Event(),
        user=user,
        attached_skills=[],
        attached_hooks=[],
        od_context=None,
        validated_images=[],
        gate_agent_ids=None,
        parent_run_id=None,
        model_overrides={},
        selections=None,
        event_queue=queue,
    )

    # The recording engine was driven with the run's identifiers.
    assert _RecordingEngine.invoked is True
    assert _RecordingEngine.last_kwargs.get("pipeline_run_id") == run_id
    assert _RecordingEngine.last_kwargs.get("user_id") == user.id
    assert _RecordingEngine.last_kwargs.get("images") == []

    # The queue carries the engine's events then the None sentinel.
    drained = []
    while True:
        item = queue.get_nowait()
        if item is None:
            break
        drained.append(item)
    types = [e["type"] for e in drained]
    assert "pipeline_start" in types
    assert "pipeline_complete" in types

    # Terminal status persisted "completed"; cleanup removed the run registries.
    row = _latest_run(env)
    assert row.status == "completed"
    assert run_id not in env["ws"]._PIPELINE_QUEUES


@pytest.mark.asyncio
async def test_driver_persists_full_agent_history_like_ws(env, monkeypatch):
    """CR-02: the REST launch driver must persist the SAME agent_outputs history as
    the WS ``_run_pipeline_to_queue`` — including tool calls, thinking text, the input
    prompt, and context sources.

    The sanctioned WS→REST duplication had dropped the ``agent_input`` /
    ``agent_thinking`` / ``tool_call`` / ``tool_result`` branches (and the four
    ``current_agent`` scaffold keys), so every REST-launched run persisted a degraded
    WorkflowRun.agent_outputs blob silently missing that data. This drives the rich
    engine stream and asserts the persisted blob now carries it (fails pre-fix).
    """
    import json

    from app.api import run_commands as rc
    from app.models.workflow import WorkflowRun

    class _RichEngine:
        """Emits the full per-agent event vocabulary the WS driver records."""

        async def execute(self, **kwargs):
            yield {"type": "agent_start", "data": {
                "agent_id": "a1", "name": "A1", "role": "r", "icon": "i"}}
            yield {"type": "agent_input", "data": {
                "context_message": "PROMPT-TEXT", "context_sources": ["upstream-1"]}}
            yield {"type": "agent_thinking", "data": {"thinking": "let me "}}
            yield {"type": "agent_thinking", "data": {"thinking": "think..."}}
            yield {"type": "tool_call", "data": {
                "tool": "write_file", "args": {"path": "x"}}}
            yield {"type": "tool_result", "data": {
                "tool": "write_file", "result": "ok"}}
            yield {"type": "agent_chunk", "data": {"chunk": "hello"}}
            yield {"type": "agent_complete", "data": {
                "duration": 1.2, "input_tokens": 10, "output_tokens": 5,
                "total_tokens": 15}}
            yield {"type": "pipeline_complete", "data": {"final_output": "done"}}

    monkeypatch.setattr(engine_mod, "get_execution_engine", lambda: _RichEngine())

    user = _seed_user(env)
    run_id = str(uuid.uuid4())
    db = env["ws"]._get_db()
    try:
        db.add(WorkflowRun(
            id=run_id, user_id=user.id, title="t", type="user_stories",
            status="running", input="build a backlog", agent_count=1,
            session_id=user.id,
        ))
        db.commit()
    finally:
        db.close()

    queue: asyncio.Queue = asyncio.Queue()
    await rc._drive_launch_to_queue(
        workflow_run_id=run_id,
        pipeline_run_id=run_id,
        agents=[object()],
        content="build a backlog",
        pipeline_type="user_stories",
        cancel_event=asyncio.Event(),
        user=user,
        attached_skills=[],
        attached_hooks=[],
        od_context=None,
        validated_images=[],
        gate_agent_ids=None,
        parent_run_id=None,
        model_overrides={},
        selections=None,
        event_queue=queue,
    )

    row = _latest_run(env)
    assert row.status == "completed"
    outputs = json.loads(row.agent_outputs)
    assert len(outputs) == 1
    agent = outputs[0]
    # The four previously-dropped fields are now persisted (WS-parity).
    assert agent["input_prompt"] == "PROMPT-TEXT"
    assert agent["context_sources"] == ["upstream-1"]
    assert agent["thinking_text"] == "let me think..."
    assert len(agent["tool_calls"]) == 1
    tc = agent["tool_calls"][0]
    assert tc["tool"] == "write_file"
    assert tc["args"] == {"path": "x"}
    assert tc["result"] == "ok"  # tool_result was matched back onto the open call
    assert tc["timestamp"]  # stamped at tool_call time
