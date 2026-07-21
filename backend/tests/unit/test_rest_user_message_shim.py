"""tests/unit/test_rest_user_message_shim.py — CHAT-07 / D-13 / ND-3 (29-04).

The up-channel REST twin of the legacy WS ``user_message`` free-chat handler,
ported to a POST+stream shim (``POST /api/runs/user_message``). The shim persists
the Message rows and drives ``ChatRunner`` EXACTLY as the WS handler does
(websocket.py:1478-1616), streaming ChatRunner's native
``phase_start/stream/phase_end/error/complete`` vocabulary back over SSE.

LOCK-B / landmine (POR §7 / ND-3): the ``chat`` agents, ``ChatRunner``, and the
frozen ``tests/unit/test_chat_contract.py`` golden are UNTOUCHED — the shim only
wraps the sequencer. This suite stubs ``ChatRunner`` to prove the shim is a
faithful passthrough (the golden proves ChatRunner's own output byte-for-byte).

Coverage:
  * Owner gate: cross-owner / unknown chat_session → 404 (no drive, no persist).
  * Passthrough: every ChatRunner event reaches the SSE stream verbatim (same
    ``{type, chunk, section, data}`` frames the WS handler forwarded).
  * Persistence: the user Message + the assistant Message (joined stream chunks)
    are written; ``final_output`` is stored from the trailing ``complete`` event.

Offline — in-memory SQLite (StaticPool) + a stubbed ChatRunner; no Bedrock.
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models.chat  # noqa: F401  (register chat_sessions / messages tables)
from app.models.chat import ChatSession, Message
from app.models.database import Base
from app.models.user import User


# ════════════════════════════════════════════════════════════════════════════
# Harness
# ════════════════════════════════════════════════════════════════════════════


class _FakeUser:
    def __init__(self, id: str):
        self.id = id
        self.preferred_model = None


# A canned ChatRunner event script — the exact StreamMessage-shaped dicts the real
# ChatRunner yields (one phase's worth). The shim must reproduce these 1:1.
_SCRIPT: list[dict] = [
    {"type": "phase_start", "section": "discovery", "chunk": None,
     "data": {"phase": 0, "name": "Discovery"}},
    {"type": "stream", "chunk": "Hello ", "section": "discovery", "data": None},
    {"type": "stream", "chunk": "world", "section": "discovery", "data": None},
    {"type": "phase_end", "section": "discovery", "chunk": None, "data": {"phase": 0}},
    {"type": "complete", "chunk": None, "section": None,
     "data": {"discovery": {"output": "Hello world"}}},
]


class _StubChatRunner:
    """Drop-in for ``run_commands.ChatRunner`` — yields the canned script and
    records its construction + astream_execute args."""

    last_init: dict | None = None
    last_call: dict | None = None

    def __init__(self, ctx=None, *, user_id=None, run_id=None):
        _StubChatRunner.last_init = {"user_id": user_id, "run_id": run_id}

    async def astream_execute(self, user_message, chat_session_id=None,
                              mode="default", mode_prompt=""):
        _StubChatRunner.last_call = {
            "user_message": user_message, "chat_session_id": chat_session_id,
            "mode": mode, "mode_prompt": mode_prompt,
        }
        for event in _SCRIPT:
            yield event


@pytest.fixture
def env(monkeypatch):
    import app.api.run_commands as rc_module

    db_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    Base.metadata.create_all(bind=db_engine)
    monkeypatch.setattr(rc_module, "_get_db", lambda: TestingSession())

    _StubChatRunner.last_init = None
    _StubChatRunner.last_call = None
    monkeypatch.setattr(rc_module, "ChatRunner", _StubChatRunner)

    from app.api.run_commands import router
    from app.core.dependencies import get_current_user

    app = FastAPI()
    app.include_router(router)
    state: dict = {"user": None}
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    client = TestClient(app)

    yield {"client": client, "state": state, "Session": TestingSession, "rc": rc_module}

    Base.metadata.drop_all(bind=db_engine)
    db_engine.dispose()


def _seed_user(env, tag="u") -> _FakeUser:
    db = env["Session"]()
    try:
        u = User(
            id=str(uuid.uuid4()),
            email=f"shim-{tag}-{uuid.uuid4().hex[:8]}@example.com",
            password_hash="x",
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return _FakeUser(id=u.id)
    finally:
        db.close()


def _seed_session(env, user_id: str) -> str:
    sid = str(uuid.uuid4())
    db = env["Session"]()
    try:
        db.add(ChatSession(id=sid, user_id=user_id, title="New Chat"))
        db.commit()
    finally:
        db.close()
    return sid


def _messages(env, session_id: str) -> list[Message]:
    db = env["Session"]()
    try:
        return (
            db.query(Message)
            .filter(Message.chat_session_id == session_id)
            .order_by(Message.created_at)
            .all()
        )
    finally:
        db.close()


def _session(env, session_id: str) -> ChatSession | None:
    db = env["Session"]()
    try:
        return db.query(ChatSession).filter(ChatSession.id == session_id).first()
    finally:
        db.close()


def _parse_sse(text: str) -> list[dict]:
    """Extract the JSON body of every ``data:`` SSE frame."""
    events = []
    for line in text.splitlines():
        if line.startswith("data:"):
            body = line[len("data:"):].strip()
            if body:
                events.append(json.loads(body))
    return events


def _post(env, user, **body):
    env["state"]["user"] = user
    return env["client"].post("/api/runs/user_message", json=body)


# ════════════════════════════════════════════════════════════════════════════
# Owner gate
# ════════════════════════════════════════════════════════════════════════════


def test_unknown_session_returns_404(env):
    user = _seed_user(env)
    resp = _post(env, user, content="hi", chat_session_id=str(uuid.uuid4()))
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Chat session not found"


def test_cross_owner_session_returns_404(env):
    owner = _seed_user(env, "owner")
    attacker = _seed_user(env, "attacker")
    sid = _seed_session(env, owner.id)
    resp = _post(env, attacker, content="steal", chat_session_id=sid)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Chat session not found"
    # The victim's session got no message from the attacker.
    assert _messages(env, sid) == []


def test_empty_content_rejected(env):
    user = _seed_user(env)
    sid = _seed_session(env, user.id)
    resp = _post(env, user, content="", chat_session_id=sid)
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "invalid_message"


# ════════════════════════════════════════════════════════════════════════════
# Passthrough — the SSE stream reproduces ChatRunner's events verbatim
# ════════════════════════════════════════════════════════════════════════════


def test_shim_streams_chatrunner_events_verbatim(env):
    user = _seed_user(env)
    sid = _seed_session(env, user.id)
    resp = _post(env, user, content="build me an app", chat_session_id=sid, mode="thinking")
    assert resp.status_code == 200, resp.text

    events = _parse_sse(resp.text)
    # Every ChatRunner event reached the SSE stream, in order, byte-for-byte.
    assert events == _SCRIPT

    # The shim built ChatRunner with the caller's ids and drove it with the turn.
    assert _StubChatRunner.last_init == {"user_id": user.id, "run_id": sid}
    assert _StubChatRunner.last_call["user_message"] == "build me an app"
    assert _StubChatRunner.last_call["chat_session_id"] == sid
    assert _StubChatRunner.last_call["mode"] == "thinking"


def test_shim_persists_user_and_assistant_messages(env):
    user = _seed_user(env)
    sid = _seed_session(env, user.id)
    resp = _post(env, user, content="hello there", chat_session_id=sid)
    assert resp.status_code == 200, resp.text

    msgs = _messages(env, sid)
    roles = [(m.role, m.content) for m in msgs]
    assert ("user", "hello there") in roles
    # The assistant content is the joined stream chunks ("Hello " + "world").
    assert ("assistant", "Hello world") in roles

    # The trailing `complete` event's data is stored as the session final_output.
    cs = _session(env, sid)
    assert cs.final_output is not None
    assert json.loads(cs.final_output) == {"discovery": {"output": "Hello world"}}
