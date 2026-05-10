"""User SQLAlchemy model."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String
from sqlalchemy.orm import relationship

from app.models.database import Base


class User(Base):
    """User account model."""

    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    # Set to "now" whenever the password changes. Any JWT whose ``iat`` is
    # before this value is treated as revoked — the cheap, enumeration-free
    # "revoke all this user's outstanding tokens" pattern. Nullable so users
    # who have never rotated their password have no blanket-revocation cutoff.
    password_changed_at = Column(DateTime, nullable=True)
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
