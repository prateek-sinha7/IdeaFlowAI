"""WorkflowMemory SQLAlchemy model — per-user key/value store (Phase 3)."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.models.database import Base


class WorkflowMemory(Base):
    """Per-user key/value store. Holds Constitution and reusable domain knowledge.

    Constraints:
    - key: 1–255 chars
    - value: up to 1,048,576 chars
    - up to 1,000 entries per user
    - UNIQUE(user_id, key)
    - Entries MUST NOT be exposed to other users
    """

    __tablename__ = "workflow_memory"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    key = Column(String(255), nullable=False)
    value = Column(Text, nullable=False)                     # up to 1,048,576 chars
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User")

    __table_args__ = (
        UniqueConstraint("user_id", "key", name="uq_workflow_memory_user_key"),
    )
