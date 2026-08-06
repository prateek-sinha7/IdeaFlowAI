"""T058 — Unit tests for revision intelligence (Phase 6 / FR-014).

Rewritten in 05-06 to the typed ``ScopedStore`` / ``artifact_refs`` API, then in
14-04 to the REAL-dispatch contract: ``_handle_revision`` no longer echoes the
composed revision context back as the "revision" (the Phase-3 stub deleted in
14-03) — it dispatches the registry's real revision pipeline
(``get_pipeline_agents(<derived WR-06 alias>)``) through the public
``execute()`` chokepoint against SCRIPTED models (offline, no Bedrock).

What this suite owns (vs ``test_run_revision_fe_contract.py``, which owns the
ORGANIC-parent E2E + revision-of-revision): the SEEDED-parent matrix — every
pre-dispatch guard plus each FR-014 chain link driven from hand-seeded
``artifact_refs`` rows.

Guard tests (fire BEFORE dispatch — no scripted wiring needed, semantics kept
byte-meaning-identical from the pre-14 suite):
  - _handle_revision raises ValueError for empty / whitespace instruction
  - _handle_revision raises ValueError for a falsy owner principal (AUTHZ-03)
  - _handle_revision raises the FR-014 ValueError (byte-exact message) for a
    non-existent artifact — and on a realistic parent with no chain-link match
  - CROSS-OWNER DENIAL (T-5-SEED): a second owner revising the first owner's
    parent run raises PermissionError BEFORE any event — on both the simple
    and the realistic-parent variants
  - link 3 skips "[Error: ...]" placeholders; all-placeholders raises FR-014
  - clarifications round-trip via artifact_refs (store-level, dispatch-free)

Proceed-path tests (REAL dispatch — scripted wiring via ``_dispatch_wiring``):
  - the revision stores a NEW exact-kind ref on the revision run with
    derived_from lineage; content == execute()'s final_output (the scripted
    REVISED deck, unwrapped — never the context blob)
  - the three-section context contract ("three separate structured inputs,
    NOT concatenated") is the agents' INPUT, observable on the forwarded
    ``agent_input`` event's ``context_message``
  - the "=== PLANNING CONTEXT" prefix is absent/present in the dispatched
    context_message (the stub-only terminal payload key is GONE — see the
    proceed-path tests for the rationale comments)
  - run_events persistence comes from execute()'s chokepoint: ledger rows
    exist with contiguous, non-duplicated seq (single stamping source)
  - the FR-014 chain (deliverable link / summary fallback / placeholder
    filter) proves WHICH link resolved via the resolved parent content
    reaching the dispatched agent input

Targeting rule (RESEARCH Pitfall 1): every proceed-path test targets
``od_ppt_output`` or ``ppt_output`` ONLY — the two kinds whose derived WR-06
aliases (``od_ppt_revision`` / ``ppt_revision``) carry ``planner: skip``
manifests (14-01). Any other ``*_output`` target would derive a
``planner: run`` manifest and hang at the clarify gate. The pre-14 suite's
"spec" proceed-path targets are re-targeted accordingly; guard tests keep
their original targets (they never reach dispatch).

Offline / in-memory SQLite / no API key — ``SessionLocal`` is monkeypatched
onto a shared StaticPool engine so every ``ScopedStore`` (engine path, no
injected session) hits the test DB; models scripted via
``tests.agents._scripted_model``.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Register every table the engine's ScopedStore path touches on Base.metadata
# BEFORE create_all: workflow_runs, artifact_refs, workspaces, run_events,
# run_capabilities (execute() records capabilities + arms the run-events sink).
import app.models.artifact_ref  # noqa: F401
import app.models.run_capabilities  # noqa: F401
import app.models.run_event  # noqa: F401
import app.models.workflow  # noqa: F401
import app.models.workspace  # noqa: F401
from agents.authz import ScopedStore
from agents.execution_engine.engine import ExecutionEngine
from app.models.artifact_ref import ArtifactRef
from app.models.database import Base
from app.models.run_event import RunEvent
from app.models.workflow import WorkflowRun
from tests.agents._scripted_model import (
    _RUNS_ROOT,
    ScriptedFakeChatModel,
    _scripts_for,
)

OWNER = "owner-x"
OTHER_OWNER = "owner-y"
WS = "ws-x"

# The deterministic REVISED decks the 14-01 harness scripts. The last agent of
# each revision pipeline streams "<narration>\n<artifact>{deck}</artifact>";
# the declared ``ppt`` deliverable strategy unwraps it, so ``final_output``
# must be EXACTLY the raw deck HTML between the artifact tags. Expected bytes
# are DERIVED from the harness (single source — never duplicated as literals).
#
# od_ppt_revision is a 1-step pipeline (od-ppt-revision-agent IS the
# deliverable producer); ppt_revision is 2 steps and the deliverable is the
# ASSEMBLER's deck (ppt-revision-assembler, the LAST agent).
_OD_REV_TURN_TEXT = _scripts_for("od-ppt-revision-agent")[0].texts[0]
EXPECTED_OD_REVISED_DECK = _OD_REV_TURN_TEXT.split("<artifact>", 1)[1].split(
    "</artifact>", 1
)[0]
_PPT_ASM_TURN_TEXT = _scripts_for("ppt-revision-assembler")[0].texts[0]
EXPECTED_PPT_REVISED_DECK = _PPT_ASM_TURN_TEXT.split("<artifact>", 1)[1].split(
    "</artifact>", 1
)[0]


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
    producer_step: str = "specify",
    producer_agent: str = "specify-agent",
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
                producer_step=producer_step,
                producer_agent=producer_agent,
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
# Scripted dispatch wiring (14-04) — the _scripted_model.py idiom, shared by
# every proceed-path test below. Guards never need it (they raise pre-dispatch).
# ---------------------------------------------------------------------------


@contextmanager
def _dispatch_wiring():
    """Wire ``_handle_revision``'s execute() dispatch onto SCRIPTED models.

    Mirrors the ``tests/agents/_scripted_model._drive`` dispatch idiom:
      * ``settings.RUNS_ROOT`` → the harness temp root (RunSandbox reads it at
        __init__; the default /app/runs is not writable locally);
      * BOTH ``agents.factory.create_runner`` AND
        ``agents.execution_engine.engine.create_runner`` patched to inject
        ``ScriptedFakeChatModel(_scripts_for(agent_id))`` as ``ctx.model``
        (the engine imported the name at module load, so both globals matter);
      * both restored in ``finally`` so repeated dispatches in one pytest
        process never accumulate patches.

    ``planner: skip`` on the two revision manifests (14-01) means no
    planner/clarify patching is needed.
    """
    import agents.execution_engine.engine as engine_mod
    import agents.factory as factory_mod
    from app.core.config import settings as _settings

    _settings.RUNS_ROOT = _RUNS_ROOT

    _orig_create_runner = factory_mod.create_runner
    _orig_engine_create_runner = engine_mod.create_runner

    def _patched_create_runner(agent_id, ctx, **kw):
        ctx.model = ScriptedFakeChatModel(_scripts_for(agent_id))
        return _orig_create_runner(agent_id, ctx, **kw)

    factory_mod.create_runner = _patched_create_runner
    engine_mod.create_runner = _patched_create_runner
    try:
        yield
    finally:
        factory_mod.create_runner = _orig_create_runner
        engine_mod.create_runner = _orig_engine_create_runner


async def _dispatch_revision(
    engine: ExecutionEngine,
    *,
    parent_run_id: str,
    target_artifact_type: str,
    instruction: str,
    pipeline_run_id: str | None = None,
) -> tuple[str, list[dict]]:
    """Drive ``_handle_revision`` through the real execute() dispatch against
    scripted models and return ``(revision_run_id, captured_events)``.

    Each call mints a UNIQUE ``pipeline_run_id`` — the state-machine singleton
    raises StateMachineError on id reuse within one pytest process.
    """
    revision_run_id = pipeline_run_id or f"run-rev-int-{uuid.uuid4().hex[:12]}"
    sent: list[dict] = []

    async def websocket_send_fn(event: dict) -> None:
        sent.append(event)

    with _dispatch_wiring():
        await engine._handle_revision(
            parent_run_id=parent_run_id,
            target_artifact_type=target_artifact_type,
            instruction=instruction,
            pipeline_run_id=revision_run_id,
            websocket_send_fn=websocket_send_fn,
            owner_id=OWNER,
        )
    return revision_run_id, sent


def _context_message(sent: list[dict]) -> str:
    """The composed revision context the FIRST dispatched agent received —
    forwarded verbatim on the ``agent_input`` event (the three-section
    contract is the agents' INPUT after 14-03, not the run's output)."""
    agent_inputs = [e for e in sent if e["type"] == "agent_input"]
    assert agent_inputs, "expected a forwarded agent_input event"
    return agent_inputs[0]["data"]["context_message"]


def _original_section(context_message: str, target_artifact_type: str) -> str:
    """The body of the ``=== ORIGINAL ARTIFACT ===`` section — evidence of
    WHICH FR-014 chain link resolved the parent original."""
    marker = f"=== ORIGINAL ARTIFACT (type: {target_artifact_type}) ==="
    assert marker in context_message, f"missing {marker!r} in the dispatched context"
    return context_message.split(marker, 1)[1].split(
        "=== END ORIGINAL ARTIFACT ===", 1
    )[0]


# ---------------------------------------------------------------------------
# Validation guards (kept byte-meaning-identical — they fire BEFORE dispatch)
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
async def test_falsy_owner_raises(engine: ExecutionEngine, db_factory) -> None:
    """AUTHZ-03: a falsy owner principal fails LOUD at the seam (ValueError,
    mirroring ClarifyEngine.run's falsy-owner guard) — never encoded as a
    downstream write error, never reaching any read or dispatch."""
    events: list[dict] = []

    async def ws(e: dict) -> None:  # pragma: no cover - never reached
        events.append(e)

    with pytest.raises(ValueError, match="real owner_id"):
        await engine._handle_revision(
            parent_run_id="run-parent",
            target_artifact_type="spec",
            instruction="Fix the introduction section",
            pipeline_run_id="run-rev-falsy-none",
            websocket_send_fn=ws,
            owner_id=None,
        )
    with pytest.raises(ValueError, match="real owner_id"):
        await engine._handle_revision(
            parent_run_id="run-parent",
            target_artifact_type="spec",
            instruction="Fix the introduction section",
            pipeline_run_id="run-rev-falsy-empty",
            websocket_send_fn=ws,
            owner_id="",
        )
    assert events == []


@pytest.mark.asyncio
async def test_nonexistent_artifact_raises(engine: ExecutionEngine, db_factory) -> None:
    parent = "run-no-artifacts"
    _seed_run(db_factory, run_id=parent, owner_id=OWNER)  # owned, but no refs

    async def ws(e: dict) -> None:  # pragma: no cover - never reached
        pass

    with pytest.raises(ValueError, match="No artifact") as excinfo:
        await engine._handle_revision(
            parent_run_id=parent,
            target_artifact_type="spec",
            instruction="Fix the introduction section",
            pipeline_run_id="run-rev-3",
            websocket_send_fn=ws,
            owner_id=OWNER,
        )
    # FR-014 message pinned BYTE-EXACT to engine.py's f-string.
    assert str(excinfo.value) == (
        "No artifact of type 'spec' found for run 'run-no-artifacts'. "
        "Revision MUST NOT proceed without original context (FR-014)."
    )


# ---------------------------------------------------------------------------
# Successful revision — REAL dispatch (scripted models), chain link 1 (exact kind)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revision_stores_new_version_with_lineage(engine: ExecutionEngine, db_factory) -> None:
    """The revision run persists a NEW exact-kind ref whose content is
    execute()'s final_output (the scripted REVISED deck, unwrapped) with
    derived_from == the seeded parent original (FR-014 chain link 1).

    Re-targeted from "spec" to "od_ppt_output" (14-04): only the two flipped
    ``planner: skip`` manifests are run_revision-dispatchable. The pre-14 stub
    assertions (final_output containing the three ``===`` section markers,
    ref content == the context blob) are GONE — the context is the agents'
    INPUT now, covered below.
    """
    parent = "run-parent-ok"
    _seed_run(db_factory, run_id=parent, owner_id=OWNER)
    original_id = _seed_ref(
        db_factory,
        run_id=parent,
        owner_id=OWNER,
        kind="od_ppt_output",
        content="<!doctype html><html><body><section class='deck-slide'>Original Title</section></body></html>",
    )

    rev_run_id, sent = await _dispatch_revision(
        engine,
        parent_run_id=parent,
        target_artifact_type="od_ppt_output",
        instruction="Improve the title slide",
    )

    complete_events = [e for e in sent if e["type"] == "pipeline_complete"]
    assert len(complete_events) == 1
    final_output = complete_events[0]["data"]["final_output"]
    # The scripted REVISED deck, unwrapped by the declared ppt deliverable
    # strategy — raw HTML, never the composed context blob.
    assert final_output == EXPECTED_OD_REVISED_DECK
    assert "=== ORIGINAL ARTIFACT" not in final_output

    # The revision artifact landed in the revision run via ScopedStore.
    store = ScopedStore(owner_id=OWNER)
    refs = await store.list_refs(rev_run_id, kind="od_ppt_output")
    assert len(refs) == 1, "expected exactly one exact-kind revision ref"
    revision = refs[0]
    assert revision.content == final_output
    assert revision.derived_from == original_id
    assert revision.run_id == rev_run_id
    assert revision.visibility == "workspace"
    # Owner/workspace stamped from the original (the lineage write lands the
    # ref in the PARENT artifact's workspace so the scope filter holds).
    assert revision.owner_id == OWNER
    assert revision.workspace_id == WS


@pytest.mark.asyncio
async def test_revision_contains_three_separate_inputs(engine: ExecutionEngine, db_factory) -> None:
    """The three-section contract ("three separate structured inputs, NOT
    concatenated") is the dispatched agents' INPUT — observable on the
    forwarded ``agent_input`` event's context_message (after 14-03 it is no
    longer the run's output)."""
    parent = "run-parent-3inputs"
    _seed_run(db_factory, run_id=parent, owner_id=OWNER)
    original_content = (
        "<!doctype html><html><body><section class='deck-slide'>Intro</section></body></html>"
    )
    _seed_ref(
        db_factory, run_id=parent, owner_id=OWNER, kind="od_ppt_output", content=original_content
    )

    instruction = "Improve the Introduction slide only"
    _, sent = await _dispatch_revision(
        engine,
        parent_run_id=parent,
        target_artifact_type="od_ppt_output",
        instruction=instruction,
    )

    context_message = _context_message(sent)

    assert "=== ORIGINAL ARTIFACT (type: od_ppt_output) ===" in context_message
    assert "=== VERSION HISTORY ===" in context_message
    assert "=== REVISION INSTRUCTION ===" in context_message

    # Original content + instruction preserved verbatim INSIDE their sections.
    original_section = _original_section(context_message, "od_ppt_output")
    assert original_content in original_section
    instruction_section = context_message.split("=== REVISION INSTRUCTION ===", 1)[1].split(
        "=== END REVISION INSTRUCTION ===", 1
    )[0]
    assert instruction in instruction_section

    orig_pos = context_message.index("=== ORIGINAL ARTIFACT")
    hist_pos = context_message.index("=== VERSION HISTORY")
    instr_pos = context_message.index("=== REVISION INSTRUCTION")
    assert orig_pos < hist_pos < instr_pos


@pytest.mark.asyncio
async def test_planning_context_prefix_absent_when_no_planning_artifact(
    engine: ExecutionEngine, db_factory
) -> None:
    """No planning_context artifact on the parent → the "=== PLANNING CONTEXT"
    prefix is ABSENT from the dispatched context_message.

    (The stub-only terminal payload key that used to annotate
    pipeline_complete was deleted with the stub in 14-03 — the observable
    contract is the dispatched INPUT prefix now, hence the rename from the
    pre-14 test name.)
    """
    parent = "run-parent-no-planning"
    _seed_run(db_factory, run_id=parent, owner_id=OWNER)
    _seed_ref(
        db_factory,
        run_id=parent,
        owner_id=OWNER,
        kind="od_ppt_output",
        content="<!doctype html><html><body>deck</body></html>",
    )

    _, sent = await _dispatch_revision(
        engine,
        parent_run_id=parent,
        target_artifact_type="od_ppt_output",
        instruction="Fix slide 2",
    )

    context_message = _context_message(sent)
    assert "=== PLANNING CONTEXT" not in context_message
    # The run still completed normally (real dispatch, real terminal pair).
    assert [e for e in sent if e["type"] == "pipeline_complete"]


@pytest.mark.asyncio
async def test_planning_context_available_when_present(engine: ExecutionEngine, db_factory) -> None:
    """A planning_context artifact on the parent → the "=== PLANNING CONTEXT"
    guardrail block is PREPENDED to the dispatched context_message, verbatim
    content included."""
    parent = "run-parent-with-planning"
    _seed_run(db_factory, run_id=parent, owner_id=OWNER)
    _seed_ref(
        db_factory,
        run_id=parent,
        owner_id=OWNER,
        kind="od_ppt_output",
        content="<!doctype html><html><body>deck</body></html>",
    )
    _seed_ref(
        db_factory,
        run_id=parent,
        owner_id=OWNER,
        kind="planning_context",
        content=json.dumps({"inferred_intent": "Build a login feature", "execution_gate": "PROCEED"}),
    )

    _, sent = await _dispatch_revision(
        engine,
        parent_run_id=parent,
        target_artifact_type="od_ppt_output",
        instruction="Fix slide 2",
    )

    context_message = _context_message(sent)
    assert "=== PLANNING CONTEXT" in context_message
    assert "Build a login feature" in context_message
    # The planning guardrail is a PREFIX — it precedes the original artifact.
    assert context_message.index("=== PLANNING CONTEXT") < context_message.index(
        "=== ORIGINAL ARTIFACT"
    )


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

    # The denial fired BEFORE any event was emitted (assert_owns is first).
    assert events == []

    # No revision artifact must have been written for the attacker's run.
    attacker_store = ScopedStore(owner_id=OTHER_OWNER)
    refs = await attacker_store.list_refs("run-rev-cross-owner", kind="spec")
    assert refs == []


# ---------------------------------------------------------------------------
# Revision run_events persist + resolve on a real DB — execute()'s chokepoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revision_run_events_persist_and_resolve_on_real_db(
    engine: ExecutionEngine, db_factory
) -> None:
    """The revision run's ledger comes from execute()'s chokepoint (14-03):
    the single stamping source persists every dispatched event to
    ``run_events`` with contiguous, NON-duplicated seq — a reintroduced second
    counter (the deleted duplicate stamping path, RESEARCH Pitfall 2) fails
    this test.

    Workspace delta (RESEARCH Pitfall 2 note): execute() mints the revision
    run's OWN workspace — it does NOT inherit the parent artifact's
    workspace. The scope for the /events-endpoint-mirroring read is therefore
    recovered from the PERSISTED rows, never from the parent.
    """
    parent = "run-parent-events"
    _seed_run(db_factory, run_id=parent, owner_id=OWNER, workspace_id=WS)
    _seed_ref(
        db_factory,
        run_id=parent,
        owner_id=OWNER,
        kind="od_ppt_output",
        content="<!doctype html><html><body><section class='deck-slide'>S1</section></body></html>",
        workspace_id=WS,
    )

    rev_run_id = f"run-rev-events-{uuid.uuid4().hex[:8]}"
    # Mirror websocket.py: the revision run row is created with a real owner
    # but NO workspace — execute()'s organic envelope (workspace mint +
    # set_run_scope) stamps the run's OWN workspace during dispatch.
    s = db_factory()
    try:
        s.add(
            WorkflowRun(
                id=rev_run_id,
                user_id=OWNER,
                owner_id=OWNER,        # AUTHZ-03 — never None at creation
                workspace_id=None,     # transiently null — execute() stamps it
                title="Revision: x",
                type="od_ppt_revision",
                status="revising",
                input="x",
            )
        )
        s.commit()
    finally:
        s.close()

    _, sent = await _dispatch_revision(
        engine,
        parent_run_id=parent,
        target_artifact_type="od_ppt_output",
        instruction="Tighten slide 1",
        pipeline_run_id=rev_run_id,
    )
    assert [e for e in sent if e["type"] == "pipeline_complete"]

    # (1) Ledger rows persisted at the chokepoint — recover the MINTED
    # workspace from the persisted rows themselves (owner-scoped raw read).
    chk = db_factory()
    try:
        rows = (
            chk.query(RunEvent)
            .filter(RunEvent.run_id == rev_run_id, RunEvent.owner_id == OWNER)
            .order_by(RunEvent.seq.asc())
            .all()
        )
        assert rows, "no run_events rows persisted for the revision run"
        workspaces = {r.workspace_id for r in rows}
        assert len(workspaces) == 1, "every ledger row must carry ONE workspace"
        minted_ws = workspaces.pop()
        assert minted_ws, "run_events.workspace_id must never be None (AUTHZ-01)"

        # seq is contiguous from 1 with NO duplicates — the single-stamping
        # regression trap: a second counter would duplicate or skip.
        seqs = [r.seq for r in rows]
        assert seqs == list(range(1, len(seqs) + 1)), (
            f"seq must be contiguous 1..N with no duplicates; got {seqs}"
        )
        # The terminal pipeline_complete row is present in the ledger.
        types = [r.type for r in rows]
        assert "pipeline_start" in types
        assert "pipeline_complete" in types
        assert all(r.owner_id == OWNER for r in rows)
    finally:
        chk.close()

    # (2) The revision run row carries the MINTED workspace (set_run_scope).
    chk2 = db_factory()
    try:
        row = chk2.query(WorkflowRun).filter(WorkflowRun.id == rev_run_id).first()
        assert row is not None
        assert row.owner_id == OWNER
        assert row.workspace_id == minted_ws, (
            "revision run workspace must be execute()'s minted workspace"
        )
    finally:
        chk2.close()

    # (3) Mirror the /events endpoint: ScopedStore(owner, workflow_run.workspace_id)
    # resolves the run AND replays the persisted events in seq order.
    endpoint_store = ScopedStore(owner_id=OWNER, workspace_id=minted_ws)
    resolved = await endpoint_store.get_run(rev_run_id)
    assert resolved is not None, "revision run 404s under owner+workspace scope"
    replayed = await endpoint_store.read_events(rev_run_id, after_seq=0)
    assert [r.type for r in replayed] == types
    assert [r.seq for r in replayed] == seqs


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


# ---------------------------------------------------------------------------
# F2 / 13-UAT.md Gap 2 — realistic persistence (de-masked seeds)
#
# The exact-kind scenarios above seed parents with EXACTLY the kind they
# target, covering FR-014 chain link 1. No real run ever persists the FE's
# target kinds ("ppt_output"/"od_ppt_output") — the run path persists
# per-agent kinds (_AGENT_KIND_MAP values, falling back to "summary") plus
# summary/planning_context/clarifications and, since 13-05, a completion
# kind="deliverable" ref. These scenarios seed parents the way the RUN PATH
# actually persists and send the FE-exact target — proving the FR-014 fallback
# chain (exact → deliverable → summary) without weakening the guard. After
# 14-03 the proof of WHICH link resolved is the resolved parent content
# reaching the DISPATCHED AGENT INPUT (the stub's echoed output is gone).
# ---------------------------------------------------------------------------


def _seed_realistic_parent(
    session_factory,
    *,
    run_id: str,
    owner_id: str,
    with_deliverable: bool,
) -> dict[str, str]:
    """Seed a parent run with what the run path ACTUALLY persists (F2):
    per-agent kind="summary" refs (one per agent id) + a kind="planning_context"
    ref + (optionally) the 13-05 completion kind="deliverable" ref. Returns the
    seeded contents keyed by role."""
    _seed_run(session_factory, run_id=run_id, owner_id=owner_id)
    contents = {
        "summary_v1": "Composing the 4-slide deck per the strategist plan.",
        "summary_v2": "Validation passed. Final deck: <section class='deck-slide'>Title</section>",
        "deliverable": "<!doctype html><html><body><section class='deck-slide'>Title</section></body></html>",
        "planning": json.dumps({"inferred_intent": "Pitch deck", "execution_gate": "PROCEED"}),
    }
    _seed_ref(
        session_factory,
        run_id=run_id,
        owner_id=owner_id,
        kind="summary",
        content=contents["summary_v1"],
        version=1,
        producer_step="od-ppt-composer",
        producer_agent="od-ppt-composer",
    )
    _seed_ref(
        session_factory,
        run_id=run_id,
        owner_id=owner_id,
        kind="summary",
        content=contents["summary_v2"],
        version=2,
        producer_step="od-ppt-validator",
        producer_agent="od-ppt-validator",
    )
    _seed_ref(
        session_factory,
        run_id=run_id,
        owner_id=owner_id,
        kind="planning_context",
        content=contents["planning"],
        producer_step="planner",
        producer_agent="deep-planner",
    )
    if with_deliverable:
        _seed_ref(
            session_factory,
            run_id=run_id,
            owner_id=owner_id,
            kind="deliverable",
            content=contents["deliverable"],
            producer_step="deliverable",
            producer_agent="od-ppt-validator",
        )
    return contents


@pytest.mark.asyncio
async def test_fe_target_resolves_deliverable_ref_on_realistic_parent(
    engine: ExecutionEngine, db_factory
) -> None:
    """(a) F2 / Gap 2: the FE-exact target "ppt_output" against a parent seeded
    the way a NEW (post-13-05) run persists proceeds via chain link 2 — the
    kind="deliverable" completion ref — and the DELIVERABLE content reaches
    the dispatched agent input as the ORIGINAL ARTIFACT (14-03 real dispatch:
    the 2-step ppt_revision pipeline runs; the ASSEMBLER's scripted deck is
    the final deliverable)."""
    parent = "run-parent-realistic-new"
    contents = _seed_realistic_parent(
        db_factory, run_id=parent, owner_id=OWNER, with_deliverable=True
    )

    _, sent = await _dispatch_revision(
        engine,
        parent_run_id=parent,
        target_artifact_type="ppt_output",  # FE-exact (DashboardLayout.tsx)
        instruction="Make the title slide bolder",
    )

    context_message = _context_message(sent)
    # The DELIVERABLE ref's content is the resolved original (not a summary).
    original_section = _original_section(context_message, "ppt_output")
    assert contents["deliverable"] in original_section
    assert contents["summary_v2"] not in original_section
    # planning_context still resolves alongside the chain — prefix PRESENT.
    assert "=== PLANNING CONTEXT" in context_message

    # The 2-step ppt_revision pipeline completed for real: final_output is the
    # ASSEMBLER's scripted deck (the LAST agent), unwrapped.
    completes = [e for e in sent if e["type"] == "pipeline_complete"]
    assert len(completes) == 1
    assert completes[0]["data"]["final_output"] == EXPECTED_PPT_REVISED_DECK


@pytest.mark.asyncio
async def test_fe_target_falls_back_to_summary_on_legacy_parent(
    engine: ExecutionEngine, db_factory
) -> None:
    """(b) F2 / Gap 2: a PRE-13-05 legacy parent (no deliverable ref) resolves
    via chain link 3 — the latest kind="summary" ref (the final agent's output
    under the _AGENT_KIND_MAP fallback) — and ITS content reaches the
    dispatched agent input as the ORIGINAL ARTIFACT."""
    parent = "run-parent-realistic-legacy"
    contents = _seed_realistic_parent(
        db_factory, run_id=parent, owner_id=OWNER, with_deliverable=False
    )

    _, sent = await _dispatch_revision(
        engine,
        parent_run_id=parent,
        target_artifact_type="ppt_output",
        instruction="Tighten the closing slide",
    )

    context_message = _context_message(sent)
    # Latest-by-version summary (the FINAL agent's output) is the original.
    original_section = _original_section(context_message, "ppt_output")
    assert contents["summary_v2"] in original_section
    # version_history is the MATCHED link's refs list (both summary versions).
    assert "2 version(s) exist" in context_message


@pytest.mark.asyncio
async def test_summary_fallback_skips_error_placeholder_refs(
    engine: ExecutionEngine, db_factory
) -> None:
    """IN-06 (13 review fix): on a legacy degraded parent whose FINAL agent
    errored, the latest summary ref is the "[Error: ...]" placeholder a failed
    agent typed-writes under its mapped kind. Link 3 must skip placeholders and
    resolve the latest REAL summary into the dispatched agent input — never
    the error blob."""
    parent = "run-parent-legacy-degraded"
    _seed_run(db_factory, run_id=parent, owner_id=OWNER)
    real_content = "Real composer output: <section class='deck-slide'>Title</section>"
    _seed_ref(
        db_factory,
        run_id=parent,
        owner_id=OWNER,
        kind="summary",
        content=real_content,
        version=1,
        producer_step="od-ppt-composer",
        producer_agent="od-ppt-composer",
    )
    _seed_ref(
        db_factory,
        run_id=parent,
        owner_id=OWNER,
        kind="summary",
        content="[Error: model timed out after 3 attempts]",
        version=2,
        producer_step="od-ppt-validator",
        producer_agent="od-ppt-validator",
    )

    _, sent = await _dispatch_revision(
        engine,
        parent_run_id=parent,
        target_artifact_type="ppt_output",
        instruction="Tighten the closing slide",
    )

    context_message = _context_message(sent)
    # The real (non-placeholder) summary resolves as the revision original.
    original_section = _original_section(context_message, "ppt_output")
    assert real_content in original_section
    assert "[Error:" not in context_message


@pytest.mark.asyncio
async def test_summary_fallback_all_error_placeholders_raises_fr014(
    engine: ExecutionEngine, db_factory
) -> None:
    """IN-06: when EVERY summary ref is an error placeholder, link 3 stays
    empty and the FR-014 guard fires — garbage never resolves as an original."""
    parent = "run-parent-all-errors"
    _seed_run(db_factory, run_id=parent, owner_id=OWNER)
    _seed_ref(
        db_factory,
        run_id=parent,
        owner_id=OWNER,
        kind="summary",
        content="[Error: ThrottlingException]",
        version=1,
    )

    async def ws(e: dict) -> None:  # pragma: no cover - never reached
        pass

    with pytest.raises(ValueError, match="No artifact"):
        await engine._handle_revision(
            parent_run_id=parent,
            target_artifact_type="ppt_output",
            instruction="Revise anything",
            pipeline_run_id="run-rev-all-errors",
            websocket_send_fn=ws,
            owner_id=OWNER,
        )


@pytest.mark.asyncio
async def test_fe_target_still_raises_fr014_when_no_chain_link_matches(
    engine: ExecutionEngine, db_factory
) -> None:
    """(c) F2 / Gap 2: the FR-014 guard is NOT weakened — a parent with no
    exact/deliverable/summary refs (planning_context only) still raises."""
    parent = "run-parent-no-chain-refs"
    _seed_run(db_factory, run_id=parent, owner_id=OWNER)
    _seed_ref(
        db_factory,
        run_id=parent,
        owner_id=OWNER,
        kind="planning_context",
        content=json.dumps({"execution_gate": "PROCEED"}),
    )

    async def ws(e: dict) -> None:  # pragma: no cover - never reached
        pass

    with pytest.raises(ValueError, match="No artifact"):
        await engine._handle_revision(
            parent_run_id=parent,
            target_artifact_type="ppt_output",
            instruction="Revise anything",
            pipeline_run_id="run-rev-no-chain-refs",
            websocket_send_fn=ws,
            owner_id=OWNER,
        )


@pytest.mark.asyncio
async def test_fe_target_cross_owner_still_denied_on_realistic_parent(
    engine: ExecutionEngine, db_factory
) -> None:
    """(d) F2 / Gap 2 + L16: the fallback chain does NOT widen ownership —
    a cross-owner replay of (a) raises PermissionError BEFORE any chain read
    (assert_owns stays first, T-5-SEED)."""
    parent = "run-parent-realistic-owned-x"
    _seed_realistic_parent(
        db_factory, run_id=parent, owner_id=OWNER, with_deliverable=True
    )

    events: list[dict] = []

    async def ws(e: dict) -> None:
        events.append(e)

    with pytest.raises(PermissionError):
        await engine._handle_revision(
            parent_run_id=parent,
            target_artifact_type="ppt_output",
            instruction="Steal owner X's deck",
            pipeline_run_id="run-rev-realistic-cross-owner",
            websocket_send_fn=ws,
            owner_id=OTHER_OWNER,  # NOT the parent owner
        )

    # The denial fired BEFORE any event was emitted (assert_owns is first).
    assert events == []

    # Nothing was written for the attacker's revision run.
    attacker_store = ScopedStore(owner_id=OTHER_OWNER)
    refs = await attacker_store.list_refs("run-rev-realistic-cross-owner", kind="ppt_output")
    assert refs == []


# ---------------------------------------------------------------------------
# CR-02 (14 review) — planner-flow targets rejected BEFORE dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_planner_run_target_rejected_before_dispatch(
    engine: ExecutionEngine, db_factory
) -> None:
    """CR-02 (14 review): a target whose derived alias resolves a REGISTERED
    revision pipeline carrying ``planner: run`` (e.g. ``app_builder_output`` →
    ``app_builder_revision``) is rejected with ValueError BEFORE dispatch —
    never parked at the clarify gate's no-timeout ``event.wait()``.

    ISS-050 (KAN-156): retargeted from ``prototype_output`` to
    ``app_builder_output`` — prototype_revision was flipped to
    ``planner: skip`` (now dispatchable) so it can no longer be used as the
    CR-02 rejection example. ``app_builder_revision`` still declares
    ``planner: run`` and is correctly rejected.

    The FR-014 artifact guard does NOT block this exploit: the deliverable
    chain link (link 2) resolves for ANY target kind, so an owned completed
    parent satisfies it — only the planner predicate stops the dispatch. The
    predicate is manifest DATA (``compiled.planner`` — SC-001): flipping a
    manifest to ``planner: skip`` makes its target dispatchable with no
    engine edit, and this test starts failing for that target by design."""
    parent = "run-parent-planner-run"
    # Realistic owned parent WITH a deliverable ref — FR-014 link 2 matches,
    # proving the rejection comes from the planner guard, not the lookup.
    _seed_realistic_parent(
        db_factory, run_id=parent, owner_id=OWNER, with_deliverable=True
    )

    events: list[dict] = []

    async def ws(e: dict) -> None:
        events.append(e)

    with pytest.raises(ValueError, match="not revision-dispatchable"):
        await engine._handle_revision(
            parent_run_id=parent,
            target_artifact_type="app_builder_output",
            instruction="Add a login page",
            pipeline_run_id="run-rev-planner-run",
            websocket_send_fn=ws,
            owner_id=OWNER,
        )

    # The guard fired pre-dispatch: no event was emitted, nothing was written
    # for the rejected revision run (no stuck task, no "revising" leak).
    assert events == []
    store = ScopedStore(owner_id=OWNER)
    refs = await store.list_refs("run-rev-planner-run", kind="app_builder_output")
    assert refs == []


@pytest.mark.asyncio
async def test_prototype_revision_now_dispatches_successfully(
    engine: ExecutionEngine, db_factory
) -> None:
    """ISS-050 (KAN-156) fix proof — fail-before / pass-after pin.

    ``prototype_output`` → ``prototype_revision`` was previously rejected by
    CR-02 (planner: run) when dispatched via the generic chat-lane revision
    channel. After the ISS-050 manifest fix (planner: run → planner: skip) it
    must pass the guard and dispatch successfully.

    **Fail-before-fix:** running this test against an unmodified
    ``prototype_revision/workflow.yaml`` (planner: run) raises
    ``ValueError: ... not revision-dispatchable ...``.

    **Pass-after-fix:** the manifest carries ``planner: skip``, the guard
    passes, execute() is invoked with scripted models, a ``pipeline_complete``
    event is observed, and a new ``prototype_output`` ref with the correct
    lineage lands in the store.
    """
    parent = "run-parent-proto-rev-iss050"
    _seed_run(db_factory, run_id=parent, owner_id=OWNER)
    original_id = _seed_ref(
        db_factory,
        run_id=parent,
        owner_id=OWNER,
        kind="prototype_output",
        content="<!doctype html><html><body><h1>Original</h1></body></html>",
    )

    rev_run_id, sent = await _dispatch_revision(
        engine,
        parent_run_id=parent,
        target_artifact_type="prototype_output",
        instruction="Make the hero section bolder",
    )

    complete_events = [e for e in sent if e["type"] == "pipeline_complete"]
    assert len(complete_events) == 1, (
        "ISS-050: prototype_revision did not dispatch — CR-02 guard still "
        "firing; check prototype_revision/workflow.yaml planner: skip"
    )

    store = ScopedStore(owner_id=OWNER)
    refs = await store.list_refs(rev_run_id, kind="prototype_output")
    assert len(refs) == 1, "expected exactly one prototype_output revision ref"
    revision = refs[0]
    assert revision.derived_from == original_id
    assert revision.run_id == rev_run_id
    assert revision.owner_id == OWNER
