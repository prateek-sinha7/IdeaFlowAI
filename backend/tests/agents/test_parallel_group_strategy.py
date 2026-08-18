"""`subagents: {mode: parallel}` must actually overlap its siblings.

REGRESSION THIS PINS: `mode: parallel` used to be decorative. The compiler
correctly emitted no dependency edge between siblings, but the engine's dispatch
loop walks the compiler's flat topological order awaiting one step at a time, so
`parallel` and `sequential` produced byte-identical dispatch. Measured live on
`sample_subagents_parallel`: sibling B started 13ms after sibling A finished —
zero overlap.

The fix routes the group through the kernel `run_fanout` spawn path (the same
`asyncio.gather` + `Semaphore` that `fanout_batch` and `wave_scheduler` use), so
these tests assert on the SHAPE that makes that possible, plus one real timing
test against the strategy itself.

The timing test uses a fake runner rather than the live engine on purpose: a live
run's overlap depends on the model, and a test whose pass/fail depends on Bedrock
latency is a flaky test. What can be pinned deterministically is that the strategy
hands all N requests to `run_fanout` in ONE call — because everything downstream of
that call is the kernel's already-tested concurrency.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from agents.capabilities.registry import CapabilityRegistry, discover
from agents.execution_engine.engine import compile_for_run


@pytest.fixture(scope="module", autouse=True)
def _registry():
    discover()
    return CapabilityRegistry()


# ── Compile shape ────────────────────────────────────────────────────────────


def test_parallel_group_compiles_to_the_fanout_dispatcher():
    compiled = compile_for_run("sample_subagents_parallel")
    parent = next(s for s in compiled.steps if s.agent_id == "custom-agent:page")

    assert parent.strategy == "parallel_group"
    assert parent.fanout is not None
    assert parent.fanout.max_parallel == 3
    assert parent.fanout.workers == [
        "custom-agent:apple", "custom-agent:ball", "custom-agent:cat",
    ]


def test_children_leave_the_serial_loop_but_stay_in_the_plan():
    """Both halves matter.

    Still in `compiled.steps`: the roster, the artifact graph and `agent_exists`
    all read the plan, and a child missing from it could not be spawned at all.
    Out of the serial loop: the engine would otherwise run each child twice, once
    in the loop and once as a spawned worker.
    """
    compiled = compile_for_run("sample_subagents_parallel")
    children = {
        s.agent_id: s for s in compiled.steps if s.agent_id != "custom-agent:page"
    }

    assert set(children) == {
        "custom-agent:apple", "custom-agent:ball", "custom-agent:cat",
    }
    assert all(c.dispatched_by == "custom-agent:page" for c in children.values())
    # No edges between siblings — an edge would serialize them again.
    assert all(c.depends_on == [] for c in children.values())


def test_children_are_auto_allow_listed_for_the_spawn_gate():
    """run_fanout rejects a named worker absent from allowed_workers, pre-spawn.

    Without this the workflow would compile clean and then raise FanoutError on
    the first run.
    """
    compiled = compile_for_run("sample_subagents_parallel")
    assert set(compiled.allowed_workers) >= {
        "custom-agent:apple", "custom-agent:ball", "custom-agent:cat",
    }


def test_sequential_mode_is_unchanged():
    """The fix must not touch `mode: sequential` — chained edges, no fan-out."""
    compiled = compile_for_run("sample_subagents_parallel")
    apple = next(s for s in compiled.steps if s.agent_id == "custom-agent:apple")
    # sample_subagents_parallel declares parallel, so `apple` is a fan-out worker
    # there. What must hold is that a SEQUENTIAL group still chains: assert on
    # the compiler directly rather than on a manifest that does not use the mode.
    from agents.workflows.compiler import WorkflowCompiler
    from agents.workflows.manifest import WorkflowManifest

    manifest = WorkflowManifest(
        id="seq-demo",
        steps=[{
            "agent": "custom-agent", "instance_id": "parent", "prompt": "p",
            "subagents": {"mode": "sequential", "steps": [
                {"agent": "custom-agent", "instance_id": "a", "prompt": "a"},
                {"agent": "custom-agent", "instance_id": "b", "prompt": "b"},
            ]},
        }],
        deliverable={}, planner="run", clarify={"mode": "auto", "defaults": []},
        context_providers=[], seed_files={}, version=1,
    )
    out = WorkflowCompiler().compile(manifest, CapabilityRegistry())
    parent = next(s for s in out.steps if s.agent_id == "custom-agent:parent")
    b = next(s for s in out.steps if s.agent_id == "custom-agent:b")

    assert parent.strategy == "single_shot"       # NOT parallel_group
    assert parent.fanout is None
    assert b.depends_on == ["custom-agent:a"]     # still chained
    assert all(not s.dispatched_by for s in out.steps)  # still serially dispatched
    assert apple is not None


# ── Strategy behaviour ───────────────────────────────────────────────────────


class _FakeRunner:
    """Records the run_fanout call and simulates concurrent workers."""

    def __init__(self, worker_delay: float = 0.05):
        self.fanout_calls: list[list[dict]] = []
        self.ran_parent = False
        self.worker_delay = worker_delay
        self.overlap_peak = 0
        self._in_flight = 0

    async def run_fanout(self, requests, ctx, *, step, event_queue=None):
        self.fanout_calls.append(list(requests))

        async def _worker():
            self._in_flight += 1
            self.overlap_peak = max(self.overlap_peak, self._in_flight)
            await asyncio.sleep(self.worker_delay)
            self._in_flight -= 1

        # Stand-in for the kernel's gather-over-semaphore.
        await asyncio.gather(*[_worker() for _ in requests])
        for i, _ in enumerate(requests):
            yield {"type": "subagent_result", "data": {"worker": i}}

    async def run_agent(self, step, ctx):
        self.ran_parent = True
        yield {"type": "agent_complete", "data": {"agent_id": step.agent_id}}


def _run(strategy, step, ctx):
    async def _collect():
        return [e async for e in strategy.run(step, ctx)]

    return asyncio.run(_collect())


def _strategy():
    from agents.capabilities.strategies.parallel_group import ParallelGroupStrategy

    return ParallelGroupStrategy()


def test_all_siblings_go_out_in_ONE_fanout_call():
    """One call is what makes them concurrent.

    N sequential `run_fanout` calls of one request each would type-check, pass a
    "did it spawn everyone" assertion, and still run strictly serially — which is
    exactly the bug being fixed. So the count of calls is the assertion, not just
    the count of workers.
    """
    runner = _FakeRunner()
    step = SimpleNamespace(
        agent_id="custom-agent:page",
        fanout=SimpleNamespace(workers=["a", "b", "c"], max_parallel=3),
    )
    _run(_strategy(), step, SimpleNamespace(runner=runner))

    assert len(runner.fanout_calls) == 1
    assert [r["agent"] for r in runner.fanout_calls[0]] == ["a", "b", "c"]
    assert runner.overlap_peak == 3


def test_the_parent_runs_after_its_children():
    """Order is load-bearing: the parent reads the children's artifacts."""
    runner = _FakeRunner()
    step = SimpleNamespace(
        agent_id="custom-agent:page",
        fanout=SimpleNamespace(workers=["a", "b"], max_parallel=None),
    )
    events = _run(_strategy(), step, SimpleNamespace(runner=runner))

    assert runner.ran_parent
    types = [e["type"] for e in events]
    assert types.index("agent_complete") > max(
        i for i, t in enumerate(types) if t == "subagent_result"
    )


def test_a_group_with_no_workers_degrades_to_a_plain_run():
    """An empty group is still a valid step — run the parent, spawn nothing."""
    runner = _FakeRunner()
    step = SimpleNamespace(agent_id="custom-agent:page", fanout=None)
    _run(_strategy(), step, SimpleNamespace(runner=runner))

    assert runner.fanout_calls == []
    assert runner.ran_parent


# ── End to end through the real engine (offline, scripted model) ─────────────


@pytest.mark.asyncio
async def test_every_child_runs_exactly_once_end_to_end():
    """The children must be spawned, and spawned ONCE.

    Two failure modes this catches, and they pull in opposite directions:
      * forget the `dispatched_by` skip → each child runs TWICE (once in the
        serial loop, once as a worker), doubling cost and racing on its artifact;
      * skip them without wiring the fan-out → they never run at all and the
        parent finds no files.
    """
    from tests.agents._scripted_model import _drive

    events = await _drive("sample_subagents_parallel")
    assert events

    started = [
        e["data"].get("agent_id")
        for e in events
        if e["type"] == "agent_start"
    ]
    # Each child now emits its own live agent_start (per-child streaming via the
    # fan-out side-channel queue), same as the parent — but EXACTLY ONCE each.
    # A `dispatched_by` regression would double a child's agent_start (once in
    # the serial loop, once as a worker); a missing fan-out wire would drop it
    # entirely. Order isn't asserted (workers race), only exactly-once-each.
    assert sorted(started) == sorted([
        "custom-agent:page", "custom-agent:apple", "custom-agent:ball", "custom-agent:cat",
    ]), started

    spawned = [e for e in events if e["type"] == "subagent_spawned"]
    assert len(spawned) == 3, f"expected 3 spawned children, got {len(spawned)}"
