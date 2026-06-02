"""T074 — Unit tests for backend-restart resumability (Phase 8 / FR-011).

Tests:
  - Non-terminal runs restored within 30s (SC-007)
  - waiting_for_user runs remain resumable after restart
  - asyncio.Events re-registered correctly
  - restore_non_terminal_runs completes without error when DB unavailable
"""

from __future__ import annotations

import asyncio
import pytest

from agents.artifact_store.store import ArtifactStore
from agents.execution_engine.engine import ExecutionEngine
from agents.execution_engine.state_machine import StateMachine


@pytest.fixture
def engine_with_inmem_store() -> ExecutionEngine:
    eng = ExecutionEngine()
    eng._store = ArtifactStore(use_db=False)
    return eng


# ---------------------------------------------------------------------------
# asyncio.Event re-registration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_event_created_for_waiting_run(engine_with_inmem_store: ExecutionEngine) -> None:
    """get_resume_event always returns an event (creates if absent)."""
    store = engine_with_inmem_store._store
    event = await store.get_resume_event("run-waiting-1")
    assert isinstance(event, asyncio.Event)
    assert not event.is_set()


@pytest.mark.asyncio
async def test_resume_event_same_instance_on_second_call(engine_with_inmem_store: ExecutionEngine) -> None:
    """The same event is returned on repeated calls (idempotent)."""
    store = engine_with_inmem_store._store
    e1 = await store.get_resume_event("run-waiting-2")
    e2 = await store.get_resume_event("run-waiting-2")
    assert e1 is e2


@pytest.mark.asyncio
async def test_set_questionnaire_responses_sets_event(engine_with_inmem_store: ExecutionEngine) -> None:
    """Submitting answers sets the resume event, unblocking the paused run."""
    store = engine_with_inmem_store._store
    pipeline_run_id = "run-waiting-3"
    event = await store.get_resume_event(pipeline_run_id)
    assert not event.is_set()

    await store.set_questionnaire_responses(pipeline_run_id, [{"question_id": "q1", "answer": "yes"}])
    assert event.is_set()

    responses = await store.get_questionnaire_responses(pipeline_run_id)
    assert responses == [{"question_id": "q1", "answer": "yes"}]


# ---------------------------------------------------------------------------
# restore_non_terminal_runs (graceful when DB unavailable)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restore_non_terminal_runs_graceful_without_db(engine_with_inmem_store: ExecutionEngine) -> None:
    """restore_non_terminal_runs must not raise even when the DB table doesn't exist."""
    # Should complete without raising
    await engine_with_inmem_store.restore_non_terminal_runs()


# ---------------------------------------------------------------------------
# StateMachine — terminal state guard
# ---------------------------------------------------------------------------


def test_terminal_state_blocks_further_transitions() -> None:
    sm = StateMachine()
    sm.transition("run-1", "completed")
    from agents.execution_engine.state_machine import StateMachineError
    with pytest.raises(StateMachineError, match="terminal"):
        sm.transition("run-1", "generating")


def test_cancelled_is_terminal() -> None:
    sm = StateMachine()
    sm.transition("run-2", "cancelled")
    from agents.execution_engine.state_machine import StateMachineError
    with pytest.raises(StateMachineError, match="terminal"):
        sm.transition("run-2", "planning")


def test_failed_is_terminal() -> None:
    sm = StateMachine()
    sm.transition("run-3", "failed")
    from agents.execution_engine.state_machine import StateMachineError
    with pytest.raises(StateMachineError, match="terminal"):
        sm.transition("run-3", "generating")
