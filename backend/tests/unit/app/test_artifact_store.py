"""Unit tests for agents/artifact_store/store.py — the HITL pause/resume half.

The artifact-persistence half (store/retrieve_latest/retrieve_version/list_by_type/
list_lineage + the WorkflowArtifact DB usage) was DELETED in 05-07 (PERSIST-02) once
all consumers were migrated onto the typed ArtifactGraph + persisted artifact_refs
layer. What remains — and what this suite covers — is the in-memory per-process
asyncio.Event HITL mechanism (Phase 8 owns HITL):

  - Resume event creation / identity
  - Questionnaire responses store/retrieve
  - Review-gate response store/retrieve
"""

import asyncio
import pytest

from agents.artifact_store.store import ArtifactStore, get_artifact_store


@pytest.fixture
def store() -> ArtifactStore:
    return ArtifactStore()


# ---------------------------------------------------------------------------
# Resume event (Human_Gate pause/resume)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_resume_event_creates_event(store: ArtifactStore) -> None:
    event = await store.get_resume_event("pipeline-abc")
    assert isinstance(event, asyncio.Event)
    assert not event.is_set()


@pytest.mark.asyncio
async def test_get_resume_event_returns_same_event(store: ArtifactStore) -> None:
    e1 = await store.get_resume_event("pipeline-xyz")
    e2 = await store.get_resume_event("pipeline-xyz")
    assert e1 is e2


@pytest.mark.asyncio
async def test_set_questionnaire_responses_sets_event(store: ArtifactStore) -> None:
    pipeline_run_id = "pipeline-q1"
    event = await store.get_resume_event(pipeline_run_id)
    assert not event.is_set()

    responses = [{"question_id": "q1", "answer": "Option A"}]
    await store.set_questionnaire_responses(pipeline_run_id, responses)

    assert event.is_set()
    retrieved = await store.get_questionnaire_responses(pipeline_run_id)
    assert retrieved == responses


@pytest.mark.asyncio
async def test_get_questionnaire_responses_returns_none_before_submission(
    store: ArtifactStore,
) -> None:
    result = await store.get_questionnaire_responses("pipeline-not-submitted")
    assert result is None


@pytest.mark.asyncio
async def test_force_proceed_defaults_false_and_for_plain_submit(
    store: ArtifactStore,
) -> None:
    """ISS-027: the force-proceed flag is False before any submit and stays False
    for an ordinary answer submission (byte-identical default)."""
    pipeline_run_id = "pipeline-q-noflag"
    assert await store.get_questionnaire_force_proceed("pipeline-never") is False

    await store.set_questionnaire_responses(
        pipeline_run_id, [{"question_id": "q1", "answer": "Option A"}]
    )
    assert await store.get_questionnaire_force_proceed(pipeline_run_id) is False


@pytest.mark.asyncio
async def test_force_proceed_set_when_skip_clarification(
    store: ArtifactStore,
) -> None:
    """ISS-027: skip_clarification=True records the force-proceed flag per run."""
    pipeline_run_id = "pipeline-q-skip"
    await store.set_questionnaire_responses(
        pipeline_run_id, [], skip_clarification=True
    )
    assert await store.get_questionnaire_force_proceed(pipeline_run_id) is True
    # The resume event is still set (the run unblocks regardless of the flag).
    event = await store.get_resume_event(pipeline_run_id)
    assert event.is_set()


# ---------------------------------------------------------------------------
# Review gate (prototype spec/plan review)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_review_event_creates_and_returns_same_event(
    store: ArtifactStore,
) -> None:
    e1 = await store.get_review_event("run-1:prototype-specify")
    e2 = await store.get_review_event("run-1:prototype-specify")
    assert isinstance(e1, asyncio.Event)
    assert e1 is e2
    assert not e1.is_set()


@pytest.mark.asyncio
async def test_set_review_response_sets_event_and_round_trips(
    store: ArtifactStore,
) -> None:
    gate_key = "run-1:prototype-plan"
    event = await store.get_review_event(gate_key)
    assert not event.is_set()

    await store.set_review_response(gate_key, approved=True, edited_content="edited")

    assert event.is_set()
    response = await store.get_review_response(gate_key)
    # REDO-GATE: the additive action/instructions keys default to the prior
    # approve behavior (action="approve", instructions=None) for every existing caller.
    assert response == {
        "approved": True,
        "edited_content": "edited",
        "action": "approve",
        "instructions": None,
    }


@pytest.mark.asyncio
async def test_set_review_response_round_trips_redo_action(
    store: ArtifactStore,
) -> None:
    """REDO-GATE test #1 — a redo action + instructions round-trip through the store."""
    gate_key = "run-redo:prototype-specify"
    event = await store.get_review_event(gate_key)
    assert not event.is_set()

    await store.set_review_response(
        gate_key, approved=False, action="redo", instructions="add dark mode"
    )

    assert event.is_set()
    response = await store.get_review_response(gate_key)
    assert response == {
        "approved": False,
        "edited_content": None,
        "action": "redo",
        "instructions": "add dark mode",
    }


@pytest.mark.asyncio
async def test_get_review_response_returns_none_before_submission(
    store: ArtifactStore,
) -> None:
    assert await store.get_review_response("run-1:not-submitted") is None


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------


def test_get_artifact_store_is_a_singleton() -> None:
    assert get_artifact_store() is get_artifact_store()
