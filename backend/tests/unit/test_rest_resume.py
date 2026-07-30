"""tests/unit/test_rest_resume.py — RESUME-18 (Phase 50).

The endpoint battery for ``POST /api/runs/{id}/resume`` — the "reopen & fix"
headline that makes a terminal-FAILED run user-resumable. The endpoint is the ONLY
new surface; drive is pure reuse of the shipped Phase 45–49 resume tier via
``engine.resume_run`` (armed on the startup singleton). This suite pins the
endpoint's guards + the thin ``_drive_user_resume`` wrapper's honest-state
contract; the failed→resume E2E (cursor-skip + gate-at-failure) lives in
``tests/agents/test_restart_resume.py``.

Authorization: LOCK-E/ND-4 supersede — POR §8.1.

Coverage (RESEARCH §Validation map):
  * Owner gate (T-50-01): cross-owner + missing → 404 (never 403; no existence
    oracle; keyed on ``user_id`` never nullable ``owner_id``).
  * Eligibility fence (T-50-02): completed / cancelled → 409 ``run_not_resumable``.
  * Overlap mutex (T-50-03): an already-live run (registry entry) → 409
    ``pipeline_already_running`` (CR-01 vocab); a concurrent double-drive → exactly
    one 200, the other 409 (asyncio no-preemption atomicity).
  * Queue-before-flip (BUG-015): the live queue is registered BEFORE the
    ``failed→running`` commit so a reconnecting FE live-attaches.
  * Status flip + marker: ``failed→running`` + a single additive ``run_resuming``
    marker (no new status vocabulary; INV-12).
  * Arm-failure honest state (T-50-06): a raising ``resume_run`` flips the row back
    to ``failed`` (never stuck ``running`` with no task).

Offline — in-memory SQLite (StaticPool) on ``run_engine._get_db`` +
``run_commands._get_db``; stub engine via ``engine_mod.get_execution_engine`` so
``_stamp_resume_marker`` / ``resume_run`` / ``_recover_workspace_id`` are
spy-controllable. Assertions land at the endpoint/registry seam — NOT via
TestClient background-task timing.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Register every table the resume path touches on Base.metadata BEFORE create_all.
import app.models.artifact_ref  # noqa: F401
import app.models.run_event  # noqa: F401
import app.models.workflow  # noqa: F401
import app.models.workspace  # noqa: F401
import agents.execution_engine.engine as engine_mod
from app.models.database import Base
from app.models.user import User
from app.models.workflow import WorkflowRun


# ════════════════════════════════════════════════════════════════════════════
# Harness
# ════════════════════════════════════════════════════════════════════════════


class _FakeUser:
    def __init__(self, id: str):
        self.id = id
        self.preferred_model = None


class _StubEngine:
    """A spy-controllable stand-in for the armed engine singleton.

    ``_stamp_resume_marker`` records the row's status AT CALL TIME (the endpoint
    flips to ``running`` BEFORE stamping — step 5 before step 6 — so a correct
    ordering records ``"running"``). ``resume_run`` records the call and defers to
    ``resume_behavior`` (default no-op; a test can make it raise to exercise the
    arm-failure flip-back). ``_recover_workspace_id`` returns ``workspace_id`` (the
    reconciler's owner-scoped tail read is empty on the unit DB → maps to failed;
    the E2E proves the completed mapping).
    """

    def __init__(self) -> None:
        self.marker_status_calls: list[str] = []
        self.resume_calls: list[str] = []
        self.resume_behavior = None  # None → no-op; else async callable(run_id)
        self.workspace_id = None

    async def _stamp_resume_marker(self, wr) -> None:
        self.marker_status_calls.append(wr.status)

    async def resume_run(self, run_id: str) -> None:
        self.resume_calls.append(run_id)
        if self.resume_behavior is not None:
            await self.resume_behavior(run_id)

    async def _recover_workspace_id(self, owner_id: str, run_id: str):
        return self.workspace_id


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

    # Clear the module-global per-run registries so a prior test never leaks a
    # phantom-live entry into this one (the overlap mutex reads these).
    ws_module._PIPELINE_TASKS.clear()
    ws_module._PIPELINE_QUEUES.clear()
    ws_module._CANCEL_EVENTS.clear()
    ws_module._SUBSCRIBERS.clear()  # KAN-134: clear per-run fan-out bus subscribers

    stub = _StubEngine()
    monkeypatch.setattr(engine_mod, "get_execution_engine", lambda: stub)

    from app.api.run_commands import router
    from app.core.dependencies import get_current_user

    app = FastAPI()
    app.include_router(router)
    state: dict = {"user": None}
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    client = TestClient(app)

    yield {
        "ws": ws_module, "rc": rc_module, "client": client,
        "state": state, "Session": TestingSession, "engine": stub,
    }

    ws_module._PIPELINE_TASKS.clear()
    ws_module._PIPELINE_QUEUES.clear()
    ws_module._CANCEL_EVENTS.clear()
    ws_module._SUBSCRIBERS.clear()  # KAN-134: clear per-run fan-out bus subscribers
    Base.metadata.drop_all(bind=db_engine)
    db_engine.dispose()


def _seed_user(env, tag="u") -> _FakeUser:
    db = env["Session"]()
    try:
        u = User(
            id=str(uuid.uuid4()),
            email=f"res50-{tag}-{uuid.uuid4().hex[:8]}@example.com",
            password_hash="x",
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return _FakeUser(id=u.id)
    finally:
        db.close()


def _seed_run(env, owner_id: str, *, status: str, run_type="prototype") -> str:
    run_id = str(uuid.uuid4())
    db = env["Session"]()
    try:
        db.add(WorkflowRun(
            id=run_id, user_id=owner_id, owner_id=owner_id,
            title="a run", type=run_type, status=status, input="brief",
            agent_count=3,
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


def _post_resume(env, run_id: str):
    return env["client"].post(f"/api/runs/{run_id}/resume")


# ════════════════════════════════════════════════════════════════════════════
# Owner gate (T-50-01) — 404 never 403, keyed on user_id
# ════════════════════════════════════════════════════════════════════════════


def test_resume_cross_owner_404(env):
    owner = _seed_user(env, "owner")
    attacker = _seed_user(env, "attacker")
    run_id = _seed_run(env, owner.id, status="failed")
    env["state"]["user"] = attacker

    resp = _post_resume(env, run_id)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Unknown run"
    # The attacker never drove the resume, and the owner's run stayed failed.
    assert env["engine"].resume_calls == []
    assert _row(env, run_id).status == "failed"
    assert run_id not in env["ws"]._PIPELINE_QUEUES


def test_resume_missing_404(env):
    caller = _seed_user(env, "caller")
    env["state"]["user"] = caller
    resp = _post_resume(env, str(uuid.uuid4()))
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Unknown run"
    assert env["engine"].resume_calls == []


# ════════════════════════════════════════════════════════════════════════════
# Eligibility fence (T-50-02) — only failed runs are resumable
# ════════════════════════════════════════════════════════════════════════════


def test_resume_completed_409(env):
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id, status="completed")
    env["state"]["user"] = owner

    resp = _post_resume(env, run_id)
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "run_not_resumable"
    assert resp.json()["detail"]["recoverable"] is False
    assert env["engine"].resume_calls == []
    assert run_id not in env["ws"]._PIPELINE_QUEUES


def test_resume_cancelled_409(env):
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id, status="cancelled")
    env["state"]["user"] = owner

    resp = _post_resume(env, run_id)
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "run_not_resumable"
    assert env["engine"].resume_calls == []


# ════════════════════════════════════════════════════════════════════════════
# Overlap mutex (T-50-03) — already-live + concurrent double-drive
# ════════════════════════════════════════════════════════════════════════════


def test_resume_already_running_409(env):
    """A run that is registry-live (a driver task present) is rejected with the
    CR-01 ``pipeline_already_running`` code — even though its DB status is still
    ``failed`` (the overlap guard's authoritative signal is the in-process registry,
    not the DB status)."""
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id, status="failed")
    env["state"]["user"] = owner

    # Simulate a live driver already registered for this run id. The overlap guard
    # tests registry MEMBERSHIP only (not task state), so a sentinel object suffices.
    env["ws"]._PIPELINE_TASKS[run_id] = object()

    resp = _post_resume(env, run_id)
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "pipeline_already_running"
    # The guard rejected BEFORE any second drive was spawned.
    assert env["engine"].resume_calls == []


@pytest.mark.asyncio
async def test_resume_double_post_second_409(env):
    """Two concurrent drives of the endpoint coroutine: exactly one wins (200) and
    the other is rejected with a 409 (asyncio no-preemption atomicity — the winner
    registers the queue + flips ``running`` synchronously before any await yields to
    the loser). Only ONE resume is ever driven."""
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id, status="failed")
    rc = env["rc"]

    async def _call():
        try:
            return await rc.resume_run_endpoint(run_id, current_user=owner)
        except HTTPException as exc:
            return exc

    a, b = await asyncio.gather(_call(), _call())
    results = [a, b]
    oks = [r for r in results if isinstance(r, dict)]
    rejects = [r for r in results if isinstance(r, HTTPException)]
    assert len(oks) == 1 and len(rejects) == 1, results
    assert oks[0]["run_id"] == run_id
    assert rejects[0].status_code == 409
    # Exactly one live driver task was registered (no double-drive).
    assert list(env["ws"]._PIPELINE_TASKS).count(run_id) <= 1
    assert run_id in env["ws"]._PIPELINE_TASKS


# ════════════════════════════════════════════════════════════════════════════
# Queue-before-flip (BUG-015) — live-attach ordering
# ════════════════════════════════════════════════════════════════════════════


def test_resume_registers_queue_before_status_flip(env, monkeypatch):
    """The live queue is registered while the DB row is STILL ``failed`` — i.e. BEFORE
    the ``failed→running`` commit — so a reconnecting FE that observes ``running`` and
    opens the SSE stream finds a live queue (``run_id in _PIPELINE_QUEUES``)."""
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id, status="failed")
    env["state"]["user"] = owner
    rc = env["rc"]

    captured: list[str | None] = []
    orig_queue = rc._get_or_create_queue

    def _spy_queue(rid: str):
        row = _row(env, rid)
        captured.append(row.status if row else None)
        return orig_queue(rid)

    monkeypatch.setattr(rc, "_get_or_create_queue", _spy_queue)

    resp = _post_resume(env, run_id)
    assert resp.status_code == 200, resp.text
    # The queue was registered at a point where the flip had NOT yet committed.
    assert captured == ["failed"], captured
    assert run_id in env["ws"]._PIPELINE_QUEUES


# ════════════════════════════════════════════════════════════════════════════
# Status flip + additive marker
# ════════════════════════════════════════════════════════════════════════════


def test_resume_flips_running_and_stamps_marker(env):
    """The happy path flips ``failed→running`` and stamps exactly ONE additive
    ``run_resuming`` marker. The marker spy records the row status at call time —
    ``running`` proves the flip (step 5) preceded the marker (step 6)."""
    owner = _seed_user(env, "owner")
    run_id = _seed_run(env, owner.id, status="failed")
    env["state"]["user"] = owner

    resp = _post_resume(env, run_id)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"run_id": run_id}
    # Marker stamped once, and the row was already ``running`` at stamp time.
    assert env["engine"].marker_status_calls == ["running"]


# ════════════════════════════════════════════════════════════════════════════
# Arm-failure honest state (T-50-06)
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_resume_arm_failure_flips_back_to_failed(env):
    """If ``resume_run`` raises, the thin wrapper flips the row back to ``failed`` +
    records the error — never left stuck ``running`` with no live task. Drives
    ``_drive_user_resume`` directly from the endpoint-left ``running`` state."""
    owner = _seed_user(env, "owner")
    # The endpoint would have already flipped the row to ``running``; simulate that.
    run_id = _seed_run(env, owner.id, status="running")
    rc = env["rc"]

    async def _boom(_rid):
        raise RuntimeError("scripted arm failure")

    env["engine"].resume_behavior = _boom

    await rc._drive_user_resume(run_id, user=owner)

    row = _row(env, run_id)
    assert row.status == "failed", "arm failure must flip back to failed (honest state)"
    assert row.status != "running"
    assert "scripted arm failure" in (row.error or "")
