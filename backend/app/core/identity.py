"""Shared credential resolver -- the single place HTTP and WebSocket/handoff
auth converge.

Cognito is the sole authentication authority (Cognito-only auth migration,
``.kiro/specs/login/prompt.md`` Phase 1). Before this module, the codebase
had TWO independent token validators that had to be kept in sync by hand:
``core/dependencies.py::_decode_and_load_user`` (HTTP, raises) and
``api/run_engine.py::_authenticate_token`` (WebSocket/handoff, returns
``None``). Both are now thin adapters over ``verify_credential`` +
``resolve_principal`` here, closing that protocol-drift risk.

Design
------
``verify_credential(token)`` verifies a Cognito RS256 access token offline
(``core.cognito.verify_cognito_access_token`` against the pool's JWKS). There
is no other credential path: local bcrypt/HS256 authentication and the
break-glass local-admin exemption have been removed entirely.

It returns a small ``Principal`` carrying whatever the generalized
revocation check + role/tier resolution need: ``sub`` (the Cognito `sub`),
``jti``, ``iat``, and ``groups`` (the token's ``cognito:groups`` claim).

``resolve_principal(principal, db)`` maps that back to a ``User`` row via
``users.cognito_sub == principal.sub``.

Precedence rule (security-critical, easy to get backwards): ``cognito:groups``
is ALWAYS authoritative for tier/admin decisions; the DB ``tier``/``is_admin``
columns are advisory only (a refreshed-on-login projection). The projection is
never itself the input to an authorization decision -- see ``effective_tier``/
``effective_is_admin`` below.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core import auth_events
from app.core.auth_events import AuthEvent
from app.core.cognito import CognitoVerificationError, verify_cognito_access_token
from app.core.entitlements import resolve_is_admin_from_groups, resolve_tier_from_groups
from app.models.user import User


logger = logging.getLogger("app.core.identity")


class CredentialInvalid(Exception):
    """Raised by verify_credential when the token is not a valid Cognito
    access token. Callers translate this into their own failure mode (401
    for HTTP, None for the WS/handoff path)."""


@dataclass
class Principal:
    """Result of verify_credential -- always a Cognito principal.

    ``sub`` is the Cognito `sub` claim; ``resolve_principal`` matches it
    against ``users.cognito_sub``, never ``users.id`` directly.
    """

    provider: str  # "cognito" -- the only value; kept as a field (rather
    # than removed) because callers across the codebase (auth.py, admin.py,
    # run_stream.py) still construct/compare Principal.provider, and pinning
    # it to the single literal here is less invasive than a wider signature
    # change in this phase.
    sub: str
    jti: str | None
    iat: int | None
    exp: int | None = None
    groups: list[str] = field(default_factory=list)


def _coerce_to_aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def verify_credential(token: str, *, allow_expired: bool = False) -> Principal:
    """Verify a Cognito RS256 access token. This is the ONLY credential path.

    ``allow_expired`` (P1 fix, COGNITO-AUTH-QA-BUGS.md "Token Refresh:
    Impossible After Access Token Expiry"): when True, an OTHERWISE-valid
    token whose ``exp`` has passed is still accepted, bounded by
    ``settings.AUTH_REFRESH_GRACE_SECONDS`` past ``exp`` -- past that grace
    window ``CredentialInvalid`` is still raised. This is used by exactly one
    caller, ``POST /api/auth/refresh``: the whole point of that endpoint is to
    mint a fresh token when the old one just ran out, so requiring the OLD
    token to still be unexpired defeats its purpose (a session can only ever
    be kept alive by a client that happens to call refresh strictly BEFORE
    expiry, which an idle REST-only tab with no SSE stream attached never
    does). Every other check (signature, issuer, client_id, token_use,
    sub/jti presence, and -- at the caller layer -- per-jti/blanket
    revocation) still applies unconditionally; only the expiry clock is
    relaxed, and only within the bounded grace window, so a token leaked long
    ago cannot be replayed into a fresh one indefinitely.

    Raises ``CredentialInvalid`` if the token fails Cognito verification.
    """
    from app.core.config import settings

    try:
        cp = verify_cognito_access_token(token, verify_exp=not allow_expired)
    except CognitoVerificationError as exc:
        raise CredentialInvalid(f"Cognito verification failed: {exc}") from exc

    if allow_expired and cp.exp:
        now = int(datetime.now(timezone.utc).timestamp())
        if now - cp.exp > settings.AUTH_REFRESH_GRACE_SECONDS:
            raise CredentialInvalid("token expired beyond the refresh grace window")

    return Principal(
        provider="cognito",
        sub=cp.sub,
        jti=cp.jti,
        iat=cp.iat,
        exp=cp.exp,
        groups=cp.groups,
    )


def resolve_principal(principal: Principal, db: Session) -> User | None:
    """Map a verified Principal to its ``User`` row. ``None`` if it cannot be.

    Lookup is by ``users.cognito_sub`` -- never ``users.id``, which stays the
    local ownership key every foreign key references.

    Two things happen here beyond the plain lookup, both introduced by Phase 2
    of the Cognito-only auth migration:

    **Just-in-time provisioning (Decision 4b).** A miss is no longer final: a
    token that has ALREADY passed full RS256 verification against the configured
    pool, whose ``sub`` has no local row, provisions one from
    ``AdminGetUser(Username=sub)`` (see ``core/provisioning.py``). Before this,
    a user created in the Cognito console could hold a perfectly valid token and
    still be rejected by every endpoint, forever. Provisioning grants nothing --
    the row's ``tier``/``is_admin`` are the advisory projection, and the gates
    read ``cognito:groups`` off this very token regardless (see the precedence
    rule in this module's docstring). It fails closed on every uncertain
    outcome, including Cognito being unreachable.

    **Disabled-account rejection (Decision 6).** A row whose ``status`` is not
    ``active`` resolves to ``None`` even when its token is otherwise impeccable.
    This is what makes "disable" a real security control rather than a label: a
    Cognito access token stays offline-valid until its own ``exp`` no matter what
    happens at the pool (AWS documents this), so ``AdminDisableUser`` alone
    cannot end a session already in flight. ``tokens_valid_from`` +
    ``AdminUserGlobalSignOut`` cover the ordinary case, and this check is the
    backstop that does not depend on the disabling code having completed every
    step in order.
    """
    user = db.query(User).filter(User.cognito_sub == principal.sub).first()

    if user is None:
        # Imported here rather than at module scope: provisioning imports
        # core.cognito and core.entitlements, and keeping the edge one-way
        # (identity -> provisioning, never the reverse) is what stops the
        # resolver and the provisioner becoming mutually recursive.
        from app.core.provisioning import provision_from_token_sub

        user = provision_from_token_sub(db, sub=principal.sub, groups=principal.groups)
        if user is None:
            return None

    if not _is_active(user):
        logger.info("Rejecting a credential for a non-active user row: %s", user.id)
        return None

    return user


def _is_active(user: User) -> bool:
    """Whether this row's ``status`` permits authentication at all.

    ``getattr`` with an ``active`` default, not ``user.status``, so a ``User``
    stand-in without the column (several unit-test fakes build a bare object
    with only the attributes their subject reads) is treated as active rather
    than silently locked out. The column itself is NOT NULL with a server
    default, so a real row always has a value.
    """
    return getattr(user, "status", "active") == "active"


def is_revoked_by_token_validity(user: User, principal: Principal) -> bool:
    """Generalized blanket-revocation check (migration plan §5.3).

    Rejects a token whose `iat` predates
    ``max(password_changed_at, tokens_valid_from)`` at whole-second
    resolution -- the exact tolerance rule the pre-Cognito
    ``_check_password_change_revocation`` already documented and tested,
    generalized to a second trigger (role/tier change) without changing the
    existing behaviour for password-only rotations.
    """
    if principal.iat is None:
        return False

    pwd_changed_at = _coerce_to_aware_utc(user.password_changed_at)
    tokens_valid_from = _coerce_to_aware_utc(user.tokens_valid_from)

    candidates = [d for d in (pwd_changed_at, tokens_valid_from) if d is not None]
    if not candidates:
        return False

    cutoff_seconds = int(max(candidates).timestamp())
    return principal.iat < cutoff_seconds


def effective_tier(user: User, principal: Principal) -> str:
    """The tier that actually governs entitlement decisions right now.

    ``cognito:groups`` is ALWAYS authoritative -- never the DB column, which
    is only a refreshed-on-login projection. ``user`` is accepted (and
    otherwise unused) to keep this function's signature stable for existing
    callers.
    """
    del user
    return resolve_tier_from_groups(principal.groups)


def effective_is_admin(user: User, principal: Principal) -> bool:
    """See effective_tier -- same precedence rule, for the admin flag."""
    del user
    return resolve_is_admin_from_groups(principal.groups)


class AdminMfaRequired(Exception):
    """Raised when the CURRENT SESSION lacks proof of completing the second
    factor their admin role requires.

    Distinct from a generic authorization failure because the caller is
    genuinely an admin -- they just haven't (yet, THIS session) proven MFA.
    Routes translate this into a 403 carrying a machine-readable code so the
    frontend can send the user to the enrolment/re-login flow instead of
    showing a dead end.
    """


def enforce_admin_mfa(user: User, principal: Principal) -> None:
    """Admin-only, SESSION-BOUND MFA gate (P0 fix — COGNITO-AUTH-QA-BUGS.md
    "Admin MFA is Off by Default and Bypassable"; migration plan §5.5, Phase
    6 item 1).

    Cognito's ``mfa_configuration`` is POOL-WIDE (``OFF``/``OPTIONAL``/``ON``);
    there is no native "required for admins only". Setting the whole pool to
    ``ON`` would force TOTP on every basic-tier user, which was explicitly not
    the cutover decision (Decision 4: optional at cutover, required for admins
    in Phase 6). So the admin requirement is enforced HERE, in application code,
    against a pool that stays ``OPTIONAL``.

    THE PROOF IS SESSION-BOUND, NOT ACCOUNT-ENROLMENT. The previous
    implementation asked Cognito "has this account EVER confirmed a factor"
    (``has_any_confirmed_mfa``) — a question about enrolment, not about
    whether THIS token was minted from a session that actually completed a
    challenge. That let an admin holding nothing but a password-only bearer
    call ``POST /mfa/totp/associate`` + ``/verify`` (no reauthentication
    required by either call) and then reuse that SAME original bearer against
    every ``/api/admin/*`` route, because enrolling a factor and proving it at
    sign-in are different Cognito operations entirely.

    The fix compares the token's ``iat`` against ``user.mfa_verified_at`` — a
    column stamped by ``api/auth.py::login_challenge`` ONLY when the caller
    just answered a real MFA challenge (``SOFTWARE_TOKEN_MFA`` /
    ``EMAIL_OTP``) during sign-in, never by the enrolment endpoints. A token
    minted before that stamp (including a password-only bearer obtained
    before the admin ever enrolled a factor) fails the gate; a token minted
    by the login flow that just passed the challenge — whose ``iat`` is at or
    after the stamp — passes. An admin who enrols a NEW factor while holding
    an old bearer gains nothing until they log out and back in through the
    challenge, which is the reauthentication the old design was missing.

    This is also FAIL-CLOSED, not fail-open: the whole point of the redesign
    is that the check no longer makes a Cognito API call on the request path
    (no ``AdminGetUser`` round-trip, no "graceful" bypass on a lookup error) —
    it reads a local column already loaded on ``user``. A missing/stale stamp
    denies, full stop.

    Scope, still deliberate: only applies when ``ADMIN_MFA_REQUIRED`` is on,
    so an operator can enable this deliberately after their admins have
    enrolled rather than locking themselves out the moment the code ships.
    There is no local-admin exemption -- Cognito is the sole authentication
    authority, so every admin principal is a Cognito principal and this gate
    applies uniformly.

    The check is factor-AGNOSTIC: any confirmed second factor satisfies it,
    whether TOTP or email OTP -- ``login_challenge`` stamps the SAME column
    regardless of which challenge type was answered.
    """
    from app.core.config import settings

    if not settings.ADMIN_MFA_REQUIRED:
        return
    if not effective_is_admin(user, principal):
        return

    mfa_verified_at = _coerce_to_aware_utc(getattr(user, "mfa_verified_at", None))
    session_proved_mfa = (
        mfa_verified_at is not None
        and principal.iat is not None
        and principal.iat >= int(mfa_verified_at.timestamp())
    )

    if not session_proved_mfa:
        auth_events.emit(
            AuthEvent.ADMIN_MFA_BLOCKED,
            user_id=user.id,
            provider="cognito",
            reason="no_confirmed_mfa" if mfa_verified_at is None else "stale_session",
        )
        raise AdminMfaRequired(
            "Two-factor authentication is required for administrator access. "
            "Enable it from your account security settings, then sign in again "
            "to complete the challenge."
        )
