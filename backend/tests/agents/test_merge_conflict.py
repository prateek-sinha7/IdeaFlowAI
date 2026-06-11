"""tests/agents/test_merge_conflict.py — merge dispatch + on_conflict policies (FANOUT-08).

Drives the merge dispatch in ``run_fanout`` OFFLINE against a fake ``ctx.runner`` that
exposes the merge handles (``resolve_merge_strategy`` / ``write_fragment_artifact`` /
``write_merge_conflict_artifact`` / ``run_human_gate`` / ``run_merge_agent``) + real
isolated workspaces, proving FANOUT-06/07/08:

  * a conflict writes a merge_conflict artifact + emits a merge_conflict event;
  * the 4 on_conflict policies behave per spec (human_gate / merge_agent / partial / abort);
  * merge_agent bounded ≤ 2 attempts then human_gate fallback (no oscillation);
  * human_gate pause/resume round-trips via the durable HITL;
  * partial keeps non-conflicting fragments; abort fails the run;
  * per-worker fragment artifacts persist BEFORE merge + the structured summary now
    carries each completed worker's fragment artifact ref (the 11-01 upgrade);
  * a merge_conflict ArtifactRef is owner-scoped (cross-owner read = ∅).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agents.capabilities.registry import CapabilityRegistry, discover
from agents.execution_engine.fanout import run_fanout, FanoutError


# ---------------------------------------------------------------------------
# A fake worker workspace exposing the _ChildSandbox-shaped _sandbox.root + write_file.
# ---------------------------------------------------------------------------


class _FakeChildSandbox:
    def __init__(self, root):
        self.root = root


class _FakeWorkerWorkspace:
    """A worker isolated workspace: writes files into its own root dir."""

    def __init__(self, root, *, branch=None):
        self._sandbox = _FakeChildSandbox(root)
        self._worktree_branch = branch

    def write_file(self, relpath, content):
        (self._sandbox.root / relpath).parent.mkdir(parents=True, exist_ok=True)
        (self._sandbox.root / relpath).write_text(content, encoding="utf-8")


class _FakeBaseWorkspace:
    has_git = False

    def __init__(self):
        self.written = {}

    def write_file(self, relpath, content):
        self.written[relpath] = content

    def spawn_point_commit(self):
        return "deadbeef"


# ---------------------------------------------------------------------------
# A fake ctx.runner exposing the merge dispatch surface + an in-memory artifact log.
# ---------------------------------------------------------------------------


class _MergeRunner:
    def __init__(self, base_workspace, *, worker_files, hitl_events=None,
                 merge_agent_resolves=None):
        self.run_id = "run-m"
        self.allowed_workers = []
        self.workspace = base_workspace
        self._worker_files = worker_files  # {worker_index: {relpath: content}}
        self._hitl_events = hitl_events or []
        self._merge_agent_resolves = merge_agent_resolves  # list[bool] per attempt
        self._row_seq = 0
        self.fragment_artifacts = []
        self.conflict_artifacts = []
        self.hitl_calls = []
        self.merge_agent_calls = []
        self._tmp_roots = {}

    def agent_exists(self, agent_id):
        return True

    async def record_subagent_run(self, *, parent_step, worker_agent, depth, isolation, status, tokens=None, cost=None):
        self._row_seq += 1
        return f"row-{self._row_seq}"

    async def update_subagent_run(self, row_id, *, status, tokens=None, cost=None):
        return None

    async def allocate_isolated_workspace(self, scope, step, *, worker_index):
        import tempfile
        from pathlib import Path

        root = Path(tempfile.mkdtemp())
        self._tmp_roots[worker_index] = root
        ws = _FakeWorkerWorkspace(root, branch=(f"fanout/{step}/{worker_index}" if scope == "worktree" else None))
        # Pre-write the worker's files into its isolated root (the "worker output").
        for relpath, content in self._worker_files.get(worker_index, {}).items():
            ws.write_file(relpath, content)
        return ws

    async def reclaim_isolated_workspace(self, base_workspace, worker_ws):
        return None

    async def run_worker(self, step, ctx, *, worker_index, thread_id, agent_id, input, workspace=None):
        yield {"type": "agent_chunk", "data": {"worker": worker_index}}

    def resolve_merge_strategy(self, name):
        discover()
        return CapabilityRegistry().resolve("merge", name)

    async def write_fragment_artifact(self, *, producer_step, worker_agent, worker_index, content, location, kind="file_bundle"):
        ref_id = f"frag-{worker_index}"
        self.fragment_artifacts.append(dict(id=ref_id, step=producer_step, worker=worker_index, location=location, content=content))
        return ref_id

    async def write_merge_conflict_artifact(self, *, producer_step, conflicts, payload=None):
        ref_id = f"conflict-{len(self.conflict_artifacts)}"
        self.conflict_artifacts.append(dict(id=ref_id, step=producer_step, conflicts=conflicts, payload=payload))
        return ref_id

    async def run_human_gate(self, step, *, output="", payload=None):
        self.hitl_calls.append({"step": getattr(step, "agent_id", None), "payload": payload})
        for ev in self._hitl_events:
            yield ev

    async def run_merge_agent(self, worker, payload, *, attempt):
        self.merge_agent_calls.append({"worker": worker, "attempt": attempt})
        if self._merge_agent_resolves is None:
            return False
        idx = attempt - 1
        return self._merge_agent_resolves[idx] if idx < len(self._merge_agent_resolves) else False


def _make_ctx(runner):
    from agents.execution_engine.budget import BudgetManager
    return SimpleNamespace(runner=runner, depth=0, budget=BudgetManager())


def _make_step(agent_id="worker-a", *, on_conflict="human_gate", merge_agent=None, mode="sequential"):
    fanout = SimpleNamespace(mode=mode, max_parallel=2, agent="self", count=None, workers=[], merge_agent=merge_agent)
    return SimpleNamespace(agent_id=agent_id, fanout=fanout, on_conflict=on_conflict)


async def _collect(gen):
    return [ev async for ev in gen]


# ---------------------------------------------------------------------------
# FANOUT-06 — fragment artifacts persist BEFORE merge + summary carries the ref
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fragment_artifacts_persist_and_summary_carries_ref():
    base = _FakeBaseWorkspace()
    # Two workers writing DISJOINT files (clean merge).
    runner = _MergeRunner(base, worker_files={0: {"a.txt": "A"}, 1: {"b.txt": "B"}})
    ctx = _make_ctx(runner)
    step = _make_step(on_conflict="human_gate")
    requests = [{"agent": "self", "input": "t0"}, {"agent": "self", "input": "t1"}]

    events = await _collect(run_fanout(requests, ctx, step=step))

    # Each completed worker persisted a fragment artifact BEFORE merge.
    assert len(runner.fragment_artifacts) == 2
    # The structured summary now carries each worker's fragment artifact ref (upgrade).
    results = [e for e in events if e["type"] == "subagent_result"]
    assert len(results) == 2
    assert all("artifact_ref" in r["data"] for r in results)
    assert {r["data"]["artifact_ref"] for r in results} == {"frag-0", "frag-1"}
    # Disjoint files merge cleanly: merge_started + merge_completed, no conflict.
    assert any(e["type"] == "merge_started" for e in events)
    assert any(e["type"] == "merge_completed" for e in events)
    assert not any(e["type"] == "merge_conflict" for e in events)
    # Both files applied to the base.
    assert base.written == {"a.txt": "A", "b.txt": "B"}


# ---------------------------------------------------------------------------
# FANOUT-08 — conflict writes a merge_conflict artifact + emits a merge_conflict event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_conflict_writes_artifact_and_emits_event():
    base = _FakeBaseWorkspace()
    # Two workers writing the SAME path with DIFFERING content → conflict.
    runner = _MergeRunner(
        base,
        worker_files={0: {"shared.txt": "FROM-0"}, 1: {"shared.txt": "FROM-1"}},
        hitl_events=[{"type": "review_gate_ready", "data": {"output": {}}}, {"type": "review_gate_resolved", "data": {}}],
    )
    ctx = _make_ctx(runner)
    step = _make_step(on_conflict="human_gate")
    requests = [{"agent": "self", "input": "t0"}, {"agent": "self", "input": "t1"}]

    events = await _collect(run_fanout(requests, ctx, step=step))

    # A merge_conflict artifact was written (owner-scoped) + a merge_conflict event emitted.
    assert len(runner.conflict_artifacts) == 1
    conflict_evs = [e for e in events if e["type"] == "merge_conflict"]
    assert len(conflict_evs) == 1
    assert conflict_evs[0]["data"]["artifact_ref"] == "conflict-0"
    # The conflict names the overlapping path; the base was NOT silently overwritten.
    assert conflict_evs[0]["data"]["conflicts"][0]["path"] == "shared.txt"
    assert "shared.txt" not in base.written


# ---------------------------------------------------------------------------
# on_conflict policy: human_gate (default) — pause/resume via the ONE durable HITL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_human_gate_policy_round_trips_via_durable_hitl():
    base = _FakeBaseWorkspace()
    runner = _MergeRunner(
        base,
        worker_files={0: {"x": "0"}, 1: {"x": "1"}},
        hitl_events=[
            {"type": "review_gate_ready", "data": {"output": {}}},
            {"type": "review_gate_resolved", "data": {}},
        ],
    )
    ctx = _make_ctx(runner)
    step = _make_step(on_conflict="human_gate")
    requests = [{"agent": "self", "input": "t0"}, {"agent": "self", "input": "t1"}]

    events = await _collect(run_fanout(requests, ctx, step=step))

    # The conflict routed through the ONE durable HITL (run_human_gate) with the payload.
    assert len(runner.hitl_calls) == 1
    assert runner.hitl_calls[0]["payload"]["conflicts"][0]["path"] == "x"
    # The review-gate events flow through (pause/resume round-trip).
    assert any(e["type"] == "review_gate_ready" for e in events)
    assert any(e["type"] == "review_gate_resolved" for e in events)


# ---------------------------------------------------------------------------
# on_conflict policy: merge_agent — bounded ≤ 2 then human_gate fallback (no oscillation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_merge_agent_bounded_then_human_gate_fallback():
    base = _FakeBaseWorkspace()
    # The merge agent never resolves → exhaust 2 attempts → fall back to human_gate.
    runner = _MergeRunner(
        base,
        worker_files={0: {"x": "0"}, 1: {"x": "1"}},
        merge_agent_resolves=[False, False, False],  # would loop forever if unbounded
        hitl_events=[{"type": "review_gate_ready", "data": {"output": {}}}],
    )
    ctx = _make_ctx(runner)
    step = _make_step(on_conflict="merge_agent", merge_agent="merge-worker")
    requests = [{"agent": "self", "input": "t0"}, {"agent": "self", "input": "t1"}]

    events = await _collect(run_fanout(requests, ctx, step=step))

    # Attempt count is bounded at 2 (no oscillation past the bound, T-11-03-03).
    assert len(runner.merge_agent_calls) == 2
    assert [c["attempt"] for c in runner.merge_agent_calls] == [1, 2]
    attempt_evs = [e for e in events if e["type"] == "merge_agent_attempt"]
    assert len(attempt_evs) == 2
    # Then it fell back to the ONE durable human_gate.
    assert len(runner.hitl_calls) == 1


@pytest.mark.asyncio
async def test_merge_agent_resolves_within_bound():
    base = _FakeBaseWorkspace()
    # The merge agent resolves on the 2nd attempt → no human_gate fallback.
    runner = _MergeRunner(
        base,
        worker_files={0: {"x": "0"}, 1: {"x": "1"}},
        merge_agent_resolves=[False, True],
    )
    ctx = _make_ctx(runner)
    step = _make_step(on_conflict="merge_agent", merge_agent="merge-worker")
    requests = [{"agent": "self", "input": "t0"}, {"agent": "self", "input": "t1"}]

    events = await _collect(run_fanout(requests, ctx, step=step))

    assert len(runner.merge_agent_calls) == 2
    assert runner.hitl_calls == []  # resolved within bound → no fallback
    assert any(e["type"] == "merge_completed" and e["data"].get("resolved_by") == "merge_agent" for e in events)


@pytest.mark.asyncio
async def test_merge_agent_no_designated_worker_falls_back_immediately():
    base = _FakeBaseWorkspace()
    runner = _MergeRunner(
        base,
        worker_files={0: {"x": "0"}, 1: {"x": "1"}},
        hitl_events=[{"type": "review_gate_ready", "data": {"output": {}}}],
    )
    ctx = _make_ctx(runner)
    step = _make_step(on_conflict="merge_agent", merge_agent=None)  # none designated
    requests = [{"agent": "self", "input": "t0"}, {"agent": "self", "input": "t1"}]

    events = await _collect(run_fanout(requests, ctx, step=step))

    assert runner.merge_agent_calls == []  # no worker → no attempts
    assert len(runner.hitl_calls) == 1  # immediate human_gate fallback


# ---------------------------------------------------------------------------
# on_conflict policy: partial — keep non-conflicting fragments, mark conflicted failed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_partial_keeps_non_conflicting_fragments():
    base = _FakeBaseWorkspace()
    # w0 writes a unique file (applies); w0 & w1 both write shared.txt differently (conflict).
    runner = _MergeRunner(
        base,
        worker_files={
            0: {"unique0.txt": "U0", "shared.txt": "S0"},
            1: {"shared.txt": "S1"},
        },
    )
    ctx = _make_ctx(runner)
    step = _make_step(on_conflict="partial")
    requests = [{"agent": "self", "input": "t0"}, {"agent": "self", "input": "t1"}]

    events = await _collect(run_fanout(requests, ctx, step=step))

    partial_evs = [e for e in events if e["type"] == "merge_partial"]
    assert len(partial_evs) == 1
    # The non-conflicting fragment is kept; the conflicting path is dropped.
    assert "unique0.txt" in partial_evs[0]["data"]["applied"]
    assert "shared.txt" in partial_evs[0]["data"]["dropped"]
    # The non-conflicting file IS applied to the base; the conflicting one is NOT.
    assert base.written.get("unique0.txt") == "U0"
    assert "shared.txt" not in base.written
    # No HITL on partial.
    assert runner.hitl_calls == []


# ---------------------------------------------------------------------------
# on_conflict policy: abort — fail the run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_abort_fails_the_run():
    base = _FakeBaseWorkspace()
    runner = _MergeRunner(
        base,
        worker_files={0: {"x": "0"}, 1: {"x": "1"}},
    )
    ctx = _make_ctx(runner)
    step = _make_step(on_conflict="abort")
    requests = [{"agent": "self", "input": "t0"}, {"agent": "self", "input": "t1"}]

    with pytest.raises(FanoutError) as exc:
        await _collect(run_fanout(requests, ctx, step=step))
    assert "abort" in str(exc.value)
    # The conflict artifact + event still fired before the abort raised (auditable).
    assert len(runner.conflict_artifacts) == 1


# ---------------------------------------------------------------------------
# WR-02 — a crashed merge strategy is reported as merge_failed (NOT a clean
# merge_completed): the failure is first-class on the event stream.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_crashed_merge_strategy_emits_merge_failed():
    base = _FakeBaseWorkspace()
    runner = _MergeRunner(base, worker_files={0: {"a.txt": "A"}})

    class _ExplodingStrategy:
        name = "copy_disjoint"

        def merge(self, base_, fragments_):
            raise RuntimeError("merge blew up")

    runner.resolve_merge_strategy = lambda name: _ExplodingStrategy()  # type: ignore[assignment]
    ctx = _make_ctx(runner)
    step = _make_step(on_conflict="human_gate")

    events = await _collect(run_fanout([{"agent": "self", "input": "t0"}], ctx, step=step))

    failed = [e for e in events if e["type"] == "merge_failed"]
    assert len(failed) == 1
    assert "merge blew up" in failed[0]["data"]["error"]
    assert failed[0]["data"]["applied"] == []
    # A crash is NEVER reported as a clean completion.
    assert not any(e["type"] == "merge_completed" for e in events)


# ---------------------------------------------------------------------------
# CR-03 — the LIVE run_merge_agent handle exists on KernelServices (no fake-only
# attribute): a designated worker runs bounded; an unknown worker degrades False.
# ---------------------------------------------------------------------------


def _real_ks_for_merge_agent():
    from agents.execution_engine.kernel_services import KernelServices

    calls: list[dict] = []

    class _Ectx:
        scoped_store = None
        depth = 0
        build_task_number = ""
        build_task_total = ""
        current_task_block = ""
        current_prototype_skeleton = ""
        current_step = None
        od_context = None

    class _FakeEngine:
        async def _run_agent(self_inner, spec, *a, **k):
            calls.append({"agent": spec.id})
            yield {"type": "agent_chunk", "data": {"chunk": "resolved"}}

    ks = KernelServices(
        engine=_FakeEngine(),
        ectx=_Ectx(),
        sandbox=None,
        ordered_agents=[SimpleNamespace(id="merge-worker", name="M", role="r", icon="i")],
        user_message="go",
        pipeline_run_id="run-ma",
        pipeline_type="custom",
        planning_context={},
        attached_skills=None,
        attached_hooks=None,
        model_id=None,
        results=[],
        cancel_event=None,
    )
    return ks, calls


@pytest.mark.asyncio
async def test_kernel_services_run_merge_agent_runs_designated_worker():
    """The live handle runs the designated merge worker over the payload (CR-03)."""
    ks, calls = _real_ks_for_merge_agent()
    payload = {"strategy": "copy_disjoint", "conflicts": [{"path": "x"}]}
    resolved = await ks.run_merge_agent("merge-worker", payload, attempt=1)
    assert resolved is True
    assert calls == [{"agent": "merge-worker"}]


@pytest.mark.asyncio
async def test_kernel_services_run_merge_agent_unknown_worker_degrades_false():
    """An unknown merge worker returns False (the caller falls back to human_gate)."""
    ks, calls = _real_ks_for_merge_agent()
    resolved = await ks.run_merge_agent("no-such-worker", {"conflicts": []}, attempt=1)
    assert resolved is False
    assert calls == []


# ---------------------------------------------------------------------------
# Owner-scoping: a cross-owner read of the merge_conflict ArtifactRef = ∅
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_merge_conflict_artifact_is_owner_scoped():
    """A merge_conflict ArtifactRef written by alice is invisible to bob (T-11-03-02)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import app.models  # noqa: F401 — register models on Base.metadata
    from app.models.database import Base
    from agents.authz import ScopedStore
    from agents.artifacts.graph import ArtifactRef

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()

    alice = ScopedStore(owner_id="alice", workspace_id="ws-a", session=session)
    ref = ArtifactRef(
        id="mc-1", kind="merge_conflict", owner_id="alice", workspace_id="ws-a",
        run_id="run-mc", producer_step="fanout-step", producer_agent="fanout-step",
        task_id=None, content='{"conflicts": [{"path": "shared.txt"}]}',
        content_hash="h", location="merge_conflict/fanout-step.json", version=1,
        visibility="private",
    )
    await alice.write_ref(ref)

    # Alice reads her own conflict artifact.
    alice_refs = await alice.list_refs("run-mc", kind="merge_conflict")
    assert len(alice_refs) == 1

    # Bob (a different owner) reads nothing — owner-scoped (cross-owner = ∅).
    bob = ScopedStore(owner_id="bob", workspace_id="ws-b", session=session)
    bob_refs = await bob.list_refs("run-mc", kind="merge_conflict")
    assert bob_refs == []

    session.close()
    Base.metadata.drop_all(bind=engine)
