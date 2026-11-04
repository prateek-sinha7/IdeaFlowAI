"""tests/integration/api/test_run_degraded_false_positive_api.py -- ISS-872.

Integration tests for the two app-layer status writers that needed the same
FIX-648 cross-check that ``_drive_launch_to_queue`` already has:

* ``_drive_revision_to_queue`` -- Change 2: captures ``degraded_failed_agents``
  from the ``pipeline_complete`` event and applies the cross-check before
  persisting terminal status.

* ``_reconcile_terminal_status`` -- Change 3: reads ``agents_failed`` from the
  degraded completion in the durable tail and cross-checks against
  ``agent_complete`` events in the same attempt.

All tests are unit-level mock tests: no real Postgres, no real engine, no real
network.  The DB is an in-memory SQLite (StaticPool) shared between sessions.
"""

from __future__ import annotations

import asyncio
import types
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Register every table the paths touch on Base.metadata BEFORE create_all.
import app.models.artifact_ref  # noqa: F401
import app.models.run_capabilities  # noqa: F401
import app.models.run_event  # noqa: F401
import app.models.workflow  # noqa: F401
import app.models.workspace  # noqa: F401
import agents.execution_engine.engine as engine_mod
from app.models.database import Base
from app.models.user import User
from app.models.workflow import WorkflowRun


# ============================================================================
# Shared harness (mirrors test_rest_revisions_api.py)
# ============================================================================


class _FakeUser:
    def __init__(self, uid: str) -> None:
        self.id = uid
        self.preferred_model = None
        self.tier = "enterprise"


class _StubEngine:
    """Minimal stub -- ``_handle_revision`` delegates to the caller-supplied
    behavior; ``_recover_workspace_id`` returns an empty workspace id."""

    def __init__(self, behavior) -> None:
        self._behavior = behavior
        self._recover_workspace_id = AsyncMock(return_value="")

    async def _handle_revision(self, **kwargs) -> None:
        await self._behavior(kwargs)


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

    yield {
        "ws": ws_module,
        "rc": rc_module,
        "Session": TestingSession,
    }

    Base.metadata.drop_all(bind=db_engine)
    db_engine.dispose()


def _seed_user(env) -> _FakeUser:
    db = env["Session"]()
    try:
        u = User(
            id=str(uuid.uuid4()),
            email="iss872-{}@example.com".format(uuid.uuid4().hex[:8]),
            cognito_sub=str(uuid.uuid4()),
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return _FakeUser(u.id)
    finally:
        db.close()


def _seed_child(env, owner_id: str, run_type: str = "ppt_revision") -> str:
    run_id = str(uuid.uuid4())
    db = env["Session"]()
    try:
        db.add(
            WorkflowRun(
                id=run_id,
                user_id=owner_id,
                owner_id=owner_id,
                title="Revision: iss872",
                type=run_type,
                status="revising",
                input="x",
                agent_count=1,
            )
        )
        db.commit()
    finally:
        db.close()
    return run_id


def _seed_run(env, owner_id: str, status: str = "failed") -> str:
    """Seed a WorkflowRun for reconcile tests."""
    run_id = str(uuid.uuid4())
    db = env["Session"]()
    try:
        db.add(
            WorkflowRun(
                id=run_id,
                user_id=owner_id,
                owner_id=owner_id,
                title="iss872 reconcile test",
                type="custom",
                status=status,
                input="x",
                agent_count=1,
            )
        )
        db.commit()
    finally:
        db.close()
    return run_id


def _row(env, run_id: str):
    db = env["Session"]()
    try:
        return db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    finally:
        db.close()


async def _drive_revision(env, run_id: str, user: _FakeUser, behavior) -> list:
    """Drive _drive_revision_to_queue directly; return drained queue events."""
    import app.api.run_commands as rc_module

    queue: asyncio.Queue = asyncio.Queue()
    stub = _StubEngine(behavior)

    with patch.object(engine_mod, "get_execution_engine", return_value=stub):
        await rc_module._drive_revision_to_queue(
            workflow_run_id=run_id,
            parent_run_id="parent-run-id",
            target_artifact_type="ppt_output",
            instruction="update slide 1",
            user=user,
            cancel_event=asyncio.Event(),
            event_queue=queue,
        )

    drained = []
    while True:
        item = queue.get_nowait()
        if item is None:
            break
        drained.append(item)
    return drained


# -- fake durable events -------------------------------------------------------


def _evt(type_: str, seq: int, payload=None) -> types.SimpleNamespace:
    """Build a minimal fake run_event object for _reconcile_terminal_status."""
    return types.SimpleNamespace(
        type=type_,
        seq=seq,
        payload_json=payload if payload is not None else {},
    )


# ============================================================================
# Change 2 -- _drive_revision_to_queue cross-check
# ============================================================================


class TestRevisionDriverFalsePositiveCrossCheck:
    """ISS-872 / FIX-648 parity in ``_drive_revision_to_queue``."""

    @pytest.mark.asyncio
    async def test_drive_revision_to_queue_returns_completed_when_all_failed_agents_also_completed(
        self, env, monkeypatch
    ) -> None:
        """All agents listed in agents_failed also emitted agent_complete in
        the same stream -- false positive -- status must be 'completed'.
        """
        owner = _seed_user(env)
        run_id = _seed_child(env, owner.id)

        async def _behavior(kwargs):
            send = kwargs["websocket_send_fn"]
            # agent_x completed successfully in the same stream.
            await send({"type": "agent_complete", "data": {"agent_id": "agent_x"}})
            # pipeline_complete incorrectly lists agent_x as failed.
            await send(
                {
                    "type": "pipeline_complete",
                    "data": {
                        "status": "degraded",
                        "agents_failed": ["agent_x"],
                        "final_output": "<html>ok</html>",
                    },
                }
            )

        await _drive_revision(env, run_id=run_id, user=owner, behavior=_behavior)

        assert _row(env, run_id).status == "completed", (
            "All agents in agents_failed also emitted agent_complete -- "
            "this is a false positive and must resolve to 'completed' (ISS-872)."
        )

    @pytest.mark.asyncio
    async def test_drive_revision_to_queue_returns_degraded_when_no_agent_complete(
        self, env, monkeypatch
    ) -> None:
        """agents_failed names an agent with NO matching agent_complete --
        genuinely failed -- status must stay 'degraded'.
        """
        owner = _seed_user(env)
        run_id = _seed_child(env, owner.id)

        async def _behavior(kwargs):
            send = kwargs["websocket_send_fn"]
            # No agent_complete for agent_x.
            await send(
                {
                    "type": "pipeline_complete",
                    "data": {
                        "status": "degraded",
                        "agents_failed": ["agent_x"],
                    },
                }
            )

        await _drive_revision(env, run_id=run_id, user=owner, behavior=_behavior)

        assert _row(env, run_id).status == "degraded", (
            "agent_x has no agent_complete -- it genuinely failed and the run "
            "must stay 'degraded'."
        )

    @pytest.mark.asyncio
    async def test_drive_revision_to_queue_returns_degraded_when_agents_failed_list_is_empty(
        self, env, monkeypatch
    ) -> None:
        """agents_failed is empty (convergence-cap abort) -- NOT a false positive
        -- status must remain 'degraded'.
        """
        owner = _seed_user(env)
        run_id = _seed_child(env, owner.id)

        async def _behavior(kwargs):
            send = kwargs["websocket_send_fn"]
            await send(
                {
                    "type": "pipeline_complete",
                    "data": {
                        "status": "degraded",
                        "agents_failed": [],
                        "degraded_reason": "loop_iterations cap reached",
                    },
                }
            )

        await _drive_revision(env, run_id=run_id, user=owner, behavior=_behavior)

        assert _row(env, run_id).status == "degraded", (
            "Empty agents_failed (convergence-cap abort) is not a false "
            "positive -- the run must stay 'degraded'."
        )

    @pytest.mark.asyncio
    async def test_drive_revision_to_queue_returns_degraded_when_some_agents_genuinely_failed(
        self, env, monkeypatch
    ) -> None:
        """Only some agents in agents_failed have matching agent_complete events;
        the others are genuinely unrecovered -- run stays 'degraded'.
        """
        owner = _seed_user(env)
        run_id = _seed_child(env, owner.id)

        async def _behavior(kwargs):
            send = kwargs["websocket_send_fn"]
            # agent_a recovered, agent_b did not.
            await send({"type": "agent_complete", "data": {"agent_id": "agent_a"}})
            await send(
                {
                    "type": "pipeline_complete",
                    "data": {
                        "status": "degraded",
                        "agents_failed": ["agent_a", "agent_b"],
                    },
                }
            )

        await _drive_revision(env, run_id=run_id, user=owner, behavior=_behavior)

        assert _row(env, run_id).status == "degraded", (
            "agent_b has no agent_complete -- the run must stay 'degraded' "
            "even though agent_a was a false positive."
        )


# ============================================================================
# Change 3 -- _reconcile_terminal_status cross-check
# ============================================================================


async def _reconcile(env, run_id: str, fake_events: list) -> None:
    """Call _reconcile_terminal_status with mocked store and engine."""
    import app.api.run_commands as rc_module

    mock_store_instance = MagicMock()
    mock_store_instance.read_events = AsyncMock(return_value=fake_events)

    with patch("agents.authz.ScopedStore", return_value=mock_store_instance):
        with patch.object(
            engine_mod,
            "get_execution_engine",
            return_value=MagicMock(_recover_workspace_id=AsyncMock(return_value="")),
        ):
            await rc_module._reconcile_terminal_status(run_id)


class TestReconcileTerminalStatusFalsePositiveCrossCheck:
    """ISS-872 / FIX-648 parity in ``_reconcile_terminal_status``."""

    @pytest.mark.asyncio
    async def test_reconcile_terminal_status_returns_completed_when_all_degraded_agents_also_completed(
        self, env
    ) -> None:
        """Durable log has a degraded completion that names an agent also present
        in an agent_complete event from the same attempt -- false positive --
        reconciled status must be 'completed'.
        """
        owner = _seed_user(env)
        run_id = _seed_run(env, owner.id)

        fake_events = [
            _evt("pipeline_start", seq=1),
            _evt("agent_complete", seq=2, payload={"agent_id": "agent_x"}),
            _evt(
                "pipeline_complete",
                seq=3,
                payload={"status": "degraded", "agents_failed": ["agent_x"]},
            ),
        ]

        await _reconcile(env, run_id, fake_events)

        assert _row(env, run_id).status == "completed", (
            "agent_x appeared in both agents_failed and agent_complete -- "
            "this is a false positive; reconcile must resolve to 'completed' (ISS-872)."
        )

    @pytest.mark.asyncio
    async def test_reconcile_terminal_status_returns_degraded_when_no_matching_agent_complete(
        self, env
    ) -> None:
        """Durable log has a degraded completion with an agents_failed agent that
        has NO agent_complete in the same attempt -- genuinely failed --
        reconciled status must be 'degraded'.
        """
        owner = _seed_user(env)
        run_id = _seed_run(env, owner.id)

        fake_events = [
            _evt("pipeline_start", seq=1),
            # No agent_complete for agent_x.
            _evt(
                "pipeline_complete",
                seq=2,
                payload={"status": "degraded", "agents_failed": ["agent_x"]},
            ),
        ]

        await _reconcile(env, run_id, fake_events)

        assert _row(env, run_id).status == "degraded", (
            "agent_x has no agent_complete in the durable tail -- the reconcile "
            "must stay 'degraded'."
        )

    @pytest.mark.asyncio
    async def test_reconcile_terminal_status_returns_degraded_when_agent_complete_from_prior_attempt(
        self, env
    ) -> None:
        """An agent_complete from a PRIOR attempt (before the last reattempt
        boundary) must NOT count -- the current attempt still shows the agent as
        failed, so reconciled status must be 'degraded'.
        """
        owner = _seed_user(env)
        run_id = _seed_run(env, owner.id)

        fake_events = [
            # Prior attempt.
            _evt("pipeline_start", seq=1),
            _evt("agent_complete", seq=2, payload={"agent_id": "agent_x"}),
            _evt(
                "pipeline_complete",
                seq=3,
                payload={"status": "degraded", "agents_failed": ["agent_x"]},
            ),
            # Resume boundary -- latest attempt starts here.
            _evt("run_resuming", seq=10),
            # No agent_complete for agent_x in this attempt.
            _evt(
                "pipeline_complete",
                seq=12,
                payload={"status": "degraded", "agents_failed": ["agent_x"]},
            ),
        ]

        await _reconcile(env, run_id, fake_events)

        assert _row(env, run_id).status == "degraded", (
            "The agent_complete at seq=2 is before the reattempt boundary "
            "(seq=10) and must not count toward the current attempt's recovery."
        )
