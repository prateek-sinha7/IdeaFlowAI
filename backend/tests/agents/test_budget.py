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

    async def record_subagent_run(self, *, parent_step, worker_agent, depth, isolation, status, tokens=None, cost=None, worker_index=None, task_id=None):
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
# CR-04 — the wall-clock / token boundaries are WIRED into run_fanout (not just
# unit-invokable): a mid-flight breach aborts the fan-out at the next boundary.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wall_clock_breach_mid_flight_stops_next_sequential_spawn(monkeypatch):
    """run_fanout checks note_wall_clock BETWEEN sequential workers (CR-04)."""
    clock = {"t": 1000.0}
    monkeypatch.setattr(budget_mod.time, "monotonic", lambda: clock["t"])

    runner = _FakeRunner()
    _orig = runner.run_worker

    async def _slow(step, ctx, *, worker_index, thread_id, agent_id, input, **kw):
        clock["t"] += 10.0  # worker 0 burns past the 5s deadline mid-flight
        async for ev in _orig(
            step, ctx, worker_index=worker_index, thread_id=thread_id,
            agent_id=agent_id, input=input, **kw,
        ):
            yield ev

    runner.run_worker = _slow  # type: ignore[assignment]
    budget = BudgetManager.from_limits(Limits(wall_clock_seconds=5))
    ctx = _make_ctx(runner, budget=budget)
    step = _make_step(mode="sequential")
    requests = [{"agent": "self", "input": f"t{i}"} for i in range(3)]

    with pytest.raises(BudgetExceeded) as exc:
        await _collect(run_fanout(requests, ctx, step=step))
    assert exc.value.dimension == "wall_clock"
    # Worker 0 ran; the breach aborted BEFORE worker 1 spawned (graceful mid-flight abort).
    assert [w["index"] for w in runner.spawned] == [0]


@pytest.mark.asyncio
async def test_worker_token_usage_enforced_at_collect_boundary():
    """run_fanout accumulates worker agent_complete tokens via note_tokens (CR-04)."""
    runner = _FakeRunner()

    async def _tokened(step, ctx, *, worker_index, thread_id, agent_id, input, **kw):
        runner.spawned.append(dict(index=worker_index, agent_id=agent_id))
        yield {"type": "agent_complete", "data": {"total_tokens": 80}}

    runner.run_worker = _tokened  # type: ignore[assignment]
    budget = BudgetManager.from_limits(Limits(max_tokens=100))
    ctx = _make_ctx(runner, budget=budget)
    step = _make_step(mode="sequential")
    requests = [{"agent": "self", "input": f"t{i}"} for i in range(3)]

    with pytest.raises(BudgetExceeded) as exc:
        await _collect(run_fanout(requests, ctx, step=step))
    assert exc.value.dimension == "tokens"
    # Worker 0 (80 ≤ 100) collected clean; worker 1 breached (160 > 100) at ITS
    # collect boundary; worker 2 never spawned.
    assert [w["index"] for w in runner.spawned] == [0, 1]


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


# ===========================================================================
# Task 2 — BudgetSnapshot persistence + partial-results surfacing
# ===========================================================================

from agents.artifacts.graph import ArtifactGraph
from agents.execution_engine.engine import ExecutionEngine
from agents.execution_engine.kernel_services import KernelServices


class _PersistEctx:
    """A minimal ectx carrying a scoped_store + artifacts graph for persist tests."""

    def __init__(self, store=None, graph=None, run_id="run-x"):
        self.scoped_store = store
        self.artifacts = graph
        self.run_id = run_id
        self.workspace_id = "ws-1"
        self.od_context = None


class _RecordingStore:
    """Records persist_budget_snapshot / workspace_budget_spent calls."""

    def __init__(self, *, spent=None, raise_on_persist=False):
        self.persisted: list[tuple] = []
        self._spent = spent or {"subagents": 0, "tokens": 0}
        self._raise = raise_on_persist

    async def persist_budget_snapshot(self, run_id, snapshot):
        if self._raise:
            raise RuntimeError("boom")
        self.persisted.append((run_id, snapshot))

    async def workspace_budget_spent(self, workspace_id=None):
        return self._spent


def _ks(ectx):
    """Build a KernelServices via __new__ + the minimal attrs the persist/aggregate
    handles touch (the test_fanout kernel-handle precedent — the full ctor needs a
    sandbox/ordered_agents we don't exercise here)."""
    ks = KernelServices.__new__(KernelServices)
    ks._engine = None
    ks._ectx = ectx
    ks.run_id = ectx.run_id
    return ks


# ── KernelServices.persist_budget_snapshot (None-degrading) ────────────────


@pytest.mark.asyncio
async def test_persist_budget_snapshot_writes_through_store():
    store = _RecordingStore()
    ks = _ks(_PersistEctx(store=store))
    snap = BudgetSnapshot(tokens=42, subagents=3, depth=1, wall_clock_seconds=5.0)
    await ks.persist_budget_snapshot(snap)
    assert len(store.persisted) == 1
    run_id, payload = store.persisted[0]
    assert run_id == "run-x"
    assert payload["tokens"] == 42 and payload["subagents"] == 3
    assert payload["depth"] == 1 and payload["wall_clock_seconds"] == 5.0


@pytest.mark.asyncio
async def test_persist_budget_snapshot_none_store_degrades():
    ks = _ks(_PersistEctx(store=None))
    # No store → no-op, never raises.
    await ks.persist_budget_snapshot(BudgetSnapshot(subagents=1))


@pytest.mark.asyncio
async def test_persist_budget_snapshot_store_error_never_aborts():
    store = _RecordingStore(raise_on_persist=True)
    ks = _ks(_PersistEctx(store=store))
    # A store failure must degrade (logger.warning) — never propagate.
    await ks.persist_budget_snapshot(BudgetSnapshot(subagents=1))


# ── ScopedStore.workspace_budget_spent + persist via KernelServices handle ──


@pytest.mark.asyncio
async def test_workspace_budget_spent_handle_reads_store():
    store = _RecordingStore(spent={"subagents": 7, "tokens": 200})
    ks = _ks(_PersistEctx(store=store))
    out = await ks.workspace_budget_spent()
    assert out["subagents"] == 7 and out["tokens"] == 200


@pytest.mark.asyncio
async def test_workspace_budget_spent_handle_none_store_degrades():
    ks = _ks(_PersistEctx(store=None))
    out = await ks.workspace_budget_spent()
    assert out == {"subagents": 0, "tokens": 0}


# ── Engine helper: snapshot persistence is STRICTLY CONDITIONAL ────────────


class _SnapEctx:
    """Carries a budget + a runner handle for the engine persist-helper tests."""

    def __init__(self, budget, runner, graph=None, run_id="run-x"):
        self.budget = budget
        self.runner = runner
        self.artifacts = graph
        self.run_id = run_id


class _SnapRunner:
    def __init__(self):
        self.persisted: list = []

    async def persist_budget_snapshot(self, snapshot):
        self.persisted.append(snapshot)


@pytest.mark.asyncio
async def test_engine_persists_snapshot_when_fanout_active():
    engine = ExecutionEngine()
    budget = BudgetManager.from_limits(None)
    budget.reserve(subagents=2)  # fan-out activity
    runner = _SnapRunner()
    ectx = _SnapEctx(budget, runner)
    await engine._persist_budget_snapshot_if_active(ectx)
    assert len(runner.persisted) == 1
    assert runner.persisted[0].subagents == 2


@pytest.mark.asyncio
async def test_engine_skips_snapshot_when_no_fanout_activity():
    # A run that never fanned out (subagents=0, no tokens/wall-clock) writes NOTHING —
    # the byte/event-identical guarantee for existing workflows (Pitfall 3).
    engine = ExecutionEngine()
    budget = BudgetManager.from_limits(None)  # nothing reserved
    runner = _SnapRunner()
    ectx = _SnapEctx(budget, runner)
    await engine._persist_budget_snapshot_if_active(ectx)
    assert runner.persisted == []


@pytest.mark.asyncio
async def test_engine_force_persists_snapshot_on_abort():
    # force=True (the BudgetExceeded abort) persists even if the snapshot looks inactive.
    engine = ExecutionEngine()
    budget = BudgetManager.from_limits(None)
    runner = _SnapRunner()
    ectx = _SnapEctx(budget, runner)
    await engine._persist_budget_snapshot_if_active(ectx, force=True)
    assert len(runner.persisted) == 1


# ── Engine helper: partial-results surfacing (the completed 11-03 fragments) ─


def test_engine_collects_partial_fragments_from_graph():
    # The completed workers' fragment artifacts (11-03 write_fragment_artifact, kind
    # file_bundle) are surfaced on the abort path with their artifact-ref ids.
    engine = ExecutionEngine()
    graph = ArtifactGraph()
    ref = graph.write_ref(
        run_id="run-x", owner_id="o", workspace_id="ws-1", kind="file_bundle",
        producer_step="fanout-step", producer_agent="worker-a", task_id="0",
        content="<html>frag</html>", location="prototype.html", visibility="workspace",
    )
    ectx = _SnapEctx(BudgetManager.from_limits(None), _SnapRunner(), graph=graph)
    fragments = engine._collect_partial_fragments(ectx)
    assert len(fragments) == 1
    assert fragments[0]["artifact_ref"] == ref.id
    assert fragments[0]["producer_step"] == "fanout-step"
    assert fragments[0]["producer_agent"] == "worker-a"


def test_engine_partial_fragments_empty_when_no_graph():
    engine = ExecutionEngine()
    ectx = _SnapEctx(BudgetManager.from_limits(None), _SnapRunner(), graph=None)
    assert engine._collect_partial_fragments(ectx) == []


def test_engine_partial_fragments_only_fragment_kinds():
    # Non-fragment refs (e.g. a plan markdown) are NOT surfaced — only the completed
    # workers' fragment artifacts.
    engine = ExecutionEngine()
    graph = ArtifactGraph()
    graph.write_ref(
        run_id="run-x", owner_id="o", workspace_id="ws-1", kind="plan",
        producer_step="planner", producer_agent="planner-a", task_id=None,
        content="# plan", location="tasks.md", visibility="workspace",
    )
    graph.write_ref(
        run_id="run-x", owner_id="o", workspace_id="ws-1", kind="file_bundle",
        producer_step="fanout-step", producer_agent="worker-a", task_id="0",
        content="frag", location="prototype.html", visibility="workspace",
    )
    ectx = _SnapEctx(BudgetManager.from_limits(None), _SnapRunner(), graph=graph)
    fragments = engine._collect_partial_fragments(ectx)
    assert len(fragments) == 1
    assert fragments[0]["producer_step"] == "fanout-step"


# ===========================================================================
# Real-DB persistence — budget_snapshot_json written on completion AND abort
# ===========================================================================


def _in_memory_store(owner_id="alice", workspace_id="ws-1"):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import app.models  # noqa: F401 — register models on Base.metadata
    from app.models.database import Base
    from agents.authz import ScopedStore

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()
    store = ScopedStore(owner_id=owner_id, workspace_id=workspace_id, session=session)
    return store, session


def _seed_run(session, run_id, owner_id="alice", workspace_id="ws-1"):
    from app.models.workflow import WorkflowRun

    row = WorkflowRun(
        id=run_id, user_id=owner_id, owner_id=owner_id, workspace_id=workspace_id,
        type="custom", input="go", status="running",
    )
    session.add(row)
    session.commit()
    return row


@pytest.mark.asyncio
async def test_budget_snapshot_persisted_to_workflow_runs_on_completion():
    store, session = _in_memory_store()
    _seed_run(session, "run-done")
    snap = {"tokens": 100, "cost": None, "subagents": 3, "depth": 1, "wall_clock_seconds": 4.0}
    await store.persist_budget_snapshot("run-done", snap)

    from app.models.workflow import WorkflowRun
    row = session.query(WorkflowRun).filter(WorkflowRun.id == "run-done").first()
    assert row.budget_snapshot_json is not None
    assert row.budget_snapshot_json["subagents"] == 3
    assert row.budget_snapshot_json["tokens"] == 100


@pytest.mark.asyncio
async def test_budget_snapshot_persisted_to_workflow_runs_on_abort():
    # The abort path writes the SAME column with the spend-at-abort figures.
    store, session = _in_memory_store()
    _seed_run(session, "run-abort")
    snap = {"tokens": 50, "cost": None, "subagents": 8, "depth": 2, "wall_clock_seconds": 1.0}
    await store.persist_budget_snapshot("run-abort", snap)

    from app.models.workflow import WorkflowRun
    row = session.query(WorkflowRun).filter(WorkflowRun.id == "run-abort").first()
    assert row.budget_snapshot_json["subagents"] == 8
    assert row.budget_snapshot_json["depth"] == 2


@pytest.mark.asyncio
async def test_persist_budget_snapshot_cross_owner_is_noop():
    # A cross-owner caller can never stamp another owner's run (default-deny).
    store, session = _in_memory_store(owner_id="alice")
    _seed_run(session, "run-alice", owner_id="alice")

    from agents.authz import ScopedStore
    bob = ScopedStore(owner_id="bob", workspace_id="ws-1", session=session)
    await bob.persist_budget_snapshot("run-alice", {"subagents": 99})

    from app.models.workflow import WorkflowRun
    row = session.query(WorkflowRun).filter(WorkflowRun.id == "run-alice").first()
    assert row.budget_snapshot_json is None  # untouched — cross-owner no-op


@pytest.mark.asyncio
async def test_workspace_budget_spent_aggregate_owner_scoped():
    # subagent_runs across the workspace's runs are summed for THIS owner; a cross-owner
    # workspace's rows are NEVER counted (T-11-04-04 default-deny).
    store, session = _in_memory_store(owner_id="alice", workspace_id="ws-1")
    # Two of alice's subagent_runs in ws-1.
    await store.record_subagent_run(
        "run-1", parent_step="fan", worker_agent="w", depth=0, isolation="shared_read",
        status="complete",
    )
    await store.record_subagent_run(
        "run-2", parent_step="fan", worker_agent="w", depth=0, isolation="shared_read",
        status="complete",
    )
    # Bob's row in the same workspace name — must NOT be counted for alice.
    from agents.authz import ScopedStore
    bob = ScopedStore(owner_id="bob", workspace_id="ws-1", session=session)
    await bob.record_subagent_run(
        "run-3", parent_step="fan", worker_agent="w", depth=0, isolation="shared_read",
        status="complete",
    )

    agg = await store.workspace_budget_spent("ws-1")
    assert agg["subagents"] == 2  # alice's two only — bob's excluded
