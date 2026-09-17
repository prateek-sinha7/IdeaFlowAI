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
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.handoff import UserApiKey
from app.models.user import User


_API_KEY_PREFIX = "flowin_"
_API_KEY_BYTES = 32

# COGNITO-MIGRATION-PLAN §7 Phase 6 item 5. Before this, a minted key was valid
# forever unless explicitly revoked — the longest-lived credential in the system
# with no natural death. 90 days is long enough that an IDE/MCP integration is
# not a rotation treadmill, short enough that a leaked key from a stale laptop
# stops working within a quarter.
DEFAULT_API_KEY_TTL_DAYS = 90


def default_api_key_expiry(now: datetime | None = None) -> datetime:
    """Expiry stamp for a newly-minted key."""
    return (now or datetime.now(timezone.utc)) + timedelta(
        days=DEFAULT_API_KEY_TTL_DAYS
    )


def mint_api_key() -> tuple[str, str, str]:
    """Generate a new (plaintext, prefix, sha256) triple.

    The plaintext is the only string we ever return to the user. The
    prefix is stored verbatim for UI display ("flowin_a1b2 ...
    flowin_a1b2"). The hash is what we look up at auth time.

    Callers are responsible for stamping ``expires_at`` on the row (use
    :func:`default_api_key_expiry`); this function deals only in the token
    material so it stays trivially testable.
    """
    token_body = secrets.token_urlsafe(_API_KEY_BYTES)
    plaintext = f"{_API_KEY_PREFIX}{token_body}"
    prefix = plaintext[:8]
    digest = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
    return plaintext, prefix, digest


def hash_api_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def resolve_api_key(plaintext: str | None, db: Session, *, detail: str) -> User:
    """Resolve an API-key string to its ``User``, or raise a uniform 401.

    THE single implementation of API-key authentication. It exists as a plain
    function, separate from the FastAPI dependency below, because the key arrives
    on two different headers: ``X-Flowin-API-Key`` for the IDE/HTTP surface
    (:func:`get_user_via_api_key`) and ``Authorization: Bearer flowin_...`` for
    the MCP JSON-RPC surface (``api/mcp.py::_get_user_from_bearer``).

    Before Phase 2 of the Cognito-only auth migration those two surfaces each had
    their OWN copy of the lookup, and the copies had drifted: when key expiry
    landed (migration 0033), only this side gained the ``is_expired()`` check. The
    MCP transport went on accepting expired keys indefinitely — the longest-lived
    credential in the system, still working past the expiry its own row recorded.
    That is the whole argument for collapsing them here: a security check added to
    one copy of duplicated auth logic is a security check missing from the other,
    and nothing about the code makes that visible.

    Every rejection returns the SAME ``detail``, whatever the cause — unknown key,
    revoked key, expired key, or a key whose owner no longer exists. Splitting
    them would hand an attacker a probe for which key strings were ever real.

    ``detail`` is the caller's own wording (the two surfaces phrase it
    differently for their clients) and MUST NOT vary by failure cause within a
    surface.
    """

    def _reject() -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not plaintext or not plaintext.startswith(_API_KEY_PREFIX):
        raise _reject()

    row = (
        db.query(UserApiKey)
        .filter(UserApiKey.token_hash == hash_api_key(plaintext))
        .first()
    )
    # Expiry is checked alongside revocation (Phase 6 item 5) and collapses into
    # the same uniform 401.
    if row is None or row.revoked_at is not None or row.is_expired():
        raise _reject()

    user = db.query(User).filter(User.id == row.user_id).first()
    if user is None:
        raise _reject()

    # A disabled account's API keys stop working too (Decision 6). Without this,
    # `AdminDisableUser` + `users.status='disabled'` would end the user's browser
    # sessions while leaving every long-lived IDE/MCP key they minted fully
    # functional — a disabled user with a paste-once credential would keep the
    # access that disabling them was meant to remove.
    if getattr(user, "status", "active") != "active":
        raise _reject()

    row.last_used_at = datetime.now(timezone.utc)
    db.add(row)
    db.commit()
    return user


def get_user_via_api_key(
    x_flowin_api_key: str | None = Header(default=None, alias="X-Flowin-API-Key"),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency: resolve ``X-Flowin-API-Key`` → ``User``.

    Returns 401 for missing/unknown/revoked/expired keys with a uniform error so
    we don't leak enumeration signal. Updates ``last_used_at`` on every hit so the
    operator can audit dead keys. All of that lives in
    :func:`resolve_api_key`, which the MCP transport shares.
    """
    return resolve_api_key(x_flowin_api_key, db, detail="Invalid API key")


__all__ = [
    "mint_api_key",
    "hash_api_key",
    "resolve_api_key",
    "get_user_via_api_key",
    "default_api_key_expiry",
    "DEFAULT_API_KEY_TTL_DAYS",
]
