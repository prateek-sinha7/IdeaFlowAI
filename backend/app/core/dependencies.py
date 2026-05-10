"""FastAPI dependencies for authentication and authorization."""

import random
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.security import decode_access_token, is_token_revoked
from app.models.database import get_db
from app.models.revoked_token import cleanup_expired_revocations
from app.models.user import User

# Bearer token security scheme
bearer_scheme = HTTPBearer()


def _coerce_to_aware_utc(value: datetime | None) -> datetime | None:
    """Treat naive datetimes as UTC.

    SQLite (and SQLAlchemy without a timezone-aware column type) hands us
    naive datetimes even though we wrote tz-aware values in. Compare apples to
    apples by promoting any naive datetime to UTC.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _invalid_token() -> HTTPException:
    """Standard 401 used for any failure mode where we don't want to leak why."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _decode_and_load_user(
    credentials: HTTPAuthorizationCredentials,
    db: Session,
) -> tuple[User, dict]:
    """Common JWT-decode + user-lookup logic, with no revocation checks.

    Returns ``(user, payload)``. Raises 401 only on the unrecoverable cases
    where the token is plainly invalid (bad signature, expired, missing
    subject, no matching user). Revocation gating is layered on top by the
    full-fat dependencies.
    """
    token = credentials.credentials

    try:
        payload = decode_access_token(token)
    except JWTError:
        raise _invalid_token()

    user_id: str | None = payload.get("sub")
    if user_id is None:
        raise _invalid_token()

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise _invalid_token()

    return user, payload


def _check_password_change_revocation(user: User, payload: dict) -> None:
    """Reject tokens whose ``iat`` predates the user's most recent password change.

    Cheap "revoke all this user's outstanding tokens" pattern that doesn't
    require enumerating every JWT — see ``app.api.auth.change_password``.

    Comparison is done at whole-second resolution. JWT ``iat`` is encoded as
    an integer (seconds since epoch), so a token issued at 12:00:00.900 ends
    up with ``iat == int(12:00:00)``. If we kept ``password_changed_at`` at
    microsecond precision, a token freshly issued in the same wall-clock
    second as the rotation would compare as "before" the rotation and be
    incorrectly revoked. Truncating ``password_changed_at`` to whole seconds
    keeps both sides on the same grid: a token whose ``iat`` second is
    strictly before the rotation second is revoked; same-second tokens are
    accepted (they were either issued by the post-rotation login or are
    indistinguishable from one, which is the right call).
    """
    pwd_changed_at = _coerce_to_aware_utc(user.password_changed_at)
    if pwd_changed_at is None:
        return
    iat_raw = payload.get("iat")
    if iat_raw is None:
        return
    # python-jose hands ``iat`` back as an int (seconds since epoch).
    if isinstance(iat_raw, (int, float)):
        iat_seconds = int(iat_raw)
    elif isinstance(iat_raw, datetime):
        iat_dt = _coerce_to_aware_utc(iat_raw)
        iat_seconds = int(iat_dt.timestamp()) if iat_dt is not None else None
    else:
        iat_seconds = None
    if iat_seconds is None:
        return
    pwd_changed_seconds = int(pwd_changed_at.timestamp())
    if iat_seconds < pwd_changed_seconds:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _maybe_run_lazy_gc(db: Session) -> None:
    """Lazy GC: ~1 in 1000 requests cleans up expired revoked-token rows."""
    if random.random() < 0.001:
        try:
            cleanup_expired_revocations(db)
        except Exception:
            # GC must never break a real request — swallow and move on.
            db.rollback()


def get_current_user_with_payload(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> tuple[User, dict]:
    """Decode the JWT, run the full revocation gate, return ``(user, payload)``.

    Same semantics as :func:`get_current_user` but exposes the decoded JWT
    payload so callers (e.g. anything wanting ``jti`` / ``exp``) don't have
    to re-decode the token.
    """
    user, payload = _decode_and_load_user(credentials, db)

    # --- Per-token revocation (logout) ---
    jti: str | None = payload.get("jti")
    if jti and is_token_revoked(jti, db):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # --- Blanket revocation on password change ---
    _check_password_change_revocation(user, payload)

    _maybe_run_lazy_gc(db)

    return user, payload


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Extract and validate JWT from Authorization header.

    Returns the authenticated user or raises 401 for:
    - Missing token
    - Expired token
    - Malformed/tampered token
    - Token with non-existent user
    - Token whose ``jti`` has been individually revoked (logout)
    - Token issued before the user's most recent password change

    Args:
        credentials: The Bearer token from the Authorization header.
        db: The database session.

    Returns:
        The authenticated User object.

    Raises:
        HTTPException: 401 Unauthorized if the token is invalid or revoked.
    """
    user, _ = get_current_user_with_payload(credentials=credentials, db=db)
    return user


def get_user_for_logout(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> tuple[User, dict]:
    """Resolve the JWT for the /logout endpoint.

    The standard dependencies reject already-revoked tokens with 401, but
    /logout must be idempotent: if the caller hits it twice with the same
    JWT, both calls should report success ("the token is revoked", which it
    is). So this dependency:

    - validates the signature and lookup as usual,
    - applies the password-change blanket revocation (we don't want to give
      back signal that the token was usable for logging out *again* after
      the password rotation already invalidated it),
    - **does not** reject on per-jti revocation. The /logout handler treats
      "already revoked" as the success case.
    """
    user, payload = _decode_and_load_user(credentials, db)
    _check_password_change_revocation(user, payload)
    _maybe_run_lazy_gc(db)
    return user, payload
