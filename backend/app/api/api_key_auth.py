"""Long-lived API key authentication for the IDE / MCP clients.

The IDE-side slash command and the MCP server cannot rely on the 24-hour
JWT a browser session uses — both need a credential the user can paste
once and forget. ``UserApiKey`` rows give us that: ``token_hash`` is the
SHA-256 of the full token string; ``token_prefix`` is the leading 8
characters used for display only.

The plaintext token is shown to the user EXACTLY ONCE on creation; we
never store nor return it again. Lost tokens require minting a new one.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.handoff import UserApiKey
from app.models.user import User


_API_KEY_PREFIX = "flowin_"
_API_KEY_BYTES = 32


def mint_api_key() -> tuple[str, str, str]:
    """Generate a new (plaintext, prefix, sha256) triple.

    The plaintext is the only string we ever return to the user. The
    prefix is stored verbatim for UI display ("flowin_a1b2 ...
    flowin_a1b2"). The hash is what we look up at auth time.
    """
    token_body = secrets.token_urlsafe(_API_KEY_BYTES)
    plaintext = f"{_API_KEY_PREFIX}{token_body}"
    prefix = plaintext[:8]
    digest = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
    return plaintext, prefix, digest


def hash_api_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def get_user_via_api_key(
    x_flowin_api_key: str | None = Header(default=None, alias="X-Flowin-API-Key"),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency: resolve ``X-Flowin-API-Key`` → ``User``.

    Returns 401 for missing/unknown/revoked keys with a uniform error so
    we don't leak enumeration signal. Updates ``last_used_at`` on every
    hit so the operator can audit dead keys.
    """
    if not x_flowin_api_key or not x_flowin_api_key.startswith(_API_KEY_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    digest = hash_api_key(x_flowin_api_key)
    row = db.query(UserApiKey).filter(UserApiKey.token_hash == digest).first()
    if row is None or row.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.query(User).filter(User.id == row.user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    row.last_used_at = datetime.now(timezone.utc)
    db.add(row)
    db.commit()
    return user


__all__ = ["mint_api_key", "hash_api_key", "get_user_via_api_key"]
