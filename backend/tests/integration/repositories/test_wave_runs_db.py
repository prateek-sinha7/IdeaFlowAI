"""``ScopedStore`` wave-run persistence — scoped write, lifecycle, default-deny read.

Phase 12 / WAVE-02. Moved out of ``tests/unit/agents/test_wave_runs.py`` in Batch 6:
real rows through a real ORM mapping is integration work. ``db_session`` comes from
this folder's conftest; the ``0020`` migration proof lives in
``tests/integration/db/test_migration_0020_wave_runs.py``.
"""

from __future__ import annotations

import pytest

from agents.authz import ScopedStore
from app.models.wave_run import WaveRun


@pytest.mark.asyncio
async def test_record_wave_run_writes_scoped_row(db_session):
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    row_id = await store.record_wave_run(
        "run-1",
        step="wave-step",
        wave_index=0,
        task_ids=["t1", "t2"],
        status="running",
    )
    assert row_id, "record_wave_run must return a non-empty id"

    rows = db_session.query(WaveRun).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.id == row_id
    assert row.run_id == "run-1"
    assert row.owner_id == "alice"  # AUTHZ-01
    assert row.workspace_id == "ws-1"  # AUTHZ-01
    assert row.step == "wave-step"
    assert row.wave_index == 0
    assert row.task_ids == ["t1", "t2"]
    assert row.status == "running"


@pytest.mark.asyncio
async def test_wave_run_lifecycle_record_then_update_terminal(db_session):
    """A wave row goes running -> completed; the read shows the terminal status."""
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    row_id = await store.record_wave_run(
        "run-1", step="wave-step", wave_index=0, task_ids=["t1"], status="running"
    )
    await store.update_wave_run(row_id, status="completed")

    rows = await store.read_wave_runs("run-1")
    assert len(rows) == 1
    assert rows[0].status == "completed"


@pytest.mark.asyncio
async def test_cross_owner_wave_read_returns_nothing(db_session):
    """T-12-01-IDOR: a different owner reads zero wave_runs rows."""
    alice = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    await alice.record_wave_run(
        "run-1", step="wave-step", wave_index=0, task_ids=["t1"], status="running"
    )

    # Cross-owner scoped read returns nothing.
    mallory = ScopedStore(owner_id="mallory", workspace_id="ws-1", session=db_session)
    assert await mallory.read_wave_runs("run-1") == []

    # The true owner still resolves it (the filter is not a blanket deny).
    assert len(await alice.read_wave_runs("run-1")) == 1


@pytest.mark.asyncio
async def test_cross_owner_wave_update_is_noop(db_session):
    """A cross-owner update_wave_run leaves the row untouched (no-op)."""
    alice = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    row_id = await alice.record_wave_run(
        "run-1", step="wave-step", wave_index=0, task_ids=["t1"], status="running"
    )

    mallory = ScopedStore(owner_id="mallory", workspace_id="ws-1", session=db_session)
    await mallory.update_wave_run(row_id, status="completed")

    rows = await alice.read_wave_runs("run-1")
    assert rows[0].status == "running", "cross-owner update must be a no-op"


@pytest.mark.asyncio
async def test_read_wave_runs_ordered_by_wave_index(db_session):
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    await store.record_wave_run(
        "run-1", step="s", wave_index=1, task_ids=["b"], status="completed"
    )
    await store.record_wave_run(
        "run-1", step="s", wave_index=0, task_ids=["a"], status="completed"
    )
    rows = await store.read_wave_runs("run-1")
    assert [r.wave_index for r in rows] == [0, 1]
