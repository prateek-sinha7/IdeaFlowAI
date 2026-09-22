"""``ScopedStore`` subagent-run persistence — scoped write, terminal flip, IDOR deny.

Phase 11 / FANOUT-10 + RESUME-06. Moved out of ``tests/unit/agents/test_subagent_runs.py``
in Batch 6: these four tests write real rows through a real ORM mapping. The
``db_session`` fixture (hermetic in-memory SQLite) comes from this folder's conftest.

Sibling halves of the original module:
  * ``0019`` / ``0026`` migration reversibility ->
    ``tests/integration/db/test_migration_0019_0026_subagent_runs.py``
  * the pure fan-out / budget / compiler seams stayed in
    ``tests/unit/agents/test_subagent_runs.py``
"""

from __future__ import annotations

import pytest

from agents.authz import ScopedStore
from app.models.subagent_run import SubagentRun


@pytest.mark.asyncio
async def test_record_subagent_run_writes_scoped_row(db_session):
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    row_id = await store.record_subagent_run(
        "parent-run-1",
        parent_step="build",
        worker_agent="prototype-build",
        depth=1,
        isolation="shared_read",
        status="running",
        tokens=42,
        cost={"cost_class": 3},
    )
    assert row_id, "record_subagent_run must return a non-empty id"

    rows = db_session.query(SubagentRun).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.id == row_id
    assert row.parent_run_id == "parent-run-1"
    assert row.owner_id == "alice"  # AUTHZ-01
    assert row.workspace_id == "ws-1"  # AUTHZ-01
    assert row.parent_step == "build"
    assert row.worker_agent == "prototype-build"
    assert row.depth == 1
    assert row.isolation == "shared_read"
    assert row.status == "running"
    assert row.tokens == 42
    assert row.cost == {"cost_class": 3}


@pytest.mark.asyncio
async def test_update_subagent_run_flips_terminal(db_session):
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    row_id = await store.record_subagent_run(
        "parent-run-1",
        parent_step="build",
        worker_agent="prototype-build",
        depth=0,
        isolation="shared_read",
        status="running",
    )
    await store.update_subagent_run(row_id, status="complete", tokens=100)

    rows = db_session.query(SubagentRun).all()
    assert len(rows) == 1
    assert rows[0].status == "complete"
    assert rows[0].tokens == 100


@pytest.mark.asyncio
async def test_cross_owner_subagent_read_returns_nothing(db_session):
    """FANOUT-10 / T-11-01-03: a different owner reads zero subagent_runs rows."""
    alice = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    await alice.record_subagent_run(
        "parent-run-1",
        parent_step="build",
        worker_agent="w0",
        depth=0,
        isolation="shared_read",
        status="running",
    )

    # Cross-owner scoped read returns nothing.
    mallory = ScopedStore(owner_id="mallory", workspace_id="ws-1", session=db_session)
    assert await mallory.read_subagent_runs("parent-run-1") == []

    # The true owner still resolves it (the filter is not a blanket deny).
    assert len(await alice.read_subagent_runs("parent-run-1")) == 1


@pytest.mark.asyncio
async def test_record_subagent_run_threads_worker_index_and_task_id(db_session):
    """RESUME-06: ``worker_index`` + ``task_id`` kwargs land on the persisted row.

    RED on HEAD: ``ScopedStore.record_subagent_run`` has no such kwargs (TypeError).
    """
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    row_id = await store.record_subagent_run(
        "parent-run-1",
        parent_step="wave-step",
        worker_agent="prototype-build",
        depth=0,
        isolation="shared_read",
        status="running",
        worker_index=2,
        task_id="t-42",
    )
    row = db_session.query(SubagentRun).filter_by(id=row_id).one()
    assert row.worker_index == 2
    assert row.task_id == "t-42"

    # Defaults stay None when not passed → dormant on scripted / golden runs (INV-3).
    bare_id = await store.record_subagent_run(
        "parent-run-1",
        parent_step="s",
        worker_agent="w",
        depth=0,
        isolation="shared_read",
        status="running",
    )
    bare = db_session.query(SubagentRun).filter_by(id=bare_id).one()
    assert bare.worker_index is None
    assert bare.task_id is None
