"""QA-KB-024 repro: resume reconcilers parse the producer's REPLY; strategies parse the FILE.

Offline. No DB, no model, no server. Drives the REAL ExecutionEngine reconciler methods,
the REAL task parsers and the REAL FanoutBatchStrategy against stub stores / sandboxes.
Run from backend/:  .venv/bin/python <this file>
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, os.getcwd())

from agents.capabilities import task_identity  # noqa: E402
from agents.capabilities.registry import discover  # noqa: E402
from agents.capabilities.strategies.fanout_batch import FanoutBatchStrategy  # noqa: E402
from agents.capabilities.task_parsers.json_tasks import JsonTasksParser  # noqa: E402
from agents.capabilities.task_parsers.screen_plan import ScreenPlanParser  # noqa: E402
from agents.execution_engine.context import ExecutionContext  # noqa: E402
from agents.execution_engine.engine import ExecutionEngine  # noqa: E402

discover()


class FakeSandbox:
    def __init__(self, files):
        self.files = dict(files)

    def read(self, name):
        return self.files.get(name)

    def write(self, name, content):
        self.files[name] = content


def make_ctx(reply, producer="planner"):
    e = ExecutionContext(run_id="run-1", owner_id="u1", disk_principal="u1")
    e.artifacts.write_ref(
        run_id="run-1", owner_id="u1", workspace_id="w", kind="plan",
        producer_step=producer, producer_agent=producer, task_id=None,
        content=reply, location="plan",
    )
    return e


def keys_of(tasks, uhash):
    ords = task_identity.occurrence_ordinals(tasks)
    return [
        task_identity.compute_task_key(uhash, task_identity.normalize_task_content(t), ords[i])
        for i, t in enumerate(tasks)
    ]


def step(strategy, agent_id, parser, target, source="planner"):
    return NS(
        agent_id=agent_id, strategy=strategy, mechanical=None,
        task_source=NS(kind="parsed", parser=parser, target=target, source_step=source, path=None),
    )


def hdr(t):
    print("\n" + "=" * 100 + f"\n{t}\n" + "=" * 100)


TASKS3 = {"tasks": [
    {"id": "a", "title": "A", "body": "do a", "targets": ["out/a.txt"]},
    {"id": "b", "title": "B", "body": "do b", "targets": ["out/b.txt"]},
    {"id": "c", "title": "C", "body": "do c", "targets": ["out/c.txt"]},
]}
TASKS2 = {"tasks": TASKS3["tasks"][:2]}
FILE3 = json.dumps(TASKS3)
ONE_LINE = "Wrote build/tasks.json: 3 tasks."  # shipped planners: "Reply with one line"
eng = ExecutionEngine()


class StubStore:
    def __init__(self, refs=(), subs=(), events=(), waves=()):
        self.refs, self.subs, self.events, self.waves = list(refs), list(subs), list(events), list(waves)

    async def tree(self, run_id):
        return self.refs

    async def read_subagent_runs(self, run_id):
        return self.subs

    async def read_events(self, run_id, since):
        return self.events

    async def read_wave_runs(self, run_id):
        return self.waves


# ---------------------------------------------------------------------------------------------
hdr("S-B1  engine.py:14971  wave_scheduler + json_tasks, shipped planner style (one-line reply)")
sb = FakeSandbox({"build/tasks.json": FILE3})
ectx = make_ctx(ONE_LINE)
wstep = step("wave_scheduler", "wave-step", "json_tasks", "build/tasks.json")
ordered = [NS(id="planner"), NS(id="wave-step")]
compiled = NS(steps=[wstep])
uh = eng._compute_upstream_context_hash(wstep, ectx)
strat = JsonTasksParser().parse_preferring_target(ONE_LINE, sandbox=sb, target="build/tasks.json")
skeys = keys_of(strat, uh)
print("strategy (wave_scheduler.py:273 parse_preferring_target) tasks:", [t.id for t in strat])
try:
    JsonTasksParser().parse(ONE_LINE)
    print("reconciler parse(reply): returned")
except ValueError as e:
    print("reconciler parse(reply) RAISES ValueError:", str(e)[:70])
allow = eng._compute_wave_orphan_allowsets(ectx, ordered, compiled, {"wave-step": set(skeys)})
print("real _compute_wave_orphan_allowsets ->", allow, "(empty => orphan gate silently DORMANT for this step)")

# ---------------------------------------------------------------------------------------------
hdr("S-B2  engine.py:14971  reply carries a fence that differs from the file the strategy reads")
reply2 = "```json\n" + json.dumps(TASKS2) + "\n```"
ectx2 = make_ctx(reply2)
uh2 = eng._compute_upstream_context_hash(wstep, ectx2)
strat2 = JsonTasksParser().parse_preferring_target(reply2, sandbox=sb, target="build/tasks.json")
skeys2 = keys_of(strat2, uh2)
allow2 = eng._compute_wave_orphan_allowsets(ectx2, ordered, compiled, {"wave-step": set(skeys2)})
print("strategy tasks (file):", [t.id for t in strat2], "| reconciler allow-set size:", len(allow2.get("wave-step", [])))
print("worker 'c' key in reconciler allow-set?", skeys2[2] in allow2.get("wave-step", set()))


async def rematerialize(allow_map, label):
    refs = [NS(kind="file_bundle", location=f"out/{n}.txt", content=f"{n.upper()}-done", version=1,
               producer_step="wave-step", producer_agent="wave-step", task_id=str(i))
            for i, n in enumerate("abc")]
    subs = [NS(parent_step="wave-step", worker_index=i, task_id=skeys2[i]) for i in range(3)]
    e = make_ctx(reply2)
    e.scoped_store = StubStore(refs=refs, subs=subs)
    out = FakeSandbox({})
    await eng._rematerialize_artifacts_to_disk(e, out, boundary_by_agent={}, wave_allow_by_step=allow_map)
    print(f"{label}: restored files ->", sorted(out.files))


asyncio.run(rematerialize({"wave-step": set(skeys2)}, "allow-set the STRATEGY would compute"))
asyncio.run(rematerialize(allow2, "allow-set the RECONCILER computed (parse(reply))"))

# ---------------------------------------------------------------------------------------------
hdr("S-B3  engine.py:14971  wave_scheduler + screen_plan, reply happens to be the inventory")
INV = json.dumps({"screens": [{"id": "home", "title": "Home"}, {"id": "about", "title": "About"}]})
SPEC = "## Screens\n### home — Home\n- Fields:\n  - Name [text]\n### about — About\n- Fields:\n  - Bio [textarea]\n"
sb3 = FakeSandbox({"build/screens.json": INV, "spec.md": SPEC})
ectx3 = make_ctx(INV, producer="planner")
sstep = step("wave_scheduler", "wave-step", "screen_plan", "build/screens.json")
compiled3 = NS(steps=[sstep])
uh3 = eng._compute_upstream_context_hash(sstep, ectx3)
strat3 = ScreenPlanParser().parse_preferring_target(INV, sandbox=sb3, target="build/screens.json")
rec3 = ScreenPlanParser().parse(INV)
sk3, rk3 = keys_of(strat3, uh3), keys_of(rec3, uh3)
print("strategy keys == reconciler keys ?", sk3 == rk3, "| disjoint:", set(sk3).isdisjoint(rk3))
print("body differs (spec inlined vs empty):", strat3[0].body != rec3[0].body)
allow3 = eng._compute_wave_orphan_allowsets(ectx3, ordered, compiled3, {"wave-step": set(sk3)})
print("real reconciler allow-set disjoint from strategy keys ->", set(allow3["wave-step"]).isdisjoint(sk3))
print("ScreenPlanParser.parse(one-line reply) raises ->", end=" ")
try:
    ScreenPlanParser().parse(ONE_LINE)
except ValueError as e:
    print("ValueError:", str(e)[:60])

# ---------------------------------------------------------------------------------------------
hdr("S-A  engine.py:14889  task_loop + json_tasks: boundary computed from the reply, strategy skips from the file")
lstep = step("task_loop", "build-step", "json_tasks", "build/tasks.json")
ordered_l = [NS(id="planner"), NS(id="build-step")]
compiled_l = NS(steps=[lstep])
ectx_l = make_ctx(reply2)  # planner reply fences only 2 of the 3 tasks the file holds
uh_l = eng._compute_upstream_context_hash(lstep, ectx_l)
strat_l = JsonTasksParser().parse_preferring_target(reply2, sandbox=sb, target="build/tasks.json")
sk_l = keys_of(strat_l, uh_l)
done = list(sk_l)  # all 3 tasks completed pre-crash under the strategy's keys
print("strategy common-prefix skip p =", task_identity.common_prefix_length(sk_l, done), "(skips all 3 tasks)")
bnd = eng._compute_cumulative_boundaries(ectx_l, ordered_l, compiled_l, {"build-step": done})
print("real _compute_cumulative_boundaries ->", {k: {kk: (vv[:8] if isinstance(vv, str) else vv) for kk, vv in v.items()} for k, v in bnd.items()})
print("boundary_task_id is key of task b (index 1)?", bnd.get("build-step", {}).get("boundary_task_id") == sk_l[1])


async def restore_deliverable(boundary, label):
    refs = [NS(kind="html_file", location="app.py", content=c, version=v, producer_step="build-step",
               producer_agent="build-step", task_id=sk_l[v - 1]) for v, c in ((1, "A"), (2, "AB"), (3, "ABC"))]
    e = make_ctx(reply2)
    e.scoped_store = StubStore(refs=refs)
    out = FakeSandbox({})
    await eng._rematerialize_artifacts_to_disk(e, out, boundary_by_agent=boundary)
    print(f"{label}: app.py restored =", repr(out.files.get("app.py")))


asyncio.run(restore_deliverable({}, "no boundary (what the file-derived keys imply)"))
asyncio.run(restore_deliverable(bnd, "boundary from reply-derived keys"))
print("=> strategy then skips tasks 1-3 (p=3) but disk holds only the as-of-task-2 deliverable: task c's edits are lost")

# narration case -> raises -> swallowed (fail-safe default global-max)
ectx_n = make_ctx(ONE_LINE)
print("narrating reply -> boundaries =", eng._compute_cumulative_boundaries(ectx_n, ordered_l, compiled_l, {"build-step": done}),
      "(swallowed ValueError => boundary silently lost)")

# ---------------------------------------------------------------------------------------------
hdr("S-C  engine.py:15202  _first_incomplete_step on a COMPLETED task_loop + json_tasks build step")


async def first_incomplete(reply, parser="json_tasks", target="build/tasks.json", plan_for=None):
    p_step = NS(agent_id="planner", strategy="single_shot", mechanical=None)
    b_step = step("task_loop", "build-step", parser, target)
    refs = [NS(producer_agent="planner", task_id=None, content=reply)] + [
        NS(producer_agent="build-step", task_id=f"k{i}", content="x") for i in range(3)
    ]
    events = [NS(type="agent_complete", payload_json={"agent_id": "planner"})]
    e = ExecutionContext(run_id="run-1", owner_id="u1", disk_principal="u1")  # == the temp ctx at engine.py:16225
    e.scoped_store = StubStore(refs=refs, events=events)
    ordered_c = [NS(id="planner"), NS(id="build-step")]
    return await eng._first_incomplete_step(e, ordered_c, NS(steps=[p_step, b_step])), e


r_narr, tmp_ctx = asyncio.run(first_incomplete(ONE_LINE))
r_fence, _ = asyncio.run(first_incomplete("```json\n" + FILE3 + "\n```"))
HEAD3 = "## Task 1: a\nbody\n## Task 2: b\nbody\n## Task 3: c\nbody\n"
r_head, _ = asyncio.run(first_incomplete(HEAD3, parser="heading_tasks", target="tasks.md"))
print("3/3 tasks persisted, planner reply = one-line narration, json_tasks  -> resume offset", r_narr, "(2 == nothing left; 1 == RE-ENTER the finished step)")
print("same, planner reply = fence with the 3 tasks                          -> resume offset", r_fence)
print("control: heading_tasks (no parse_preferring_target), 3 headings       -> resume offset", r_head)
print("temp ExecutionContext used by _compute_resume_offset has runner =", tmp_ctx.runner,
      "=> the agreed fix's getattr(ectx.runner,'sandbox') is None at this site (fix is a silent no-op here)")

# ---------------------------------------------------------------------------------------------
hdr("S-D  fanout_batch.py:92  the strategy itself (not a reconciler), normal run, narrating planner reply")


class FakeRunner:
    sandbox = FakeSandbox({"build/tasks.json": FILE3})

    def latest_typed_content(self, step_id):
        return ONE_LINE

    async def run_fanout(self, requests, ctx, step=None):
        yield {"type": "fanout_ran", "data": {"n": len(requests)}}


async def run_fanout_batch():
    st = NS(task_source=NS(source_step="planner", parser="json_tasks", target="build/tasks.json"), fanout=None)
    out = []
    async for ev in FanoutBatchStrategy().run(st, NS(runner=FakeRunner())):
        out.append(ev)
    return out


try:
    print("events:", asyncio.run(run_fanout_batch()))
except ValueError as e:
    print("FanoutBatchStrategy.run RAISES ValueError although build/tasks.json is on disk with 3 tasks:\n   ", str(e)[:90])
