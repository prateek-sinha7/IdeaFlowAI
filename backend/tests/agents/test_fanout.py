"""tests/agents/test_fanout.py — the single kernel run_fanout spawn path (Phase 11).

Drives ``agents.execution_engine.fanout.run_fanout`` fully OFFLINE against a fake
``ctx.runner`` handle (no Bedrock / no engine / no DB), proving FANOUT-02/03/04:

  * FANOUT-02 (funnel): both a declarative ``fanout_batch`` strategy step AND a
    tool-emitted request reach the SAME ``run_fanout`` (the strategy test lives here;
    the engine tool-result derivation funnel is the Task-3 end-to-end test);
  * FANOUT-03 (worker select): ``self``×N spawns N workers reusing the step agent; a
    NAMED worker in ``allowed_workers`` + the registry resolves; a disallowed/unknown
    worker raises BEFORE any spawn, leaving ZERO subagent_runs rows;
  * FANOUT-04 (modes): parallel mode observes max concurrent workers ≤ the cap (4);
    sequential mode runs workers in strict order.

The structured summary carries per-worker STATUS only (no typed artifact refs — those
arrive with 11-03 / FANOUT-06).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from agents.execution_engine.fanout import run_fanout, FanoutError
from agents.execution_engine.budget import BudgetManager


# ---------------------------------------------------------------------------
# Fake ctx.runner handle — the single spawn-path dependency surface.
# ---------------------------------------------------------------------------


class _FakeRunner:
    """A minimal ``ctx.runner`` standing in for KernelServices in the fan-out tests.

    Records every spawned worker + every subagent_runs write, and instruments the
    concurrency observed during a parallel run (the FANOUT-04 cap assertion).
    """

    def __init__(self, *, allowed_workers=None, known_agents=None, worker_delay=0.0):
        self.run_id = "run-x"
        self.allowed_workers = list(allowed_workers or [])
        # The agents the registry "knows" (self resolution + named resolution).
        self._known_agents = set(known_agents or [])
        self._worker_delay = worker_delay
        # Instrumentation.
        self.spawned: list[dict] = []
        self.recorded_rows: list[dict] = []
        self.updated_rows: list[dict] = []
        self._live = 0
        self._max_live = 0
        self._row_seq = 0

    def agent_exists(self, agent_id: str) -> bool:
        return agent_id in self._known_agents

    async def record_subagent_run(self, *, parent_step, worker_agent, depth, isolation, status, tokens=None, cost=None):
        self._row_seq += 1
        row_id = f"row-{self._row_seq}"
        self.recorded_rows.append(
            dict(id=row_id, parent_step=parent_step, worker_agent=worker_agent,
                 depth=depth, isolation=isolation, status=status)
        )
        return row_id

    async def update_subagent_run(self, row_id, *, status, tokens=None, cost=None):
        self.updated_rows.append(dict(id=row_id, status=status, tokens=tokens))

    async def run_worker(self, step, ctx, *, worker_index, thread_id, agent_id, input):
        # Instrument concurrency: track the live-worker high-water mark.
        self._live += 1
        self._max_live = max(self._max_live, self._live)
        self.spawned.append(dict(index=worker_index, thread_id=thread_id, agent_id=agent_id, input=input))
        try:
            if self._worker_delay:
                await asyncio.sleep(self._worker_delay)
            # Re-yield one lifecycle-ish event (workers carry no gates — D-01).
            yield {"type": "agent_chunk", "data": {"worker": worker_index}}
        finally:
            self._live -= 1


def _make_ctx(runner, *, depth=0):
    return SimpleNamespace(runner=runner, depth=depth, budget=BudgetManager())


def _make_step(agent_id="worker-a", *, mode="parallel", max_parallel=None):
    fanout = SimpleNamespace(mode=mode, max_parallel=max_parallel, agent="self", count=None, workers=[])
    return SimpleNamespace(agent_id=agent_id, fanout=fanout)


async def _collect(gen):
    return [ev async for ev in gen]


# ---------------------------------------------------------------------------
# FANOUT-03 — worker selection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_self_n_spawns_n_workers():
    runner = _FakeRunner(known_agents={"worker-a"})
    ctx = _make_ctx(runner)
    step = _make_step("worker-a")
    requests = [{"agent": "self", "input": f"task-{i}"} for i in range(3)]

    events = await _collect(run_fanout(requests, ctx, step=step))

    assert len(runner.spawned) == 3
    assert all(w["agent_id"] == "worker-a" for w in runner.spawned)
    # One subagent_runs row per child (status running at spawn).
    assert len(runner.recorded_rows) == 3
    assert all(r["status"] == "running" for r in runner.recorded_rows)
    # Each child updated terminal on completion.
    assert len(runner.updated_rows) == 3
    assert all(r["status"] == "complete" for r in runner.updated_rows)
    # Lifecycle events present: a subagent_spawned + subagent_result per child.
    spawned_evs = [e for e in events if e["type"] == "subagent_spawned"]
    result_evs = [e for e in events if e["type"] == "subagent_result"]
    assert len(spawned_evs) == 3
    assert len(result_evs) == 3


@pytest.mark.asyncio
async def test_named_worker_in_allowed_workers_resolves():
    runner = _FakeRunner(allowed_workers=["worker-b"], known_agents={"worker-a", "worker-b"})
    ctx = _make_ctx(runner)
    step = _make_step("worker-a")
    requests = [{"agent": "worker-b", "input": "go"}]

    events = await _collect(run_fanout(requests, ctx, step=step))

    assert len(runner.spawned) == 1
    assert runner.spawned[0]["agent_id"] == "worker-b"
    assert any(e["type"] == "subagent_result" for e in events)


@pytest.mark.asyncio
async def test_disallowed_worker_rejected_before_any_spawn():
    runner = _FakeRunner(allowed_workers=["worker-b"], known_agents={"worker-a", "worker-b"})
    ctx = _make_ctx(runner)
    step = _make_step("worker-a")
    # "worker-c" is not in allowed_workers → rejected pre-spawn.
    requests = [{"agent": "worker-c", "input": "go"}]

    with pytest.raises(FanoutError) as exc:
        await _collect(run_fanout(requests, ctx, step=step))
    assert "worker-c" in str(exc.value)
    # ZERO spawns + ZERO subagent_runs rows (pre-spawn rejection).
    assert runner.spawned == []
    assert runner.recorded_rows == []


@pytest.mark.asyncio
async def test_unknown_worker_rejected_before_any_spawn():
    runner = _FakeRunner(allowed_workers=["ghost"], known_agents={"worker-a"})
    ctx = _make_ctx(runner)
    step = _make_step("worker-a")
    # "ghost" is allow-listed but NOT in the agent registry → rejected pre-spawn.
    requests = [{"agent": "ghost", "input": "go"}]

    with pytest.raises(FanoutError):
        await _collect(run_fanout(requests, ctx, step=step))
    assert runner.spawned == []
    assert runner.recorded_rows == []


# ---------------------------------------------------------------------------
# FANOUT-04 — modes + concurrency cap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parallel_mode_observes_concurrency_cap():
    # 10 workers, manifest asks for max_parallel=10, but the engine caps at 4.
    runner = _FakeRunner(known_agents={"worker-a"}, worker_delay=0.02)
    ctx = _make_ctx(runner)
    step = _make_step("worker-a", mode="parallel", max_parallel=10)
    requests = [{"agent": "self", "input": f"t{i}"} for i in range(10)]

    await _collect(run_fanout(requests, ctx, step=step))

    assert len(runner.spawned) == 10
    assert runner._max_live <= 4, f"concurrency exceeded the cap: {runner._max_live}"


@pytest.mark.asyncio
async def test_sequential_mode_runs_in_order():
    runner = _FakeRunner(known_agents={"worker-a"}, worker_delay=0.005)
    ctx = _make_ctx(runner)
    step = _make_step("worker-a", mode="sequential")
    requests = [{"agent": "self", "input": f"t{i}"} for i in range(4)]

    await _collect(run_fanout(requests, ctx, step=step))

    # Strict order: indices observed in ascending order, never overlapping.
    assert [w["index"] for w in runner.spawned] == [0, 1, 2, 3]
    assert runner._max_live == 1, "sequential mode must run one worker at a time"


@pytest.mark.asyncio
async def test_summary_carries_per_worker_status_only():
    runner = _FakeRunner(known_agents={"worker-a"})
    ctx = _make_ctx(runner)
    step = _make_step("worker-a")
    requests = [{"agent": "self", "input": "t0"}, {"agent": "self", "input": "t1"}]

    events = await _collect(run_fanout(requests, ctx, step=step))
    results = [e for e in events if e["type"] == "subagent_result"]
    assert len(results) == 2
    for r in results:
        assert r["data"]["status"] == "complete"
        assert "worker" in r["data"]
        # No typed artifact refs in this plan (those arrive with 11-03).
        assert "artifact_ref" not in r["data"]


# ---------------------------------------------------------------------------
# FANOUT-02 — declarative funnel via the fanout_batch strategy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fanout_batch_strategy_funnels_through_run_fanout():
    """The declarative fanout_batch strategy reaches run_fanout via ctx.runner."""
    from agents.capabilities.registry import discover, CapabilityRegistry

    discover()
    registry = CapabilityRegistry()
    strategy = registry.resolve("strategy", "fanout_batch")

    # A fake runner whose run_fanout records the funnel + the requests it received.
    funnel: dict = {}

    class _StratRunner:
        run_id = "run-y"

        def latest_typed_content(self, producer_step):
            return "## Task 1: A\nbody A\n\n## Task 2: B\nbody B\n"

        async def run_fanout(self, requests, ctx, *, step):
            funnel["requests"] = requests
            funnel["reached"] = True
            yield {"type": "subagent_result", "data": {"worker": 0, "status": "complete"}}

    task_source = SimpleNamespace(parser="heading_tasks", source_step="planner", spec_step=None)
    step = SimpleNamespace(agent_id="worker-a", task_source=task_source, fanout=SimpleNamespace(
        mode="parallel", max_parallel=2, agent="self", count=None, workers=[]))
    ctx = SimpleNamespace(runner=_StratRunner(), deliverable=None, seed_files={}, depth=0)

    events = [ev async for ev in strategy.run(step, ctx)]

    assert funnel.get("reached") is True
    # Two tasks parsed → two worker requests funneled to the SINGLE run_fanout.
    assert len(funnel["requests"]) == 2
    assert all(r["agent"] == "self" for r in funnel["requests"])
    assert any(e["type"] == "subagent_result" for e in events)
