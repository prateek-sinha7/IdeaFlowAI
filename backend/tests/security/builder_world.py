"""A small, real-routes test world for the AI Workflow Builder security tests.

The security files for the builder (``test_workflow_builder_access.py``,
``test_workflow_builder_idor.py``) need the same setup: the builder router mounted
on a minimal FastAPI app, a directory of callers with different tiers, a Session_Store
behind it, and spies on every place a refused request must not reach (the turn
starter, the capacity gate, the event bus, the stream generator, the sandbox folder).

This module holds that setup so the two files state only their attack and their
assertion. It is a helper, not a test module, and it asserts nothing.

What is real: ``require_builder_access`` (entitlement, readiness), every route
handler, admission, ``BuilderSandbox`` and the event bus registry.
What is replaced:

* authentication. With ``real_auth=False`` the dependency ``get_current_principal``
  maps the bearer token to a caller of the directory (a missing token still answers
  401, through the real ``bearer_scheme``). With ``real_auth=True`` the real
  dependency runs, with ``get_db`` replaced by a database that records every use.
* the Session_Store. ``kind="in_memory"`` uses ``InMemoryBuilderStore`` and a
  recording database mock; ``kind="postgres"`` uses the real ``BuilderStore`` on a
  throwaway PostgreSQL database (CI; see ``conftest.builder_pg_engine``).
* the turn starter, the capacity gate and the stream generator, which record their
  calls. A refused request must leave all three untouched.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from unittest.mock import MagicMock

import pytest
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.agents.workflow_builder.events import BuilderEvent
from app.agents.workflow_builder.model_catalog_view import builder_models
from app.agents.workflow_builder.sandbox import BuilderSandbox
from app.api import workflow_builder
from app.api.workflow_builder import stream, turns
from app.api.workflow_builder.admission import (
    BuilderReadiness,
    get_builder_readiness,
    get_capacity_gate,
    get_turn_starter,
)
from app.api.workflow_builder.bus import SessionEventBus, SessionQueue
from app.api.workflow_builder.store import BuilderStore, get_builder_store
from app.api.workflow_builder.turns import LiveTurn, register_live_turn, set_event_bus
from app.core.config import settings
from app.core.dependencies import bearer_scheme, get_current_principal
from app.core.identity import Principal
from app.models.database import get_db
from app.models.user import User
from app.models.workflow_builder import (
    WorkflowBuilderDraft,
    WorkflowBuilderMessage,
    WorkflowBuilderSession,
)
from tests.factories.builder_session_factory import BuilderSessionFactory
from tests.fakes.builder_store import InMemoryBuilderStore
from tests.fakes.principal import principal_for

__all__ = [
    "API",
    "BuilderWorld",
    "Caller",
    "RecordingBus",
    "RouteCase",
    "Seeded",
    "WorldKind",
    "route_cases",
    "route_signatures",
]

API = "/api/workflow-builder"
WorldKind = Literal["in_memory", "postgres"]

#: One frame the stream spy yields, so a request that gets through answers 200.
_SPY_FRAME = {"data": json.dumps({"type": "snapshot", "data": {}})}


# --- Route table -----------------------------------------------------------------------


@dataclass(frozen=True)
class RouteCase:
    """One builder route and a well-formed request for it.

    Attributes:
        method: HTTP method.
        template: The route path with ``{session_id}`` and ``{turn_id}`` left in.
        body: Builds the JSON body from the model choice, or ``None`` for no body.
    """

    method: str
    template: str
    body: Callable[[dict[str, Any]], dict[str, Any]] | None = None

    @property
    def signature(self) -> str:
        """``METHOD /path`` as the route-contract test writes it."""
        return f"{self.method} {self.template}"

    @property
    def session_scoped(self) -> bool:
        """True when the route names a Session id."""
        return "{session_id}" in self.template

    def url(self, session_id: str, turn_id: str) -> str:
        """The request path for ``session_id`` and ``turn_id``."""
        return self.template.format(session_id=session_id, turn_id=turn_id)


def _create_body(choice: dict[str, Any]) -> dict[str, Any]:
    return {"mode": "create", **choice}


def _message_body(choice: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": "Add a review step",
        "canvas_state": {"steps": []},
        "client_message_id": "cid-0123456789ab",
        **choice,
    }


def _link_body(_choice: dict[str, Any]) -> dict[str, Any]:
    return {"workflow_id": "workflow-1"}


def _undo_body(_choice: dict[str, Any]) -> dict[str, Any]:
    return {"expected_revision": 0}


_SESSION = f"{API}/sessions/{{session_id}}"

#: Every builder route, with the DELETE last so a request series can still use the session.
route_cases: tuple[RouteCase, ...] = (
    RouteCase("GET", f"{API}/models"),
    RouteCase("POST", f"{API}/sessions", _create_body),
    RouteCase("GET", f"{API}/sessions"),
    RouteCase("GET", _SESSION),
    RouteCase("POST", f"{_SESSION}/link", _link_body),
    RouteCase("POST", f"{_SESSION}/messages", _message_body),
    RouteCase("POST", f"{_SESSION}/turns/{{turn_id}}/retry"),
    RouteCase("POST", f"{_SESSION}/turns/{{turn_id}}/cancel"),
    RouteCase("POST", f"{_SESSION}/undo", _undo_body),
    RouteCase("GET", f"{_SESSION}/events"),
    RouteCase("DELETE", _SESSION),
)


def route_signatures(app: FastAPI) -> set[str]:
    """``METHOD /path`` of every builder endpoint mounted on ``app``.

    Descends through included-router wrappers, as ``test_route_contract`` does, because
    ``include_router`` does not flatten routes on this FastAPI version.
    """
    found: set[str] = set()

    def walk(routes: Iterator[Any] | list[Any]) -> None:
        for route in routes:
            included = getattr(route, "original_router", None)
            if included is not None:
                walk(included.routes)
                continue
            path = getattr(route, "path", "")
            methods = getattr(route, "methods", None) or ()
            if path.startswith(API):
                found.update(
                    f"{method} {path}" for method in methods if method != "HEAD"
                )

    walk(app.routes)
    return found


def model_choice() -> dict[str, Any]:
    """A model and effort an enterprise caller may use (what ``GET /models`` offers)."""
    view = builder_models("enterprise")
    entry = next(e for e in view.chat if e.id == view.default_chat_id)
    return {"model_id": entry.id, "effort": entry.reasoning.default_effort}


# --- Callers, spies, seeded rows -------------------------------------------------------


@dataclass(frozen=True)
class Caller:
    """A person who can call the API: a user row and the bearer token that names it."""

    name: str
    user: User
    token: str

    @property
    def user_id(self) -> str:
        """The caller's user id, the authorisation key of every Session."""
        return str(self.user.id)

    @property
    def headers(self) -> dict[str, str]:
        """The ``Authorization`` header this caller sends."""
        return {"Authorization": f"Bearer {self.token}"}


class RecordingBus(SessionEventBus):
    """A ``SessionEventBus`` that records publishes, closes and subscribes."""

    def __init__(self) -> None:
        super().__init__()
        self.publishes: list[tuple[str, BuilderEvent]] = []
        self.closes: list[str] = []
        self.subscribes: list[str] = []

    def publish(self, session_id: str, event: BuilderEvent) -> None:
        """Record the publish, then deliver it."""
        self.publishes.append((session_id, event))
        super().publish(session_id, event)

    def close_session(self, session_id: str, final: BuilderEvent | None) -> None:
        """Record the close, then close the clients."""
        self.closes.append(session_id)
        super().close_session(session_id, final)

    def subscribe(self, session_id: str, snapshot_fn: Callable[..., Any]) -> Any:
        """Record the subscription, then register the client."""
        self.subscribes.append(session_id)
        return super().subscribe(session_id, snapshot_fn)


@dataclass(frozen=True)
class Seeded:
    """A stored Session, optionally with a running Turn.

    Attributes:
        session_id: The Session id.
        turn_id: The running assistant row id, or ``None`` when no Turn was seeded.
        live: The registered ``LiveTurn`` of that Turn, or ``None``.
        sandbox: The Session's sandbox folder, which holds one marker file.
    """

    session_id: str
    turn_id: str | None
    live: LiveTurn | None
    sandbox: Path


@dataclass
class _Spies:
    starts: list[tuple[str, str]] = field(default_factory=list)
    capacity: list[str] = field(default_factory=list)
    frames: list[dict[str, Any]] = field(default_factory=list)


# --- The world -------------------------------------------------------------------------


class BuilderWorld:
    """The builder API on a minimal app, with callers, a store and spies."""

    def __init__(
        self,
        *,
        kind: WorldKind,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        engine: Engine | None = None,
        real_auth: bool = False,
        real_stream: bool = False,
    ) -> None:
        self.kind = kind
        self.real_auth = real_auth
        self.sandbox_root = tmp_path / "builder"
        self.bus = RecordingBus()
        self.spies = _Spies()
        self.callers: dict[str, Caller] = {}
        self.store_memory = InMemoryBuilderStore()
        # The recording database used by the in-memory world (and by the real
        # dependency chain, which must not reach a database before it refuses).
        self.db = MagicMock(name="db")
        self.db.query.return_value.filter.return_value.first.return_value = None
        self._session_factory: sessionmaker[Session] | None = None
        if kind == "postgres":
            assert engine is not None, "the postgres world needs an engine"
            self._session_factory = sessionmaker(
                bind=engine, autoflush=False, expire_on_commit=False
            )
        self._stack = ExitStack()
        monkeypatch.setattr(settings, "BUILDER_SANDBOX_ROOT", str(self.sandbox_root))
        self.real_stream = real_stream
        self._patch_stream(monkeypatch)
        turns._LIVE_TURNS.clear()
        turns._TURN_TASKS.clear()
        set_event_bus(self.bus)
        self.app = self._build_app()
        self.client = self._stack.enter_context(TestClient(self.app))

    # --- construction ---

    def _patch_stream(self, monkeypatch: pytest.MonkeyPatch) -> None:
        spies = self.spies
        memory = self.store_memory

        async def spy_frames(**kwargs: Any) -> Any:
            spies.frames.append(kwargs)
            yield _SPY_FRAME

        @contextmanager
        def memory_snapshot_store() -> Iterator[InMemoryBuilderStore]:
            yield memory

        if self.real_stream:
            # The real generator runs; only the store it opens for snapshots is local.
            monkeypatch.setattr(stream, "_open_snapshot_store", memory_snapshot_store)
        else:
            monkeypatch.setattr(stream, "iter_session_frames", spy_frames)
        if self.kind == "in_memory":
            monkeypatch.setattr(stream, "BuilderStore", lambda _db: memory)

    def _build_app(self) -> FastAPI:
        app = FastAPI()
        app.include_router(workflow_builder.router)
        readiness = BuilderReadiness()
        readiness.mark_ready()
        spies = self.spies

        def starter(turn: LiveTurn, content: str, canvas: dict[str, Any]) -> None:
            del content, canvas
            spies.starts.append((turn.session_id, turn.turn_id))

        def capacity(user: User) -> None:
            spies.capacity.append(str(user.id))

        def override_db() -> Iterator[Any]:
            if self._session_factory is None:
                yield self.db
                return
            session = self._session_factory()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_builder_readiness] = lambda: readiness
        app.dependency_overrides[get_capacity_gate] = lambda: capacity
        app.dependency_overrides[get_turn_starter] = lambda: starter
        if self.kind == "in_memory":
            app.dependency_overrides[get_builder_store] = lambda: self.store_memory
        if not self.real_auth:
            app.dependency_overrides[get_current_principal] = self._principal_override()
        return app

    def _principal_override(self) -> Callable[..., tuple[User, Principal]]:
        directory = self.callers

        def override(
            credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
        ) -> tuple[User, Principal]:
            caller = next(
                (c for c in directory.values() if c.token == credentials.credentials),
                None,
            )
            if caller is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return caller.user, principal_for(caller.user)

        return override

    def close(self) -> None:
        """Stop the client and empty the process-wide Turn registries and bus."""
        self._stack.close()
        turns._LIVE_TURNS.clear()
        turns._TURN_TASKS.clear()
        set_event_bus(None)

    # --- callers ---

    def add_caller(self, name: str, tier: str = "enterprise") -> Caller:
        """Add a user of ``tier``; the postgres world inserts the ``users`` row."""
        user_id = str(uuid.uuid4())
        user = User(
            id=user_id,
            email=f"{user_id}@example.test",
            cognito_sub=f"sub-{user_id}",
            tier=tier,
        )
        if self._session_factory is not None:
            with self._session_factory() as db:
                db.add(user)
                db.commit()
        caller = Caller(name=name, user=user, token=f"token-{name}-{user_id[:8]}")
        self.callers[name] = caller
        return caller

    # --- stored rows ---

    @contextmanager
    def _store(self) -> Iterator[Any]:
        if self._session_factory is None:
            yield self.store_memory
            return
        with self._session_factory() as db:
            yield BuilderStore(db)

    def seed_session(self, owner: Caller, *, running_turn: bool = False) -> Seeded:
        """Store a Session for ``owner`` with a sandbox, and optionally a running Turn.

        A running Turn is a stored ``running`` assistant row plus a registered
        ``LiveTurn`` (no task), so a request that stopped it would be visible.
        """
        choice = model_choice()
        with self._store() as store:
            session = store.create_session(
                owner.user_id, **BuilderSessionFactory.create_kwargs()
            )
            session_id = str(session.id)
            turn_id: str | None = None
            live: LiveTurn | None = None
            if running_turn:
                begun = store.begin_turn(
                    owner.user_id,
                    session_id,
                    content="Build a research workflow",
                    canvas_state={"steps": []},
                    client_message_id=f"cid-{uuid.uuid4().hex[:16]}",
                    model_id=choice["model_id"],
                    effort=choice["effort"],
                    skill_hash=str(session.skill_hash),
                )
                turn_id = str(begun.assistant_message.id)
                live = LiveTurn(
                    session_id=session_id,
                    turn_id=turn_id,
                    user_message_id=str(begun.user_message.id),
                    user_id=owner.user_id,
                    model_id=str(choice["model_id"]),
                    effort=choice["effort"],
                    tier=owner.user.tier,  # type: ignore[arg-type]
                )
                register_live_turn(live)
        sandbox = BuilderSandbox(owner.user_id, session_id)
        sandbox.ensure()
        (sandbox.path / "workflows" / "keep.workflow.json").write_text(
            '{"steps": []}', encoding="utf-8"
        )
        return Seeded(session_id, turn_id, live, sandbox.path)

    def subscribe(self, session_id: str) -> SessionQueue:
        """Register a client queue on the bus, as an open stream would."""
        queue, _snapshot = self.bus.subscribe(session_id, lambda: None)  # type: ignore[arg-type,return-value]
        self.bus.subscribes.clear()
        return queue

    # --- observation ---

    def fingerprint(self) -> tuple[Any, ...]:
        """Everything the Session_Store holds, reduced to comparable tuples."""
        if self._session_factory is None:
            store = self.store_memory
            return (
                sorted(
                    (s.id, s.updated_at, s.turn_count, s.workflow_id, s.next_seq)
                    for s in store._sessions.values()  # noqa: SLF001 - the fake's rows
                ),
                sorted(
                    (m.id, m.status, m.seq, m.content)
                    for m in store._messages  # noqa: SLF001
                ),
                sorted(
                    (d.id, d.revision, d.manifest_hash)
                    for d in store._drafts  # noqa: SLF001
                ),
            )
        with self._session_factory() as db:
            sessions = db.execute(
                select(
                    WorkflowBuilderSession.id,
                    WorkflowBuilderSession.updated_at,
                    WorkflowBuilderSession.turn_count,
                    WorkflowBuilderSession.workflow_id,
                    WorkflowBuilderSession.next_seq,
                )
            ).all()
            messages = db.execute(
                select(
                    WorkflowBuilderMessage.id,
                    WorkflowBuilderMessage.status,
                    WorkflowBuilderMessage.seq,
                    WorkflowBuilderMessage.content,
                )
            ).all()
            drafts = db.execute(
                select(
                    WorkflowBuilderDraft.id,
                    WorkflowBuilderDraft.revision,
                    WorkflowBuilderDraft.manifest_hash,
                )
            ).all()
        return (
            sorted(tuple(row) for row in sessions),
            sorted(tuple(row) for row in messages),
            sorted(tuple(row) for row in drafts),
        )

    def sandbox_listing(self) -> list[str]:
        """Every file and folder under the sandbox root, as relative paths."""
        if not self.sandbox_root.exists():
            return []
        return sorted(
            p.relative_to(self.sandbox_root).as_posix()
            for p in self.sandbox_root.rglob("*")
        )

    def state(self) -> dict[str, Any]:
        """A snapshot of everything a refused request must leave alone."""
        return {
            "store": self.fingerprint(),
            "sandbox": self.sandbox_listing(),
            "live": dict(turns._LIVE_TURNS),  # noqa: SLF001
            "starts": list(self.spies.starts),
            "capacity": list(self.spies.capacity),
            "frames": len(self.spies.frames),
            "publishes": list(self.bus.publishes),
            "closes": list(self.bus.closes),
            "subscribes": list(self.bus.subscribes),
            "db_calls": list(self.db.mock_calls),
        }

    # --- requests ---

    def send(
        self,
        case: RouteCase,
        *,
        caller: Caller | None,
        session_id: str,
        turn_id: str,
    ) -> Any:
        """Send ``case`` as ``caller`` (``None`` sends no credential)."""
        body = case.body(model_choice()) if case.body is not None else None
        return self.client.request(
            case.method,
            case.url(session_id, turn_id),
            json=body,
            headers=caller.headers if caller is not None else None,
        )
