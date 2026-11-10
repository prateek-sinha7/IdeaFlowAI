"""P27 E6 self-healing (``resilience:`` manifest key).

Covers: manifest accept/reject, runner retry window, stall watchdog, step retry,
credential / poison / budget pauses, startup keep-paused, resume accepting ``paused``,
and that a workflow WITHOUT the key still fails exactly as before.
"""

from __future__ import annotations

import asyncio
import copy
from types import SimpleNamespace

import pytest

import agents.execution_engine.engine as engine_mod
import app.agents.deep_agent_runner as runner_module
from agents.capabilities.registry import CapabilityRegistry
from agents.model_policy import StepStalled, _is_transient_throttle
from agents.workflows.compiler import WorkflowCompiler
from agents.workflows.manifest import (
    RESILIENCE_DEFAULTS,
    ManifestValidationError,
    build_manifest_from_dict,
)
from tests.agents import _scripted_model as _sm
from tests.agents._scripted_model import (
    ScriptedFakeChatModel,
    ScriptedThrottleError,
    _drive,
    _ScriptedTurn,
)
from tests.agents.test_transient_retry import (
    _event_stream_error,
    _make_runner,
    _RaiseThenSucceedModel,
)


# ---------------------------------------------------------------------------
# Manifest / compiler
# ---------------------------------------------------------------------------
def _manifest_dict(**extra):
    base = {
        "id": "res-test",
        "steps": [{"agent": "custom-agent:a", "strategy": "single_shot"}],
        "deliverable": {},
        "planner": "run",
        "clarify": {"mode": "off", "defaults": []},
    }
    base.update(extra)
    return base


def test_manifest_without_resilience_is_none():
    assert build_manifest_from_dict(_manifest_dict(), "t").resilience is None


def test_manifest_block_present_fills_defaults():
    m = build_manifest_from_dict(_manifest_dict(resilience={}), "t")
    assert m.resilience == RESILIENCE_DEFAULTS
    assert m.resilience == {
        "retry_window_seconds": 900,
        "stall_seconds": 600,
        "max_same_error": 3,
        "pause_after_seconds": 14400,
        "credential_probe_seconds": 300,
    }


def test_manifest_partial_override():
    m = build_manifest_from_dict(
        _manifest_dict(resilience={"stall_seconds": 5, "max_same_error": 2}), "t"
    )
    assert m.resilience["stall_seconds"] == 5
    assert m.resilience["max_same_error"] == 2
    assert m.resilience["retry_window_seconds"] == 900


@pytest.mark.parametrize(
    "block",
    [
        {"bogus": 1},
        {"stall_seconds": 0},
        {"stall_seconds": -3},
        {"stall_seconds": True},
        {"stall_seconds": "600"},
        {"stall_seconds": 1.5},
        [1, 2],
    ],
)
def test_manifest_rejects_bad_block(block):
    with pytest.raises(ManifestValidationError):
        build_manifest_from_dict(_manifest_dict(resilience=block), "t")


def test_compiled_workflow_carries_resilience():
    m = build_manifest_from_dict(_manifest_dict(resilience={"max_same_error": 4}), "t")
    compiled = WorkflowCompiler().compile(m, CapabilityRegistry())
    assert compiled.resilience["max_same_error"] == 4
    plain = WorkflowCompiler().compile(
        build_manifest_from_dict(_manifest_dict(), "t"), CapabilityRegistry()
    )
    assert plain.resilience is None


# ---------------------------------------------------------------------------
# Level 1 — runner retry window
# ---------------------------------------------------------------------------
class _FakeClock:
    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now


def _patch_clock(monkeypatch):
    clock = _FakeClock()
    monkeypatch.setattr(runner_module.time, "monotonic", clock.monotonic)

    async def _sleep(delay):
        clock.now += delay

    monkeypatch.setattr(runner_module.asyncio, "sleep", _sleep)
    return clock


@pytest.mark.asyncio
async def test_runner_retries_past_three_attempts_within_window(monkeypatch):
    _patch_clock(monkeypatch)
    exc = _event_stream_error("internalServerException", "try again")
    model = _RaiseThenSucceedModel(exc, fail_count=6, final_text="finally")
    runner = _make_runner(model, "res-window-ok")
    runner.resilience = {"retry_window_seconds": 900}

    events = [ev async for ev in runner.astream_events("hi")]

    assert model._calls == 7  # > the fixed 3 attempts
    assert "finally" in [e for e in events if e.get("type") == "done"][-1]["output"]
    assert any(e.get("type") == "retry_wait" for e in events)


@pytest.mark.asyncio
async def test_runner_stops_when_window_elapsed(monkeypatch):
    clock = _patch_clock(monkeypatch)
    exc = _event_stream_error("internalServerException", "try again")
    model = _RaiseThenSucceedModel(exc, fail_count=10_000, final_text="never")
    runner = _make_runner(model, "res-window-end")
    runner.resilience = {"retry_window_seconds": 100}

    with pytest.raises(type(exc)):
        [ev async for ev in runner.astream_events("hi")]

    assert model._calls > 3
    assert clock.now - 1000.0 >= 100  # slept right up to the window edge
    assert clock.now - 1000.0 < 100 + 61  # and no further than one more call


@pytest.mark.asyncio
async def test_runner_without_resilience_keeps_three_attempts(monkeypatch):
    _patch_clock(monkeypatch)
    exc = _event_stream_error("internalServerException", "try again")
    model = _RaiseThenSucceedModel(exc, fail_count=99, final_text="never")
    runner = _make_runner(model, "res-none")
    with pytest.raises(type(exc)):
        [ev async for ev in runner.astream_events("hi")]
    assert model._calls == 3


# ---------------------------------------------------------------------------
# Level 3 — stall watchdog + step retry
# ---------------------------------------------------------------------------
def test_step_stalled_is_transient():
    assert _is_transient_throttle(StepStalled("x")) is True


@pytest.mark.asyncio
async def test_stall_guard_passes_events_and_raises_on_silence():
    async def _ok():
        yield 1
        yield 2

    assert [e async for e in engine_mod._stall_guarded(_ok(), 5)] == [1, 2]

    closed = []

    async def _hang():
        try:
            yield 1
            await asyncio.sleep(60)
            yield 2
        finally:
            closed.append(True)

    got = []
    with pytest.raises(StepStalled):
        async for e in engine_mod._stall_guarded(_hang(), 0.05):
            got.append(e)
    assert got == [1]
    assert closed == [True]  # the agent stream was really stopped


def _retry_ectx(resilience):
    return SimpleNamespace(
        resilience=resilience,
        run_id="r1",
        artifacts=SimpleNamespace(tree=lambda _rid: []),
    )


@pytest.mark.asyncio
async def test_step_stall_triggers_step_retry(monkeypatch):
    eng = engine_mod.ExecutionEngine()
    sleeps = []

    async def _fake_sleep(s):
        sleeps.append(s)

    async def _no_reuse(*a, **k):
        return None

    monkeypatch.setattr(engine_mod, "_retry_sleep", _fake_sleep)
    monkeypatch.setattr(eng, "_find_reused_completion", _no_reuse)
    monkeypatch.setattr(eng, "_compute_step_input_hash", lambda *a, **k: "h")

    calls = {"n": 0}

    class _Strategy:
        async def run(self, step, ectx):
            calls["n"] += 1
            if calls["n"] == 1:
                raise StepStalled("silent")
            yield {"type": "agent_complete", "data": {}}

    step = SimpleNamespace(agent_id="s1", retry=None)
    ectx = _retry_ectx({"max_same_error": 3})
    events = [e async for e in eng._dispatch_step_with_retry(step, ectx, _Strategy())]

    types = [e["type"] for e in events]
    assert types == ["step_retry", "agent_complete", "step_completed"]
    assert sleeps == [30.0]


@pytest.mark.asyncio
async def test_step_retry_exhausts_after_max_same_error(monkeypatch):
    eng = engine_mod.ExecutionEngine()

    async def _fake_sleep(s):
        return None

    async def _no_reuse(*a, **k):
        return None

    monkeypatch.setattr(engine_mod, "_retry_sleep", _fake_sleep)
    monkeypatch.setattr(eng, "_find_reused_completion", _no_reuse)
    monkeypatch.setattr(eng, "_compute_step_input_hash", lambda *a, **k: "h")
    calls = {"n": 0}

    class _Strategy:
        async def run(self, step, ectx):
            calls["n"] += 1
            raise ScriptedThrottleError()
            yield  # pragma: no cover

    step = SimpleNamespace(agent_id="s1", retry=None)
    with pytest.raises(ScriptedThrottleError):
        [
            e
            async for e in eng._dispatch_step_with_retry(
                step, _retry_ectx({"max_same_error": 2}), _Strategy()
            )
        ]
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_step_without_resilience_has_no_retry():
    eng = engine_mod.ExecutionEngine()
    calls = {"n": 0}

    class _Strategy:
        async def run(self, step, ectx):
            calls["n"] += 1
            raise ScriptedThrottleError()
            yield  # pragma: no cover

    step = SimpleNamespace(agent_id="s1", retry=None)
    with pytest.raises(ScriptedThrottleError):
        [
            e
            async for e in eng._dispatch_step_with_retry(
                step, _retry_ectx(None), _Strategy()
            )
        ]
    assert calls["n"] == 1


# ---------------------------------------------------------------------------
# Level 5 — pause, end to end through the scripted engine
# ---------------------------------------------------------------------------
_PIPELINE = "ex_A1_loop"
_RES = {
    "retry_window_seconds": 1,
    "stall_seconds": 30,
    "max_same_error": 2,
    "pause_after_seconds": 3600,
    "credential_probe_seconds": 7,
}


def _install(monkeypatch, *, resilience, raise_exc=None, mutate=None):
    """Patch compile_for_run (chained under the harness's own) and the scripted model."""
    orig_compile = engine_mod.compile_for_run

    def _compile(pipeline_type):
        compiled = copy.deepcopy(orig_compile(pipeline_type))
        compiled.resilience = dict(resilience) if resilience else None
        if mutate:
            mutate(compiled)
        return compiled

    monkeypatch.setattr(engine_mod, "compile_for_run", _compile)

    real = ScriptedFakeChatModel

    def _model(turns, **kw):
        return real(turns, raise_exc=raise_exc, **kw)

    monkeypatch.setattr(_sm, "ScriptedFakeChatModel", _model)

    async def _nosleep(*a, **k):
        return None

    monkeypatch.setattr(engine_mod, "_retry_sleep", _nosleep)


@pytest.fixture
def probes(monkeypatch):
    started = []
    monkeypatch.setattr(
        engine_mod.ExecutionEngine,
        "_start_credential_probe",
        lambda self, run_id, res: started.append((run_id, res)),
    )
    return started


def _paused(events):
    return [e for e in events if e["type"] == "run_paused"]


@pytest.mark.asyncio
async def test_credential_error_pauses_and_starts_probe(monkeypatch, probes):
    _install(
        monkeypatch,
        resilience=_RES,
        raise_exc=Exception("AccessDeniedException: credential rejected"),
    )
    events = await _drive(_PIPELINE)
    paused = _paused(events)
    assert len(paused) == 1 and paused[0]["data"]["kind"] == "credentials"
    assert paused[0]["data"]["run_id"]
    assert not [
        e for e in events if e["type"] in ("pipeline_failed", "pipeline_complete")
    ]
    assert len(probes) == 1 and probes[0][1]["credential_probe_seconds"] == 7
    assert engine_mod.get_state_machine().get_state(probes[0][0]) == "paused"


@pytest.mark.asyncio
async def test_non_transient_error_pauses_as_poison(monkeypatch, probes):
    _install(
        monkeypatch,
        resilience=_RES,
        raise_exc=_sm.ScriptedNonTransientError(),
    )
    events = await _drive(_PIPELINE)
    paused = _paused(events)
    assert len(paused) == 1 and paused[0]["data"]["kind"] == "poison"
    assert probes == []
    assert not [
        e for e in events if e["type"] in ("pipeline_failed", "pipeline_complete")
    ]


@pytest.mark.asyncio
async def test_transient_error_exhausted_pauses_as_poison(monkeypatch, probes):
    real_sleep = asyncio.sleep

    async def _fast_sleep(delay):
        await real_sleep(0)

    monkeypatch.setattr(runner_module.asyncio, "sleep", _fast_sleep)
    _install(monkeypatch, resilience=_RES, raise_exc=ScriptedThrottleError())
    events = await _drive(_PIPELINE)
    paused = _paused(events)
    assert len(paused) == 1 and paused[0]["data"]["kind"] == "poison"
    assert len([e for e in events if e["type"] == "step_retry"]) == 1  # 2 attempts


@pytest.mark.asyncio
async def test_budget_exceeded_pauses(monkeypatch, probes):
    def _fail_mode(compiled):
        for step in compiled.steps:
            if "check" in step.id and step.route is not None:
                step.route.on_loop_exhausted = "fail"

    def _scripts(agent_id):
        if agent_id == "custom-agent:check":
            return [_ScriptedTurn(texts=['{"decision": "retry"}'], usage=(5, 3))]
        return [_ScriptedTurn(texts=[f"{agent_id} out."], usage=(5, 3))]

    monkeypatch.setattr(_sm, "_scripts_for", _scripts)
    _install(monkeypatch, resilience=_RES, mutate=_fail_mode)
    events = await _drive(_PIPELINE)
    paused = _paused(events)
    assert len(paused) == 1 and paused[0]["data"]["kind"] == "budget"
    assert (
        "loop_iterations" in paused[0]["data"]["reason"] or paused[0]["data"]["reason"]
    )
    assert not [e for e in events if e["type"] == "pipeline_failed"]


@pytest.mark.asyncio
async def test_wall_clock_pauses(monkeypatch, probes):
    _install(monkeypatch, resilience={**_RES, "pause_after_seconds": 0})
    events = await _drive(_PIPELINE)
    paused = _paused(events)
    assert len(paused) == 1 and paused[0]["data"]["kind"] == "budget"
    assert not [e for e in events if e["type"] == "agent_start"]


@pytest.mark.asyncio
async def test_without_resilience_failure_is_unchanged(monkeypatch, probes):
    _install(monkeypatch, resilience=None, raise_exc=_sm.ScriptedNonTransientError())
    events = await _drive(_PIPELINE)
    assert _paused(events) == []
    assert probes == []
    assert [e for e in events if e["type"] == "pipeline_failed"]


# ---------------------------------------------------------------------------
# State machine helpers, resume endpoint, probe, startup
# ---------------------------------------------------------------------------
def test_paused_is_non_terminal_and_reason_roundtrips():
    from agents.execution_engine.state_machine import (
        TERMINAL_STATES,
        VALID_STATES,
        format_pause_reason,
        parse_pause_kind,
    )

    assert "paused" in VALID_STATES and "paused" not in TERMINAL_STATES
    assert "paused" in engine_mod.NON_TERMINAL_RUN_STATUSES
    text = format_pause_reason("credentials", "key: expired")
    assert parse_pause_kind(text) == "credentials"
    assert parse_pause_kind("boom") is None


@pytest.fixture
def db_session(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import app.api.run_commands as rc
    import app.models.database as dbm
    from app.models.database import Base
    from app.models.workflow import WorkflowRun  # noqa: F401

    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    try:
        from app.models.user import User  # noqa: F401

        Base.metadata.create_all(
            eng,
            tables=[
                Base.metadata.tables["workflow_runs"],
                Base.metadata.tables["users"],
            ],
        )
    except Exception:
        pytest.skip("workflow_runs cannot be created on sqlite here")
    Session = sessionmaker(bind=eng)
    monkeypatch.setattr(dbm, "SessionLocal", Session)
    monkeypatch.setattr(rc, "_get_db", lambda: Session())
    return Session


def _make_run(
    Session, status, error=None, run_id="run-paused-1", *, run_type="ex_A1_loop", **cols
):
    from app.models.user import User
    from app.models.workflow import WorkflowRun

    db = Session()
    try:
        if db.query(User).filter(User.id == "u1").first() is None:
            db.add(
                User(
                    id="u1",
                    email="u1@example.com",
                    cognito_sub="sub-u1",
                    tier="enterprise",
                    preferred_model=cols.pop("preferred_model", None),
                )
            )
        db.add(
            WorkflowRun(
                id=run_id,
                user_id="u1",
                type=run_type,
                status=status,
                input="x",
                error=error,
                **cols,
            )
        )
        db.commit()
    finally:
        db.close()
    return run_id


@pytest.mark.asyncio
async def test_auto_resume_accepts_paused_and_clears_reason(monkeypatch, db_session):
    import app.api.run_commands as rc
    from app.models.workflow import WorkflowRun

    run_id = _make_run(db_session, "paused", "paused:credentials: expired")
    driven = []

    async def _fake_drive(rid, *, user):
        driven.append(rid)

    monkeypatch.setattr(rc, "_drive_user_resume", _fake_drive)
    monkeypatch.setattr(rc, "_is_run_live", lambda rid: False)
    try:
        assert await rc.auto_resume_paused_run(run_id) is True
        await asyncio.sleep(0)
        assert driven == [run_id]
        db = db_session()
        wr = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
        assert wr.status == "running" and wr.error is None
        db.close()
        # a second call is a no-op: no longer paused
        assert await rc.auto_resume_paused_run(run_id) is False
    finally:
        rc._PIPELINE_TASKS.pop(run_id, None)
        rc._CANCEL_EVENTS.pop(run_id, None)


@pytest.mark.asyncio
async def test_probe_resumes_when_model_call_succeeds(monkeypatch, db_session):
    import app.api.run_commands as rc

    run_id = _make_run(
        db_session, "paused", "paused:credentials: expired", run_id="run-probe-1"
    )
    attempts = {"n": 0}

    async def _probe(model_id=None):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("still revoked")

    resumed = []

    async def _resume(rid):
        resumed.append(rid)
        return True

    real_sleep = asyncio.sleep

    async def _fast(_s):
        await real_sleep(0)

    monkeypatch.setattr(rc, "_probe_model_once", _probe)
    monkeypatch.setattr(rc, "auto_resume_paused_run", _resume)
    monkeypatch.setattr(rc.asyncio, "sleep", _fast)
    await rc._credential_probe_loop(run_id, 300)
    assert attempts["n"] == 3 and resumed == [run_id]


@pytest.mark.asyncio
async def test_probe_stops_when_no_longer_paused(monkeypatch, db_session):
    import app.api.run_commands as rc

    run_id = _make_run(db_session, "cancelled", None, run_id="run-probe-2")
    called = []

    async def _probe(model_id=None):
        called.append(1)

    real_sleep = asyncio.sleep

    async def _fast(_s):
        await real_sleep(0)

    monkeypatch.setattr(rc, "_probe_model_once", _probe)
    monkeypatch.setattr(rc.asyncio, "sleep", _fast)
    await rc._credential_probe_loop(run_id, 300)
    assert called == []


def test_resume_endpoint_lists_paused_as_resumable():
    import inspect

    import app.api.run_commands as rc

    src = inspect.getsource(rc.resume_run_endpoint)
    assert '| {"paused"}' in src


@pytest.mark.asyncio
async def test_startup_keeps_paused_and_restarts_credential_probe(
    monkeypatch, db_session
):
    from app.models.workflow import WorkflowRun

    _make_run(db_session, "paused", "paused:credentials: expired", run_id="boot-1")
    _make_run(db_session, "paused", "paused:poison: step x", run_id="boot-2")
    eng = engine_mod.ExecutionEngine()
    started = []
    eng._paused_probe_start = lambda rid, secs: started.append((rid, secs))

    async def _never(*a, **k):
        raise AssertionError("a paused run must not be auto-resumed")

    monkeypatch.setattr(eng, "resume_run", _never)
    await eng.restore_non_terminal_runs()

    assert [r for r, _ in started] == ["boot-1"]
    db = db_session()
    try:
        for rid in ("boot-1", "boot-2"):
            wr = db.query(WorkflowRun).filter(WorkflowRun.id == rid).first()
            assert wr.status == "paused"
    finally:
        db.close()


@pytest.mark.asyncio
async def test_auto_resume_blocked_gate_keeps_paused_with_reason(
    monkeypatch, db_session
):
    import app.api.run_commands as rc
    from app.models.workflow import WorkflowRun

    run_id = _make_run(
        db_session, "paused", "paused:credentials: expired", run_id="gate-1"
    )
    monkeypatch.setattr(rc, "_is_run_live", lambda rid: False)
    monkeypatch.setattr(
        rc, "_auto_resume_gate_failure", lambda wr, owner: "tier too low"
    )
    spawned = []

    async def _drive(rid, *, user):
        spawned.append(rid)

    monkeypatch.setattr(rc, "_drive_user_resume", _drive)
    assert await rc.auto_resume_paused_run(run_id) is False
    db = db_session()
    wr = db.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    assert wr.status == "paused"
    assert wr.error == "paused:poison: auto-resume blocked: tier too low"
    db.close()
    assert spawned == []


def test_gate_failure_real_gates(monkeypatch, db_session):
    import app.api.run_commands as rc
    from app.models.user import User
    from app.models.workflow import WorkflowRun

    _make_run(db_session, "paused", None, run_id="gate-2")
    db = db_session()
    wr = db.query(WorkflowRun).filter(WorkflowRun.id == "gate-2").first()
    owner = db.query(User).filter(User.id == "u1").first()
    assert rc._auto_resume_gate_failure(wr, owner) is None  # enterprise: passes
    assert rc._auto_resume_gate_failure(wr, None) == "owner account not found"

    monkeypatch.setattr(
        rc,
        "_require_tier_entitlement",
        lambda u, p, t: (_ for _ in ()).throw(
            rc._reject("tier_not_entitled", "not on your plan", http_status=403)
        ),
    )
    assert rc._auto_resume_gate_failure(wr, owner) == "not on your plan"
    monkeypatch.undo()

    monkeypatch.setattr(rc, "can_use_model", lambda tier, m: (False, "no"))
    owner.preferred_model = "some-model"
    assert "some-model" in rc._auto_resume_gate_failure(wr, owner)
    db.close()


@pytest.mark.asyncio
async def test_auto_resume_passes_real_owner_when_gates_pass(monkeypatch, db_session):
    import app.api.run_commands as rc

    run_id = _make_run(db_session, "paused", "paused:credentials: x", run_id="gate-3")
    monkeypatch.setattr(rc, "_is_run_live", lambda rid: False)
    got = []

    async def _drive(rid, *, user):
        got.append(user)

    monkeypatch.setattr(rc, "_drive_user_resume", _drive)
    try:
        assert await rc.auto_resume_paused_run(run_id) is True
        await asyncio.sleep(0)
        assert got and got[0].id == "u1"
    finally:
        rc._PIPELINE_TASKS.pop(run_id, None)
        rc._CANCEL_EVENTS.pop(run_id, None)


@pytest.mark.asyncio
async def test_probe_uses_the_runs_model(monkeypatch, db_session):
    import app.api.run_commands as rc

    run_id = _make_run(
        db_session,
        "paused",
        "paused:credentials: x",
        run_id="probe-model",
        model_id="run-model-x",
    )
    seen = []

    async def _probe(model_id=None):
        seen.append(model_id)

    async def _resume(rid):
        return True

    real_sleep = asyncio.sleep

    async def _fast(_s):
        await real_sleep(0)

    monkeypatch.setattr(rc, "_probe_model_once", _probe)
    monkeypatch.setattr(rc, "auto_resume_paused_run", _resume)
    monkeypatch.setattr(rc.asyncio, "sleep", _fast)
    await rc._credential_probe_loop(run_id, 1)
    assert seen == ["run-model-x"]


@pytest.mark.asyncio
async def test_probe_model_once_builds_requested_model(monkeypatch):
    import app.agents.model_factory as mf
    import app.api.run_commands as rc

    built = {}

    class _M:
        async def ainvoke(self, _x):
            return None

    def _build(model_id, **kw):
        built["id"], built["kw"] = model_id, kw
        return _M()

    monkeypatch.setattr(mf, "build_model", _build)
    await rc._probe_model_once("the-run-model")
    assert built["id"] == "the-run-model" and built["kw"] == {"max_tokens": 1}
