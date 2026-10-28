"""E1/E2 — opt-in ``deliverable.revision_context: workspace`` (spec 022 rev 6).

Compiler field, the workspace-mode revision message, and the opt-in human gates.
Every manifest that does not declare the field must behave exactly as before.
"""

from __future__ import annotations

import hashlib
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models.artifact_ref  # noqa: F401
import app.models.run_capabilities  # noqa: F401
import app.models.run_event  # noqa: F401
import app.models.workspace  # noqa: F401
import agents.execution_engine.engine as engine_mod
from agents.capabilities.registry import CapabilityRegistry
from agents.execution_engine.context import ExecutionContext
from agents.execution_engine.engine import ExecutionEngine
from agents.workflows.compiler import CompilerError, WorkflowCompiler
from agents.workflows.manifest import WorkflowManifest
from app.models.artifact_ref import ArtifactRef
from app.models.database import Base
from app.models.workflow import WorkflowRun

pytestmark = pytest.mark.allow_io("in-memory SQLite parent run for _handle_revision")

OWNER = "ws-mode-owner"
WS = "ws-x"
INSTRUCTION = "make the header blue"
WORKSPACE_MESSAGE = (
    f"=== REVISION REQUEST ===\n{INSTRUCTION}\n=== END REQUEST ===\n\n"
    "The original run's files are in this folder (the run's workspace); "
    "find what you need with grep/glob/read_file."
)


# ── T1: compiler ──────────────────────────────────────────────────────────────


def _compile(deliverable: dict):
    manifest = WorkflowManifest(
        id="t-revctx",
        steps=[],
        deliverable=deliverable,
        planner="skip",
        clarify={"mode": "auto", "defaults": []},
    )
    return WorkflowCompiler().compile(manifest, CapabilityRegistry())


def test_compiler_reads_workspace_default_and_rejects_unknown() -> None:
    base = {"strategy": "single_file", "name": "x.html"}
    assert (
        _compile({**base, "revision_context": "workspace"}).deliverable.revision_context
        == "workspace"
    )
    assert _compile(base).deliverable.revision_context == "artifact"
    with pytest.raises(CompilerError, match=r"'bogus'.*t-revctx"):
        _compile({**base, "revision_context": "bogus"})


# ── harness: real SQLite parent + captured execute() kwargs ───────────────────


@pytest.fixture
def db_factory(monkeypatch):
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=eng)
    factory = sessionmaker(bind=eng, autocommit=False, autoflush=False)
    monkeypatch.setattr("app.models.database.SessionLocal", factory, raising=False)
    try:
        yield factory
    finally:
        Base.metadata.drop_all(bind=eng)


def _seed_parent(factory, *, kind: str, content: str, status: str = "completed") -> str:
    run_id = f"parent-{uuid.uuid4().hex[:8]}"
    s = factory()
    try:
        s.add(
            WorkflowRun(
                id=run_id,
                user_id=OWNER,
                owner_id=OWNER,
                workspace_id=WS,
                title="t",
                type="prototype",
                status=status,
                input="t",
                error="boom" if status == "degraded" else None,
            )
        )
        s.add(
            ArtifactRef(
                id=str(uuid.uuid4()),
                run_id=run_id,
                owner_id=OWNER,
                workspace_id=WS,
                kind=kind,
                producer_step="s",
                producer_agent="a",
                content=content,
                content_hash=hashlib.sha256(content.encode()).hexdigest(),
                location=f"artifact_refs/{kind}",
                version=1,
                visibility="workspace",
            )
        )
        s.commit()
    finally:
        s.close()
    return run_id


async def _revise(monkeypatch, parent_run_id: str, target: str) -> dict:
    """Run _handle_revision with execute() replaced by a kwargs capture."""
    captured: dict = {}

    async def _fake_execute(self, **kwargs):
        captured.update(kwargs)
        return
        yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(ExecutionEngine, "execute", _fake_execute)

    async def _send(_event: dict) -> None:  # pragma: no cover
        pass

    await ExecutionEngine()._handle_revision(
        parent_run_id=parent_run_id,
        target_artifact_type=target,
        instruction=INSTRUCTION,
        pipeline_run_id=f"rev-{uuid.uuid4().hex[:8]}",
        websocket_send_fn=_send,
        owner_id=OWNER,
    )
    return captured


def _stub_workspace_pipeline(monkeypatch):
    """compile_for_run -> an opted-in plan, independent of any real manifest."""
    steps = [
        SimpleNamespace(agent_id="custom-agent:blr-intake", gates=[]),
        SimpleNamespace(agent_id="custom-agent:blr-locate", gates=["human"]),
        SimpleNamespace(agent_id="custom-agent:blr-write", gates=[]),
    ]
    plan = SimpleNamespace(
        deliverable=SimpleNamespace(revision_context="workspace"),
        steps=steps,
        planner="skip",
    )
    monkeypatch.setattr(engine_mod, "compile_for_run", lambda _t: plan)


# ── T2: E1 opted in ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_workspace_mode_sends_only_instruction_and_pointer(
    db_factory, monkeypatch
):
    _stub_workspace_pipeline(monkeypatch)
    parent = _seed_parent(
        db_factory, kind="widget_output", content="PARENT BODY", status="degraded"
    )
    kw = await _revise(monkeypatch, parent, "widget_output")
    assert kw["user_message"] == WORKSPACE_MESSAGE
    assert "=== ORIGINAL ARTIFACT" not in kw["user_message"]
    assert "=== PARENT RUN STATUS" not in kw["user_message"]


# ── T3: E1 unchanged for a v1 manifest ────────────────────────────────────────


@pytest.mark.asyncio
async def test_v1_revision_message_and_gates_unchanged(db_factory, monkeypatch):
    parent = _seed_parent(
        db_factory, kind="prototype_output", content="<html>old</html>"
    )
    kw = await _revise(monkeypatch, parent, "prototype_output")
    assert kw["user_message"] == (
        "=== EXISTING PROTOTYPE HTML ===\n<html>old</html>\n"
        "=== END EXISTING HTML ===\n\n"
        "=== VERSION HISTORY ===\n1 version(s) exist for this artifact.\n"
        "=== END VERSION HISTORY ===\n\n"
        f"=== REVISION REQUEST ===\n{INSTRUCTION}\n=== END REQUEST ==="
    )
    assert kw["gate_agent_ids"] == []


# ── T4: E2 gate ids ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_opted_in_pipeline_gates_declared_human_steps(db_factory, monkeypatch):
    _stub_workspace_pipeline(monkeypatch)
    parent = _seed_parent(db_factory, kind="widget_output", content="x")
    kw = await _revise(monkeypatch, parent, "widget_output")
    assert kw["gate_agent_ids"] == ["custom-agent:blr-locate"]


@pytest.mark.asyncio
async def test_v1_feature_revision_declares_human_gates_but_does_not_opt_in(
    db_factory, monkeypatch
):
    parent = _seed_parent(db_factory, kind="prototype_feature_output", content="x")
    kw = await _revise(monkeypatch, parent, "prototype_feature_output")
    assert kw["gate_agent_ids"] == []


# ── T5: the gate actually parks ───────────────────────────────────────────────


def test_should_gate_follows_gate_agent_ids_and_redo_is_offered() -> None:
    eng = ExecutionEngine()
    gated = SimpleNamespace(id="custom-agent:blr-locate")
    other = SimpleNamespace(id="custom-agent:blr-write")
    ectx = ExecutionContext(run_id="r", owner_id=OWNER, workspace_id=WS)
    ectx.gate_agent_ids = ["custom-agent:blr-locate"]
    assert eng._should_gate(gated, ectx) is True
    assert eng._should_gate(other, ectx) is False
    assert eng._redoable(ectx) is True  # single_shot: build_task_number empty

    ectx.gate_agent_ids = []
    for agent in ("prototype-revision-feature-specify", "prototype-plan"):
        assert eng._should_gate(SimpleNamespace(id=agent), ectx) is False
