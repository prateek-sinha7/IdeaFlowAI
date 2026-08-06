"""User SQLAlchemy model."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.models.database import Base


class User(Base):
    """User account model."""

    __tablename__ = "users"

    # `cognito_sub`'s uniqueness is declared here rather than inline on the
    # column, so the model matches migration 0031 EXACTLY: 0031 creates a named
    # unique CONSTRAINT plus a separate non-unique INDEX (plan §6.1), whereas an
    # inline `unique=True, index=True` renders as a single unique index under a
    # different name. Left mismatched, `alembic check` reported perpetual drift
    # (drop the constraint, re-create the index as unique) on every autogenerate.
    __table_args__ = (
        UniqueConstraint("cognito_sub", name="uq_users_cognito_sub"),
        Index("ix_users_cognito_sub", "cognito_sub"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, index=True, nullable=False)
    # Nullable (Cognito migration, 0031): a Cognito-native user has no local
    # bcrypt hash. Non-null ONLY for the single break-glass local-admin
    # account (auth_provider == "local") and for any pre-migration row.
    password_hash = Column(String, nullable=True)
    # Set to "now" whenever the password changes. Any JWT whose ``iat`` is
    # before this value is treated as revoked — the cheap, enumeration-free
    # "revoke all this user's outstanding tokens" pattern. Nullable so users
    # who have never rotated their password have no blanket-revocation cutoff.
    password_changed_at = Column(DateTime, nullable=True)
    tier = Column(String, nullable=False, default="basic", server_default="basic")
    is_admin = Column(Boolean, nullable=False, default=False, server_default="0")
    preferred_model = Column(String, nullable=True, default=None)

    # --- Cognito identity mapping (0031) ---
    # Cognito `sub` claim. NEVER the identity key -- `id` (above) stays the
    # local UUID every foreign key references (WorkflowRun.user_id etc.); this
    # is a mapping column only, unique + indexed so `resolve_principal` can
    # look a Cognito-authenticated principal up by it.
    # Uniqueness + index are declared in __table_args__ above (see the note
    # there) so this model and migration 0031 render identical DDL.
    cognito_sub = Column(String, nullable=True)
    # "cognito" | "local" (break-glass). Drives the login-endpoint branch and
    # which credential-verification path applies.
    auth_provider = Column(String, nullable=False, default="local", server_default="local")
    # Generalizes password_changed_at: any JWT/Cognito-token whose `iat` is
    # before max(password_changed_at, tokens_valid_from) is rejected. A role
    # or tier change stamps this to force re-authentication with fresh groups.
    tokens_valid_from = Column(DateTime, nullable=True)
    # Observability only (when the tier/is_admin projection below was last
    # refreshed from cognito:groups) -- never read by an authorization check.
    roles_synced_at = Column(DateTime, nullable=True)
    # Fernet-encrypted Cognito refresh token (0032), stored so
    # POST /api/auth/refresh can call REFRESH_TOKEN_AUTH server-side -- the
    # browser only ever holds one bearer value (the access token), per the
    # getToken()/setToken() seam (Decision 3). NULL for local/break-glass
    # users, who have no Cognito refresh token.
    encrypted_cognito_refresh_token = Column(Text, nullable=True)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    chat_sessions = relationship("ChatSession", back_populates="user")
    workflow_runs = relationship("WorkflowRun", back_populates="user")
