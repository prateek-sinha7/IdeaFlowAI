"""tests/integration/test_gate_redo_enforcement.py — ISS-090 / FIX-422, over the wire.

``backend/tests/agents/test_redoable_eligibility_fence.py`` proves the ``redoable``
predicate and enforcement directly against ``ExecutionEngine`` methods (unit level).
This file proves the SAME defect through the real production ingress: a
``POST /api/runs/{run_id}/gate`` request, handled by the real FastAPI router, hitting
the real ``agents.artifact_store`` singleton, observed by a live ``_run_review_gate``
coroutine — the actual "way in" ISS-090 describes ("a replayed or scripted response
still re-ran an agent").

Harness ported from ``tests/unit/test_rest_gate_commands.py`` (TestClient + in-memory
SQLite bound to the real owner/terminal predicates + a fresh artifact-store singleton).

Offline-safe: no Bedrock / Postgres / Chromium. The gated "agent" here is the review
primitive itself — no model call, no pipeline agent — so this is deliberately the
narrowest slice of the real stack that exercises the HTTP → store → engine path.
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

_ARM_TIMEOUT = 1.5
_DRIVE_TIMEOUT = 10.0


class _FakeUser:
    def __init__(self, id: str):
        self.id = id


@pytest.fixture
def env(monkeypatch):
    from app.api import run_engine as ws_module
    from app.models.database import Base

    db_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    Base.metadata.create_all(bind=db_engine)
    monkeypatch.setattr(ws_module, "_get_db", lambda: TestingSession())

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

    yield {"ws": ws_module, "store": store, "client": client, "state": state}

    Base.metadata.drop_all(bind=db_engine)
    db_engine.dispose()
    store_mod._STORE = None


def _seed_user(env, tag: str) -> _FakeUser:
    from app.models.user import User

    db = env["ws"]._get_db()
    try:
        u = User(
            id=str(uuid.uuid4()),
            email=f"iss090-{tag}-{uuid.uuid4().hex[:8]}@example.com",
            password_hash="x",
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return _FakeUser(id=u.id)
    finally:
        db.close()


def _seed_run(env, user_id: str) -> str:
    from app.models.workflow import WorkflowRun

    run_id = str(uuid.uuid4())
    db = env["ws"]._get_db()
    try:
        db.add(
            WorkflowRun(
                id=run_id,
                user_id=user_id,
                title="t",
                type="prototype",
                status="running",
                input="i",
                agent_count=1,
                session_id=user_id,
            )
        )
        db.commit()
        return run_id
    finally:
        db.close()


def _post_gate(env, run_id: str, gate_key: str, **body):
    return env["client"].post(
        f"/api/runs/{run_id}/gate", json={"gate_key": gate_key, **body}
    )


async def _wait_until(pred, timeout: float = _ARM_TIMEOUT) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if pred():
            return True
        await asyncio.sleep(0.01)
    return False


async def _drive_gate_over_http(env, run_id: str, *, redoable: bool):
    """Run a REAL ``_run_review_gate`` coroutine against the store the REST
    endpoint writes to, while a client resolves it via REAL HTTP POSTs to
    ``/api/runs/{run_id}/gate`` — never a direct ``store.set_review_response`` call.

    Returns ``(events, http_responses)``.
    """
    import agents.artifact_store.store as store_mod
    from agents.execution_engine.engine import ExecutionEngine

    store_mod._STORE = None
    engine = ExecutionEngine()
    agent_id = "gated-agent"
    gate_key = f"{run_id}:{agent_id}:0"
    http_responses: list = []

    async def _client() -> None:
        if not await _wait_until(lambda: engine._store.review_event_pending(gate_key)):
            return
        resp = _post_gate(
            env, run_id, gate_key, action="redo", instructions="do it differently"
        )
        http_responses.append(("redo", resp))
        # If refused, the gate RE-ARMS — the client posts a real approve next.
        if not await _wait_until(lambda: engine._store.review_event_pending(gate_key)):
            return
        resp = _post_gate(env, run_id, gate_key, action="approve")
        http_responses.append(("approve", resp))

    events: list[dict] = []

    async def _collect() -> None:
        async for ev in engine._run_review_gate(
            pipeline_run_id=run_id,
            agent_id=agent_id,
            agent_name="Gated Agent",
            output="THE OUTPUT",
            redoable=redoable,
            update_specs_eligible=False,
            artifact_kind="summary",
        ):
            events.append(ev)

    client_task = asyncio.create_task(_client())
    try:
        await asyncio.wait_for(_collect(), timeout=_DRIVE_TIMEOUT)
    finally:
        client_task.cancel()

    return events, http_responses


@pytest.mark.issue("ISS-090")
@pytest.mark.asyncio
async def test_http_redo_is_refused_when_the_firing_advertised_no_redo_button(env):
    """A real ``POST /api/runs/{id}/gate`` carrying ``action: "redo"`` against a gate
    that published ``redoable: False`` must be REFUSED by the engine, not honoured.

    Pre-fix: the REST endpoint has no ``redoable`` awareness of its own (it only
    validates ownership + that a gate is pending, then writes the response) — the
    refusal has to happen inside ``_run_review_gate``. Pre-fix that method acted on
    ``action == "redo"`` unconditionally, so this same HTTP request re-ran the gated
    agent even though the firing never advertised the Redo button — ISS-090's "way in".
    """
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id)
    env["state"]["user"] = owner

    events, http_responses = await _drive_gate_over_http(env, run_id, redoable=False)
    types = [e.get("type") for e in events]
    actions = [a for a, _r in http_responses]

    assert actions == ["redo", "approve"], (
        "the redo must be refused (gate re-arms) so a follow-up approve is what "
        f"resolves the run; got HTTP actions {actions}"
    )
    for action, resp in http_responses:
        assert resp.status_code == 200, f"{action} POST failed: {resp.status_code} {resp.text}"

    assert "_gate_redo" not in types, (
        f"the engine re-ran the agent on a redo the firing published redoable=False "
        f"for (ISS-090); events={types}"
    )
    assert "review_gate_approved" in types, (
        f"the gate did not resolve via the follow-up approve; events={types}"
    )


@pytest.mark.asyncio
async def test_http_redo_still_fires_when_the_firing_advertised_the_redo_button(env):
    """Dormancy guard: over the SAME real HTTP path, a firing that published
    ``redoable: True`` still honours a redo — the enforcement above narrows nothing
    the rule permits."""
    owner = _seed_user(env, "owner2")
    run_id = _seed_run(env, owner.id)
    env["state"]["user"] = owner

    events, http_responses = await _drive_gate_over_http(env, run_id, redoable=True)
    types = [e.get("type") for e in events]
    actions = [a for a, _r in http_responses]

    assert actions == ["redo"], f"an advertised redo must resolve in one HTTP POST; got {actions}"
    assert http_responses[0][1].status_code == 200, http_responses[0][1].text
    assert "_gate_redo" in types, f"an advertised redo no longer re-runs the agent; events={types}"
