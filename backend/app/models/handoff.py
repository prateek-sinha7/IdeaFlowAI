"""SQLAlchemy models for the /flowin-handoff feature.

Three tables:

* ``user_github_credentials`` — one row per user that has connected a
  GitHub PAT. The PAT itself is stored Fernet-encrypted (see
  ``app.core.crypto``). We never round-trip the plaintext through the
  API; the only consumer is the in-process handoff pipeline.

* ``user_api_keys`` — long-lived bearer tokens issued to a user so the
  slash-command / MCP client can POST to ``/api/handoff/receive`` and
  ``/mcp/handoff/*`` without a 24h-lifetime JWT. ``token_prefix`` is the
  first 8 chars shown back in the UI; ``token_hash`` is the SHA-256 of
  the full token (never the plaintext) so a DB read alone cannot mint a
  working credential.

* ``handoff_sessions`` — one row per handoff invocation. The transcript
  (the IDE's session JSONL) and the task description live here, along
  with the pipeline run state and the eventual PR URL. Tokens are 32-byte
  url-safe random strings.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _default_expiry(hours: int = 1) -> datetime:
    return _now() + timedelta(hours=hours)


class UserGithubCredential(Base):
    """Encrypted GitHub PAT for a single user.

    We keep this in its own row (rather than denormalising onto ``users``)
    so the encrypted_pat blob and the github_username/scopes metadata
    stay together, and so dropping the table during a rotation is a
    single SQL statement.
    """

    __tablename__ = "user_github_credentials"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    encrypted_pat = Column(Text, nullable=False)
    github_username = Column(String, nullable=True)
    scopes = Column(String, nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now, nullable=False)

    user = relationship("User")


class UserApiKey(Base):
    """Long-lived bearer token for IDE / MCP clients."""

    __tablename__ = "user_api_keys"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False, default="Default")
    token_prefix = Column(String(8), nullable=False)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_now, nullable=False)
    revoked_at = Column(DateTime, nullable=True)

    user = relationship("User")


# Status values for HandoffSession.status
HANDOFF_STATUS_PENDING = "pending"          # Created, awaiting user claim in browser
HANDOFF_STATUS_RUNNING = "running"          # Pipeline executing
HANDOFF_STATUS_COMPLETED = "completed"      # PR created (or report delivered)
HANDOFF_STATUS_FAILED = "failed"            # Pipeline raised
HANDOFF_STATUS_EXPIRED = "expired"          # Lapsed before claim

# Mode values
HANDOFF_MODE_AUTO = "auto"
HANDOFF_MODE_CODING = "coding"
HANDOFF_MODE_TEST = "test"


class HandoffSession(Base):
    """One IDE handoff: transcript + task + repo, evolving into a PR.

    Token semantics:

    * ``token`` is the URL component that the slash command receives and
      that opens the browser page (``/handoff/<token>``). It is 32 bytes
      base64url-encoded, indistinguishable from random.
    * ``token`` alone is NOT sufficient to view the session: the GET
      endpoint additionally requires that the authenticated Flowin user's
      id matches ``issuer_user_id``. A leaked URL therefore lets nobody
      else even view the task description, let alone start the pipeline.
    """

    __tablename__ = "handoff_sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    token = Column(String(64), unique=True, index=True, nullable=False)
    issuer_user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    task_description = Column(Text, nullable=False)
    transcript = Column(Text, nullable=False, default="")
    repo_url = Column(String, nullable=False)
    repo_default_branch = Column(String, nullable=True)
    source_branch = Column(String, nullable=True)
    mode = Column(String, nullable=False, default=HANDOFF_MODE_AUTO)
    source_client = Column(String, nullable=True)  # "claude-code" | "mcp" | "cursor" | ...

    status = Column(String, nullable=False, default=HANDOFF_STATUS_PENDING)
    resolved_mode = Column(String, nullable=True)  # populated post-classification
    pr_url = Column(String, nullable=True)
    pr_number = Column(Integer, nullable=True)
    branch_name = Column(String, nullable=True)

    # Structured pipeline output: JSON-encoded list of agent steps and reports.
    pipeline_output = Column(Text, nullable=True)
    error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=_now, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, default=_default_expiry, nullable=False)

    issuer = relationship("User")
