"""McpCredential SQLAlchemy model — per-owner scoped MCP server credential (09-05 / MCP-02).

Table ``mcp_credentials`` — one row per (owner, mcp_server) that has stored a
credential (a PAT / token / API key) for an external MCP server. Owner-scoped +
encrypted, NEVER global, mirroring the ``UserGithubCredential`` PAT precedent
(``handoff.py:40``): the secret is Fernet-encrypted (``app.core.crypto``) in
``encrypted_secret`` and never round-tripped in plaintext through the API.

Carries ``owner_id`` + ``workspace_id`` (both NOT NULL, AUTHZ-01) so the
``ScopedStore`` default-deny filter scopes every read — a per-owner credential is
NEVER readable cross-owner (the cross-owner ``PermissionError`` denial test is the
T-09-05-ID gate). ``server`` is a free ``String`` holding the catalog server name
(``github`` / ``gitlab`` / ``jira`` / ``slack`` / ``filesystem`` / ``postgres``) —
NO ``sa.Enum``, consistent with the free-String columns elsewhere (additive +
reversible). ``scope`` records the granted read/write scope (e.g. ``gitlab_read``).

Schema source: specs/003-workflow-engine-decoupling/plan.md §15 + 09-RESEARCH R-D.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String, Text

from app.models.database import Base


class McpCredential(Base):
    """A per-owner credential for an external MCP server. Owner-scoped + encrypted (AUTHZ-01)."""

    __tablename__ = "mcp_credentials"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(String, nullable=False)        # AUTHZ-01
    workspace_id = Column(String, nullable=False)    # AUTHZ-01
    # Free String (NO sa.Enum): the catalog mcp_server name.
    server = Column(String, nullable=False)
    # Granted scope (e.g. 'gitlab_read' / 'jira_read' / 'slack_post'); free String.
    scope = Column(String, nullable=True)
    # Fernet-encrypted secret (PAT / token / API key) — never the plaintext.
    encrypted_secret = Column(Text, nullable=False)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
