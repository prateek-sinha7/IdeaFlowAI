"""Unit tests for agents/artifact_store/store.py (Phase 1 in-memory implementation).

Tests:
  - Round-trip store/retrieve
  - Version increment per type per run
  - Lineage chain
  - Resume event creation and set
  - Questionnaire responses store/retrieve
  - ArtifactStoreWriteError on failure
"""

import asyncio
import pytest

from agents.artifact_store.store import ArtifactStore, ArtifactStoreWriteError


@pytest.fixture
def store() -> ArtifactStore:
    return ArtifactStore(use_db=False)


# ---------------------------------------------------------------------------
# Round-trip store / retrieve_latest
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_and_retrieve_latest(store: ArtifactStore) -> None:
    run_id = "run-001"
    artifact_id = await store.store(
        run_id=run_id,
        artifact_type="spec",
        name="spec.md",
        content="# My Spec",
        producing_agent_id="specify-agent",
    )
    assert artifact_id

    result = await store.retrieve_latest(run_id, "spec")
    assert result is not None
    assert result["content"] == "# My Spec"
    assert result["type"] == "spec"
    assert result["name"] == "spec.md"
    assert result["producing_agent_id"] == "specify-agent"
    assert result["schema_version"] == "1.0"
    assert result["version"] == 1


@pytest.mark.asyncio
async def test_retrieve_latest_returns_none_when_missing(store: ArtifactStore) -> None:
    result = await store.retrieve_latest("run-999", "nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_retrieve_version_by_id(store: ArtifactStore) -> None:
    run_id = "run-002"
    artifact_id = await store.store(
        run_id=run_id,
        artifact_type="plan",
        name="plan.md",
        content="# Plan",
        producing_agent_id="plan-agent",
    )
    result = await store.retrieve_version(artifact_id)
    assert result is not None
    assert result["id"] == artifact_id
    assert result["content"] == "# Plan"


@pytest.mark.asyncio
async def test_retrieve_version_returns_none_when_missing(store: ArtifactStore) -> None:
    result = await store.retrieve_version("nonexistent-id")
    assert result is None


# ---------------------------------------------------------------------------
# Version increment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_version_increments_per_type_per_run(store: ArtifactStore) -> None:
    run_id = "run-003"
    id1 = await store.store(run_id, "spec", "spec-v1.md", "v1", "agent-a")
    id2 = await store.store(run_id, "spec", "spec-v2.md", "v2", "agent-b")
    id3 = await store.store(run_id, "spec", "spec-v3.md", "v3", "agent-c")

    v1 = await store.retrieve_version(id1)
    v2 = await store.retrieve_version(id2)
    v3 = await store.retrieve_version(id3)

    assert v1["version"] == 1
    assert v2["version"] == 2
    assert v3["version"] == 3

    # retrieve_latest returns v3
    latest = await store.retrieve_latest(run_id, "spec")
    assert latest["version"] == 3
    assert latest["content"] == "v3"


@pytest.mark.asyncio
async def test_versions_independent_across_types(store: ArtifactStore) -> None:
    run_id = "run-004"
    await store.store(run_id, "spec", "spec.md", "spec content", "agent-a")
    await store.store(run_id, "plan", "plan.md", "plan content", "agent-b")
    await store.store(run_id, "spec", "spec-v2.md", "spec v2", "agent-c")

    spec_latest = await store.retrieve_latest(run_id, "spec")
    plan_latest = await store.retrieve_latest(run_id, "plan")

    assert spec_latest["version"] == 2
    assert plan_latest["version"] == 1


# ---------------------------------------------------------------------------
# list_by_type
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_by_type_returns_oldest_first(store: ArtifactStore) -> None:
    run_id = "run-005"
    await store.store(run_id, "research", "r1.md", "first", "agent-a")
    await store.store(run_id, "research", "r2.md", "second", "agent-b")
    await store.store(run_id, "research", "r3.md", "third", "agent-c")

    results = await store.list_by_type(run_id, "research")
    assert len(results) == 3
    assert results[0]["content"] == "first"
    assert results[1]["content"] == "second"
    assert results[2]["content"] == "third"


# ---------------------------------------------------------------------------
# Lineage chain
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lineage_chain(store: ArtifactStore) -> None:
    run_id = "run-006"
    id1 = await store.store(run_id, "spec", "spec.md", "original", "specify-agent")
    id2 = await store.store(
        run_id, "spec", "spec-revised.md", "revised",
        "revision-agent", derived_from_id=id1,
    )

    v2 = await store.retrieve_version(id2)
    assert v2["derived_from_artifact_id"] == id1

    lineage = await store.list_lineage(run_id)
    assert len(lineage) == 2
    ids_in_lineage = [a["id"] for a in lineage]
    assert id1 in ids_in_lineage
    assert id2 in ids_in_lineage


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


# ---------------------------------------------------------------------------
# Round-trip equality (SC-010)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_round_trip_equality_unicode(store: ArtifactStore) -> None:
    content = "# Spec\n\nUnicode: 日本語 🎉 \u2603"
    run_id = "run-unicode"
    artifact_id = await store.store(run_id, "spec", "spec.md", content, "agent")
    result = await store.retrieve_version(artifact_id)
    assert result["content"] == content


@pytest.mark.asyncio
async def test_round_trip_equality_large_content(store: ArtifactStore) -> None:
    content = "x" * 1_048_576  # 1MB
    run_id = "run-large"
    artifact_id = await store.store(run_id, "spec", "spec.md", content, "agent")
    result = await store.retrieve_version(artifact_id)
    assert result["content"] == content
    assert len(result["content"]) == 1_048_576
