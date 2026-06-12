"""14-03 — FE-exact ``run_revision`` REAL-DISPATCH contract regression (F2 / SC1+SC2).

The frontend (DashboardLayout.tsx:388-403) sends ``run_revision`` frames with
``target_artifact_type: "ppt_output" | "od_ppt_output"``. Before Phase 14 the
engine's ``_handle_revision`` echoed the composed revision CONTEXT back as the
"revision" (the Phase-3 stub — no model ever ran, ``total_duration: 0.0``).
After 14-03 the handler dispatches the registry's real revision pipeline
through the public ``execute()`` chokepoint: the deepagents runtime runs the
``od-ppt-revision-agent``, the declared ``ppt`` deliverable strategy unwraps
the agent's ``<artifact>``-wrapped REVISED deck, and the post-dispatch lineage
write persists it under the exact target kind with ``derived_from``.

This suite pins that real-dispatch contract end-to-end:
  * a scripted ``od_ppt`` parent run completes ORGANICALLY through execute()
    (nothing seeded by hand — the FR-014 chain resolves only what the run
    path persisted);
  * ``_handle_revision`` with the FE-exact frame drives REAL agents (observed
    ``agent_start``/``agent_complete``), one real ``pipeline_start``/
    ``pipeline_complete`` pair, single-source contiguous ``seq`` stamping;
  * ``final_output`` is the REVISED deck (raw HTML, unwrapped), never the
    context blob;
  * the exact-kind ref carries ``derived_from`` == the parent's resolved
    deliverable ref id (FR-014 chain link 1 for revision-of-revision);
  * a revision OF a revision resolves the FIRST revision's deck as its
    original via chain link 1 (ROADMAP SC2).

Offline: scripted models via ``tests.agents._scripted_model`` (no Bedrock /
no network); in-memory SQLite (StaticPool) monkeypatched onto
``app.models.database.SessionLocal`` so the engine's best-effort ScopedStore
writes PERSIST (instead of degrading) and the cross-run revision reads resolve.
"""

from __future__ import annotations

import uuid

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
from app.models.database import Base
from tests.agents._scripted_model import (
    _RUNS_ROOT,
    ScriptedFakeChatModel,
    _drive,
    _scripts_for,
)

# _drive() runs execute() with user_id="harness-user" → that string is the
# owner principal every ScopedStore write is stamped with. The direct
# _handle_revision calls below thread the SAME owner so the cross-run
# owner+visibility-scoped reads resolve.
OWNER = "harness-user"

# The deterministic revised deck the 14-01 harness scripts for the
# od-ppt-revision-agent: its single turn streams
# "Revised per instruction.\n<artifact>{deck}</artifact>" — the declared
# ``ppt`` deliverable strategy unwraps it, so final_output must be EXACTLY
# the raw deck HTML between the artifact tags (no wrapper, no narration).
_REV_TURN_TEXT = _scripts_for("od-ppt-revision-agent")[0].texts[0]
EXPECTED_REVISED_DECK = _REV_TURN_TEXT.split("<artifact>", 1)[1].split(
    "</artifact>", 1
)[0]


@pytest.fixture
def db_factory(monkeypatch):
    """In-memory SQLite (StaticPool, shared connection) wired into
    ``app.models.database.SessionLocal`` so every engine-path ``ScopedStore``
    (execute()'s writes AND _handle_revision's cross-run reads) hits THIS DB."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr("app.models.database.SessionLocal", TestingSession, raising=False)
    try:
        yield TestingSession
    finally:
        Base.metadata.drop_all(bind=engine)


async def _dispatch_revision(
    engine: ExecutionEngine,
    *,
    parent_run_id: str,
    instruction: str,
) -> tuple[str, list[dict]]:
    """Drive ``_handle_revision`` with the FE-exact frame against SCRIPTED models.

    Mirrors the ``_scripted_model._drive`` dispatch wiring for the revision
    call (the engine imported ``create_runner`` by name, so BOTH module
    globals are patched and restored): ``planner: skip`` (14-01) means no
    planner/clarify patching is needed. Each call mints a UNIQUE
    ``pipeline_run_id`` — the state-machine singleton raises StateMachineError
    on id reuse. Returns ``(revision_run_id, captured_events)``.
    """
    import agents.factory as factory_mod
    import agents.execution_engine.engine as engine_mod
    from app.core.config import settings as _settings

    # RunSandbox reads settings.RUNS_ROOT at __init__ — force the harness temp
    # dir at runtime (the default /app/runs is not writable locally).
    _settings.RUNS_ROOT = _RUNS_ROOT

    _orig_create_runner = factory_mod.create_runner
    _orig_engine_create_runner = engine_mod.create_runner

    def _patched_create_runner(agent_id, ctx, **kw):
        ctx.model = ScriptedFakeChatModel(_scripts_for(agent_id))
        return _orig_create_runner(agent_id, ctx, **kw)

    factory_mod.create_runner = _patched_create_runner
    engine_mod.create_runner = _patched_create_runner

    revision_run_id = f"run-rev-fe-{uuid.uuid4().hex[:12]}"
    sent: list[dict] = []

    async def websocket_send_fn(event: dict) -> None:
        sent.append(event)

    try:
        await engine._handle_revision(
            parent_run_id=parent_run_id,
            target_artifact_type="od_ppt_output",  # FE-exact — never a persisted kind
            instruction=instruction,
            pipeline_run_id=revision_run_id,
            websocket_send_fn=websocket_send_fn,
            owner_id=OWNER,
        )
    finally:
        # Restore both names so repeated dispatches in one pytest process never
        # accumulate patches (the _scripted_model finally discipline).
        factory_mod.create_runner = _orig_create_runner
        engine_mod.create_runner = _orig_engine_create_runner
    return revision_run_id, sent


@pytest.mark.asyncio
async def test_fe_exact_run_revision_dispatches_real_pipeline(db_factory) -> None:
    """SC1+SC2: the FE's exact run_revision payload drives the REAL
    od_ppt_revision pipeline through execute() — model runs observed, revised
    deck as final_output, single-source seq, exact-kind derived_from lineage."""
    # ── 1) Complete a scripted od_ppt run end-to-end via the PUBLIC execute().
    # The 13-05 completion block persists the run deliverable itself — this test
    # deliberately seeds NO artifact rows, so the only way the revision below can
    # resolve is through what the run path organically persisted.
    run_events = await _drive("od_ppt")
    run_completes = [e for e in run_events if e["type"] == "pipeline_complete"]
    assert run_completes, "scripted od_ppt run did not complete"
    parent_run_id = run_completes[-1]["data"]["pipeline_run_id"]
    parent_deliverable = run_completes[-1]["data"]["final_output"]
    assert parent_deliverable, "scripted run produced an empty deliverable"

    # ── 2) Dispatch the FE-exact revision frame against scripted models.
    engine = ExecutionEngine()
    instruction = "Make the closing slide a clear call to action."
    revision_run_id, sent = await _dispatch_revision(
        engine, parent_run_id=parent_run_id, instruction=instruction
    )

    # ── (a) The revision PROCEEDED: no failure events of any vocabulary.
    assert not [e for e in sent if e["type"] == "state_restoration_failed"]
    assert not [e for e in sent if e["type"] == "pipeline_failed"]

    # ── (b) REAL model runs observed (SC1): the registry revision agent
    # started AND completed — the stub never emitted either event type.
    starts = [e for e in sent if e["type"] == "agent_start"]
    completes_agent = [e for e in sent if e["type"] == "agent_complete"]
    assert any(e["data"].get("agent_id") == "od-ppt-revision-agent" for e in starts), (
        "expected agent_start for od-ppt-revision-agent (real dispatch)"
    )
    assert any(
        e["data"].get("agent_id") == "od-ppt-revision-agent" for e in completes_agent
    ), "expected agent_complete for od-ppt-revision-agent (real dispatch)"

    # ── (c) Exactly ONE real pipeline_start / pipeline_complete pair, both
    # carrying the FE-routed WR-06 alias (data-derived, no kernel literal).
    pipeline_starts = [e for e in sent if e["type"] == "pipeline_start"]
    pipeline_completes = [e for e in sent if e["type"] == "pipeline_complete"]
    assert len(pipeline_starts) == 1, "expected exactly one pipeline_start"
    assert len(pipeline_completes) == 1, "expected exactly one pipeline_complete"
    assert pipeline_starts[0]["data"]["pipeline_type"] == "od_ppt_revision"
    terminal = pipeline_completes[0]["data"]
    assert terminal["pipeline_type"] == "od_ppt_revision"
    assert terminal["pipeline_run_id"] == revision_run_id

    # ── (d) final_output is the agents' REVISED deck, unwrapped by the
    # declared ppt deliverable strategy — raw HTML, never the context blob.
    # (Per RESEARCH Pitfall 5: do NOT match the instruction text in
    # final_output — a real revision may legitimately echo it. The instruction
    # is asserted nowhere against final_output in this suite.)
    final_output = terminal["final_output"]
    assert final_output == EXPECTED_REVISED_DECK
    assert final_output.startswith("<!doctype html>")
    assert "Revised Title" in final_output
    assert "<artifact>" not in final_output
    assert final_output != parent_deliverable
    assert "=== ORIGINAL ARTIFACT" not in final_output  # never the context blob

    # ── (e) Stamping is single-sourced (INV-12/SAFE-03): every forwarded
    # event's data carries a seq, and the seq sequence over ALL captured events
    # is contiguous 1..N with no duplicates — the deleted _stamped_send wrapper
    # cannot double-stamp.
    seqs = [e["data"]["seq"] for e in sent]
    assert seqs == list(range(1, len(seqs) + 1)), (
        f"seq must be contiguous 1..N with no duplicates; got {seqs}"
    )

    # ── (f) Exact-kind lineage (SC2): exactly one od_ppt_output ref on the
    # revision run, content == final_output, derived_from == the PARENT's
    # resolved deliverable ref id (the FR-014 chain-link-2 ref the run path
    # organically persisted — read-side lookup only, nothing seeded).
    store = ScopedStore(owner_id=OWNER)
    parent_deliverable_refs = await store.list_refs(parent_run_id, kind="deliverable")
    assert parent_deliverable_refs, "parent run persisted no deliverable ref"
    parent_original_id = parent_deliverable_refs[-1].id

    revision_refs = await store.list_refs(revision_run_id, kind="od_ppt_output")
    assert len(revision_refs) == 1, "expected exactly one exact-kind revision ref"
    rev_ref = revision_refs[0]
    assert rev_ref.content == final_output
    assert rev_ref.derived_from == parent_original_id
    assert rev_ref.owner_id == OWNER
    assert rev_ref.visibility == "workspace"
    assert rev_ref.producer_agent == "od-ppt-revision-agent"


@pytest.mark.asyncio
async def test_revision_of_revision_resolves_via_exact_kind_chain_link_1(
    db_factory,
) -> None:
    """ROADMAP SC2: a revision OF a revision resolves the FIRST revision's
    REVISED deck as its original via FR-014 chain link 1 (exact target kind) —
    proving the 14-03 lineage write feeds the chain. (``assert_owns`` degrades
    gracefully for an absent same-owner run row — the engine-driven first
    revision has no WorkflowRun row, exactly like the _drive parent run;
    same-owner discipline is preserved throughout.)"""
    # ── 1) Parent run + FIRST revision (same shape as the main test).
    run_events = await _drive("od_ppt")
    run_completes = [e for e in run_events if e["type"] == "pipeline_complete"]
    assert run_completes, "scripted od_ppt run did not complete"
    parent_run_id = run_completes[-1]["data"]["pipeline_run_id"]

    engine = ExecutionEngine()
    first_rev_run_id, first_sent = await _dispatch_revision(
        engine, parent_run_id=parent_run_id, instruction="Punch up the closing slide."
    )
    first_completes = [e for e in first_sent if e["type"] == "pipeline_complete"]
    assert len(first_completes) == 1
    first_revised_deck = first_completes[0]["data"]["final_output"]
    assert "Revised Title" in first_revised_deck

    # ── 2) SECOND revision against the FIRST revision's run id as parent.
    # Chain link 1 (exact kind od_ppt_output) must match the 14-03 lineage ref
    # — no FR-014 ValueError, and the run proceeds to its own terminal pair.
    second_rev_run_id, second_sent = await _dispatch_revision(
        engine,
        parent_run_id=first_rev_run_id,
        instruction="Now tighten the title slide copy.",
    )
    assert not [e for e in second_sent if e["type"] == "state_restoration_failed"]
    second_completes = [e for e in second_sent if e["type"] == "pipeline_complete"]
    assert len(second_completes) == 1, "revision-of-revision did not complete"
    assert second_completes[0]["data"]["pipeline_type"] == "od_ppt_revision"

    # ── 3) The composed context the SECOND revision's agent received embeds
    # the FIRST revision's deck content as the ORIGINAL ARTIFACT — evidence
    # chain link 1 resolved the exact-kind lineage ref (not the parent's
    # generic deliverable, not the summary fallback).
    agent_inputs = [e for e in second_sent if e["type"] == "agent_input"]
    assert agent_inputs, "expected a forwarded agent_input event"
    context_message = agent_inputs[0]["data"]["context_message"]
    assert "=== ORIGINAL ARTIFACT (type: od_ppt_output) ===" in context_message
    original_section = context_message.split(
        "=== ORIGINAL ARTIFACT (type: od_ppt_output) ===", 1
    )[1].split("=== END ORIGINAL ARTIFACT ===", 1)[0]
    assert "Revised Title" in original_section, (
        "chain link 1 must resolve the FIRST revision's REVISED deck as the original"
    )

    # ── 4) And the second revision's own lineage ref chains off the FIRST
    # revision's exact-kind ref (derived_from == that ref's id).
    store = ScopedStore(owner_id=OWNER)
    first_rev_refs = await store.list_refs(first_rev_run_id, kind="od_ppt_output")
    assert len(first_rev_refs) == 1
    second_rev_refs = await store.list_refs(second_rev_run_id, kind="od_ppt_output")
    assert len(second_rev_refs) == 1
    assert second_rev_refs[0].derived_from == first_rev_refs[0].id
