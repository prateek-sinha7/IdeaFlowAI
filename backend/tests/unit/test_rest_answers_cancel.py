"""tests/unit/test_rest_answers_cancel.py — CHAT-07 / D-13 (29-03).

The up-channel REST twins of ``POST /api/runs/{id}/answers`` (clarify) and
``POST /api/runs/{id}/cancel`` (cooperative cancel), ported from
``test_pipeline_cancel.py`` (+ the WS ``submit_questionnaire`` assertions) against
the REST endpoints. Each endpoint is a thin wrapper over the SAME seams the WS
handlers call (LOCK-B — ``websocket.py`` is untouched):

  * answers → ``store.set_questionnaire_responses(run_id, responses,
    skip_clarification)`` (store.py:62), incl. the ISS-027 force-proceed and the
    ``question_id:"freeform"`` note mapping.
  * cancel  → sets the per-run cooperative ``asyncio.Event`` in
    ``_CANCEL_EVENTS[run_id]`` (ISS-007); the engine observes it and emits
    ``pipeline_cancelled`` through the normal persisted+drained path (suspend/
    persist semantics unchanged). Idempotent ack when nothing is active.

Both are owner-scoped (T-29-03-3): a cross-owner target denies with a
non-revealing 404 (IDOR → 404, never 403), touching no seam.
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


class _FakeUser:
    def __init__(self, id: str):
        self.id = id


@pytest.fixture
def env(monkeypatch):
    # W4a (44-03): _get_db + _CANCEL_EVENTS relocated to app.api.run_engine
    # (INV-12 extract-before-delete). Patch the seam at its new home.
    import app.models.database as db_module
    from app.api import run_commands as rc_module
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
    # ISS-089: the cancel endpoint now WRITES. ``run_commands`` binds ``_get_db`` at
    # import (``from app.api.run_engine import _get_db``), so patching only the
    # ``run_engine`` attribute above leaves the writer pointed at the real
    # ``SessionLocal`` — i.e. at dev.db. ``ScopedStore`` and ``_recover_workspace_id``
    # open ``SessionLocal()`` themselves, so that too must be redirected. Both are
    # SAFETY, not convenience: an unpatched seam here mutates real run rows.
    monkeypatch.setattr(rc_module, "_get_db", lambda: TestingSession())
    monkeypatch.setattr(db_module, "SessionLocal", TestingSession)

    import agents.artifact_store.store as store_mod
    store_mod._STORE = None
    store = store_mod.get_artifact_store()

    # Clean cooperative-cancel + driver-task registries per test (module-globals on
    # ws_module). ISS-084: liveness is decided from _PIPELINE_TASKS, so a leaked entry
    # from another test would make an orphan look live.
    ws_module._CANCEL_EVENTS.clear()
    ws_module._PIPELINE_TASKS.clear()

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
    ws_module._CANCEL_EVENTS.clear()
    ws_module._PIPELINE_TASKS.clear()


def _seed_user(env, email_tag: str) -> _FakeUser:
    from app.models.user import User

    db = env["ws"]._get_db()
    try:
        u = User(
            id=str(uuid.uuid4()),
            email=f"rest03ac-{email_tag}-{uuid.uuid4().hex[:8]}@example.com",
            password_hash="x",
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return _FakeUser(id=u.id)
    finally:
        db.close()


def _seed_run(
    env,
    user_id: str,
    *,
    status: str = "running",
    owner_id: str | None = None,
    workspace_id: str | None = None,
) -> str:
    """Insert the ``workflow_runs`` row the endpoints read.

    ``owner_id``/``workspace_id`` default to None (the historical shape — the WS creation
    path leaves both unset, and every pre-ISS-089 caller is byte-unchanged). The
    durable-tail tests pass both, because ``run_events.workspace_id`` is NOT NULL: a run
    with no recoverable workspace cannot carry an audit row at all.
    """
    from app.models.workflow import WorkflowRun

    run_id = str(uuid.uuid4())
    db = env["ws"]._get_db()
    try:
        db.add(
            WorkflowRun(
                id=run_id,
                user_id=user_id,
                owner_id=owner_id,
                workspace_id=workspace_id,
                title="t",
                type="user_stories",
                status=status,
                input="i",
                agent_count=1,
                session_id=user_id,
            )
        )
        db.commit()
        return run_id
    finally:
        db.close()


def _run_status(env, run_id: str):
    from app.models.workflow import WorkflowRun

    db = env["ws"]._get_db()
    try:
        row = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
        return None if row is None else (row.status, row.completed_at)
    finally:
        db.close()


def _seed_event(env, run_id: str, *, owner_id: str, workspace_id: str, seq: int,
                type_: str = "pipeline_start") -> None:
    from app.models.run_event import RunEvent

    db = env["ws"]._get_db()
    try:
        db.add(
            RunEvent(
                id=str(uuid.uuid4()),
                run_id=run_id,
                owner_id=owner_id,
                workspace_id=workspace_id,
                seq=seq,
                event_id=str(uuid.uuid4()),
                type=type_,
                payload_json={},
            )
        )
        db.commit()
    finally:
        db.close()


def _events(env, run_id: str) -> list:
    from app.models.run_event import RunEvent

    db = env["ws"]._get_db()
    try:
        return [
            (r.seq, r.type)
            for r in db.query(RunEvent)
            .filter(RunEvent.run_id == run_id)
            .order_by(RunEvent.seq.asc())
            .all()
        ]
    finally:
        db.close()


# ────────────────────────────────────────────────────────────────────────────
# POST /{id}/answers — clarify responses (mirrors WS submit_questionnaire)
# ────────────────────────────────────────────────────────────────────────────


def test_answers_resolve_the_clarify_pause(env):
    """The owner's responses reach the SAME store seam and set the per-run resume
    event the ClarifyEngine awaits."""
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id)
    env["state"]["user"] = owner
    responses = [{"question_id": "r1_q1", "answer": "yes"}]

    resp = env["client"].post(
        f"/api/runs/{run_id}/answers", json={"responses": responses}
    )
    assert resp.status_code == 200, resp.text
    assert env["store"]._questionnaire_responses[run_id] == responses
    # The resume event fired (clarify loop unblocks).
    assert env["store"]._resume_events[run_id].is_set() is True
    # Ordinary submission does NOT force-proceed (byte-identical default).
    assert env["store"]._questionnaire_force_proceed[run_id] is False


def test_answers_skip_clarification_force_proceeds(env):
    """ISS-027: "Skip all & run directly" flows through ``skip_clarification`` so
    the clarify loop proceeds immediately instead of re-asking."""
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id)
    env["state"]["user"] = owner

    resp = env["client"].post(
        f"/api/runs/{run_id}/answers",
        json={"responses": [], "skip_clarification": True},
    )
    assert resp.status_code == 200, resp.text
    assert env["store"]._questionnaire_force_proceed[run_id] is True


def test_answers_freeform_maps_to_freeform_question_id(env):
    """The global "anything else" note rides as ``question_id:"freeform"`` (the
    shape the frontend + ClarifyEngine already use)."""
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id)
    env["state"]["user"] = owner

    resp = env["client"].post(
        f"/api/runs/{run_id}/answers",
        json={"responses": [{"question_id": "r1_q1", "answer": "a"}], "freeform": "note"},
    )
    assert resp.status_code == 200, resp.text
    stored = env["store"]._questionnaire_responses[run_id]
    assert {"question_id": "freeform", "answer": "note"} in stored


def test_answers_cross_owner_is_denied(env):
    """T-29-03-3: a cross-owner clarify submission denies with a non-revealing
    404 and never touches the seam (no resume event, no responses)."""
    victim = _seed_user(env, "victim")
    attacker = _seed_user(env, "attacker")
    run_id = _seed_run(env, victim.id)
    env["state"]["user"] = attacker

    resp = env["client"].post(
        f"/api/runs/{run_id}/answers",
        json={"responses": [{"question_id": "r1_q1", "answer": "x"}]},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Unknown gate_key"
    assert run_id not in env["store"]._questionnaire_responses
    assert run_id not in env["store"]._resume_events


def test_answers_unknown_run_is_denied(env):
    caller = _seed_user(env, "caller")
    env["state"]["user"] = caller
    run_id = str(uuid.uuid4())

    resp = env["client"].post(
        f"/api/runs/{run_id}/answers", json={"responses": []}
    )
    assert resp.status_code == 404


# ────────────────────────────────────────────────────────────────────────────
# POST /{id}/cancel — cooperative cancel (mirrors WS cancel_pipeline)
# ────────────────────────────────────────────────────────────────────────────


def test_cancel_sets_the_cooperative_event(env):
    """ISS-007: a Stop over HTTP sets the per-run cooperative ``cancel_event``
    (never a destructive task kill) — the engine observes it and emits the clean
    ``pipeline_cancelled`` terminal through the normal drained path.

    ISS-084 reconcile: this test used to seed ONLY ``_CANCEL_EVENTS`` and assert the
    endpoint set it, which made its own docstring premise ("a live run has an armed cancel
    event") unfalsifiable — in production that entry was an orphan for every resumed run.
    The premise is now made TRUE by seeding the driver task as well, and the assertion is
    on the honest ``accepted`` acknowledgement rather than the unearned ``cancelled``.
    """
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id)
    # A live run has an armed cancel event AND a driver task that can observe it.
    env["ws"]._CANCEL_EVENTS[run_id] = asyncio.Event()
    env["ws"]._PIPELINE_TASKS[run_id] = object()
    env["state"]["user"] = owner

    resp = env["client"].post(f"/api/runs/{run_id}/cancel")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accepted"] is True
    assert body["status"] == "stopping"
    assert env["ws"]._CANCEL_EVENTS[run_id].is_set() is True


def test_cancel_does_not_claim_success_without_a_live_driver(env):
    """ISS-084 — the anti-lie test. A ``_CANCEL_EVENTS`` entry with no in-process driver
    is an ORPHAN: setting it stops nothing, because nothing holds it. The endpoint must
    not report success for it.

    This is the shape that cost the owner 7,510,082 tokens: ``POST /cancel`` answered
    ``HTTP 200 {"cancelled": true}`` and the run went on to complete, emitting zero
    ``pipeline_cancelled`` events. The API asserted a result it had never verified.

    ISS-089 reconcile — the run seeded here is now TERMINAL. The invariant is unchanged
    ("never claim an outcome nothing achieved") but its reachable case narrowed: for a
    NON-terminal run the endpoint now genuinely achieves the cancellation durably, so
    ``cancelled: true`` there is earned rather than asserted (see
    ``test_cancel_without_a_live_driver_is_made_durable``). A terminal run is the case
    where there is still nothing to be done, and the honest answer is still ``false``.
    """
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id, status="completed")
    env["ws"]._CANCEL_EVENTS[run_id] = asyncio.Event()  # orphan: no driver task
    env["state"]["user"] = owner

    resp = env["client"].post(f"/api/runs/{run_id}/cancel")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accepted"] is False, (
        f"the endpoint claimed a cancellation nothing could perform: {body}"
    )
    assert body["cancelled"] is False
    assert body["status"] == "not_running"


def test_cancel_is_idempotent_with_no_active_event(env):
    """No active pipeline → an idempotent ack (nothing to cancel), so the client
    UI state machine can return to idle.

    ISS-089 reconcile: "no active pipeline" is now decided from the DURABLE status, not
    from registry membership alone, so the run is seeded terminal. A second Stop on an
    already-cancelled run takes exactly this branch — that is what makes the durable
    cancel idempotent.
    """
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id, status="cancelled")
    env["state"]["user"] = owner  # no _CANCEL_EVENTS entry

    resp = env["client"].post(f"/api/runs/{run_id}/cancel")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accepted"] is False
    assert body["cancelled"] is False
    assert body["message"] == "No active pipeline"


# ────────────────────────────────────────────────────────────────────────────
# ISS-089 — a Stop with no live driver must SURVIVE the process
#
# Before this, the endpoint wrote nothing at all in the not-live branch: it set an
# in-memory ``asyncio.Event`` and armed an in-process task, both of which die with the
# process. So the owner's Stop was lost, the row stayed inside
# ``NON_TERMINAL_RUN_STATUSES``, and the next boot re-adopted the run and finished it at
# the owner's expense — the second half of the ``d5dbc9f2`` incident (16,530,718 tokens,
# $3.58, ~45% of it billed AFTER the API answered ``cancelled: true``).
# ────────────────────────────────────────────────────────────────────────────


def test_cancel_without_a_live_driver_is_made_durable(env):
    """The money assertion at the endpoint: a non-terminal run with no in-process driver
    is written TERMINAL, so no later process can re-adopt it."""
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id, status="generating")
    env["state"]["user"] = owner

    resp = env["client"].post(f"/api/runs/{run_id}/cancel")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accepted"] is True, f"the owner's Stop was dropped: {body}"
    assert body["cancelled"] is True
    assert body["status"] == "cancelled"

    status_after, completed_at = _run_status(env, run_id)
    assert status_after == "cancelled", (
        f"the run is still {status_after!r} — the next boot will re-adopt and bill it"
    )
    assert completed_at is not None, "a terminal run must carry completed_at"


def test_a_durably_cancelled_run_is_outside_the_boot_restore_set(env):
    """The decision the boot scan actually makes, asserted directly: ``cancelled`` is
    outside ``NON_TERMINAL_RUN_STATUSES``, which is why this fix needs no engine edit."""
    from agents.execution_engine.engine import NON_TERMINAL_RUN_STATUSES

    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id, status="generating")
    env["state"]["user"] = owner
    assert "generating" in NON_TERMINAL_RUN_STATUSES

    env["client"].post(f"/api/runs/{run_id}/cancel")

    status_after, _ = _run_status(env, run_id)
    assert status_after not in NON_TERMINAL_RUN_STATUSES


def test_cancel_of_a_terminal_run_writes_nothing(env):
    """Idempotence, asserted as the absence of a write — a Stop on a finished run must
    not overwrite ``completed`` with ``cancelled`` (that would corrupt history and make
    the run spuriously ``/resume``-eligible)."""
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id, status="completed")
    env["state"]["user"] = owner
    before = _run_status(env, run_id)

    resp = env["client"].post(f"/api/runs/{run_id}/cancel")
    assert resp.status_code == 200, resp.text
    assert _run_status(env, run_id) == before, "a terminal run must not be rewritten"
    assert _events(env, run_id) == [], "no durable row may be appended for a no-op Stop"


def test_terminal_cancel_response_is_byte_identical_to_the_pre_iss089_ack(env):
    """The exact bytes the pre-ISS-089 endpoint returned for the not-live branch, key
    order included — the FE ignores the body, but ``/cancel`` is a public contract and
    the no-op case must not have moved."""
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id, status="failed")
    env["state"]["user"] = owner

    resp = env["client"].post(f"/api/runs/{run_id}/cancel")
    assert resp.status_code == 200, resp.text
    assert resp.text == (
        '{"ok":true,"run_id":"' + run_id + '",'
        '"accepted":false,"cancelled":false,'
        '"status":"not_running","message":"No active pipeline"}'
    )


def test_durable_cancel_appends_a_pipeline_cancelled_row(env):
    """The cancellation is visible to SSE replay and to ``_reconcile_terminal_status``,
    which both read the durable tail rather than the status column."""
    owner = _seed_user(env, "owner")
    ws_id = f"ws-{uuid.uuid4().hex[:8]}"
    run_id = _seed_run(
        env, owner.id, status="generating", owner_id=owner.id, workspace_id=ws_id
    )
    _seed_event(env, run_id, owner_id=owner.id, workspace_id=ws_id, seq=1)
    env["state"]["user"] = owner

    resp = env["client"].post(f"/api/runs/{run_id}/cancel")
    assert resp.status_code == 200, resp.text
    assert _events(env, run_id) == [(1, "pipeline_start"), (2, "pipeline_cancelled")]


def test_durable_cancel_appends_past_an_already_occupied_seq(env):
    """FIX-240 / ISS-121's failure mode, mutation-tested: the chat lane allocates from the
    same per-run seq space, so ``max(seq)+1`` can already be taken by the time the row is
    written. A naive ``append_event`` is rejected by ``uq_run_events_scope_seq`` and the
    rejection is swallowed by the persist degrade — the audit row would silently vanish.
    ``append_event_at_or_after`` re-derives the tail and lands past it.

    The mutation is the race itself: the FIRST tail probe reports 3 (the tail as it was
    before the chat lane committed), so the endpoint attempts seq 4 — which is already
    taken. A naive ``append_event`` stops there and the row is lost; the collision-safe
    append re-probes, finds the real tail at 4, and lands at 5.
    """
    from agents.authz import ScopedStore

    owner = _seed_user(env, "owner")
    ws_id = f"ws-{uuid.uuid4().hex[:8]}"
    run_id = _seed_run(
        env, owner.id, status="generating", owner_id=owner.id, workspace_id=ws_id
    )
    for seq in (1, 2, 3):
        _seed_event(env, run_id, owner_id=owner.id, workspace_id=ws_id, seq=seq)
    _seed_event(env, run_id, owner_id=owner.id, workspace_id=ws_id, seq=4,
                type_="chat_message")  # the racing chat-lane row, already at max+1
    env["state"]["user"] = owner

    original_max_seq = ScopedStore._max_event_seq
    probes = {"n": 0}

    async def _stale_on_the_first_probe(self, rid):
        probes["n"] += 1
        if probes["n"] == 1:
            return 3
        return await original_max_seq(self, rid)

    ScopedStore._max_event_seq = _stale_on_the_first_probe
    try:
        resp = env["client"].post(f"/api/runs/{run_id}/cancel")
    finally:
        ScopedStore._max_event_seq = original_max_seq

    assert resp.status_code == 200, resp.text
    rows = _events(env, run_id)
    assert (5, "pipeline_cancelled") in rows, (
        f"the audit row was dropped on a seq collision instead of re-appended: {rows}"
    )
    assert _run_status(env, run_id)[0] == "cancelled"


def test_durable_cancel_survives_a_failed_audit_append(env):
    """The audit row is best-effort; the terminal status is not. A run whose workspace
    cannot be recovered (``run_events.workspace_id`` is NOT NULL, and the WS creation path
    leaves ``workflow_runs.workspace_id`` unset) still gets the write that closes the
    money hole."""
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id, status="running")  # no owner_id, no workspace_id
    env["state"]["user"] = owner

    resp = env["client"].post(f"/api/runs/{run_id}/cancel")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "cancelled"
    assert _run_status(env, run_id)[0] == "cancelled"
    assert _events(env, run_id) == [], "the append could not succeed here — and must not"


def test_cross_owner_cancel_writes_nothing(env):
    """IDOR / INV-8: the new write path is BEHIND the owner gate. An attacker must not be
    able to terminate someone else's run — the durable write makes that a destructive
    capability, not just an information leak."""
    victim = _seed_user(env, "victim")
    attacker = _seed_user(env, "attacker")
    run_id = _seed_run(env, victim.id, status="generating")
    env["state"]["user"] = attacker
    before = _run_status(env, run_id)

    resp = env["client"].post(f"/api/runs/{run_id}/cancel")
    assert resp.status_code == 404
    assert _run_status(env, run_id) == before, "a cross-owner Stop wrote to the victim's run"
    assert _events(env, run_id) == []


@pytest.mark.asyncio
async def test_a_cancelled_run_creates_no_driver_task_on_the_next_boot(env):
    """THE money assertion — the boot scan, not the endpoint.

    A resumable in-flight run is exactly the shape ``restore_non_terminal_runs`` branch
    (b) auto-resumes: compilable type + at least one durable ``run_events`` row. Without
    the durable cancel this scan spawns a driver task and the run finishes itself at the
    owner's expense; the assertion is on the TASK COUNT, because "no exception" is what a
    silently re-adopted run also looks like.
    """
    from agents.execution_engine.engine import ExecutionEngine
    from app.api.run_commands import cancel_run

    owner = _seed_user(env, "owner")
    ws_id = f"ws-{uuid.uuid4().hex[:8]}"
    run_id = _seed_run(
        env, owner.id, status="generating", owner_id=owner.id, workspace_id=ws_id
    )
    _seed_event(env, run_id, owner_id=owner.id, workspace_id=ws_id, seq=1)

    body = await cancel_run(run_id, current_user=owner)
    assert body["status"] == "cancelled", body

    created: list[str] = []
    real_create_task = asyncio.create_task

    async def _noop() -> None:
        return None

    def _spy_create_task(coro, *a, **k):
        created.append(
            getattr(coro, "__qualname__", None)
            or getattr(coro, "__name__", None)
            or repr(coro)
        )
        closer = getattr(coro, "close", None)
        if callable(closer):
            closer()  # a unit test never DRIVES a resume
        return real_create_task(_noop())

    asyncio.create_task = _spy_create_task  # type: ignore[assignment]
    try:
        await ExecutionEngine().restore_non_terminal_runs()
    finally:
        asyncio.create_task = real_create_task  # type: ignore[assignment]

    assert created == [], (
        f"the next boot re-adopted a run the owner stopped and spawned {created} — "
        f"this is the token-burn hole ISS-089 exists to close"
    )
    assert _run_status(env, run_id)[0] == "cancelled"


def test_the_non_terminal_status_set_has_exactly_one_definition():
    """Source guard (INV-12). This tuple was copied into a second module and cited by five
    different ``file:line`` values in one week, every one of them wrong within days. One
    definition, imported — a copy is how the drift keeps happening."""
    import ast
    import pathlib

    from agents.execution_engine.engine import NON_TERMINAL_RUN_STATUSES

    expected = {
        "running", "planning", "clarifying", "waiting_for_user",
        "generating", "analyzing", "revising",
    }
    assert set(NON_TERMINAL_RUN_STATUSES) == expected

    backend = pathlib.Path(__file__).resolve().parents[2]
    definitions: list[str] = []
    for package in ("agents", "app", "scripts"):
        for path in sorted((backend / package).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                value = getattr(node, "value", None)
                if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                    continue
                if not isinstance(value, (ast.Tuple, ast.List, ast.Set)):
                    continue
                items = value.elts
                if not items or not all(
                    isinstance(e, ast.Constant) and isinstance(e.value, str)
                    for e in items
                ):
                    continue
                if {e.value for e in items} == expected:
                    definitions.append(f"{path.relative_to(backend)}:{node.lineno}")

    assert len(definitions) == 1, (
        f"the non-terminal status set is defined {len(definitions)} times: {definitions}"
    )
    assert definitions[0].startswith("agents/execution_engine/engine.py:"), definitions


def test_cancel_cross_owner_is_denied_and_does_not_fire_event(env):
    """T-29-03-3: a cross-owner Stop denies with 404 and must NOT set the
    victim's cooperative event (IDOR → 404, never 403)."""
    victim = _seed_user(env, "victim")
    attacker = _seed_user(env, "attacker")
    run_id = _seed_run(env, victim.id)
    env["ws"]._CANCEL_EVENTS[run_id] = asyncio.Event()
    env["state"]["user"] = attacker

    resp = env["client"].post(f"/api/runs/{run_id}/cancel")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Unknown gate_key"
    assert env["ws"]._CANCEL_EVENTS[run_id].is_set() is False


def test_cancel_unknown_run_is_denied(env):
    caller = _seed_user(env, "caller")
    env["state"]["user"] = caller
    run_id = str(uuid.uuid4())

    resp = env["client"].post(f"/api/runs/{run_id}/cancel")
    assert resp.status_code == 404


# ────────────────────────────────────────────────────────────────────────────
# ISS-124 — the two APP-LAYER driver terminals must be DURABLE, not queue-only
# ────────────────────────────────────────────────────────────────────────────
#
# ``_drive_launch_to_queue`` and ``_drive_revision_to_queue`` both catch
# ``asyncio.CancelledError`` (the escalation path ``stop_run_driver`` takes when a
# driver cannot observe the cooperative event in time), push a ``pipeline_cancelled``
# FRAME onto the queue and set ``status="cancelled"`` — but write NO ``run_events``
# row. Two consequences, both live today:
#
#   1. The durable log of such a run has no terminal at all, so a fresh reopen
#      replays a dangling ``review_gate_ready`` (ISS-126) — i.e. this path keeps
#      MINTING the corrupted runs ISS-126 has to render.
#   2. ``stop_run_driver`` calls ``_reconcile_terminal_status`` once the task is
#      provably gone, and that function decides purely from the durable tail:
#      no ``pipeline_cancelled`` row → ``cancelled=[]``, ``completes=[]`` → the D2
#      fail-safe ``"failed"``, which OVERWRITES the driver's own "cancelled".
#      The owner's Stop is recorded as a failure.
#
# Every assertion below is on the durable ROW, never on the queued frame — the
# frame is already correct today, which is exactly why earlier probes missed this.


def _terminal_rows(env, run_id: str) -> list:
    """The durable ``pipeline_cancelled`` rows, with their event_ids."""
    from app.models.run_event import RunEvent

    db = env["ws"]._get_db()
    try:
        return [
            (r.seq, r.type, r.event_id, r.payload_json)
            for r in db.query(RunEvent)
            .filter(RunEvent.run_id == run_id, RunEvent.type == "pipeline_cancelled")
            .order_by(RunEvent.seq.asc())
            .all()
        ]
    finally:
        db.close()


class _CancellingEngine:
    """Stands in for the ExecutionEngine: raises CancelledError out of the drive."""

    def __init__(self, workspace_id: str = "ws-124"):
        self._workspace_id = workspace_id

    async def _recover_workspace_id(self, owner_id, run_id):
        return self._workspace_id

    async def execute(self, **kwargs):
        raise asyncio.CancelledError()
        yield  # pragma: no cover — makes this an async generator

    async def _handle_revision(self, **kwargs):
        raise asyncio.CancelledError()


class _HangingEngine(_CancellingEngine):
    """Blocks inside the drive so a REAL ``task.cancel()`` lands mid-await."""

    def __init__(self, workspace_id: str = "ws-124"):
        super().__init__(workspace_id)
        self.started = asyncio.Event()

    async def execute(self, **kwargs):
        self.started.set()
        await asyncio.Event().wait()
        yield  # pragma: no cover


def _patch_engine(monkeypatch, engine) -> None:
    import agents.execution_engine.engine as eng_mod

    monkeypatch.setattr(eng_mod, "get_execution_engine", lambda: engine)


async def _drive_launch(env, user, run_id, *, queue=None):
    from app.api.run_commands import _drive_launch_to_queue

    await _drive_launch_to_queue(
        workflow_run_id=run_id,
        pipeline_run_id=run_id,
        agents=[],
        content="idea",
        pipeline_type="user_stories",
        cancel_event=asyncio.Event(),
        user=user,
        attached_skills=[],
        attached_hooks=[],
        od_context=None,
        validated_images=[],
        gate_agent_ids=[],
        parent_run_id=None,
        model_overrides={},
        selections=None,
        event_queue=queue if queue is not None else asyncio.Queue(),
    )


@pytest.mark.asyncio
async def test_launch_driver_cancellation_is_durable(env, monkeypatch):
    """ISS-124: the launch driver's CancelledError branch must APPEND a durable
    ``pipeline_cancelled`` row carrying a real ``event_id`` — not only queue a frame."""
    user = _seed_user(env, "l124")
    run_id = _seed_run(env, user.id, owner_id=user.id, workspace_id="ws-124")
    _patch_engine(monkeypatch, _CancellingEngine())

    await _drive_launch(env, user, run_id)

    rows = _terminal_rows(env, run_id)
    assert len(rows) == 1, f"expected exactly one durable pipeline_cancelled row, got {rows}"
    _seq, _type, event_id, payload = rows[0]
    assert event_id, "the durable row must carry a real event_id (the replay de-dup key)"
    assert payload.get("pipeline_run_id") == run_id
    # and the status the driver itself writes is unchanged
    assert _run_status(env, run_id)[0] == "cancelled"


@pytest.mark.asyncio
async def test_launch_driver_durable_row_survives_a_real_task_cancel(env, monkeypatch):
    """ISS-124, the discriminating case: the append lives inside an
    ``except asyncio.CancelledError`` block and therefore must complete while the
    task is being cancelled FOR REAL — ``stop_run_driver`` reaches this branch via
    ``task.cancel()``, not by the engine raising. If the await were cut short the
    row would be missing exactly on the path that matters."""
    user = _seed_user(env, "l124real")
    run_id = _seed_run(env, user.id, owner_id=user.id, workspace_id="ws-124")
    engine = _HangingEngine()
    _patch_engine(monkeypatch, engine)

    queue: asyncio.Queue = asyncio.Queue()
    task = asyncio.get_running_loop().create_task(
        _drive_launch(env, user, run_id, queue=queue)
    )
    await engine.started.wait()  # the drive is provably INSIDE the engine await
    task.cancel()
    # The driver deliberately CONVERTS the cancellation into a terminal rather than
    # re-raising it — ``_drain_then_cancel`` only needs ``task.done()``. Observed, not
    # assumed: an earlier version of this test asserted a re-raise and was wrong.
    await task
    assert task.done() and not task.cancelled()

    rows = _terminal_rows(env, run_id)
    assert len(rows) == 1, f"a real task.cancel() left no durable terminal: {rows}"
    assert rows[0][2], "the durable row must carry a real event_id"


@pytest.mark.asyncio
async def test_a_cancelled_driver_reconciles_to_cancelled_not_failed(env, monkeypatch):
    """ISS-124's user-visible half: ``stop_run_driver`` runs
    ``_reconcile_terminal_status`` once the driver is provably gone, and that decides
    from the DURABLE TAIL alone. With no ``pipeline_cancelled`` row the D2 fail-safe
    fires and the owner's Stop is recorded as ``failed``."""
    from app.api.run_commands import _reconcile_terminal_status

    user = _seed_user(env, "l124rec")
    run_id = _seed_run(env, user.id, owner_id=user.id, workspace_id="ws-124")
    _patch_engine(monkeypatch, _CancellingEngine())

    await _drive_launch(env, user, run_id)
    await _reconcile_terminal_status(run_id)

    assert _run_status(env, run_id)[0] == "cancelled", (
        "the reconcile overwrote the owner's Stop with the D2 fail-safe"
    )


@pytest.mark.asyncio
async def test_revision_driver_cancellation_is_durable(env, monkeypatch):
    """ISS-124, second locus: ``_drive_revision_to_queue`` has the same shape and
    the same hole."""
    from app.api.run_commands import _drive_revision_to_queue

    user = _seed_user(env, "r124")
    parent_id = _seed_run(env, user.id, owner_id=user.id, workspace_id="ws-124")
    run_id = _seed_run(env, user.id, owner_id=user.id, workspace_id="ws-124")
    _patch_engine(monkeypatch, _CancellingEngine())

    await _drive_revision_to_queue(
        workflow_run_id=run_id,
        parent_run_id=parent_id,
        target_artifact_type="prototype",
        instruction="tweak it",
        user=user,
        cancel_event=asyncio.Event(),
        event_queue=asyncio.Queue(),
    )

    rows = _terminal_rows(env, run_id)
    assert len(rows) == 1, f"expected exactly one durable pipeline_cancelled row, got {rows}"
    assert rows[0][2], "the durable row must carry a real event_id"
    assert _run_status(env, run_id)[0] == "cancelled"
