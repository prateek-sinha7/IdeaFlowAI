"""task_loop ``fix.full_every``: full validation every Nth task + last; quick check on all."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from agents.capabilities.strategies.task_loop import TaskLoopStrategy
from agents.workflows.compiler import CompilerError, WorkflowCompiler
from agents.workflows.plan import FixPolicy

_PLAN = "\n\n".join(f"## Task {i}: thing {i}\nDo {i}.\n" for i in range(1, 10))


class _FakeSandbox:
    def __init__(self) -> None:
        self.files: dict[str, str] = {}

    def write(self, name, content):
        self.files[name] = content

    def read(self, name):
        return self.files.get(name)

    def path_for(self, name):
        return Path("/run-sandbox") / name


class _Runner:
    def __init__(self):
        self.sandbox = _FakeSandbox()
        self.od_context: dict = {}
        self.run_id = "run-1"
        self.cancel_event = None
        self.full: list[int] = []
        self.static: list[bool] = []

    def latest_typed_content(self, _step):
        return _PLAN

    async def run_agent(self, step, ctx, **kw):
        yield {"type": "agent_chunk", "data": {}}

    async def run_validation_fix_loop(self, step, *, task_num, **kw):
        self.full.append(task_num)

    def static_check(self, path, *, audit=True):
        self.static.append(audit)
        return SimpleNamespace(ok=True, issues=[], warnings=[])


def _run(fix):
    runner = _Runner()
    step = SimpleNamespace(agent_id="prototype-build", task_source=None, fix=fix)
    ctx = SimpleNamespace(runner=runner, deliverable=None, seed_files={})

    async def go():
        return [e async for e in TaskLoopStrategy().run(step, ctx)]

    asyncio.run(go())
    return runner


def test_full_every_4_over_9_tasks():
    r = _run(FixPolicy(mode="internal", max_attempts=2, full_every=4))
    assert r.full == [4, 8, 9]
    # quick check (no audit) after tasks 1-3,5-7 + final findings call (audit default)
    assert r.static.count(False) == 6


def test_default_runs_full_every_task():
    assert _run(None).full == list(range(1, 10))
    assert _run(FixPolicy(mode="internal", max_attempts=2)).full == list(range(1, 10))


def test_compiler_accepts_and_validates_full_every():
    assert (
        WorkflowCompiler._compile_fix_policy(
            {"max_attempts": 2, "full_every": 4}, "w"
        ).full_every
        == 4
    )
    assert (
        WorkflowCompiler._compile_fix_policy({"max_attempts": 2}, "w").full_every == 1
    )
    with pytest.raises(CompilerError):
        WorkflowCompiler._compile_fix_policy({"full_every": 0}, "w")
