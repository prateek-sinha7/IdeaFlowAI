"""Shared credential resolver -- the single place HTTP and WebSocket/handoff
auth converge.

Part of the Cognito Authentication & Authorization Migration
(``.planning/COGNITO-MIGRATION-PLAN.md`` §4.2). Before this module, the
codebase had TWO independent token validators that had to be kept in sync by
hand: ``core/dependencies.py::_decode_and_load_user`` (HTTP, raises) and
``api/run_engine.py::_authenticate_token`` (WebSocket/handoff, returns
``None``). Both are now thin adapters over ``verify_credential`` +
``resolve_principal`` here, closing the protocol-drift risk the plan calls
out (R8).

Design
------
``verify_credential(token)`` dual-accepts:

  * a Cognito RS256 access token (verified offline via
    ``core.cognito.verify_cognito_access_token``), or
  * (only while ``settings.AUTH_ALLOW_LEGACY_JWT`` is True, OR the token's
    ``sub`` resolves to the break-glass local-admin account) a legacy HS256
    token signed with the local ``SECRET_KEY``.

It returns a small, provider-agnostic ``Principal`` carrying whatever the
generalized revocation check + role/tier resolution need: ``sub`` (the
Cognito `sub` OR the local ``users.id``, depending on provider), ``jti``,
``iat``, and ``groups`` (empty for the legacy path -- the legacy path has no
group concept and DB columns are authoritative for it, see §5.4).

``resolve_principal(principal, db)`` maps that back to a ``User`` row:
Cognito path -> ``users.cognito_sub == principal.sub``; legacy path ->
``users.id == principal.sub``.

Precedence rule (migration plan §5.4, restated here because it is
security-critical and easy to get backwards): for a Cognito-authenticated
principal, ``cognito:groups`` is authoritative and the DB
``tier``/``is_admin`` columns are advisory (refreshed-on-login projection
only). For the break-glass local principal, the DB columns ARE the
authority. The projection is never itself the input to an authorization
decision on the Cognito path -- see ``effective_tier``/``effective_is_admin``
below, which is the ONLY sanctioned place that branches on provider to decide
which source wins.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from jose import JWTError
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core import auth_events
from app.core.auth_events import AuthEvent
from app.core.cognito import CognitoVerificationError, verify_cognito_access_token
from app.core.config import settings
from app.core.entitlements import resolve_is_admin_from_groups, resolve_tier_from_groups
from app.core.security import decode_access_token
from app.models.user import User


logger = logging.getLogger("app.core.identity")


class CredentialInvalid(Exception):
    """Raised by verify_credential when neither the Cognito nor the legacy
    path accepts the token. Callers translate this into their own failure
    mode (401 for HTTP, None for the WS/handoff path)."""


@dataclass
class Principal:
    """Provider-agnostic result of verify_credential.

    `sub` is EITHER a Cognito `sub` (provider == "cognito") OR a local
    `users.id` (provider == "local") -- resolve_principal knows which column
    to match on from `provider`. Never conflate the two: a Cognito `sub` is
    never a valid `users.id` and vice versa (COGNITO-MIGRATION-PLAN §3.3 --
    `users.id` never changes meaning).
    """

    provider: str  # "cognito" | "local"
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


def verify_credential(token: str) -> Principal:
    """Dual-accept verifier: Cognito RS256 first, legacy HS256 as fallback.

    Ordering rationale: once Cognito is the active provider, the overwhelming
    majority of tokens presented are Cognito tokens, so trying that path
    first avoids paying the legacy-decode cost (and its distinct error
    surface) on every request during the dual-accept window. A token that
    fails Cognito verification falls through to the legacy decode only while
    ``AUTH_ALLOW_LEGACY_JWT`` is True (or unconditionally, if
    ``AUTH_PROVIDER`` is still "local" -- an environment that hasn't enabled
    Cognito yet must keep working exactly as before).

    Raises ``CredentialInvalid`` if neither path accepts the token.
    """
    cognito_active = settings.AUTH_PROVIDER.lower() == "cognito"

    if cognito_active:
        try:
            cp = verify_cognito_access_token(token)
            return Principal(
                provider="cognito",
                sub=cp.sub,
                jti=cp.jti,
                iat=cp.iat,
                exp=cp.exp,
                groups=cp.groups,
            )
        except CognitoVerificationError:
            if not settings.AUTH_ALLOW_LEGACY_JWT and not settings.BREAK_GLASS_ENABLED:
                raise CredentialInvalid("Cognito verification failed and legacy fallback disabled")
            # Fall through -- either the dual-accept window is open, or the
            # break-glass account may be presenting a legacy token even with
            # AUTH_ALLOW_LEGACY_JWT off (break-glass always accepts local
            # tokens; resolve_principal is what actually enforces that only
            # the single break-glass row can use this path in practice,
            # since every other user's local password_hash is NULL post-cutover).

    try:
        payload = decode_access_token(token)
    except JWTError as exc:
        raise CredentialInvalid(f"legacy token verification failed: {exc}") from exc

    sub = payload.get("sub")
    if not sub:
        raise CredentialInvalid("legacy token missing sub")

    exp_raw = payload.get("exp")
    return Principal(
        provider="local",
        sub=sub,
        jti=payload.get("jti"),
        iat=int(payload["iat"]) if isinstance(payload.get("iat"), (int, float)) else None,
        exp=int(exp_raw) if isinstance(exp_raw, (int, float)) else None,
        groups=[],
    )


def resolve_principal(principal: Principal, db: Session) -> User | None:
    """Map a verified Principal to its User row. None if no match.

    On the LOCAL path this also enforces the break-glass invariants (§5.6),
    fail-closed: a local-admin credential is only honoured when
    ``BREAK_GLASS_ENABLED`` is set AND exactly one local admin exists. See
    ``_local_admin_credential_is_permitted``.
    """
    if principal.provider == "cognito":
        return db.query(User).filter(User.cognito_sub == principal.sub).first()

    user = db.query(User).filter(User.id == principal.sub).first()
    if user is None:
        return None

    if (
        user.auth_provider == "local"
        and bool(user.is_admin)
        and not _local_admin_credential_is_permitted(db)
    ):
        return None

    return user


def _local_admin_credential_is_permitted(db: Session) -> bool:
    """Fail-closed gate on the break-glass admin credential (plan §5.6).

    Two conditions, both required:

    1. ``settings.BREAK_GLASS_ENABLED`` — the documented kill switch.
    2. Exactly ONE ``auth_provider='local'`` admin row exists.

    Condition 2 is the load-bearing one. The break-glass account's whole
    justification is that there is exactly one of it, documented and alarmed.
    If a second local admin appears — whether by operator error, a bad seed
    script, or an attacker who managed an INSERT — the correct response is to
    stop honouring the local-admin path entirely rather than to trust an
    unknown number of privileged local credentials. Regular Cognito users are
    completely unaffected; the only thing that stops working is the very path
    whose safety assumption has been violated.

    Deliberately NOT cached: it is one indexed COUNT on the local-admin path
    only (never on the Cognito path, which is every normal request), and a
    stale cached "permitted" answer here would defeat the entire control.
    """
    if not settings.BREAK_GLASS_ENABLED:
        logger.warning(
            "Rejected a local-admin credential: BREAK_GLASS_ENABLED is false."
        )
        return False

    local_admin_count = (
        db.query(func.count(User.id))
        .filter(User.auth_provider == "local", User.is_admin.is_(True))
        .scalar()
        or 0
    )

    if local_admin_count != 1:
        # Alarmed event: in a healthy system this is impossible, which is
        # precisely why it warrants a page rather than a log line nobody reads.
        auth_events.emit(
            AuthEvent.BREAK_GLASS_INVARIANT_VIOLATED,
            reason="unexpected_local_admin_count",
            local_admin_count=local_admin_count,
        )
        logger.error(
            "Rejected a local-admin credential: expected exactly 1 local admin "
            "(break-glass invariant, plan section 5.6) but found %d. "
            "Run scripts/verify_cognito_cutover.py to inspect.",
            local_admin_count,
        )
        return False

    return True


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

    Cognito path: `cognito:groups` is authoritative (never the DB column).
    Local/break-glass path: the DB column IS the authority (there is no
    group claim to read). This function is the ONLY place that branches on
    provider to decide precedence -- see the module docstring's precedence
    rule.
    """
    if principal.provider == "cognito":
        return resolve_tier_from_groups(principal.groups)
    return user.tier


def effective_is_admin(user: User, principal: Principal) -> bool:
    """See effective_tier -- same precedence rule, for the admin flag."""
    if principal.provider == "cognito":
        return resolve_is_admin_from_groups(principal.groups)
    return bool(user.is_admin)


class AdminMfaRequired(Exception):
    """Raised when an admin lacks the TOTP factor their role requires.

    Distinct from a generic authorization failure because the caller is
    genuinely an admin -- they just need to finish enrolment. Routes translate
    this into a 403 carrying a machine-readable code so the frontend can send
    the user to the enrolment flow instead of showing a dead end.
    """


def enforce_admin_mfa(user: User, principal: Principal) -> None:
    """Admin-only MFA gate (migration plan §5.5, Phase 6 item 1).

    Cognito's ``mfa_configuration`` is POOL-WIDE (``OFF``/``OPTIONAL``/``ON``);
    there is no native "required for admins only". Setting the whole pool to
    ``ON`` would force TOTP on every basic-tier user, which was explicitly not
    the cutover decision (Decision 4: optional at cutover, required for admins
    in Phase 6). So the admin requirement is enforced HERE, in application code,
    against a pool that stays ``OPTIONAL``.

    Scope and fail-safety, both deliberate:

    * Only applies to a **Cognito** principal. The break-glass local admin is
      exempt by construction -- it exists precisely for the case where Cognito
      is unreachable, so gating it on a Cognito API call would defeat its only
      purpose. Its compensating control is the alarm on every use (§5.6).
    * Only applies when ``ADMIN_MFA_REQUIRED`` is on, so an operator can enable
      this deliberately after their admins have enrolled rather than locking
      themselves out the moment the code ships.
    * If the Cognito lookup itself fails, we FAIL OPEN for this specific check
      and log loudly. This is the one place in the auth path that does not fail
      closed, and the reasoning is explicit: the caller has ALREADY been fully
      authenticated and authorized as an admin by this point. Turning a
      transient ``AdminGetUser`` blip into a total loss of admin access would
      make a Cognito hiccup an outage, which is a worse failure than briefly
      not enforcing a second factor on an already-verified admin.
    """
    if not settings.ADMIN_MFA_REQUIRED:
        return
    if principal.provider != "cognito":
        return
    if not effective_is_admin(user, principal):
        return

    from app.core.cognito import has_confirmed_totp

    try:
        enrolled = has_confirmed_totp(user.email)
    except Exception as exc:  # noqa: BLE001 - deliberate fail-open, see docstring
        logger.error(
            "Admin MFA check could not reach Cognito for %s; allowing the request "
            "rather than failing an authenticated admin closed: %s",
            user.id,
            exc,
        )
        return

    if not enrolled:
        auth_events.emit(
            AuthEvent.ADMIN_MFA_BLOCKED,
            user_id=user.id,
            provider="cognito",
            reason="no_confirmed_totp",
        )
        raise AdminMfaRequired(
            "Two-factor authentication is required for administrator access. "
            "Enrol a TOTP device via POST /api/auth/mfa/totp/associate."
        )
