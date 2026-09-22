"""``ScopedStore.record_exec_run`` — scoped write + default-deny read (Phase 10 / EXEC-01).

Moved out of ``tests/unit/agents/test_exec_runs.py`` in Batch 6: these tests write real
rows through a real ORM mapping, which is integration work. The ``db_session`` fixture
comes from this folder's conftest (hermetic in-memory SQLite).

Sibling halves of the original module:
  * migration reversibility -> ``tests/integration/db/test_migration_0018_exec_runs.py``
  * the ``KernelServices`` best-effort degrade -> ``tests/unit/agents/test_exec_runs.py``
"""

from __future__ import annotations

import pytest

from agents.authz import ScopedStore
from app.models.exec_runs import ExecRun


@pytest.mark.asyncio
async def test_record_exec_run_allowed_writes_scoped_row(db_session):
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    row_id = await store.record_exec_run(
        "run-1",
        "build",
        ["python3", "-c", "print(1)"],
        "allowed",
        exit_code=0,
        duration_ms=12,
        policy_snapshot={"exec_allow": ["python3"]},
        output_digest="ok",
    )
    assert row_id, "record_exec_run must return a non-empty id"

    rows = db_session.query(ExecRun).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.id == row_id
    assert row.run_id == "run-1"
    assert row.owner_id == "alice"  # AUTHZ-01
    assert row.workspace_id == "ws-1"  # AUTHZ-01
    assert row.step == "build"
    assert row.outcome == "allowed"
    assert row.exit_code == 0
    assert row.argv_json == ["python3", "-c", "print(1)"]


@pytest.mark.asyncio
async def test_record_exec_run_denied_writes_row(db_session):
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    row_id = await store.record_exec_run(
        "run-1", "build", ["bash", "-c", "echo hi"], "denied", exit_code=None
    )
    assert row_id
    rows = db_session.query(ExecRun).filter(ExecRun.outcome == "denied").all()
    assert len(rows) == 1
    assert rows[0].exit_code is None


@pytest.mark.asyncio
async def test_record_exec_run_killed_writes_row(db_session):
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    row_id = await store.record_exec_run(
        "run-1", "build", ["python3", "-c", "import time;time.sleep(99)"], "killed"
    )
    assert row_id
    rows = db_session.query(ExecRun).filter(ExecRun.outcome == "killed").all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_cross_owner_exec_run_read_returns_nothing(db_session):
    """T-10-01-08: a different owner reads zero exec_runs rows (default-deny)."""
    alice = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    await alice.record_exec_run("run-1", "build", ["python3"], "allowed", exit_code=0)

    # Cross-owner scoped read returns nothing.
    mallory = ScopedStore(owner_id="mallory", workspace_id="ws-1", session=db_session)
    assert await mallory.read_exec_runs("run-1") == []

    # The true owner still resolves it (the filter is not a blanket deny).
    assert len(await alice.read_exec_runs("run-1")) == 1
