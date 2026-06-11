"""tests/agents/test_restart_resume.py — RESUME-04 / WAVE-03 durable mid-wave resume.

The 12-03 durable resume tier: a backend restart leaves an in-flight run mid-build;
``restore_non_terminal_runs`` classifies it three ways (D-08) and a resumable in-flight
run is auto-resumed IN-PROCESS via ``resume_run`` — which rebuilds the ExecutionContext
through the SAME ``_execute_impl`` construction path (no forked dispatch loop, INV-12)
and re-enters the SINGLE per-step dispatch loop at the FIRST incomplete step. MID-WAVE
(WAVE-03): the wave_scheduler strategy reads the durable ``wave_runs``/``subagent_runs``
rows and re-fans-out ONLY the incomplete workers — a completed wave/worker is NOT
re-invoked.

The mid-wave test (the headline assertion) binds a REAL in-memory SQLite ScopedStore
(RESEARCH Open Q3) so instance A's ``wave_runs``/``subagent_runs``/``run_events`` persist
for instance B:

  * engine instance A drives the ``sample_wave`` workflow but is interrupted mid-wave:
    wave 0 completes (part_a/part_b written, wave_runs[0]=completed); wave 1 fails (the
    scripted worker raises on part_c/part_d), so the run is left non-terminal with one
    completed wave + an incomplete wave;
  * a NEW engine instance B runs ``resume_run`` over the SAME durable DB: the wave step
    is re-entered, the strategy SKIPS the completed wave 0 (terminal wave_runs row) and
    re-runs only wave 1; the run reaches the final deliverable;
  * ASSERTION: the wave-0 workers are NOT re-invoked on resume (the part_a/part_b model
    calls happen ZERO times in instance B), and the run produces all four files.

Plus the two non-(b) branches of ``restore_non_terminal_runs``:
  (a) a ``waiting_for_user`` run still resumes only on user action (re-armed, not driven);
  (c) a stateless legacy run (no durable step state) keeps the WR-05 abandoned→failed path.

Offline / in-memory SQLite / no API key / no network — the ``backend:characterization``
job.
"""

from __future__ import annotations

import json as _json
import re
import uuid
from pathlib import Path
from typing import Any, Iterator

import frontmatter  # type: ignore[import-untyped]
import pytest
from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from tests.agents._scripted_model import (  # noqa: E402
    _RUNS_ROOT,
    ScriptedFakeChatModel,
    _ScriptedTurn,
)

_MANIFEST_HOME = Path(__file__).resolve().parents[2] / "agents" / "workflows"
_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "sample_wave"
_FIXTURE_ID = "sample_wave"
_PART_RE = re.compile(r"part_([a-d])\.txt")

_TASK_PLAN = (
    "Here is the plan:\n\n```json\n"
    + _json.dumps(
        {
            "tasks": [
                {"id": "t1", "title": "Write A", "body": "Write the file part_a.txt with the content 'a'.", "targets": ["part_a.txt"]},
                {"id": "t2", "title": "Write B", "body": "Write the file part_b.txt with the content 'b'.", "targets": ["part_b.txt"]},
                {"id": "t3", "title": "Write C", "body": "Write the file part_c.txt with the content 'c'.", "targets": ["part_c.txt"], "depends_on": ["t1"]},
                {"id": "t4", "title": "Write D", "body": "Write the file part_d.txt with the content 'd'.", "targets": ["part_d.txt"], "depends_on": ["t2"]},
            ]
        },
        indent=2,
    )
    + "\n```\n"
)


class _PartWritingModel(ScriptedFakeChatModel):
    """Worker model: writes the ``part_X.txt`` in its task; counts per-letter calls.

    ``fail_on`` is a set of letters (e.g. {'c','d'}) the model RAISES on (the instance-A
    interrupt — wave 1 fails). ``call_log`` is a SHARED dict letter→count so the resume
    test can assert wave-0 workers (a/b) are NOT re-invoked by instance B.
    """

    def __init__(self, turns, *, is_worker=False, fail_on=None, call_log=None, **kwargs: Any) -> None:
        super().__init__(turns, **kwargs)
        object.__setattr__(self, "_is_worker", is_worker)
        object.__setattr__(self, "_fail_on", set(fail_on or ()))
        object.__setattr__(self, "_call_log", call_log if call_log is not None else {})

    def _stream(self, messages, stop=None, run_manager=None, **kwargs) -> Iterator[ChatGenerationChunk]:
        if not self._is_worker:
            yield from super()._stream(messages, stop, run_manager, **kwargs)
            return
        blob = "\n".join(str(getattr(m, "content", "")) for m in messages)
        task_blocks = re.findall(
            r"=== CURRENT TASK ===\n(.*?)\n=== END CURRENT TASK ===", blob, re.DOTALL
        )
        scope = task_blocks[-1] if task_blocks else blob
        matches = list(_PART_RE.finditer(scope))
        if matches:
            letter = matches[-1].group(1)
            # Count the call for THIS letter (the wave worker for part_<letter>.txt).
            self._call_log[letter] = self._call_log.get(letter, 0) + 1
            if letter in self._fail_on:
                raise RuntimeError(f"scripted interrupt on part_{letter}.txt (instance A crash)")
        already_wrote = bool(self._call_index)
        object.__setattr__(self, "_call_index", self._call_index + 1)
        if not matches or already_wrote:
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content="Done.",
                    usage_metadata={"input_tokens": 4, "output_tokens": 2, "total_tokens": 6},
                    chunk_position="last",
                )
            )
            return
        m = matches[-1]
        fname, letter = m.group(0), m.group(1)
        yield ChatGenerationChunk(
            message=AIMessageChunk(
                content=f"Writing {fname}. ",
                tool_call_chunks=[{
                    "name": "write_file",
                    "args": _json.dumps({"file_path": fname, "content": f"{letter}\n"}),
                    "id": f"c_w_{letter}", "index": 0,
                }],
                usage_metadata={"input_tokens": 12, "output_tokens": 6, "total_tokens": 18},
                chunk_position="last",
            )
        )


def _load_fixture_specs():
    from agents.loader import AgentSpec

    specs = []
    for agent_dir in sorted(_FIXTURE_DIR.iterdir()):
        agent_file = agent_dir / "AGENT.md"
        if not agent_file.is_file():
            continue
        post = frontmatter.loads(agent_file.read_text(encoding="utf-8"))
        md = post.metadata
        specs.append(
            AgentSpec(
                id=md["id"], name=md["name"], role=md["role"],
                pipeline_type=md["pipeline_type"], order=int(md["order"]),
                max_tokens=int(md["max_tokens"]), prompt_body=post.content,
                tools=list(md.get("tools", []) or []),
                guardrails=list(md.get("guardrails", []) or []),
                context_from=list(md.get("context_from", []) or []),
                produces=list(md.get("produces", []) or []),
                consumes=list(md.get("consumes", []) or []),
            )
        )
    specs.sort(key=lambda s: s.order)
    return specs


def _scripts_for(agent_id: str):
    if agent_id == "sample-wave-plan":
        return [_ScriptedTurn(texts=[_TASK_PLAN], usage=(20, 16))]
    return [_ScriptedTurn(texts=[f"{agent_id} default."], usage=(5, 3))]


class _ResumeHarness:
    """Patches compile/registry/factory/ScopedStore onto a SHARED in-memory session.

    The SAME session is reused across instance A and instance B so the durable
    wave_runs/subagent_runs/run_events persist across the simulated restart (Open Q3).
    """

    def __init__(self, session, call_log, fail_on, *, db_engine=None, raise_on_fanout_call=None):
        self.session = session
        self.call_log = call_log
        self.fail_on = fail_on
        self.db_engine = db_engine
        # When set to N, the Nth run_fanout invocation (1-based) raises mid-wave AFTER
        # its workers ran — simulating an instance-A crash after wave (N-1) completed.
        self.raise_on_fanout_call = raise_on_fanout_call
        self._restore = []

    def __enter__(self):
        import agents.execution_engine.engine as engine_mod
        import agents.factory as factory_mod
        import agents.registry as registry_mod
        from agents.loader import _SPEC_CACHE
        from agents.workflows.manifest import load_manifest
        from app.core.config import settings as _settings

        _settings.RUNS_ROOT = _RUNS_ROOT
        self._engine_mod = engine_mod
        self._registry_mod = registry_mod
        self._factory_mod = factory_mod
        self._spec_cache = _SPEC_CACHE
        specs = _load_fixture_specs()
        self.specs = specs
        self.spec_ids = [s.id for s in specs]

        _orig_compile = engine_mod.compile_for_run
        _CAP = engine_mod._CAPABILITY_REGISTRY
        _WC = engine_mod._WORKFLOW_COMPILER

        def _patched_compile(pt, _orig=_orig_compile):
            if pt == _FIXTURE_ID:
                compiled = _WC.compile(load_manifest(_FIXTURE_ID, _MANIFEST_HOME), _CAP)
                compiled.clarify.mode = "off"
                return compiled
            compiled = _orig(pt)
            compiled.clarify.mode = "off"
            return compiled

        _orig_alias = engine_mod.resolve_alias

        def _patched_alias(pt, _orig=_orig_alias):
            return _FIXTURE_ID if pt == _FIXTURE_ID else _orig(pt)

        _orig_gpa = registry_mod.get_pipeline_agents

        def _patched_gpa(pt, _orig=_orig_gpa):
            return list(specs) if pt == _FIXTURE_ID else _orig(pt)

        _orig_cr = factory_mod.create_runner
        _orig_engine_cr = getattr(engine_mod, "create_runner", None)

        def _patched_cr(agent_id, ctx, **kw):
            ctx.model = _PartWritingModel(
                _scripts_for(agent_id),
                is_worker=(agent_id == "sample-wave-worker"),
                fail_on=self.fail_on,
                call_log=self.call_log,
            )
            return _orig_cr(agent_id, ctx, **kw)

        _orig_ss = engine_mod.ScopedStore
        session = self.session

        def _patched_ss(*a, **k):
            k.setdefault("session", session)
            return _orig_ss(*a, **k)

        for s in specs:
            _SPEC_CACHE[s.id] = s
        engine_mod.compile_for_run = _patched_compile
        engine_mod.resolve_alias = _patched_alias
        registry_mod.get_pipeline_agents = _patched_gpa
        factory_mod.create_runner = _patched_cr
        engine_mod.create_runner = _patched_cr
        engine_mod.ScopedStore = _patched_ss

        # Optionally interrupt instance A on the Nth run_fanout call (mid-wave crash):
        # the wrapper raises ON ENTRY for that call so the failing wave's workers never
        # run on instance A — the resume must run them, proving the offset re-enters the
        # incomplete wave (and the completed waves' workers are NOT re-invoked).
        from agents.execution_engine.kernel_services import KernelServices as _KS

        _orig_fanout = _KS.run_fanout
        _fanout_calls = {"n": 0}
        _raise_on = self.raise_on_fanout_call

        if _raise_on is not None:
            async def _wrapped_fanout(self_ks, *a, **k):
                _fanout_calls["n"] += 1
                if _fanout_calls["n"] == _raise_on:
                    raise RuntimeError(
                        f"scripted instance-A crash on run_fanout call #{_raise_on}"
                    )
                async for ev in _orig_fanout(self_ks, *a, **k):
                    yield ev

            _KS.run_fanout = _wrapped_fanout
            _restore_fanout = lambda: setattr(_KS, "run_fanout", _orig_fanout)
        else:
            _restore_fanout = lambda: None

        # Point the module-level SessionLocal (used by restore_non_terminal_runs +
        # resume_run for the workflow_runs query) at the SAME in-memory engine, so the
        # classifier/resume read the durable rows instance A wrote (StaticPool ⇒ one
        # shared connection). Closing this child session is a no-op for the data.
        import app.models.database as _db_mod

        _orig_session_local = _db_mod.SessionLocal
        if self.db_engine is not None:
            _shared_maker = sessionmaker(
                bind=self.db_engine, autocommit=False, autoflush=False,
                expire_on_commit=False,
            )
            _db_mod.SessionLocal = _shared_maker
            self._restore_session_local = (
                lambda: setattr(_db_mod, "SessionLocal", _orig_session_local)
            )
        else:
            self._restore_session_local = lambda: None

        self._restore = [
            _restore_fanout,
            self._restore_session_local,
            lambda: setattr(engine_mod, "compile_for_run", _orig_compile),
            lambda: setattr(engine_mod, "resolve_alias", _orig_alias),
            lambda: setattr(registry_mod, "get_pipeline_agents", _orig_gpa),
            lambda: setattr(factory_mod, "create_runner", _orig_cr),
            (lambda: setattr(engine_mod, "create_runner", _orig_engine_cr))
            if _orig_engine_cr is not None else (lambda: None),
            lambda: setattr(engine_mod, "ScopedStore", _orig_ss),
        ]
        return self

    def __exit__(self, *exc):
        for fn in self._restore:
            fn()
        for sid in self.spec_ids:
            self._spec_cache.pop(sid, None)
        return False

    def make_engine(self):
        from agents.execution_engine.engine import ExecutionEngine

        engine = ExecutionEngine()

        async def _fake_planner(user_message, pipeline_run_id, model_id, cancel_event, ptype="custom", **kw):
            return engine._default_planning_context(user_message), "PROCEED"

        engine._run_planner = _fake_planner  # type: ignore[assignment]

        async def _noop_store(*a, **k):
            return "artifact-id"

        engine._store.store = _noop_store  # type: ignore[assignment]

        async def _noop_gate(*a, **k):
            return
            yield  # pragma: no cover

        engine._run_review_gate = _noop_gate  # type: ignore[assignment]
        return engine


def _make_session():
    import app.models  # noqa: F401 — register models on Base.metadata
    from app.models.database import Base

    db = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=db)
    Session = sessionmaker(bind=db, autocommit=False, autoflush=False)
    return Session(), db


def _seed_workflow_run(session, run_id, *, owner, status, type_="sample_wave", input_="brief"):
    """Insert the workflow_runs row resume_run + the classifier read."""
    from app.models.workflow import WorkflowRun

    session.add(
        WorkflowRun(
            id=run_id, user_id=owner, owner_id=owner, workspace_id=None,
            status=status, type=type_, input=input_,
        )
    )
    session.commit()


# ===========================================================================
# (b) — the headline mid-wave resume: completed workers NOT re-invoked
# ===========================================================================


@pytest.mark.asyncio
async def test_midwave_resume_does_not_reinvoke_completed_workers():
    session, db_engine = _make_session()
    run_id = f"rr-{uuid.uuid4().hex[:8]}"
    owner = "rr-user"
    # The workflow_runs row resume_run reads (left non-terminal by the interrupt).
    _seed_workflow_run(session, run_id, owner=owner, status="generating")

    call_log: dict[str, int] = {}

    # ── Instance A: interrupted mid-wave — wave 0 completes, the 2nd run_fanout
    # (wave 1) crashes ON ENTRY so part_c/part_d never run on instance A ───────────
    with _ResumeHarness(
        session, call_log, fail_on=set(), db_engine=db_engine, raise_on_fanout_call=2
    ) as h:
        engine_a = h.make_engine()
        a_events: list[dict] = []
        # Instance A is interrupted mid-wave: the scripted worker raises on part_c/d, so
        # wave 1 fails. The engine surfaces this (a wave_failed/error event or a raised
        # exception) and leaves the run non-terminal — either way wave 0 is durably
        # complete. Tolerate both shapes (the dispatch loop may catch + surface, or
        # propagate) so the test asserts on the DURABLE state, not the control flow.
        try:
            async for ev in engine_a._execute_impl(
                agents=list(h.specs),
                user_message="Run the wave workflow.",
                pipeline_run_id=run_id,
                pipeline_type=_FIXTURE_ID,
                user_id=owner,
                gate_agent_ids=[],
            ):
                a_events.append(ev)
        except Exception:
            pass
        # Wave 1 must NOT have completed on instance A (the interrupt fired).
        assert any(e.get("type") == "wave_failed" for e in a_events) or not any(
            e.get("type") == "wave_completed"
            and e.get("data", {}).get("wave_index") == 1
            for e in a_events
        ), "instance A should have been interrupted before wave 1 completed"

    # Wave 0 completed before the crash: part_a + part_b workers each ran once.
    from app.models.wave_run import WaveRun

    wave0 = (
        session.query(WaveRun)
        .filter(WaveRun.run_id == run_id, WaveRun.wave_index == 0)
        .first()
    )
    assert wave0 is not None and wave0.status == "completed", (
        "instance A must have completed wave 0 before the mid-wave crash"
    )
    assert call_log.get("a", 0) >= 1 and call_log.get("b", 0) >= 1, (
        f"wave-0 workers should have run on instance A: {call_log}"
    )
    a_calls_a = call_log.get("a", 0)
    a_calls_b = call_log.get("b", 0)

    # ── Instance B: resume over the SAME durable DB, wave 1 now SUCCEEDS ───────────
    with _ResumeHarness(session, call_log, fail_on=set(), db_engine=db_engine) as h:
        engine_b = h.make_engine()
        await engine_b.resume_run(run_id)

    # The wave-0 workers (a/b) were NOT re-invoked by instance B (mid-wave skip).
    assert call_log.get("a", 0) == a_calls_a, (
        f"part_a worker was re-invoked on resume (mid-wave skip failed): {call_log}"
    )
    assert call_log.get("b", 0) == a_calls_b, (
        f"part_b worker was re-invoked on resume (mid-wave skip failed): {call_log}"
    )
    # Wave 1 workers (c/d) ran on resume and produced their files.
    assert call_log.get("c", 0) >= 1 and call_log.get("d", 0) >= 1, (
        f"wave-1 workers did not run on resume: {call_log}"
    )

    from app.agents.sandbox import RunSandbox

    root = RunSandbox(owner, run_id).root
    produced = {
        p.name for p in root.rglob("*.txt")
        if _PART_RE.fullmatch(p.name) and ".worktrees" not in p.parts
    }
    assert produced == {"part_a.txt", "part_b.txt", "part_c.txt", "part_d.txt"}, (
        f"resume did not complete every wave file: {sorted(produced)}"
    )
    session.close()


# ===========================================================================
# (a) — waiting_for_user still gates on user action (not auto-driven)
# ===========================================================================


@pytest.mark.asyncio
async def test_waiting_for_user_run_is_rearmed_not_driven():
    session, db_engine = _make_session()
    run_id = f"wf-{uuid.uuid4().hex[:8]}"
    _seed_workflow_run(session, run_id, owner="wf-user", status="waiting_for_user")

    with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h:
        engine = h.make_engine()
        resume_called = {"n": 0}

        async def _spy_resume(rid):
            resume_called["n"] += 1

        engine.resume_run = _spy_resume  # type: ignore[assignment]
        await engine.restore_non_terminal_runs()

    # branch (a): the waiting_for_user run is re-armed on its resume event, NOT
    # auto-driven through resume_run.
    assert resume_called["n"] == 0, "waiting_for_user must NOT be auto-resumed (branch a)"
    from app.models.workflow import WorkflowRun

    row = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    assert row.status == "waiting_for_user", "waiting_for_user status must be unchanged"
    session.close()


# ===========================================================================
# (c) — a stateless legacy run keeps the WR-05 abandoned→failed path
# ===========================================================================


@pytest.mark.asyncio
async def test_stateless_run_keeps_wr05_failed_path():
    session, db_engine = _make_session()
    run_id = f"st-{uuid.uuid4().hex[:8]}"
    # No durable run_events / artifact_refs / wave_runs ⇒ not resumable in-flight.
    _seed_workflow_run(session, run_id, owner="st-user", status="generating")

    with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h:
        engine = h.make_engine()
        resume_called = {"n": 0}

        async def _spy_resume(rid):
            resume_called["n"] += 1

        engine.resume_run = _spy_resume  # type: ignore[assignment]
        await engine.restore_non_terminal_runs()

    assert resume_called["n"] == 0, "a stateless run must NOT be auto-resumed (branch c)"
    from app.models.workflow import WorkflowRun

    row = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    assert row.status == "failed", "stateless run must hit the WR-05 abandoned→failed path"
    assert "WR-05" in (row.error or ""), f"WR-05 message missing: {row.error!r}"
    session.close()
