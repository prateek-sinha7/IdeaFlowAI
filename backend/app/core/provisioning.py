"""Just-in-time provisioning of local ``users`` rows from Cognito identities.

Cognito-only auth migration, ``.kiro/specs/login/prompt.md`` Decision 4. This
module is the ONE place a ``users`` row is created from an authentication event
rather than from an explicit admin action.

Why this exists
---------------
Before Phase 2, a user created directly in the Cognito console could
authenticate against the pool and still not log in: both ``POST
/api/auth/login`` and ``core/identity.py::resolve_principal`` required a local
``users`` row to already exist, and nothing created one outside
``POST /api/admin/users``. Such an account was an "orphan" -- provably present
in the pool, permanently unable to use the application, and diagnosable only by
running ``scripts/verify_cognito_cutover.py --check-pool``. ``api/auth.py``
went as far as classifying the condition into a dedicated audit reason
(``unknown_user_orphaned_pool_user``) precisely because it was a real,
recurring operational failure that looked identical to a typo'd email.

Provisioning on first successful authentication removes the failure mode
outright rather than reporting it better.

Security posture
----------------
Provisioning is an identity MAPPING step, never an authorization decision.
Nothing here grants anything: the row it writes carries only the advisory
``tier``/``is_admin`` PROJECTION, and every gate resolves the effective values
from the verified token's ``cognito:groups`` (``core/identity.py``'s precedence
rule). A row provisioned with the wrong projection is a stale display value,
not a privilege.

Three rules make that safe, and all three are load-bearing:

1. **Authentication happens FIRST, always.** Both entry points are reached
   only after Cognito has already accepted the caller -- either a successful
   ``AdminInitiateAuth``/``AdminRespondToAuthChallenge``
   (:func:`provision_from_login`) or a fully verified RS256 access token
   signed by the configured pool (:func:`provision_from_token_sub`). Neither
   ever provisions from an unauthenticated, client-supplied identity claim.
2. **A disabled pool user is never provisioned.** ``Enabled=false`` at Cognito
   means the account must not obtain a foothold in the application, so
   provisioning refuses rather than creating a row that a later token could
   attach to.
3. **An email collision fails CLOSED.** See :func:`_link_or_refuse`.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone

from botocore.exceptions import ClientError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import cognito
from app.core.entitlements import resolve_is_admin_from_groups, resolve_tier_from_groups
from app.models.user import User

logger = logging.getLogger("app.core.provisioning")

#: Refusal cache: sub -> expiry epoch. Caches decisions to refuse provisioning
#: (disabled/missing pool user) for 60 seconds to avoid re-calling AdminGetUser
#: on the hot path.
_refusal_cache: dict[str, float] = {}

#: Local row states. ``users.status`` (migration 0038) is authoritative for
#: whether a row may authenticate AT ALL, independent of token validity.
STATUS_ACTIVE = "active"
STATUS_DISABLED = "disabled"


class ProvisioningRefused(Exception):
    """Provisioning was declined for a fail-closed reason.

    Distinct from "the provider was unreachable": a refusal is a decision, and
    callers translate it into the same generic 401 an ordinary auth failure
    produces. The refusal reason is server-side only -- never echoed to the
    client, since it would otherwise describe pool state to an unauthenticated
    caller.
    """


def _coerce_to_aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _projection_from_groups(groups: list[str]) -> tuple[str, bool]:
    return resolve_tier_from_groups(groups), resolve_is_admin_from_groups(groups)


def refresh_projection(user: User, groups: list[str], db: Session) -> None:
    """Overwrite the advisory ``tier``/``is_admin`` projection from ``groups``.

    Commits. Never consulted by an authorization decision -- the projection
    exists so ``GET /api/admin/users`` can list tier/role without an
    ``AdminListGroupsForUser`` call per row.
    """
    user.tier, user.is_admin = _projection_from_groups(groups)
    user.roles_synced_at = datetime.now(timezone.utc)
    db.commit()


def refresh_projection_if_stale(
    user: User, groups: list[str], token_iat: int | None, db: Session
) -> None:
    """Refresh the projection when this token is NEWER than the last sync.

    Decision 4: "DB ``tier``/``is_admin`` remain a projection refreshed at
    login and on any authenticated request whose token ``iat`` >
    ``roles_synced_at``." Without the second half, the projection only ever
    tracked logins, so an admin tier change followed by a
    ``AdminUserGlobalSignOut`` + silent ``POST /api/auth/refresh`` (which mints
    a token with fresh groups but is NOT a login) left the admin list showing
    the pre-change tier indefinitely.

    Cheap by construction: the comparison is against a column already loaded on
    ``user``, and the write only happens on the FIRST request carrying a newer
    token, not on every request. ``iat`` resolution is whole seconds, matching
    ``is_revoked_by_token_validity``'s tolerance rule, so a token minted in the
    same second as the last sync does not re-write.

    Failure here is deliberately swallowed: a projection refresh is
    observability, and a commit failure on it must not turn an otherwise valid
    authenticated request into a 500.
    """
    if token_iat is None:
        return

    synced_at = _coerce_to_aware_utc(user.roles_synced_at)
    if synced_at is not None and token_iat <= int(synced_at.timestamp()):
        return

    tier, is_admin = _projection_from_groups(groups)
    try:
        user.tier = tier
        user.is_admin = is_admin
        user.roles_synced_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as exc:  # noqa: BLE001 - projection refresh is best-effort
        logger.warning("Could not refresh role projection for %s: %s", user.id, exc)
        db.rollback()


def _link_or_refuse(db: Session, *, email: str, sub: str) -> User | None:
    """Handle an existing row that shares this email but not this ``sub``.

    Decision 4a asks for a LINK here: "if a row with the same email exists with
    ``cognito_sub IS NULL``, LINK it instead of duplicating". That branch is
    unreachable as written -- migration 0038 made ``cognito_sub`` NOT NULL, so
    no such row can exist any more (recorded in ``MERGE_NOTES.md`` §7). The
    linking of pre-cutover rows is done ahead of the migration by
    ``scripts/migrate_local_users_to_cognito.py --link``, which is where that
    behaviour now lives.

    What CAN still happen is an email collision with a DIFFERENT ``sub``: an
    operator deletes a pool user and recreates the same address, minting a new
    ``sub`` while the old local row (and everything it owns) still carries the
    old one. Re-pointing the row at the new ``sub`` would be an account-takeover
    primitive -- whoever controls that mailbox at the pool would inherit the
    previous holder's runs, chats, artifacts and API keys, all of which are
    keyed on ``users.id``. So this refuses and leaves the collision for an
    operator to resolve deliberately (``scripts/reconcile_cognito_users.py
    --report`` surfaces it). Returns ``None`` when there is no collision.
    """
    existing = db.query(User).filter(User.email == email).first()
    if existing is None:
        return None

    if existing.cognito_sub == sub:
        return existing

    logger.error(
        "Refusing to provision: local user %s already holds email with a "
        "DIFFERENT cognito_sub. The pool user was likely deleted and "
        "recreated. Resolve with scripts/reconcile_cognito_users.py before "
        "this account can sign in.",
        existing.id,
    )
    raise ProvisioningRefused("email is already mapped to a different Cognito identity")


def _insert_user(db: Session, *, email: str, sub: str, groups: list[str]) -> User:
    """Insert a provisioned row, tolerating a concurrent winner.

    Race-safe via the database, not a lock: two requests for the same brand-new
    identity (a browser that fires several parallel calls on first load is
    enough) can both find no row and both insert. ``uq_users_cognito_sub``
    (0031/0038) makes exactly one of them win; the loser re-reads the winner's
    row rather than surfacing a 500. This is the "idempotent and race-safe
    (unique index; catch ``IntegrityError``, re-read)" requirement of
    Decision 4.
    """
    tier, is_admin = _projection_from_groups(groups)
    user = User(
        id=str(uuid.uuid4()),
        email=email,
        cognito_sub=sub,
        tier=tier,
        is_admin=is_admin,
        status=STATUS_ACTIVE,
        roles_synced_at=datetime.now(timezone.utc),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        winner = db.query(User).filter(User.cognito_sub == sub).first()
        if winner is None:
            # The unique violation was on something else -- almost certainly
            # `users.email` against a row holding a different sub, i.e. the
            # collision `_link_or_refuse` guards, lost as a race instead of
            # seen as a read. Same fail-closed answer.
            logger.error(
                "Provisioning for cognito_sub=... hit an integrity error with no "
                "matching row afterwards; treating as an email collision."
            )
            raise ProvisioningRefused("could not provision a local identity row")
        return winner

    db.refresh(user)
    logger.info("Provisioned local user %s from Cognito on first sign-in", user.id)
    return user


def provision_from_login(
    db: Session, *, email: str, sub: str, groups: list[str]
) -> User:
    """Resolve (or create) the local row for a caller Cognito just authenticated.

    Called from ``api/auth.py`` after a successful ``AdminInitiateAuth`` or
    ``AdminRespondToAuthChallenge``. ``sub`` and ``groups`` come from the access
    token that call just returned, so no extra AWS round-trip is needed to learn
    them, and no ``AdminGetUser`` is issued on the hot path where the row
    already exists.

    ``Enabled`` is not re-checked here: Cognito refuses to authenticate a
    disabled user at all, so a successful auth result IS the enabled proof.
    """
    user = db.query(User).filter(User.cognito_sub == sub).first()
    if user is not None:
        return user

    linked = _link_or_refuse(db, email=email, sub=sub)
    if linked is not None:
        return linked

    return _insert_user(db, email=email, sub=sub, groups=groups)


def provision_from_token_sub(db: Session, *, sub: str, groups: list[str]) -> User | None:
    """Resolve (or create) the local row for a VERIFIED access token's ``sub``.

    Decision 4b: a verified RS256 token whose ``sub`` has no local row triggers
    provisioning via ``AdminGetUser(Username=sub)``. This is the path that makes
    a console-created user work on a token they obtained from some other flow,
    and the path that heals a local row deleted out from under a live session.

    Returns ``None`` -- never raises -- when the identity cannot be provisioned,
    because every caller's contract for "no user" is already "reject this
    credential":

    * pool user absent (``UserNotFoundException``) -> the account is gone;
    * pool user ``Enabled=false`` -> disabled accounts get no foothold;
    * email collision (:func:`_link_or_refuse`) -> fail closed;
    * Cognito unreachable / no credentials -> FAIL CLOSED, deliberately. An
      unverifiable provisioning read must not become a provisioned row.

    Cost: one ``AdminGetUser`` on a genuine miss only. The overwhelmingly common
    case (row exists) never reaches this function -- ``resolve_principal``
    returns on the DB hit first.
    """
    # Check refusal cache first: if sub was recently refused, don't call Cognito again
    now = time.time()
    if sub in _refusal_cache:
        expiry = _refusal_cache[sub]
        if now < expiry:
            # Cached refusal is still valid
            return None
        else:
            # Expired, clean up and proceed to Cognito
            del _refusal_cache[sub]

    try:
        result = cognito.admin_get_user(sub)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code != "UserNotFoundException":
            logger.warning("AdminGetUser during JIT provisioning returned %s", code)
        # Cache the refusal for 60 seconds
        _refusal_cache[sub] = now + 60
        return None
    except Exception as exc:  # noqa: BLE001 - no creds / endpoint / DNS failure
        logger.warning("AdminGetUser during JIT provisioning failed: %s", exc)
        # Cache the refusal for 60 seconds
        _refusal_cache[sub] = now + 60
        return None

    if not result.get("Enabled", True):
        logger.info("Refusing to provision a DISABLED Cognito user")
        # Cache the refusal for 60 seconds
        _refusal_cache[sub] = now + 60
        return None

    attributes = cognito.user_attributes(result)
    email = attributes.get("email")
    if not email:
        # An email-username pool cannot produce this; a misconfigured pool
        # could. `users.email` is NOT NULL and unique, so there is nothing
        # sensible to insert.
        logger.warning("Refusing to provision a Cognito user with no email attribute")
        # Cache the refusal for 60 seconds
        _refusal_cache[sub] = now + 60
        return None

    try:
        return provision_from_login(db, email=email, sub=sub, groups=groups)
    except ProvisioningRefused:
        # Cache the refusal for 60 seconds
        _refusal_cache[sub] = now + 60
        return None
