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

    def __init__(self, session, call_log, fail_on, *, db_engine=None, raise_on_fanout_call=None, plan=_TASK_PLAN):
        self.session = session
        self.call_log = call_log
        self.fail_on = fail_on
        self.db_engine = db_engine
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
