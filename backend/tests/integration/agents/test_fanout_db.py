"""Kernel fan-out spawn path against a REAL scoped store (Phase 11 / FANOUT-02..04).

Moved out of ``tests/unit/agents/test_fanout.py`` in Batch 6: this is the one test in
that module that builds a real SQLAlchemy engine and asserts on persisted
``subagent_runs`` rows, so it belongs with the integration suite. Everything else in
the original module drives ``run_fanout`` against a fake runner handle with no
database and stayed in the unit suite.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agents.execution_engine.budget import BudgetManager
from agents.execution_engine.state_machine import StateMachine


@pytest.mark.asyncio
async def test_kernel_handle_run_fanout_writes_rows_and_events():
    """run_fanout via KernelServices → N subagent_runs rows + N lifecycle events.

    Drives the SINGLE kernel spawn path through the real ``KernelServices.run_fanout``
    /``run_worker``/``record_subagent_run`` handle (bypassing __init__, the
    test_exec_runs.py precedent) against a real in-memory ScopedStore and a fake
    engine ``_run_agent``. Asserts the status-only structured summary (no artifact
    refs — deferred to 11-03).
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import app.models  # noqa: F401 — register models on Base.metadata
    from app.models.database import Base
    from app.models.subagent_run import SubagentRun
    from agents.authz import ScopedStore
    from agents.execution_engine.kernel_services import KernelServices

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()
    # SQLite (SQLAlchemy default) does not enforce the parent_run_id FK, so no parent
    # WorkflowRun row is needed (the test_exec_runs.py scoped-write precedent).

    scoped = ScopedStore(owner_id="alice", workspace_id="ws-1", session=session)

    class _Ectx:
        scoped_store = scoped
        depth = 0
        # Build-scratch fields run_agent touches.
        build_task_number = ""
        build_task_total = ""
        current_task_block = ""
        current_prototype_skeleton = ""
        current_step = None

    class _FakeEngine:
        # A per-instance StateMachine (not the module singleton) so the real
        # KernelServices.is_run_terminal() the fan-out cancel boundary consults
        # (ISS-091) is genuinely exercised here and stays test-independent. An
        # unknown run id reads None -> not terminal, so the fan-out proceeds.
        _state_machine = StateMachine()

        async def _run_agent(self, *a, **k):
            yield {"type": "agent_chunk", "data": {"chunk": "x"}}

    ks = KernelServices.__new__(KernelServices)
    ks._engine = _FakeEngine()
    ks._ectx = _Ectx()
    ks.run_id = "run-e2e"
    ks._ordered_agents = [SimpleNamespace(id="worker-a", name="W", role="r", icon="i")]
    ks._user_message = "go"
    ks._pipeline_type = "custom"
    ks._planning_context = {}
    ks._attached_skills = None
    ks._attached_hooks = None
    ks._model_id = None
    ks._results = []
    ks.cancel_event = None
    ks.sandbox = None
    ks.workspace = None

    step = SimpleNamespace(
        agent_id="worker-a",
        fanout=SimpleNamespace(
            mode="parallel", max_parallel=3, agent="self", count=None, workers=[]
        ),
    )
    ctx = SimpleNamespace(runner=ks, depth=0, budget=BudgetManager())
    requests = [{"agent": "self", "input": f"t{i}"} for i in range(3)]

    events = [ev async for ev in ks.run_fanout(requests, ctx, step=step)]

    # N subagent_runs rows persisted, all flipped terminal.
    rows = (
        session.query(SubagentRun).filter(SubagentRun.parent_run_id == "run-e2e").all()
    )
    assert len(rows) == 3
    assert all(r.status == "complete" for r in rows)
    assert all(r.worker_agent == "worker-a" for r in rows)
    # N subagent_spawned + N subagent_result events.
    assert len([e for e in events if e["type"] == "subagent_spawned"]) == 3
    results = [e for e in events if e["type"] == "subagent_result"]
    assert len(results) == 3
    assert all(r["data"]["status"] == "complete" for r in results)
    assert all(
        "artifact_ref" not in r["data"] for r in results
    )  # status-only (11-03 defers refs)

    session.close()
    Base.metadata.drop_all(bind=engine)
