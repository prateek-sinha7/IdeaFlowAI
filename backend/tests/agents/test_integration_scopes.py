"""INTEG-02 Wave-0 acceptance: the ``integrations`` tool-permission scopes.

Proves the scope semantics + the per-run ``run_capabilities`` recording:

  * ``integrations`` defaults to NONE — a step with no grant activates ZERO integration
    providers (binds zero integration tools);
  * granting ``gitlab_read`` activates ONLY the gitlab provider, binding only its read
    tools (the catalog read-tool allow-list), NOT github/jira/slack;
  * the effective-perms intersection (08-03) is what gates a scope grant — an
    ``integrations`` scope absent from BOTH the workflow ceiling and the step grant is
    not effective (least-privilege);
  * a ``run_capabilities`` row records the active integration scopes + the MCP servers
    they activate + the runtime (the SAME single write path the engine drives at entry).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from agents.authz import ScopedStore
from agents.capabilities.integration_providers.providers import (
    SCOPE_TO_SERVER,
    resolve_integration_scopes,
)
from agents.workflows.plan import ToolPermissions, intersect_permissions
from app.models.database import Base
from app.models.run_capabilities import RunCapabilities
from app.models.workflow import WorkflowRun


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


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


# ---------------------------------------------------------------------------
# INTEG-02 — default none; gitlab_read binds only gitlab read tools
# ---------------------------------------------------------------------------


def test_default_none_binds_zero_integration_tools() -> None:
    """A step with no ``integrations`` grant activates ZERO providers (binds nothing)."""
    configs, exposed = resolve_integration_scopes([])
    assert configs == {}
    assert exposed == {}


def test_gitlab_read_binds_only_gitlab_read_tools() -> None:
    """Granting ``gitlab_read`` activates ONLY gitlab — its read tools, nothing else."""
    configs, exposed = resolve_integration_scopes(["gitlab_read"])

    # Only the gitlab server is activated (not github/jira/slack).
    assert set(configs) == {"gitlab"}
    assert set(exposed) == {"gitlab"}

    # The bound tools are exactly the gitlab catalog read-tool allow-list.
    from agents.capabilities.mcp_servers.catalog import CATALOG

    assert exposed["gitlab"] == set(CATALOG["gitlab"].exposed_tools)
    # The gitlab allow-list is read-only (no write/delete tool leaks in).
    assert exposed["gitlab"] == {"list_issues", "get_issue", "list_merge_requests", "get_project"}


def test_intersection_gates_an_ungranted_integration_scope() -> None:
    """The 08-03 effective-perms intersection is what gates a scope grant (least-privilege).

    An ``integrations`` scope present on the step grant but ABSENT from the workflow
    ceiling is NOT effective — the intersection drops it, so no provider activates.
    """
    owner = ToolPermissions(integrations=["github_read", "gitlab_read"])
    workflow = ToolPermissions(integrations=["gitlab_read"])  # ceiling omits github_read
    step = ToolPermissions(integrations=["github_read", "gitlab_read"])

    effective = intersect_permissions(owner, workflow, step)
    # Only gitlab_read survives all three levels.
    assert effective.integrations == ["gitlab_read"]

    configs, _ = resolve_integration_scopes(effective.integrations)
    assert set(configs) == {"gitlab"}  # github_read was gated out → no github provider


def test_no_grant_means_empty_effective_integrations() -> None:
    """Default-none: an empty step grant ⇒ empty effective ⇒ zero providers."""
    effective = intersect_permissions(
        ToolPermissions(), ToolPermissions(), ToolPermissions()
    )
    assert effective.integrations == []
    configs, exposed = resolve_integration_scopes(effective.integrations)
    assert configs == {} and exposed == {}


# ---------------------------------------------------------------------------
# CAPRUN-01 — run_capabilities records the active scopes + servers + runtime
# ---------------------------------------------------------------------------


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
