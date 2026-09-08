"""Tests for the host-capacity admission gate (specs/014 D-01/D-02/D-03) —
``_require_host_capacity`` in ``app/api/run_commands.py`` and its inline twin
in ``app/api/handoff.py``.

Two layers:

1. Direct unit tests of ``_require_host_capacity`` itself — every branch
   (disabled / admin / blind / engaged) without any HTTP machinery.
2. End-to-end endpoint tests reusing this repo's existing per-file harness
   patterns (``test_rest_run_launch.py`` / ``test_rest_resume.py`` /
   ``test_rest_revisions.py`` / ``test_rest_answers_cancel.py`` /
   ``test_handoff_api.py``) to prove the wiring actually reaches a real HTTP
   response — including the D-01 regression guard that every EXEMPT endpoint
   (cancel, gate, answers, steering) still returns 2xx while the gate is
   engaged.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models.artifact_ref  # noqa: F401
import app.models.run_capabilities  # noqa: F401
import app.models.run_event  # noqa: F401
import app.models.workflow  # noqa: F401
import app.models.workspace  # noqa: F401
import agents.execution_engine.engine as engine_mod
from app.core.config import settings
from app.models.database import Base
from app.models.user import User
from app.models.workflow import WorkflowRun
from app.services import capacity_state as cs

UTC = timezone.utc


class _FakeUser:
    def __init__(self, id: str, *, tier: str = "enterprise", is_admin: bool = False):
        self.id = id
        self.preferred_model = None
        self.tier = tier
        self.is_admin = is_admin


def _engaged_decision(now: datetime) -> cs.AdmissionState:
    return cs.AdmissionState(
        engaged=True,
        engaged_at=now,
        breach_streak=2,
        blind=False,
        blind_reason=None,
        signals=(cs.Signal(name="cpu", value=91.0, threshold=75.0),),
        evaluated_at=now,
    )


def _allowing_decision(now: datetime) -> cs.AdmissionState:
    return cs.AdmissionState(
        engaged=False,
        engaged_at=None,
        breach_streak=0,
        blind=False,
        blind_reason=None,
        signals=(),
        evaluated_at=now,
    )


@pytest.fixture(autouse=True)
def _clean_capacity_state_and_settings(monkeypatch):
    """Every test starts from the shipped defaults (gate disabled) and a
    clean state holder, restoring both afterwards."""
    cs.reset_state_for_tests()
    original_gate_enabled = settings.HOST_CAPACITY_GATE_ENABLED
    yield
    settings.HOST_CAPACITY_GATE_ENABLED = original_gate_enabled
    cs.reset_state_for_tests()


# ---------------------------------------------------------------------------
# 1. Direct unit tests of _require_host_capacity
# ---------------------------------------------------------------------------


class TestRequireHostCapacityDirect:
    def test_noop_when_gate_disabled_even_if_engaged(self, monkeypatch):
        from app.api.run_commands import _require_host_capacity

        monkeypatch.setattr(settings, "HOST_CAPACITY_GATE_ENABLED", False)
        cs.publish_decision(_engaged_decision(datetime.now(UTC)))
        _require_host_capacity(_FakeUser("u1"))  # must not raise

    def test_noop_for_admin_even_if_engaged(self, monkeypatch):
        from app.api.run_commands import _require_host_capacity

        monkeypatch.setattr(settings, "HOST_CAPACITY_GATE_ENABLED", True)
        cs.publish_decision(_engaged_decision(datetime.now(UTC)))
        _require_host_capacity(_FakeUser("u1", is_admin=True))  # must not raise

    def test_noop_when_blind_even_if_gate_enabled(self, monkeypatch):
        from app.api.run_commands import _require_host_capacity

        monkeypatch.setattr(settings, "HOST_CAPACITY_GATE_ENABLED", True)
        # INITIAL_ADMISSION_STATE (the reset default) is blind.
        _require_host_capacity(_FakeUser("u1"))  # must not raise

    def test_noop_when_allowing(self, monkeypatch):
        from app.api.run_commands import _require_host_capacity

        monkeypatch.setattr(settings, "HOST_CAPACITY_GATE_ENABLED", True)
        cs.publish_decision(_allowing_decision(datetime.now(UTC)))
        _require_host_capacity(_FakeUser("u1"))  # must not raise

    def test_raises_503_with_full_contract_when_engaged(self, monkeypatch):
        from app.api.run_commands import _require_host_capacity

        monkeypatch.setattr(settings, "HOST_CAPACITY_GATE_ENABLED", True)
        monkeypatch.setattr(settings, "HOST_CAPACITY_RETRY_AFTER_SECONDS", 120)
        cs.publish_decision(_engaged_decision(datetime.now(UTC)))

        with pytest.raises(HTTPException) as excinfo:
            _require_host_capacity(_FakeUser("u1"))

        exc = excinfo.value
        assert exc.status_code == 503
        assert exc.headers is not None
        assert exc.headers["Retry-After"] == "120"
        assert exc.detail["code"] == "host_capacity_exhausted"
        assert exc.detail["recoverable"] is True
        assert exc.detail["retry_after_seconds"] == 120
        assert exc.detail["signals"] == [
            {"name": "cpu", "value": 91.0, "threshold": 75.0}
        ]

    def test_non_admin_flag_missing_entirely_still_gated(self, monkeypatch):
        """A caller object with no ``is_admin`` attribute at all must be
        treated as non-admin (``getattr(..., False)``), not exempted by
        accident."""
        from app.api.run_commands import _require_host_capacity

        class _BareUser:
            id = "bare"

        monkeypatch.setattr(settings, "HOST_CAPACITY_GATE_ENABLED", True)
        cs.publish_decision(_engaged_decision(datetime.now(UTC)))
        with pytest.raises(HTTPException):
            _require_host_capacity(_BareUser())


# ---------------------------------------------------------------------------
# 2a. End-to-end — POST /api/runs (launch), gated
# ---------------------------------------------------------------------------


class _RecordingEngine:
    invoked = False

    async def execute(self, **kwargs):
        _RecordingEngine.invoked = True
        yield {"type": "pipeline_start", "data": {"agents": []}}
        yield {"type": "pipeline_complete", "data": {"final_output": "done"}}


@pytest.fixture
def launch_env(monkeypatch):
    from app.api import run_engine as ws_module
    import app.api.run_commands as rc_module

    db_engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    Base.metadata.create_all(bind=db_engine)
    monkeypatch.setattr(ws_module, "_get_db", lambda: TestingSession())
    monkeypatch.setattr(rc_module, "_get_db", lambda: TestingSession())

    _RecordingEngine.invoked = False
    monkeypatch.setattr(engine_mod, "get_execution_engine", lambda: _RecordingEngine())

    from app.api.run_commands import router
    from app.core.dependencies import get_current_user

    app = FastAPI()
    app.include_router(router)
    state: dict = {"user": None}
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    client = TestClient(app)

    yield {"client": client, "state": state, "Session": TestingSession}

    Base.metadata.drop_all(bind=db_engine)
    db_engine.dispose()


def _seed_user(session_factory, *, tier="enterprise", is_admin=False) -> _FakeUser:
    db = session_factory()
    try:
        u = User(
            id=str(uuid.uuid4()),
            email=f"capgate-{uuid.uuid4().hex[:8]}@example.com",
            password_hash="x",
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return _FakeUser(id=u.id, tier=tier, is_admin=is_admin)
    finally:
        db.close()


def _run_count(session_factory) -> int:
    db = session_factory()
    try:
        return db.query(WorkflowRun).count()
    finally:
        db.close()


class TestLaunchIsGated:
    def test_launch_503s_when_gate_engaged_and_enabled(self, launch_env, monkeypatch):
        monkeypatch.setattr(settings, "HOST_CAPACITY_GATE_ENABLED", True)
        cs.publish_decision(_engaged_decision(datetime.now(UTC)))
        user = _seed_user(launch_env["Session"])
        launch_env["state"]["user"] = user

        resp = launch_env["client"].post(
            "/api/runs", json={"message": "build it", "pipeline_type": "user_stories"}
        )
        assert resp.status_code == 503, resp.text
        assert resp.json()["detail"]["code"] == "host_capacity_exhausted"
        assert resp.headers.get("retry-after") is not None
        # Rejected BEFORE any mint (specs/014 §5's admission-control framing).
        assert _run_count(launch_env["Session"]) == 0
        assert _RecordingEngine.invoked is False

    def test_launch_unaffected_when_gate_disabled_default(
        self, launch_env, monkeypatch
    ):
        """The default (HOST_CAPACITY_GATE_ENABLED=False) must leave launch
        completely unaffected even when the underlying decision is engaged —
        this is what makes the feature safe to ship dark (D-10)."""
        monkeypatch.setattr(settings, "HOST_CAPACITY_GATE_ENABLED", False)
        cs.publish_decision(_engaged_decision(datetime.now(UTC)))
        user = _seed_user(launch_env["Session"])
        launch_env["state"]["user"] = user

        resp = launch_env["client"].post(
            "/api/runs", json={"message": "build it", "pipeline_type": "user_stories"}
        )
        assert resp.status_code == 200, resp.text
        assert _run_count(launch_env["Session"]) == 1

    def test_launch_unaffected_for_admin_even_when_engaged(
        self, launch_env, monkeypatch
    ):
        monkeypatch.setattr(settings, "HOST_CAPACITY_GATE_ENABLED", True)
        cs.publish_decision(_engaged_decision(datetime.now(UTC)))
        admin = _seed_user(launch_env["Session"], is_admin=True)
        launch_env["state"]["user"] = admin

        resp = launch_env["client"].post(
            "/api/runs", json={"message": "build it", "pipeline_type": "user_stories"}
        )
        assert resp.status_code == 200, resp.text

    def test_launch_unaffected_when_gate_enabled_but_blind(
        self, launch_env, monkeypatch
    ):
        monkeypatch.setattr(settings, "HOST_CAPACITY_GATE_ENABLED", True)
        # No publish_decision() call — stays at INITIAL_ADMISSION_STATE (blind).
        user = _seed_user(launch_env["Session"])
        launch_env["state"]["user"] = user

        resp = launch_env["client"].post(
            "/api/runs", json={"message": "build it", "pipeline_type": "user_stories"}
        )
        assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# 2b. End-to-end — POST /{id}/cancel and /{id}/answers remain EXEMPT (D-01)
# ---------------------------------------------------------------------------


@pytest.fixture
def answers_cancel_env(monkeypatch):
    import app.models.database as db_module
    from app.api import run_commands as rc_module
    from app.api import run_engine as ws_module

    db_engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    Base.metadata.create_all(bind=db_engine)
    monkeypatch.setattr(ws_module, "_get_db", lambda: TestingSession())
    monkeypatch.setattr(rc_module, "_get_db", lambda: TestingSession())
    monkeypatch.setattr(db_module, "SessionLocal", TestingSession)

    import agents.artifact_store.store as store_mod

    store_mod._STORE = None
    store_mod.get_artifact_store()

    ws_module._CANCEL_EVENTS.clear()
    ws_module._PIPELINE_TASKS.clear()

    from app.api.run_commands import router
    from app.core.dependencies import get_current_user

    app = FastAPI()
    app.include_router(router)
    state: dict = {"user": None}
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    client = TestClient(app)

    yield {"client": client, "state": state, "Session": TestingSession}

    Base.metadata.drop_all(bind=db_engine)
    db_engine.dispose()
    store_mod._STORE = None
    ws_module._CANCEL_EVENTS.clear()
    ws_module._PIPELINE_TASKS.clear()


def _seed_ac_run(session_factory, user_id: str, *, status: str = "running") -> str:
    run_id = str(uuid.uuid4())
    db = session_factory()
    try:
        db.add(
            WorkflowRun(
                id=run_id,
                user_id=user_id,
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


class TestCancelAndAnswersAreExempt:
    """D-01 regression guard: the gate must NEVER block an operation that
    releases or resolves work already in flight, even while fully engaged."""

    def test_cancel_still_200s_while_gate_engaged(
        self, answers_cancel_env, monkeypatch
    ):
        monkeypatch.setattr(settings, "HOST_CAPACITY_GATE_ENABLED", True)
        cs.publish_decision(_engaged_decision(datetime.now(UTC)))

        owner = _FakeUser(str(uuid.uuid4()))
        db = answers_cancel_env["Session"]()
        try:
            db.add(
                User(id=owner.id, email=f"{owner.id}@example.com", password_hash="x")
            )
            db.commit()
        finally:
            db.close()
        run_id = _seed_ac_run(answers_cancel_env["Session"], owner.id)
        answers_cancel_env["state"]["user"] = owner

        resp = answers_cancel_env["client"].post(f"/api/runs/{run_id}/cancel")
        assert resp.status_code == 200, resp.text

    def test_answers_still_resolve_while_gate_engaged(
        self, answers_cancel_env, monkeypatch
    ):
        monkeypatch.setattr(settings, "HOST_CAPACITY_GATE_ENABLED", True)
        cs.publish_decision(_engaged_decision(datetime.now(UTC)))

        owner = _FakeUser(str(uuid.uuid4()))
        db = answers_cancel_env["Session"]()
        try:
            db.add(
                User(id=owner.id, email=f"{owner.id}@example.com", password_hash="x")
            )
            db.commit()
        finally:
            db.close()
        run_id = _seed_ac_run(answers_cancel_env["Session"], owner.id)
        answers_cancel_env["state"]["user"] = owner

        resp = answers_cancel_env["client"].post(
            f"/api/runs/{run_id}/answers",
            json={"responses": [{"question_id": "q1", "answer": "yes"}]},
        )
        assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# 2c. End-to-end — POST /{id}/resume is gated
# ---------------------------------------------------------------------------


class _ResumeStubEngine:
    async def _stamp_resume_marker(self, wr) -> None:
        pass

    async def resume_run(self, run_id: str) -> None:
        pass

    async def _recover_workspace_id(self, owner_id: str, run_id: str):
        return None


@pytest.fixture
def resume_env(monkeypatch):
    from app.api import run_engine as ws_module
    import app.api.run_commands as rc_module

    db_engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    Base.metadata.create_all(bind=db_engine)
    monkeypatch.setattr(ws_module, "_get_db", lambda: TestingSession())
    monkeypatch.setattr(rc_module, "_get_db", lambda: TestingSession())
    ws_module._PIPELINE_TASKS.clear()
    ws_module._PIPELINE_QUEUES.clear()
    ws_module._CANCEL_EVENTS.clear()
    ws_module._SUBSCRIBERS.clear()

    monkeypatch.setattr(engine_mod, "get_execution_engine", lambda: _ResumeStubEngine())

    from app.api.run_commands import router
    from app.core.dependencies import get_current_user

    app = FastAPI()
    app.include_router(router)
    state: dict = {"user": None}
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    client = TestClient(app)

    yield {"client": client, "state": state, "Session": TestingSession}

    ws_module._PIPELINE_TASKS.clear()
    ws_module._PIPELINE_QUEUES.clear()
    ws_module._CANCEL_EVENTS.clear()
    ws_module._SUBSCRIBERS.clear()
    Base.metadata.drop_all(bind=db_engine)
    db_engine.dispose()


def _seed_resume_run(session_factory, owner_id: str, *, status="failed") -> str:
    run_id = str(uuid.uuid4())
    db = session_factory()
    try:
        db.add(
            WorkflowRun(
                id=run_id,
                user_id=owner_id,
                owner_id=owner_id,
                title="a run",
                type="prototype",
                status=status,
                input="brief",
                agent_count=3,
            )
        )
        db.commit()
    finally:
        db.close()
    return run_id


class TestResumeIsGated:
    def test_resume_503s_when_gate_engaged_and_enabled(self, resume_env, monkeypatch):
        monkeypatch.setattr(settings, "HOST_CAPACITY_GATE_ENABLED", True)
        cs.publish_decision(_engaged_decision(datetime.now(UTC)))
        owner = _seed_user(resume_env["Session"])
        run_id = _seed_resume_run(resume_env["Session"], owner.id)
        resume_env["state"]["user"] = owner

        resp = resume_env["client"].post(f"/api/runs/{run_id}/resume")
        assert resp.status_code == 503, resp.text
        assert resp.json()["detail"]["code"] == "host_capacity_exhausted"
        # Row must stay in its pre-resume terminal state — never flipped to
        # running for a resume that was refused (specs/014 D-08).
        db = resume_env["Session"]()
        try:
            row = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
            assert row.status == "failed"
        finally:
            db.close()

    def test_resume_unaffected_when_gate_disabled(self, resume_env, monkeypatch):
        monkeypatch.setattr(settings, "HOST_CAPACITY_GATE_ENABLED", False)
        cs.publish_decision(_engaged_decision(datetime.now(UTC)))
        owner = _seed_user(resume_env["Session"])
        run_id = _seed_resume_run(resume_env["Session"], owner.id)
        resume_env["state"]["user"] = owner

        resp = resume_env["client"].post(f"/api/runs/{run_id}/resume")
        assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# 2d. End-to-end — POST /{id}/revisions is gated
# ---------------------------------------------------------------------------


@pytest.fixture
def revision_env(monkeypatch):
    from app.api import run_engine as ws_module
    import app.api.run_commands as rc_module

    db_engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
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

    yield {"client": client, "state": state, "Session": TestingSession}

    Base.metadata.drop_all(bind=db_engine)
    db_engine.dispose()


def _seed_revision_parent(session_factory, owner_id: str, run_type="ppt") -> str:
    parent_id = str(uuid.uuid4())
    db = session_factory()
    try:
        db.add(
            WorkflowRun(
                id=parent_id,
                user_id=owner_id,
                owner_id=owner_id,
                title="parent deck",
                type=run_type,
                status="completed",
                input="make a deck",
                agent_count=3,
            )
        )
        db.commit()
    finally:
        db.close()
    return parent_id


class TestCreateRevisionIsGated:
    def test_revision_503s_when_gate_engaged_and_enabled(
        self, revision_env, monkeypatch
    ):
        monkeypatch.setattr(settings, "HOST_CAPACITY_GATE_ENABLED", True)
        cs.publish_decision(_engaged_decision(datetime.now(UTC)))
        owner = _seed_user(revision_env["Session"])
        parent_id = _seed_revision_parent(revision_env["Session"], owner.id)
        revision_env["state"]["user"] = owner

        resp = revision_env["client"].post(
            f"/api/runs/{parent_id}/revisions",
            json={"target_artifact_type": "ppt_output", "instruction": "make it blue"},
        )
        assert resp.status_code == 503, resp.text
        assert resp.json()["detail"]["code"] == "host_capacity_exhausted"
        # No child row minted for a refused revision.
        db = revision_env["Session"]()
        try:
            children = (
                db.query(WorkflowRun)
                .filter(WorkflowRun.parent_run_id == parent_id)
                .count()
            )
            assert children == 0
        finally:
            db.close()

    def test_revision_unaffected_when_gate_disabled(self, revision_env, monkeypatch):
        monkeypatch.setattr(settings, "HOST_CAPACITY_GATE_ENABLED", False)
        cs.publish_decision(_engaged_decision(datetime.now(UTC)))
        owner = _seed_user(revision_env["Session"])
        parent_id = _seed_revision_parent(revision_env["Session"], owner.id)
        revision_env["state"]["user"] = owner

        resp = revision_env["client"].post(
            f"/api/runs/{parent_id}/revisions",
            json={"target_artifact_type": "ppt_output", "instruction": "make it blue"},
        )
        assert resp.status_code == 200, resp.text

    def test_cross_owner_404_takes_precedence_over_capacity_gate(
        self, revision_env, monkeypatch
    ):
        """The owner check runs BEFORE the capacity gate (specs/014 Wave 2.1
        task notes), so IDOR must still 404 even while the gate is engaged —
        the gate must never become an oracle that reveals a run exists."""
        monkeypatch.setattr(settings, "HOST_CAPACITY_GATE_ENABLED", True)
        cs.publish_decision(_engaged_decision(datetime.now(UTC)))
        owner = _seed_user(revision_env["Session"])
        parent_id = _seed_revision_parent(revision_env["Session"], owner.id)
        attacker = _seed_user(revision_env["Session"])
        revision_env["state"]["user"] = attacker

        resp = revision_env["client"].post(
            f"/api/runs/{parent_id}/revisions",
            json={"target_artifact_type": "ppt_output", "instruction": "x"},
        )
        assert resp.status_code == 404, resp.text
