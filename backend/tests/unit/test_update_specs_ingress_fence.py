"""tests/unit/test_update_specs_ingress_fence.py — ISS-053 layer 1, all three ingresses.

The engine publishes its eligibility verdict on every ``review_gate_ready``. This suite
pins the caller-facing half of the fence: an ``update_specs`` aimed at a gate that
published ``update_specs_eligible: False`` is answered **409 ``update_specs_not_offered``**
and never reaches ``store.set_review_response`` — instead of the silently-ignored 200 it
used to get.

There are exactly THREE production writers of ``set_review_response`` (swept across the
whole backend; the WS handler is gone), so all three are covered here — a fence on
``POST /gate`` alone would leave both ``/messages`` routes open:

  1. ``POST /api/runs/{id}/gate``                       — ``run_commands.resolve_gate``
  2. ``POST /api/runs/{id}/messages`` → ``CHANNEL_GATE`` — ``run_commands.post_message``
  3. ``POST /api/runs/{id}/messages`` → Concierge ``gate_action`` disposal
     — ``run_commands._dispose_concierge_proposal``

The predicate itself (``run_engine._review_gate_advertises_update_specs``) is pinned
separately: it must ABSTAIN — never fabricate a denial — when the durable log cannot answer
(no row / a different gate / a pre-KAN-101 payload), because event persistence is
best-effort and a false 409 would block a LEGITIMATE revision. Abstaining is only safe
because the engine-side fence re-checks from memory and never abstains
(``tests/agents/test_update_specs_enforcement.py``).

Offline: TestClient + in-memory SQLite. No Bedrock / uvicorn / Postgres.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

_CODE = "update_specs_not_offered"


class _FakeUser:
    def __init__(self, id: str):
        self.id = id


@pytest.fixture
def env(monkeypatch):
    """TestClient over the real run_commands router on an in-memory DB.

    Both modules' ``_get_db`` AND ``database.SessionLocal`` are patched: ``run_commands``
    binds its own ``_get_db`` reference at import, and ``ScopedStore(session=None)`` opens
    ``SessionLocal`` directly (the recipe ``test_chat_messages_endpoint`` established).
    """
    from app.api import run_commands as rc_module
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

    yield {
        "ws": ws_module,
        "store": store,
        "client": TestClient(app),
        "state": state,
        "Session": TestingSession,
    }

    Base.metadata.drop_all(bind=db_engine)
    db_engine.dispose()
    store_mod._STORE = None


def _seed_user(env, tag: str) -> _FakeUser:
    from app.models.user import User

    db = env["Session"]()
    try:
        u = User(id=str(uuid.uuid4()),
                 email=f"iss053-{tag}-{uuid.uuid4().hex[:8]}@example.com",
                 password_hash="x")
        db.add(u)
        db.commit()
        db.refresh(u)
        return _FakeUser(id=u.id)
    finally:
        db.close()


def _seed_run(env, user_id: str, *, status: str = "waiting_for_user") -> str:
    from app.models.workflow import WorkflowRun

    run_id = str(uuid.uuid4())
    db = env["Session"]()
    try:
        db.add(WorkflowRun(
            id=run_id, user_id=user_id, owner_id=user_id, workspace_id="ws-1",
            title="t", type="prototype", status=status, input="i",
            agent_count=1, session_id=user_id, created_at=datetime.now(timezone.utc),
        ))
        db.commit()
        return run_id
    finally:
        db.close()


def _publish_gate_ready(env, run_id, owner_id, payload, *, seq=1):
    """Persist ONE ``review_gate_ready`` row — the engine's published verdict."""
    from app.models.run_event import RunEvent

    db = env["Session"]()
    try:
        db.add(RunEvent(
            id=str(uuid.uuid4()), run_id=run_id, owner_id=owner_id,
            workspace_id="ws-1", seq=seq, event_id=str(uuid.uuid4()),
            type="review_gate_ready", payload_json=payload,
        ))
        db.commit()
    finally:
        db.close()


def _arm(env, gate_key: str) -> None:
    """KAN-94 ground truth: an armed-but-unset review event is a genuine pending pause."""
    env["store"]._resume_events[f"review:{gate_key}"] = asyncio.Event()


def _recorded(env, gate_key: str):
    rows = env["store"]._questionnaire_responses.get(f"review:{gate_key}")
    return rows[0] if rows else None


def _setup(env, *, eligible, tag):
    """A run paused at an armed gate whose published verdict is ``eligible``.

    ``eligible=None`` publishes a payload with NO ``update_specs_eligible`` key at all
    (a pre-KAN-101 row).
    """
    owner = _seed_user(env, tag)
    run_id = _seed_run(env, owner.id)
    gate_key = f"{run_id}:prototype-analyze"
    payload = {"gate_key": gate_key, "agent_id": "prototype-analyze"}
    if eligible is not None:
        payload["update_specs_eligible"] = eligible
    _publish_gate_ready(env, run_id, owner.id, payload)
    _arm(env, gate_key)
    env["state"]["user"] = owner
    return owner, run_id, gate_key


# ════════════════════════════════════════════════════════════════════════════
# Ingress 1 — POST /api/runs/{id}/gate
# ════════════════════════════════════════════════════════════════════════════


def test_gate_endpoint_rejects_update_specs_at_an_ineligible_gate(env):
    """The gate published ``False``; the POST is refused with a 409 the caller can act on,
    and nothing is written to the gate seam."""
    _owner, run_id, gate_key = _setup(env, eligible=False, tag="g-no")

    resp = env["client"].post(
        f"/api/runs/{run_id}/gate",
        json={"gate_key": gate_key, "action": "update_specs", "analysis_report": "x"},
    )

    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["code"] == _CODE
    assert _recorded(env, gate_key) is None, (
        "the gate seam was written despite the gate advertising update_specs_eligible=False"
    )


def test_gate_endpoint_allows_update_specs_at_an_eligible_gate(env):
    """Dormancy: the fence narrows nothing the engine's own rule permits."""
    _owner, run_id, gate_key = _setup(env, eligible=True, tag="g-yes")

    resp = env["client"].post(
        f"/api/runs/{run_id}/gate",
        json={"gate_key": gate_key, "action": "update_specs", "analysis_report": "RPT"},
    )

    assert resp.status_code == 200, resp.text
    rec = _recorded(env, gate_key)
    assert rec["action"] == "update_specs" and rec["instructions"] == "RPT"


@pytest.mark.parametrize("action", ["approve", "reject", "redo"])
def test_gate_endpoint_leaves_the_other_actions_untouched(env, action):
    """The fence is scoped to ``update_specs``: approve / reject / redo still resolve an
    ineligible gate, so the user is never trapped at it."""
    _owner, run_id, gate_key = _setup(env, eligible=False, tag=f"g-{action}")

    resp = env["client"].post(
        f"/api/runs/{run_id}/gate", json={"gate_key": gate_key, "action": action},
    )

    assert resp.status_code == 200, resp.text
    assert _recorded(env, gate_key) is not None


# ════════════════════════════════════════════════════════════════════════════
# Ingress 2 — POST /api/runs/{id}/messages → CHANNEL_GATE
# ════════════════════════════════════════════════════════════════════════════


def test_messages_route_rejects_update_specs_at_an_ineligible_gate(env):
    """A fence on /gate alone would leave this route wide open — it reaches the identical
    seam and needs no ``gate_key`` (the server derives it from the event log)."""
    _owner, run_id, gate_key = _setup(env, eligible=False, tag="m-no")

    resp = env["client"].post(
        f"/api/runs/{run_id}/messages",
        json={"message_id": uuid.uuid4().hex, "text": "",
              "action": "update_specs", "analysis_report": "x"},
    )

    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["code"] == _CODE
    assert _recorded(env, gate_key) is None


def test_messages_route_allows_update_specs_at_an_eligible_gate(env):
    _owner, run_id, gate_key = _setup(env, eligible=True, tag="m-yes")

    resp = env["client"].post(
        f"/api/runs/{run_id}/messages",
        json={"message_id": uuid.uuid4().hex, "text": "",
              "action": "update_specs", "analysis_report": "RPT"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["channel"] == "gate"
    assert _recorded(env, gate_key)["action"] == "update_specs"


# ════════════════════════════════════════════════════════════════════════════
# Ingress 3 — the Concierge gate_action disposal
# ════════════════════════════════════════════════════════════════════════════


class _SpyArtStore:
    def __init__(self):
        self.review_calls: list[tuple] = []
        self._resume_events: dict = {}

    async def set_review_response(self, gate_key, **kwargs):
        self.review_calls.append((gate_key, kwargs))

    def arm(self, gate_key):
        self._resume_events[f"review:{gate_key}"] = asyncio.Event()

    def review_event_pending(self, gate_key: str) -> bool:
        event = self._resume_events.get(f"review:{gate_key}")
        return event is not None and not event.is_set()


class _SpyStore:
    def __init__(self):
        self.appended: list[dict] = []

    async def append_event_next_seq(self, run_id, *, event_id, type, payload_json):
        self.appended.append({"event_id": event_id, "type": type, "payload": payload_json})
        return True, 1


async def _dispose_gate_action(env, gate_key, *, art):
    """Drive the Concierge disposal for a CONFIRMED ``update_specs`` gate action."""
    from app.agents.chat.concierge import propose_gate_action
    from app.api import run_commands as rc

    return await rc._dispose_concierge_proposal(
        propose_gate_action.func(action="update_specs", rationale="RPT"),
        confirmed=True,
        store=_SpyStore(),
        art_store=art,
        run_id=gate_key.split(":", 1)[0],
        message_id="m-1",
        current_user=env["state"]["user"],
        wr_status="waiting_for_user",
        wr_type="prototype",
        gate_key=gate_key,
        ectx=None,
    )


@pytest.mark.asyncio
async def test_concierge_disposal_rejects_update_specs_at_an_ineligible_gate(env):
    """The Concierge reaches the same seam on a confirmed proposal — it is fenced too."""
    from fastapi import HTTPException

    _owner, _run_id, gate_key = _setup(env, eligible=False, tag="c-no")
    art = _SpyArtStore()
    art.arm(gate_key)

    with pytest.raises(HTTPException) as excinfo:
        await _dispose_gate_action(env, gate_key, art=art)

    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["code"] == _CODE
    assert art.review_calls == []


@pytest.mark.asyncio
async def test_concierge_disposal_allows_update_specs_at_an_eligible_gate(env):
    _owner, _run_id, gate_key = _setup(env, eligible=True, tag="c-yes")
    art = _SpyArtStore()
    art.arm(gate_key)

    res = await _dispose_gate_action(env, gate_key, art=art)

    assert res["disposed"] == "gate" and res["action"] == "update_specs"
    assert len(art.review_calls) == 1
    assert art.review_calls[0][1]["action"] == "update_specs"


# ════════════════════════════════════════════════════════════════════════════
# The predicate ABSTAINS rather than fabricating a denial
# ════════════════════════════════════════════════════════════════════════════


def test_predicate_abstains_when_no_gate_ready_row_exists(env):
    """Event persistence is best-effort, so "no row" means UNKNOWN, never "ineligible".
    Denying here would 409 a legitimate revision whenever a durable write degraded."""
    owner = _seed_user(env, "abstain-norow")
    run_id = _seed_run(env, owner.id)
    gate_key = f"{run_id}:prototype-analyze"

    assert env["ws"]._review_gate_advertises_update_specs(gate_key) is True


def test_predicate_abstains_on_a_pre_kan101_payload(env):
    """A row predating the flag carries no verdict to read — abstain, don't invent one.
    (This is also what keeps the shipped routing tests, which seed a bare
    ``{"gate_key": ...}`` payload, green.)"""
    _owner, _run_id, gate_key = _setup(env, eligible=None, tag="abstain-old")

    assert env["ws"]._review_gate_advertises_update_specs(gate_key) is True


def test_predicate_abstains_when_the_latest_ready_is_a_different_gate(env):
    """The published verdict belongs to a specific gate_key; a verdict for another gate
    says nothing about this one."""
    owner = _seed_user(env, "abstain-other")
    run_id = _seed_run(env, owner.id)
    other_key = f"{run_id}:prototype-specify"
    _publish_gate_ready(
        env, run_id, owner.id,
        {"gate_key": other_key, "update_specs_eligible": False}, seq=1,
    )

    assert env["ws"]._review_gate_advertises_update_specs(f"{run_id}:prototype-analyze") is True


def test_predicate_reads_the_LATEST_verdict_not_the_first(env):
    """``gate_key`` names a gate SLOT, not a firing — the same key fires repeatedly with
    different verdicts (True at the outer analyze gate, False at the in-pass one). The
    fence must read the CURRENT firing, which is the highest-seq row."""
    owner = _seed_user(env, "latest")
    run_id = _seed_run(env, owner.id)
    gate_key = f"{run_id}:prototype-analyze"
    _publish_gate_ready(
        env, run_id, owner.id,
        {"gate_key": gate_key, "update_specs_eligible": True}, seq=1,
    )
    _publish_gate_ready(
        env, run_id, owner.id,
        {"gate_key": gate_key, "update_specs_eligible": False}, seq=2,
    )

    assert env["ws"]._review_gate_advertises_update_specs(gate_key) is False
