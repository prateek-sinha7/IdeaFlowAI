"""tests/agents/test_fanout_cancel.py — cancellation propagation + zero-residue teardown.

Drives ``agents.execution_engine.fanout.run_fanout`` fully OFFLINE against a fake
``ctx.runner`` handle, proving FANOUT-11 + RESUME-01 (the Phase-11 close):

  * cancel mid-PARALLEL fan-out — in-flight workers stop, pending workers never start,
    EVERY child's ``subagent_runs`` row reads terminal ``cancelled``, ``teardown`` runs
    for every allocated isolated workspace (the zero-residue acceptance), and the
    completed workers' fragment artifacts are retained;
  * cancel BETWEEN sequential workers — the next worker never spawns;
  * cancel BEFORE merge — the merge is skipped and the run is cancelled;
  * ``pipeline_cancelled`` flows from the kernel's outer CancelledError handler (here we
    assert the CancelledError propagates out of run_fanout, which is what drives it);
  * zero isolated workspace residue — every allocated workspace was torn down on cancel.

These tests assert the cooperative cancel BOUNDARIES (before the wave, between
sequential workers, before merge) + the ``finally`` teardown of every allocation. They
are offline (no Bedrock / engine / DB) — a fake runner records allocations + teardowns
and a real ``asyncio.Event`` is the cancel signal.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from agents.execution_engine.budget import BudgetManager
from agents.execution_engine.fanout import run_fanout


# ---------------------------------------------------------------------------
# Fake isolated workspace + ctx.runner handle (cancel-aware).
# ---------------------------------------------------------------------------


class _FakeWorkspace:
    """A stand-in isolated workspace recording its own teardown + written files."""

    def __init__(self, index: int, *, files: dict | None = None) -> None:
        self.index = index
        self.torn_down = False
        # _sandbox.root surface so run_fanout._fragment_files can read written files.
        self._files = dict(files or {})
        self._sandbox = SimpleNamespace(root=None)
        # Worktree workspaces stamp _worktree_branch; sub_sandbox leaves it None.
        self._worktree_branch = None


class _CancelRunner:
    """A ``ctx.runner`` standing in for KernelServices in the cancel tests.

    Allocates a ``_FakeWorkspace`` per worker, records every subagent_runs write/update,
    and tracks teardown calls so the zero-residue acceptance can assert no leaks.
    ``run_worker`` blocks until released so the test can fire the cancel mid-flight.
    """

    def __init__(self, *, allowed_workers=None, known_agents=None, block: bool = True):
        self.run_id = "run-cancel"
        self.allowed_workers = list(allowed_workers or [])
        self._known_agents = set(known_agents or [])
        self._block = block
        self.workspace = SimpleNamespace(has_git=False)  # -> sub_sandbox scope
        # Instrumentation.
        self.recorded_rows: list[dict] = []
        self.updated_rows: list[dict] = []
        self.allocated: list[_FakeWorkspace] = []
        self.torn_down: list[int] = []
        self.fragments_written: list[dict] = []
        self.entered: list[int] = []  # worker indices that started run_worker
        self._row_seq = 0
        # A barrier the test releases (or cancels through).
        self._release = asyncio.Event()

    # -- selection / registry -------------------------------------------------
    def agent_exists(self, agent_id: str) -> bool:
        return agent_id in self._known_agents

    # -- isolation alloc / teardown ------------------------------------------
    async def allocate_isolated_workspace(self, scope, step, *, worker_index):
        ws = _FakeWorkspace(worker_index)
        self.allocated.append(ws)
        return ws

    async def teardown_isolated_workspace(self, base_workspace, worker_ws):
        if worker_ws is not None:
            worker_ws.torn_down = True
            self.torn_down.append(worker_ws.index)

    async def reclaim_isolated_workspace(self, base_workspace, worker_ws):
        # The teardown handle is preferred; reclaim is the fallback (also tracked).
        await self.teardown_isolated_workspace(base_workspace, worker_ws)

    # -- subagent_runs audit --------------------------------------------------
    async def record_subagent_run(self, *, parent_step, worker_agent, depth, isolation, status, tokens=None, cost=None):
        self._row_seq += 1
        row_id = f"row-{self._row_seq}"
        self.recorded_rows.append(dict(id=row_id, worker_agent=worker_agent, status=status))
        return row_id

    async def update_subagent_run(self, row_id, *, status, tokens=None, cost=None):
        self.updated_rows.append(dict(id=row_id, status=status))

    # -- worker run + fragment persistence -----------------------------------
    async def run_worker(self, step, ctx, *, worker_index, thread_id, agent_id, input, workspace=None):
        self.entered.append(worker_index)
        if self._block:
            # Block until released — the test fires the cancel while we are in-flight.
            await self._release.wait()
        yield {"type": "agent_chunk", "data": {"worker": worker_index}}

    async def write_fragment_artifact(self, *, producer_step, worker_agent, worker_index, content, location, kind="file_bundle"):
        ref = f"frag-{worker_index}"
        self.fragments_written.append(dict(worker=worker_index, ref=ref, location=location))
        return ref

    def release(self) -> None:
        self._release.set()


def _make_ctx(runner, *, cancel_event=None, depth=0):
    return SimpleNamespace(
        runner=runner, depth=depth, budget=BudgetManager(),
        cancel_event=cancel_event,
    )


def _make_step(agent_id="worker-a", *, mode="parallel", max_parallel=None):
    fanout = SimpleNamespace(mode=mode, max_parallel=max_parallel, agent="self", count=None, workers=[])
    return SimpleNamespace(agent_id=agent_id, fanout=fanout)


# ---------------------------------------------------------------------------
# FANOUT-11 — cancel BEFORE the wave
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_before_wave_spawns_nothing():
    """A cancel_event already set before the fan-out starts spawns ZERO workers."""
    cancel = asyncio.Event()
    cancel.set()
    runner = _CancelRunner(known_agents={"worker-a"}, block=False)
    ctx = _make_ctx(runner, cancel_event=cancel)
    step = _make_step("worker-a")
    requests = [{"agent": "self", "input": f"t-{i}"} for i in range(3)]

    with pytest.raises(asyncio.CancelledError):
        async for _ev in run_fanout(requests, ctx, step=step):
            pass

    assert runner.recorded_rows == [], "a pre-wave cancel must leave zero subagent_runs rows"
    assert runner.allocated == [], "a pre-wave cancel must allocate no workspaces"
    assert runner.entered == [], "a pre-wave cancel must spawn no workers"


# ---------------------------------------------------------------------------
# FANOUT-11 + RESUME-01 — cancel mid-PARALLEL fan-out
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_mid_parallel_marks_rows_cancelled_and_tears_down():
    """Cancel mid-parallel: in-flight stop, rows cancelled, every workspace torn down."""
    cancel = asyncio.Event()
    runner = _CancelRunner(known_agents={"worker-a"}, block=True)
    ctx = _make_ctx(runner, cancel_event=cancel)
    step = _make_step("worker-a")  # parallel, 3 workers all blocking
    requests = [{"agent": "self", "input": f"t-{i}"} for i in range(3)]

    async def _drive():
        events = []
        with pytest.raises(asyncio.CancelledError):
            async for ev in run_fanout(requests, ctx, step=step):
                events.append(ev)
        return events

    task = asyncio.ensure_future(_drive())
    # Let the workers enter run_worker (block on the barrier), then fire the cancel.
    await asyncio.sleep(0.05)
    assert runner.entered, "no worker entered run_worker before the cancel"
    cancel.set()
    await task

    # Every allocated workspace was torn down (zero-residue acceptance — no leaks).
    assert len(runner.allocated) >= 1
    assert all(ws.torn_down for ws in runner.allocated), (
        "some allocated isolated workspaces were NOT torn down on cancel (leak)"
    )
    assert sorted(runner.torn_down) == sorted(ws.index for ws in runner.allocated)

    # Every recorded child row reached terminal `cancelled` (FANOUT-11).
    assert runner.recorded_rows, "no subagent_runs rows were recorded"
    cancelled = [u for u in runner.updated_rows if u["status"] == "cancelled"]
    recorded_ids = {r["id"] for r in runner.recorded_rows}
    cancelled_ids = {u["id"] for u in cancelled}
    assert recorded_ids == cancelled_ids, (
        f"not every recorded child row was marked cancelled: "
        f"recorded={recorded_ids} cancelled={cancelled_ids}"
    )
    assert not any(u["status"] == "complete" for u in runner.updated_rows), (
        "a worker reported complete despite the mid-flight cancel"
    )


@pytest.mark.asyncio
async def test_cancel_mid_parallel_zero_workspace_residue():
    """The zero-residue acceptance: NO allocated workspace remains un-torn-down."""
    cancel = asyncio.Event()
    runner = _CancelRunner(known_agents={"worker-a"}, block=True)
    ctx = _make_ctx(runner, cancel_event=cancel)
    step = _make_step("worker-a")
    requests = [{"agent": "self", "input": f"t-{i}"} for i in range(4)]

    async def _drive():
        with pytest.raises(asyncio.CancelledError):
            async for _ev in run_fanout(requests, ctx, step=step):
                pass

    task = asyncio.ensure_future(_drive())
    await asyncio.sleep(0.05)
    cancel.set()
    await task

    residue = [ws.index for ws in runner.allocated if not ws.torn_down]
    assert residue == [], f"leaked isolated workspaces after cancel: {residue}"


# ---------------------------------------------------------------------------
# WR-04 — a NON-worker exception (e.g. allocate crash) cancels in-flight
# siblings before propagating: no orphaned tasks, no rows left running.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_worker_exception_cancels_siblings_and_flips_rows():
    runner = _CancelRunner(known_agents={"worker-a"}, block=True)
    _orig_alloc = runner.allocate_isolated_workspace

    async def _failing_alloc(scope, step, *, worker_index):
        if worker_index == 2:
            await asyncio.sleep(0.05)  # let the sibling workers enter run_worker first
            raise RuntimeError("allocation exploded")
        return await _orig_alloc(scope, step, worker_index=worker_index)

    runner.allocate_isolated_workspace = _failing_alloc  # type: ignore[assignment]
    ctx = _make_ctx(runner)  # NO cancel_event — the pure exception path
    step = _make_step("worker-a")
    requests = [{"agent": "self", "input": f"t-{i}"} for i in range(3)]

    with pytest.raises(RuntimeError, match="allocation exploded"):
        async for _ev in run_fanout(requests, ctx, step=step):
            pass

    # The blocking siblings were CANCELLED, not orphaned: every recorded row
    # reached terminal cancelled (none left running forever).
    assert runner.recorded_rows, "siblings never recorded rows before the crash"
    assert {u["status"] for u in runner.updated_rows} == {"cancelled"}
    recorded_ids = {r["id"] for r in runner.recorded_rows}
    updated_ids = {u["id"] for u in runner.updated_rows}
    assert recorded_ids == updated_ids, "a row was left running (orphaned sibling)"
    # And the teardown ran only after the siblings stopped — zero residue.
    assert all(ws.torn_down for ws in runner.allocated)


# ---------------------------------------------------------------------------
# RESUME-01 — cancel BETWEEN sequential workers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_between_sequential_workers_stops_next_spawn():
    """Sequential mode: a cancel after worker 0 stops the next worker from spawning."""
    cancel = asyncio.Event()
    # Non-blocking workers so worker 0 completes; we set cancel after it via a runner hook.
    runner = _CancelRunner(known_agents={"worker-a"}, block=False)
    ctx = _make_ctx(runner, cancel_event=cancel)
    step = _make_step("worker-a", mode="sequential")
    requests = [{"agent": "self", "input": f"t-{i}"} for i in range(3)]

    # Fire the cancel as soon as the FIRST worker has entered run_worker, so the
    # between-workers _check_cancel trips before worker 1 spawns.
    _orig_run_worker = runner.run_worker

    async def _hooked(step, ctx, *, worker_index, thread_id, agent_id, input, workspace=None):
        if worker_index == 0:
            cancel.set()
        async for ev in _orig_run_worker(
            step, ctx, worker_index=worker_index, thread_id=thread_id,
            agent_id=agent_id, input=input, workspace=workspace,
        ):
            yield ev

    runner.run_worker = _hooked  # type: ignore[assignment]

    with pytest.raises(asyncio.CancelledError):
        async for _ev in run_fanout(requests, ctx, step=step):
            pass

    # Only worker 0 spawned; worker 1 + 2 never entered run_worker.
    assert runner.entered == [0], f"sequential cancel did not stop the next spawn: {runner.entered}"
    # Worker 0's row flipped complete (it finished before the cancel boundary); no other
    # row was recorded (workers 1/2 never spawned).
    assert len(runner.recorded_rows) == 1
    # Every allocated workspace (just worker 0's) was still torn down (finally).
    assert all(ws.torn_down for ws in runner.allocated)


# ---------------------------------------------------------------------------
# FANOUT-11 — cancel BEFORE merge preserves completed fragments
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_before_merge_preserves_fragments_and_skips_merge():
    """A cancel after collect but before merge: merge skipped, fragments retained."""
    cancel = asyncio.Event()
    runner = _CancelRunner(known_agents={"worker-a"}, block=False)
    ctx = _make_ctx(runner, cancel_event=cancel)
    step = _make_step("worker-a")
    requests = [{"agent": "self", "input": f"t-{i}"} for i in range(2)]

    # Give each fake workspace a written file so write_fragment_artifact fires.
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp())

    _orig_alloc = runner.allocate_isolated_workspace

    async def _alloc_with_file(scope, step_, *, worker_index):
        ws = await _orig_alloc(scope, step_, worker_index=worker_index)
        wdir = tmp / f"w{worker_index}"
        wdir.mkdir(parents=True, exist_ok=True)
        (wdir / f"part_{worker_index}.txt").write_text(f"content-{worker_index}", encoding="utf-8")
        ws._sandbox = SimpleNamespace(root=wdir)
        return ws

    runner.allocate_isolated_workspace = _alloc_with_file  # type: ignore[assignment]

    # Fire the cancel after BOTH workers complete (they are non-blocking), so the
    # pre-merge _check_cancel trips. We hook the second worker's completion.
    _orig_run_worker = runner.run_worker

    async def _hooked(step_, ctx_, *, worker_index, thread_id, agent_id, input, workspace=None):
        async for ev in _orig_run_worker(
            step_, ctx_, worker_index=worker_index, thread_id=thread_id,
            agent_id=agent_id, input=input, workspace=workspace,
        ):
            yield ev
        if worker_index == 1:
            cancel.set()  # both done -> trip the pre-merge boundary

    runner.run_worker = _hooked  # type: ignore[assignment]

    events: list[dict] = []
    with pytest.raises(asyncio.CancelledError):
        async for ev in run_fanout(requests, ctx, step=step):
            events.append(ev)

    # Completed fragments were persisted BEFORE the cancel (retained, not lost).
    assert len(runner.fragments_written) == 2, (
        f"completed fragments were not persisted before cancel: {runner.fragments_written}"
    )
    # The merge never ran (no merge_started / merge_completed event was yielded).
    assert not any(e["type"].startswith("merge_") for e in events), (
        "merge ran despite the pre-merge cancel"
    )
    # Both workers' rows flipped complete (they finished); workspaces torn down.
    assert all(u["status"] == "complete" for u in runner.updated_rows)
    assert all(ws.torn_down for ws in runner.allocated)
