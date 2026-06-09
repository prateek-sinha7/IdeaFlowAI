"""Wave-0 unit tests for the ``single_shot`` + ``task_loop`` strategies
(07-01 / PARITY-01 acceptance line).

Both strategies are driven from a compiled ``Step`` against a FAKE ``ctx.runner``
(the D-03 KernelServices handle) — no real agent, no Chromium, no kernel/app
import. The fakes script ``run_agent`` to yield a known sequence of event dicts
and record every handle call; the tests assert:

  * single_shot makes exactly ONE run_agent call and re-yields its events
    unchanged ({"type","data"} vocabulary parity, INV-3);
  * task_loop (a) writes spec.md/design.md/tasks.md before the loop, (b) parses
    the 2-task plan via heading_tasks, (c) calls run_agent once per task with the
    per-task task_block set, (d) requests html_skeleton compaction for task-2
    (routed via the registry — stubbed), (e) invokes static_check + render_check
    and the bounded N=2 fix-loop via the handle, (f) yields the engine's
    task_loop_progress + run_agent event vocabulary.
"""

from __future__ import annotations

import pytest

from agents.capabilities import registry as registry_mod
from agents.capabilities.strategies.single_shot import SingleShotStrategy
from agents.capabilities.strategies.task_loop import TaskLoopStrategy
# The fix-selection logic has a SINGLE canonical home — the engine (INV-3/INV-12,
# same import test_phase5_fixloop_selection.py uses). NEVER import it from task_loop.
from agents.execution_engine.engine import _select_issues_to_fix
from agents.workflows.plan import Step, TaskSource

_MAX_FIX_ATTEMPTS = 2


# ===========================================================================
# Fakes — the ctx.runner handle + ctx, plus validator result stand-ins
# ===========================================================================


class _Ctx:
    """Minimal stand-in for ExecutionContext — only ``.runner`` is read."""

    def __init__(self, runner) -> None:
        self.runner = runner


class _FakeStatic:
    def __init__(self, issues=None) -> None:
        self.issues = list(issues or [])
        self.ok = not self.issues

    def summary(self) -> str:
        return f"{len(self.issues)} issue(s)"


class _FakeRender:
    def __init__(self, available=False, ok=True, console_errors=None) -> None:
        self.available = available
        self.ok = ok
        self.console_errors = list(console_errors or [])
        self.page_errors: list[str] = []
        self.nav_results: list = []

    def summary(self) -> str:
        return "render-ok" if self.ok else "render-fail"


class _FakeSandbox:
    """In-memory sandbox: read/write/path_for/root over a dict."""

    def __init__(self, files=None) -> None:
        self._files = dict(files or {})

    def read(self, name):
        return self._files.get(name)

    def write(self, name, text):
        self._files[name] = text

    def path_for(self, name):
        return _FakePath(name in self._files)

    @property
    def root(self):
        return "/tmp/fake"


class _FakePath:
    def __init__(self, exists: bool) -> None:
        self._exists = exists

    def is_file(self) -> bool:
        return self._exists


class _FakeRunner:
    """Fake KernelServices handle scripting run_agent + recording every call."""

    def __init__(
        self,
        *,
        agent_events=None,
        typed_content=None,
        sandbox=None,
        static_results=None,
        render_result=None,
        od_context=None,
        fix_writes_html=None,
    ) -> None:
        self._agent_events = list(agent_events or [])
        self._typed = dict(typed_content or {})
        self.sandbox = sandbox if sandbox is not None else _FakeSandbox()
        # static_check returns the next scripted result each call (defaults clean).
        self._static_results = list(static_results or [_FakeStatic()])
        self._render_result = render_result if render_result is not None else _FakeRender()
        self.od_context = od_context
        # WR-05: when set, run_validation_fix_loop writes this HTML to prototype.html
        # (simulating a fix-loop edit). persist_task_html records the typed dual-write.
        self._fix_writes_html = fix_writes_html
        self.persist_calls: list[dict] = []
        self.cancel_event = None
        self.run_id = "run-1"

        # Call records for assertions.
        self.run_agent_calls: list[dict] = []
        self.fix_calls: list[dict] = []
        self.static_calls = 0

    async def run_agent(
        self, step, ctx, *, task_number=None, total_tasks=None, task_block=None,
        skeleton=None,
    ):
        # WR-01 (07-09): the task-2+ skeleton is passed via a dedicated `skeleton`
        # param (no longer nested into task_block); record it for assertions.
        self.run_agent_calls.append(
            {
                "task_number": task_number,
                "total_tasks": total_tasks,
                "task_block": task_block,
                "skeleton": skeleton,
            }
        )
        for ev in self._agent_events:
            yield ev

    async def run_validation_fix_loop(
        self,
        step,
        *,
        task_num,
        total_tasks,
        agent_id="prototype-build",
        baseline_static=None,
        baseline_console=None,
        user_instruction=None,
        label="",
    ):
        """Drive the SAME path real runs take (the engine's run_validation_fix_loop).

        Reproduces the bounded N=2 decision the strategy delegates to the engine:
        read the scripted static/render results, compute the fix list via the SINGLE
        engine selection home, and for each failing attempt (max 2) record a fix call
        in the ``{"task_num","attempt","agent_id","message"}`` shape the assertions read.
        """
        html_path = self.sandbox.path_for("prototype.html")
        if not html_path.is_file():
            return

        # WR-05: simulate a fix-loop edit by writing the scripted fixed HTML to disk
        # (the real fix sub-agent edits prototype.html as a side effect).
        if self._fix_writes_html is not None:
            self.sandbox.write("prototype.html", self._fix_writes_html)

        attempt = 0
        while True:
            sres = self.static_check(html_path)
            rres = await self.render_check(html_path)
            error_lines = _select_issues_to_fix(
                sres, rres, baseline_static, baseline_console
            )
            if not error_lines:
                return
            if attempt >= _MAX_FIX_ATTEMPTS:
                return
            attempt += 1
            fix_message = (
                f"=== VALIDATION ERRORS (fix prototype.html) ===\n"
                + "\n".join(f"- {e}" for e in error_lines)
            )
            self.fix_calls.append(
                {"task_num": task_num, "attempt": attempt, "agent_id": agent_id, "message": fix_message}
            )

    def latest_typed_content(self, producer_step):
        return self._typed.get(producer_step)

    async def persist_task_html(self, task_num, agent_id="prototype-build"):
        """Typed dual-write — record the call + mirror the on-disk HTML into the typed
        graph (so latest_typed_content("prototype-build") reflects the persisted HTML)."""
        html = self.sandbox.read("prototype.html")
        self.persist_calls.append({"task_num": task_num, "html": html})
        if html:
            self._typed["prototype-build"] = html

    def static_check(self, html_path):
        self.static_calls += 1
        idx = min(self.static_calls - 1, len(self._static_results) - 1)
        return self._static_results[idx]

    async def render_check(self, html_path):
        return self._render_result


# ===========================================================================
# single_shot
# ===========================================================================


@pytest.mark.asyncio
async def test_single_shot_reyields_events_in_order() -> None:
    events = [
        {"type": "agent_start", "data": {"agent_id": "x"}},
        {"type": "agent_chunk", "data": {"text": "hi"}},
        {"type": "agent_complete", "data": {"agent_id": "x"}},
    ]
    runner = _FakeRunner(agent_events=events)
    ctx = _Ctx(runner)
    step = Step(agent_id="prototype-specify", strategy="single_shot")

    out = [ev async for ev in SingleShotStrategy().run(step, ctx)]

    assert out == events  # same {"type","data"} dicts, in order (INV-3)
    assert len(runner.run_agent_calls) == 1  # exactly one run_agent call


@pytest.mark.asyncio
async def test_single_shot_name() -> None:
    assert SingleShotStrategy().name == "single_shot"


# ===========================================================================
# task_loop
# ===========================================================================


_TWO_TASK_PLAN = (
    "## Task 1: Build shell\n"
    "Write the HTML shell.\n\n"
    "## Task 2: Add dashboard\n"
    "Add the dashboard page.\n"
)


def _two_task_step() -> Step:
    return Step(
        agent_id="prototype-build",
        strategy="task_loop",
        task_source=TaskSource(kind="parsed", parser="heading_tasks"),
        compaction="html_skeleton",
    )


@pytest.mark.asyncio
async def test_task_loop_writes_reference_files_before_loop() -> None:
    sandbox = _FakeSandbox(files={"prototype.html": "<html></html>"})
    runner = _FakeRunner(
        agent_events=[{"type": "agent_chunk", "data": {"text": "."}}],
        typed_content={
            "prototype-specify": "the spec text",
            "prototype-plan": _TWO_TASK_PLAN,
        },
        sandbox=sandbox,
        od_context={"template_body": "TPL", "ds_body": "DS"},
    )
    ctx = _Ctx(runner)

    _ = [ev async for ev in TaskLoopStrategy().run(_two_task_step(), ctx)]

    assert sandbox.read("spec.md") == "the spec text"
    assert sandbox.read("tasks.md") == _TWO_TASK_PLAN
    design = sandbox.read("design.md")
    assert design is not None and "ACTIVE TEMPLATE" in design and "ACTIVE DESIGN SYSTEM" in design


@pytest.mark.asyncio
async def test_task_loop_parses_two_tasks_one_run_agent_each() -> None:
    sandbox = _FakeSandbox(files={"prototype.html": "<html></html>"})
    runner = _FakeRunner(
        agent_events=[{"type": "agent_chunk", "data": {"text": "."}}],
        typed_content={"prototype-plan": _TWO_TASK_PLAN},
        sandbox=sandbox,
    )
    ctx = _Ctx(runner)

    _ = [ev async for ev in TaskLoopStrategy().run(_two_task_step(), ctx)]

    assert len(runner.run_agent_calls) == 2  # one sub-agent per task
    # Per-task task_block carries ONLY that task's ## Task N: block.
    assert "Task 1: Build shell" in runner.run_agent_calls[0]["task_block"]
    assert "Task 2: Add dashboard" in runner.run_agent_calls[1]["task_block"]
    # Task 1's block does not leak task 2's heading.
    assert "Task 2: Add dashboard" not in runner.run_agent_calls[0]["task_block"]
    assert runner.run_agent_calls[0]["total_tasks"] == 2


@pytest.mark.asyncio
async def test_task_loop_requests_html_skeleton_compaction_for_task_2() -> None:
    # Register a fake html_skeleton compaction impl via the registry seam so the
    # task-2+ compaction call routes through resolve("compaction","html_skeleton").
    compact_calls: list[str] = []

    class _FakeCompactor:
        name = "html_skeleton"

        def compact(self, html):
            compact_calls.append(html)
            return "SKELETON"

    registry_mod.install()
    registry_mod._IMPLS[("compaction", "html_skeleton")] = _FakeCompactor()
    try:
        # WR-01 (07-09): the strategy sources the task-2 skeleton from the TYPED GRAPH
        # (latest_typed_content("prototype-build")). persist_task_html (called after each
        # task) dual-writes the on-disk prototype.html into the typed graph, so the task-2
        # compaction reads the persisted task-1 HTML.
        sandbox = _FakeSandbox(files={"prototype.html": "<html>page1 full content</html>"})
        runner = _FakeRunner(
            agent_events=[{"type": "agent_chunk", "data": {"text": "."}}],
            typed_content={"prototype-plan": _TWO_TASK_PLAN},
            sandbox=sandbox,
        )
        ctx = _Ctx(runner)

        _ = [ev async for ev in TaskLoopStrategy().run(_two_task_step(), ctx)]

        # Compaction requested exactly once (task-2 only, not task-1) on the persisted
        # TYPED HTML (written by persist_task_html after task 1).
        assert len(compact_calls) == 1
        assert compact_calls[0] == "<html>page1 full content</html>"
        # WR-01: the task-2 skeleton rides the dedicated `skeleton` param (NOT nested
        # into the task block) so the engine emits the legacy STANDALONE skeleton block.
        assert runner.run_agent_calls[1]["skeleton"] == "SKELETON"
        assert runner.run_agent_calls[0]["skeleton"] is None
        # The task block itself no longer carries the nested skeleton.
        assert "SKELETON" not in (runner.run_agent_calls[1]["task_block"] or "")
    finally:
        registry_mod._IMPLS.pop(("compaction", "html_skeleton"), None)


_ONE_TASK_PLAN = "## Task 1: Build shell\nWrite the HTML shell.\n"


def _one_task_step() -> Step:
    return Step(
        agent_id="prototype-build",
        strategy="task_loop",
        task_source=TaskSource(kind="parsed", parser="heading_tasks"),
        compaction="html_skeleton",
    )


@pytest.mark.asyncio
async def test_task_loop_repersists_typed_artifact_after_fix_changes_html() -> None:
    """WR-05 (07-09): when the fix-loop edits prototype.html, the typed build artifact is
    RE-PERSISTED so the consumer (prototype-validate) reads the FIXED HTML.

    The fix-loop edits prototype.html on disk but does NOT touch the typed graph. The
    legacy build loop re-wrote the typed artifact when ``fixed_html != task_html``; this
    test drives a one-task build whose fix-loop rewrites the HTML and asserts (a) persist
    is called a SECOND time after the fix and (b) latest_typed_content reflects the post-fix
    bytes (not the pre-fix ones).
    """
    # static_check fails first (triggers a fix), then clean — so the fix-loop runs once.
    sandbox = _FakeSandbox(files={"prototype.html": "<html>PRE-FIX</html>"})
    runner = _FakeRunner(
        agent_events=[{"type": "agent_chunk", "data": {"text": "."}}],
        typed_content={"prototype-plan": _ONE_TASK_PLAN},
        sandbox=sandbox,
        static_results=[_FakeStatic(issues=["E1"]), _FakeStatic()],
        render_result=_FakeRender(available=False),
        fix_writes_html="<html>POST-FIX (corrected)</html>",
    )
    ctx = _Ctx(runner)

    _ = [ev async for ev in TaskLoopStrategy().run(_one_task_step(), ctx)]

    # persist_task_html called TWICE: once after run_agent (pre-fix), once after the
    # fix-loop changed the HTML (WR-05 re-persist).
    assert len(runner.persist_calls) == 2
    assert runner.persist_calls[0]["html"] == "<html>PRE-FIX</html>"
    assert runner.persist_calls[1]["html"] == "<html>POST-FIX (corrected)</html>"
    # The typed graph now reflects the FIXED HTML (what prototype-validate will read).
    assert runner.latest_typed_content("prototype-build") == "<html>POST-FIX (corrected)</html>"


@pytest.mark.asyncio
async def test_task_loop_no_repersist_when_fix_does_not_change_html() -> None:
    """WR-05 negative: a clean task (no fix edit) re-persists only ONCE (no redundant write)."""
    sandbox = _FakeSandbox(files={"prototype.html": "<html>BUILT</html>"})
    runner = _FakeRunner(
        agent_events=[{"type": "agent_chunk", "data": {"text": "."}}],
        typed_content={"prototype-plan": _ONE_TASK_PLAN},
        sandbox=sandbox,
        static_results=[_FakeStatic()],  # clean → no fix → no disk change
        render_result=_FakeRender(available=False),
    )
    ctx = _Ctx(runner)

    _ = [ev async for ev in TaskLoopStrategy().run(_one_task_step(), ctx)]

    # Only the pre-fix persist ran (the fix-loop made no change → no redundant re-persist).
    assert len(runner.persist_calls) == 1
    assert runner.persist_calls[0]["html"] == "<html>BUILT</html>"


@pytest.mark.asyncio
async def test_task_loop_runs_validation_each_task() -> None:
    sandbox = _FakeSandbox(files={"prototype.html": "<html></html>"})
    runner = _FakeRunner(
        agent_events=[{"type": "agent_chunk", "data": {"text": "."}}],
        typed_content={"prototype-plan": _TWO_TASK_PLAN},
        sandbox=sandbox,
        static_results=[_FakeStatic(), _FakeStatic()],  # both clean → no fix
        render_result=_FakeRender(available=False),
    )
    ctx = _Ctx(runner)

    _ = [ev async for ev in TaskLoopStrategy().run(_two_task_step(), ctx)]

    # static_check called at least once per task (clean → passes, no fix).
    assert runner.static_calls >= 2
    assert runner.fix_calls == []


@pytest.mark.asyncio
async def test_task_loop_bounded_n2_fix_loop_on_persistent_failure() -> None:
    # static_check always reports an issue → the fix-loop fires N=2 times then
    # logs + continues (never blocks). render unavailable (treated as pass-on-render).
    sandbox = _FakeSandbox(files={"prototype.html": "<html></html>"})
    runner = _FakeRunner(
        agent_events=[{"type": "agent_chunk", "data": {"text": "."}}],
        typed_content={"prototype-plan": "## Task 1: only\nbody\n"},  # 1 task
        sandbox=sandbox,
        static_results=[_FakeStatic(issues=["broken nav"])],  # always failing
        render_result=_FakeRender(available=False),
    )
    ctx = _Ctx(runner)

    out = [ev async for ev in TaskLoopStrategy().run(_two_task_step(), ctx)]

    # Exactly 2 internal fix attempts for the single task (bounded N=2).
    assert len(runner.fix_calls) == 2
    assert runner.fix_calls[0]["attempt"] == 1
    assert runner.fix_calls[1]["attempt"] == 2
    # The build still completes — events were produced (never blocked).
    assert any(ev["type"] == "task_loop_progress" for ev in out)


@pytest.mark.asyncio
async def test_task_loop_yields_engine_event_vocabulary() -> None:
    sandbox = _FakeSandbox(files={"prototype.html": "<html></html>"})
    agent_events = [
        {"type": "agent_start", "data": {"agent_id": "prototype-build"}},
        {"type": "agent_chunk", "data": {"text": "x"}},
    ]
    runner = _FakeRunner(
        agent_events=agent_events,
        typed_content={"prototype-plan": _TWO_TASK_PLAN},
        sandbox=sandbox,
    )
    ctx = _Ctx(runner)

    out = [ev async for ev in TaskLoopStrategy().run(_two_task_step(), ctx)]

    types = [ev["type"] for ev in out]
    # task_loop_progress (strategy) interleaved with the re-yielded run_agent events.
    assert types.count("task_loop_progress") == 2
    assert "agent_start" in types and "agent_chunk" in types
    # Every yielded event keeps the {"type","data"} shape (INV-3).
    assert all(set(ev.keys()) >= {"type", "data"} for ev in out)


@pytest.mark.asyncio
async def test_task_loop_name() -> None:
    assert TaskLoopStrategy().name == "task_loop"
