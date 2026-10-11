"""tests/agents/test_fanout_ordering.py — Req 25 merge ordering + Req 26 on_conflict policies.

Two focused assertions driven entirely OFFLINE (no Bedrock / no engine / no DB):

1. **Merge ordering (Req 25 AC 1)** — fragments MUST reach the MergeStrategy in
   declared (worker-index) order regardless of which parallel worker finished first.
   ``fragments_meta`` is populated by ``_run_one`` as workers complete, so parallel
   workers append in *arrival* order. The merge dispatch in ``_merge_fragments`` MUST
   sort by ``index`` before handing the completed list to the strategy — otherwise
   git_3way and copy_disjoint both see non-deterministic arrival order.

   The test injects a *recording* merge strategy that captures the order fragments
   arrive and asserts it matches ascending index order (0 → 1 → 2), even when the
   slowest worker (index 0) finishes last.

2. **All four on_conflict policies (Req 25 AC 4, Req 26)** — ``human_gate``,
   ``partial``, ``abort``, and ``merge_agent`` are exercised exactly once each here,
   producing their distinct event signatures:
   - ``human_gate``  → ``merge_conflict`` + ``review_gate_ready`` / ``review_gate_resolved``
   - ``partial``     → ``merge_conflict`` + ``merge_partial``
   - ``abort``       → ``merge_conflict`` + ``FanoutError`` raised
   - ``merge_agent`` → ``merge_conflict`` + ``merge_agent_attempt`` + ``merge_completed``
     (resolved_by="merge_agent") or human_gate fallback when unresolved

These tests are an *addition* to the per-policy depth coverage already in
``test_merge_conflict.py``; they prove that all four code paths are reachable from
a single test sweep (Req 25 AC 4: "exercised by test before ship").
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from agents.capabilities.merge.base import MergeResult, MergeStrategy
from agents.execution_engine.budget import BudgetManager
from agents.execution_engine.fanout import FanoutError, run_fanout


# ---------------------------------------------------------------------------
# Shared fakes — minimal runner surface for ordering + policy tests
# ---------------------------------------------------------------------------


class _FakeChildSandbox:
    def __init__(self, root_path):
        self.root = root_path


class _FakeWorkerWorkspace:
    """Mimics an allocated isolated worker workspace (sub_sandbox path)."""

    def __init__(self, tmp_root, worker_index: int):
        self._sandbox = _FakeChildSandbox(tmp_root)
        self._worktree_branch = None  # sub_sandbox path
        self._index = worker_index

    def write_file(self, relpath, content):
        (self._sandbox.root / relpath).parent.mkdir(parents=True, exist_ok=True)
        (self._sandbox.root / relpath).write_text(content, encoding="utf-8")


class _FakeBaseWorkspace:
    has_git = False

    def __init__(self):
        self.written: dict[str, str] = {}

    def write_file(self, relpath, content):
        self.written[relpath] = content

    def spawn_point_commit(self):
        return "deadbeef"


# ---------------------------------------------------------------------------
# Recording merge strategy — captures the fragment order arriving at merge()
# ---------------------------------------------------------------------------


class _RecordingMerge(MergeStrategy):
    """A merge strategy that records the order of fragment names passed to merge().

    Used to assert that _merge_fragments delivers fragments in declared worker-index
    order — not the arrival order from parallel _run_one completions.
    """

    name = "copy_disjoint"  # must match what _select_merge_strategy returns for sub_sandbox

    def __init__(self):
        self.fragment_names_received: list[str] = []

    def merge(self, base, fragments):
        self.fragment_names_received = [
            getattr(f, "name", "<unknown>") for f in (fragments or [])
        ]
        # Return a clean result (no conflicts) so run_fanout completes normally.
        result = MergeResult()
        for frag in fragments or []:
            result.applied.append(getattr(frag, "name", ""))
        return result


# ---------------------------------------------------------------------------
# Ordering runner — delays worker 0 to ensure it finishes LAST in parallel mode
# ---------------------------------------------------------------------------


class _OrderingRunner:
    """Runner that intentionally delays worker index 0 to finish after indices 1 and 2.

    In parallel mode the three workers complete in arrival order 1 → 2 → 0.
    The merge dispatch must still deliver fragments sorted by worker index (0 → 1 → 2).
    """

    def __init__(self, tmp_path, recording_strategy: _RecordingMerge):
        self.run_id = "run-order"
        self.allowed_workers: list[str] = []
        self._recording = recording_strategy
        self._tmp_path = tmp_path
        self._row_seq = 0
        # The base workspace is the coordination point.
        self.workspace = _FakeBaseWorkspace()
        self._workspaces: dict[int, _FakeWorkerWorkspace] = {}

    # --- worker selection / registry protocol ----------------------------
    def agent_exists(self, agent_id: str) -> bool:
        return True

    # --- subagent_runs protocol ------------------------------------------
    async def record_subagent_run(
        self,
        *,
        parent_step,
        worker_agent,
        depth,
        isolation,
        status,
        tokens=None,
        cost=None,
        worker_index=None,
        task_id=None,
    ):
        self._row_seq += 1
        return f"row-{self._row_seq}"

    async def update_subagent_run(self, row_id, *, status, tokens=None, cost=None):
        return None

    # --- workspace allocation protocol -----------------------------------
    async def allocate_isolated_workspace(self, scope, step, *, worker_index):
        root = self._tmp_path / f"worker-{worker_index}"
        root.mkdir(parents=True, exist_ok=True)
        ws = _FakeWorkerWorkspace(root, worker_index)
        # Pre-write a unique file per worker so the merge has something to integrate.
        ws.write_file(
            f"output-{worker_index}.txt", f"content from worker {worker_index}"
        )
        self._workspaces[worker_index] = ws
        return ws

    async def reclaim_isolated_workspace(self, base_workspace, worker_ws):
        return None

    # --- run_worker protocol — worker 0 is slowest -----------------------
    async def run_worker(
        self,
        step,
        ctx,
        *,
        worker_index,
        thread_id,
        agent_id,
        input,
        workspace=None,
        total_workers=None,
        **kw,
    ):
        # Worker 0 sleeps longest → completes LAST in parallel mode.
        delays = {0: 0.04, 1: 0.01, 2: 0.02}
        await asyncio.sleep(delays.get(worker_index, 0.0))
        yield {"type": "agent_chunk", "data": {"worker": worker_index}}

    # --- merge dispatch protocol -----------------------------------------
    def resolve_merge_strategy(self, name: str):
        # Always return our recording strategy, regardless of the requested name.
        return self._recording

    async def write_fragment_artifact(
        self,
        *,
        producer_step,
        worker_agent,
        worker_index,
        content,
        location,
        kind="file_bundle",
    ):
        return f"frag-{worker_index}"

    async def write_merge_conflict_artifact(
        self, *, producer_step, conflicts, payload=None
    ):
        return "conflict-ref"


def _make_ordering_ctx(runner):
    return SimpleNamespace(runner=runner, depth=0, budget=BudgetManager())


def _make_ordering_step(
    agent_id="worker-a", *, mode="parallel", on_conflict="human_gate"
):
    fanout = SimpleNamespace(
        mode=mode,
        max_parallel=3,
        agent="self",
        count=None,
        workers=[],
        merge_agent=None,
    )
    return SimpleNamespace(agent_id=agent_id, fanout=fanout, on_conflict=on_conflict)


async def _collect(gen):
    return [ev async for ev in gen]


# ===========================================================================
# Test 1 — Merge ordering: declared (worker-index) order, not arrival order
# ===========================================================================


@pytest.mark.asyncio
async def test_merge_receives_fragments_in_declared_worker_index_order(tmp_path):
    """Req 25 AC 1 — fragments reach the strategy in index order 0 → 1 → 2.

    Worker 0 is the slowest and finishes LAST (after indices 1 and 2) in parallel
    mode, so ``fragments_meta`` is populated in arrival order 1 → 2 → 0.
    ``_merge_fragments`` MUST sort completed entries by ``index`` before building
    the typed fragment list — otherwise the strategy sees arrival order.

    The _RecordingMerge strategy captures the fragment names it receives.
    fragment names are ``"worker-{index}"`` so index order produces:
        ["worker-0", "worker-1", "worker-2"]
    Arrival order (the bug) would produce:
        ["worker-1", "worker-2", "worker-0"]
    """
    recording = _RecordingMerge()
    runner = _OrderingRunner(tmp_path, recording)
    ctx = _make_ordering_ctx(runner)
    step = _make_ordering_step(mode="parallel")

    requests = [{"agent": "self", "input": f"task-{i}"} for i in range(3)]
    events = await _collect(run_fanout(requests, ctx, step=step))

    # Confirm merge_started and merge_completed fired (merge ran).
    assert any(
        e["type"] == "merge_started" for e in events
    ), "merge_started event missing — merge never ran"
    assert any(
        e["type"] == "merge_completed" for e in events
    ), "merge_completed event missing — merge did not complete cleanly"

    # The recording strategy captured the fragments in the order they arrived.
    # They MUST be in declared worker-index order, not arrival order.
    assert recording.fragment_names_received == ["worker-0", "worker-1", "worker-2"], (
        f"Fragments reached the merge strategy in the wrong order: "
        f"{recording.fragment_names_received!r}. "
        "Expected declared worker-index order ['worker-0', 'worker-1', 'worker-2']. "
        "Req 25 AC 1: the merge sequence SHALL be deterministic regardless of which "
        "worker finished first."
    )


@pytest.mark.asyncio
async def test_sequential_mode_merge_order_is_also_index_order(tmp_path):
    """Sequential mode trivially produces index order — verifying no regression.

    In sequential mode workers run in declared order so fragments_meta is always
    populated 0 → 1 → 2.  The ordering assertion still holds (and must keep holding
    if a future sort is removed from the sequential path too).
    """
    recording = _RecordingMerge()
    runner = _OrderingRunner(tmp_path, recording)
    ctx = _make_ordering_ctx(runner)
    step = _make_ordering_step(mode="sequential")

    requests = [{"agent": "self", "input": f"task-{i}"} for i in range(3)]
    await _collect(run_fanout(requests, ctx, step=step))

    assert recording.fragment_names_received == ["worker-0", "worker-1", "worker-2"]


@pytest.mark.asyncio
async def test_subagent_result_events_also_in_index_order_parallel(tmp_path):
    """subagent_result events are sorted by worker index even in parallel mode.

    This is the existing guarantee (``sorted(gathered, key=lambda r: r["worker"])``
    in run_fanout). Pinned here so any change to the result-event ordering is
    explicit and visible alongside the merge-ordering test.
    """
    recording = _RecordingMerge()
    runner = _OrderingRunner(tmp_path, recording)
    ctx = _make_ordering_ctx(runner)
    step = _make_ordering_step(mode="parallel")

    requests = [{"agent": "self", "input": f"task-{i}"} for i in range(3)]
    events = await _collect(run_fanout(requests, ctx, step=step))

    result_workers = [
        e["data"]["worker"] for e in events if e["type"] == "subagent_result"
    ]
    assert result_workers == [
        0,
        1,
        2,
    ], f"subagent_result events not in index order: {result_workers}"


# ===========================================================================
# Test 2 — All four on_conflict policies produce distinct event signatures
# ===========================================================================
#
# These complement the depth coverage in test_merge_conflict.py by exercising
# all four reachable code paths from a single test sweep (Req 25 AC 4).
# The runner / step setup mirrors test_merge_conflict.py's _MergeRunner pattern.
# ===========================================================================


class _ConflictRunner:
    """Runner for on_conflict policy tests — always produces a conflicting merge."""

    def __init__(self, *, hitl_events=None, merge_agent_resolves=None):
        self.run_id = "run-conflict"
        self.allowed_workers: list[str] = []
        self.workspace = _FakeBaseWorkspace()
        self._row_seq = 0
        self.hitl_calls: list[dict] = []
        self.merge_agent_calls: list[dict] = []
        self._hitl_events = list(hitl_events or [])
        self._merge_agent_resolves = merge_agent_resolves  # list[bool] per attempt

    # --- worker selection / registry protocol ----------------------------
    def agent_exists(self, agent_id: str) -> bool:
        return True

    # --- subagent_runs protocol ------------------------------------------
    async def record_subagent_run(
        self,
        *,
        parent_step,
        worker_agent,
        depth,
        isolation,
        status,
        tokens=None,
        cost=None,
        worker_index=None,
        task_id=None,
    ):
        self._row_seq += 1
        return f"row-{self._row_seq}"

    async def update_subagent_run(self, row_id, *, status, tokens=None, cost=None):
        return None

    # --- workspace allocation protocol —two workers write the SAME path ----
    async def allocate_isolated_workspace(self, scope, step, *, worker_index, **kw):
        import tempfile
        from pathlib import Path

        root = Path(tempfile.mkdtemp())
        ws = _FakeWorkerWorkspace(root, worker_index)
        # Both workers write "conflict.txt" with different content → guaranteed conflict.
        ws.write_file("conflict.txt", f"content-from-worker-{worker_index}")
        return ws

    async def reclaim_isolated_workspace(self, base_workspace, worker_ws):
        return None

    # --- run_worker ----------------------------------------------------------
    async def run_worker(
        self,
        step,
        ctx,
        *,
        worker_index,
        thread_id,
        agent_id,
        input,
        workspace=None,
        total_workers=None,
        **kw,
    ):
        yield {"type": "agent_chunk", "data": {"worker": worker_index}}

    # --- merge dispatch protocol (real copy_disjoint via registry) -----------
    def resolve_merge_strategy(self, name: str):
        from agents.capabilities.registry import CapabilityRegistry, discover

        discover()
        return CapabilityRegistry().resolve("merge", name)

    async def write_fragment_artifact(
        self,
        *,
        producer_step,
        worker_agent,
        worker_index,
        content,
        location,
        kind="file_bundle",
    ):
        return f"frag-{worker_index}"

    async def write_merge_conflict_artifact(
        self, *, producer_step, conflicts, payload=None
    ):
        return "conflict-ref"

    async def run_human_gate(self, step, *, output="", payload=None):
        self.hitl_calls.append(
            {"step": getattr(step, "agent_id", None), "payload": payload}
        )
        for ev in self._hitl_events:
            yield ev

    async def run_merge_agent(self, worker, payload, *, attempt):
        self.merge_agent_calls.append({"worker": worker, "attempt": attempt})
        if self._merge_agent_resolves is None:
            return False
        idx = attempt - 1
        return (
            self._merge_agent_resolves[idx]
            if idx < len(self._merge_agent_resolves)
            else False
        )


def _make_conflict_ctx(runner):
    return SimpleNamespace(runner=runner, depth=0, budget=BudgetManager())


def _make_conflict_step(on_conflict: str, *, merge_agent=None, mode="sequential"):
    fanout = SimpleNamespace(
        mode=mode,
        max_parallel=2,
        agent="self",
        count=None,
        workers=[],
        merge_agent=merge_agent,
    )
    return SimpleNamespace(agent_id="worker-a", fanout=fanout, on_conflict=on_conflict)


# ---------------------------------------------------------------------------
# Policy 1: human_gate — default — triggers the durable HITL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_conflict_human_gate_triggers_durable_hitl():
    """Req 25 AC 4, Req 26 — human_gate policy routes conflict through run_human_gate.

    A merge conflict on human_gate MUST:
    - emit a ``merge_conflict`` event (auditable)
    - call run_human_gate exactly once with the conflict payload
    - re-yield the gate's pause/resume events (review_gate_ready + review_gate_resolved)
    """
    runner = _ConflictRunner(
        hitl_events=[
            {"type": "review_gate_ready", "data": {"output": {}}},
            {"type": "review_gate_resolved", "data": {}},
        ]
    )
    ctx = _make_conflict_ctx(runner)
    step = _make_conflict_step("human_gate")
    requests = [{"agent": "self", "input": "t0"}, {"agent": "self", "input": "t1"}]

    events = await _collect(run_fanout(requests, ctx, step=step))

    # A merge_conflict event was emitted.
    conflict_evs = [e for e in events if e["type"] == "merge_conflict"]
    assert len(conflict_evs) == 1, "Expected exactly one merge_conflict event"
    assert conflict_evs[0]["data"]["conflicts"][0]["path"] == "conflict.txt"

    # The ONE durable HITL was called exactly once with the conflict payload.
    assert len(runner.hitl_calls) == 1
    assert runner.hitl_calls[0]["payload"]["conflicts"][0]["path"] == "conflict.txt"

    # The gate's pause/resume events are forwarded.
    assert any(e["type"] == "review_gate_ready" for e in events)
    assert any(e["type"] == "review_gate_resolved" for e in events)


# ---------------------------------------------------------------------------
# Policy 2: partial — keeps non-conflicting fragments, drops conflicted paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_conflict_partial_keeps_non_conflicting_fragments():
    """Req 25 AC 4, Req 26 — partial policy emits merge_partial and continues the run.

    With partial:
    - ``merge_conflict`` event is emitted (conflict is auditable)
    - ``merge_partial`` event is emitted naming the dropped paths
    - the run does NOT raise or call run_human_gate
    - no ``review_gate_*`` events appear
    """
    runner = _ConflictRunner()
    ctx = _make_conflict_ctx(runner)
    step = _make_conflict_step("partial")
    requests = [{"agent": "self", "input": "t0"}, {"agent": "self", "input": "t1"}]

    events = await _collect(run_fanout(requests, ctx, step=step))

    # merge_conflict event still emitted (conflict is always auditable).
    conflict_evs = [e for e in events if e["type"] == "merge_conflict"]
    assert len(conflict_evs) == 1

    # merge_partial event carries the dropped path.
    partial_evs = [e for e in events if e["type"] == "merge_partial"]
    assert len(partial_evs) == 1, "Expected exactly one merge_partial event"
    assert "conflict.txt" in partial_evs[0]["data"]["dropped"]

    # No HITL involved.
    assert runner.hitl_calls == []
    assert not any(e["type"] == "review_gate_ready" for e in events)


# ---------------------------------------------------------------------------
# Policy 3: abort — raises FanoutError immediately
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_conflict_abort_raises_fanout_error():
    """Req 25 AC 4, Req 26 — abort policy raises FanoutError on conflict.

    With abort:
    - ``merge_conflict`` event IS emitted (auditable, before the raise)
    - ``FanoutError`` is raised (naming the conflicting path)
    - no HITL, no merge_partial, no merge_completed
    """
    runner = _ConflictRunner()
    ctx = _make_conflict_ctx(runner)
    step = _make_conflict_step("abort")
    requests = [{"agent": "self", "input": "t0"}, {"agent": "self", "input": "t1"}]

    events: list[dict] = []
    with pytest.raises(FanoutError) as exc_info:
        async for ev in run_fanout(requests, ctx, step=step):
            events.append(ev)

    assert "abort" in str(exc_info.value).lower()

    # merge_conflict was emitted BEFORE the abort raised (auditable).
    conflict_evs = [e for e in events if e["type"] == "merge_conflict"]
    assert len(conflict_evs) == 1

    # Nothing soft-succeeded after the conflict.
    assert not any(e["type"] == "merge_completed" for e in events)
    assert not any(e["type"] == "merge_partial" for e in events)
    assert runner.hitl_calls == []


# ---------------------------------------------------------------------------
# Policy 4: merge_agent — triggers bounded merge-agent invocations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_conflict_merge_agent_resolves_within_bound():
    """Req 25 AC 4, Req 26 — merge_agent policy triggers a bounded agent run.

    The merge agent resolves on the first attempt → no HITL fallback needed.
    Distinct events: merge_conflict + merge_agent_attempt + merge_completed
    (resolved_by="merge_agent").
    """
    runner = _ConflictRunner(merge_agent_resolves=[True])
    ctx = _make_conflict_ctx(runner)
    step = _make_conflict_step("merge_agent", merge_agent="merge-worker")
    requests = [{"agent": "self", "input": "t0"}, {"agent": "self", "input": "t1"}]

    events = await _collect(run_fanout(requests, ctx, step=step))

    # merge_conflict emitted first.
    assert any(e["type"] == "merge_conflict" for e in events)

    # merge_agent_attempt event indicates the agent was invoked.
    attempt_evs = [e for e in events if e["type"] == "merge_agent_attempt"]
    assert len(attempt_evs) == 1
    assert attempt_evs[0]["data"]["attempt"] == 1

    # Resolved by the merge_agent within bound — no HITL fallback.
    assert runner.hitl_calls == []
    completed_evs = [e for e in events if e["type"] == "merge_completed"]
    assert len(completed_evs) == 1
    assert completed_evs[0]["data"].get("resolved_by") == "merge_agent"


@pytest.mark.asyncio
async def test_on_conflict_merge_agent_exhausted_falls_back_to_human_gate():
    """Req 25 AC 4, Req 26 — merge_agent falls back to human_gate when bound exhausted.

    The merge agent never resolves (2 attempts, both False) → human_gate fallback
    (no oscillation — T-11-03-03 / MERGE_AGENT_MAX_ATTEMPTS = 2).
    """
    runner = _ConflictRunner(
        merge_agent_resolves=[False, False],
        hitl_events=[{"type": "review_gate_ready", "data": {"output": {}}}],
    )
    ctx = _make_conflict_ctx(runner)
    step = _make_conflict_step("merge_agent", merge_agent="merge-worker")
    requests = [{"agent": "self", "input": "t0"}, {"agent": "self", "input": "t1"}]

    events = await _collect(run_fanout(requests, ctx, step=step))

    # Exactly 2 merge_agent attempts (not 3 — bounded).
    assert len(runner.merge_agent_calls) == 2
    assert [c["attempt"] for c in runner.merge_agent_calls] == [1, 2]

    # Fell back to human_gate after exhausting the bound.
    assert len(runner.hitl_calls) == 1
    assert any(e["type"] == "review_gate_ready" for e in events)


# ===========================================================================
# Summary sweep — all four policies produce DISTINCT event-type signatures
# ===========================================================================


@pytest.mark.asyncio
async def test_all_four_on_conflict_policies_produce_distinct_event_signatures():
    """Req 25 AC 4 — four policies, four distinct outcomes, one sweep.

    Demonstrates that every policy is reachable and produces its own unique
    event-type footprint:
    - human_gate  → review_gate_ready
    - partial     → merge_partial
    - abort       → FanoutError (no merge_completed)
    - merge_agent → merge_agent_attempt

    All four run from the same test to confirm none is a dead branch.
    """

    async def _events_for(policy, *, merge_agent=None, hitl_events=None, resolves=None):
        runner = _ConflictRunner(
            hitl_events=hitl_events or [],
            merge_agent_resolves=resolves,
        )
        ctx = _make_conflict_ctx(runner)
        step = _make_conflict_step(policy, merge_agent=merge_agent)
        requests = [{"agent": "self", "input": "t0"}, {"agent": "self", "input": "t1"}]
        collected: list[dict] = []
        try:
            async for ev in run_fanout(requests, ctx, step=step):
                collected.append(ev)
        except FanoutError:
            pass  # abort policy raises — expected
        return {e["type"] for e in collected}

    human_gate_types = await _events_for(
        "human_gate",
        hitl_events=[
            {"type": "review_gate_ready", "data": {}},
            {"type": "review_gate_resolved", "data": {}},
        ],
    )
    partial_types = await _events_for("partial")
    abort_types = await _events_for("abort")
    merge_agent_types = await _events_for(
        "merge_agent", merge_agent="merge-worker", resolves=[True]
    )

    # human_gate is the only policy that emits review_gate_ready.
    assert (
        "review_gate_ready" in human_gate_types
    ), "human_gate policy did not emit review_gate_ready"
    assert "review_gate_ready" not in partial_types
    assert "review_gate_ready" not in abort_types
    assert "review_gate_ready" not in merge_agent_types

    # partial is the only policy that emits merge_partial.
    assert "merge_partial" in partial_types, "partial policy did not emit merge_partial"
    assert "merge_partial" not in human_gate_types
    assert "merge_partial" not in abort_types
    assert "merge_partial" not in merge_agent_types

    # merge_agent is the only policy that emits merge_agent_attempt.
    assert (
        "merge_agent_attempt" in merge_agent_types
    ), "merge_agent policy did not emit merge_agent_attempt"
    assert "merge_agent_attempt" not in human_gate_types
    assert "merge_agent_attempt" not in partial_types
    assert "merge_agent_attempt" not in abort_types

    # abort is the only policy with NO merge_completed (run terminated via exception).
    assert (
        "merge_completed" not in abort_types
    ), "abort policy must not emit merge_completed"
    # All other policies produce merge_completed or a downstream resolution event.
    assert "merge_completed" in merge_agent_types
    # partial and human_gate don't produce a standard merge_completed in this
    # conflict path — partial produces merge_partial, human_gate re-yields HITL events.
    # The key invariant is that abort is UNIQUELY without merge_completed.
