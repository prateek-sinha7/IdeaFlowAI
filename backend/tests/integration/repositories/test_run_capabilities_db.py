"""``run_capabilities`` recording — active integration scopes, MCP servers, runtime.

CAPRUN-01. Moved out of ``tests/unit/agents/test_integration_scopes.py`` in Batch 6:
both tests seed a ``workflow_runs`` parent row and assert on the persisted
``run_capabilities`` row, so they need a real engine and real ORM mapping. The scope
semantics themselves (``resolve_integration_scopes`` + the effective-perms
intersection) are pure and stayed in the unit suite.

``db_session`` comes from this folder's conftest (hermetic in-memory SQLite).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agents.authz import ScopedStore
from agents.capabilities.integration_providers.providers import SCOPE_TO_SERVER
from app.models.run_capabilities import RunCapabilities
from app.models.workflow import WorkflowRun


def _seed_run(db, *, run_id="run-i", owner_id="alice", workspace_id="ws-1"):
    db.add(
        WorkflowRun(
            id=run_id,
            user_id=owner_id,
            title="t",
            type="prototype",
            status="running",
            input="idea",
            owner_id=owner_id,
            workspace_id=workspace_id,
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()


@pytest.mark.asyncio
async def test_run_capabilities_records_scopes_servers_runtime(db_session) -> None:
    """A run_capabilities row records the active integration scopes + MCP servers + runtime.

    Drives the SAME single write path the engine uses at entry
    (``record_capabilities(..., integrations=..., mcp_servers=...)``).
    """
    _seed_run(db_session, run_id="run-i", owner_id="alice", workspace_id="ws-1")
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)

    scopes = ["gitlab_read"]
    servers = sorted({SCOPE_TO_SERVER[s] for s in scopes})

    await store.record_capabilities(
        "run-i",
        runtime="langchain_deepagents",
        integrations=(scopes or None),
        mcp_servers=(servers or None),
    )

    row = (
        db_session.query(RunCapabilities)
        .filter(RunCapabilities.run_id == "run-i")
        .one()
    )
    assert row.runtime == "langchain_deepagents"
    assert row.integrations == ["gitlab_read"]
    assert row.mcp_servers == ["gitlab"]
    assert row.owner_id == "alice"
    assert row.workspace_id == "ws-1"


@pytest.mark.asyncio
async def test_no_integration_run_records_null(db_session) -> None:
    """INV-3 row parity: a run with no integration scope persists both columns as NULL."""
    _seed_run(db_session, run_id="run-none", owner_id="alice", workspace_id="ws-1")
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)

    # The engine passes ``([] or None)`` → None for a no-integration run.
    await store.record_capabilities(
        "run-none",
        runtime="langchain_deepagents",
        integrations=([] or None),
        mcp_servers=([] or None),
    )

    row = (
        db_session.query(RunCapabilities)
        .filter(RunCapabilities.run_id == "run-none")
        .one()
    )
    assert row.integrations is None
    assert row.mcp_servers is None
