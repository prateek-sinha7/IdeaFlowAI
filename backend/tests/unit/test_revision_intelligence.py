"""T058 — Unit tests for revision intelligence (Phase 6 / FR-014).

Rewritten in 05-06 to the typed ``ScopedStore`` / ``artifact_refs`` API: the thin
``ArtifactStore`` is no longer the artifact path for ``_handle_revision`` — the
cross-run parent reads + the revision write go through the owner-scoped persisted
``ScopedStore`` against ``artifact_refs`` (assert_owns-gated, T-5-SEED).

Tests:
  - _handle_revision raises ValueError for empty / whitespace instruction
  - _handle_revision raises ValueError for non-existent artifact
  - _handle_revision stores result as a new ArtifactRef with derived_from + version==1
  - _handle_revision annotates run with planning_context_unavailable when no planning_context
  - _handle_revision includes original artifact, version history, instruction as separate inputs
  - planning_context available path prepends the planning context verbatim
  - CROSS-OWNER DENIAL (T-5-SEED): a second owner revising the first owner's
    parent run raises PermissionError before any read.

Offline / in-memory SQLite / no API key — ``SessionLocal`` is monkeypatched onto
a shared StaticPool engine so every ``ScopedStore`` (engine path, no injected
session) hits the test DB.
"""

from __future__ import annotations

import hashlib
import json
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from agents.authz import ScopedStore
from agents.execution_engine.engine import ExecutionEngine
from app.models.artifact_ref import ArtifactRef
from app.models.database import Base
from app.models.workflow import WorkflowRun

OWNER = "owner-x"
OTHER_OWNER = "owner-y"
WS = "ws-x"


@pytest.fixture
def db_factory(monkeypatch):
    """In-memory SQLite (StaticPool, shared connection) wired into
    ``app.models.database.SessionLocal`` so every engine-path ``ScopedStore``
    (no injected session) opens THIS DB. Returns a session factory for seeding."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    # Every ScopedStore._acquire() does `from app.models.database import SessionLocal`
    # then `SessionLocal()` — patch the attribute so it resolves to our test factory.
    monkeypatch.setattr("app.models.database.SessionLocal", TestingSession, raising=False)
    try:
        yield TestingSession
    finally:
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def engine() -> ExecutionEngine:
    return ExecutionEngine()


def _seed_run(session_factory, *, run_id: str, owner_id: str, workspace_id: str = WS) -> None:
    """Insert the parent ``workflow_runs`` row (assert_owns reads its true owner)."""
    s = session_factory()
    try:
        s.add(
            WorkflowRun(
                id=run_id,
                user_id=owner_id,
                owner_id=owner_id,
                workspace_id=workspace_id,
                title="t",
                type="prototype",
                status="completed",
                input="t",
            )
        )
        s.commit()
    finally:
        s.close()


def _seed_ref(
    session_factory,
    *,
    run_id: str,
    owner_id: str,
    kind: str,
    content: str,
    version: int = 1,
    workspace_id: str = WS,
) -> str:
    """Insert one ``artifact_refs`` row (visibility=workspace, like the producer
    writes) and return its id."""
    ref_id = str(uuid.uuid4())
    s = session_factory()
    try:
        s.add(
            ArtifactRef(
                id=ref_id,
                run_id=run_id,
                owner_id=owner_id,
                workspace_id=workspace_id,
                kind=kind,
                producer_step="specify",
                producer_agent="specify-agent",
                content=content,
                content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                location=f"artifact_refs/{kind}",
                version=version,
                visibility="workspace",
            )
        )
        s.commit()
    finally:
        s.close()
    return ref_id


# ---------------------------------------------------------------------------
# Validation guards
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_instruction_raises(engine: ExecutionEngine, db_factory) -> None:
    async def ws(e: dict) -> None:  # pragma: no cover - never reached
        pass

    with pytest.raises(ValueError, match="empty"):
        await engine._handle_revision(
            parent_run_id="run-parent",
            target_artifact_type="spec",
            instruction="",
            pipeline_run_id="run-rev-1",
            websocket_send_fn=ws,
            owner_id=OWNER,
        )


@pytest.mark.asyncio
async def test_whitespace_only_instruction_raises(engine: ExecutionEngine, db_factory) -> None:
    async def ws(e: dict) -> None:  # pragma: no cover - never reached
        pass

    with pytest.raises(ValueError, match="empty"):
        await engine._handle_revision(
            parent_run_id="run-parent",
            target_artifact_type="spec",
            instruction="   ",
            pipeline_run_id="run-rev-2",
            websocket_send_fn=ws,
            owner_id=OWNER,
        )


@pytest.mark.asyncio
async def test_nonexistent_artifact_raises(engine: ExecutionEngine, db_factory) -> None:
    parent = "run-no-artifacts"
    _seed_run(db_factory, run_id=parent, owner_id=OWNER)  # owned, but no refs

    async def ws(e: dict) -> None:  # pragma: no cover - never reached
        pass

    with pytest.raises(ValueError, match="No artifact"):
        await engine._handle_revision(
            parent_run_id=parent,
            target_artifact_type="spec",
            instruction="Fix the introduction section",
            pipeline_run_id="run-rev-3",
            websocket_send_fn=ws,
            owner_id=OWNER,
        )


# ---------------------------------------------------------------------------
# Successful revision
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revision_stores_new_version_with_lineage(engine: ExecutionEngine, db_factory) -> None:
    parent = "run-parent-ok"
    _seed_run(db_factory, run_id=parent, owner_id=OWNER)
    original_id = _seed_ref(
        db_factory,
        run_id=parent,
        owner_id=OWNER,
        kind="spec",
        content="# Original Spec\n\nSection 1: Introduction\nSection 2: Requirements",
    )

    events: list[dict] = []

    async def ws(e: dict) -> None:
        events.append(e)

    await engine._handle_revision(
        parent_run_id=parent,
        target_artifact_type="spec",
        instruction="Improve the Introduction section",
        pipeline_run_id="run-rev-ok",
        websocket_send_fn=ws,
        owner_id=OWNER,
    )

    complete_events = [e for e in events if e["type"] == "pipeline_complete"]
    assert len(complete_events) == 1

    # The revision artifact landed in the revision run via ScopedStore.
    store = ScopedStore(owner_id=OWNER)
    refs = await store.list_refs("run-rev-ok", kind="spec")
    assert refs, "revision artifact not persisted"
    revision = refs[-1]
    assert revision.derived_from == original_id
    assert revision.version == 1


@pytest.mark.asyncio
async def test_revision_contains_three_separate_inputs(engine: ExecutionEngine, db_factory) -> None:
    parent = "run-parent-3inputs"
    _seed_run(db_factory, run_id=parent, owner_id=OWNER)
    original_content = "# Spec\n\nSection 1: Introduction\nSection 2: Requirements"
    _seed_ref(db_factory, run_id=parent, owner_id=OWNER, kind="spec", content=original_content)

    events: list[dict] = []

    async def ws(e: dict) -> None:
        events.append(e)

    instruction = "Improve the Introduction section only"
    await engine._handle_revision(
        parent_run_id=parent,
        target_artifact_type="spec",
        instruction=instruction,
        pipeline_run_id="run-rev-3inputs",
        websocket_send_fn=ws,
        owner_id=OWNER,
    )

    complete = next(e for e in events if e["type"] == "pipeline_complete")
    final_output = complete["data"]["final_output"]

    assert "=== ORIGINAL ARTIFACT" in final_output
    assert "=== VERSION HISTORY" in final_output
    assert "=== REVISION INSTRUCTION" in final_output

    # Original content + instruction preserved verbatim.
    assert original_content in final_output
    assert instruction in final_output

    orig_pos = final_output.index("=== ORIGINAL ARTIFACT")
    hist_pos = final_output.index("=== VERSION HISTORY")
    instr_pos = final_output.index("=== REVISION INSTRUCTION")
    assert orig_pos < hist_pos < instr_pos


@pytest.mark.asyncio
async def test_planning_context_unavailable_when_no_planning_artifact(
    engine: ExecutionEngine, db_factory
) -> None:
    parent = "run-parent-no-planning"
    _seed_run(db_factory, run_id=parent, owner_id=OWNER)
    _seed_ref(db_factory, run_id=parent, owner_id=OWNER, kind="spec", content="# Spec")

    events: list[dict] = []

    async def ws(e: dict) -> None:
        events.append(e)

    await engine._handle_revision(
        parent_run_id=parent,
        target_artifact_type="spec",
        instruction="Fix section 2",
        pipeline_run_id="run-rev-no-planning",
        websocket_send_fn=ws,
        owner_id=OWNER,
    )

    complete = next(e for e in events if e["type"] == "pipeline_complete")
    assert complete["data"]["planning_context_unavailable"] is True


@pytest.mark.asyncio
async def test_planning_context_available_when_present(engine: ExecutionEngine, db_factory) -> None:
    parent = "run-parent-with-planning"
    _seed_run(db_factory, run_id=parent, owner_id=OWNER)
    _seed_ref(db_factory, run_id=parent, owner_id=OWNER, kind="spec", content="# Spec")
    _seed_ref(
        db_factory,
        run_id=parent,
        owner_id=OWNER,
        kind="planning_context",
        content=json.dumps({"inferred_intent": "Build a login feature", "execution_gate": "PROCEED"}),
    )

    events: list[dict] = []

    async def ws(e: dict) -> None:
        events.append(e)

    await engine._handle_revision(
        parent_run_id=parent,
        target_artifact_type="spec",
        instruction="Fix section 2",
        pipeline_run_id="run-rev-with-planning",
        websocket_send_fn=ws,
        owner_id=OWNER,
    )

    complete = next(e for e in events if e["type"] == "pipeline_complete")
    assert complete["data"]["planning_context_unavailable"] is False

    final_output = complete["data"]["final_output"]
    assert "PLANNING CONTEXT" in final_output
    assert "Build a login feature" in final_output


# ---------------------------------------------------------------------------
# Cross-owner denial (T-5-SEED)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_owner_revision_denied(engine: ExecutionEngine, db_factory) -> None:
    """A second owner revising the FIRST owner's parent run is denied by
    assert_owns(parent_run_id) BEFORE any cross-run read (T-5-SEED)."""
    parent = "run-parent-owned-by-x"
    _seed_run(db_factory, run_id=parent, owner_id=OWNER)
    _seed_ref(db_factory, run_id=parent, owner_id=OWNER, kind="spec", content="# Owner X spec")

    events: list[dict] = []

    async def ws(e: dict) -> None:
        events.append(e)

    with pytest.raises(PermissionError):
        await engine._handle_revision(
            parent_run_id=parent,
            target_artifact_type="spec",
            instruction="Steal owner X's spec",
            pipeline_run_id="run-rev-cross-owner",
            websocket_send_fn=ws,
            owner_id=OTHER_OWNER,  # NOT the parent owner
        )

    # No revision artifact must have been written for the attacker's run.
    attacker_store = ScopedStore(owner_id=OTHER_OWNER)
    refs = await attacker_store.list_refs("run-rev-cross-owner", kind="spec")
    assert refs == []


# ---------------------------------------------------------------------------
# CR-01 regression: revision run_events persist + /events resolution on a real DB
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revision_run_events_persist_and_resolve_on_real_db(
    engine: ExecutionEngine, db_factory
) -> None:
    """CR-01 (iteration-2 BLOCKER) regression.

    The round-1 WR-06 fix routed revision emits through a ``_RunEventSink``, but on
    a REAL DB it (a) stamped ``run_events.workspace_id = None`` (NOT NULL) → the
    IntegrityError was swallowed by the WR-02 narrow-catch, so NO ledger row landed,
    and (b) left the revision ``workflow_runs`` row owner/workspace-None, so the
    owner+workspace-scoped ``get_run`` (and therefore the /events endpoint) 404'd.

    This test creates the revision ``workflow_runs`` row exactly as the WS layer
    does (owner set, workspace UNSET), drives ``_handle_revision``, then asserts:
      1. ``run_events`` rows actually persisted (the sink got a real workspace).
      2. The revision run row had its scope stamped back (owner + workspace).
      3. An owner+workspace-scoped ``ScopedStore`` (mirroring the /events endpoint
         that builds ``ScopedStore(owner, workflow_run.workspace_id)``) resolves
         the run AND replays the stamped ``pipeline_start``/``pipeline_complete``
         events — i.e. the run no longer 404s.
    """
    parent = "run-parent-events"
    _seed_run(db_factory, run_id=parent, owner_id=OWNER, workspace_id=WS)
    _seed_ref(
        db_factory,
        run_id=parent,
        owner_id=OWNER,
        kind="spec",
        content="# Spec\n\nSection 1",
        workspace_id=WS,
    )

    rev_run_id = "run-rev-events"
    # Mirror websocket.py: revision run created with a real owner but NO workspace
    # (the workspace is the parent artifact's workspace, resolved in the engine).
    s = db_factory()
    try:
        s.add(
            WorkflowRun(
                id=rev_run_id,
                user_id=OWNER,
                owner_id=OWNER,        # AUTHZ-03 — never None at creation
                workspace_id=None,     # transiently null — engine stamps it back
                title="Revision: x",
                type="spec_revision",
                status="revising",
                input="x",
            )
        )
        s.commit()
    finally:
        s.close()

    events: list[dict] = []

    async def ws(e: dict) -> None:
        events.append(e)

    await engine._handle_revision(
        parent_run_id=parent,
        target_artifact_type="spec",
        instruction="Tighten section 1",
        pipeline_run_id=rev_run_id,
        websocket_send_fn=ws,
        owner_id=OWNER,
    )

    # (2) The revision run row had its scope stamped back to the parent workspace.
    chk = db_factory()
    try:
        row = chk.query(WorkflowRun).filter(WorkflowRun.id == rev_run_id).first()
        assert row is not None
        assert row.owner_id == OWNER
        assert row.workspace_id == WS, "revision run workspace not stamped back (CR-01)"
    finally:
        chk.close()

    # (3) Mirror the /events endpoint: ScopedStore(owner, workflow_run.workspace_id).
    endpoint_store = ScopedStore(owner_id=OWNER, workspace_id=WS)
    resolved = await endpoint_store.get_run(rev_run_id)
    assert resolved is not None, "revision run 404s under owner+workspace scope (CR-01)"

    # (1) The stamped lifecycle events actually persisted and replay in seq order.
    rows = await endpoint_store.read_events(rev_run_id, after_seq=0)
    types = [r.type for r in rows]
    assert "pipeline_start" in types, "pipeline_start run_events row missing (CR-01)"
    assert "pipeline_complete" in types, "pipeline_complete run_events row missing (CR-01)"
    # Every persisted row carries the real workspace (AUTHZ-01, never None).
    assert all(r.workspace_id == WS for r in rows)
    assert all(r.owner_id == OWNER for r in rows)
    # seq is monotonic per run (idempotent replay contract, API-05).
    seqs = [r.seq for r in rows]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)


# ---------------------------------------------------------------------------
# Clarifications round-trip (05-06 Task 3): clarify_engine write → websocket read
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clarifications_round_trip_via_artifact_refs(db_factory) -> None:
    """ClarifyEngine._persist_qa writes the clarifications payload into
    artifact_refs (kind=clarifications); the reconnect read path resolves it back
    via ScopedStore.list_refs — owner-scoped, served entirely from the typed layer.
    A non-owner read returns nothing (T-5-IDOR)."""
    from agents.execution_engine.clarify_engine import ClarifyEngine

    run_id = "run-clarify-rt"
    _seed_run(db_factory, run_id=run_id, owner_id=OWNER)

    clarify = ClarifyEngine()
    clarify._owner_id = OWNER
    clarify._workspace_id = WS

    questions = [
        {"question_id": "r1_q1", "question_text": "What topic?", "impact_level": "high"},
    ]
    responses = [{"question_id": "r1_q1", "answer": "Login feature"}]
    await clarify._persist_qa(run_id, questions, responses, round_num=1)

    # Owner read resolves the clarifications payload back from artifact_refs.
    owner_store = ScopedStore(owner_id=OWNER)
    refs = await owner_store.list_refs(run_id, kind="clarifications")
    assert refs, "clarifications payload not persisted to artifact_refs"
    payload = json.loads(refs[-1].content)
    assert payload[0]["question_id"] == "r1_q1"
    assert payload[0]["answer"] == "Login feature"

    # A non-owner read returns nothing (no cross-session disclosure).
    other_store = ScopedStore(owner_id=OTHER_OWNER)
    other_refs = await other_store.list_refs(run_id, kind="clarifications")
    assert other_refs == []
