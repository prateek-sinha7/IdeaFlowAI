"""Turn flow of the AI Workflow Builder over HTTP, on real PostgreSQL (task 22.4).

Covers Req 21.3, 21.6, 21.7, 22.1, 22.2, 23.18, 24.5 and 49.4 of the
ai-workflow-builder spec:

* ``POST /messages`` answers 202 with the ids and nothing else, then the Turn's
  events arrive on the Session_Stream and the rows are stored (21.3, 21.4);
* a second message while a Turn runs is refused with 409 and stores nothing (21.7);
* a stream that drops mid-Turn does not stop the Turn; its result is stored (21.6);
* a Turn that hits a short time cap, set through ``settings``, ends ``timed_out`` and
  stores the file the agent wrote as an unproposed revision (23.18);
* tool rows are readable from the database while the Turn is still running (24.5);
* the startup sweep marks a leftover running Turn ``interrupted``, keeps its work, and
  starts no model call (22.2);
* the shutdown step stops a live Turn with its partial text stored as
  ``interrupted`` and closes the stream (22.1).

Real: PostgreSQL (a throwaway database migrated to Alembic head), the FastAPI routers,
admission, ``TurnRunner``, the bus, the stream frame generator, the stores and the
sandbox on ``tmp_path``. Faked: the chat model (``FakeChatModel``, played back through
the real ``DeepAgentRunner``), the Server_Gate (``FakeGate``, unused by these scripts)
and authentication. No network.

The Session_Stream is read through ``iter_session_frames``, the generator the SSE route
wraps, because ``httpx.ASGITransport`` buffers a whole response and cannot read an open
stream. The route itself is covered by the stream integration test (task 22.5).

Database: PostgreSQL only, never SQLite. Needs Docker (testcontainers) or
``PYTEST_POSTGRES_ADMIN_URL``; without either the tests error at fixture setup, as
the other integration tests do. They run on the Docker-capable CI runner.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Callable, Generator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.agents.workflow_builder.model_catalog_view import builder_models
from app.agents.workflow_builder.sandbox import BuilderSandbox
from app.api import run_shutdown
from app.api.workflow_builder import lifecycle, router, stream, turns
from app.api.workflow_builder.admission import (
    get_builder_readiness,
    get_capacity_gate,
    set_turn_starter,
)
from app.api.workflow_builder.store import BuilderStore
from app.api.workflow_builder.turns import (
    TurnDeps,
    build_snapshot,
    get_event_bus,
    get_live_turn,
    set_event_bus,
    stop_all,
)
from app.core.config import settings
from app.core.dependencies import get_current_principal
from app.models.database import get_db
from app.models.user import User
from app.models.workflow_builder import (
    DRAFT_KIND_UNPROPOSED,
    MESSAGE_ROLE_TOOL,
    MESSAGE_ROLE_USER,
    MESSAGE_STATUS_CANCELLED,
    MESSAGE_STATUS_COMPLETED,
    MESSAGE_STATUS_INTERRUPTED,
    MESSAGE_STATUS_RUNNING,
    MESSAGE_STATUS_TIMED_OUT,
    MESSAGE_STATUS_TOOL_OK,
    WorkflowBuilderMessage,
)
from tests.fakes.builder_gate import FakeGate
from tests.fakes.principal import principal_for
from tests.fakes.scripted_chat_model import (
    FakeChatModel,
    ModelTurn,
    ScriptedToolCall,
)

_PREFIX = "/api/workflow-builder"
_WAIT_SECONDS = 20.0
_HANG_SECONDS = 60.0  # a scripted model call that only a stop or a cap can end
_MANIFEST: dict[str, Any] = {"id": "wf-one", "steps": [{"agent": "custom-agent"}]}
_LIST_AGENTS = ScriptedToolCall("get_builder_models", {})
_WRITE_MANIFEST = ScriptedToolCall(
    "write_file",
    {"file_path": "/workflows/a.workflow.json", "content": json.dumps(_MANIFEST)},
)

Frame = dict[str, Any]


# --- Environment -----------------------------------------------------------------------


@dataclass
class BuilderEnv:
    """Everything one test needs: the HTTP client, the stores and the scripted model."""

    client: httpx.AsyncClient
    session_factory: sessionmaker[Session]
    user_id: str
    model_id: str
    effort: str | None
    sandbox_root: Path
    model: FakeChatModel | None = None
    opened: list[AsyncIterator[dict[str, str]]] = field(default_factory=list)

    @contextmanager
    def store(self) -> Iterator[BuilderStore]:
        """A Session_Store on its own database session (reads see committed rows)."""
        db = self.session_factory()
        try:
            yield BuilderStore(db)
        finally:
            db.close()

    def script(self, *model_turns: ModelTurn) -> FakeChatModel:
        """Install the scripted model the next Turn will use."""
        self.model = FakeChatModel(turns=tuple(model_turns))
        return self.model


def _new_user(factory: sessionmaker[Session]) -> User:
    """Insert a ``users`` row and return a detached stand-in the auth override serves."""
    user_id = str(uuid.uuid4())
    with factory() as db:
        db.add(
            User(
                id=user_id,
                email=f"{user_id}@example.test",
                cognito_sub=f"sub-{user_id}",
            )
        )
        db.commit()
    return _CallerStub(user_id)  # type: ignore[return-value]


class _CallerStub:
    """The authenticated caller: an enterprise user who may use the builder."""

    def __init__(self, user_id: str) -> None:
        self.id = user_id
        self.tier = "enterprise"
        self.is_admin = False
        self.cognito_sub = f"sub-{user_id}"
        self.preferred_model = None


@pytest.fixture
async def env(
    builder_pg_engine: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[BuilderEnv]:
    """The builder app on the throwaway database, with a scripted chat model.

    The production starter (``lifecycle.start_turn_task``) runs the real ``run_turn``;
    only its ``deps`` are replaced so the agent uses ``env.model`` and ``FakeGate``.
    """
    factory = sessionmaker(
        bind=builder_pg_engine, autoflush=False, expire_on_commit=False
    )
    sandbox_root = tmp_path / "builder"
    monkeypatch.setattr(settings, "BUILDER_SANDBOX_ROOT", str(sandbox_root))
    # Every module that opens its own short-lived database session.
    for module in (turns, stream, lifecycle):
        monkeypatch.setattr(module, "SessionLocal", factory)

    view = builder_models("enterprise")
    chosen = next(entry for entry in view.chat if entry.id == view.default_chat_id)
    effort = chosen.reasoning.default_effort if chosen.reasoning.levels else None
    user = _new_user(factory)

    holder = BuilderEnv(
        client=None,  # type: ignore[arg-type]  # set below, once the app exists
        session_factory=factory,
        user_id=user.id,
        model_id=chosen.id,
        effort=effort,
        sandbox_root=sandbox_root,
    )

    real_run_turn = lifecycle.run_turn

    async def run_turn_with_fakes(turn: Any, request: Any) -> None:
        assert holder.model is not None, "the test must call env.script() first"
        deps = TurnDeps(chat_model=holder.model, gate=FakeGate())
        await real_run_turn(turn, request, deps)

    monkeypatch.setattr(lifecycle, "run_turn", run_turn_with_fakes)

    def get_test_db() -> Iterator[Session]:
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = get_test_db
    app.dependency_overrides[get_current_principal] = lambda: (
        user,
        principal_for(user),
    )
    app.dependency_overrides[get_capacity_gate] = lambda: lambda _user: None

    set_event_bus(None)
    set_turn_starter(lifecycle.start_turn_task)
    get_builder_readiness().mark_ready()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        holder.client = client
        try:
            yield holder
        finally:
            for opened in holder.opened:
                await opened.aclose()  # type: ignore[attr-defined]
            await stop_all("shutdown", persist_seconds=5.0)
            turns._LIVE_TURNS.clear()
            turns._TURN_TASKS.clear()
            set_turn_starter(None)
            set_event_bus(None)
            get_builder_readiness().mark_unavailable()


# --- Helpers ---------------------------------------------------------------------------


async def _eventually(
    check: Callable[[], Any], what: str, *, timeout: float = _WAIT_SECONDS
) -> Any:
    """Poll ``check`` until it returns something truthy; fail with ``what`` otherwise."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        value = check()
        if value:
            return value
        if loop.time() > deadline:
            raise AssertionError(f"timed out waiting for {what}")
        await asyncio.sleep(0.05)


async def _create_session(env: BuilderEnv) -> str:
    response = await env.client.post(
        f"{_PREFIX}/sessions",
        json={"mode": "create", "model_id": env.model_id, "effort": env.effort},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def _send(
    env: BuilderEnv, session_id: str, content: str = "Build me a workflow"
) -> httpx.Response:
    return await env.client.post(
        f"{_PREFIX}/sessions/{session_id}/messages",
        json={
            "content": content,
            "model_id": env.model_id,
            "effort": env.effort,
            "canvas_state": {"steps": []},
            "client_message_id": uuid.uuid4().hex,
        },
    )


def _open_stream(env: BuilderEnv, session_id: str) -> AsyncIterator[dict[str, str]]:
    """The frame generator the SSE route serves, bound to this test's stores."""

    def snapshot_fn() -> Any:
        with env.store() as store:
            return build_snapshot(session_id, user_id=env.user_id, store=store)

    async def never_revoked() -> str | None:
        return None

    frames = stream.iter_session_frames(
        session_id=session_id,
        bus=get_event_bus(),
        snapshot_fn=snapshot_fn,
        revocation_check=never_revoked,
    )
    env.opened.append(frames)
    return frames


async def _next_frame(frames: AsyncIterator[dict[str, str]]) -> Frame:
    async with asyncio.timeout(_WAIT_SECONDS):
        parsed: Frame = json.loads((await anext(frames))["data"])
    return parsed


async def _frames_until(
    frames: AsyncIterator[dict[str, str]], final_type: str
) -> list[Frame]:
    """Read frames up to and including the first of ``final_type``."""
    seen: list[Frame] = []
    while not seen or seen[-1]["type"] != final_type:
        seen.append(await _next_frame(frames))
    return seen


def _assistant(env: BuilderEnv, turn_id: str) -> WorkflowBuilderMessage | None:
    with env.store() as store:
        return store.get_message(env.user_id, turn_id)


def _tool_rows(env: BuilderEnv, turn_id: str) -> list[WorkflowBuilderMessage]:
    with env.store() as store:
        return store.list_tool_rows(env.user_id, turn_id)


async def _await_status(
    env: BuilderEnv, turn_id: str, status: str
) -> WorkflowBuilderMessage:
    def check() -> WorkflowBuilderMessage | None:
        row = _assistant(env, turn_id)
        return row if row is not None and row.status == status else None

    return await _eventually(check, f"turn {turn_id} to reach status {status}")


# --- 202, then the stream (Req 21.3, 21.4) ----------------------------------------------


async def test_send_message_returns_202_then_streams_turn_events_when_turn_runs(
    env: BuilderEnv,
) -> None:
    env.script(ModelTurn(text=("Hello ", "there")))
    session_id = await _create_session(env)
    frames = _open_stream(env, session_id)
    first = await _next_frame(frames)

    response = await _send(env, session_id)
    body = response.json()
    events = await _frames_until(frames, "turn_completed")

    assert response.status_code == 202
    assert set(body) == {"turn_id", "message_id", "replayed"}
    assert body["replayed"] is False
    assert first["type"] == "snapshot"
    assert first["data"]["state"] == "idle"
    assert events[0]["type"] == "turn_started"
    assert events[0]["data"]["turn_id"] == body["turn_id"]
    assert events[0]["data"]["message_id"] == body["message_id"]
    assert "stage" in {e["type"] for e in events}
    assert "".join(e["data"]["text"] for e in events if e["type"] == "text") == (
        "Hello there"
    )
    seqs = [e["data"]["seq"] for e in events if "seq" in e["data"]]
    assert seqs == list(range(1, len(seqs) + 1))
    assert events[-1]["data"]["status"] == "completed"

    row = await _await_status(env, body["turn_id"], MESSAGE_STATUS_COMPLETED)
    assert row.content == "Hello there"
    assert row.reply_to_message_id == body["message_id"]
    with env.store() as store:
        user_row = store.get_message(env.user_id, body["message_id"])
    assert user_row is not None
    assert user_row.role == MESSAGE_ROLE_USER
    assert user_row.content == "Build me a workflow"


# --- 409 on a second Turn (Req 21.7) -----------------------------------------------------


async def test_send_message_returns_409_and_stores_nothing_when_turn_is_running(
    env: BuilderEnv,
) -> None:
    model = env.script(ModelTurn(text=("slow",), delay=_HANG_SECONDS))
    session_id = await _create_session(env)
    first = await _send(env, session_id)
    assert first.status_code == 202
    turn_id = first.json()["turn_id"]

    second = await _send(env, session_id, content="A second message")

    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "turn_running"
    with env.store() as store:
        messages = store.list_messages(env.user_id, session_id)
    user_messages = [m for m in messages if m.role == MESSAGE_ROLE_USER]
    assert [m.content for m in user_messages] == ["Build me a workflow"]
    assert get_live_turn(session_id) is not None
    assert get_live_turn(session_id).turn_id == turn_id  # type: ignore[union-attr]

    cancel = await env.client.post(
        f"{_PREFIX}/sessions/{session_id}/turns/{turn_id}/cancel"
    )
    assert cancel.status_code == 202
    await _await_status(env, turn_id, MESSAGE_STATUS_CANCELLED)
    assert model.call_count <= 1  # the refused message never reached the model


# --- Stream drop while the Turn completes (Req 21.6) -------------------------------------


async def test_turn_completes_and_stores_result_when_stream_drops_mid_turn(
    env: BuilderEnv,
) -> None:
    env.script(
        ModelTurn(text=("part one ",), tool_calls=(_LIST_AGENTS,)),
        ModelTurn(text=("final answer",), delay=1.0),
    )
    session_id = await _create_session(env)
    frames = _open_stream(env, session_id)
    await _next_frame(frames)  # snapshot
    sent = await _send(env, session_id)
    turn_id = sent.json()["turn_id"]
    await _frames_until(frames, "turn_started")

    await frames.aclose()  # type: ignore[attr-defined]  # the client goes away mid-Turn

    assert get_event_bus().subscriber_count(session_id) == 0
    assert (_assistant(env, turn_id) or pytest.fail("no row")).status == (
        MESSAGE_STATUS_RUNNING
    )
    row = await _await_status(env, turn_id, MESSAGE_STATUS_COMPLETED)
    assert "final answer" in row.content
    assert row.ended_at is not None

    reconnect = _open_stream(env, session_id)
    snapshot = await _next_frame(reconnect)
    assert snapshot["type"] == "snapshot"
    assert snapshot["data"]["state"] == "idle"
    assert snapshot["data"]["latest_message_id"] == turn_id
    detail = await env.client.get(f"{_PREFIX}/sessions/{session_id}")
    assistant = [m for m in detail.json()["messages"] if m["role"] == "assistant"]
    assert [m["status"] for m in assistant] == ["completed"]


# --- Time cap with an unproposed revision (Req 23.18) ------------------------------------


async def test_turn_ends_timed_out_and_stores_unproposed_revision_when_cap_hits(
    env: BuilderEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "BUILDER_TURN_TIMEOUT_SECONDS", 3)
    env.script(
        ModelTurn(tool_calls=(_WRITE_MANIFEST,)),
        ModelTurn(text=("too late",), delay=_HANG_SECONDS),
    )
    session_id = await _create_session(env)
    frames = _open_stream(env, session_id)
    await _next_frame(frames)  # snapshot
    sent = await _send(env, session_id)
    turn_id = sent.json()["turn_id"]

    events = await _frames_until(frames, "turn_completed")
    row = await _await_status(env, turn_id, MESSAGE_STATUS_TIMED_OUT)

    assert events[-1]["data"]["status"] == "timed_out"
    assert events[-1]["data"]["stop_reason"] == "time"
    assert row.stop_reason == "time"
    with env.store() as store:
        unproposed = store.get_latest_revisions(env.user_id, session_id).unproposed
        running = store.get_running_turn(env.user_id, session_id)
    assert unproposed is not None
    assert unproposed.kind == DRAFT_KIND_UNPROPOSED
    assert unproposed.manifest == _MANIFEST
    assert unproposed.source_file == "/workflows/a.workflow.json"
    assert unproposed.source_turn_id == turn_id
    assert running is None  # the Session takes a new message

    detail = (await env.client.get(f"{_PREFIX}/sessions/{session_id}")).json()
    assert detail["latest_unproposed"]["manifest"] == _MANIFEST


# --- Tool rows are stored while the Turn runs (Req 24.5) ---------------------------------


async def test_tool_row_is_readable_from_database_when_turn_is_still_running(
    env: BuilderEnv,
) -> None:
    env.script(
        ModelTurn(tool_calls=(_LIST_AGENTS,)),
        ModelTurn(text=("done",), delay=1.5),
    )
    session_id = await _create_session(env)
    turn_id = (await _send(env, session_id)).json()["turn_id"]

    rows = await _eventually(lambda: _tool_rows(env, turn_id), "a stored tool row")

    mid_turn = _assistant(env, turn_id)
    assert mid_turn is not None
    assert mid_turn.status == MESSAGE_STATUS_RUNNING
    assert rows[0].role == MESSAGE_ROLE_TOOL
    assert rows[0].status == MESSAGE_STATUS_TOOL_OK
    assert rows[0].turn_id == turn_id
    assert isinstance(rows[0].tool, dict)
    assert rows[0].tool["tool"] == "get_builder_models"
    await _await_status(env, turn_id, MESSAGE_STATUS_COMPLETED)
    assert len(_tool_rows(env, turn_id)) == len(rows)


# --- Startup sweep (Req 22.2) ------------------------------------------------------------


async def test_startup_sweep_marks_running_turn_interrupted_and_keeps_its_work(
    env: BuilderEnv,
) -> None:
    model = env.script(ModelTurn(text=("after restart",)))
    session_id = await _create_session(env)
    with env.store() as store:
        begun = store.begin_turn(
            env.user_id,
            session_id,
            content="left running by a crash",
            canvas_state={"steps": []},
            client_message_id=uuid.uuid4().hex,
            model_id=env.model_id,
            effort=env.effort,
            skill_hash="skill-hash",
        )
    leftover_id = str(begun.assistant_message.id)
    sandbox = BuilderSandbox(env.user_id, session_id)
    sandbox.ensure()
    sandbox.path_for("/workflows/swept.workflow.json").write_text(
        json.dumps(_MANIFEST), encoding="utf-8"
    )
    blocked = await _send(env, session_id)
    assert blocked.status_code == 409  # before the sweep, the Session looks busy

    await lifecycle.builder_startup(store_scope=env.store)

    row = _assistant(env, leftover_id)
    assert row is not None
    assert row.status == MESSAGE_STATUS_INTERRUPTED
    assert row.stop_reason == "restart"
    with env.store() as store:
        unproposed = store.get_latest_revisions(env.user_id, session_id).unproposed
    assert unproposed is not None
    assert unproposed.manifest == _MANIFEST
    assert unproposed.source_file == "/workflows/swept.workflow.json"
    assert sandbox.path_for("/workflows/swept.workflow.json").is_file()
    assert get_builder_readiness().is_ready
    assert get_live_turn(session_id) is None
    assert model.call_count == 0  # the sweep starts no Turn and makes no model call

    after = await _send(env, session_id)
    assert after.status_code == 202  # the Session no longer answers 409
    await _await_status(env, after.json()["turn_id"], MESSAGE_STATUS_COMPLETED)


# --- Shutdown step (Req 22.1) ------------------------------------------------------------


async def test_shutdown_stops_live_turn_with_partial_text_and_closes_stream(
    env: BuilderEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The checkpointer pool is another subsystem; the builder step runs first.
    monkeypatch.setattr(
        "app.agents.checkpointer.close_checkpointer", AsyncMock(return_value=None)
    )
    model = env.script(
        ModelTurn(text=("Working on it",), tool_calls=(_LIST_AGENTS,)),
        ModelTurn(text=("late",), delay=_HANG_SECONDS),
    )
    session_id = await _create_session(env)
    frames = _open_stream(env, session_id)
    await _next_frame(frames)  # snapshot
    turn_id = (await _send(env, session_id)).json()["turn_id"]
    await _eventually(
        lambda: _tool_rows(env, turn_id) and model.call_count >= 2,
        "the Turn to be waiting on its second model call",
    )
    reader = asyncio.create_task(_frames_until_closed(frames))

    summary = await run_shutdown.shutdown_run_infrastructure()

    assert summary["builder_turns_stopped"] is True
    row = _assistant(env, turn_id)
    assert row is not None
    assert row.status == MESSAGE_STATUS_INTERRUPTED
    assert row.stop_reason == "shutdown"
    assert "Working on it" in row.content
    async with asyncio.timeout(_WAIT_SECONDS):
        events = await reader  # the stream ends instead of staying open
    assert events[-1]["type"] == "turn_completed"
    assert events[-1]["data"]["status"] == "interrupted"
    assert get_live_turn(session_id) is None
    refused = await _send(env, session_id)
    assert refused.status_code == 503
    assert refused.json()["detail"]["code"] == "builder_unavailable"


async def _frames_until_closed(frames: AsyncIterator[dict[str, str]]) -> list[Frame]:
    """Read every frame until the generator ends."""
    seen: list[Frame] = []
    async for frame in frames:
        seen.append(json.loads(frame["data"]))
    return seen
