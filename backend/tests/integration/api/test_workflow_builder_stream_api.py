"""``GET /api/workflow-builder/sessions/{id}/events`` (Session_Stream) on real PostgreSQL.

Covers task 22.5 of the AI Workflow Builder spec (Req 31.4, 40.1 to 40.5):

* snapshot first, then live events, also while a Turn is running (Req 40.4);
* two clients of one Session see the same events in the same order, and a client of
  another Session sees none of them (Req 40.5);
* the stream stays open when a Turn completes and delivers the next ``turn_started``
  on the same connection (Req 40.3);
* ``DELETE /sessions/{id}`` sends ``session_deleted`` on every open stream and then
  closes it (Req 31.4);
* the ``X-Accel-Buffering: no`` and ``Cache-Control: no-cache`` headers (Req 40.2);
* the keep-alive ping: the default of 15 s and the ping on the wire while idle, during
  a Turn and between Turns (Req 40.1).

Why a hand-written ASGI driver: ``TestClient`` and ``httpx.ASGITransport`` hold the
response back until the body ends, and this body never ends on its own. The driver in
this module calls the app with ``receive``/``send`` and hands each body chunk to the
test as it is sent, so a test reads frames one at a time and closes the connection by
sending ``http.disconnect``. Everything runs on the test's event loop, which the
in-process :class:`SessionEventBus` requires.

Database: real PostgreSQL, never SQLite. The module builds a private throwaway
database from ``tests/integration/conftest.py`` (testcontainers, needs Docker, errors
at setup without it) or from ``PYTEST_POSTGRES_ADMIN_URL``, and upgrades it with
Alembic to head. These tests run on the Docker-capable CI runner; locally they only
need to collect.

Faked: the authentication dependencies (the user is a real ``users`` row and the
principal comes from ``tests/fakes/principal.py``) and the periodic revocation check
(its timing is covered with the stream unit tests). Turn events are published on the
real bus the way the Turn_Runner does.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Callable, Generator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

import app.api.workflow_builder.stream as stream_module
from app.agents.workflow_builder.events import (
    BuilderEvent,
    StageChanged,
    Text,
    TokenUsage,
    TurnCompleted,
    TurnStarted,
    to_wire,
)
from app.agents.workflow_builder.stages import Stage, label_for
from app.api.workflow_builder import router as builder_router
from app.api.workflow_builder.admission import (
    BuilderReadiness,
    get_builder_readiness,
)
from app.api.workflow_builder.bus import SessionEventBus
from app.api.workflow_builder.store import BuilderStore
from app.api.workflow_builder.turns import (
    LiveTurn,
    register_live_turn,
    release_live_turn,
    set_event_bus,
)
from app.core.config import Settings, settings
from app.core.dependencies import bearer_scheme, get_current_principal
from app.models.database import get_db
from app.models.user import User
from tests.factories.builder_session_factory import BuilderSessionFactory
from tests.fakes.principal import principal_for

_WAIT_SECONDS = 5.0
_PING_SECONDS = 1  # SSE_KEEPALIVE_PING_SECONDS is an int; 1 s keeps the tests short
_QUIET_SECONDS = 0.3
_EVENTS_PATH = "/api/workflow-builder/sessions/{session_id}/events"
_SESSION_PATH = "/api/workflow-builder/sessions/{session_id}"
_FIXED_TIME = datetime(2030, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


# --- SSE driver --------------------------------------------------------------------------


@dataclass(frozen=True)
class SseFrame:
    """One parsed SSE frame: a ``{"type", "data"}`` envelope or a comment (ping)."""

    envelope: dict[str, Any] | None
    comment: str | None


def _parse_frame(raw: str) -> SseFrame:
    lines = [line for line in raw.split("\n") if line]
    data_lines = [
        line[len("data:") :].lstrip() for line in lines if line.startswith("data:")
    ]
    if data_lines:
        return SseFrame(envelope=json.loads("\n".join(data_lines)), comment=None)
    comments = [line[1:].strip() for line in lines if line.startswith(":")]
    return SseFrame(envelope=None, comment=" ".join(comments))


class SseConnection:
    """One open GET request against the app, read frame by frame."""

    def __init__(self, app: FastAPI, path: str) -> None:
        self._app = app
        self._path = path
        self._disconnect = asyncio.Event()
        self._started = asyncio.Event()
        self._finished = asyncio.Event()
        self._chunks: asyncio.Queue[bytes] = asyncio.Queue()
        self._buffer = ""
        self._request_sent = False
        self._error: BaseException | None = None
        self._task: asyncio.Task[None] | None = None
        self.status = 0
        self.headers: dict[str, str] = {}

    async def open(self) -> None:
        """Start the request and wait until the response headers are known."""
        self._task = asyncio.create_task(self._run())
        await asyncio.wait_for(self._started.wait(), _WAIT_SECONDS)
        if self._error is not None:
            raise self._error

    async def close(self) -> None:
        """Disconnect the client and wait for the app to finish."""
        self._disconnect.set()
        if self._task is not None:
            await asyncio.wait_for(self._task, _WAIT_SECONDS)

    @property
    def closed(self) -> bool:
        """True once the server ended the response."""
        return self._finished.is_set()

    async def wait_closed(self) -> None:
        """Wait until the server ends the response and the app returns."""
        await asyncio.wait_for(self._finished.wait(), _WAIT_SECONDS)
        if self._task is not None:
            await asyncio.wait_for(self._task, _WAIT_SECONDS)

    async def next_frame(self, timeout: float = _WAIT_SECONDS) -> SseFrame:
        """Return the next complete frame. Raises ``TimeoutError`` when none arrives."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while "\n\n" not in self._buffer:
            remaining = max(0.0, deadline - loop.time())
            chunk = await asyncio.wait_for(self._chunks.get(), remaining)
            self._buffer += chunk.decode("utf-8").replace("\r\n", "\n")
        raw, self._buffer = self._buffer.split("\n\n", 1)
        return _parse_frame(raw)

    async def next_event(self, timeout: float = _WAIT_SECONDS) -> dict[str, Any]:
        """Return the next ``{"type", "data"}`` envelope, skipping keep-alive pings."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            frame = await self.next_frame(max(0.0, deadline - loop.time()))
            if frame.envelope is not None:
                return frame.envelope

    async def expect_ping(self, timeout: float = _WAIT_SECONDS) -> str:
        """Return the next keep-alive comment. An event arriving first fails the test."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            frame = await self.next_frame(max(0.0, deadline - loop.time()))
            if frame.comment is not None:
                return frame.comment
            raise AssertionError(f"expected a ping, got event {frame.envelope}")

    async def expect_no_event(self, duration: float = _QUIET_SECONDS) -> None:
        """Assert that no event arrives for ``duration`` seconds (pings are ignored)."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + duration
        try:
            while True:
                frame = await self.next_frame(max(0.0, deadline - loop.time()))
                assert frame.envelope is None, f"unexpected event {frame.envelope}"
        except TimeoutError:
            return

    async def _run(self) -> None:
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": self._path,
            "raw_path": self._path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [
                (b"host", b"testserver"),
                (b"accept", b"text/event-stream"),
                (b"authorization", b"Bearer test-token"),
            ],
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 50000),
        }
        try:
            await self._app(scope, self._receive, self._send)
        except BaseException as exc:  # noqa: BLE001 - handed to the test thread of control
            self._error = exc
        finally:
            self._started.set()
            self._finished.set()

    async def _receive(self) -> dict[str, Any]:
        if not self._request_sent:
            self._request_sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await self._disconnect.wait()
        return {"type": "http.disconnect"}

    async def _send(self, message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            self.status = message["status"]
            self.headers = {
                key.decode("latin-1").lower(): value.decode("latin-1")
                for key, value in message["headers"]
            }
            self._started.set()
        elif message["type"] == "http.response.body":
            body = message.get("body", b"")
            if body:
                self._chunks.put_nowait(body)
            if not message.get("more_body", False):
                self._finished.set()


# --- Fixtures ----------------------------------------------------------------------------


@dataclass
class StreamEnv:
    """The app and the data a test needs."""

    app: FastAPI
    bus: SessionEventBus
    session_factory: sessionmaker[Session]
    user_id: str
    make_session: Callable[[], str]

    @asynccontextmanager
    async def open_stream(self, session_id: str) -> AsyncIterator[SseConnection]:
        """Open the stream, read the snapshot (so the client is subscribed) and yield."""
        conn = SseConnection(self.app, _EVENTS_PATH.format(session_id=session_id))
        await conn.open()
        try:
            assert conn.status == 200
            first = await conn.next_event()
            assert first["type"] == "snapshot"
            yield conn
        finally:
            await conn.close()

    @asynccontextmanager
    async def open_raw_stream(self, session_id: str) -> AsyncIterator[SseConnection]:
        """Open the stream without reading any frame (for header checks)."""
        conn = SseConnection(self.app, _EVENTS_PATH.format(session_id=session_id))
        await conn.open()
        try:
            yield conn
        finally:
            await conn.close()


@pytest.fixture
def stream_env(
    builder_pg_engine: Engine, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Generator[StreamEnv, None, None]:
    """The builder router on a migrated database, with auth stubbed and a fresh bus."""
    session_factory: sessionmaker[Session] = sessionmaker(
        bind=builder_pg_engine, autoflush=False, expire_on_commit=False
    )
    user_id = str(uuid.uuid4())
    with session_factory() as db:
        user = User(
            id=user_id,
            email=f"{user_id}@example.test",
            cognito_sub=f"sub-{user_id}",
            tier="enterprise",
        )
        db.add(user)
        db.commit()
    principal = principal_for(user)

    readiness = BuilderReadiness()
    readiness.mark_ready()

    def override_db() -> Generator[Session, None, None]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    async def no_revocation(**_: Any) -> None:
        return None

    app = FastAPI()
    app.include_router(builder_router)
    app.dependency_overrides[get_current_principal] = lambda: (user, principal)
    app.dependency_overrides[bearer_scheme] = lambda: HTTPAuthorizationCredentials(
        scheme="Bearer", credentials="test-token"
    )
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_builder_readiness] = lambda: readiness

    monkeypatch.setattr(settings, "SSE_KEEPALIVE_PING_SECONDS", _PING_SECONDS)
    monkeypatch.setattr(settings, "BUILDER_SANDBOX_ROOT", str(tmp_path))
    # The generator opens its own sessions (BUG-004); point them at the test database.
    monkeypatch.setattr(stream_module, "SessionLocal", session_factory)
    monkeypatch.setattr(stream_module, "_run_revocation_check", no_revocation)

    bus = SessionEventBus()
    set_event_bus(bus)

    def make_session() -> str:
        with session_factory() as db:
            row = BuilderStore(db).create_session(
                user_id,
                **BuilderSessionFactory.create_kwargs(
                    seed_manifest={"steps": []}, seed_manifest_hash="seed-hash"
                ),
            )
            return str(row.id)

    try:
        yield StreamEnv(
            app=app,
            bus=bus,
            session_factory=session_factory,
            user_id=user_id,
            make_session=make_session,
        )
    finally:
        set_event_bus(None)


# --- Event builders ----------------------------------------------------------------------


def _turn_started(turn_id: str, seq: int = 1) -> TurnStarted:
    return TurnStarted(
        ts=_FIXED_TIME,
        turn_id=turn_id,
        seq=seq,
        message_id=f"msg-{turn_id}",
        model_id="model-1",
        effort=None,
        skill_hash="skill-hash-1",
    )


def _stage(turn_id: str, seq: int) -> StageChanged:
    return StageChanged(
        ts=_FIXED_TIME,
        turn_id=turn_id,
        seq=seq,
        stage=Stage.STARTING,
        label=label_for(Stage.STARTING),
    )


def _text(turn_id: str, seq: int, text: str = "Hello") -> Text:
    return Text(ts=_FIXED_TIME, turn_id=turn_id, seq=seq, text=text)


def _turn_completed(turn_id: str, seq: int) -> TurnCompleted:
    return TurnCompleted(
        ts=_FIXED_TIME,
        turn_id=turn_id,
        seq=seq,
        status="completed",
        outcome="reply",
        stop_reason=None,
        message_id=f"reply-{turn_id}",
        revision=None,
        usage=TokenUsage.zero(),
    )


def _wire(event: BuilderEvent) -> dict[str, Any]:
    """The envelope a client reads for ``event``."""
    event_type, data = to_wire(event)
    return {"type": event_type, "data": data}


# --- Tests -------------------------------------------------------------------------------


class TestSnapshotFirst:
    """Req 40.4: ``snapshot`` first, then live events."""

    async def test_stream_session_events_sends_idle_snapshot_first_when_no_turn_runs(
        self, stream_env: StreamEnv
    ) -> None:
        session_id = stream_env.make_session()
        conn = SseConnection(stream_env.app, _EVENTS_PATH.format(session_id=session_id))
        await conn.open()
        try:
            first = await conn.next_event()

            assert first["type"] == "snapshot"
            assert first["data"]["state"] == "idle"
            assert first["data"]["running_turn"] is None
            assert first["data"]["latest_message_id"] is None
            assert first["data"]["latest_revision"] == 0  # the seed of the edit session
        finally:
            await conn.close()

    async def test_stream_session_events_sends_live_event_after_snapshot_when_event_published(
        self, stream_env: StreamEnv
    ) -> None:
        session_id = stream_env.make_session()
        async with stream_env.open_stream(session_id) as conn:
            event = _turn_started("turn-1")

            stream_env.bus.publish(session_id, event)

            assert await conn.next_event() == _wire(event)

    async def test_stream_session_events_sends_running_snapshot_first_when_turn_is_running(
        self, stream_env: StreamEnv
    ) -> None:
        session_id = stream_env.make_session()
        live = LiveTurn(
            session_id=session_id,
            turn_id="turn-live",
            user_message_id="msg-live",
            user_id=stream_env.user_id,
            model_id="model-1",
            effort=None,
            seq=2,
            stage=Stage.STARTING,
        )
        register_live_turn(live)
        try:
            conn = SseConnection(
                stream_env.app, _EVENTS_PATH.format(session_id=session_id)
            )
            await conn.open()
            try:
                first = await conn.next_event()
                stream_env.bus.publish(session_id, _text("turn-live", seq=3))
                second = await conn.next_event()
            finally:
                await conn.close()
        finally:
            release_live_turn(live)

        assert first["type"] == "snapshot"
        assert first["data"]["state"] == "running"
        assert first["data"]["running_turn"]["turn_id"] == "turn-live"
        assert first["data"]["running_turn"]["through_seq"] == 2
        assert second["type"] == "text"
        assert second["data"]["seq"] == 3


class TestFanOut:
    """Req 40.5: every client of the Session gets every live event."""

    async def test_stream_session_events_delivers_same_events_when_two_clients_connected(
        self, stream_env: StreamEnv
    ) -> None:
        session_id = stream_env.make_session()
        other_session_id = stream_env.make_session()
        events: list[BuilderEvent] = [
            _turn_started("turn-1", 1),
            _stage("turn-1", 2),
            _text("turn-1", 3),
            _turn_completed("turn-1", 4),
        ]
        async with (
            stream_env.open_stream(session_id) as first,
            stream_env.open_stream(session_id) as second,
            stream_env.open_stream(other_session_id) as bystander,
        ):
            assert stream_env.bus.subscriber_count(session_id) == 2

            for event in events:
                stream_env.bus.publish(session_id, event)

            received_first = [await first.next_event() for _ in events]
            received_second = [await second.next_event() for _ in events]

            assert received_first == [_wire(event) for event in events]
            assert received_second == received_first
            await bystander.expect_no_event()


class TestStaysOpen:
    """Req 40.3: the stream outlives a Turn and carries the next ``turn_started``."""

    async def test_stream_session_events_delivers_next_turn_started_when_turn_completed_earlier(
        self, stream_env: StreamEnv
    ) -> None:
        session_id = stream_env.make_session()
        first_turn = [
            _turn_started("turn-1", 1),
            _text("turn-1", 2),
            _turn_completed("turn-1", 3),
        ]
        next_turn = _turn_started("turn-2", 1)
        async with (
            stream_env.open_stream(session_id) as first,
            stream_env.open_stream(session_id) as second,
        ):
            # Idle, with no Turn: a ping arrives, so the connection is still open.
            await first.expect_ping()
            await second.expect_ping()

            for event in first_turn:
                stream_env.bus.publish(session_id, event)
            for conn in (first, second):
                for event in first_turn:
                    assert await conn.next_event() == _wire(event)

            # Turn 1 is over. Neither stream closed and both are still subscribed.
            await first.expect_no_event()
            assert not first.closed
            assert not second.closed
            assert stream_env.bus.subscriber_count(session_id) == 2

            stream_env.bus.publish(session_id, next_turn)

            assert await first.next_event() == _wire(next_turn)
            assert await second.next_event() == _wire(next_turn)


class TestSessionDeleted:
    """Req 31.4: ``session_deleted`` on every open stream, then the streams close."""

    async def test_delete_session_closes_every_stream_when_session_deleted(
        self, stream_env: StreamEnv
    ) -> None:
        session_id = stream_env.make_session()
        other_session_id = stream_env.make_session()
        async with (
            stream_env.open_stream(session_id) as first,
            stream_env.open_stream(session_id) as second,
            stream_env.open_stream(other_session_id) as bystander,
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=stream_env.app),
                base_url="http://testserver",
            ) as client:
                response = await client.delete(
                    _SESSION_PATH.format(session_id=session_id)
                )

            assert response.status_code == 204
            for conn in (first, second):
                event = await conn.next_event()
                assert event["type"] == "session_deleted"
                assert set(event["data"]) == {"ts"}
                await conn.wait_closed()
            assert stream_env.bus.subscriber_count(session_id) == 0
            # The other Session's stream is untouched.
            await bystander.expect_no_event()
            assert not bystander.closed

        with stream_env.session_factory() as db:
            assert BuilderStore(db).get_session(stream_env.user_id, session_id) is None
            assert (
                BuilderStore(db).get_session(stream_env.user_id, other_session_id)
                is not None
            )

    async def test_stream_session_events_answers_404_when_session_was_deleted(
        self, stream_env: StreamEnv
    ) -> None:
        session_id = stream_env.make_session()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=stream_env.app),
            base_url="http://testserver",
        ) as client:
            await client.delete(_SESSION_PATH.format(session_id=session_id))

            response = await client.get(_EVENTS_PATH.format(session_id=session_id))

        assert response.status_code == 404


class TestHeaders:
    """Req 40.2: the proxy must not buffer the stream."""

    async def test_stream_session_events_sets_streaming_headers_when_connected(
        self, stream_env: StreamEnv
    ) -> None:
        session_id = stream_env.make_session()
        async with stream_env.open_raw_stream(session_id) as conn:
            assert conn.status == 200
            assert conn.headers["content-type"].startswith("text/event-stream")
            assert conn.headers["x-accel-buffering"] == "no"
            assert conn.headers["cache-control"] == "no-cache"


class TestKeepAlive:
    """Req 40.1: the keep-alive ping, with the interval taken from settings."""

    def test_settings_keepalive_ping_defaults_to_15_seconds_when_not_overridden(
        self,
    ) -> None:
        assert Settings.model_fields["SSE_KEEPALIVE_PING_SECONDS"].default == 15

    async def test_stream_session_events_sends_ping_when_idle_during_turn_and_between_turns(
        self, stream_env: StreamEnv
    ) -> None:
        session_id = stream_env.make_session()
        async with stream_env.open_stream(session_id) as conn:
            # No Turn is running.
            await conn.expect_ping()

            # A Turn is running.
            stream_env.bus.publish(session_id, _turn_started("turn-1", 1))
            assert (await conn.next_event())["type"] == "turn_started"
            await conn.expect_ping()

            # The Turn is over.
            stream_env.bus.publish(session_id, _turn_completed("turn-1", 2))
            assert (await conn.next_event())["type"] == "turn_completed"
            await conn.expect_ping()
