"""Revoked JWT tokens table — supports per-token logout / revocation.

Holds one row per revoked JWT, keyed by the token's ``jti`` claim. ``user_id``
is denormalised onto the row to make "all tokens for this user" queries cheap
and ``expires_at`` mirrors the JWT's ``exp`` so the lazy-GC pass can drop rows
once they can no longer be presented anyway.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.orm import Session

from app.models.database import Base


class RevokedToken(Base):
    """A revoked JWT, identified by its ``jti`` claim."""

    __tablename__ = "revoked_tokens"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    # The JWT ID being revoked. Unique + indexed for fast lookup on every
    # request that hits an authenticated endpoint.
    jti = Column(String, unique=True, index=True, nullable=False)
    # Indexed so "revoke all this user's tokens" / audit queries are cheap,
    # even though we currently use the ``password_changed_at`` blanket-revoke
    # path for password changes (see app.api.auth.change_password).
    user_id = Column(
        String, ForeignKey("users.id"), index=True, nullable=False
    )
    revoked_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    # Mirrors the JWT's ``exp``. Once we're past this instant the JWT can no
    # longer be presented, so the row can be deleted by ``cleanup_expired_revocations``.
    expires_at = Column(DateTime, nullable=False)


def cleanup_expired_revocations(db: Session) -> int:
    """Delete revoked-token rows whose JWT has already expired.

    Called opportunistically (lazy GC) from ``get_current_user`` so the table
    doesn't grow unbounded. Returns the number of rows deleted.

    In a high-traffic deployment this should move behind a real cron / sidecar
    (the deployment doc already mentions on-host systemd timers) — but at the
    current scale running it on ~1-in-1000 authenticated requests keeps the
    table bounded with zero infrastructure overhead.
    """
    now = datetime.now(timezone.utc)
    deleted = (
        db.query(RevokedToken)
        .filter(RevokedToken.expires_at < now)
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted
