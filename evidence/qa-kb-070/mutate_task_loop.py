"""QA-KB-070 / ISS-897 analyze aid: an in-memory mutation of TaskLoopStrategy.run.

Edits NO repo file. With MUTATE_TASK_LOOP=1 it strips the ``invocation_gated=False,``
keyword from the single ``runner.run_agent(...)`` call in ``TaskLoopStrategy.run``
(``backend/agents/capabilities/strategies/task_loop.py:364``), which is exactly what
deleting that line would do. Without the env var it is inert.

Usage (cwd ``backend/``, ONE test file per run):

    PYTHONPATH=../evidence/qa-kb-070 MUTATE_TASK_LOOP=1 \
        .venv/bin/python -m pytest tests/unit/agents/test_strategies.py \
        -q -p no:cacheprovider -p mutate_task_loop

Lazy on purpose: ``-p`` plugins load before ``tests/conftest.py`` pins DATABASE_URL, so
nothing here may import ``app`` or ``agents`` at import time. The patch is applied in
``pytest_runtest_setup``, after the conftest pin and after collection.
"""

from __future__ import annotations

import inspect
import os
import re
import textwrap

_APPLIED = {"done": False}
_ENV = "MUTATE_TASK_LOOP"


def apply_mutation() -> None:
    import agents.capabilities.strategies.task_loop as m

    cls = m.TaskLoopStrategy
    src = textwrap.dedent(inspect.getsource(cls.run))
    # Only a line that STARTS with the kwarg: the comment at task_loop.py:356 also
    # contains the text "invocation_gated=False" but begins with "#".
    mutated, n = re.subn(
        r"^[ \t]*invocation_gated=False,[ \t]*\n", "", src, count=1, flags=re.M
    )
    assert n == 1, "mutation did not apply: kwarg line not found in TaskLoopStrategy.run"
    assert "invocation_gated=False," not in re.sub(r"#.*", "", mutated)
    ns: dict = {}
    exec(compile(mutated, "<mutated TaskLoopStrategy.run>", "exec"), vars(m), ns)
    cls.run = ns["run"]
    _APPLIED["done"] = True


_ENV_FWD = "MUTATE_RUN_AGENT_FORWARD"
_APPLIED_FWD = {"done": False}


def apply_forward_mutation() -> None:
    """Consumption-half mutation: KernelServices.run_agent forgets to forward the flag.

    Equivalent to deleting ``invocation_gated=invocation_gated`` at
    ``backend/agents/execution_engine/kernel_services.py:2065``: whatever a caller passes,
    ``_run_agent`` sees the default ``True``. In memory only; no repo file is touched.
    """
    from agents.execution_engine.kernel_services import KernelServices

    orig = KernelServices.run_agent

    async def run_agent(
        self,
        step,
        ctx,
        *,
        task_number=None,
        total_tasks=None,
        task_block=None,
        skeleton=None,
        invocation_gated=True,  # noqa: ARG001 - deliberately dropped
        ectx_override=None,
    ):
        async for ev in orig(
            self,
            step,
            ctx,
            task_number=task_number,
            total_tasks=total_tasks,
            task_block=task_block,
            skeleton=skeleton,
            invocation_gated=True,
            ectx_override=ectx_override,
        ):
            yield ev

    KernelServices.run_agent = run_agent
    _APPLIED_FWD["done"] = True


_ENV_DECL = "MUTATE_UNDECLARE"  # comma list of: task_loop, fanout_batch, wave_scheduler
_APPLIED_DECL: dict = {"done": [], "wanted": []}
_DECL_TARGETS = {
    "task_loop": ("agents.capabilities.strategies.task_loop", "TaskLoopStrategy"),
    "fanout_batch": ("agents.capabilities.strategies.fanout_batch", "FanoutBatchStrategy"),
    "wave_scheduler": ("agents.capabilities.strategies.wave_scheduler", "WaveSchedulerStrategy"),
}


def apply_undeclare() -> None:
    """Step-scope mutation: delete a strategy's ``runs_agent_inline = False`` declaration.

    The kernel reads ``bool(getattr(strategy, "runs_agent_inline", True))``
    (engine.py:11522), so an ABSENT declaration and ``True`` are the same thing. Setting
    ``True`` in memory is therefore exactly "delete the class attribute". No repo file is
    touched.
    """
    import importlib

    for name in [n for n in os.environ.get(_ENV_DECL, "").split(",") if n]:
        mod, cls = _DECL_TARGETS[name]
        getattr(importlib.import_module(mod), cls).runs_agent_inline = True
        _APPLIED_DECL["done"].append(name)


_ENV_STRIP = "MUTATE_STRIP_KWARG"  # comma list of KernelServices methods: run_worker, run_merge_agent
_APPLIED_STRIP: dict = {"done": []}


def apply_strip_kwarg() -> None:
    """Call-site mutation on the kernel's two other ``invocation_gated=False`` sites.

    Same technique as :func:`apply_mutation`: re-compile the method with the kwarg line
    removed and bind it back on the class, in memory only.
    """
    import agents.execution_engine.kernel_services as ks

    cls = ks.KernelServices
    for name in [n for n in os.environ.get(_ENV_STRIP, "").split(",") if n]:
        src = textwrap.dedent(inspect.getsource(getattr(cls, name)))
        mutated, n = re.subn(
            r"^[ \t]*invocation_gated=False,[ \t]*\n", "", src, count=1, flags=re.M
        )
        assert n == 1, f"kwarg line not found in KernelServices.{name}"
        ns: dict = {}
        exec(compile(mutated, f"<mutated KernelServices.{name}>", "exec"), vars(ks), ns)
        setattr(cls, name, ns[name])
        _APPLIED_STRIP["done"].append(name)


def pytest_runtest_setup(item) -> None:  # noqa: ARG001
    if os.environ.get(_ENV) == "1" and not _APPLIED["done"]:
        apply_mutation()
    if os.environ.get(_ENV_FWD) == "1" and not _APPLIED_FWD["done"]:
        apply_forward_mutation()
    if os.environ.get(_ENV_DECL) and not _APPLIED_DECL["done"]:
        apply_undeclare()
    if os.environ.get(_ENV_STRIP) and not _APPLIED_STRIP["done"]:
        apply_strip_kwarg()


def pytest_terminal_summary(terminalreporter) -> None:
    # Self-proving: a mutated run that never applied the patch would be a false "green".
    if os.environ.get(_ENV) == "1":
        terminalreporter.write_line(
            f"QA-KB-070 mutation applied during this run: {_APPLIED['done']}"
        )
    if os.environ.get(_ENV_FWD) == "1":
        terminalreporter.write_line(
            f"QA-KB-070 forward-mutation applied during this run: {_APPLIED_FWD['done']}"
        )
    if os.environ.get(_ENV_DECL):
        terminalreporter.write_line(
            f"QA-KB-070 undeclared runs_agent_inline during this run: {_APPLIED_DECL['done']}"
        )
    if os.environ.get(_ENV_STRIP):
        terminalreporter.write_line(
            f"QA-KB-070 kwarg stripped from KernelServices methods during this run: {_APPLIED_STRIP['done']}"
        )


def pytest_report_header(config) -> str | None:  # noqa: ARG001
    if os.environ.get(_ENV) == "1":
        return "QA-KB-070 MUTATION ON: invocation_gated=False stripped from TaskLoopStrategy.run (in memory)"
    return "QA-KB-070 mutation plugin loaded but INERT (MUTATE_TASK_LOOP != 1)"
