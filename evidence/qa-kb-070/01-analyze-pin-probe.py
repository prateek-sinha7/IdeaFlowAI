#!/usr/bin/env python3
"""QA-KB-070 / ISS-897 analyze probe. Edits NO repo file.

Run from backend/:

    .venv/bin/python -I ../evidence/qa-kb-070/01-analyze-pin-probe.py            # as shipped
    .venv/bin/python -I ../evidence/qa-kb-070/01-analyze-pin-probe.py --mutate   # kwarg deleted

Drives the REAL ``TaskLoopStrategy.run`` over a 3-task plan against a RECORDING fake
runner: the shape the missing pin needs (``run_agent`` records ``invocation_gated`` and
defaults it to ``True``, like ``KernelServices.run_agent`` at kernel_services.py:1964 and
``_FakeRunner.run_agent`` at tests/unit/agents/test_strategies.py:168-177).

``--mutate`` strips the ``invocation_gated=False,`` line from ``TaskLoopStrategy.run`` in
memory, which is exactly "delete task_loop.py:364".

Expected: as shipped -> every call False (the proposed pin passes);
          --mutate   -> every call True  (the proposed pin fails, i.e. it WOULD catch the revert).
"""

from __future__ import annotations

import asyncio
import inspect
import os
import re
import sys
import tempfile
import textwrap
from types import SimpleNamespace

# Same hermetic pin tests/conftest.py applies BEFORE any app import: registry.discover()
# imports app.* modules, and backend/.env points DATABASE_URL at the live Postgres.
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(
    tempfile.gettempdir(), "qa-kb-070-probe.db"
)
sys.path.insert(0, ".")  # cwd is backend/

from agents.capabilities import registry  # noqa: E402
from agents.capabilities.strategies import task_loop as m  # noqa: E402
from agents.workflows.plan import Step, TaskSource  # noqa: E402

MUTATE = "--mutate" in sys.argv

if MUTATE:
    cls = m.TaskLoopStrategy
    src = textwrap.dedent(inspect.getsource(cls.run))
    new, n = re.subn(r"^[ \t]*invocation_gated=False,[ \t]*\n", "", src, count=1, flags=re.M)
    assert n == 1, "mutation did not apply"
    ns: dict = {}
    exec(compile(new, "<mutated TaskLoopStrategy.run>", "exec"), vars(m), ns)
    cls.run = ns["run"]

registry.discover()

PLAN = "## Task 1: A\nbody a\n\n## Task 2: B\nbody b\n\n## Task 3: C\nbody c\n"


class _Sandbox:
    def __init__(self) -> None:
        self.files = {"prototype.html": "<html></html>"}

    def read(self, name):
        return self.files.get(name)

    def write(self, name, text):
        self.files[name] = text

    root = "/tmp/fake"


class _RecordingRunner:
    cancel_event = None
    run_id = "probe-run"
    od_context = None

    def __init__(self) -> None:
        self.sandbox = _Sandbox()
        self.run_agent_calls: list[dict] = []
        self._typed = {"prototype-plan": PLAN}

    def latest_typed_content(self, key):
        return self._typed.get(key)

    def upstream_context_hash(self, step):
        return "u-fake"

    async def run_agent(
        self,
        step,
        ctx,
        *,
        task_number=None,
        total_tasks=None,
        task_block=None,
        skeleton=None,
        invocation_gated=True,
    ):
        self.run_agent_calls.append(
            {"task_number": task_number, "invocation_gated": invocation_gated}
        )
        yield {"type": "agent_chunk", "data": {"text": "."}}

    async def persist_task_html(
        self, task_num, agent_id="prototype-build", *, filename="prototype.html", task_key=None
    ):
        return None

    async def run_validation_fix_loop(self, step, *, task_num, total_tasks, **kw):
        return None


async def main() -> int:
    runner = _RecordingRunner()
    ctx = SimpleNamespace(runner=runner)
    step = Step(
        agent_id="prototype-build",
        strategy="task_loop",
        task_source=TaskSource(kind="parsed", parser="heading_tasks"),
    )
    _ = [ev async for ev in m.TaskLoopStrategy().run(step, ctx)]

    flags = [c["invocation_gated"] for c in runner.run_agent_calls]
    print(f"mode                       : {'MUTATED (kwarg deleted)' if MUTATE else 'as shipped'}")
    print(f"run_agent calls            : {len(flags)}")
    print(f"invocation_gated per call  : {flags}")
    pin_holds = bool(flags) and all(f is False for f in flags)
    print(f"proposed pin (all False)   : {'PASS' if pin_holds else 'FAIL  <- the revert is now visible'}")
    print(f"TaskLoopStrategy.runs_agent_inline = {m.TaskLoopStrategy.runs_agent_inline}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
