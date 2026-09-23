"""Fan-out task identity + budget/compiler seams (Phase 11 / FANOUT-10, RESUME-06).

What is left here after the Batch 6 split is the half that needs NO database:

  * spawn-time task-identity threading — ``fanout._select_workers`` carries
    ``task_id``, defaulting to ``None`` for legacy/non-wave fan-out, and the wave
    scheduler builds requests carrying the content-addressed key;
  * the budget seam (``BudgetManager`` defaults + the stub ``reserve()``);
  * ``FanoutSpec.count``/``workers`` + ``CompiledWorkflow.allowed_workers`` +
    ``compiler._compile_fanout`` materialization.

The database halves moved to where their dependencies live:
  * ``0019`` / ``0026`` migration reversibility ->
    ``tests/integration/db/test_migration_0019_0026_subagent_runs.py``
  * ``ScopedStore.record_subagent_run`` / ``update_subagent_run`` scoped write +
    default-deny read ->
    ``tests/integration/repositories/test_subagent_runs_db.py``

Offline, no DB, no API key, no network.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# RESUME-06 — spawn-time task identity threading (fan-out + wave)
# ---------------------------------------------------------------------------


def test_select_workers_preserves_task_id():
    """``fanout._select_workers`` carries ``req['task_id']`` onto each selected worker
    dict so the plan-global id survives from the wave request to the record site.

    RED on HEAD: ``:115`` builds ``{"index","agent_id","input"}`` and DROPS task_id.
    """
    from agents.execution_engine.fanout import _select_workers

    class _Runner:
        allowed_workers: list = []
        agent_exists = None

    ctx = type("Ctx", (), {"runner": _Runner()})()
    step = type("Step", (), {"agent_id": "build"})()
    requests = [
        {"agent": "self", "input": "b0", "task_id": "t-0"},
        {"agent": "self", "input": "b1", "task_id": "t-1"},
    ]
    selected = _select_workers(requests, ctx, step)
    assert [w["task_id"] for w in selected] == ["t-0", "t-1"]
    # The existing keys are preserved (not clobbered).
    assert [w["index"] for w in selected] == [0, 1]
    assert all(w["agent_id"] == "build" for w in selected)
    assert [w["input"] for w in selected] == ["b0", "b1"]


def test_select_workers_task_id_defaults_none_when_absent():
    """A request WITHOUT a task_id (legacy/non-wave fan-out) selects with
    ``task_id=None`` — the column stays dormant on those rows (INV-3 golden-safe)."""
    from agents.execution_engine.fanout import _select_workers

    class _Runner:
        allowed_workers: list = []
        agent_exists = None

    ctx = type("Ctx", (), {"runner": _Runner()})()
    step = type("Step", (), {"agent_id": "build"})()
    selected = _select_workers([{"agent": "self", "input": "b"}], ctx, step)
    assert selected[0]["task_id"] is None


@pytest.mark.asyncio
async def test_wave_requests_carry_task_id():
    """RESUME-06/RESUME-14: ``wave_scheduler`` builds each ``run_fanout`` request carrying
    ``task_id`` = the content-addressed KEY wrapping the author id, so each spawned
    ``subagent_runs`` row is stamped with the skip-cursor key. The key still lines up
    one-to-one with the worker's body (identity ↔ input preserved); the DAG/dup-guard
    keep operating on the author ``t.id``.

    RED on HEAD: ``wave_scheduler.py:245`` built ``{"agent","input"}`` only.
    """
    from agents.capabilities import task_identity
    from agents.capabilities.strategies.wave_scheduler import WaveSchedulerStrategy
    from agents.workflows.plan import Task

    captured: list = []

    class _Runner:
        def latest_typed_content(self, _step):
            return ""

        async def read_wave_runs(self):
            return []

        async def read_subagent_runs(self):
            return []

        async def record_wave_run(self, *, step, wave_index, task_ids, status):
            return f"row-{wave_index}"

        async def update_wave_run(self, row_id, *, status):
            pass

        async def run_fanout(self, requests, ctx, *, step=None, event_queue=None):
            captured.append([dict(r) for r in requests])
            return
            yield  # noqa: unreachable — makes this an async generator

    ctx = type("Ctx", (), {"runner": _Runner(), "is_resuming": False})()
    step = type(
        "Step",
        (),
        {
            "agent_id": "wave-step",
            "task_source": type(
                "TS", (), {"source_step": "plan", "parser": "json_tasks"}
            )(),
        },
    )()
    # Two disjoint-target tasks with no deps → a single wave [ta, tb].
    tasks = [
        Task(id="ta", title="ta", body="body-ta", targets=["a.txt"]),
        Task(id="tb", title="tb", body="body-tb", targets=["b.txt"]),
    ]

    class _FakeParser:
        def parse(self, _text):
            return tasks

    strat = WaveSchedulerStrategy()
    strat._registry = type("R", (), {"resolve": lambda self, k, n: _FakeParser()})()

    _ = [ev async for ev in strat.run(step, ctx)]

    assert captured, "run_fanout was never called"
    all_reqs = [r for wave in captured for r in wave]
    assert all_reqs, "no requests were dispatched"
    assert all(
        "task_id" in r for r in all_reqs
    ), f"a wave request is missing task_id: {all_reqs}"
    # RESUME-14: the request task_id is the content-addressed key (this fake exposes no
    # upstream_context_hash handle → the strategy folds an empty upstream; all-distinct
    # content → ordinals 0). The key wraps the author id.
    key_ta = task_identity.compute_task_key(
        "", task_identity.normalize_task_content(tasks[0]), 0
    )
    key_tb = task_identity.compute_task_key(
        "", task_identity.normalize_task_content(tasks[1]), 0
    )
    assert {r["task_id"] for r in all_reqs} == {key_ta, key_tb}
    # The content-addressed key lines up one-to-one with the worker's input body.
    assert {(r["task_id"], r["input"]) for r in all_reqs} == {
        (key_ta, "body-ta"),
        (key_tb, "body-tb"),
    }


# ---------------------------------------------------------------------------
# Budget seam (BudgetManager defaults + stub reserve())
# ---------------------------------------------------------------------------


def test_budget_module_constants_present():
    from agents.execution_engine import budget as b

    assert b.DEFAULT_MAX_SUBAGENTS == 8
    assert b.DEFAULT_MAX_CONCURRENCY == 5
    assert b.DEFAULT_MAX_DEPTH == 2
    assert b.DEFAULT_WALL_CLOCK_SECONDS == 900
    assert b.MERGE_AGENT_MAX_ATTEMPTS == 2
    assert b.BUDGET_WARN_THRESHOLD == 0.8


def test_budget_manager_reserve_is_a_stub_seam():
    """reserve() records units and returns WITHOUT raising (enforcement is 11-04)."""
    from agents.execution_engine.budget import (
        BudgetManager,
        BudgetExceeded,
        BudgetSnapshot,
    )

    mgr = BudgetManager()
    # The stub seam never raises in this plan (FANOUT-09 enforcement lands 11-04).
    mgr.reserve(tokens=1000, subagents=3, concurrency=4, depth=1)
    snap = mgr.spent()
    assert isinstance(snap, BudgetSnapshot)
    assert snap.subagents == 3
    assert snap.tokens == 1000
    assert issubclass(BudgetExceeded, Exception)


def test_budget_manager_resolves_caps_from_limits():
    from agents.execution_engine.budget import BudgetManager, DEFAULT_MAX_SUBAGENTS
    from agents.workflows.plan import Limits

    mgr = BudgetManager(Limits(max_subagents=5, max_depth=1))
    assert mgr.max_subagents == 5
    assert mgr.max_depth == 1
    # Unspecified caps fall back to the module defaults.
    assert BudgetManager().max_subagents == DEFAULT_MAX_SUBAGENTS


# ---------------------------------------------------------------------------
# ExecutionContext.budget field
# ---------------------------------------------------------------------------


def test_execution_context_has_budget_field():
    from agents.execution_engine.context import ExecutionContext
    from agents.artifacts.graph import ArtifactGraph

    ctx = ExecutionContext(run_id="r1", owner_id="alice", artifacts=ArtifactGraph())
    assert ctx.budget is None  # per-run object, default None (INV-2)


# ---------------------------------------------------------------------------
# FanoutSpec / allowed_workers / compiler._compile_fanout
# ---------------------------------------------------------------------------


def test_fanout_spec_additive_fields():
    from agents.workflows.plan import FanoutSpec

    spec = FanoutSpec(
        mode="parallel", max_parallel=2, agent="self", count=3, workers=["w1"]
    )
    assert spec.mode == "parallel"
    assert spec.max_parallel == 2
    assert spec.agent == "self"
    assert spec.count == 3
    assert spec.workers == ["w1"]
    # Defaults additive (existing manifests keep mode/max_parallel only).
    bare = FanoutSpec()
    assert bare.agent is None and bare.count is None and bare.workers == []


def test_compiled_workflow_has_allowed_workers():
    from agents.workflows.plan import CompiledWorkflow

    cw = CompiledWorkflow(id="wf")
    assert cw.allowed_workers == []


def test_compiler_materializes_fanout_and_allowed_workers():
    from agents.capabilities.registry import CapabilityRegistry, discover
    from agents.workflows.compiler import WorkflowCompiler
    from agents.workflows.manifest import WorkflowManifest

    discover()
    registry = CapabilityRegistry()
    manifest = WorkflowManifest(
        id="fanout-wf",
        steps=[
            {
                "agent": "worker-a",
                "strategy": "single_shot",
                "fanout": {
                    "mode": "parallel",
                    "max_parallel": 3,
                    "agent": "self",
                    "count": 3,
                },
            }
        ],
        deliverable={"strategy": "streamed_text", "name": "out.txt"},
        planner="skip",
        clarify={"mode": "off", "defaults": []},
        allowed_workers=["worker-a", "worker-b"],
    )
    compiled = WorkflowCompiler().compile(manifest, registry)
    step = compiled.steps[0]
    assert step.fanout is not None
    assert step.fanout.mode == "parallel"
    assert step.fanout.count == 3
    assert step.fanout.agent == "self"
    assert compiled.allowed_workers == ["worker-a", "worker-b"]


def test_compiler_materializes_on_conflict_and_merge_agent():
    """CR-03: on_conflict + fanout.merge_agent survive compilation (not dropped)."""
    from agents.capabilities.registry import CapabilityRegistry, discover
    from agents.workflows.compiler import CompilerError, WorkflowCompiler
    from agents.workflows.manifest import WorkflowManifest

    discover()
    registry = CapabilityRegistry()

    def _manifest(on_conflict="abort", merge_agent="merge-worker"):
        return WorkflowManifest(
            id="conflict-wf",
            steps=[
                {
                    "agent": "worker-a",
                    "strategy": "single_shot",
                    "on_conflict": on_conflict,
                    "fanout": {"mode": "parallel", "merge_agent": merge_agent},
                }
            ],
            deliverable={"strategy": "streamed_text", "name": "out.txt"},
            planner="skip",
            clarify={"mode": "off", "defaults": []},
        )

    compiled = WorkflowCompiler().compile(_manifest(), registry)
    step = compiled.steps[0]
    # The authored policy is carried — NOT silently downgraded to human_gate.
    assert step.on_conflict == "abort"
    # The designated merge worker is materialized onto the FanoutSpec.
    assert step.fanout.merge_agent == "merge-worker"

    # An omitted on_conflict keeps the human_gate default (parity).
    no_policy = WorkflowCompiler().compile(
        WorkflowManifest(
            id="default-wf",
            steps=[{"agent": "worker-a", "strategy": "single_shot"}],
            deliverable={},
            planner="skip",
            clarify={"mode": "off", "defaults": []},
        ),
        registry,
    )
    assert no_policy.steps[0].on_conflict == "human_gate"

    # An unknown policy is a fail-loud CompilerError (never a silent fallback).
    import pytest as _pytest

    with _pytest.raises(CompilerError) as exc:
        WorkflowCompiler().compile(_manifest(on_conflict="overwrite"), registry)
    assert "on_conflict" in str(exc.value)
