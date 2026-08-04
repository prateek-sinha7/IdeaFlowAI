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

# A SINGLE-WAVE plan (4 disjoint-target tasks, no deps) so all four workers fan out in
# ONE run_fanout call — the CR-03 parallel-order test needs partial completion WITHIN one
# wave (some workers terminal, some not). Dispatch order is t1,t2,t3,t4; on instance A the
# model RAISES for t1 and t3 (the leading + middle task) while t2 and t4 complete — proving
# completion order != dispatch order so the pre-fix leading-N prefix skip drops t1/t3.
_SINGLE_WAVE_PLAN = (
    "Here is the plan:\n\n```json\n"
    + _json.dumps(
        {
            "tasks": [
                {"id": "t1", "title": "Write A", "body": "Write the file part_a.txt with the content 'a'.", "targets": ["part_a.txt"]},
                {"id": "t2", "title": "Write B", "body": "Write the file part_b.txt with the content 'b'.", "targets": ["part_b.txt"]},
                {"id": "t3", "title": "Write C", "body": "Write the file part_c.txt with the content 'c'.", "targets": ["part_c.txt"]},
                {"id": "t4", "title": "Write D", "body": "Write the file part_d.txt with the content 'd'.", "targets": ["part_d.txt"]},
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


def _scripts_for(agent_id: str, plan: str = _TASK_PLAN):
    if agent_id == "sample-wave-plan":
        return [_ScriptedTurn(texts=[plan], usage=(20, 16))]
    return [_ScriptedTurn(texts=[f"{agent_id} default."], usage=(5, 3))]


class _ResumeHarness:
    """Patches compile/registry/factory/ScopedStore onto a SHARED in-memory session.

    The SAME session is reused across instance A and instance B so the durable
    wave_runs/subagent_runs/run_events persist across the simulated restart (Open Q3).
    """

    def __init__(self, session, call_log, fail_on, *, db_engine=None, raise_on_fanout_call=None, plan=_TASK_PLAN, clarify_mode="off"):
        self.session = session
        self.call_log = call_log
        self.fail_on = fail_on
        self.db_engine = db_engine
        # Compiled clarify.mode override (BUG-2 Cond A, quick-260720-ec4). Default
        # "off" keeps EVERY existing caller byte-identical (the historical hardcode);
        # "auto" makes the run park at clarify so the Stop/cancel path can be driven.
        self.clarify_mode = clarify_mode
        # The planner-emitted JSON plan (defaults to the 2-wave plan).
        self.plan = plan
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

        _clarify_mode = self.clarify_mode

        def _patched_compile(pt, _orig=_orig_compile, _mode=_clarify_mode):
            if pt == _FIXTURE_ID:
                compiled = _WC.compile(load_manifest(_FIXTURE_ID, _MANIFEST_HOME), _CAP)
                compiled.clarify.mode = _mode
                return compiled
            compiled = _orig(pt)
            compiled.clarify.mode = _mode
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
                _scripts_for(agent_id, self.plan),
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


def _seed_workflow_run(
    session, run_id, *, owner, status, type_="sample_wave", input_="brief",
    workspace_id=None,
):
    """Insert the workflow_runs row resume_run + the classifier read.

    ``workspace_id`` defaults to None (the historical shape — every existing caller is
    byte-unchanged). A non-null value is used by the RESUME-17 branch-(a) tests, which
    seed the run row AND its durable ``run_events`` under the SAME workspace so both the
    ``_is_resumable_in_flight`` gate and the branch-(a) open-gate read (both scoped on
    ``wr.workspace_id``) resolve them.
    """
    from app.models.workflow import WorkflowRun

    session.add(
        WorkflowRun(
            id=run_id, user_id=owner, owner_id=owner, workspace_id=workspace_id,
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
# CR-03 — parallel completion-order != dispatch order: the WHOLE in-flight wave
#         is re-run on resume (no leading-N prefix skip dropping incomplete tasks)
# ===========================================================================


class _ParallelOrderFakeRunner:
    """Reproduces CR-03 at the strategy boundary: a mid-wave resume where the COMPLETED
    workers (terminal ``subagent_runs``) do NOT correspond to the LEADING tasks by dispatch
    order.

    Durable state reported on resume:
      * wave 0 (step1) ``completed`` — its 2 workers skipped wholesale (correct);
      * wave 1 in-flight: 2 of its workers reached a terminal ``subagent_runs`` row, but —
        because waves run PARALLEL — they are NOT the first 2 tasks by dispatch order.

    The strategy records which task ids it actually re-fans-out per wave. The CORRECT
    behavior is to re-run the ENTIRE in-flight wave (all of wave 1's tasks). The pre-fix
    leading-N prefix skip would re-run only ``wave1[remaining:]`` — dropping the leading
    tasks even though THOSE are the ones that never completed.
    """

    def __init__(self, *, terminal_worker_count):
        # The number of terminal subagent_runs rows reported for step1 (wave0's 2 workers
        # + the workers that completed in wave1 before the crash). With wave0=2 tasks and 2
        # wave1 workers terminal, this is 4 — the pre-fix slice drops wave1's leading tasks.
        self._terminal = terminal_worker_count
        self.fanned_out: list[tuple[int, list[str]]] = []  # (wave_index, task_ids)
        self.recorded: list = []
        self.updated: list = []

    def latest_typed_content(self, _step):
        return ""

    async def read_wave_runs(self):
        # wave 0 completed for step1; wave 1 has a non-terminal (running) row.
        return [
            _FakeWaveRow("step1", 0, "completed"),
            _FakeWaveRow("step1", 1, "running"),
        ]

    async def read_subagent_runs(self):
        rows = []
        for _ in range(self._terminal):
            r = type("S", (), {})()
            r.parent_step = "step1"
            r.status = "complete"
            rows.append(r)
        return rows

    async def record_wave_run(self, *, step, wave_index, task_ids, status):
        self.recorded.append((step, wave_index, list(task_ids), status))
        # Capture the ACTUAL fanned-out task set for the wave dispatched here.
        self.fanned_out.append((wave_index, list(task_ids)))
        return f"row-{step}-{wave_index}"

    async def update_wave_run(self, row_id, *, status):
        self.updated.append((row_id, status))

    async def run_fanout(self, requests, ctx, *, step=None):
        if False:  # pragma: no cover — async generator
            yield {}


@pytest.mark.asyncio
async def test_midwave_resume_reruns_whole_inflight_wave_no_parallel_dropout():
    """CR-03 (WAVE-03 / data-loss): the in-flight wave is re-run WHOLE on resume — no
    leading-N prefix skip that drops incomplete parallel tasks.

    wave 0 (2 tasks) completed; wave 1 (2 tasks [t3,t4]) is in-flight with 2 terminal
    subagent_runs reported for the step (so ``_completed_worker_count`` = 4 = wave0's 2 +
    2). The pre-fix prefix logic accounts wave 0's 2 tasks, leaving ``_remaining = 2`` for
    wave 1 and slicing ``wave1[2:]`` = [] → wave 1 is SKIPPED ENTIRELY (its tasks never
    re-run) even though completion order != dispatch order, so an incomplete parallel task
    is dropped. The fix re-runs ALL of wave 1's tasks.

    FAILS on the pre-fix prefix skip (wave 1 not fanned out / fanned out with a truncated
    task set); PASSES once the whole in-flight wave is re-run.
    """
    from agents.capabilities.strategies.wave_scheduler import WaveSchedulerStrategy
    from agents.workflows.plan import Task

    strat = WaveSchedulerStrategy()
    runner = _ParallelOrderFakeRunner(terminal_worker_count=4)
    ctx = _Ctx(runner, is_resuming=True)
    step = _Step("step1")

    # wave 0 = [t1,t2] (disjoint, no deps); wave 1 = [t3 deps t1, t4 deps t2].
    tasks = [
        Task(id="t1", title="A", body="a", targets=["a.txt"]),
        Task(id="t2", title="B", body="b", targets=["b.txt"]),
        Task(id="t3", title="C", body="c", targets=["c.txt"], depends_on=["t1"]),
        Task(id="t4", title="D", body="d", targets=["d.txt"], depends_on=["t2"]),
    ]

    class _FakeParser:
        def parse(self, _text):
            return tasks

    strat._registry = type("R", (), {"resolve": lambda self, k, n: _FakeParser()})()
    step.task_source = type("TS", (), {"source_step": "plan", "parser": "json_tasks"})()

    _ = [ev async for ev in strat.run(step, ctx)]

    # Wave 0 (completed) must be SKIPPED (not re-fanned-out).
    wave0_fanouts = [tids for (widx, tids) in runner.fanned_out if widx == 0]
    assert not wave0_fanouts, (
        f"completed wave 0 should be skipped wholesale, but was re-run: {wave0_fanouts}"
    )
    # Wave 1 (in-flight) must be re-run WHOLE — BOTH t3 and t4, not a dispatch-order prefix.
    wave1_fanouts = [tids for (widx, tids) in runner.fanned_out if widx == 1]
    assert wave1_fanouts, (
        "in-flight wave 1 was SKIPPED entirely by the prefix skip — parallel-order data "
        f"loss (CR-03). recorded={runner.recorded}"
    )
    assert set(wave1_fanouts[0]) == {"t3", "t4"}, (
        f"in-flight wave 1 must re-run ALL its tasks (whole-wave re-run), not a prefix: "
        f"{wave1_fanouts[0]}"
    )


# ===========================================================================
# CR-04 — _completed_wave_indices is step-filtered: a second wave_scheduler step
#         resumes its OWN waves (no cross-step contamination)
# ===========================================================================


class _FakeWaveRow:
    def __init__(self, step, wave_index, status):
        self.step = step
        self.wave_index = wave_index
        self.status = status
        self.id = f"{step}:{wave_index}:{status}"


class _CrossStepFakeRunner:
    """A minimal ctx.runner capturing which waves a wave_scheduler step actually fans out.

    ``read_wave_runs`` returns rows for BOTH a first step (step1, waves 0,1 completed) and
    THIS step (step2, none completed). The pre-fix unfiltered comprehension treats step1's
    completed indices {0,1} as step2's own → skips step2's waves 0,1 wholesale. The
    step-filtered fix reads ONLY step2's rows (none) → runs every wave.
    """

    def __init__(self, this_step):
        self.this_step = this_step
        self.fanned_out_waves: list[int] = []
        self.recorded: list = []
        self.updated: list = []

    def latest_typed_content(self, _step):
        return _SINGLE_WAVE_PLAN  # unused (tasks injected directly in the test)

    async def read_wave_runs(self):
        return [
            _FakeWaveRow("step1", 0, "completed"),
            _FakeWaveRow("step1", 1, "completed"),
        ]

    async def read_subagent_runs(self):
        return []

    async def record_wave_run(self, *, step, wave_index, task_ids, status):
        self.recorded.append((step, wave_index, status))
        return f"row-{step}-{wave_index}"

    async def update_wave_run(self, row_id, *, status):
        self.updated.append((row_id, status))

    async def run_fanout(self, requests, ctx, *, step=None):
        # Record the wave (by the wave_index threaded via the current record_wave_run).
        self.fanned_out_waves.append(len(requests))
        if False:  # pragma: no cover — make this an async generator
            yield {}


class _Ctx:
    def __init__(self, runner, is_resuming):
        self.runner = runner
        self.is_resuming = is_resuming


class _Step:
    def __init__(self, agent_id):
        self.agent_id = agent_id
        self.task_source = None


@pytest.mark.asyncio
async def test_cross_step_does_not_skip_second_steps_waves():
    """CR-04: a wave_scheduler step must read ONLY its OWN step's completed waves.

    The runner reports step1's waves 0,1 as completed and step2 (THIS step) with none. The
    strategy (resuming) must fan out step2's waves regardless of step1's indices. FAILS on
    the pre-fix unfiltered ``_completed_wave_indices`` (which includes step1's {0,1} and
    skips step2's waves 0,1 wholesale).
    """
    from agents.capabilities.strategies.wave_scheduler import WaveSchedulerStrategy
    from agents.workflows.plan import Task

    strat = WaveSchedulerStrategy()
    runner = _CrossStepFakeRunner("step2")
    ctx = _Ctx(runner, is_resuming=True)
    step = _Step("step2")

    # Inject a 2-wave task list directly (t_a,t_b in wave 0; t_c deps t_a in wave 1).
    tasks = [
        Task(id="ta", title="A", body="a", targets=["a.txt"]),
        Task(id="tb", title="B", body="b", targets=["b.txt"]),
        Task(id="tc", title="C", body="c", targets=["c.txt"], depends_on=["ta"]),
    ]

    # Patch the parser-resolve + build_waves source by feeding tasks via a tiny parser.
    class _FakeParser:
        def parse(self, _text):
            return tasks

    strat._registry = type("R", (), {"resolve": lambda self, k, n: _FakeParser()})()
    step.task_source = type("TS", (), {"source_step": "plan", "parser": "json_tasks"})()

    events = [ev async for ev in strat.run(step, ctx)]

    # The strategy must have recorded a wave_run for step2's waves (NOT skipped them).
    step2_recorded = [r for r in runner.recorded if r[0] == "step2"]
    assert step2_recorded, (
        "step2's waves were SKIPPED — cross-step contamination from step1 (CR-04). "
        f"recorded={runner.recorded}"
    )
    # Both step2 waves (0 and 1) must have been dispatched.
    step2_wave_indices = {r[1] for r in step2_recorded}
    assert step2_wave_indices == {0, 1}, (
        f"step2 did not dispatch all its own waves (CR-04 cross-step skip): {step2_wave_indices}"
    )


# ===========================================================================
# WR-01 — the stale pre-crash running wave_runs row is flipped terminal on resume
# ===========================================================================


class _StaleRowFakeRunner:
    """Reports a STALE ``running`` wave_runs row for (this_step, wave 0) — the pre-crash row.

    On resume the strategy must FLIP it terminal (``superseded``) before recording the
    re-entry's row, so no non-terminal row lingers for (step, 0).
    """

    def __init__(self, this_step):
        self.this_step = this_step
        self.stale_row = _FakeWaveRow(this_step, 0, "running")
        self.recorded: list = []
        self.updated: list = []

    def latest_typed_content(self, _step):
        return ""

    async def read_wave_runs(self):
        return [self.stale_row]

    async def read_subagent_runs(self):
        return []

    async def record_wave_run(self, *, step, wave_index, task_ids, status):
        self.recorded.append((step, wave_index, status))
        return f"row-{step}-{wave_index}-new"

    async def update_wave_run(self, row_id, *, status):
        self.updated.append((row_id, status))

    async def run_fanout(self, requests, ctx, *, step=None):
        if False:  # pragma: no cover — async generator
            yield {}


@pytest.mark.asyncio
async def test_stale_running_wave_row_is_flipped_terminal_on_resume():
    """WR-01: the pre-crash ``running`` wave_runs row for the re-entered wave is flipped
    terminal (``superseded``) on resume — so the wave step is not permanently incomplete.

    FAILS on the pre-fix (the old running row is never updated; ``update_wave_run`` is only
    ever called with the NEW re-entry row's id, leaving the stale running row forever).
    """
    from agents.capabilities.strategies.wave_scheduler import WaveSchedulerStrategy
    from agents.workflows.plan import Task

    strat = WaveSchedulerStrategy()
    runner = _StaleRowFakeRunner("step1")
    ctx = _Ctx(runner, is_resuming=True)
    step = _Step("step1")

    tasks = [Task(id="ta", title="A", body="a", targets=["a.txt"])]

    class _FakeParser:
        def parse(self, _text):
            return tasks

    strat._registry = type("R", (), {"resolve": lambda self, k, n: _FakeParser()})()
    step.task_source = type("TS", (), {"source_step": "plan", "parser": "json_tasks"})()

    _ = [ev async for ev in strat.run(step, ctx)]

    # The stale running row (id of stale_row) must have been flipped to a terminal status.
    flipped = [u for u in runner.updated if u[0] == runner.stale_row.id]
    assert flipped, (
        "the stale pre-crash running wave_runs row was NOT flipped terminal (WR-01). "
        f"updates={runner.updated}"
    )
    assert flipped[0][1] == "superseded", (
        f"stale row should be flipped to 'superseded', got {flipped[0][1]}"
    )


# ===========================================================================
# CR-01 — resumed run_events continue PAST the durable tail (no seq collision)
# ===========================================================================


@pytest.mark.asyncio
async def test_resumed_events_seq_continues_past_durable_tail():
    """CR-01 (RESUME-03): resume_run must SEED its seq counter past the durable tail.

    The pre-restart run already persisted ``run_events`` at seq 1..N (plus the
    ``run_resuming`` marker at N+1). If ``resume_run`` re-uses ``itertools.count(1)``
    every resumed event collides with seq 1..N — so a client that sends ``after_seq=N``
    (its last pre-crash seq) never receives ANY resumed event (they all carry seq <= N).

    This test seeds run_events at seq 1..N under the run's REAL (owner, workspace)
    scope, drives ``resume_run`` over the same durable DB, then asserts EVERY event the
    resume driver persisted carries seq > N (strictly continues the monotonic per-run
    seq) — and that a reconnect-style ``read_events(after_seq=N)`` returns those resumed
    events (non-empty). FAILS on the pre-fix ``itertools.count(1)`` (resumed events get
    seq 1..M, colliding, and the after_seq=N read returns nothing new).
    """
    from agents.authz import ScopedStore
    from app.models.run_event import RunEvent

    session, db_engine = _make_session()
    run_id = f"sq-{uuid.uuid4().hex[:8]}"
    owner = "sq-user"
    workspace_id = "ws-sq"
    # The workflow_runs row resume_run reads (left non-terminal by the interrupt).
    _seed_workflow_run(session, run_id, owner=owner, status="generating")

    # ── Seed a durable tail: run_events at seq 1..N stamped with the REAL workspace_id
    # the engine sink would write under (so _recover_workspace_id finds it). ──────────
    pre_store = ScopedStore(owner_id=owner, workspace_id=workspace_id, session=session)
    N = 5
    for seq in range(1, N + 1):
        await pre_store.append_event(
            run_id, seq=seq, event_id=f"pre-{seq}",
            type=f"agent_chunk_{seq}", payload_json={"seq": seq},
        )
    session.commit()

    call_log: dict[str, int] = {}

    # ── Resume over the SAME durable DB. The resume driver re-drives the wave workflow
    # (no prior wave_runs ⇒ offset 0 ⇒ full re-drive) and persists its events. ─────────
    with _ResumeHarness(session, call_log, fail_on=set(), db_engine=db_engine) as h:
        engine_b = h.make_engine()
        await engine_b.resume_run(run_id)

    # Every run_events row whose event_id is NOT a pre-seeded one was persisted by the
    # resume driver — assert they ALL carry seq > N (continue the monotonic per-run seq).
    all_rows = (
        session.query(RunEvent)
        .filter(RunEvent.run_id == run_id)
        .order_by(RunEvent.seq.asc())
        .all()
    )
    pre_ids = {f"pre-{s}" for s in range(1, N + 1)}
    resumed = [r for r in all_rows if r.event_id not in pre_ids]
    assert resumed, "resume_run persisted no events to assert continuity on"
    assert all(r.seq > N for r in resumed), (
        f"resumed events must carry seq > {N} (durable-tail continuity); "
        f"got seqs {[r.seq for r in resumed]} (pre-fix itertools.count(1) collides)"
    )
    # min resumed seq is exactly N+1 (strictly contiguous from the tail).
    assert min(r.seq for r in resumed) == N + 1, (
        f"first resumed seq must be {N + 1} (max(seq)+1), got {min(r.seq for r in resumed)}"
    )

    # A reconnect-style read with after_seq=N returns the resumed tail (non-empty) — the
    # exact RESUME-03 contract a reconnecting FE (lastSeqRef=N) relies on.
    read_store = ScopedStore(owner_id=owner, workspace_id=workspace_id, session=session)
    missed = await read_store.read_events(run_id, after_seq=N)
    assert missed, "after_seq=N must deliver the resumed tail (it is empty pre-fix)"
    assert all(r.seq > N for r in missed)
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


# ===========================================================================
# (a) RESUME-17 — branch (a) fail→re-arm classification (PINNED A1)
# ===========================================================================


async def _seed_open_review_gate(session, run_id, owner, workspace_id, gate_key):
    """Seed a durable, still-OPEN ``review_gate_ready`` (no resolution) under the SAME
    ``(owner, workspace_id)`` the run row carries — so the owner+workspace-scoped
    ``read_events`` (scoped on ``wr.workspace_id`` in both ``_is_resumable_in_flight``
    and branch (a)) finds it → ``derive_open_gate`` → ``("review", gate_key)`` AND
    ``_is_resumable_in_flight`` is True (one durable ``run_events`` row is enough
    evidence). ``run_events.workspace_id`` is NOT NULL, so a real workspace is required."""
    from agents.authz import ScopedStore

    pre_store = ScopedStore(owner_id=owner, workspace_id=workspace_id, session=session)
    await pre_store.append_event(
        run_id, seq=1, event_id="rg-1", type="review_gate_ready",
        payload_json={"gate_key": gate_key},
    )
    session.commit()


@pytest.mark.asyncio
async def test_waiting_for_user_with_open_review_gate_is_rearmed_and_driver_spawned():
    """A compilable ``waiting_for_user`` run WITH a durable open ``review_gate_ready`` +
    resumable-in-flight → the store review event is ARMED and a DISTINCT re-arm driver
    (NOT ``resume_run`` — the KAN-88 spy) is spawned with the run_id BEFORE the row is
    left ``waiting_for_user``."""
    session, db_engine = _make_session()
    run_id = f"wr-{uuid.uuid4().hex[:8]}"
    owner = "wr-user"
    ws = "ws-wr"
    _seed_workflow_run(
        session, run_id, owner=owner, status="waiting_for_user", workspace_id=ws
    )
    gate_key = f"{run_id}:sample-wave-plan"
    await _seed_open_review_gate(session, run_id, owner, ws, gate_key)

    with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h:
        engine = h.make_engine()

        # Defensive: even if the driver were driven, it must never be resume_run.
        async def _spy_resume(rid):
            raise AssertionError("branch (a) must never spawn resume_run directly")

        engine.resume_run = _spy_resume  # type: ignore[assignment]

        # CHECKER FIX: spy ``_rearm_gate_run`` ITSELF — record the run_id SYNCHRONOUSLY
        # at coroutine-creation time (a plain def returning a real awaitable), NOT
        # resume_run's count, which only holds by create_task scheduling timing.
        spawned: dict = {"run_id": None, "n": 0}

        async def _noop():
            return

        def _spy_rearm(rid):
            spawned["run_id"] = rid
            spawned["n"] += 1
            return _noop()

        engine._rearm_gate_run = _spy_rearm  # type: ignore[assignment]

        await engine.restore_non_terminal_runs()
        import asyncio as _asyncio
        await _asyncio.sleep(0)  # let the scheduled driver task run to completion

        # The store review event was ARMED (created + not set) before the row was left
        # waiting_for_user — the arm-then-classify ordering (never a phantom-live row).
        assert engine._store.review_event_pending(gate_key), (
            "branch (a) must arm the review event before leaving waiting_for_user"
        )
        # The DISTINCT re-arm driver was spawned exactly once with the run_id.
        assert spawned["n"] == 1 and spawned["run_id"] == run_id, (
            f"the re-arm driver must be spawned once with the run_id: {spawned}"
        )

    from app.models.workflow import WorkflowRun

    row = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    assert row.status == "waiting_for_user", (
        "a re-armed run's status stays waiting_for_user (KAN-88 assertion)"
    )
    session.close()


@pytest.mark.asyncio
async def test_waiting_for_user_rearm_arm_failure_falls_back_to_wr05_fail(monkeypatch):
    """ARM-THEN-CLASSIFY fail-safe: a compilable ``waiting_for_user`` run WITH durable
    open-gate evidence whose store arm RAISES falls back to the WR-05 fail path (never a
    phantom-live row left waiting with no waiter)."""
    session, db_engine = _make_session()
    run_id = f"fs-{uuid.uuid4().hex[:8]}"
    owner = "fs-user"
    ws = "ws-fs"
    _seed_workflow_run(
        session, run_id, owner=owner, status="waiting_for_user", workspace_id=ws
    )
    gate_key = f"{run_id}:sample-wave-plan"
    await _seed_open_review_gate(session, run_id, owner, ws, gate_key)

    with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h:
        engine = h.make_engine()

        async def _boom(*a, **k):
            raise RuntimeError("scripted store-arm failure")

        # monkeypatch auto-restores the singleton store method after the test.
        monkeypatch.setattr(engine._store, "get_review_event", _boom)

        async def _spy_resume(rid):
            raise AssertionError("must not drive resume_run on the fail-safe path")

        engine.resume_run = _spy_resume  # type: ignore[assignment]
        await engine.restore_non_terminal_runs()

    from app.models.workflow import WorkflowRun

    row = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    assert row.status == "failed", (
        "an arm failure must fail-safe to the WR-05 fail path (never a phantom-live row)"
    )
    assert "WR-05-clarify" in (row.error or ""), f"WR-05-clarify missing: {row.error!r}"
    session.close()


@pytest.mark.asyncio
async def test_waiting_for_user_uncompilable_type_keeps_wr05_fail():
    """An UNCOMPILABLE / stateless-legacy ``waiting_for_user`` run (``compile_for_run``
    RAISES) keeps the byte-unchanged WR-05-clarify fail — the ONLY fail path for a
    waiting_for_user run (branch-(a) scope proof)."""
    session, db_engine = _make_session()
    run_id = f"uc-{uuid.uuid4().hex[:8]}"
    _seed_workflow_run(
        session, run_id, owner="uc-user", status="waiting_for_user",
        type_="__nonexistent_pipeline__",
    )

    with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h:
        engine = h.make_engine()
        resume_called = {"n": 0}

        async def _spy_resume(rid):
            resume_called["n"] += 1

        engine.resume_run = _spy_resume  # type: ignore[assignment]
        await engine.restore_non_terminal_runs()

    assert resume_called["n"] == 0, "an uncompilable run must NOT be auto-resumed"
    from app.models.workflow import WorkflowRun

    row = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    assert row.status == "failed", (
        "an uncompilable waiting_for_user run keeps the WR-05-clarify fail"
    )
    assert "WR-05-clarify" in (row.error or ""), f"WR-05-clarify missing: {row.error!r}"
    session.close()


# ===========================================================================
# RESUME-17 (49-02) — review-gate re-entry AT the gate phase (all five actions)
# ===========================================================================
#
# The crux is the CLASSIFIER: a produced-but-ungated step classifies "complete" at
# the produced-disjunct and a naive resume SKIPS the unresolved gate. The open-gate
# override in ``_first_incomplete_step`` returns the gated step (re-enter in GATE
# MODE); the ``gate_reentry`` sentinel then skips the model call, reconstructs the
# output from the persisted max-version ref (WR-02), and falls into the SHIPPED
# five-action consumer so approve/reject/edit/redo/update_specs all work post-restart.


async def _build_open_review_gate_fixture(session, *, gated_index=1, seed_gate=True):
    """Seed a durable single_shot run PARKED at a review gate on ``ordered_agents[gated_index]``.

    Three single_shot agents; agent[0] AND the gated agent BOTH produced their typed
    (``summary``) artifact — so BOTH are in ``produced_agents`` and the gated one would
    be SKIPPED by the produced-disjunct on HEAD. When ``seed_gate`` a durable
    ``review_gate_ready`` with ``gate_key = {run}:{gated agent}`` is appended (no
    resolution ⇒ ``derive_open_gate`` → ``("review", key)``). Returns
    ``(ordered_agents, compiled, tmp, gated_index)`` for a direct classifier call.
    """
    import types

    from agents.artifacts.graph import ArtifactRef
    from agents.authz import ScopedStore
    from agents.execution_engine.context import ExecutionContext
    from agents.workflows.plan import Step

    run_id = f"og-{uuid.uuid4().hex[:8]}"
    owner = "og-user"
    ws = "ws-og"
    _seed_workflow_run(
        session, run_id, owner=owner, status="waiting_for_user", workspace_id=ws
    )

    agent_ids = ["og-a", "og-b", "og-c"]
    gated_id = agent_ids[gated_index]
    pre_store = ScopedStore(owner_id=owner, workspace_id=ws, session=session)
    # agent[0] and the gated agent both produced their durable summary artifact.
    for produced_id in (agent_ids[0], gated_id):
        content = f"<output of {produced_id}>"
        await pre_store.write_ref(
            ArtifactRef(
                id=str(uuid.uuid4()), run_id=run_id, owner_id=owner, workspace_id=ws,
                kind="summary", producer_step=produced_id, producer_agent=produced_id,
                task_id=None, content=content, content_hash=_pb_hash(content),
                location=f"artifact_refs/{produced_id}", version=1,
            )
        )
    if seed_gate:
        await pre_store.append_event(
            run_id, seq=1, event_id="og-rg", type="review_gate_ready",
            payload_json={"gate_key": f"{run_id}:{gated_id}"},
        )
    session.commit()

    compiled = types.SimpleNamespace(
        steps=[Step(agent_id=a, strategy="single_shot") for a in agent_ids]
    )
    ordered_agents = [_IdSpec(a) for a in agent_ids]
    tmp = ExecutionContext(run_id=run_id, owner_id=owner, disk_principal="anon")
    tmp.workspace_id = ws
    tmp.scoped_store = ScopedStore(owner_id=owner, workspace_id=ws, session=session)
    return ordered_agents, compiled, tmp, gated_index


@pytest.mark.asyncio
async def test_open_review_gate_overrides_produced_disjunct():
    """RESUME-17 (RED on HEAD without the override): a produced-but-ungated step with an
    OPEN review gate is re-entered AT the gate (idx == gated step), NOT skipped past."""
    from agents.execution_engine.engine import ExecutionEngine

    session, db_engine = _make_session()
    ordered_agents, compiled, tmp, gated_index = await _build_open_review_gate_fixture(
        session
    )
    idx = await ExecutionEngine()._first_incomplete_step(tmp, ordered_agents, compiled)
    assert idx == gated_index, (
        f"an open review gate must re-enter the gated step (idx == {gated_index}); got "
        f"idx={idx} (HEAD skips it via the produced-agents disjunct → the gate is lost)"
    )
    session.close()


@pytest.mark.asyncio
async def test_open_gate_override_is_noop_without_review_gate():
    """The override is a NO-OP when no review gate is durable — the offset is the normal
    produced-disjunct result (byte-identical to HEAD)."""
    from agents.execution_engine.engine import ExecutionEngine

    session, db_engine = _make_session()
    ordered_agents, compiled, tmp, gated_index = await _build_open_review_gate_fixture(
        session, seed_gate=False
    )
    idx = await ExecutionEngine()._first_incomplete_step(tmp, ordered_agents, compiled)
    # agent[0] + gated agent produced; agent[2] did NOT → first incomplete is index 2.
    assert idx == 2, f"no open gate ⇒ the normal produced-disjunct offset (2); got {idx}"
    session.close()


class _FakeGateEventRow:
    """A minimal ``gate_events``-shaped row (the seed_helper reads step/gate/outcome)."""

    def __init__(self, step, gate, outcome):
        self.step = step
        self.gate = gate
        self.outcome = outcome


class _FakeGateRunner:
    """A KernelServices-shaped fake exposing the two audit methods the gate re-entry
    seeding + consumer reach (``read_gate_events`` / ``record_gate_event``)."""

    def __init__(self, rows=None):
        self._rows = list(rows or [])
        self.recorded: list[tuple] = []

    async def read_gate_events(self, run_id):
        return list(self._rows)

    async def record_gate_event(self, step, gate, outcome, detail=None):
        self.recorded.append((step, gate, outcome, detail))
        self._rows.append(_FakeGateEventRow(step, gate, outcome))
        return "gate-event-id"


def _seed_gate_reentry_ectx(run_id, spec, *, content="PERSISTED GATED OUTPUT", runner=None):
    """Return an ectx armed for a gate re-entry: one durable ``summary`` ref for the
    gated agent + the ``gate_reentry`` sentinel + ``gate_agent_ids`` so ``_should_gate``
    fires. ``scoped_store`` left None ⇒ ``_dual_write_artifact`` writes the in-memory
    graph only (the direct-unit path, mirroring test_redo_gate_safety._make_ectx)."""
    from tests.agents.test_redo_gate_safety import _make_ectx

    ectx = _make_ectx(run_id, gate_agent_ids=[spec.id])
    ectx.artifacts.write_ref(
        run_id=run_id, owner_id="anon", workspace_id="ws", kind="summary",
        producer_step=spec.id, producer_agent=spec.id, task_id=None,
        content=content, location=f"artifact_refs/{spec.id}",
    )
    ectx.runner = runner
    ectx.gate_reentry = {
        "agent_id": spec.id, "artifact_kind": "summary",
        "gate_key": f"{run_id}:{spec.id}",
    }
    return ectx


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["approve", "reject", "edit", "redo", "update_specs"])
async def test_gate_reentry_all_five_actions_post_restart(action):
    """RESUME-17 SC-3: on a post-restart gate re-entry the model call is SKIPPED, the
    output is reconstructed from the persisted ref (WR-02), and ALL FIVE gate actions
    behave IDENTICALLY to a live gate."""
    from agents.loader import load_agent_spec

    from tests.agents._scripted_model import ScriptedFakeChatModel
    from tests.agents.test_redo_gate_safety import (
        _EngineHarness,
        _drive_agent,
        _text_turn,
    )

    # domain-analyst: text-only, artifact kind "summary" (update_specs-eligible).
    spec = load_agent_spec("domain-analyst")
    scripts = {
        "approve":      [[]],
        "reject":       [[{"type": "_gate_rejected"}]],
        "edit":         [[{"type": "_gate_edited", "edited_content": "EDITED OUTPUT"}]],
        "redo":         [[{"type": "_gate_redo", "instructions": "redo it"}], []],
        "update_specs": [[{"type": "_gate_update_specs", "analysis_report": "revise"}], []],
    }[action]
    captured_outputs: list[str] = []
    gate_n = {"n": 0}

    async def _gate(pipeline_run_id, agent_id, agent_name, output, redoable=False,
                    update_specs_eligible=False, artifact_kind=None, cancel_event=None):
        i = gate_n["n"]
        gate_n["n"] += 1
        captured_outputs.append(output)
        yield {"type": "review_gate_ready", "data": {
            "gate_key": f"{pipeline_run_id}:{agent_id}",
            "redoable": redoable, "update_specs_eligible": update_specs_eligible,
        }}
        for ev in scripts[i]:
            yield ev

    sub_fired = {"n": 0}

    async def _fake_subpipeline(**kwargs):
        sub_fired["n"] += 1
        yield {"type": "_revision_analyze_output", "output": "revised analysis"}

    with _EngineHarness(lambda aid, idx: ScriptedFakeChatModel(_text_turn("redo output. "))) as h:
        h.engine._run_review_gate = _gate  # type: ignore[assignment]
        h.engine._run_spec_revision_sub_pipeline = _fake_subpipeline  # type: ignore[assignment]
        run_id = f"re-{action}"
        ectx = _seed_gate_reentry_ectx(run_id, spec)
        seeded_ref_id = ectx.artifacts.tree(run_id)[0].id
        results: list[dict] = [{"agent_id": spec.id, "output": "PERSISTED GATED OUTPUT"}]
        events = await _drive_agent(h.engine, spec, ectx, results, [spec])

    # The sentinel is CONSUMED (consume-once) and the gate reviewed the RECONSTRUCTED
    # persisted output — never a re-generated one (WR-02, model-skip).
    assert getattr(ectx, "gate_reentry", None) is None, "the gate_reentry sentinel was not consumed"
    assert captured_outputs and captured_outputs[0] == "PERSISTED GATED OUTPUT", (
        f"the gate must review the persisted max-version output (WR-02); got {captured_outputs!r}"
    )

    if action == "approve":
        assert not any(e["type"] == "pipeline_cancelled" for e in events)
        assert gate_n["n"] == 1
        assert results[-1]["output"] == "PERSISTED GATED OUTPUT"
    elif action == "reject":
        assert any(e["type"] == "pipeline_cancelled" for e in events), "reject must cancel"
    elif action == "edit":
        refs = [
            r for r in ectx.artifacts.tree(run_id)
            if r.producer_agent == spec.id and r.content == "EDITED OUTPUT"
        ]
        assert refs, "edit must dual-write a new versioned ref"
        assert refs[-1].derived_from == seeded_ref_id, (
            "the edit's derived_from must point at the superseded persisted version (lineage)"
        )
    elif action == "redo":
        assert gate_n["n"] == 2, "redo must re-open the gate after the fresh re-run"
        redo_threads = [t for t in h.thread_ids if t and ":redo" in t]
        assert redo_threads, f"redo must thread a fresh :redo{{N}} checkpoint: {h.thread_ids}"
    elif action == "update_specs":
        assert sub_fired["n"] == 1, "update_specs must FIRE the spec-revision sub-pipeline"
        assert gate_n["n"] == 2, "update_specs must re-open the gate with the new output"
        assert captured_outputs[1] == "revised analysis", (
            "the re-opened gate must review the sub-pipeline's new analysis output"
        )


@pytest.mark.asyncio
async def test_gate_reentry_redo_numbering_continues_past_pre_restart_redos():
    """RESUME-17 SC-3 (P23 replay class): a post-restart redo threads a ``:redo{N}`` id
    STRICTLY greater than any pre-restart redo. Two durable ``redo`` gate_events rows ⇒
    the seed is HIGH ⇒ the next redo threads ``{run}:{agent}:redo3`` (never reuses 1/2)."""
    from agents.loader import load_agent_spec

    from tests.agents._scripted_model import ScriptedFakeChatModel
    from tests.agents.test_redo_gate_safety import (
        _EngineHarness,
        _drive_agent,
        _text_turn,
    )

    spec = load_agent_spec("domain-analyst")
    gate_n = {"n": 0}

    async def _gate(pipeline_run_id, agent_id, agent_name, output, redoable=False,
                    update_specs_eligible=False, artifact_kind=None, cancel_event=None):
        i = gate_n["n"]
        gate_n["n"] += 1
        yield {"type": "review_gate_ready", "data": {
            "gate_key": f"{pipeline_run_id}:{agent_id}", "redoable": redoable,
        }}
        # First firing (the re-entry) requests a redo; the re-run's gate approves.
        if i == 0:
            yield {"type": "_gate_redo", "instructions": ""}

    # Two durable pre-restart redo audit rows for this agent.
    runner = _FakeGateRunner(rows=[
        _FakeGateEventRow(spec.id, "human", "redo"),
        _FakeGateEventRow(spec.id, "human", "redo"),
    ])

    with _EngineHarness(lambda aid, idx: ScriptedFakeChatModel(_text_turn("redo output. "))) as h:
        h.engine._run_review_gate = _gate  # type: ignore[assignment]
        run_id = "redo-num-run"
        ectx = _seed_gate_reentry_ectx(run_id, spec, runner=runner)
        results: list[dict] = [{"agent_id": spec.id, "output": "PERSISTED GATED OUTPUT"}]
        await _drive_agent(h.engine, spec, ectx, results, [spec])

    # Seed = max(2 durable redo rows, 1 version − 1) = 2 → the redo threads :redo3.
    redo_threads = [t for t in h.thread_ids if t and ":redo" in t]
    assert redo_threads == [f"{run_id}:{spec.id}:redo3"], (
        f"post-restart redo must continue past the 2 pre-restart redos (:redo3); got {redo_threads}"
    )


@pytest.mark.asyncio
async def test_gate_reentry_update_specs_writes_audit_row_a2():
    """A2: the inline update_specs consumer writes a best-effort ``gate_events`` audit row
    (symmetric with redo) so a post-restart spec_revision_attempt is durable-derivable."""
    from agents.loader import load_agent_spec

    from tests.agents._scripted_model import ScriptedFakeChatModel
    from tests.agents.test_redo_gate_safety import (
        _EngineHarness,
        _drive_agent,
        _text_turn,
    )

    spec = load_agent_spec("domain-analyst")
    gate_n = {"n": 0}

    async def _gate(pipeline_run_id, agent_id, agent_name, output, redoable=False,
                    update_specs_eligible=False, artifact_kind=None, cancel_event=None):
        i = gate_n["n"]
        gate_n["n"] += 1
        yield {"type": "review_gate_ready", "data": {
            "gate_key": f"{pipeline_run_id}:{agent_id}", "redoable": redoable,
        }}
        if i == 0:
            yield {"type": "_gate_update_specs", "analysis_report": "revise the specs"}

    async def _fake_subpipeline(**kwargs):
        yield {"type": "_revision_analyze_output", "output": "revised analysis"}

    runner = _FakeGateRunner()

    with _EngineHarness(lambda aid, idx: ScriptedFakeChatModel(_text_turn("x. "))) as h:
        h.engine._run_review_gate = _gate  # type: ignore[assignment]
        h.engine._run_spec_revision_sub_pipeline = _fake_subpipeline  # type: ignore[assignment]
        run_id = "us-audit-run"
        ectx = _seed_gate_reentry_ectx(run_id, spec, runner=runner)
        results: list[dict] = [{"agent_id": spec.id, "output": "PERSISTED GATED OUTPUT"}]
        await _drive_agent(h.engine, spec, ectx, results, [spec])

    us_rows = [r for r in runner.recorded if r[2] == "update_specs"]
    assert us_rows and us_rows[0][0] == spec.id and us_rows[0][1] == "human", (
        f"update_specs must write a best-effort audit row (step, human, update_specs); got {runner.recorded}"
    )


# ===========================================================================
# RESUME-05 — task_loop completeness is task-granular (partial build re-enters,
# completed build stays complete). Offline direct-classifier unit tests.
# ===========================================================================


def _pb_hash(content: str) -> str:
    import hashlib

    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class _IdSpec:
    """Minimal ``.id``-bearing spec — the classifier reads getattr(spec, 'id')."""

    def __init__(self, agent_id):
        self.id = agent_id


async def _build_partial_build_fixture(session, *, seed_task_ids):
    """Seed a durable partial/complete task_loop build and return the pieces the
    classifier consumes.

    Mirrors ``test_resumed_events_seq_continues_past_durable_tail`` (:798) but
    seeds ``artifact_refs`` (via ``pre_store.write_ref``) instead of ``run_events``:
      * one ``task_list`` plan ref with 3 ``## Task`` headings (heading_tasks → 3);
      * one ``html_file`` ref per ``seed_task_ids`` entry, all producer_agent
        "prototype-build" (exactly what ``persist_task_html`` dual-writes per task).

    Returns ``(ordered_agents, compiled, tmp, build_index)`` — call the classifier
    with ``await engine._first_incomplete_step(tmp, ordered_agents, compiled)``.
    """
    import types

    from agents.artifacts.graph import ArtifactRef
    from agents.authz import ScopedStore
    from agents.execution_engine.context import ExecutionContext
    from agents.workflows.plan import Step, TaskSource

    run_id = f"pb-{uuid.uuid4().hex[:8]}"
    owner = "pb-user"
    workspace_id = "ws-pb"
    _seed_workflow_run(session, run_id, owner=owner, status="generating")

    pre_store = ScopedStore(owner_id=owner, workspace_id=workspace_id, session=session)

    plan_content = "## Task 1: A\n## Task 2: B\n## Task 3: C"
    await pre_store.write_ref(
        ArtifactRef(
            id=str(uuid.uuid4()),
            run_id=run_id,
            owner_id=owner,
            workspace_id=workspace_id,
            kind="task_list",
            producer_step="prototype-plan",
            producer_agent="prototype-plan",
            task_id=None,
            content=plan_content,
            content_hash=_pb_hash(plan_content),
            location="tasks.md",
            version=1,
        )
    )
    for tid in seed_task_ids:
        body = f"<partial task {tid}>"
        await pre_store.write_ref(
            ArtifactRef(
                id=str(uuid.uuid4()),
                run_id=run_id,
                owner_id=owner,
                workspace_id=workspace_id,
                kind="html_file",
                producer_step="prototype-build",
                producer_agent="prototype-build",
                task_id=str(tid),
                content=body,
                content_hash=_pb_hash(body),
                location="prototype.html",
                version=1,
            )
        )
    session.commit()

    # Compiled plan: a single_shot plan step, the task_loop build step (the one under
    # test), and a trailing single_shot validate step — built from the REAL Step /
    # TaskSource dataclasses so ``strategy`` + ``task_source`` are populated (NOT the
    # ``_Step`` stub, which carries no ``strategy``).
    compiled = types.SimpleNamespace(
        steps=[
            Step(agent_id="prototype-plan", strategy="single_shot"),
            Step(
                agent_id="prototype-build",
                strategy="task_loop",
                task_source=TaskSource(
                    kind="parsed",
                    parser="heading_tasks",
                    source_step="prototype-plan",
                ),
            ),
            Step(agent_id="prototype-validate", strategy="single_shot"),
        ]
    )
    ordered_agents = [
        _IdSpec("prototype-plan"),
        _IdSpec("prototype-build"),
        _IdSpec("prototype-validate"),
    ]
    build_index = 1

    tmp = ExecutionContext(run_id=run_id, owner_id=owner, disk_principal="anon")
    tmp.workspace_id = workspace_id
    tmp.scoped_store = ScopedStore(
        owner_id=owner, workspace_id=workspace_id, session=session
    )
    return ordered_agents, compiled, tmp, build_index


@pytest.mark.asyncio
async def test_partial_task_loop_build_reenters_step_not_skipped():
    """RESUME-05 (RED on HEAD): a partial ``task_loop`` build MUST re-enter its step.

    The build persisted only task 1 of 3 (the crash point). ``persist_task_html``
    dual-writes an ``html_file`` ref with ``producer_agent="prototype-build"`` from
    task 1, so on HEAD ``produced_agents`` contains "prototype-build" and the :6002
    disjunct ``continue``s PAST the build → ``idx > build_index`` = the silent-skip
    data loss (truncated deliverable). After the strategy-conditional fix the
    task-granular count (distinct done 1 < expected 3) classifies the build INCOMPLETE
    → ``idx == build_index`` (the build is re-entered).
    """
    from agents.execution_engine.engine import ExecutionEngine

    session, db_engine = _make_session()
    ordered_agents, compiled, tmp, build_index = await _build_partial_build_fixture(
        session, seed_task_ids=["1"]
    )
    engine = ExecutionEngine()

    idx = await engine._first_incomplete_step(tmp, ordered_agents, compiled)

    assert idx == build_index, (
        f"a partial task_loop build (1 of 3 tasks) must re-enter its step "
        f"(idx == {build_index}); got idx={idx} (HEAD silently skips it via the "
        f"produced_agents membership at :6002 → deliverable truncation)"
    )
    session.close()


@pytest.mark.asyncio
async def test_completed_task_loop_build_stays_complete_no_rerun():
    """RESUME-05 (companion, guards over-correction): a fully-completed ``task_loop``
    build MUST still classify COMPLETE — the classifier returns an index PAST the
    build, so it is not re-entered (no infinite re-run).

    All three build task_ids ("1","2","3") are durable. Distinct done 3 >= expected 3
    → COMPLETE. Holds BOTH before and after the fix (before: coincidentally via the
    :6002 membership; after: via the count check).
    """
    from agents.execution_engine.engine import ExecutionEngine

    session, db_engine = _make_session()
    ordered_agents, compiled, tmp, build_index = await _build_partial_build_fixture(
        session, seed_task_ids=["1", "2", "3"]
    )
    engine = ExecutionEngine()

    idx = await engine._first_incomplete_step(tmp, ordered_agents, compiled)

    assert idx > build_index, (
        f"a fully-completed task_loop build (3 of 3 tasks) must NOT be re-entered "
        f"(idx > {build_index}); got idx={idx} (over-correction / infinite re-run)"
    )
    session.close()


# ===========================================================================
# RESUME-08 (Plan 46-03) — durable → disk re-materialization + merge re-entry
# ===========================================================================
#
# The missing DISK half of resume. ``_hydrate_artifacts_from_store`` restores the
# durable ``artifact_refs`` into the in-memory graph ONLY; the fresh ``RunSandbox``
# on disk stays empty, so a resumed strategy re-reading the sandbox sees nothing.
# ``_rematerialize_artifacts_to_disk(ectx, sandbox)`` walks the latest durable
# file-backed refs (by ``location``, ``max(version)``) and writes their content back
# onto the sandbox — reconstructed from ``artifact_refs``, NEVER git (POR §3.2).
#
# These are offline seed-durable-then-invoke tests (register 11-05: fan-out isolated
# writes are live-only; seed the durable rows directly and drive the transform). On
# HEAD (no such method) they FAIL — the method does not exist / files stay absent.


async def _build_rematerialize_ctx(session, tmp_path, *, owner="rm-user", ws="ws-rm"):
    """Return ``(ectx, sandbox, store, run_id)`` for a direct re-materialization call.

    A durable ``workflow_runs`` row + a real ``ScopedStore`` over ``session`` + a
    resume ``ExecutionContext`` carrying that store and a FRESH empty ``RunSandbox``
    (mirrors ``_build_capture_runner`` in test_per_task_capture.py, the 46-02 twin).
    """
    from agents.authz import ScopedStore
    from agents.execution_engine.context import ExecutionContext
    from app.agents.sandbox import RunSandbox

    run_id = f"rm-{uuid.uuid4().hex[:8]}"
    _seed_workflow_run(session, run_id, owner=owner, status="generating")

    ectx = ExecutionContext(run_id=run_id, owner_id=owner, disk_principal=owner)
    ectx.workspace_id = ws
    ectx.scoped_store = ScopedStore(owner_id=owner, workspace_id=ws, session=session)

    sandbox = RunSandbox(owner, run_id, runs_root=str(tmp_path))
    sandbox.ensure()
    return ectx, sandbox, ectx.scoped_store, run_id


async def _seed_ref(store, *, run_id, owner, ws, kind, location, content, version,
                    producer_agent="prototype-build", task_id=None):
    from agents.artifacts.graph import ArtifactRef

    await store.write_ref(
        ArtifactRef(
            id=str(uuid.uuid4()),
            run_id=run_id,
            owner_id=owner,
            workspace_id=ws,
            kind=kind,
            producer_step=producer_agent,
            producer_agent=producer_agent,
            task_id=task_id,
            content=content,
            content_hash=_pb_hash(content),
            location=location,
            version=version,
        ),
        force_db_version=True,
    )


@pytest.mark.asyncio
async def test_rematerialize_restores_durable_files_to_disk(tmp_path):
    """RESUME-08 (RED on HEAD): the latest durable file-backed refs (``html_file`` +
    ``file_bundle`` sibling) are written back onto the fresh ``RunSandbox``; the
    max-version content wins; ``.uploads/`` and non-file kinds NEVER land on disk.

    On HEAD ``_rematerialize_artifacts_to_disk`` does not exist → AttributeError.
    """
    from agents.execution_engine.engine import ExecutionEngine

    session, _db = _make_session()
    owner, ws = "rm-user", "ws-rm"
    ectx, sandbox, store, run_id = await _build_rematerialize_ctx(
        session, tmp_path, owner=owner, ws=ws
    )

    # Declared deliverable (html_file) + a sibling (file_bundle).
    await _seed_ref(store, run_id=run_id, owner=owner, ws=ws, kind="html_file",
                    location="prototype.html", content="<html>declared</html>", version=1)
    await _seed_ref(store, run_id=run_id, owner=owner, ws=ws, kind="file_bundle",
                    location="nested/part_b.md", content="# sibling B", version=1)
    # Two versions of the SAME location — only the latest content must be written.
    await _seed_ref(store, run_id=run_id, owner=owner, ws=ws, kind="file_bundle",
                    location="notes.txt", content="v1 stale", version=1)
    await _seed_ref(store, run_id=run_id, owner=owner, ws=ws, kind="file_bundle",
                    location="notes.txt", content="v2 latest", version=2)
    # .uploads/ (Phase-47 fence) + a non-file kind (spec) — neither may reach disk.
    await _seed_ref(store, run_id=run_id, owner=owner, ws=ws, kind="file_bundle",
                    location=".uploads/doc.txt", content="uploaded", version=1)
    await _seed_ref(store, run_id=run_id, owner=owner, ws=ws, kind="spec",
                    location="spec.md", content="graph-only spec", version=1,
                    producer_agent="prototype-specify")
    session.commit()

    engine = ExecutionEngine()
    await engine._rematerialize_artifacts_to_disk(ectx, sandbox)

    assert sandbox.read("prototype.html") == "<html>declared</html>"
    assert sandbox.read("nested/part_b.md") == "# sibling B"
    # max-version wins.
    assert sandbox.read("notes.txt") == "v2 latest"
    # .uploads/ NEVER re-materialized.
    assert sandbox.read(".uploads/doc.txt") is None
    # A non-file kind (spec) is graph-only — not written to disk.
    assert sandbox.read("spec.md") is None

    session.close()


@pytest.mark.asyncio
async def test_midwave_merge_reentry_rematerializes_fragments(tmp_path):
    """RESUME-08 (RED on HEAD): a crash between fragment-persist and the per-wave
    merge leaves the wave's ``wave_runs`` row ``running`` and the fragments durable
    but off-disk. Re-materialization writes those fragments back so the EXISTING
    wave re-run (``run_fanout``→``_merge_fragments``) merges over the recovered
    fragments — no second merge implementation.

    On HEAD ``_rematerialize_artifacts_to_disk`` does not exist → AttributeError.
    """
    from agents.execution_engine.engine import ExecutionEngine

    session, _db = _make_session()
    owner, ws = "rm-user", "ws-rm"
    ectx, sandbox, store, run_id = await _build_rematerialize_ctx(
        session, tmp_path, owner=owner, ws=ws
    )

    # Two workers' fragments persisted BEFORE the merge (write_fragment_artifact
    # uses kind="file_bundle", task_id=str(worker_index)).
    await _seed_ref(store, run_id=run_id, owner=owner, ws=ws, kind="file_bundle",
                    location="part_a.txt", content="fragment-a", version=1,
                    producer_agent="wave-worker", task_id="0")
    await _seed_ref(store, run_id=run_id, owner=owner, ws=ws, kind="file_bundle",
                    location="part_b.txt", content="fragment-b", version=1,
                    producer_agent="wave-worker", task_id="1")
    # The wave_runs row is still `running` — the merge never ran (the discriminator).
    row_id = await store.record_wave_run(
        run_id, step="build", wave_index=0, task_ids=["t1", "t2"], status="running"
    )
    session.commit()

    # Sanity: the wave is durably unmerged (running) — merge re-entry is warranted.
    waves = await store.read_wave_runs(run_id)
    assert [w.status for w in waves] == ["running"]

    engine = ExecutionEngine()
    await engine._rematerialize_artifacts_to_disk(ectx, sandbox)

    # Both workers' fragments are back on disk → _fragment_files can pick them up
    # for the re-run merge.
    assert sandbox.read("part_a.txt") == "fragment-a"
    assert sandbox.read("part_b.txt") == "fragment-b"
    # The merged base is reconstructable from the recovered fragments.
    merged = "".join(sandbox.read(loc) for loc in ("part_a.txt", "part_b.txt"))
    assert merged == "fragment-afragment-b"

    session.close()


@pytest.mark.asyncio
async def test_task_loop_reconcile_boundary_version(tmp_path):
    """RESUME-16 cumulative (Pitfall 4): a p>0 common-prefix boundary restores the
    deliverable to the boundary task's version — NOT the global max (which embeds the
    deleted/edited-suffix task's work). Restore-by-max(version) PER boundary task_id
    handles the fix-loop re-persist multiplicity (Pitfall 9).
    """
    from agents.capabilities import task_identity
    from agents.execution_engine.engine import ExecutionEngine

    session, _db = _make_session()
    owner, ws = "rm-user", "ws-rm"
    ectx, sandbox, store, run_id = await _build_rematerialize_ctx(
        session, tmp_path, owner=owner, ws=ws
    )

    keyA = task_identity.compute_task_key("u", "alpha", 0)
    keyB = task_identity.compute_task_key("u", "bravo", 0)  # the boundary task
    keyC = task_identity.compute_task_key("u", "charlie", 0)  # post-boundary (deleted)

    # All at ONE location ("prototype.html"), produced by the build agent. The boundary
    # task B has TWO versions (fix-loop re-persist) → restore its MAX (v4). C is the
    # post-boundary task whose version (v5) would win under global-max.
    await _seed_ref(store, run_id=run_id, owner=owner, ws=ws, kind="html_file",
                    location="prototype.html", content="after-A", version=1, task_id=keyA)
    await _seed_ref(store, run_id=run_id, owner=owner, ws=ws, kind="html_file",
                    location="prototype.html", content="after-B-run", version=2, task_id=keyB)
    await _seed_ref(store, run_id=run_id, owner=owner, ws=ws, kind="html_file",
                    location="prototype.html", content="after-C-DELETED", version=3, task_id=keyC)
    await _seed_ref(store, run_id=run_id, owner=owner, ws=ws, kind="html_file",
                    location="prototype.html", content="after-B-FIXED", version=4, task_id=keyB)
    await _seed_ref(store, run_id=run_id, owner=owner, ws=ws, kind="html_file",
                    location="prototype.html", content="after-C-DELETED-FIXED", version=5, task_id=keyC)
    session.commit()

    engine = ExecutionEngine()
    await engine._rematerialize_artifacts_to_disk(
        ectx, sandbox,
        boundary_by_agent={
            "prototype-build": {"restore_nothing": False, "boundary_task_id": keyB}
        },
    )

    assert sandbox.read("prototype.html") == "after-B-FIXED", (
        "boundary re-materialization must restore the boundary task B's MAX-version file "
        "(after-B-FIXED), NOT the global-max C version which embeds deleted-task work"
    )
    session.close()


@pytest.mark.asyncio
async def test_task_loop_reconcile_first_task_clean_basis(tmp_path):
    """RESUME-16 cumulative p==0: when the FIRST current task diverges the boundary
    restores NOTHING — no prior deliverable version reaches disk, so the build starts
    from a clean/empty basis and every current task re-runs. NEVER a negative-index
    (current_keys[-1]) wrong-restore.
    """
    from agents.capabilities import task_identity
    from agents.execution_engine.engine import ExecutionEngine

    session, _db = _make_session()
    owner, ws = "rm-user", "ws-rm"
    ectx, sandbox, store, run_id = await _build_rematerialize_ctx(
        session, tmp_path, owner=owner, ws=ws
    )

    keyA = task_identity.compute_task_key("u", "alpha", 0)
    keyB = task_identity.compute_task_key("u", "bravo", 0)

    # Prior completed versions exist on the durable store — global-max would restore
    # "after-B". The p==0 restore-nothing signal must materialize NONE of them.
    await _seed_ref(store, run_id=run_id, owner=owner, ws=ws, kind="html_file",
                    location="prototype.html", content="after-A", version=1, task_id=keyA)
    await _seed_ref(store, run_id=run_id, owner=owner, ws=ws, kind="html_file",
                    location="prototype.html", content="after-B", version=2, task_id=keyB)
    session.commit()

    engine = ExecutionEngine()
    await engine._rematerialize_artifacts_to_disk(
        ectx, sandbox,
        boundary_by_agent={
            "prototype-build": {"restore_nothing": True, "boundary_task_id": None}
        },
    )

    assert sandbox.read("prototype.html") is None, (
        "p==0 restore-nothing must write NO prior deliverable version to disk (clean "
        "basis); every current task re-runs from empty"
    )
    session.close()


# ── RESUME-16 independent (wave) — orphan-fragment exclusion (48-03) ─────────
# On a resume-after-edit of a wave step, a CONFIDENTLY-orphaned fragment (its owning
# worker's key is MAPPABLE via subagent_runs but ABSENT from the current list) must be
# excluded at the re-materialization gate so it reaches NEITHER _merge_fragments NOR the
# terminal serialized_sandbox assembly (both read only disk) — merge impls untouched,
# no row deleted (T-48-04). The fragment→key join is PINNED to three cases:
#   (1) resolvable + key ∈ allow-set → RESTORE
#   (2) resolvable + key ∉ allow-set → EXCLUDE (confidently orphaned)
#   (3) unresolvable/ambiguous       → RESTORE (fail-safe keep, T-48-05)


@pytest.mark.asyncio
async def test_wave_reconcile_orphan_excluded(tmp_path):
    """RESUME-16 independent (T-48-04): a CONFIDENTLY-orphaned wave fragment — its
    owning worker's key is MAPPABLE (its subagent_runs.task_id resolves) but ABSENT
    from the current (edited) task list — is EXCLUDED from disk (hence from
    _merge_fragments AND the terminal serialized_sandbox assembly, both read only
    disk). The surviving in-list fragment IS restored. Zero merge-impl edit; no row
    deleted (rows only read).
    """
    from agents.capabilities import task_identity
    from agents.execution_engine.engine import ExecutionEngine

    session, _db = _make_session()
    owner, ws = "rm-user", "ws-rm"
    ectx, sandbox, store, run_id = await _build_rematerialize_ctx(
        session, tmp_path, owner=owner, ws=ws
    )

    key_live = task_identity.compute_task_key("u", "alpha", 0)    # in the current list
    key_orphan = task_identity.compute_task_key("u", "bravo", 0)  # deleted from the list

    # Two workers' fragments persisted BEFORE the merge (write_fragment_artifact:
    # kind="file_bundle", producer_step=<wave step agent>, task_id=str(worker_index)).
    await _seed_ref(store, run_id=run_id, owner=owner, ws=ws, kind="file_bundle",
                    location="part_a.txt", content="fragment-a", version=1,
                    producer_agent="build-wave", task_id="0")
    await _seed_ref(store, run_id=run_id, owner=owner, ws=ws, kind="file_bundle",
                    location="part_b.txt", content="fragment-b-ORPHAN", version=1,
                    producer_agent="build-wave", task_id="1")
    # subagent_runs give the worker_index → key join: worker 0 → live key (present),
    # worker 1 → orphan key (absent from the current list = confidently orphaned).
    await store.record_subagent_run(
        run_id, parent_step="build-wave", worker_agent="w", depth=1,
        isolation="shared_read", status="complete", worker_index=0, task_id=key_live,
    )
    await store.record_subagent_run(
        run_id, parent_step="build-wave", worker_agent="w", depth=1,
        isolation="shared_read", status="complete", worker_index=1, task_id=key_orphan,
    )
    session.commit()

    engine = ExecutionEngine()
    await engine._rematerialize_artifacts_to_disk(
        ectx, sandbox,
        wave_allow_by_step={"build-wave": {key_live}},  # only the live key survives
    )

    assert sandbox.read("part_a.txt") == "fragment-a", (
        "the in-list (mappable + present) fragment must be restored to disk"
    )
    assert sandbox.read("part_b.txt") is None, (
        "the confidently-orphaned fragment (mappable but ABSENT from the current list) "
        "must NOT reach disk → excluded from merge + assembly with zero merge edits"
    )
    session.close()


@pytest.mark.asyncio
async def test_wave_reconcile_unmappable_kept(tmp_path):
    """RESUME-16 independent (T-48-05 fail-safe): a wave fragment whose owning-worker
    key is UNRESOLVABLE (no subagent_run maps its worker_index → a key — e.g. a legacy
    positional row / missing subagent_run) is RESTORED (fail-safe keep), DISTINCT from
    the confidently-orphaned exclusion. Ambiguity → keep (a wasteful-but-correct
    include), never a wrong exclude of live work.
    """
    from agents.capabilities import task_identity
    from agents.execution_engine.engine import ExecutionEngine

    session, _db = _make_session()
    owner, ws = "rm-user", "ws-rm"
    ectx, sandbox, store, run_id = await _build_rematerialize_ctx(
        session, tmp_path, owner=owner, ws=ws
    )

    key_live = task_identity.compute_task_key("u", "alpha", 0)

    # A fragment whose worker_index (2) has NO subagent_run to map it → a key: the join
    # is UNRESOLVABLE. Under the three-way rule this is fail-safe RESTORED (kept).
    await _seed_ref(store, run_id=run_id, owner=owner, ws=ws, kind="file_bundle",
                    location="legacy.txt", content="fragment-legacy", version=1,
                    producer_agent="build-wave", task_id="2")
    # A live worker exists (index 0 → key_live) but NONE maps worker_index 2.
    await store.record_subagent_run(
        run_id, parent_step="build-wave", worker_agent="w", depth=1,
        isolation="shared_read", status="complete", worker_index=0, task_id=key_live,
    )
    session.commit()

    engine = ExecutionEngine()
    await engine._rematerialize_artifacts_to_disk(
        ectx, sandbox,
        wave_allow_by_step={"build-wave": {key_live}},
    )

    assert sandbox.read("legacy.txt") == "fragment-legacy", (
        "an UNRESOLVABLE fragment→key join must be fail-safe RESTORED (kept) — distinct "
        "from the confidently-orphaned exclusion; never a wrong exclude of live work"
    )
    session.close()


# ===========================================================================
# RESUME-09 (Plan 46-04) — per-task / per-worker SKIP CURSOR
#
# The KERNEL computes the completed-identity set per step from the run's own
# durable rows and threads it via the dormant ``ExecutionContext``
# ``resume_completed_task_ids`` field; the strategies SKIP the completed
# identities. The AGENT never decides the skip set (INV-1); re-invocation of the
# remaining work stays on the same run_agent/run_fanout paths (INV-13). Fail-safe
# direction is RE-RUN: any read failure / ambiguity leaves the cursor None so
# nothing is skipped.
# ===========================================================================


_THREE_TASK_PLAN = (
    "## Task 1: Shell\nBuild the HTML shell.\n\n"
    "## Task 2: Dashboard\nAdd the dashboard page.\n\n"
    "## Task 3: Reports\nAdd the reports page.\n"
)


@pytest.mark.asyncio
async def test_task_loop_skips_completed_tasks_on_resume_cursor():
    """RESUME-09 (RED on HEAD): task_loop SKIPS the completed task_nums named by the
    kernel-stamped ``resume_completed_task_ids`` cursor instead of re-dispatching from
    task 1.

    With tasks 1+2 of the build step marked complete + a 3-task plan, ONLY task 3
    reaches ``run_agent``; tasks 1-2 are skipped (their files are already on disk from
    the Plan 46-03 re-materialization, so task 3's skeleton read stays coherent). On
    HEAD the loop always starts at task 1 (no cursor read) → all 3 dispatched → RED.
    """
    from types import SimpleNamespace

    from agents.capabilities import task_identity
    from agents.capabilities.strategies.task_loop import TaskLoopStrategy
    from agents.capabilities.task_parsers.heading_tasks import HeadingTasksParser
    from agents.workflows.plan import Step, TaskSource
    from tests.agents.test_strategies import _FakeRunner, _FakeSandbox

    sandbox = _FakeSandbox(files={"prototype.html": "<html></html>"})
    runner = _FakeRunner(
        agent_events=[{"type": "agent_chunk", "data": {"text": "."}}],
        typed_content={"prototype-plan": _THREE_TASK_PLAN},
        sandbox=sandbox,
    )
    # RESUME-14: the cursor now carries content-addressed task_keys (not positions).
    # Compute the SAME keys the strategy will (heading parse + "u-fake" upstream, the
    # _FakeRunner.upstream_context_hash value) and mark tasks 1+2 completed.
    _tasks = HeadingTasksParser().parse(_THREE_TASK_PLAN)
    _ords = task_identity.occurrence_ordinals(_tasks)
    _keys = [
        task_identity.compute_task_key(
            "u-fake", task_identity.normalize_task_content(t), _ords[i]
        )
        for i, t in enumerate(_tasks)
    ]
    # KERNEL-stamped cursor: tasks 1+2 of the build step already completed pre-crash.
    # RESUME-16 cumulative: the task_loop skip is now the ORDER-based common-prefix rule
    # (``resume_completed_ordered`` = completed keys in build order), not set-membership.
    # Here [k0,k1] is a clean prefix of current [k0,k1,k2] → p=2 → skip 1+2, run task 3.
    ctx = SimpleNamespace(
        runner=runner,
        resume_completed_ordered={"prototype-build": [_keys[0], _keys[1]]},
    )
    step = Step(
        agent_id="prototype-build",
        strategy="task_loop",
        task_source=TaskSource(
            kind="parsed", parser="heading_tasks", source_step="prototype-plan"
        ),
    )

    _ = [ev async for ev in TaskLoopStrategy().run(step, ctx)]

    dispatched = [c["task_number"] for c in runner.run_agent_calls]
    assert dispatched == [3], (
        "task_loop must SKIP the completed tasks 1+2 (resume cursor) and dispatch ONLY "
        f"task 3 through run_agent; got task_nums {dispatched}"
    )


# ── RESUME-16 cumulative common-prefix reconcile (48-02) ────────────────────

_PLAN_ABC = (
    "## Task 1: Alpha\nBuild the alpha section.\n\n"
    "## Task 2: Bravo\nAdd the bravo section.\n\n"
    "## Task 3: Charlie\nAdd the charlie section.\n"
)
# Bravo DELETED in the middle; Charlie re-numbered to Task 2 (the ordinal is stripped
# in normalization, so Charlie's key is identical across the renumber).
_PLAN_A_C = (
    "## Task 1: Alpha\nBuild the alpha section.\n\n"
    "## Task 2: Charlie\nAdd the charlie section.\n"
)


def _heading_keys(plan_text: str) -> list[str]:
    from agents.capabilities import task_identity
    from agents.capabilities.task_parsers.heading_tasks import HeadingTasksParser

    tasks = HeadingTasksParser().parse(plan_text)
    ords = task_identity.occurrence_ordinals(tasks)
    return [
        task_identity.compute_task_key(
            "u-fake", task_identity.normalize_task_content(t), ords[i]
        )
        for i, t in enumerate(tasks)
    ]


@pytest.mark.asyncio
async def test_task_loop_reconcile_common_prefix():
    """RESUME-16 cumulative: a mid-list DELETE re-runs the divergence suffix — NOT
    set-membership. Completed [A,B,C]; current [A,C] (B deleted). Position 0 A==A ✓;
    position 1 C != B → p=1 → skip only A, re-run C (B's forward work never merged).
    """
    from types import SimpleNamespace

    from agents.capabilities.strategies.task_loop import TaskLoopStrategy
    from agents.workflows.plan import Step, TaskSource
    from tests.agents.test_strategies import _FakeRunner, _FakeSandbox

    keys_abc = _heading_keys(_PLAN_ABC)  # [keyA, keyB, keyC]

    sandbox = _FakeSandbox(files={"prototype.html": "<html></html>"})
    runner = _FakeRunner(
        agent_events=[{"type": "agent_chunk", "data": {"text": "."}}],
        typed_content={"prototype-plan": _PLAN_A_C},  # CURRENT (edited) list = [A, C]
        sandbox=sandbox,
    )
    # Completed keys in build ORDER = [A, B, C] (all three ran before the edit).
    ctx = SimpleNamespace(
        runner=runner,
        resume_completed_ordered={"prototype-build": keys_abc},
    )
    step = Step(
        agent_id="prototype-build",
        strategy="task_loop",
        task_source=TaskSource(
            kind="parsed", parser="heading_tasks", source_step="prototype-plan"
        ),
    )

    _ = [ev async for ev in TaskLoopStrategy().run(step, ctx)]

    dispatched = [c["task_number"] for c in runner.run_agent_calls]
    assert dispatched == [2], (
        "common-prefix reconcile must SKIP task 1 (A, unchanged prefix) and re-run ONLY "
        f"task 2 (C — its predecessor B was deleted, so its basis changed); got {dispatched}"
    )


@pytest.mark.asyncio
async def test_task_loop_reconcile_first_task_divergence_runs_all():
    """RESUME-16 cumulative p==0: when the FIRST current task diverges (first task
    edited/deleted or a task inserted at head) the common prefix is EMPTY → p=0 → every
    current task re-runs from a clean basis. NEVER a negative-index skip.
    """
    from types import SimpleNamespace

    from agents.capabilities.strategies.task_loop import TaskLoopStrategy
    from agents.workflows.plan import Step, TaskSource
    from tests.agents.test_strategies import _FakeRunner, _FakeSandbox

    keys_abc = _heading_keys(_PLAN_ABC)  # [keyA, keyB, keyC]

    sandbox = _FakeSandbox(files={"prototype.html": "<html></html>"})
    runner = _FakeRunner(
        agent_events=[{"type": "agent_chunk", "data": {"text": "."}}],
        typed_content={"prototype-plan": _PLAN_ABC},  # current = [A, B, C]
        sandbox=sandbox,
    )
    # Completed order starts with B (Alpha was deleted from the FRONT / a new head task
    # inserted): current[0]=keyA != completed[0]=keyB → p=0 → run every current task.
    ctx = SimpleNamespace(
        runner=runner,
        resume_completed_ordered={"prototype-build": [keys_abc[1], keys_abc[2]]},
    )
    step = Step(
        agent_id="prototype-build",
        strategy="task_loop",
        task_source=TaskSource(
            kind="parsed", parser="heading_tasks", source_step="prototype-plan"
        ),
    )

    _ = [ev async for ev in TaskLoopStrategy().run(step, ctx)]

    dispatched = [c["task_number"] for c in runner.run_agent_calls]
    assert dispatched == [1, 2, 3], (
        "p==0 first-task divergence must re-run EVERY current task from a clean basis "
        f"(no negative-index skip); got {dispatched}"
    )


class _WorkerCursorFakeRunner:
    """A minimal ctx.runner capturing the ``task_id`` set each wave actually fans out.

    ``read_wave_runs`` reports a single ``running`` wave 0 for this step (the in-flight
    wave: not terminal, so it is NOT skipped wholesale). The strategy re-enters wave 0
    and — reading the kernel-stamped ``resume_completed_task_ids`` cursor off ``ctx`` —
    must FILTER the completed worker's ``task_id`` out of the dispatched ``requests``.
    On HEAD (no cursor read) the whole wave re-runs → the completed worker is
    re-dispatched → RED.
    """

    def __init__(self, this_step):
        self.this_step = this_step
        self.fanned_requests: list[list[str]] = []  # per-wave dispatched task_ids
        self.recorded: list = []
        self.updated: list = []

    def latest_typed_content(self, _step):
        return ""

    def upstream_context_hash(self, _step):
        # RESUME-14: fixed per-step upstream digest for deterministic wave task_keys.
        return "u-fake"

    async def read_wave_runs(self):
        return [_FakeWaveRow(self.this_step, 0, "running")]

    async def read_subagent_runs(self):
        # The strategy does NOT read subagent_runs itself — the completed set is
        # kernel-computed and threaded via the ectx cursor. Present for shape parity.
        return []

    async def record_wave_run(self, *, step, wave_index, task_ids, status):
        self.recorded.append((step, wave_index, list(task_ids), status))
        return f"row-{step}-{wave_index}"

    async def update_wave_run(self, row_id, *, status):
        self.updated.append((row_id, status))

    async def run_fanout(self, requests, ctx, *, step=None):
        self.fanned_requests.append([r.get("task_id") for r in requests])
        if False:  # pragma: no cover — make this an async generator
            yield {}


@pytest.mark.asyncio
async def test_wave_scheduler_skips_completed_workers_on_resume_cursor():
    """RESUME-09 (RED on HEAD): the wave_scheduler SKIPS the completed WORKERS named by
    the kernel-stamped cursor (identity-based, by ``task_id``) instead of re-running the
    whole in-flight wave.

    A 3-worker in-flight wave with one worker (``tb``) already complete: the dispatched
    ``requests``/``task_ids`` must EXCLUDE ``tb`` (its file is already on disk from
    re-materialization) and include only the two incomplete workers ``ta``/``tc``. This
    is the CR-03-followup — identity-based, NOT the deleted prefix-by-count skip. On HEAD
    the whole wave re-runs (all 3 dispatched) → RED.
    """
    from agents.capabilities import task_identity
    from agents.capabilities.strategies.wave_scheduler import WaveSchedulerStrategy
    from agents.workflows.plan import Task

    strat = WaveSchedulerStrategy()
    runner = _WorkerCursorFakeRunner("wstep")
    ctx = _Ctx(runner, is_resuming=True)
    step = _Step("wstep")

    # Three disjoint tasks (no deps) → a SINGLE wave [ta, tb, tc].
    tasks = [
        Task(id="ta", title="A", body="a", targets=["a.txt"]),
        Task(id="tb", title="B", body="b", targets=["b.txt"]),
        Task(id="tc", title="C", body="c", targets=["c.txt"]),
    ]

    # RESUME-14: the request task_id + skip are now content-addressed KEYS wrapping the
    # author id. Compute the SAME keys the strategy will ("u-fake" upstream from the fake;
    # all-distinct content → ordinals 0). The DAG/dup-guard still key on author t.id.
    def _key(t):
        return task_identity.compute_task_key(
            "u-fake", task_identity.normalize_task_content(t), 0
        )

    key_ta, key_tb, key_tc = _key(tasks[0]), _key(tasks[1]), _key(tasks[2])
    # KERNEL-stamped cursor: worker tb of this wave step already completed pre-crash.
    ctx.resume_completed_task_ids = {"wstep": {key_tb}}

    class _FakeParser:
        def parse(self, _text):
            return tasks

    strat._registry = type("R", (), {"resolve": lambda self, k, n: _FakeParser()})()
    step.task_source = type("TS", (), {"source_step": "plan", "parser": "json_tasks"})()

    _ = [ev async for ev in strat.run(step, ctx)]

    assert runner.fanned_requests, "the in-flight wave was not dispatched at all"
    dispatched = set(runner.fanned_requests[0])
    assert key_tb not in dispatched, (
        "the completed worker 'tb' (by key) was RE-DISPATCHED — per-worker skip failed "
        f"(dispatched {sorted(dispatched)})"
    )
    assert dispatched == {key_ta, key_tc}, (
        "the in-flight wave must re-run ONLY the incomplete workers ta+tc, keyed "
        f"content-addressed (identity-based skip); got {sorted(dispatched)}"
    )
    # The wave_runs row's task_ids stay AUTHOR ids (they feed the wave events; only the
    # request/subagent_runs task_id becomes the key) — the completed worker is excluded.
    assert runner.recorded, "no wave_run was recorded for the in-flight wave"
    assert set(runner.recorded[0][2]) == {"ta", "tc"}, (
        f"the wave_runs task_ids must exclude the completed worker; got {runner.recorded[0][2]}"
    )


@pytest.mark.asyncio
async def test_kernel_computes_resume_completed_task_ids_cursor():
    """RESUME-09 (RED on HEAD): the KERNEL computes the per-step completed-identity set
    from the run's own owner-scoped durable rows and returns it keyed by step agent id.

    - task_loop step: DISTINCT ``task_id`` from ``store.tree`` where
      ``producer_agent == step agent`` — a fix-loop re-persist of the SAME ``task_id``
      counts ONCE (Edge-Case 1 dedup, a ``set``).
    - wave step: ``task_id`` from ``read_subagent_runs`` where ``status == "complete"``
      (a ``running`` worker is NOT completed), keyed on the plan-global ``task_id`` NOT
      the wave-local ``worker_index`` (Edge-Case 5).

    On HEAD the method does not exist → AttributeError → RED.
    """
    import types

    from agents.authz import ScopedStore
    from agents.capabilities import task_identity
    from agents.execution_engine.context import ExecutionContext
    from agents.execution_engine.engine import ExecutionEngine
    from agents.workflows.plan import Step, TaskSource

    session, db_engine = _make_session()
    run_id = f"cur-{uuid.uuid4().hex[:8]}"
    owner = "cur-user"
    ws = "ws-cur"
    _seed_workflow_run(session, run_id, owner=owner, status="generating")
    store = ScopedStore(owner_id=owner, workspace_id=ws, session=session)

    # RESUME-14: the durable rows now carry content-addressed task_keys in the task_id
    # slot (the write-path switch). The cursor is IDENTITY-AGNOSTIC — it dedups + filters
    # by whatever identity is stamped and returns it verbatim. Seed real keys and assert
    # the cursor returns them (the core RESUME-14 contract).
    k1 = task_identity.compute_task_key("u", "task-one", 0)
    k2 = task_identity.compute_task_key("u", "task-two", 0)
    kA = task_identity.compute_task_key("u", "worker-a", 0)
    kB = task_identity.compute_task_key("u", "worker-b", 0)
    kC = task_identity.compute_task_key("u", "worker-c", 0)

    # task_loop step "build": task-key k1 persisted TWICE (fix-loop re-persist, same key)
    # + k2 once → distinct done {k1,k2}. A third task-key never persisted.
    await _seed_ref(store, run_id=run_id, owner=owner, ws=ws, kind="html_file",
                    location="prototype.html", content="t1-v1", version=1,
                    producer_agent="build", task_id=k1)
    await _seed_ref(store, run_id=run_id, owner=owner, ws=ws, kind="html_file",
                    location="prototype.html", content="t1-v2", version=2,
                    producer_agent="build", task_id=k1)
    await _seed_ref(store, run_id=run_id, owner=owner, ws=ws, kind="html_file",
                    location="prototype.html", content="t2-v1", version=3,
                    producer_agent="build", task_id=k2)

    # wave step "wave": worker kA+kC complete, kB still running → completed {kA,kC}.
    for tid, status in ((kA, "complete"), (kB, "running"), (kC, "complete")):
        await store.record_subagent_run(
            run_id, parent_step="wave", worker_agent="w", depth=1,
            isolation="shared_read", status=status, worker_index=0, task_id=tid,
        )
    session.commit()

    compiled = types.SimpleNamespace(
        steps=[
            Step(
                agent_id="build",
                strategy="task_loop",
                task_source=TaskSource(
                    kind="parsed", parser="heading_tasks", source_step="plan"
                ),
            ),
            Step(agent_id="wave", strategy="wave_scheduler"),
        ]
    )
    ordered_agents = [_IdSpec("build"), _IdSpec("wave")]

    ectx = ExecutionContext(run_id=run_id, owner_id=owner, disk_principal=owner)
    ectx.workspace_id = ws
    ectx.scoped_store = store

    engine = ExecutionEngine()
    cursor, cursor_ordered = await engine._compute_resume_completed_task_ids(
        ectx, ordered_agents, compiled
    )

    assert cursor.get("build") == {k1, k2}, (
        "task_loop completed set must dedup the fix-loop re-persist AND return the "
        f"content-addressed keys (not positions); got {cursor.get('build')}"
    )
    assert cursor.get("wave") == {kA, kC}, (
        "wave completed set must include only status=='complete' workers, keyed on the "
        f"content-addressed task_key; got {cursor.get('wave')}"
    )
    # RESUME-16 cumulative: the cursor ALSO emits completed keys in build ORDER (by
    # min(version) per distinct task_id) for the task_loop common-prefix reconcile. k1's
    # min-version (1) precedes k2's (3) → [k1, k2]. Waves need no order (set-membership).
    assert cursor_ordered.get("build") == [k1, k2], (
        "task_loop cursor must emit completed keys ordered by min(version) per task_id "
        f"(build order); got {cursor_ordered.get('build')}"
    )
    session.close()


@pytest.mark.asyncio
async def test_upstream_context_hash_single_home_stable(tmp_path):
    """RESUME-14 (RED on HEAD): the upstream-context-hash has ONE home (INV-12).

    The engine exposes ``_compute_upstream_context_hash(step, ectx)`` returning a
    stable 64-char hex digest of the SORTED upstream content_hashes the step consumes
    (the same scheme ``_compute_step_input_hash`` uses for its upstream half — factored,
    not duplicated). The strategy reaches it via ``runner.upstream_context_hash(step)``,
    which MUST return the identical digest.

    On HEAD neither the engine helper nor the runner handle exist → AttributeError → RED.
    """
    from types import SimpleNamespace

    from agents.artifacts.graph import ArtifactGraph
    from agents.execution_engine.context import ExecutionContext
    from agents.execution_engine.engine import ExecutionEngine
    from agents.execution_engine.kernel_services import KernelServices
    from agents.workflows.plan import Step
    from app.agents.sandbox import RunSandbox

    run_id = f"uh-{uuid.uuid4().hex[:8]}"
    owner = "uh-user"
    ws = "ws-uh"

    graph = ArtifactGraph()
    # An upstream 'plan' ref the 'build' step consumes → its content_hash feeds the digest.
    graph.write_ref(
        run_id=run_id, owner_id=owner, workspace_id=ws, kind="task_list",
        producer_step="plan", producer_agent="plan", task_id=None,
        content="## Task 1: do it", location="artifact_refs/plan",
    )

    ectx = ExecutionContext(
        run_id=run_id, owner_id=owner, disk_principal=owner, artifacts=graph
    )
    ectx.workspace_id = ws

    engine = ExecutionEngine()
    sandbox = RunSandbox(owner, run_id, runs_root=str(tmp_path))
    sandbox.ensure()

    ordered = [
        SimpleNamespace(id="plan", produces=["task_list"], consumes=[]),
        SimpleNamespace(id="build", produces=[], consumes=["task_list"]),
    ]
    runner = KernelServices(
        engine=engine, ectx=ectx, sandbox=sandbox, ordered_agents=ordered,
        user_message="brief", pipeline_run_id=run_id, pipeline_type="prototype",
        planning_context={}, attached_skills=None, attached_hooks=None,
        model_id=None, results=[], cancel_event=None,
    )
    ectx.runner = runner
    step = Step(agent_id="build", strategy="task_loop")

    # (a) engine helper: a stable 64-char hex, non-empty upstream folded in.
    h1 = engine._compute_upstream_context_hash(step, ectx)
    h2 = engine._compute_upstream_context_hash(step, ectx)
    assert re.fullmatch(r"[0-9a-f]{64}", h1 or ""), f"expected 64-hex digest, got {h1!r}"
    assert h1 == h2, "the upstream-context-hash must be deterministic across calls"

    # (b) the runner handle delegates to the SAME digest.
    assert runner.upstream_context_hash(step) == h1, (
        "runner.upstream_context_hash(step) must equal the engine helper's digest "
        "(one home, INV-12)"
    )


# ── RESUME-16 rotation: update_specs composes (proof, no new production code) ─
# A spec edit (Phase-27 update_specs mints a NEW spec version → a new content_hash)
# rotates the build step's _compute_upstream_context_hash → every build task_key rotates
# → on resume/continue the reconciler finds NO current key in the completed set → all
# build tasks re-run (no v1-key wrongly skipped). This falls out of 48-01 upstream-
# namespacing — the test is a PROOF/regression, not a new capability (INV-12: the
# rotation is generic, no bespoke update_specs branch).


@pytest.mark.asyncio
async def test_update_specs_reconcile_composes(tmp_path):
    """RESUME-16 rotation: a spec-v2 edit rotates every build task_key so all build
    tasks re-run and no v1-completed key is skipped — with NO new production code (the
    rotation is a property of the 48-01 upstream-context-hash namespace).
    """
    from types import SimpleNamespace

    from agents.artifacts.graph import ArtifactGraph
    from agents.capabilities import task_identity
    from agents.capabilities.task_parsers.heading_tasks import HeadingTasksParser
    from agents.execution_engine.context import ExecutionContext
    from agents.execution_engine.engine import ExecutionEngine
    from agents.execution_engine.kernel_services import KernelServices
    from agents.workflows.plan import Step
    from app.agents.sandbox import RunSandbox

    run_id = f"us-{uuid.uuid4().hex[:8]}"
    owner, ws = "us-user", "ws-us"

    _BUILD_PLAN = (
        "## Task 1: Shell\nBuild the HTML shell.\n\n"
        "## Task 2: Dashboard\nAdd the dashboard page.\n"
    )

    graph = ArtifactGraph()
    # The build step consumes BOTH the task_list (from 'plan') and the spec (from
    # 'specify'); update_specs rotates the SPEC content, which feeds the build upstream.
    graph.write_ref(
        run_id=run_id, owner_id=owner, workspace_id=ws, kind="task_list",
        producer_step="plan", producer_agent="plan", task_id=None,
        content=_BUILD_PLAN, location="artifact_refs/plan",
    )
    graph.write_ref(
        run_id=run_id, owner_id=owner, workspace_id=ws, kind="spec",
        producer_step="specify", producer_agent="specify", task_id=None,
        content="Spec v1: a plain dashboard.", location="artifact_refs/specify",
    )

    ectx = ExecutionContext(
        run_id=run_id, owner_id=owner, disk_principal=owner, artifacts=graph
    )
    ectx.workspace_id = ws
    engine = ExecutionEngine()
    sandbox = RunSandbox(owner, run_id, runs_root=str(tmp_path))
    sandbox.ensure()
    ordered = [
        SimpleNamespace(id="plan", produces=["task_list"], consumes=[]),
        SimpleNamespace(id="specify", produces=["spec"], consumes=[]),
        SimpleNamespace(id="build", produces=[], consumes=["task_list", "spec"]),
    ]
    runner = KernelServices(
        engine=engine, ectx=ectx, sandbox=sandbox, ordered_agents=ordered,
        user_message="brief", pipeline_run_id=run_id, pipeline_type="prototype",
        planning_context={}, attached_skills=None, attached_hooks=None,
        model_id=None, results=[], cancel_event=None,
    )
    ectx.runner = runner
    step = Step(agent_id="build", strategy="task_loop")

    def _keys_now() -> list[str]:
        uhash = engine._compute_upstream_context_hash(step, ectx)
        tasks = HeadingTasksParser().parse(_BUILD_PLAN)
        ords = task_identity.occurrence_ordinals(tasks)
        return [
            task_identity.compute_task_key(
                uhash, task_identity.normalize_task_content(t), ords[i]
            )
            for i, t in enumerate(tasks)
        ]

    # Build ran under spec-v1 → these are the COMPLETED keys (in build order).
    uhash_v1 = engine._compute_upstream_context_hash(step, ectx)
    completed_v1 = _keys_now()

    # update_specs mints a NEW spec version (Phase 27) — a different content_hash.
    graph.write_ref(
        run_id=run_id, owner_id=owner, workspace_id=ws, kind="spec",
        producer_step="specify", producer_agent="specify", task_id=None,
        content="Spec v2: a dashboard WITH a reports tab and dark mode.",
        location="artifact_refs/specify",
    )

    uhash_v2 = engine._compute_upstream_context_hash(step, ectx)
    current_v2 = _keys_now()

    # (rotation) the spec-v2 write rotates the build step's upstream namespace.
    assert uhash_v2 != uhash_v1, (
        "a new spec version must rotate the build step's upstream_context_hash "
        "(Phase-27 update_specs composition)"
    )
    # (a) every build task re-runs: NONE of the v1 completed keys survives into the
    #     current key set → the common-prefix reconciler skips nothing (p == 0).
    assert set(completed_v1).isdisjoint(current_v2), (
        "every build task_key must rotate under the new spec version — no v1 key may "
        "appear in the current-key set (else a stale-spec task would be wrongly skipped)"
    )
    assert task_identity.common_prefix_length(current_v2, completed_v1) == 0, (
        "the cumulative reconciler must re-run EVERY current build task after an "
        "update_specs rotation (common prefix == 0)"
    )
    # (b) the wave-style per-key set-membership skip is likewise empty: no current key
    #     is in the completed set → nothing skipped, all dispatch.
    _skipped = [k for k in current_v2 if k in set(completed_v1)]
    assert _skipped == [], f"no current task may be skipped after rotation; got {_skipped}"


# ===========================================================================
# RESUME-10 — a resumed run is a first-class LIVE run: live-ectx registered
# (+ guaranteed unregister in finally), milestone cards emitted with an
# engine-counter seq (DEF-43-03-1), never append_event_next_seq for the base
# events. Drives resume_run with injected register/unregister/milestone stubs.
# ===========================================================================


@pytest.mark.asyncio
async def test_resumed_run_is_wired_live_ectx_and_milestone_cards():
    """RESUME-10: resume_run threads the SAME live-layer callbacks execute() does.

    On HEAD ``resume_run`` builds ``_RunEventSink()`` (no milestone_sink), threads no
    ``live_ectx_register``, and has no ``live_ectx_unregister`` in its finally — so a
    resumed run is dead to steering / per-turn images / Concierge / narrator cards.

    This injects the three engine hooks (as the app layer does at ``app/main.py``),
    drives ``resume_run`` over a seeded durable tail, and asserts:
      * the run's rebuilt ectx was REGISTERED (``_live_ectx_for_run(run_id)`` resolves);
      * at least one ``chat_reply`` milestone card was emitted with a seq drawn from the
        engine's advanceable counter (contiguous PAST the durable tail — no collision);
      * ``unregister`` fired exactly ONCE in the finally (no ``_LIVE_ECTX`` leak).

    FAILS on HEAD (no register threaded, no card, no unregister).
    """
    from agents.authz import ScopedStore
    from app.models.run_event import RunEvent

    session, db_engine = _make_session()
    run_id = f"lw-{uuid.uuid4().hex[:8]}"
    owner = "lw-user"
    workspace_id = "ws-lw"
    _seed_workflow_run(session, run_id, owner=owner, status="generating")

    # Seed a durable tail at seq 1..N under the REAL workspace the sink writes under, so
    # the engine seeds its resume counter at N+1 (CR-01) and cards must land beyond N.
    pre_store = ScopedStore(owner_id=owner, workspace_id=workspace_id, session=session)
    N = 5
    for seq in range(1, N + 1):
        await pre_store.append_event(
            run_id, seq=seq, event_id=f"pre-{seq}",
            type=f"agent_chunk_{seq}", payload_json={"seq": seq},
        )
    session.commit()

    # ── The three injected live-layer hooks (mirroring app/main.py + run_commands). ──
    registered: dict[str, Any] = {}
    unregister_calls: list[str] = []
    card_state = {"emitted": False}
    emitted_cards: list[tuple] = []

    def _stub_register(rid, ectx):
        registered[rid] = ectx

    def _stub_unregister(rid):
        unregister_calls.append(rid)

    async def _stub_milestone_sink(store, rid, event):
        # Self-filtering narrator analog: project exactly ONE card (the first event),
        # allocating its seq from the durable tail via append_event_next_seq — EXACTLY
        # as chat_narrator.persist_milestone_card does, so the engine must advance its
        # own counter PAST the card seq (DEF-43-03-1, no collision on the 0024 constraint).
        if card_state["emitted"]:
            return None
        card_state["emitted"] = True
        src_event_id = (event.get("data") or {}).get("event_id")
        created, card_seq = await store.append_event_next_seq(
            rid,
            event_id=f"chat_reply:{src_event_id}",
            type="chat_reply",
            payload_json={"kind": "milestone", "text": "resumed"},
        )
        card = {"kind": "milestone", "text": "resumed"}
        emitted_cards.append((created, card_seq, card))
        return (created, card_seq, card)

    call_log: dict[str, int] = {}
    with _ResumeHarness(session, call_log, fail_on=set(), db_engine=db_engine) as h:
        engine_b = h.make_engine()
        engine_b._resume_live_ectx_register = _stub_register
        engine_b._resume_live_ectx_unregister = _stub_unregister
        engine_b._resume_milestone_sink = _stub_milestone_sink
        await engine_b.resume_run(run_id)

    # (1) the rebuilt ectx was registered under run_id (live-ectx resolves during the run).
    assert run_id in registered, (
        "resume_run must thread live_ectx_register so _live_ectx_for_run(run_id) resolves "
        "the resumed run (steering / per-turn images / Concierge)"
    )
    assert registered[run_id] is not None

    # (2) at least one milestone card was emitted, its seq drawn from the engine's
    # advanceable counter space (contiguous PAST the durable tail — never a collision).
    assert emitted_cards, (
        "resume_run must build _RunEventSink(milestone_sink=...) and emit_milestone_card "
        "per event so narrator cards reach a resumed run"
    )
    _created, _card_seq, _, _reply_eid = emitted_cards[0]
    assert _card_seq > N, (
        f"the milestone card seq must continue past the durable tail (> {N}); "
        f"got {_card_seq}"
    )
    # The card row is durable — and every resumed row (base events + card) is > N with
    # NO duplicate seq (the engine counter advanced past the card, DEF-43-03-1).
    all_rows = (
        session.query(RunEvent)
        .filter(RunEvent.run_id == run_id)
        .order_by(RunEvent.seq.asc())
        .all()
    )
    pre_ids = {f"pre-{s}" for s in range(1, N + 1)}
    resumed = [r for r in all_rows if r.event_id not in pre_ids]
    assert resumed, "resume_run persisted no resumed events"
    assert all(r.seq > N for r in resumed), (
        f"every resumed row must carry seq > {N}; got {[r.seq for r in resumed]}"
    )
    resumed_seqs = [r.seq for r in resumed]
    assert len(resumed_seqs) == len(set(resumed_seqs)), (
        f"resumed seqs must be unique (no card/base collision); got {resumed_seqs}"
    )
    card_rows = [r for r in resumed if r.type == "chat_reply"]
    assert card_rows, "the milestone chat_reply row must be durably persisted"

    # (3) unregister fired exactly once in the finally (normal completion) — no leak.
    assert unregister_calls == [run_id], (
        f"live_ectx_unregister must fire exactly once in resume_run's finally; "
        f"got {unregister_calls}"
    )
    session.close()


# ===========================================================================
# RESUME-11 — steering re-drain: undrained chat_message notes (seq > max
# agent_input.seq) re-queue onto ectx.steering_notes at resume (no-loss);
# a drained note (seq < last_input_seq) is NOT re-queued (no-duplicate).
# ===========================================================================


async def _seed_run_event(store, *, run_id, seq, type_, payload):
    await store.append_event(
        run_id, seq=seq, event_id=f"ev-{seq}", type=type_, payload_json=payload
    )


@pytest.mark.asyncio
async def test_redrain_steering_notes_no_loss():
    """RESUME-11 no-loss (RED on HEAD): a durably-logged-but-undrained steering note
    (a ``chat_message`` row whose ``seq > max(agent_input.seq)``) re-queues onto
    ``ectx.steering_notes`` at resume, in the ``apply_steering`` append shape
    (``{"text": ..., "sticky": False}``). On HEAD the helper does not exist → RED.
    """
    from agents.authz import ScopedStore
    from agents.execution_engine.context import ExecutionContext
    from agents.execution_engine.engine import ExecutionEngine

    session, db_engine = _make_session()
    run_id = f"sd-{uuid.uuid4().hex[:8]}"
    owner = "sd-user"
    ws = "ws-sd"
    _seed_workflow_run(session, run_id, owner=owner, status="generating")
    store = ScopedStore(owner_id=owner, workspace_id=ws, session=session)

    # agent_input rows at seq 1 and 3 → last_input_seq = 3. Two undrained chat_message
    # rows AFTER it (seq 4, 5) + a drained one BEFORE it (seq 2) + an empty-text row
    # (seq 6, skipped).
    await _seed_run_event(store, run_id=run_id, seq=1, type_="agent_input", payload={"x": 1})
    await _seed_run_event(store, run_id=run_id, seq=2, type_="chat_message",
                          payload={"text": "drained-note"})
    await _seed_run_event(store, run_id=run_id, seq=3, type_="agent_input", payload={"x": 2})
    await _seed_run_event(store, run_id=run_id, seq=4, type_="chat_message",
                          payload={"text": "undrained-A"})
    await _seed_run_event(store, run_id=run_id, seq=5, type_="chat_message",
                          payload={"text": "undrained-B"})
    await _seed_run_event(store, run_id=run_id, seq=6, type_="chat_message",
                          payload={"text": ""})
    session.commit()

    ectx = ExecutionContext(run_id=run_id, owner_id=owner, disk_principal=owner)
    ectx.workspace_id = ws
    ectx.scoped_store = store

    engine = ExecutionEngine()
    await engine._redrain_steering_notes(ectx)

    texts = [n["text"] for n in ectx.steering_notes]
    assert texts == ["undrained-A", "undrained-B"], (
        f"no-loss: both undrained notes (seq > last_input_seq) must re-queue in order; "
        f"got {texts}"
    )
    assert all(n.get("sticky") is False for n in ectx.steering_notes), (
        "re-queued notes are one-shot (sticky False) — the durable row lacks the flag"
    )
    session.close()


@pytest.mark.asyncio
async def test_redrain_steering_notes_no_duplicate():
    """RESUME-11 no-duplicate (RED on HEAD): a chat_message row already DRAINED before the
    crash (``seq < max(agent_input.seq)``) is NOT re-queued — the seq-compare heuristic
    skips it. Otherwise a resume would re-inject guidance the run already consumed.
    """
    from agents.authz import ScopedStore
    from agents.execution_engine.context import ExecutionContext
    from agents.execution_engine.engine import ExecutionEngine

    session, db_engine = _make_session()
    run_id = f"nd-{uuid.uuid4().hex[:8]}"
    owner = "nd-user"
    ws = "ws-nd"
    _seed_workflow_run(session, run_id, owner=owner, status="generating")
    store = ScopedStore(owner_id=owner, workspace_id=ws, session=session)

    # A steering note at seq 2, then an agent_input at seq 5 CONSUMED it → last_input_seq
    # = 5. The note (seq 2 < 5) is drained; nothing undrained remains.
    await _seed_run_event(store, run_id=run_id, seq=2, type_="chat_message",
                          payload={"text": "already-drained"})
    await _seed_run_event(store, run_id=run_id, seq=5, type_="agent_input", payload={"x": 1})
    session.commit()

    ectx = ExecutionContext(run_id=run_id, owner_id=owner, disk_principal=owner)
    ectx.workspace_id = ws
    ectx.scoped_store = store

    engine = ExecutionEngine()
    await engine._redrain_steering_notes(ectx)

    assert ectx.steering_notes == [], (
        f"no-duplicate: a note drained pre-crash (seq < last_input_seq) must NOT re-queue; "
        f"got {ectx.steering_notes}"
    )
    session.close()


# ===========================================================================
# RESUME-17 (49-03) — clarify twin: REPLAY the durable questionnaire on restart
# ===========================================================================
#
# The asymmetric sibling of the review re-entry (engine.py:1708): a resumed run SKIPS
# planner AND clarify, so a clarify-parked run cannot route through the review offset
# override. It needs a dedicated REPLAY driver (PINNED A5): read the durable
# ``questionnaire_ready`` payload, re-emit its questions verbatim (NO ``_generate_questions``
# LLM re-gen of the open round), re-enter the store wait, and on answers (via the UNCHANGED
# ``POST /answers`` seam) proceed into the normal dispatch exactly as a never-restarted run.


async def _seed_open_questionnaire_gate(
    session, run_id, owner, workspace_id, questions, round_num=1
):
    """Seed a durable, still-OPEN ``questionnaire_ready`` (no ``questionnaire_complete``)
    under the SAME ``(owner, workspace_id)`` the run row carries — so the owner+workspace
    scoped ``read_events`` (scoped on ``wr.workspace_id`` in both ``_is_resumable_in_flight``
    and branch (a)) finds it → ``derive_open_gate`` → ``("questionnaire", None)`` AND
    ``_is_resumable_in_flight`` is True (one durable ``run_events`` row is enough evidence).
    ``run_events.workspace_id`` is NOT NULL, so a real workspace is required."""
    from agents.authz import ScopedStore

    pre_store = ScopedStore(owner_id=owner, workspace_id=workspace_id, session=session)
    await pre_store.append_event(
        run_id, seq=1, event_id="qr-1", type="questionnaire_ready",
        payload_json={
            "pipeline_run_id": run_id, "questions": questions, "round": round_num,
        },
    )
    session.commit()


@pytest.mark.asyncio
async def test_clarify_parked_run_replays_durable_questions_and_proceeds():
    """RESUME-17 SC-4/SC-5 (the KAN-88 twin): a restart-parked clarify run re-arms by
    REPLAYING its durable ``questionnaire_ready`` (no LLM re-gen of the open round), stays
    ``waiting_for_user`` until answered, is NOT driven through ``resume_run``, and — on
    answers via the SAME store seam ``POST /answers`` wraps — proceeds into the normal
    dispatch (planner→agents) exactly as a never-restarted run."""
    import asyncio as _asyncio

    from agents.execution_engine import clarify_engine as _ce
    from app.models.workflow import WorkflowRun

    session, db_engine = _make_session()
    run_id = f"cl-{uuid.uuid4().hex[:8]}"
    owner = "cl-user"
    ws = "ws-cl"
    _seed_workflow_run(
        session, run_id, owner=owner, status="waiting_for_user", workspace_id=ws
    )
    questions = [{
        "question_id": "r1_q1", "question_text": "Replayed?",
        "options": ["yes", "no"], "answer_type": "single_choice",
        "impact_level": "high", "ambiguity_category": "Functional Scope",
    }]
    await _seed_open_questionnaire_gate(session, run_id, owner, ws, questions, round_num=1)

    # Spy _generate_questions: the OPEN round must be REPLAYED, never re-generated.
    gen_calls = {"n": 0}
    _orig_gen = _ce.ClarifyEngine._generate_questions

    async def _spy_gen(self, *a, **k):
        gen_calls["n"] += 1
        return await _orig_gen(self, *a, **k)

    with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h:
        engine = h.make_engine()
        _ce.ClarifyEngine._generate_questions = _spy_gen

        async def _spy_resume(rid):
            raise AssertionError(
                "a clarify re-arm must NEVER be driven through resume_run"
            )

        engine.resume_run = _spy_resume  # type: ignore[assignment]

        queues: dict = {}

        def _reg_queue(rid):
            return queues.setdefault(rid, _asyncio.Queue())

        engine._resume_register_queue = _reg_queue  # type: ignore[assignment]

        tasks: dict = {}

        def _reg_task(rid, task):
            tasks[rid] = task

        engine._resume_register_task = _reg_task  # type: ignore[assignment]

        saw_complete = False
        saw_pipeline_start = False
        try:
            await engine.restore_non_terminal_runs()
            driver_task = tasks.get(run_id)
            assert driver_task is not None, (
                "branch (a) must spawn + register the clarify re-arm driver"
            )
            q = queues[run_id]

            # Drain until the driver REPLAYS questionnaire_ready then parks at the wait.
            replayed = None
            for _ in range(500):
                ev = await _asyncio.wait_for(q.get(), timeout=5)
                if ev is None:
                    break
                if ev.get("type") == "questionnaire_ready":
                    replayed = ev
                    break
            assert replayed is not None, "the driver must re-emit questionnaire_ready"
            assert replayed["data"]["questions"] == questions, (
                "questions must be REPLAYED verbatim from the durable payload"
            )
            assert gen_calls["n"] == 0, (
                "the open round must be REPLAYED, never LLM-re-generated"
            )

            # Status stays waiting_for_user while parked (KAN-88 twin assertion).
            row = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
            assert row.status == "waiting_for_user", (
                "a re-armed clarify run stays waiting_for_user until answered"
            )

            # Answers ride the UNCHANGED store seam POST /answers wraps → run proceeds.
            await engine._store.set_questionnaire_responses(
                run_id, [{"question_id": "r1_q1", "answer": "yes"}]
            )

            for _ in range(4000):
                ev = await _asyncio.wait_for(q.get(), timeout=10)
                if ev is None:
                    break
                t = ev.get("type")
                if t == "questionnaire_complete":
                    saw_complete = True
                if t == "pipeline_start":
                    saw_pipeline_start = True
                if t == "pipeline_complete":
                    break
            await _asyncio.wait_for(driver_task, timeout=10)
        finally:
            _ce.ClarifyEngine._generate_questions = _orig_gen

    assert saw_complete, "answers must resolve the gate (questionnaire_complete emitted)"
    assert saw_pipeline_start, (
        "after answers the run must proceed into the normal dispatch (pipeline_start)"
    )
    assert gen_calls["n"] == 0, "no LLM re-gen of the answered round at any point"
    session.close()


@pytest.mark.asyncio
async def test_clarify_run_without_replay_generates_normally():
    """INV-3 dormancy: ``ClarifyEngine.run`` WITHOUT the replay params generates round-1
    questions normally (the A5 replay branch is unreachable) — the new machinery is inert
    on every non-re-arm clarify run."""
    from agents.execution_engine.clarify_engine import ClarifyEngine

    ce = ClarifyEngine()
    gen = {"n": 0}

    async def _gen(planning_context, round_num, clarify_agent):
        gen["n"] += 1
        return []

    ce._generate_questions = _gen  # type: ignore[assignment]

    sent: list = []

    async def _send(ev):
        sent.append(ev)

    result = await ce.run(
        "run-dormant",
        {"missing_information": ["x"], "user_request": "hi"},
        _send,
        owner_id="o",
        replay_questions=None,
        replay_round=None,
    )
    assert gen["n"] == 1, "round 1 must generate normally when no replay params are passed"
    assert result["execution_gate"] == "PROCEED"
    assert not any(e.get("type") == "questionnaire_ready" for e in sent), (
        "no questions ⇒ no questionnaire_ready emitted (dormant replay branch)"
    )


# ===========================================================================
# RESUME-18 (Phase 50) — user resume-from-failed E2E: the endpoint's thin
# ``_drive_user_resume`` wrapper over the SHIPPED resume tier. These cases drive
# ``run_commands._drive_user_resume(run_id, user=...)`` DIRECTLY (avoiding the
# TestClient background-task timing race the pattern map flags) over the SAME
# durable-seed harness — no new harness, no production code touched here (Task 2
# is the integration proof over Task 1's surface).
# ===========================================================================


class _ResumeUser:
    """A minimal owner principal for ``_drive_user_resume(run_id, *, user=...)`` — the
    wrapper does not read ``user`` (drive is keyed on run_id inside ``resume_run``); it is
    threaded only for parity with the endpoint's ``current_user``."""

    def __init__(self, id: str):
        self.id = id
        self.preferred_model = None


def _wire_user_resume_drive(monkeypatch, db_engine, engine_instance):
    """Point ``run_commands`` / ``run_engine`` ``_get_db`` + the engine singleton at the
    harness's shared in-memory DB + the harnessed engine, so ``_drive_user_resume`` (and its
    reconcile / flip-back) resolve against the SAME durable rows ``resume_run`` reads. Called
    INSIDE the ``_ResumeHarness`` ``with`` block (which also patches ``SessionLocal`` — the
    seam ``resume_run`` / ScopedStore / ``_recover_workspace_id`` use)."""
    import app.api.run_engine as _re_mod
    import app.api.run_commands as _rc_mod
    import agents.execution_engine.engine as _eng_mod

    shared = sessionmaker(
        bind=db_engine, autocommit=False, autoflush=False, expire_on_commit=False
    )
    monkeypatch.setattr(_re_mod, "_get_db", lambda: shared())
    monkeypatch.setattr(_rc_mod, "_get_db", lambda: shared())
    monkeypatch.setattr(_eng_mod, "get_execution_engine", lambda: engine_instance)
    return _rc_mod


@pytest.mark.asyncio
async def test_failed_run_resumes_skips_completed_tasks(monkeypatch):
    """A run failed MID-BUILD (wave 0 durably complete, wave 1 never finished) → user
    resume via ``_drive_user_resume`` SKIPS the completed wave-0 workers (cursor evidence),
    COMPLETES the deliverable, RECONCILES the terminal status to ``completed``, and keeps
    the SAME run id with NO new ``WorkflowRun`` row (family coherence; Pitfall 5)."""
    session, db_engine = _make_session()
    run_id = f"ur-{uuid.uuid4().hex[:8]}"
    owner = "ur-user"
    _seed_workflow_run(session, run_id, owner=owner, status="generating")

    call_log: dict[str, int] = {}

    # ── Instance A: interrupted mid-wave — wave 0 completes, wave 1 crashes on entry ──
    with _ResumeHarness(
        session, call_log, fail_on=set(), db_engine=db_engine, raise_on_fanout_call=2
    ) as h:
        engine_a = h.make_engine()
        try:
            async for _ev in engine_a._execute_impl(
                agents=list(h.specs),
                user_message="Run the wave workflow.",
                pipeline_run_id=run_id,
                pipeline_type=_FIXTURE_ID,
                user_id=owner,
                gate_agent_ids=[],
            ):
                pass
        except Exception:
            pass

    a_calls_a = call_log.get("a", 0)
    a_calls_b = call_log.get("b", 0)
    assert a_calls_a >= 1 and a_calls_b >= 1, (
        f"wave-0 workers must have run on instance A before the crash: {call_log}"
    )

    # The interrupt landed the run TERMINAL-FAILED (the Phase-50 premise: a user resumes
    # a run that reached the ``failed`` terminal, not a still-non-terminal restart).
    from app.models.workflow import WorkflowRun

    row = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    row.status = "failed"
    session.commit()
    runs_before = session.query(WorkflowRun).count()

    # ── Instance B: user resume through the endpoint's thin wrapper (NOT resume_run
    # directly, NOT a hand-copied launch ladder) over the SAME durable DB ─────────────
    with _ResumeHarness(session, call_log, fail_on=set(), db_engine=db_engine) as h:
        engine_b = h.make_engine()
        rc = _wire_user_resume_drive(monkeypatch, db_engine, engine_b)
        await rc._drive_user_resume(run_id, user=_ResumeUser(owner))

    # (a) cursor evidence — the completed wave-0 workers were NOT re-invoked on resume.
    assert call_log.get("a", 0) == a_calls_a, f"part_a re-invoked on resume: {call_log}"
    assert call_log.get("b", 0) == a_calls_b, f"part_b re-invoked on resume: {call_log}"
    # wave-1 workers ran on resume (the incomplete wave was re-entered).
    assert call_log.get("c", 0) >= 1 and call_log.get("d", 0) >= 1, (
        f"wave-1 workers did not run on resume: {call_log}"
    )

    # (b) the deliverable completes — all four files exist on the recovered sandbox.
    from app.agents.sandbox import RunSandbox

    root = RunSandbox(owner, run_id).root
    produced = {
        p.name for p in root.rglob("*.txt")
        if _PART_RE.fullmatch(p.name) and ".worktrees" not in p.parts
    }
    assert produced == {"part_a.txt", "part_b.txt", "part_c.txt", "part_d.txt"}, (
        f"user resume did not complete every wave file: {sorted(produced)}"
    )

    # (c) terminal status reconciled from the durable tail to ``completed``.
    session.expire_all()
    row2 = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    assert row2.status == "completed", (
        f"user resume must reconcile the terminal status to completed: {row2.status!r}"
    )

    # (d) family coherence — SAME run id, parent link untouched, NO new WorkflowRun row.
    assert row2.parent_run_id is None
    assert session.query(WorkflowRun).count() == runs_before, (
        "user resume must NOT mint a new WorkflowRun row (Pitfall 5)"
    )
    session.close()


@pytest.mark.asyncio
async def test_failed_run_with_open_gate_resumes_into_gate(monkeypatch):
    """A ``failed`` run carrying a durable OPEN review gate resumes INTO the gate — the 49
    classifier (``_first_incomplete_step`` open-gate override → ``gate_reentry`` sentinel →
    consumer) re-enters ``_run_review_gate`` for the gated agent with ZERO endpoint
    special-casing, rather than running the gated agent's model or completing past it."""
    session, db_engine = _make_session()
    run_id = f"ug-{uuid.uuid4().hex[:8]}"
    owner = "ug-user"
    ws = "ws-ug"
    _seed_workflow_run(
        session, run_id, owner=owner, status="failed", workspace_id=ws
    )
    gate_key = f"{run_id}:sample-wave-plan"
    await _seed_open_review_gate(session, run_id, owner, ws, gate_key)

    from app.models.workflow import WorkflowRun

    runs_before = session.query(WorkflowRun).count()

    gate_spy: dict = {"agent_ids": []}

    with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h:
        engine_b = h.make_engine()

        # The gated agent must be a genuinely-gated agent for the reentry consumer's
        # ``_should_gate`` fence (Phase-49 config, not Phase-50 scope). Mark the plan spec
        # statically gated — exactly as a real gated agent (e.g. prototype-specify) carries
        # ``gate: Human_Gate`` — so the durable open gate re-enters via the REAL gate seam.
        for _spec in h.specs:
            if getattr(_spec, "id", None) == "sample-wave-plan":
                _spec.gate = "Human_Gate"

        # Spy the gate seam: record which agent re-entered the gate, then REJECT so the run
        # stops AT the gate (the deterministic offline stand-in for "parks awaiting the
        # human" — it must NOT complete the deliverable past the gate).
        async def _spy_gate(*, pipeline_run_id, agent_id, agent_name, output, redoable,
                            update_specs_eligible, artifact_kind, cancel_event, **kw):
            gate_spy["agent_ids"].append(agent_id)
            yield {"type": "review_gate_ready",
                   "data": {"gate_key": f"{pipeline_run_id}:{agent_id}"}}
            yield {"type": "_gate_rejected"}

        engine_b._run_review_gate = _spy_gate  # type: ignore[assignment]

        rc = _wire_user_resume_drive(monkeypatch, db_engine, engine_b)
        await rc._drive_user_resume(run_id, user=_ResumeUser(owner))

    # The resume RE-ENTERED the gate for the gated agent (49 classifier composed) — the
    # gated agent's model was skipped (gate-reentry mode reconstructs output; never a
    # ``create_runner`` for that step) and the wave never ran.
    assert gate_spy["agent_ids"] == ["sample-wave-plan"], (
        f"resume must re-enter the gate for the gated agent: {gate_spy}"
    )

    session.expire_all()
    row = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    # Rejected AT the gate → cancelled; the run did NOT complete past the gate.
    assert row.status == "cancelled", (
        f"a run parked/stopped at the re-entered gate must not complete past it: {row.status!r}"
    )
    # Family coherence — no new WorkflowRun row minted by the resume.
    assert session.query(WorkflowRun).count() == runs_before
    session.close()


# ===========================================================================
# BUG-R01 / BUG-R02 (quick 260719-ghn) — the od_prototype id-alias empty-roster
# bail that black-holes restart clarify-answers and gate-approvals.
#
# On restart both re-arm drivers rebuild the roster with
# ``get_pipeline_agents(wr.type)`` using the RAW stored pipeline type. ``od_prototype``
# is a routing id-alias with NO AGENT.md of its own (its agents declare
# ``pipeline_type: prototype``), so ``get_pipeline_agents("od_prototype") == []`` →
# the driver logs "empty agent list" and EARLY-RETURNS before re-creating the
# coroutine that awaits the gate/clarify response → every restart od_prototype
# clarify-answer and gate-approve is a silent black hole. The fresh path is immune
# because ``_execute_impl`` keys off the RESOLVED ``compiled.id``. The fix resolves
# the id-alias before the roster lookup in BOTH drivers:
# ``get_pipeline_agents(resolve_alias(pipeline_type))``.
#
# These two tests seed a durable ``od_prototype`` run parked at a gate and drive the
# REAL ``get_pipeline_agents`` — ``_ResumeHarness._patched_gpa`` delegates to the
# real registry for any non-fixture type (``od_prototype`` != ``sample_wave``), so
# the id-alias path IS exercised (the coverage hole every existing test misses by
# using the always-non-empty ``sample_wave`` fixture). Each asserts the driver
# proceeds PAST the roster bail into the offset / replay re-entry instead of
# early-returning. RED on pre-fix HEAD (empty roster → bail → downstream never
# reached); GREEN after the alias is resolved.
# ===========================================================================


class _ReachedPastRoster(Exception):
    """Sentinel: the driver progressed past the empty-roster check (did NOT bail)."""


@pytest.mark.asyncio
async def test_resume_run_od_prototype_alias_resolves_roster_not_bail():
    """BUG-R02: a review-gate-parked ``od_prototype`` run, on restart re-arm, must
    resolve the ``od_prototype``→``prototype`` id-alias for the roster lookup and
    reach the resume-offset re-entry — NOT bail at the empty-agent-list check that
    black-holes the gate approval. Drives the REAL ``get_pipeline_agents`` (non-
    fixture type), so the missing ``resolve_alias`` is visible."""
    session, db_engine = _make_session()
    run_id = f"odp-{uuid.uuid4().hex[:8]}"
    owner = "odp-user"
    ws = "ws-odp"
    _seed_workflow_run(
        session, run_id, owner=owner, status="waiting_for_user",
        type_="od_prototype", workspace_id=ws,
    )
    gate_key = f"{run_id}:prototype-specify"
    await _seed_open_review_gate(session, run_id, owner, ws, gate_key)

    with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h:
        engine = h.make_engine()

        # Precondition: the harness is NOT masking the bug — the REAL registry gives
        # an EMPTY roster for the raw id-alias and 5 agents for the resolved base.
        import agents.registry as _reg

        assert _reg.get_pipeline_agents("od_prototype") == [], (
            "precondition: raw od_prototype roster must be empty (the bug's cause)"
        )
        assert len(_reg.get_pipeline_agents("prototype")) == 5, (
            "precondition: the resolved prototype roster must be non-empty (5 agents)"
        )

        reached = {"offset": False}

        async def _spy_offset(*a, **k):
            reached["offset"] = True
            raise _ReachedPastRoster()

        engine._compute_resume_offset = _spy_offset  # type: ignore[assignment]

        try:
            await engine.resume_run(run_id)
        except _ReachedPastRoster:
            pass

    assert reached["offset"] is True, (
        "resume_run must resolve od_prototype→prototype and reach the resume-offset "
        "re-entry; pre-fix it bails at the empty-agent-list check (BUG-R02 black hole)"
    )
    session.close()


@pytest.mark.asyncio
async def test_replay_clarify_run_od_prototype_alias_resolves_roster_not_bail():
    """BUG-R01: a clarify-parked ``od_prototype`` run, on restart re-arm, must
    resolve the ``od_prototype``→``prototype`` id-alias for the roster lookup and
    reach the replay drive (``_drive_resumed_stream``) — NOT bail at the empty-
    agent-list check that black-holes the clarify answer. Drives the REAL
    ``get_pipeline_agents`` (non-fixture type)."""
    session, db_engine = _make_session()
    run_id = f"odc-{uuid.uuid4().hex[:8]}"
    owner = "odc-user"
    ws = "ws-odc"
    _seed_workflow_run(
        session, run_id, owner=owner, status="waiting_for_user",
        type_="od_prototype", workspace_id=ws,
    )
    questions = [{
        "question_id": "r1_q1", "question_text": "Scope?",
        "options": ["a", "b"], "answer_type": "single_choice",
        "impact_level": "high", "ambiguity_category": "Functional Scope",
    }]
    await _seed_open_questionnaire_gate(session, run_id, owner, ws, questions, round_num=1)

    with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h:
        engine = h.make_engine()

        import agents.registry as _reg

        assert _reg.get_pipeline_agents("od_prototype") == [], (
            "precondition: raw od_prototype roster must be empty (the bug's cause)"
        )
        assert len(_reg.get_pipeline_agents("prototype")) == 5, (
            "precondition: the resolved prototype roster must be non-empty (5 agents)"
        )

        reached = {"drive": False}

        async def _spy_drive(rid, **k):
            reached["drive"] = True

        engine._drive_resumed_stream = _spy_drive  # type: ignore[assignment]

        await engine._replay_clarify_run(run_id)

    assert reached["drive"] is True, (
        "_replay_clarify_run must resolve od_prototype→prototype and reach the replay "
        "drive; pre-fix it bails at the empty-agent-list check (BUG-R01 black hole)"
    )
    session.close()


# ===========================================================================
# BUG-R05 (quick 260719-hd5) — the offset-0 gate-at-step-0 preamble re-run.
#
# An od_prototype run parked at the SPEC review gate resumes with offset 0 (the gated
# agent ``prototype-specify`` is step INDEX 0). Pre-fix, ``_execute_impl`` decides "am I
# resuming?" with ``_resuming = _resume_from > 0`` — which reads offset 0 as a FRESH
# start, so ``skip_planner`` is False, the planner + auto-clarifier RE-RUN, and the
# ClarifyEngine re-parks the run at a NEW questionnaire BEFORE the 49-02 gate-reentry
# block (armed inside ``if _is_resume:``) is ever reached. The whole pre-crash pipeline
# is wastefully re-run and the original gate context is lost. The fix keys the
# planner/clarify skip (and the graph hydration) on ``_is_resume`` — True for EVERY
# resume, offset 0 or >0 — so an offset-0 gate re-entry is recognised as a resume.
#
# The coverage hole this closes: ``test_failed_run_with_open_gate_resumes_into_gate``
# (:3110) seeds a step-0 gate and drives the REAL resume tier, but stubs the planner to
# always return "PROCEED" (``_ResumeHarness._fake_planner``), which — pre-fix — lets the
# offset-0 resume fall THROUGH to the gate (a PROCEED verdict skips the clarify block), so
# the re-clarify never manifests. This test is the SAME shape with the ONLY change that
# matters: the planner returns CLARIFY_REQUIRED (the live conjunction), so pre-fix the
# offset-0 resume diverts into the planner + clarifier instead of re-entering the gate.
# ===========================================================================


@pytest.mark.asyncio
async def test_offset0_gate_resume_does_not_replan_or_reclarify(monkeypatch):
    """BUG-R05: a run parked at a review gate on the FIRST agent (step INDEX 0) resumes
    with offset 0 and MUST re-enter the gate — NOT re-run the planner + auto-clarifier.

    Pre-fix (``_resuming = _resume_from > 0`` ⇒ ``0 > 0`` False) the offset-0 resume is
    mis-read as fresh: ``skip_planner`` is False, the planner runs, returns
    CLARIFY_REQUIRED, and the auto-clarifier re-parks the run at a new questionnaire
    BEFORE the gate-reentry block. Post-fix (``_resuming = _is_resume`` True) the planner
    + clarifier are skipped and the step-0 review gate re-enters.

    RED on pre-fix HEAD (planner re-runs AND the clarifier re-parks); GREEN after the fix
    (both skipped, the gate re-enters for the step-0 agent). This is the {step-0 gate} ∧
    {planner→CLARIFY_REQUIRED} conjunction the :3110 test hides with its PROCEED fake.
    """
    session, db_engine = _make_session()
    run_id = f"r5-{uuid.uuid4().hex[:8]}"
    owner = "r5-user"
    ws = "ws-r5"
    # A run parked at the step-0 review gate (mirrors the live od_prototype spec-gate:
    # the gated agent is ``ordered_agents[0]``; sample-wave-plan is fixture step index 0).
    _seed_workflow_run(session, run_id, owner=owner, status="failed", workspace_id=ws)
    gate_key = f"{run_id}:sample-wave-plan"
    await _seed_open_review_gate(session, run_id, owner, ws, gate_key)

    from app.models.workflow import WorkflowRun

    runs_before = session.query(WorkflowRun).count()

    planner_calls = {"n": 0}
    clarify_runs = {"n": 0}
    gate_spy: dict = {"agent_ids": []}

    with _ResumeHarness(session, {}, fail_on=set(), db_engine=db_engine) as h:
        engine_b = h.make_engine()

        # The step-0 agent must be genuinely gated for the reentry consumer's
        # ``_should_gate`` fence — exactly as prototype-specify carries ``gate:
        # Human_Gate`` — so the durable open gate re-enters via the REAL gate seam.
        for _spec in h.specs:
            if getattr(_spec, "id", None) == "sample-wave-plan":
                _spec.gate = "Human_Gate"

        # THE conjunction :3110 breaks with its PROCEED fake: the planner returns
        # CLARIFY_REQUIRED, so pre-fix (``skip_planner`` False at offset 0) the run
        # diverts into the auto-clarifier and re-parks at a NEW questionnaire.
        async def _clarify_required_planner(
            user_message, pipeline_run_id, model_id, cancel_event,
            ptype="custom", **kw,
        ):
            planner_calls["n"] += 1
            return engine_b._default_planning_context(user_message), "CLARIFY_REQUIRED"

        engine_b._run_planner = _clarify_required_planner  # type: ignore[assignment]

        # Stub ClarifyEngine so the re-clarify is OBSERVABLE without blocking the test on
        # the real ``await event.wait()`` (the live re-park hang). It records that it ran
        # and emits the spurious second ``questionnaire_ready``, then returns.
        import agents.execution_engine.clarify_engine as _clar_mod

        class _FakeClarify:
            def __init__(self):
                self._usage_sink = None

            async def run(
                self, pipeline_run_id, planning_context, ws_send, *,
                owner_id=None, workspace_id=None, max_rounds=1,
                replay_questions=None, replay_round=None,
            ):
                clarify_runs["n"] += 1
                await ws_send({
                    "type": "questionnaire_ready",
                    "data": {"pipeline_run_id": pipeline_run_id, "round": 1},
                })
                return planning_context

        monkeypatch.setattr(_clar_mod, "ClarifyEngine", _FakeClarify)

        # Spy the gate seam: record which agent re-entered the gate, then REJECT so the
        # run stops AT the gate (the deterministic stand-in for "parks awaiting the
        # human"). Same shape as the :3110 gate spy.
        async def _spy_gate(*, pipeline_run_id, agent_id, agent_name, output, redoable,
                            update_specs_eligible, artifact_kind, cancel_event, **kw):
            gate_spy["agent_ids"].append(agent_id)
            yield {"type": "review_gate_ready",
                   "data": {"gate_key": f"{pipeline_run_id}:{agent_id}"}}
            yield {"type": "_gate_rejected"}

        engine_b._run_review_gate = _spy_gate  # type: ignore[assignment]

        rc = _wire_user_resume_drive(monkeypatch, db_engine, engine_b)
        await rc._drive_user_resume(run_id, user=_ResumeUser(owner))

    # POST-fix (GREEN): the offset-0 gate resume is recognised as a resume — the planner
    # and the auto-clarifier are SKIPPED and the step-0 review gate re-enters.
    assert planner_calls["n"] == 0, (
        f"offset-0 gate resume must NOT re-run the planner — pre-fix it mis-reads offset "
        f"0 as a fresh start and re-plans (BUG-R05): {planner_calls}"
    )
    assert clarify_runs["n"] == 0, (
        f"offset-0 gate resume must NOT re-clarify / re-park at a new questionnaire — "
        f"pre-fix the auto-clarifier re-runs (BUG-R05): {clarify_runs}"
    )
    assert gate_spy["agent_ids"] == ["sample-wave-plan"], (
        f"offset-0 gate resume must RE-ENTER the step-0 review gate (not re-plan / "
        f"re-clarify): {gate_spy}"
    )
    # Family coherence — no new WorkflowRun row minted by the resume.
    assert session.query(WorkflowRun).count() == runs_before
    session.close()


# ===========================================================================
# BUG-R03 — the resume tier persists the terminal OUTPUT-bearing columns
#   (output / agent_outputs / token_usage / duration / deliverable_*), not
#   only status. Coverage hole: NO prior resume test asserted these columns.
# ===========================================================================


def test_apply_terminal_output_columns_populates_all_columns():
    """The SHARED event→WorkflowRun output-column mapping (the SOLE writer for BOTH the
    launch driver and the two resume entry points, INV-12) populates output / agent_outputs
    / token_usage / duration / deliverable_* from a durable ``run_events`` tail — proven on
    a REAL registry key's agent ids (user_stories, non-aliased). BUG-R03 coverage."""
    import json as _json

    from app.api.run_commands import _apply_terminal_output_columns
    from app.models.workflow import WorkflowRun

    # A user_stories-shaped durable tail: two of the real pipeline agents + a clean terminal.
    events = [
        ("agent_start", {"agent_id": "domain-analyst", "name": "Domain Analyst", "role": "Analyst", "icon": "🧠"}),
        ("agent_chunk", {"chunk": "domain analysis body"}),
        ("agent_complete", {"duration": 1.5, "input_tokens": 100, "output_tokens": 50,
                             "total_tokens": 150, "cache_read_tokens": 10, "cache_write_tokens": 5}),
        ("agent_start", {"agent_id": "backlog-compiler", "name": "Backlog Compiler", "role": "Compiler", "icon": "📋"}),
        ("agent_chunk", {"chunk": "# Backlog\n- story 1"}),
        ("agent_complete", {"duration": 2.0, "input_tokens": 200, "output_tokens": 80,
                             "total_tokens": 280, "cache_read_tokens": 0, "cache_write_tokens": 0}),
        ("pipeline_complete", {"final_output": "# Backlog\n- story 1\n- story 2",
                               "deliverable_mimetype": "text/markdown",
                               "deliverable_filename": "backlog.md"}),
    ]
    wr = WorkflowRun(
        id="bugr03-helper", user_id="o", owner_id="o",
        status="completed", type="user_stories", input="brief",
    )
    _apply_terminal_output_columns(wr, events, model_id="claude-x", duration_seconds=3.5)

    assert wr.output == "# Backlog\n- story 1\n- story 2", "final_output → output column"
    agents = _json.loads(wr.agent_outputs)
    assert [a["agent_id"] for a in agents] == ["domain-analyst", "backlog-compiler"], (
        f"agent_outputs must carry every completed agent: {agents}"
    )
    assert agents[0]["output"] == "domain analysis body"
    tu = _json.loads(wr.token_usage)
    assert tu["total_input_tokens"] == 300 and tu["total_output_tokens"] == 130
    assert tu["total_tokens"] == 430 and tu["total_cache_read_tokens"] == 10
    assert wr.duration == 3.5
    assert wr.deliverable_mimetype == "text/markdown"
    assert wr.deliverable_filename == "backlog.md"
    assert wr.model_id == "claude-x"


@pytest.mark.asyncio
async def test_user_resume_persists_output_columns(monkeypatch):
    """END-TO-END (BUG-R03): a run crashed mid-build then USER-resumed to completion persists
    the terminal ``output`` column (the headline bug column) — not only ``status``. Drives the
    real ``_drive_user_resume`` → ``_reconcile_terminal_status`` path over the same durable DB,
    then asserts ``output`` is POPULATED from the durable ``pipeline_complete.final_output``
    (pre-fix it is empty — the resume tier wrote status but no output columns; the coverage
    hole). The per-agent columns (agent_outputs/token_usage/duration) ride the SAME mapping and
    are asserted deterministically on a real agent_complete tail in
    ``test_apply_terminal_output_columns_populates_all_columns`` — the ``sample_wave`` fixture
    is a wave-fanout pipeline that emits ``subagent_*`` events, not per-agent ``agent_complete``,
    so ``final_output``→``output`` is its populated column."""
    from app.models.workflow import WorkflowRun

    session, db_engine = _make_session()
    run_id = f"r03-{uuid.uuid4().hex[:8]}"
    owner = "r03-user"
    _seed_workflow_run(session, run_id, owner=owner, status="generating")

    call_log: dict[str, int] = {}

    # ── Instance A: interrupted mid-wave — wave 0 completes, wave 1 crashes on entry ──
    with _ResumeHarness(
        session, call_log, fail_on=set(), db_engine=db_engine, raise_on_fanout_call=2
    ) as h:
        engine_a = h.make_engine()
        try:
            async for _ev in engine_a._execute_impl(
                agents=list(h.specs), user_message="Run the wave workflow.",
                pipeline_run_id=run_id, pipeline_type=_FIXTURE_ID, user_id=owner,
                gate_agent_ids=[],
            ):
                pass
        except Exception:
            pass

    row = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    row.status = "failed"
    session.commit()
    # The bug premise: an interrupted run has an EMPTY output column going into resume.
    assert not row.output, "precondition: output column empty before resume"

    # ── Instance B: user resume to completion over the SAME durable DB ────────────────
    with _ResumeHarness(session, call_log, fail_on=set(), db_engine=db_engine) as h:
        engine_b = h.make_engine()
        rc = _wire_user_resume_drive(monkeypatch, db_engine, engine_b)
        await rc._drive_user_resume(run_id, user=_ResumeUser(owner))

    session.expire_all()
    row2 = session.query(WorkflowRun).filter(WorkflowRun.id == run_id).first()
    assert row2.status == "completed", f"status must reconcile to completed: {row2.status!r}"
    # BUG-R03 — the terminal ``output`` column is now POPULATED on resume-completion (the
    # durable pipeline_complete.final_output), where pre-fix the resume tier wrote none.
    assert row2.output, (
        "BUG-R03: resume-completion must persist the output column (empty pre-fix)"
    )
    for part in ("part_a.txt", "part_c.txt"):
        assert part in row2.output, f"output must carry the resumed deliverable: {part}"
    session.close()


@pytest.mark.asyncio
async def test_restart_resume_fires_output_persist_hook(monkeypatch):
    """BUG-R03 branch-(b): the RESTART auto-resume drive (``resume_run`` → the SHARED
    ``_drive_resumed_stream``) FIRES the injected ``_resume_output_persist_sink`` with the
    run_id in its ``finally`` — the ports-and-adapters hook the app arms (app/main.py) so the
    engine (which cannot import ``app.*``) persists the resume-completion output columns.
    Pre-fix the finally does no output-column persistence → the spy is never called (RED)."""
    session, db_engine = _make_session()
    run_id = f"r03b-{uuid.uuid4().hex[:8]}"
    owner = "r03b-user"
    _seed_workflow_run(session, run_id, owner=owner, status="generating")

    call_log: dict[str, int] = {}

    with _ResumeHarness(
        session, call_log, fail_on=set(), db_engine=db_engine, raise_on_fanout_call=2
    ) as h:
        engine_a = h.make_engine()
        try:
            async for _ev in engine_a._execute_impl(
                agents=list(h.specs), user_message="Run the wave workflow.",
                pipeline_run_id=run_id, pipeline_type=_FIXTURE_ID, user_id=owner,
                gate_agent_ids=[],
            ):
                pass
        except Exception:
            pass

    fired: list[str] = []

    async def _spy_persist(rid: str) -> None:
        fired.append(rid)

    with _ResumeHarness(session, call_log, fail_on=set(), db_engine=db_engine) as h:
        engine_b = h.make_engine()
        # Arm the persistence hook exactly as app/main.py arms it on the restore engine.
        engine_b._resume_output_persist_sink = _spy_persist
        await engine_b.resume_run(run_id)

    assert fired == [run_id], (
        f"restart auto-resume must fire _resume_output_persist_sink(run_id) from "
        f"_drive_resumed_stream's finally (branch b): {fired}"
    )
    session.close()


# ===========================================================================
# BUG-2 Cond A (quick-260720-ec4) — Stop cancels a run parked at CLARIFY
# ===========================================================================


@pytest.mark.asyncio
async def test_stop_at_clarify_yields_pipeline_cancelled(monkeypatch):
    """A run PARKED at clarify (the engine drain loop draining a ClarifyEngine that
    never emits questionnaire_complete) honors the Stop button: setting the shared
    cancel_event makes the drain loop cancel the clarify task and yield the existing
    pipeline_cancelled terminal within the 1s heartbeat.

    RED pre-fix: the drain loop ignores cancel_event → the generator never yields
    pipeline_cancelled → the bounded asyncio.wait_for raises TimeoutError.

    Per the plan-checker: the ClarifyEngine here is a PARKING FAKE (emits
    questionnaire_ready then blocks forever) — the real ClarifyEngine.run does an LLM
    call and would HANG offline, muddying the RED→GREEN signal.
    """
    import asyncio

    import agents.execution_engine.clarify_engine as _clar_mod

    session, db_engine = _make_session()
    run_id = f"rr-{uuid.uuid4().hex[:8]}"
    owner = "rr-clarify-user"

    # A ClarifyEngine that emits ONE questionnaire_ready then PARKS forever (never
    # emits questionnaire_complete) — the offline stand-in for "awaiting the user".
    class _ParkingClarify:
        def __init__(self):
            self._usage_sink = None

        async def run(
            self, pipeline_run_id, planning_context, ws_send, *,
            owner_id=None, workspace_id=None, max_rounds=1,
            replay_questions=None, replay_round=None,
        ):
            await ws_send({
                "type": "questionnaire_ready",
                "data": {"pipeline_run_id": pipeline_run_id, "round": 1},
            })
            await asyncio.Event().wait()  # PARK — never resolves (no answers submitted)
            return planning_context  # pragma: no cover

    monkeypatch.setattr(_clar_mod, "ClarifyEngine", _ParkingClarify)

    with _ResumeHarness(
        session, call_log={}, fail_on=set(), db_engine=db_engine, clarify_mode="auto"
    ) as h:
        engine = h.make_engine()

        # Force the planner to route to clarify (missing_information non-empty) so the
        # run parks AT clarify, before any domain agent / fan-out runs.
        async def _clarify_planner(
            user_message, pipeline_run_id, model_id, cancel_event, ptype="custom", **kw
        ):
            return (
                {
                    "execution_gate": "CLARIFY_REQUIRED",
                    "missing_information": ["target audience"],
                    "explicit_constraints": [],
                    "pipeline_type": ptype,
                },
                "CLARIFY_REQUIRED",
            )

        engine._run_planner = _clarify_planner  # type: ignore[assignment]

        ev = asyncio.Event()
        saw_cancelled = False

        agen = engine._execute_impl(
            agents=list(h.specs),
            user_message="Run the wave workflow.",
            pipeline_run_id=run_id,
            pipeline_type=_FIXTURE_ID,
            user_id=owner,
            gate_agent_ids=[],
            cancel_event=ev,
        )

        async def _drive():
            nonlocal saw_cancelled
            async for evt in agen:
                if evt.get("type") == "questionnaire_ready":
                    ev.set()  # press Stop the instant the questionnaire parks
                if evt.get("type") == "pipeline_cancelled":
                    saw_cancelled = True
                    break

        # RED pre-fix: the drain loop never observes ev → this times out.
        await asyncio.wait_for(_drive(), timeout=8)
        await agen.aclose()

    assert saw_cancelled, "Stop at clarify must yield the existing pipeline_cancelled terminal"
    session.close()
