"""MCP-02 Wave-0 acceptance: the mcp_server catalog + scoped per-owner credentials.

  * the catalog registers github/gitlab/jira/slack (user_allowed=True) +
    filesystem/postgres (user_allowed=False); the trust flags are read off the
    registry (the single trust source the compiler consults);
  * a per-owner MCP credential is stored SCOPED + encrypted (never plaintext) and
    a same-owner read decrypts it; a cross-owner read raises ``PermissionError``
    (T-09-05-ID — the default-deny denial gate), and the scoped reader returns
    ``None`` cross-owner.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from agents.authz import ScopedStore
from agents.capabilities.registry import CapabilityRegistry, discover

# Importing app.models registers every model on Base.metadata so create_all builds
# mcp_credentials (+ the rest) for the in-memory test DB (Pitfall 5).
import app.models  # noqa: F401
from app.models.database import Base
from app.models.mcp_credential import McpCredential


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


# ---------------------------------------------------------------------------
# MCP-02 — catalog trust flags
# ---------------------------------------------------------------------------


def test_catalog_user_allowed_flags() -> None:
    discover()
    r = CapabilityRegistry()
    # Read-scoped servers are on the user palette.
    for name in ("github", "gitlab", "jira", "slack"):
        assert r.is_registered("mcp_server", name)
        assert r.is_user_allowed("mcp_server", name) is True, f"{name} should be user_allowed"
    # Powerful/write servers are OFF the user palette.
    for name in ("filesystem", "postgres"):
        assert r.is_registered("mcp_server", name)
        assert r.is_user_allowed("mcp_server", name) is False, f"{name} must NOT be user_allowed"


def test_catalog_exposed_tools_and_powerful_flags() -> None:
    from agents.capabilities.mcp_servers.catalog import CATALOG

    # The read-scoped servers are not powerful; the FS/PG servers are.
    assert CATALOG["gitlab"].powerful is False
    assert CATALOG["filesystem"].powerful is True
    assert CATALOG["postgres"].powerful is True
    # The exposed-tool allow-list gates what a manifest may name.
    assert CATALOG["gitlab"].is_tool_exposed("list_issues") is True
    assert CATALOG["gitlab"].is_tool_exposed("delete_everything") is False


# ---------------------------------------------------------------------------
# MCP-02 — scoped per-owner credential (encrypted, cross-owner denied)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_credential_stored_scoped_and_encrypted(db_session) -> None:
    store = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    cred_id = await store.write_mcp_credential(
        server="gitlab", secret="glpat-SECRET-TOKEN", scope="gitlab_read"
    )

    # Exactly one row, owner/workspace-stamped (AUTHZ-01), secret NEVER plaintext.
    rows = db_session.query(McpCredential).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.owner_id == "alice"
    assert row.workspace_id == "ws-1"
    assert row.server == "gitlab"
    assert row.scope == "gitlab_read"
    assert row.encrypted_secret != "glpat-SECRET-TOKEN", "secret must be encrypted at rest"
    assert "glpat-SECRET-TOKEN" not in row.encrypted_secret

    # The owner can read it back decrypted.
    assert await store.read_mcp_credential(cred_id) == "glpat-SECRET-TOKEN"


@pytest.mark.asyncio
async def test_cross_owner_mcp_credential_read_is_denied(db_session) -> None:
    """T-09-05-ID: a different owner cannot read the credential (default-deny + assert)."""
    alice = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    cred_id = await alice.write_mcp_credential(server="jira", secret="jira-token", scope="jira_read")

    bob = ScopedStore(owner_id="bob", workspace_id="ws-1", session=db_session)
    # Default-deny scoped read returns None cross-owner.
    assert await bob.read_mcp_credential(cred_id) is None
    # The explicit denial gate raises PermissionError cross-owner.
    with pytest.raises(PermissionError):
        await bob.assert_mcp_cred_owned(cred_id)

    # The true owner is unaffected (no false denial).
    assert await alice.assert_mcp_cred_owned(cred_id) is None
    assert await alice.read_mcp_credential(cred_id) == "jira-token"
