"""ISS-685 / QA-KB-024 — resume reconcilers and fanout_batch must parse the task FILE
(parse_preferring_target), exactly like task_loop / wave_scheduler, not the producer's reply.

Offline: stub stores and sandboxes, real engine reconcilers, real parsers.
"""

from __future__ import annotations

import ast
import json
import pathlib
from types import SimpleNamespace as NS

import pytest

from agents.capabilities import task_identity
from agents.capabilities.registry import discover
from agents.capabilities.strategies.fanout_batch import FanoutBatchStrategy
from agents.capabilities.task_parsers.json_tasks import JsonTasksParser
from agents.capabilities.task_parsers.screen_plan import ScreenPlanParser
from agents.execution_engine.context import ExecutionContext
from agents.execution_engine.engine import ExecutionEngine

discover()

TASKS3 = {
    "tasks": [
        {"id": c, "title": c.upper(), "body": f"do {c}", "targets": [f"out/{c}.txt"]}
        for c in "abc"
    ]
}
FILE3 = json.dumps(TASKS3)
FENCED2 = "```json\n" + json.dumps({"tasks": TASKS3["tasks"][:2]}) + "\n```"
ONE_LINE = "Wrote build/tasks.json: 3 tasks."


class FakeSandbox:
    def __init__(self, files):
        self.files = dict(files)

    def read(self, name):
        return self.files.get(name)


class StubStore:
    def __init__(self, refs=(), events=()):
        self.refs, self.events = list(refs), list(events)

    async def tree(self, run_id):
        return self.refs

    async def read_subagent_runs(self, run_id):
        return []

    async def read_events(self, run_id, since):
        return self.events

    async def read_wave_runs(self, run_id):
        return []


def _ctx(reply, producer="planner"):
    e = ExecutionContext(run_id="run-1", owner_id="u1", disk_principal="u1")
    e.artifacts.write_ref(
        run_id="run-1",
        owner_id="u1",
        workspace_id="w",
        kind="plan",
        producer_step=producer,
        producer_agent=producer,
        task_id=None,
        content=reply,
        location="plan",
    )
    return e


def _keys(tasks, uhash):
    ords = task_identity.occurrence_ordinals(tasks)
    return [
        task_identity.compute_task_key(
            uhash, task_identity.normalize_task_content(t), ords[i]
        )
        for i, t in enumerate(tasks)
    ]


def _step(strategy, agent_id, parser, target, kind="parsed", path=None):
    return NS(
        agent_id=agent_id,
        strategy=strategy,
        mechanical=None,
        task_source=NS(
            kind=kind, parser=parser, target=target, source_step="planner", path=path
        ),
    )


eng = ExecutionEngine()
ORDERED = [NS(id="planner"), NS(id="wave-step")]


@pytest.mark.issue("ISS-685")
def test_wave_allowset_json_tasks_parses_file_not_reply():
    """ISS-685 — one-line reply, 3 tasks on disk: allow-set == the strategy's keys."""
    sb = FakeSandbox({"build/tasks.json": FILE3})
    ectx = _ctx(ONE_LINE)
    ectx.runner = NS(sandbox=sb)
    st = _step("wave_scheduler", "wave-step", "json_tasks", "build/tasks.json")
    uh = eng._compute_upstream_context_hash(st, ectx)
    skeys = _keys(
        JsonTasksParser().parse_preferring_target(
            ONE_LINE, sandbox=sb, target="build/tasks.json"
        ),
        uh,
    )
    allow = eng._compute_wave_orphan_allowsets(
        ectx, ORDERED, NS(steps=[st]), {"wave-step": set(skeys)}
    )
    assert set(allow.get("wave-step", set())) == set(skeys)


@pytest.mark.issue("ISS-685")
def test_wave_allowset_screen_plan_parses_file_not_reply():
    """ISS-685 — screen_plan: allow-set equals keys from parse_preferring_target."""
    inv = json.dumps(
        {
            "screens": [
                {"id": "home", "title": "Home"},
                {"id": "about", "title": "About"},
            ]
        }
    )
    spec = "## Screens\n### home — Home\n- Fields:\n  - Name [text]\n### about — About\n- Fields:\n  - Bio [textarea]\n"
    sb = FakeSandbox({"build/screens.json": inv, "spec.md": spec})
    ectx = _ctx(inv)
    ectx.runner = NS(sandbox=sb)
    st = _step("wave_scheduler", "wave-step", "screen_plan", "build/screens.json")
    uh = eng._compute_upstream_context_hash(st, ectx)
    skeys = _keys(
        ScreenPlanParser().parse_preferring_target(
            inv, sandbox=sb, target="build/screens.json"
        ),
        uh,
    )
    allow = eng._compute_wave_orphan_allowsets(
        ectx, ORDERED, NS(steps=[st]), {"wave-step": set(skeys)}
    )
    assert set(allow.get("wave-step", set())) == set(skeys)


@pytest.mark.issue("ISS-685")
def test_wave_allowset_skips_custom_path_without_parsing(monkeypatch):
    """ISS-685 — the shipped blr-write shape (custom_path + source_step) is skipped, no parse."""
    calls = []
    orig = JsonTasksParser.parse
    monkeypatch.setattr(
        JsonTasksParser, "parse", lambda self, t: calls.append(t) or orig(self, t)
    )
    ectx = _ctx(ONE_LINE)
    ectx.runner = NS(sandbox=FakeSandbox({}))
    st = _step(
        "wave_scheduler",
        "wave-step",
        "json_tasks",
        None,
        kind="custom_path",
        path="x.json",
    )
    eng._compute_wave_orphan_allowsets(
        ectx, ORDERED, NS(steps=[st]), {"wave-step": {"k"}}
    )
    assert calls == []


@pytest.mark.issue("ISS-685")
def test_cumulative_boundaries_use_file_tasks_not_reply():
    """ISS-685 — reply fences 2 of the file's 3 tasks, 3 keys completed: no boundary."""
    sb = FakeSandbox({"build/tasks.json": FILE3})
    ectx = _ctx(FENCED2)
    ectx.runner = NS(sandbox=sb)
    st = _step("task_loop", "build-step", "json_tasks", "build/tasks.json")
    uh = eng._compute_upstream_context_hash(st, ectx)
    done = _keys(
        JsonTasksParser().parse_preferring_target(
            FENCED2, sandbox=sb, target="build/tasks.json"
        ),
        uh,
    )
    assert len(done) == 3
    bnd = eng._compute_cumulative_boundaries(
        ectx,
        [NS(id="planner"), NS(id="build-step")],
        NS(steps=[st]),
        {"build-step": done},
    )
    assert bnd.get("build-step", {}).get("restore_nothing", False) is False
    assert "boundary_task_id" not in bnd.get("build-step", {})


@pytest.mark.issue("ISS-685")
async def test_first_incomplete_step_finished_build_is_not_reentered():
    """ISS-685 — 3/3 done, one-line planner reply, file on disk: offset == len(ordered)."""
    p_step = NS(agent_id="planner", strategy="single_shot", mechanical=None)
    b_step = _step("task_loop", "build-step", "json_tasks", "build/tasks.json")
    refs = [NS(producer_agent="planner", task_id=None, content=ONE_LINE)] + [
        NS(producer_agent="build-step", task_id=f"k{i}", content="x") for i in range(3)
    ]
    ev = [NS(type="agent_complete", payload_json={"agent_id": "planner"})]
    e = ExecutionContext(run_id="run-1", owner_id="u1", disk_principal="u1")
    e.scoped_store = StubStore(refs=refs, events=ev)
    e.runner = NS(
        sandbox=FakeSandbox({"build/tasks.json": FILE3})
    )  # fix falls back to ectx.runner.sandbox
    ordered = [NS(id="planner"), NS(id="build-step")]
    got = await eng._first_incomplete_step(e, ordered, NS(steps=[p_step, b_step]))
    assert got == len(ordered)


@pytest.mark.issue("ISS-685")
async def test_fanout_batch_reads_task_file_on_narrating_reply():
    """ISS-685 — narrating reply, file on disk: 3 requests reach run_fanout, no ValueError."""
    seen = []

    class Runner:
        sandbox = FakeSandbox({"build/tasks.json": FILE3})

        def latest_typed_content(self, step_id):
            return ONE_LINE

        async def run_fanout(self, requests, ctx, step=None):
            seen.append(len(requests))
            yield {"type": "fanout_ran"}

    st = NS(
        task_source=NS(
            source_step="planner", parser="json_tasks", target="build/tasks.json"
        ),
        fanout=None,
    )
    async for _ in FanoutBatchStrategy().run(st, NS(runner=Runner())):
        pass
    assert seen == [3]


@pytest.mark.issue("ISS-685")
def test_no_bare_parse_on_resolved_task_parser():
    """ISS-685 — `.parse(` on a resolve("task_parser", ...) result only inside parse_step_tasks."""
    root = pathlib.Path(__file__).resolve().parents[4] / "agents"
    offenders = []
    for path in root.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text())
        except (SyntaxError, UnicodeDecodeError):
            continue
        for fn in ast.walk(tree):
            if (
                not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
                or fn.name == "parse_step_tasks"
            ):
                continue
            names = {
                t.id
                for n in ast.walk(fn)
                if isinstance(n, ast.Assign)
                and isinstance(n.value, ast.Call)
                and any(
                    isinstance(a, ast.Constant) and a.value == "task_parser"
                    for a in n.value.args
                )
                for t in n.targets
                if isinstance(t, ast.Name)
            }
            for n in ast.walk(fn):
                if (
                    isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "parse"
                    and isinstance(n.func.value, ast.Name)
                    and n.func.value.id in names
                ):
                    arg = n.args[0] if n.args else None
                    # custom_path reads the file itself; its input is the file, not a reply
                    if (
                        isinstance(arg, ast.Call)
                        and getattr(arg.func, "id", "") == "read_custom_path"
                    ):
                        continue
                    offenders.append(f"{path.relative_to(root.parent)}:{n.lineno}")
    assert not offenders, offenders
