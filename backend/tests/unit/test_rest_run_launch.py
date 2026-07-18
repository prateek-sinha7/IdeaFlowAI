"""tests/unit/test_rest_run_launch.py — CHAT-07 / D-13 (29-04).

The up-channel REST twin of ``POST /api/runs`` (run launch), ported from
``test_run_pipeline_validation.py`` (the WS ``run_pipeline`` ingress-validation
suite) against the REST endpoint. The endpoint mints the WorkflowRun + spawns the
WS-agnostic background driver onto the per-run queue (the SSE stream then attaches)
— LOCK-B: ``websocket.py`` is untouched; the ingress validators + queue registry
are read-only imports, and the engine-drive loop is a sanctioned duplication.

Coverage:
  * The ported allow-list predicates (``allowed_custom_agent_ids`` /
    ``SUPPORTED_PIPELINE_TYPES`` / ``_validate_model_overrides``) are re-asserted
    at the REST boundary — a bad pipeline_type / bad agent_ids / bad
    model_overrides denies with NO WorkflowRun and NO execute (rejected pre-mint).
  * The happy path mints a WorkflowRun (``user_id`` = caller) + spawns the driver,
    which populates the per-run queue (offline recording engine — no Bedrock).

Offline — in-memory SQLite (StaticPool) monkeypatched onto ``ws_module._get_db``;
a recording stub engine via ``agents.execution_engine.engine.get_execution_engine``.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Register every table the launch path touches on Base.metadata BEFORE create_all.
import app.models.artifact_ref  # noqa: F401
import app.models.run_capabilities  # noqa: F401
import app.models.run_event  # noqa: F401
import app.models.workflow  # noqa: F401
import app.models.workspace  # noqa: F401
import agents.execution_engine.engine as engine_mod


# ════════════════════════════════════════════════════════════════════════════
# Harness — in-memory SQLite + TestClient over the run_commands router
# ════════════════════════════════════════════════════════════════════════════


class _FakeUser:
    def __init__(self, id: str):
        self.id = id
        self.preferred_model = None


class _RecordingEngine:
    """Stub engine recording the execute() kwargs + emitting a minimal stream."""

    last_kwargs: dict | None = None
    invoked = False

    async def execute(self, **kwargs):
        _RecordingEngine.invoked = True
        _RecordingEngine.last_kwargs = kwargs
        yield {"type": "pipeline_start", "data": {"agents": []}}
        yield {"type": "pipeline_complete", "data": {"final_output": "done"}}


@pytest.fixture
def env(monkeypatch):
    from app.api import run_engine as ws_module
    from app.models.database import Base

    db_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    Base.metadata.create_all(bind=db_engine)
    # Patch _get_db on BOTH modules: run_commands binds its OWN reference at import
    # (``from app.api.run_engine import _get_db`` — the transport-neutral seam, 44-03),
    # so patching ws_module alone would miss the REST endpoints' direct calls. The
    # queue registries + validators are shared object references, so they need no patch.
    monkeypatch.setattr(ws_module, "_get_db", lambda: TestingSession())
    import app.api.run_commands as rc_module
    monkeypatch.setattr(rc_module, "_get_db", lambda: TestingSession())

    _RecordingEngine.invoked = False
    _RecordingEngine.last_kwargs = None
    monkeypatch.setattr(engine_mod, "get_execution_engine", lambda: _RecordingEngine())

    from app.api.run_commands import router
    from app.core.dependencies import get_current_user

    app = FastAPI()
    app.include_router(router)
    state: dict = {"user": None}
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    client = TestClient(app)

    yield {"ws": ws_module, "client": client, "state": state, "Session": TestingSession}

    Base.metadata.drop_all(bind=db_engine)
    db_engine.dispose()


def _seed_user(env) -> _FakeUser:
    from app.models.user import User

    db = env["ws"]._get_db()
    try:
        u = User(
            id=str(uuid.uuid4()),
            email=f"launch-{uuid.uuid4().hex[:8]}@example.com",
            password_hash="x",
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return _FakeUser(id=u.id)
    finally:
        db.close()


def _latest_run(env):
    from app.models.workflow import WorkflowRun

    db = env["ws"]._get_db()
    try:
        return db.query(WorkflowRun).order_by(WorkflowRun.created_at.desc()).first()
    finally:
        db.close()


def _run_count(env) -> int:
    from app.models.workflow import WorkflowRun

    db = env["ws"]._get_db()
    try:
        return db.query(WorkflowRun).count()
    finally:
        db.close()


def _post_launch(env, **body):
    return env["client"].post("/api/runs", json=body)


# ────────────────────────────────────────────────────────────────────────────
# 1. Ported ingress validation — rejected PRE-MINT (no WorkflowRun, no execute)
# ────────────────────────────────────────────────────────────────────────────


def test_unsupported_pipeline_type_rejected_pre_mint(env):
    user = _seed_user(env)
    env["state"]["user"] = user
    resp = _post_launch(env, message="build it", pipeline_type="totally_made_up")
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "invalid_pipeline_type"
    assert _run_count(env) == 0
    assert _RecordingEngine.invoked is False


def test_unknown_agent_id_rejected(env):
    """G1-C6: an agent id in NO allow-list (nonexistent / smuggled) is rejected —
    the exact ``allowed_custom_agent_ids`` predicate, now at the REST boundary.

    (The stricter cross-*base*-pipeline rejection is asserted by the registry-level
    suite; on this branch the "custom" pool has widened — see deferred-items.md —
    so this REST pin uses a genuinely-unknown id, which no widening can admit.)"""
    user = _seed_user(env)
    env["state"]["user"] = user
    resp = _post_launch(
        env, message="deck", pipeline_type="ppt",
        agent_ids=["totally-nonexistent-agent-xyz"],
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["code"] == "invalid_agent_ids"
    assert "totally-nonexistent-agent-xyz" in detail["rejected_agent_ids"]
    assert _run_count(env) == 0
    assert _RecordingEngine.invoked is False


def test_bare_prototype_missing_template_context_rejected_pre_mint(env):
    """DEF-44-08-1 / F3 (13-06): a bare ``prototype`` launch whose resolved agents
    declare ``template`` injection but carries no ``template_body`` (no ``template_id``,
    not an od_* alias) is rejected PRE-MINT with ``missing_template_context`` — the
    ingress guard re-homed to the REST launch path after 44-07 deleted the WS ingress
    where it used to live. Generic (keyed on declared injects, SC-001), no mint, no execute."""
    user = _seed_user(env)
    env["state"]["user"] = user
    resp = _post_launch(env, message="a pomodoro timer app", pipeline_type="prototype")
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "missing_template_context"
    assert _run_count(env) == 0
    assert _RecordingEngine.invoked is False


def test_unknown_model_override_rejected_pre_mint(env):
    """T-06-06 [HIGH]: an arbitrary model id (not in the catalog) is rejected."""
    user = _seed_user(env)
    env["state"]["user"] = user
    resp = _post_launch(
        env,
        message="build a backlog",
        pipeline_type="user_stories",
        model_overrides={"domain-analyst": "evil.attacker/unknown:latest"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "invalid_model_override"
    assert _run_count(env) == 0
    assert _RecordingEngine.invoked is False


def test_missing_message_is_a_422_bad_payload(env):
    """A launch with no ``message`` is a malformed payload (pydantic 422) — no
    run is minted."""
    user = _seed_user(env)
    env["state"]["user"] = user
    resp = env["client"].post("/api/runs", json={"pipeline_type": "user_stories"})
    assert resp.status_code == 422
    assert _run_count(env) == 0


# ────────────────────────────────────────────────────────────────────────────
# 2. Happy path — the endpoint mints the run (synchronous) + returns {run_id}
# ────────────────────────────────────────────────────────────────────────────


def test_launch_mints_run(env):
    user = _seed_user(env)
    env["state"]["user"] = user
    resp = _post_launch(env, message="build a backlog", pipeline_type="user_stories")
    assert resp.status_code == 200, resp.text
    run_id = resp.json()["run_id"]
    assert run_id

    # The WorkflowRun was minted BEFORE the endpoint returned, owned by the caller
    # (user_id). The background driver + SSE attach are proven at the driver level.
    run = _latest_run(env)
    assert run is not None
    assert run.id == run_id
    assert run.user_id == user.id
    assert run.type == "user_stories"
    assert run.input == "build a backlog"
    assert run.agent_count > 0


# ────────────────────────────────────────────────────────────────────────────
# 3. Driver level — the WS-agnostic background driver populates the per-run queue
#    (deterministic: drive the coroutine directly, no TestClient task-timing race)
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_driver_drives_engine_and_populates_queue(env):
    """The launch driver runs the engine + pushes every event onto the per-run
    queue (the queue the SSE stream drains) and terminates with the None sentinel,
    then persists the terminal status onto the run row."""
    from app.api import run_commands as rc

    user = _seed_user(env)
    # Seed a run row for the driver to finalize.
    from app.models.workflow import WorkflowRun

    run_id = str(uuid.uuid4())
    db = env["ws"]._get_db()
    try:
        db.add(WorkflowRun(
            id=run_id, user_id=user.id, title="t", type="user_stories",
            status="running", input="build a backlog", agent_count=1,
            session_id=user.id,
        ))
        db.commit()
    finally:
        db.close()

    queue: asyncio.Queue = asyncio.Queue()
    await rc._drive_launch_to_queue(
        workflow_run_id=run_id,
        pipeline_run_id=run_id,
        agents=[object()],  # opaque — the recording engine ignores it
        content="build a backlog",
        pipeline_type="user_stories",
        cancel_event=asyncio.Event(),
        user=user,
        attached_skills=[],
        attached_hooks=[],
        od_context=None,
        validated_images=[],
        gate_agent_ids=None,
        parent_run_id=None,
        model_overrides={},
        selections=None,
        event_queue=queue,
    )

    # The recording engine was driven with the run's identifiers.
    assert _RecordingEngine.invoked is True
    assert _RecordingEngine.last_kwargs.get("pipeline_run_id") == run_id
    assert _RecordingEngine.last_kwargs.get("user_id") == user.id
    assert _RecordingEngine.last_kwargs.get("images") == []

    # The queue carries the engine's events then the None sentinel.
    drained = []
    while True:
        item = queue.get_nowait()
        if item is None:
            break
        drained.append(item)
    types = [e["type"] for e in drained]
    assert "pipeline_start" in types
    assert "pipeline_complete" in types

    # Terminal status persisted "completed"; cleanup removed the run registries.
    # Fail-safe contract (CWF-001 D2): a CLEAN ``pipeline_complete`` with no error
    # signal is legitimately "completed"; only a missing/errored terminal → "failed".
    # The _RecordingEngine emits a clean pipeline_complete, so this stays "completed".
    row = _latest_run(env)
    assert row.status == "completed"
    assert row.status != "failed"  # anti-regression: clean terminal must not fail-safe to failed
    assert run_id not in env["ws"]._PIPELINE_QUEUES


@pytest.mark.asyncio
async def test_driver_persists_full_agent_history_like_ws(env, monkeypatch):
    """CR-02: the REST launch driver must persist the SAME agent_outputs history as
    the WS ``_run_pipeline_to_queue`` — including tool calls, thinking text, the input
    prompt, and context sources.

    The sanctioned WS→REST duplication had dropped the ``agent_input`` /
    ``agent_thinking`` / ``tool_call`` / ``tool_result`` branches (and the four
    ``current_agent`` scaffold keys), so every REST-launched run persisted a degraded
    WorkflowRun.agent_outputs blob silently missing that data. This drives the rich
    engine stream and asserts the persisted blob now carries it (fails pre-fix).
    """
    import json

    from app.api import run_commands as rc
    from app.models.workflow import WorkflowRun

    class _RichEngine:
        """Emits the full per-agent event vocabulary the WS driver records."""

        async def execute(self, **kwargs):
            yield {"type": "agent_start", "data": {
                "agent_id": "a1", "name": "A1", "role": "r", "icon": "i"}}
            yield {"type": "agent_input", "data": {
                "context_message": "PROMPT-TEXT", "context_sources": ["upstream-1"]}}
            yield {"type": "agent_thinking", "data": {"thinking": "let me "}}
            yield {"type": "agent_thinking", "data": {"thinking": "think..."}}
            yield {"type": "tool_call", "data": {
                "tool": "write_file", "args": {"path": "x"}}}
            yield {"type": "tool_result", "data": {
                "tool": "write_file", "result": "ok"}}
            yield {"type": "agent_chunk", "data": {"chunk": "hello"}}
            yield {"type": "agent_complete", "data": {
                "duration": 1.2, "input_tokens": 10, "output_tokens": 5,
                "total_tokens": 15}}
            yield {"type": "pipeline_complete", "data": {"final_output": "done"}}

    monkeypatch.setattr(engine_mod, "get_execution_engine", lambda: _RichEngine())

    user = _seed_user(env)
    run_id = str(uuid.uuid4())
    db = env["ws"]._get_db()
    try:
        db.add(WorkflowRun(
            id=run_id, user_id=user.id, title="t", type="user_stories",
            status="running", input="build a backlog", agent_count=1,
            session_id=user.id,
        ))
        db.commit()
    finally:
        db.close()

    queue: asyncio.Queue = asyncio.Queue()
    await rc._drive_launch_to_queue(
        workflow_run_id=run_id,
        pipeline_run_id=run_id,
        agents=[object()],
        content="build a backlog",
        pipeline_type="user_stories",
        cancel_event=asyncio.Event(),
        user=user,
        attached_skills=[],
        attached_hooks=[],
        od_context=None,
        validated_images=[],
        gate_agent_ids=None,
        parent_run_id=None,
        model_overrides={},
        selections=None,
        event_queue=queue,
    )

    row = _latest_run(env)
    assert row.status == "completed"
    outputs = json.loads(row.agent_outputs)
    assert len(outputs) == 1
    agent = outputs[0]
    # The four previously-dropped fields are now persisted (WS-parity).
    assert agent["input_prompt"] == "PROMPT-TEXT"
    assert agent["context_sources"] == ["upstream-1"]
    assert agent["thinking_text"] == "let me think..."
    assert len(agent["tool_calls"]) == 1
    tc = agent["tool_calls"][0]
    assert tc["tool"] == "write_file"
    assert tc["args"] == {"path": "x"}
    assert tc["result"] == "ok"  # tool_result was matched back onto the open call
    assert tc["timestamp"]  # stamped at tool_call time


# ────────────────────────────────────────────────────────────────────────────
# 3b. Fail-safe terminal status (CWF-001 D2) — a run that errors/fails at runtime
#     must NOT be persisted "completed". Reconciles the launch driver toward the
#     LOCK-B revision twin _drive_revision_to_queue (Phase 29). RED→GREEN.
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_driver_generic_error_records_failed(env, monkeypatch):
    """CWF-001 D2: a launch whose engine stream ends in a GENERIC ``error`` event
    (e.g. the compile-time DAG-unsatisfiable error) with NO clean ``pipeline_complete``
    must persist status == "failed" (was mislabeled "completed"), with the error
    message captured onto wr.error. Mirrors the revision twin's fail-safe else."""
    from app.api import run_commands as rc
    from app.models.workflow import WorkflowRun

    class _ErrorEngine:
        async def execute(self, **kwargs):
            yield {"type": "pipeline_start", "data": {"agents": []}}
            yield {"type": "error", "data": {
                "error": ("Workflow DAG is unsatisfiable: Agent 'swot-analyst' "
                          "consumes 'market-research' but no upstream agent produces it"),
                "code": "workflow_unsatisfiable",
                "recoverable": False,
            }}

    monkeypatch.setattr(engine_mod, "get_execution_engine", lambda: _ErrorEngine())

    user = _seed_user(env)
    run_id = str(uuid.uuid4())
    db = env["ws"]._get_db()
    try:
        db.add(WorkflowRun(
            id=run_id, user_id=user.id, title="t", type="user_stories",
            status="running", input="build a backlog", agent_count=1,
            session_id=user.id,
        ))
        db.commit()
    finally:
        db.close()

    queue: asyncio.Queue = asyncio.Queue()
    await rc._drive_launch_to_queue(
        workflow_run_id=run_id,
        pipeline_run_id=run_id,
        agents=[object()],
        content="build a backlog",
        pipeline_type="user_stories",
        cancel_event=asyncio.Event(),
        user=user,
        attached_skills=[],
        attached_hooks=[],
        od_context=None,
        validated_images=[],
        gate_agent_ids=None,
        parent_run_id=None,
        model_overrides={},
        selections=None,
        event_queue=queue,
    )

    row = _latest_run(env)
    assert row.status == "failed"
    assert row.status != "completed"
    assert row.error is not None
    assert "unsatisfiable" in row.error


@pytest.mark.asyncio
async def test_driver_pipeline_failed_records_failed(env, monkeypatch):
    """CWF-001 D2: a launch whose stream emits ``pipeline_failed`` with NO clean
    ``pipeline_complete`` must persist status == "failed". Mirrors the LOCK-B twin's
    ``test_driver_pipeline_failed_records_failed`` in test_rest_revisions.py."""
    from app.api import run_commands as rc
    from app.models.workflow import WorkflowRun

    class _FailEngine:
        async def execute(self, **kwargs):
            yield {"type": "pipeline_start", "data": {"agents": []}}
            yield {"type": "pipeline_failed", "data": {"error": "no agent completed"}}

    monkeypatch.setattr(engine_mod, "get_execution_engine", lambda: _FailEngine())

    user = _seed_user(env)
    run_id = str(uuid.uuid4())
    db = env["ws"]._get_db()
    try:
        db.add(WorkflowRun(
            id=run_id, user_id=user.id, title="t", type="user_stories",
            status="running", input="build a backlog", agent_count=1,
            session_id=user.id,
        ))
        db.commit()
    finally:
        db.close()

    queue: asyncio.Queue = asyncio.Queue()
    await rc._drive_launch_to_queue(
        workflow_run_id=run_id,
        pipeline_run_id=run_id,
        agents=[object()],
        content="build a backlog",
        pipeline_type="user_stories",
        cancel_event=asyncio.Event(),
        user=user,
        attached_skills=[],
        attached_hooks=[],
        od_context=None,
        validated_images=[],
        gate_agent_ids=None,
        parent_run_id=None,
        model_overrides={},
        selections=None,
        event_queue=queue,
    )

    row = _latest_run(env)
    assert row.status == "failed"
    assert row.status != "completed"


# ────────────────────────────────────────────────────────────────────────────
# 4. D-15/C — declared-signal od_context parity (SC-001 / INV-1)
#
# The launch boundary must load template/DS od_context keyed on the DECLARED
# manifest signal (``context_providers: [opendesign]``), producing the SAME dict
# the old pipeline-name branch (``pipeline_type == "od_prototype"/"od_ppt"``)
# produced. These pin byte-identity across the Task-2 rewire: the parity/None/
# rejection/REST-revision cases pass against the CURRENT name-branch and must keep
# passing against the declared-signal seam; the three ``resolve_launch_od_context``
# seam cases are the Task-2 gate (RED until the seam exists).
#
# AUDIT (Task-1 finding, contradicts RESEARCH A1 "two"): EXACTLY THREE manifests
# declare ``context_providers: [opendesign]`` — prototype, od_ppt, od_ppt_revision.
# The seam therefore preserves od_ppt_revision's per-boundary behavior: REST → None
# (this file), WS → non-fatal ppt loader (the seam ``fatal=False`` cases below).
# ────────────────────────────────────────────────────────────────────────────

# Offline-resolvable ids (present under skills/opendesign/design-templates).
_PROTO_TEMPLATE = "web-prototype"
_PROTO_DS = "material"
_PPT_TEMPLATE = "html-ppt"
_BAD_TEMPLATE = "definitely-not-a-real-template-xyz"


def _launch_body(**kw):
    from app.api.run_commands import LaunchCommand

    kw.setdefault("message", "build it")
    return LaunchCommand(**kw)


def test_od_prototype_launch_od_context_parity():
    """od_prototype resolves base 'prototype' AND builds the SAME od_context dict
    ``load_prototype_od_context`` produces directly (declared-signal == name-branch).
    The dict-equality is the byte-identity pin for the Task-2 rewire."""
    from agents.execution_engine.od_context import load_prototype_od_context

    from app.api.run_commands import _resolve_launch_agents

    body = _launch_body(pipeline_type="od_prototype",
                        template_id=_PROTO_TEMPLATE, design_system_id=_PROTO_DS)
    base, od_context = _resolve_launch_agents(body)
    expected = load_prototype_od_context(
        _PROTO_TEMPLATE, _PROTO_DS, custom_ds_body=None, custom_template_body=None)
    assert base == "prototype"
    assert od_context == expected


def test_od_ppt_launch_od_context_parity():
    """od_ppt resolves base 'od_ppt' AND builds the SAME od_context dict
    ``load_ppt_od_context`` produces directly (declared-signal == name-branch)."""
    from agents.execution_engine.od_context import load_ppt_od_context

    from app.api.run_commands import _resolve_launch_agents

    body = _launch_body(pipeline_type="od_ppt", template_id=_PPT_TEMPLATE)
    base, od_context = _resolve_launch_agents(body)
    expected = load_ppt_od_context(
        _PPT_TEMPLATE, None, custom_ds_body=None, custom_template_body=None)
    assert base == "od_ppt"
    assert od_context == expected


def test_undeclared_pipeline_launches_with_none_od_context():
    """A pipeline whose resolved manifest does NOT declare opendesign
    (user_stories) launches with od_context = None — unchanged for all non-OD
    workflows."""
    from app.api.run_commands import _resolve_launch_agents

    body = _launch_body(pipeline_type="user_stories")
    base, od_context = _resolve_launch_agents(body)
    assert base == "user_stories"
    assert od_context is None


def test_unknown_pipeline_type_rejected_in_resolver():
    """An unknown/unsupported pipeline_type still rejects pre-mint with
    invalid_pipeline_type (rejection path preserved through the seam)."""
    from fastapi import HTTPException

    from app.api.run_commands import _resolve_launch_agents

    body = _launch_body(pipeline_type="totally_made_up")
    with pytest.raises(HTTPException) as ei:
        _resolve_launch_agents(body)
    assert ei.value.detail["code"] == "invalid_pipeline_type"


def test_od_ppt_revision_rest_keeps_none():
    """REST parity: od_ppt_revision (declares opendesign) does NOT load od_context
    on the REST boundary — preserved as None, matching today's fall-through
    (websocket.py loads it NON-FATALLY; the REST twin never did)."""
    from app.api.run_commands import _resolve_launch_agents

    body = _launch_body(pipeline_type="od_ppt_revision", template_id=_PPT_TEMPLATE)
    base, od_context = _resolve_launch_agents(body)
    assert base == "od_ppt_revision"
    assert od_context is None


# ── The seam cases (Task-2 gate — RED until launch_context.py exists) ──────────


def test_seam_od_prototype_parity_via_declared_signal():
    """The shared seam resolves od_prototype through the DECLARED opendesign signal
    to the SAME dict the loader produces (name-free eligibility)."""
    from agents.execution_engine.od_context import load_prototype_od_context

    from app.api.launch_context import resolve_launch_od_context

    base, od_context = resolve_launch_od_context(
        "od_prototype", _PROTO_TEMPLATE, _PROTO_DS,
        custom_ds_body=None, custom_template_body=None, fatal=True)
    expected = load_prototype_od_context(
        _PROTO_TEMPLATE, _PROTO_DS, custom_ds_body=None, custom_template_body=None)
    assert base == "prototype"
    assert od_context == expected


def test_seam_undeclared_returns_none():
    """A pipeline that does not declare opendesign resolves to od_context None
    through the seam (the SC-001 win — eligibility is the declared signal)."""
    from app.api.launch_context import resolve_launch_od_context

    base, od_context = resolve_launch_od_context(
        "user_stories", None, None,
        custom_ds_body=None, custom_template_body=None, fatal=True)
    assert base == "user_stories"
    assert od_context is None


def test_seam_fatal_propagates_lookup_error():
    """On the fatal path a bad template raises LookupError so the caller shapes the
    rejection (V5 input-validation preserved)."""
    from app.api.launch_context import resolve_launch_od_context

    with pytest.raises(LookupError):
        resolve_launch_od_context(
            "od_ppt", _BAD_TEMPLATE, None,
            custom_ds_body=None, custom_template_body=None, fatal=True)


def test_seam_od_ppt_revision_non_fatal_swallows_lookup_error():
    """WS arm parity: od_ppt_revision loads NON-FATALLY — a failing template lookup
    returns od_context None instead of raising (reproduces websocket.py:1741-1753)."""
    from app.api.launch_context import resolve_launch_od_context

    base, od_context = resolve_launch_od_context(
        "od_ppt_revision", _BAD_TEMPLATE, None,
        custom_ds_body=None, custom_template_body=None, fatal=False)
    assert base == "od_ppt_revision"
    assert od_context is None


def test_seam_od_ppt_revision_non_fatal_loads_when_resolvable():
    """The non-fatal arm still LOADS the SAME od_context dict when the template
    resolves (od_ppt-family loader profile)."""
    from agents.execution_engine.od_context import load_ppt_od_context

    from app.api.launch_context import resolve_launch_od_context

    base, od_context = resolve_launch_od_context(
        "od_ppt_revision", _PPT_TEMPLATE, None,
        custom_ds_body=None, custom_template_body=None, fatal=False)
    expected = load_ppt_od_context(
        _PPT_TEMPLATE, None, custom_ds_body=None, custom_template_body=None)
    assert base == "od_ppt_revision"
    assert od_context == expected


# ────────────────────────────────────────────────────────────────────────────
# 5. Parent-link ownership — the primary run_pipeline IDOR path (Site 1, T-44-08-01)
#
# Migrated from ``test_ws_parent_link_ownership.py`` (the deleted
# ``_handle_workflow_execution`` :1688 ``source_workflow_run_id`` chaining site).
# The REST launch endpoint mints the WorkflowRun with
# ``parent_run_id = _resolve_owned_parent_run_id(db, body.source_workflow_run_id,
# current_user.id)`` (run_commands.py:1204) — the SAME owner-checked resolver. An
# OWNED source links; a FOREIGN / unknown source has its link DROPPED (parent_run_id
# = None) while the run still launches (mirrors the WS Site-1 contract: drop the
# edge, never leak a foreign lineage; the run is not rejected). The resolver's exact
# contract is pinned in ``test_rest_revisions.py::TestResolverDirect``.
# ────────────────────────────────────────────────────────────────────────────


def _seed_run_owned_by(env, owner_id: str) -> str:
    from app.models.workflow import WorkflowRun

    run_id = str(uuid.uuid4())
    db = env["ws"]._get_db()
    try:
        db.add(WorkflowRun(
            id=run_id, user_id=owner_id, owner_id=owner_id, title="parent",
            type="user_stories", status="completed", input="prior run",
            agent_count=1, session_id=owner_id,
        ))
        db.commit()
    finally:
        db.close()
    return run_id


def test_owned_source_links_the_child(env):
    """An owned ``source_workflow_run_id`` is persisted as the child's
    ``parent_run_id`` (family lineage intact)."""
    user = _seed_user(env)
    parent_id = _seed_run_owned_by(env, user.id)
    env["state"]["user"] = user

    resp = _post_launch(
        env, message="continue from prior", pipeline_type="user_stories",
        source_workflow_run_id=parent_id,
    )
    assert resp.status_code == 200, resp.text
    child = _latest_run(env)
    assert child.id == resp.json()["run_id"]
    assert child.parent_run_id == parent_id


def test_foreign_source_drops_the_link_but_still_launches(env):
    """T-44-08-01 (primary IDOR): a FOREIGN source run id (owned by someone else)
    must NOT be persisted as a family edge — the resolver drops it to None — while
    the run still launches (the WS Site-1 contract: drop the link, never reject)."""
    owner = _seed_user(env)
    attacker = _seed_user(env)
    foreign_parent = _seed_run_owned_by(env, owner.id)
    env["state"]["user"] = attacker

    resp = _post_launch(
        env, message="steal the lineage", pipeline_type="user_stories",
        source_workflow_run_id=foreign_parent,
    )
    assert resp.status_code == 200, resp.text
    child = _latest_run(env)
    assert child.user_id == attacker.id
    # The foreign parent edge was dropped — the family walk can never reach it.
    assert child.parent_run_id is None


def test_unknown_source_drops_the_link_but_still_launches(env):
    """An unknown source run id resolves to None (no run-existence oracle) and the
    run still launches with no parent edge."""
    user = _seed_user(env)
    env["state"]["user"] = user

    resp = _post_launch(
        env, message="unknown parent", pipeline_type="user_stories",
        source_workflow_run_id=str(uuid.uuid4()),
    )
    assert resp.status_code == 200, resp.text
    assert _latest_run(env).parent_run_id is None
