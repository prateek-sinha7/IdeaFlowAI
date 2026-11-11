"""Connector SQLAlchemy models (migration 0053).

Three tables back the connectors feature (design section 2.1):

- ``connector_connections``: one row per (user, connector) holding the encrypted
  OAuth tokens (the Token Vault).
- ``oauth_states``: single-use, 10-minute authorization states bound to the
  initiating user.
- ``connector_audit_log``: one row per connector event; never a secret or a payload.

Q5 exemption: these tables carry ``user_id`` (FK ``users.id ON DELETE CASCADE``)
and no ``owner_id`` / ``workspace_id``. A connection belongs to a person, not to a
run workspace, and every read filters on the verified ``user_id`` (the
``user_github_credentials`` / ``user_api_keys`` precedent, migration 0039).

``status`` and ``action`` are free strings, never ``sa.Enum``. The migration that
creates these tables is ``0053_connectors``; its indexes and constraints must
mirror the declarations here exactly.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.types import JSON

from app.models.database import Base

# ``connector_connections.status``
CONNECTION_STATUS_ACTIVE = "active"
CONNECTION_STATUS_EXPIRED = "expired"

# ``connector_audit_log.action``
AUDIT_AUTHORIZE_STARTED = "authorize_started"
AUDIT_CONNECTED = "connected"
AUDIT_CONNECT_FAILED = "connect_failed"
AUDIT_REFRESHED = "refreshed"
AUDIT_REFRESH_FAILED = "refresh_failed"
AUDIT_DISCONNECTED = "disconnected"
AUDIT_REVOKE_FAILED = "revoke_failed"
AUDIT_TOOLS_BOUND = "tools_bound"
AUDIT_TOOL_CALL = "tool_call"

# ``connector_audit_log.outcome``
AUDIT_OUTCOME_OK = "ok"
AUDIT_OUTCOME_ERROR = "error"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


class ConnectorConnection(Base):
    """One user's OAuth connection to one connector, tokens encrypted at rest."""

    __tablename__ = "connector_connections"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "connector_key", name="uq_connector_connections_user_connector"
        ),
        Index("ix_connector_connections_user", "user_id"),
    )

    id = Column(String, primary_key=True, default=_new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    connector_key = Column(String(32), nullable=False)
    status = Column(String(16), nullable=False, default=CONNECTION_STATUS_ACTIVE)
    provider_account_id = Column(String(128), nullable=False)
    provider_account_login = Column(String(255), nullable=True)
    provider_account_name = Column(String(255), nullable=True)
    granted_scopes = Column(JSON, nullable=False)
    provider_metadata = Column(JSON, nullable=True)
    access_token_ciphertext = Column(Text, nullable=False)
    refresh_token_ciphertext = Column(Text, nullable=True)
    # NULL means the provider issued no expiry.
    access_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    refresh_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    token_version = Column(Integer, nullable=False, default=1, server_default="1")
    last_refreshed_at = Column(DateTime(timezone=True), nullable=True)
    last_error_code = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class OAuthState(Base):
    """A pending authorization: only the state's hash is stored, never the state."""

    __tablename__ = "oauth_states"
    __table_args__ = (
        UniqueConstraint("state_hash", name="uq_oauth_states_state_hash"),
        Index("ix_oauth_states_user_expires", "user_id", "expires_at"),
        Index("ix_oauth_states_expires", "expires_at"),
    )

    id = Column(String, primary_key=True, default=_new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    connector_key = Column(String(32), nullable=False)
    state_hash = Column(String(64), nullable=False)
    code_verifier_ciphertext = Column(Text, nullable=False)
    redirect_uri = Column(String(512), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)


class ConnectorAuditLog(Base):
    """One connector event. No tokens, codes, arguments or results are ever stored."""

    __tablename__ = "connector_audit_log"
    __table_args__ = (
        Index("ix_connector_audit_user_created", "user_id", "created_at"),
        Index("ix_connector_audit_run", "run_id"),
    )

    id = Column(String, primary_key=True, default=_new_id)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    connector_key = Column(String(32), nullable=False)
    action = Column(String(32), nullable=False)
    outcome = Column(String(16), nullable=False)
    error_code = Column(String(64), nullable=True)
    tool_name = Column(String(128), nullable=True)
    # No FK: the audit trail outlives a deleted run.
    run_id = Column(String, nullable=True)
    agent_ref = Column(String(128), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
