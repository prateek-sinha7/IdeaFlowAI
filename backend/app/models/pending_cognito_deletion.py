"""Durable retry queue for a user delete whose Cognito-side cleanup failed.

Part of the Cognito-only auth migration (``.kiro/specs/login/prompt.md``
Phase 1, migration 0038). ``api/admin.py::delete_user`` disables + globally
signs out a Cognito user, deletes the LOCAL row, then calls
``AdminDeleteUser``. If that last call fails (network/throttle), the user is
already gone locally and disabled at the provider -- correctly unable to log
in either way -- but the pool user still exists. This table records that
so ``app/scripts/retry_cognito_deletions.py`` (Phase 3) can finish the job
later without a human combing through logs for the failed email.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Index, Integer, String, Text

from app.models.database import Base


class PendingCognitoDeletion(Base):
    """One row per user-delete whose ``AdminDeleteUser`` call failed."""

    __tablename__ = "pending_cognito_deletions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    # Snapshot of the deleted user's local id -- NOT a foreign key, since the
    # whole point of this row is that the local User row is already gone by
    # the time it's written.
    user_id_snapshot = Column(String, nullable=False)
    cognito_sub = Column(String, nullable=False)
    # Hashed, not plaintext -- mirrors auth_events.py's PII-in-logs posture.
    email_hash = Column(String(16), nullable=False)
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    last_error = Column(Text, nullable=True)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_pending_cognito_deletions_cognito_sub", "cognito_sub"),
    )
