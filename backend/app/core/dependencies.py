"""FastAPI dependencies for authentication and authorization.

Rewired for the Cognito Authentication & Authorization Migration
(``.planning/COGNITO-MIGRATION-PLAN.md`` §7 Phase 2): ``_decode_and_load_user``
now delegates to the single shared resolver in ``core/identity.py``
(``verify_credential`` + ``resolve_principal``), which dual-accepts Cognito
RS256 and legacy HS256 tokens. Every external signature in this module is
UNCHANGED -- the 76 ``Depends(get_current_user)`` call sites across 21 files
need no edits.
"""

import random
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.identity import (
    CredentialInvalid,
    Principal,
    is_revoked_by_token_validity,
    resolve_principal,
    verify_credential,
)
from app.core.security import is_token_revoked
from app.models.database import get_db
from app.models.revoked_token import cleanup_expired_revocations
from app.models.user import User

class _BearerScheme(HTTPBearer):
    """``HTTPBearer`` that answers a MISSING/non-bearer Authorization header with 401.

    FastAPI's stock ``HTTPBearer`` raises **403** when the header is absent or is
    not a ``Bearer`` credential, which conflates "you sent no credentials" with
    "your credentials were rejected". RFC 7235 separates them: absent or
    unparseable credentials are **401** plus a ``WWW-Authenticate`` challenge;
    403 is authenticated-but-not-permitted.

    Every other auth failure in this module already answers 401 via
    ``_credentials_exception`` (bad signature, EXPIRED token, missing subject, no
    matching user) — the stock 403 was the one inconsistent case, so a client could
    not tell "log in again" from "you are not allowed here". Overriding the scheme
    once keeps all five ``Depends(bearer_scheme)`` call sites below byte-identical;
    ``auto_error=False`` would have pushed a None-check into each of them.
    """

    async def __call__(self, request: Request) -> HTTPAuthorizationCredentials | None:
        try:
            return await super().__call__(request)
        except HTTPException as exc:
            if exc.status_code == status.HTTP_403_FORBIDDEN:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=exc.detail,
                    headers={"WWW-Authenticate": "Bearer"},
                ) from exc
            raise


# Bearer token security scheme
bearer_scheme = _BearerScheme()


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


def _principal_as_payload(principal: Principal) -> dict:
    """Project a Principal into the legacy ``dict`` payload shape.

    A handful of call sites (``/logout``, tests) read ``payload["jti"]`` /
    ``payload["exp"]`` / ``payload["iat"]`` directly rather than taking the
    ``User`` object. This keeps that contract alive across both providers.
    """
    return {
        "sub": principal.sub,
        "jti": principal.jti,
        "iat": principal.iat,
        "exp": principal.exp or 0,
        "groups": principal.groups,
    }


def _decode_and_load_user(
    credentials: HTTPAuthorizationCredentials,
    db: Session,
    *,
    allow_expired: bool = False,
) -> tuple[User, Principal]:
    """Common credential-verify + user-lookup logic, with no revocation checks.

    Returns ``(user, principal)``. Raises 401 only on the unrecoverable cases
    where the token is plainly invalid (bad signature, expired -- unless
    ``allow_expired`` --, missing subject, no matching user). Revocation
    gating is layered on top by the full-fat dependencies.
    """
    token = credentials.credentials

    try:
        principal = verify_credential(token, allow_expired=allow_expired)
    except CredentialInvalid:
        raise _invalid_token()

    user = resolve_principal(principal, db)
    if user is None:
        raise _invalid_token()

    return user, principal


def _check_password_change_revocation(user: User, principal: Principal) -> None:
    """Reject tokens whose ``iat`` predates ``max(password_changed_at,
    tokens_valid_from)`` -- the generalized blanket-revocation check
    (migration plan §5.3). See ``core.identity.is_revoked_by_token_validity``
    for the whole-second-resolution tolerance rationale, unchanged from the
    original password-only check this generalizes.
    """
    if is_revoked_by_token_validity(user, principal):
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
    """Verify the credential, run the full revocation gate, return
    ``(user, payload)``.

    Same semantics as :func:`get_current_user` but exposes a dict-shaped
    payload (projected from the resolved ``Principal``) so callers wanting
    ``jti``/``exp`` don't have to re-decode the token. ``user.tier`` /
    ``user.is_admin`` on the returned ``User`` are the raw DB columns --
    callers that need the EFFECTIVE (group-authoritative-on-Cognito) role/tier
    must call ``core.identity.effective_tier``/``effective_is_admin`` with the
    principal, not read the column directly. ``GET /api/auth/me`` does this
    (see api/auth.py).
    """
    user, principal = _decode_and_load_user(credentials, db)

    # --- Per-token revocation (logout) --- applies to BOTH providers (R3 in
    # the migration plan's risk register): a revoked Cognito access token is
    # still offline-valid until its own `exp` (AWS documents this caveat
    # explicitly), so the local `revoked_tokens` jti denylist is the defense
    # that closes the gap for Cognito tokens too, not just legacy ones. Every
    # jti (Cognito or legacy) that reaches /logout is inserted the same way.
    if principal.jti and is_token_revoked(principal.jti, db):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # --- Generalized blanket revocation (password change OR role/tier change) ---
    _check_password_change_revocation(user, principal)

    _maybe_run_lazy_gc(db)

    return user, _principal_as_payload(principal)


def get_current_principal(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> tuple[User, Principal]:
    """Verify the credential, run the full revocation gate, return
    ``(user, principal)`` with the REAL ``Principal`` object (not the dict
    projection ``get_current_user_with_payload`` hands back).

    Callers that need to make an authorization decision keyed on the
    EFFECTIVE role/tier (``core.identity.effective_tier`` /
    ``effective_is_admin``) should depend on this instead of
    ``get_current_user`` — those functions take a ``Principal``, and
    reconstructing one from the dict payload (as ``api/auth.py``'s
    ``_principal_from_payload`` and ``api/admin.py``'s inline construction
    both do) is a needless second projection. New call sites should prefer
    this dependency; the dict-payload path stays only for the two existing
    callers that were already built around it.
    """
    user, principal = _decode_and_load_user(credentials, db)

    if principal.jti and is_token_revoked(principal.jti, db):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    _check_password_change_revocation(user, principal)
    _maybe_run_lazy_gc(db)

    return user, principal


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Extract and validate the bearer credential from the Authorization header.

    Returns the authenticated user or raises 401 for:
    - Missing token
    - Expired token
    - Malformed/tampered token
    - Token with non-existent user
    - Token whose ``jti`` has been individually revoked (logout, legacy path)
    - Token issued before the user's most recent password OR role/tier change

    Accepts either a Cognito RS256 access token or (while
    ``AUTH_ALLOW_LEGACY_JWT``/break-glass applies) a legacy HS256 token — see
    ``core.identity.verify_credential``.

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


def get_current_user_for_refresh(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> tuple[User, dict]:
    """Resolve the credential for ``POST /api/auth/refresh`` ONLY.

    P1 fix (COGNITO-AUTH-QA-BUGS.md "Token Refresh: Impossible After Access
    Token Expiry"): identical to :func:`get_current_user_with_payload`
    EXCEPT it accepts a token whose ``exp`` has already passed, bounded by
    ``settings.AUTH_REFRESH_GRACE_SECONDS`` (see
    ``core.identity.verify_credential(allow_expired=True)``). Every other
    check still applies in full — signature, issuer, client_id, per-jti
    revocation (a LOGGED-OUT user cannot use this to mint a new token), and
    the generalized blanket revocation (a token issued before a password/role
    change is still rejected even if it hasn't reached its own ``exp`` yet).

    Do NOT reuse this dependency for any other endpoint — accepting expired
    bearers is exactly the wrong contract for a normal protected route.
    """
    user, principal = _decode_and_load_user(credentials, db, allow_expired=True)

    if principal.jti and is_token_revoked(principal.jti, db):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    _check_password_change_revocation(user, principal)
    _maybe_run_lazy_gc(db)

    return user, _principal_as_payload(principal)


def get_user_for_logout(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> tuple[User, dict]:
    """Resolve the credential for the /logout endpoint.

    The standard dependencies reject already-revoked tokens with 401, but
    /logout must be idempotent: if the caller hits it twice with the same
    token, both calls should report success ("the token is revoked", which it
    is). So this dependency:

    - validates the signature and lookup as usual,
    - applies the generalized blanket revocation (we don't want to give back
      signal that the token was usable for logging out *again* after a
      password/role rotation already invalidated it),
    - **does not** reject on per-jti revocation. The /logout handler treats
      "already revoked" as the success case.
    """
    user, principal = _decode_and_load_user(credentials, db)
    _check_password_change_revocation(user, principal)
    _maybe_run_lazy_gc(db)
    return user, _principal_as_payload(principal)
