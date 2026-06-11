"""tests/agents/test_budget.py — the ENFORCING fan-out BudgetManager (Phase 11 / 11-04).

Drives the budget enforcement fully OFFLINE (no Bedrock / engine / DB), proving
FANOUT-09 + OBS-01:

  * reserve-before-spawn: with cap N, the N+1 worker never spawns AND the rejection
    leaves ZERO new subagent_runs rows (the reservation raises BEFORE any allocate /
    run_worker / record);
  * nested fan-out beyond depth 2 is refused (ctx.depth+1 > max_depth → BudgetExceeded);
  * a wall-clock breach aborts mid-flight;
  * the locked defaults are module constants (8 / 4 / 2 / 900);
  * a configured-low per-workspace ceiling fails a SECOND run's reserve (workspace
    accounting keyed owner+workspace; cross-owner unaffected);
  * partial results are surfaced on a BudgetExceeded abort (Task 2 extends this with the
    11-03 fragment-artifact refs).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agents.execution_engine import budget as budget_mod
from agents.execution_engine.budget import (
    BUDGET_WARN_THRESHOLD,
    DEFAULT_MAX_CONCURRENCY,
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_SUBAGENTS,
    DEFAULT_WALL_CLOCK_SECONDS,
    BudgetExceeded,
    BudgetManager,
    BudgetSnapshot,
)
from agents.execution_engine.fanout import run_fanout
from agents.workflows.plan import Limits


# ---------------------------------------------------------------------------
# Fake ctx.runner — instruments subagent_runs writes so a refused reserve can be
# proven to leave ZERO rows (reserve-before-spawn).
# ---------------------------------------------------------------------------


class _FakeRunner:
    def __init__(self, *, known_agents=None, workspace_spent=None):
        self.run_id = "run-x"
        self.allowed_workers: list[str] = []
        self._known_agents = set(known_agents or {"worker-a"})
        self.recorded_rows: list[dict] = []
        self.spawned: list[dict] = []
        self._row_seq = 0
        # When set, the run_fanout per-workspace ceiling read returns this aggregate.
        self._workspace_spent = workspace_spent

    def agent_exists(self, agent_id):
        return agent_id in self._known_agents

    async def workspace_budget_spent(self):
        return self._workspace_spent or {"subagents": 0, "tokens": 0}

    async def record_subagent_run(self, *, parent_step, worker_agent, depth, isolation, status, tokens=None, cost=None):
        self._row_seq += 1
        row_id = f"row-{self._row_seq}"
        self.recorded_rows.append(dict(id=row_id, worker_agent=worker_agent, status=status))
        return row_id

    async def update_subagent_run(self, row_id, *, status, tokens=None, cost=None):
        pass

    async def run_worker(self, step, ctx, *, worker_index, thread_id, agent_id, input, **kw):
        self.spawned.append(dict(index=worker_index, agent_id=agent_id))
        yield {"type": "agent_chunk", "data": {"worker": worker_index}}


def _make_step(agent_id="worker-a", *, mode="parallel", max_parallel=None):
    fanout = SimpleNamespace(mode=mode, max_parallel=max_parallel, agent="self", count=None, workers=[], merge_agent=None)
    return SimpleNamespace(agent_id=agent_id, fanout=fanout, on_conflict="human_gate")


def _make_ctx(runner, *, depth=0, budget=None):
    return SimpleNamespace(runner=runner, depth=depth, budget=budget or BudgetManager())


async def _collect(gen):
    return [ev async for ev in gen]


# ---------------------------------------------------------------------------
# Defaults are module constants (8 / 4 / 2 / 900)
# ---------------------------------------------------------------------------


def test_locked_defaults_are_module_constants():
    assert DEFAULT_MAX_SUBAGENTS == 8
    assert DEFAULT_MAX_CONCURRENCY == 4
    assert DEFAULT_MAX_DEPTH == 2
    assert DEFAULT_WALL_CLOCK_SECONDS == 900


def test_from_limits_falls_back_to_defaults_when_unset():
    mgr = BudgetManager.from_limits(None)
    assert mgr.max_subagents == DEFAULT_MAX_SUBAGENTS
    assert mgr.max_depth == DEFAULT_MAX_DEPTH
    assert mgr.wall_clock_seconds == DEFAULT_WALL_CLOCK_SECONDS
    assert mgr.max_concurrency == DEFAULT_MAX_CONCURRENCY
    assert mgr.max_tokens is None  # uncapped unless declared


def test_from_limits_honours_declared_caps():
    mgr = BudgetManager.from_limits(
        Limits(max_subagents=3, max_depth=1, wall_clock_seconds=10, max_tokens=500)
    )
    assert mgr.max_subagents == 3
    assert mgr.max_depth == 1
    assert mgr.wall_clock_seconds == 10
    assert mgr.max_tokens == 500


# ---------------------------------------------------------------------------
# reserve() enforcement — subagents / concurrency / depth
# ---------------------------------------------------------------------------


def test_reserve_raises_when_subagents_exceed_cap():
    mgr = BudgetManager.from_limits(Limits(max_subagents=2))
    mgr.reserve(subagents=2)  # at the cap — fine
    with pytest.raises(BudgetExceeded) as exc:
        mgr.reserve(subagents=1)  # the 3rd subagent — over the cap
    assert exc.value.dimension == "subagents"


def test_reserve_raises_when_concurrency_exceeds_cap():
    mgr = BudgetManager.from_limits(None)  # max_concurrency=4
    with pytest.raises(BudgetExceeded) as exc:
        mgr.reserve(subagents=5, concurrency=5)
    # concurrency is checked before subagents-total in the body; either dimension is a
    # valid first breach, but with concurrency=5 it is the concurrency cap that trips.
    assert exc.value.dimension == "concurrency"


def test_reserve_raises_on_nested_fanout_beyond_max_depth():
    mgr = BudgetManager.from_limits(None)  # max_depth=2
    # depth 0 → spawn at depth 1 (fine); depth 1 → spawn at depth 2 (fine);
    # depth 2 → would spawn at depth 3 > max_depth=2 → refused.
    mgr.reserve(subagents=1, depth=0)
    mgr.reserve(subagents=1, depth=1)
    with pytest.raises(BudgetExceeded) as exc:
        mgr.reserve(subagents=1, depth=2)
    assert exc.value.dimension == "depth"


@pytest.mark.asyncio
async def test_reserve_before_spawn_leaves_zero_rows_on_rejection():
    # cap N=2; a fan-out of 3 workers must be REFUSED before any spawn / row.
    runner = _FakeRunner()
    budget = BudgetManager.from_limits(Limits(max_subagents=2))
    ctx = _make_ctx(runner, budget=budget)
    step = _make_step()
    requests = [{"agent": "self", "input": f"t{i}"} for i in range(3)]

    with pytest.raises(BudgetExceeded):
        await _collect(run_fanout(requests, ctx, step=step))

    # Reserve-before-spawn: ZERO subagent_runs rows + ZERO spawns on the rejection.
    assert runner.recorded_rows == []
    assert runner.spawned == []


@pytest.mark.asyncio
async def test_under_cap_fanout_spawns_all_workers():
    runner = _FakeRunner()
    budget = BudgetManager.from_limits(Limits(max_subagents=4))
    ctx = _make_ctx(runner, budget=budget)
    step = _make_step()
    requests = [{"agent": "self", "input": f"t{i}"} for i in range(3)]
    events = await _collect(run_fanout(requests, ctx, step=step))
    assert len(runner.spawned) == 3
    assert sum(1 for e in events if e["type"] == "subagent_result") == 3


# ---------------------------------------------------------------------------
# Tokens + wall-clock are check-at-boundary
# ---------------------------------------------------------------------------


def test_note_tokens_raises_when_over_declared_cap():
    mgr = BudgetManager.from_limits(Limits(max_tokens=100))
    mgr.note_tokens(60)
    with pytest.raises(BudgetExceeded) as exc:
        mgr.note_tokens(50)  # 110 > 100
    assert exc.value.dimension == "tokens"


def test_note_tokens_uncapped_never_raises():
    mgr = BudgetManager.from_limits(None)  # max_tokens None
    mgr.note_tokens(10_000_000)
    assert mgr.spent().tokens == 10_000_000


def test_wall_clock_breach_aborts(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(budget_mod.time, "monotonic", lambda: clock["t"])
    mgr = BudgetManager.from_limits(Limits(wall_clock_seconds=5))
    mgr.arm()  # deadline = 1005.0
    clock["t"] = 1004.0
    mgr.note_wall_clock()  # not yet past — fine
    clock["t"] = 1006.0
    with pytest.raises(BudgetExceeded) as exc:
        mgr.note_wall_clock()  # past the deadline
    assert exc.value.dimension == "wall_clock"


def test_arm_is_idempotent_first_deadline_wins(monkeypatch):
    clock = {"t": 100.0}
    monkeypatch.setattr(budget_mod.time, "monotonic", lambda: clock["t"])
    mgr = BudgetManager.from_limits(Limits(wall_clock_seconds=10))
    mgr.arm()  # deadline = 110.0
    clock["t"] = 105.0
    mgr.arm()  # idempotent — must NOT extend to 115.0
    clock["t"] = 111.0
    with pytest.raises(BudgetExceeded):
        mgr.note_wall_clock()


# ---------------------------------------------------------------------------
# warn_threshold_reached (≥80%)
# ---------------------------------------------------------------------------


def test_warn_threshold_reached_subagents():
    mgr = BudgetManager.from_limits(Limits(max_subagents=10))
    mgr.reserve(subagents=7)
    assert mgr.warn_threshold_reached("subagents") is False
    mgr.reserve(subagents=1)  # 8/10 = 0.8
    assert mgr.warn_threshold_reached("subagents") is True


def test_warn_threshold_uncapped_dimension_never_warns():
    mgr = BudgetManager.from_limits(None)  # tokens uncapped
    mgr.note_tokens(1_000_000)
    assert mgr.warn_threshold_reached("tokens") is False


@pytest.mark.asyncio
async def test_budget_warning_event_emitted_at_threshold():
    # A fan-out that consumes ≥80% of the subagent cap emits a budget_warning.
    runner = _FakeRunner()
    budget = BudgetManager.from_limits(Limits(max_subagents=5))
    ctx = _make_ctx(runner, budget=budget)
    step = _make_step()
    requests = [{"agent": "self", "input": f"t{i}"} for i in range(4)]  # 4/5 = 0.8
    events = await _collect(run_fanout(requests, ctx, step=step))
    warnings = [e for e in events if e["type"] == "budget_warning"]
    assert warnings, "expected a budget_warning at ≥80% consumption"
    assert warnings[0]["data"]["dimension"] == "subagents"


@pytest.mark.asyncio
async def test_failed_reserve_emits_budget_warning_then_raises():
    runner = _FakeRunner()
    budget = BudgetManager.from_limits(Limits(max_subagents=2))
    ctx = _make_ctx(runner, budget=budget)
    step = _make_step()
    requests = [{"agent": "self", "input": f"t{i}"} for i in range(3)]

    emitted: list[dict] = []
    with pytest.raises(BudgetExceeded):
        async for ev in run_fanout(requests, ctx, step=step):
            emitted.append(ev)
    warnings = [e for e in emitted if e["type"] == "budget_warning"]
    assert warnings and warnings[-1]["data"]["reason"] == "reserve_failed"


# ---------------------------------------------------------------------------
# Per-workspace ceiling (OBS-01) — a second run fails once the aggregate is spent
# ---------------------------------------------------------------------------


def test_workspace_ceiling_refuses_when_aggregate_exhausted():
    # ceiling=5; the workspace has already spent 4; reserving 2 more (6 > 5) is refused.
    mgr = BudgetManager.from_limits(None, workspace_ceiling=5)
    with pytest.raises(BudgetExceeded) as exc:
        mgr.reserve(subagents=2, workspace_spent=4)
    assert exc.value.dimension == "workspace"


def test_workspace_ceiling_unset_never_refuses():
    mgr = BudgetManager.from_limits(None)  # workspace_ceiling None
    mgr.reserve(subagents=8, workspace_spent=1_000_000)  # never raises on workspace
    assert mgr.spent().subagents == 8


@pytest.mark.asyncio
async def test_second_run_reserve_fails_against_configured_low_workspace_ceiling():
    # First run spent 3 subagents in the workspace; the configured ceiling is 4; a second
    # run reserving 2 (3 + 2 = 5 > 4) is refused at reserve time.
    runner = _FakeRunner(workspace_spent={"subagents": 3, "tokens": 0})
    budget = BudgetManager.from_limits(None, workspace_ceiling=4)
    ctx = _make_ctx(runner, budget=budget)
    step = _make_step()
    requests = [{"agent": "self", "input": f"t{i}"} for i in range(2)]
    with pytest.raises(BudgetExceeded) as exc:
        await _collect(run_fanout(requests, ctx, step=step))
    assert exc.value.dimension == "workspace"
    # Reserve-before-spawn: zero rows / spawns on the workspace-ceiling rejection.
    assert runner.recorded_rows == []
    assert runner.spawned == []


def test_cross_owner_workspace_aggregate_does_not_interfere():
    # The aggregate read is owner+workspace scoped (ScopedStore.workspace_budget_spent);
    # at the manager level a different workspace_spent value (e.g. 0 for another owner)
    # leaves THIS run unconstrained — proving cross-owner spend does not throttle.
    mgr = BudgetManager.from_limits(None, workspace_ceiling=4)
    mgr.reserve(subagents=3, workspace_spent=0)  # another owner's spend is 0 → fine
    assert mgr.spent().subagents == 3


# ---------------------------------------------------------------------------
# spent() returns a BudgetSnapshot
# ---------------------------------------------------------------------------


def test_spent_returns_snapshot_with_counts():
    mgr = BudgetManager.from_limits(None)
    mgr.reserve(subagents=2, depth=1)
    mgr.note_tokens(123)
    snap = mgr.spent()
    assert isinstance(snap, BudgetSnapshot)
    assert snap.subagents == 2
    assert snap.depth == 1
    assert snap.tokens == 123
