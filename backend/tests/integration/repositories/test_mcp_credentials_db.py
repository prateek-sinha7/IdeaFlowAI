"""Scoped, encrypted per-owner MCP credentials (MCP-02 / T-09-05-ID).

Moved out of ``tests/unit/agents/test_mcp_catalog.py`` in Batch 6: these two tests
write a real row and assert on the persisted ciphertext, which needs a real engine.
The catalog trust-flag tests (pure registry reads) stayed in the unit suite.

``db_session`` comes from this folder's conftest (hermetic in-memory SQLite).
"""

from __future__ import annotations

import pytest

from agents.authz import ScopedStore
from app.models.mcp_credential import McpCredential


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
    assert (
        row.encrypted_secret != "glpat-SECRET-TOKEN"
    ), "secret must be encrypted at rest"
    assert "glpat-SECRET-TOKEN" not in row.encrypted_secret

    # The owner can read it back decrypted.
    assert await store.read_mcp_credential(cred_id) == "glpat-SECRET-TOKEN"


@pytest.mark.asyncio
async def test_cross_owner_mcp_credential_read_is_denied(db_session) -> None:
    """T-09-05-ID: a different owner cannot read the credential (default-deny + assert)."""
    alice = ScopedStore(owner_id="alice", workspace_id="ws-1", session=db_session)
    cred_id = await alice.write_mcp_credential(
        server="jira", secret="jira-token", scope="jira_read"
    )

    bob = ScopedStore(owner_id="bob", workspace_id="ws-1", session=db_session)
    # Default-deny scoped read returns None cross-owner.
    assert await bob.read_mcp_credential(cred_id) is None
    # The explicit denial gate raises PermissionError cross-owner.
    with pytest.raises(PermissionError):
        await bob.assert_mcp_cred_owned(cred_id)

    # The true owner is unaffected (no false denial).
    assert await alice.assert_mcp_cred_owned(cred_id) is None
    assert await alice.read_mcp_credential(cred_id) == "jira-token"
