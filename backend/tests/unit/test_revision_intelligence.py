"""T058 — Unit tests for revision intelligence (Phase 6 / FR-014).

Tests:
  - _handle_revision raises ValueError for empty instruction
  - _handle_revision raises ValueError for non-existent artifact
  - _handle_revision stores result as new version with derived_from_artifact_id
  - _handle_revision annotates run with planning_context_unavailable when no planning_context
  - _handle_revision includes original artifact, version history, and instruction as separate inputs
  - section-level targeting: content outside targeted section preserved byte-for-byte
    (verified by checking the revision context contains the original content verbatim)
"""

from __future__ import annotations

import asyncio
import json
import pytest

from agents.artifact_store.store import ArtifactStore
from agents.execution_engine.engine import ExecutionEngine


@pytest.fixture
def store() -> ArtifactStore:
    return ArtifactStore(use_db=False)


@pytest.fixture
def engine(store: ArtifactStore) -> ExecutionEngine:
    eng = ExecutionEngine()
    eng._store = store
    return eng


# ---------------------------------------------------------------------------
# Validation guards
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_instruction_raises(engine: ExecutionEngine, store: ArtifactStore) -> None:
    engine._store = store
    events: list[dict] = []

    async def ws(e: dict) -> None:
        events.append(e)

    with pytest.raises(ValueError, match="empty"):
        await engine._handle_revision(
            parent_run_id="run-parent",
            target_artifact_type="spec",
            instruction="",
            pipeline_run_id="run-rev-1",
            websocket_send_fn=ws,
        )


@pytest.mark.asyncio
async def test_whitespace_only_instruction_raises(engine: ExecutionEngine, store: ArtifactStore) -> None:
    engine._store = store
    events: list[dict] = []

    async def ws(e: dict) -> None:
        events.append(e)

    with pytest.raises(ValueError, match="empty"):
        await engine._handle_revision(
            parent_run_id="run-parent",
            target_artifact_type="spec",
            instruction="   ",
            pipeline_run_id="run-rev-2",
            websocket_send_fn=ws,
        )


@pytest.mark.asyncio
async def test_nonexistent_artifact_raises(engine: ExecutionEngine, store: ArtifactStore) -> None:
    engine._store = store
    events: list[dict] = []

    async def ws(e: dict) -> None:
        events.append(e)

    with pytest.raises(ValueError, match="No artifact"):
        await engine._handle_revision(
            parent_run_id="run-no-artifacts",
            target_artifact_type="spec",
            instruction="Fix the introduction section",
            pipeline_run_id="run-rev-3",
            websocket_send_fn=ws,
        )


# ---------------------------------------------------------------------------
# Successful revision
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revision_stores_new_version_with_lineage(
    engine: ExecutionEngine, store: ArtifactStore
) -> None:
    engine._store = store
    parent_run_id = "run-parent-ok"

    # Store an original artifact
    original_id = await store.store(
        run_id=parent_run_id,
        artifact_type="spec",
        name="spec.md",
        content="# Original Spec\n\nSection 1: Introduction\nSection 2: Requirements",
        producing_agent_id="specify-agent",
    )

    events: list[dict] = []

    async def ws(e: dict) -> None:
        events.append(e)

    await engine._handle_revision(
        parent_run_id=parent_run_id,
        target_artifact_type="spec",
        instruction="Improve the Introduction section",
        pipeline_run_id="run-rev-ok",
        websocket_send_fn=ws,
    )

    # pipeline_complete should be emitted
    complete_events = [e for e in events if e["type"] == "pipeline_complete"]
    assert len(complete_events) == 1

    # The revision artifact should be stored in the revision run
    revision_artifact = await store.retrieve_latest("run-rev-ok", "spec")
    assert revision_artifact is not None
    assert revision_artifact["derived_from_artifact_id"] == original_id
    assert revision_artifact["version"] == 1


@pytest.mark.asyncio
async def test_revision_contains_three_separate_inputs(
    engine: ExecutionEngine, store: ArtifactStore
) -> None:
    """The revision context must contain original artifact, version history,
    and instruction as three separate structured sections (NOT concatenated)."""
    engine._store = store
    parent_run_id = "run-parent-3inputs"

    original_content = "# Spec\n\nSection 1: Introduction\nSection 2: Requirements"
    await store.store(
        run_id=parent_run_id,
        artifact_type="spec",
        name="spec.md",
        content=original_content,
        producing_agent_id="specify-agent",
    )

    events: list[dict] = []

    async def ws(e: dict) -> None:
        events.append(e)

    instruction = "Improve the Introduction section only"
    await engine._handle_revision(
        parent_run_id=parent_run_id,
        target_artifact_type="spec",
        instruction=instruction,
        pipeline_run_id="run-rev-3inputs",
        websocket_send_fn=ws,
    )

    complete = next(e for e in events if e["type"] == "pipeline_complete")
    final_output = complete["data"]["final_output"]

    # All three sections must be present and clearly separated
    assert "=== ORIGINAL ARTIFACT" in final_output
    assert "=== VERSION HISTORY" in final_output
    assert "=== REVISION INSTRUCTION" in final_output

    # Original content preserved verbatim (byte-for-byte)
    assert original_content in final_output

    # Instruction present verbatim
    assert instruction in final_output

    # They must NOT be concatenated — each section has its own header
    orig_pos = final_output.index("=== ORIGINAL ARTIFACT")
    hist_pos = final_output.index("=== VERSION HISTORY")
    instr_pos = final_output.index("=== REVISION INSTRUCTION")
    assert orig_pos < hist_pos < instr_pos


@pytest.mark.asyncio
async def test_planning_context_unavailable_when_no_planning_artifact(
    engine: ExecutionEngine, store: ArtifactStore
) -> None:
    """When no planning_context artifact exists for the parent run,
    planning_context_unavailable must be True in the pipeline_complete event."""
    engine._store = store
    parent_run_id = "run-parent-no-planning"

    await store.store(
        run_id=parent_run_id,
        artifact_type="spec",
        name="spec.md",
        content="# Spec",
        producing_agent_id="specify-agent",
    )

    events: list[dict] = []

    async def ws(e: dict) -> None:
        events.append(e)

    await engine._handle_revision(
        parent_run_id=parent_run_id,
        target_artifact_type="spec",
        instruction="Fix section 2",
        pipeline_run_id="run-rev-no-planning",
        websocket_send_fn=ws,
    )

    complete = next(e for e in events if e["type"] == "pipeline_complete")
    assert complete["data"]["planning_context_unavailable"] is True


@pytest.mark.asyncio
async def test_planning_context_available_when_present(
    engine: ExecutionEngine, store: ArtifactStore
) -> None:
    """When planning_context artifact exists, planning_context_unavailable is False."""
    engine._store = store
    parent_run_id = "run-parent-with-planning"

    await store.store(
        run_id=parent_run_id,
        artifact_type="spec",
        name="spec.md",
        content="# Spec",
        producing_agent_id="specify-agent",
    )
    await store.store(
        run_id=parent_run_id,
        artifact_type="planning_context",
        name="planning_context",
        content=json.dumps({"inferred_intent": "Build a login feature", "execution_gate": "PROCEED"}),
        producing_agent_id="deep-planner",
    )

    events: list[dict] = []

    async def ws(e: dict) -> None:
        events.append(e)

    await engine._handle_revision(
        parent_run_id=parent_run_id,
        target_artifact_type="spec",
        instruction="Fix section 2",
        pipeline_run_id="run-rev-with-planning",
        websocket_send_fn=ws,
    )

    complete = next(e for e in events if e["type"] == "pipeline_complete")
    assert complete["data"]["planning_context_unavailable"] is False

    # Planning context should be prepended to the revision context
    final_output = complete["data"]["final_output"]
    assert "PLANNING CONTEXT" in final_output
    assert "Build a login feature" in final_output
