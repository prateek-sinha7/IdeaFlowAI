"""Budget snapshot persistence + the workspace spend aggregate (Phase 11 / 11-04).

Moved out of ``tests/unit/agents/test_budget.py`` in Batch 6: these four tests are the
only ones in that module that build a real SQLAlchemy engine — they assert the
``workflow_runs.budget_snapshot_json`` column is stamped on completion and on abort,
that a cross-owner stamp is a no-op, and that the workspace aggregate sums only THIS
owner's ``subagent_runs`` (T-11-04-04 default-deny).

The ~35 enforcement tests they lived beside (cap arithmetic, reserve refusals,
wall-clock arming, warning thresholds, engine snapshot wiring) drive ``BudgetManager``
and fakes with no database and stayed in the unit suite.
"""

from __future__ import annotations

import pytest


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
        id=run_id,
        user_id=owner_id,
        owner_id=owner_id,
        workspace_id=workspace_id,
        type="custom",
        input="go",
        status="running",
    )
    session.add(row)
    session.commit()
    return row


@pytest.mark.asyncio
async def test_budget_snapshot_persisted_to_workflow_runs_on_completion():
    store, session = _in_memory_store()
    _seed_run(session, "run-done")
    snap = {
        "tokens": 100,
        "cost": None,
        "subagents": 3,
        "depth": 1,
        "wall_clock_seconds": 4.0,
    }
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
    snap = {
        "tokens": 50,
        "cost": None,
        "subagents": 8,
        "depth": 2,
        "wall_clock_seconds": 1.0,
    }
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
        "run-1",
        parent_step="fan",
        worker_agent="w",
        depth=0,
        isolation="shared_read",
        status="complete",
    )
    await store.record_subagent_run(
        "run-2",
        parent_step="fan",
        worker_agent="w",
        depth=0,
        isolation="shared_read",
        status="complete",
    )
    # Bob's row in the same workspace name — must NOT be counted for alice.
    from agents.authz import ScopedStore

    bob = ScopedStore(owner_id="bob", workspace_id="ws-1", session=session)
    await bob.record_subagent_run(
        "run-3",
        parent_step="fan",
        worker_agent="w",
        depth=0,
        isolation="shared_read",
        status="complete",
    )

    agg = await store.workspace_budget_spent("ws-1")
    assert agg["subagents"] == 2  # alice's two only — bob's excluded
