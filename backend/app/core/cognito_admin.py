"""The admin lifecycle service — every Cognito Admin* write, in one place.

Cognito-only auth migration (``.kiro/specs/login/prompt.md``), Decision 6:
*"One service module (``backend/app/core/cognito_admin.py``) wraps all Admin
APIs with typed errors, idempotent ``UserNotFoundException`` handling,
throttle retries, and ``auth_events.py`` audit events."*

Why this exists, given ``core/cognito.py`` already wraps every Admin* call
-----------------------------------------------------------------------
``core/cognito.py`` is a pure boto3 ADAPTER: one function per API, doing
parameter marshalling and nothing else. Before this module, every LIFECYCLE
decision — what order to call things in, how to compensate a partial failure,
whether ``UserNotFoundException`` means "fine, proceed" or "stop and report" —
lived inline in ``api/admin.py``'s route handlers, duplicated (and drifting)
across create/tier/role/delete. The ordering bugs the prior audit found
(non-atomic Cognito/DB updates, a missing stale-group sweep) were symptoms of
that duplication, not of the adapter layer being wrong.

This module is the LIFECYCLE layer: it knows the *sequence* an admin action
requires and the *compensation* a partial failure needs, but it still calls
``core/cognito.py`` for every actual AWS request. ``api/admin.py`` becomes a
thin FastAPI-shaped caller of these functions — request parsing, response
shaping, audit emission at the call site — never a second copy of the
ordering logic.

Ordering invariants every mutation here upholds (Decision 6 / the security
invariants section of the brief)
-----------------------------------------------------------------------
* **Revoke-before-mutate.** Every privilege change or account-ending action
  advances ``tokens_valid_from`` (and commits it) BEFORE the corresponding
  Cognito call, never after. A token minted under the old privilege must fail
  the blanket-revocation check the instant the DECISION is made, regardless of
  whether the Cognito call that enacts it succeeds, retries, or ultimately
  fails. Fail-closed, not fail-open, is the whole point of the ordering.
* **Disable-before-delete.** A pool user is never deleted while still active;
  it is disabled (and globally signed out) first, so a slow or failing
  ``AdminDeleteUser`` cannot leave an ENABLED pool user pointing at a DELETED
  local row — the exact state the security invariants section forbids ("A user
  cannot exist as enabled in Cognito while deleted in the DB").
* **``UserNotFoundException`` is success, not failure**, on every DELETE-shaped
  operation (disable, remove-from-group, delete). The pool user may already be
  absent from a prior partial run; re-running the operation must converge, not
  raise.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from botocore.exceptions import ClientError
from sqlalchemy.orm import Session

from app.core import auth_events, cognito
from app.core.email_identity import canonicalize_email
from app.core.entitlements import ADMIN_GROUP, TIER_GROUPS, group_for_tier
from app.models.user import User

logger = logging.getLogger("app.core.cognito_admin")

#: Exceptions worth one bounded retry — request-rate conditions, not
#: authorization or validation failures. Retrying a THROTTLING error is
#: correct and expected; retrying, say, ``InvalidParameterException`` would
#: just burn the retry budget on a request that can never succeed.
_THROTTLE_CODES = frozenset(
    {"TooManyRequestsException", "ThrottlingException", "LimitExceededException"}
)

#: A handful of Cognito calls per lifecycle action, on a control-plane surface
#: (not a per-request hot path) — two attempts with a short fixed pause is
#: proportionate. An exponential/jittered backoff would be over-engineering
#: for a call volume this low; see core.cognito._fetch_jwks for the same
#: judgement call on the read side.
_THROTTLE_RETRY_ATTEMPTS = 2
_THROTTLE_RETRY_DELAY_SECONDS = 1.0


class CognitoAdminError(Exception):
    """Base for every typed error this module raises.

    ``api/admin.py`` catches this ONE hierarchy at the route layer and maps it
    to an HTTP response — it never needs to know which boto3 exception code
    produced it. Carries the raw ``code`` (when known) so a caller that wants
    it (audit logging) still can.
    """

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class ConflictError(CognitoAdminError):
    """The action conflicts with existing state (duplicate email, etc)."""


class ValidationError(CognitoAdminError):
    """The request itself is invalid (bad tier, weak password, ...)."""


class LastAdminError(CognitoAdminError):
    """Refused because it would leave the admin group empty.

    Distinct from a generic ``ConflictError`` because the caller (the route
    layer) renders a specific, actionable message rather than a generic 409 —
    "you are the last admin" is a materially different situation from "this
    email is taken".
    """


class ProviderUnavailableError(CognitoAdminError):
    """Cognito could not be reached, or returned a non-retryable server error."""


def _retry_on_throttle(operation_name: str, fn, *args, **kwargs):
    """Call ``fn(*args, **kwargs)``, retrying once on a throttling response.

    Every OTHER ``ClientError`` propagates immediately and untouched — this is
    the ONLY place in the lifecycle layer that swallows an exception to retry,
    and it only ever swallows the throttle family. A caller wanting
    ``UserNotFoundException`` treated as success is expected to catch it
    itself; baking that into a shared retry helper would hide the very
    exception type each caller needs to branch on.
    """
    last_exc: ClientError | None = None
    for attempt in range(_THROTTLE_RETRY_ATTEMPTS):
        try:
            return fn(*args, **kwargs)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code not in _THROTTLE_CODES or attempt == _THROTTLE_RETRY_ATTEMPTS - 1:
                raise
            logger.warning(
                "%s throttled (attempt %d/%d), retrying: %s",
                operation_name,
                attempt + 1,
                _THROTTLE_RETRY_ATTEMPTS,
                code,
            )
            last_exc = exc
            time.sleep(_THROTTLE_RETRY_DELAY_SECONDS)
    # Unreachable in practice (the loop either returns or raises), but keeps
    # the type checker honest about every path producing a value or raising.
    if last_exc is not None:
        raise last_exc
    raise AssertionError("_retry_on_throttle: retry loop exited without a result")


def _tolerate_missing(operation_name: str, fn, *args, **kwargs) -> None:
    """Call ``fn``; ``UserNotFoundException`` is success, anything else raises.

    The idempotent-``UserNotFoundException`` half of Decision 6. Used by every
    DELETE-shaped step (disable, group removal, delete) so re-running an
    operation after a partial prior failure converges instead of raising on
    the second attempt.
    """
    try:
        _retry_on_throttle(operation_name, fn, *args, **kwargs)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "UserNotFoundException":
            logger.info(
                "%s: pool user already absent — treating as success", operation_name
            )
            return
        logger.error("%s failed: %s", operation_name, code)
        raise ProviderUnavailableError(
            f"Could not complete {operation_name} at the identity provider.",
            code=code,
        )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def is_last_admin(user: User) -> bool:
    """True if the admin group currently has at most one member.

    A live ``ListUsersInGroup`` read, not the local ``is_admin`` projection —
    the projection is advisory (Decision 3) and could under-count (missing a
    console-added admin) or over-count (a stale row) relative to what Cognito
    would actually let someone act as.

    T6: for the user being acted upon (demoted/disabled/deleted), "is this
    person an admin?" is answered by OR-ing the two sources that could say so,
    then counting the group only if the answer was yes:

        is_admin_target = ADMIN_GROUP in cognito_groups or bool(user.is_admin)

    OR rather than AND because the two sources drift in OPPOSITE directions and
    each failure mode is a lockout:

    * Cognito group, local ``is_admin=False`` — a console-added admin the DB
      never learned about. They are a real admin; demoting them on the strength
      of the stale column would empty the group.
    * local ``is_admin=True``, no Cognito group — a stale row. Honoured anyway,
      because a row claiming admin is itself evidence of drift, and treating it
      as "not an admin" removes the guard from precisely the account whose state
      is already untrustworthy.

    Returns False (no protection needed) only when NEITHER source claims admin.
    """
    # This read ALWAYS runs. It is the authoritative half of the OR, so checking
    # `user.is_admin` first and short-circuiting would let a stale is_admin=False
    # row hide a genuine Cognito admin -- the exact drift this function exists to
    # catch.
    try:
        cognito_groups = cognito.admin_list_groups_for_user(user.email)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "UserNotFoundException":
            # Authoritative: no pool identity => no provider admin rights to protect.
            # Read APIs like ListGroupsForUser sit outside prevent_user_existence_errors,
            # so this is a definitive "user does not exist" (see cognito.py:437-441),
            # not a transient throttle or network failure.
            return False
        # Any other failure: degrade to the local projection ALONE, which the OR
        # below expresses as `False or bool(user.is_admin)`. A provider outage
        # therefore cannot silently drop the protection from a row that still claims
        # admin.
        cognito_groups = []

    is_admin_target = ADMIN_GROUP in cognito_groups or bool(user.is_admin)
    if not is_admin_target:
        return False

    # Only now is the count meaningful: a non-admin can never be the last admin,
    # so the second call is skipped for them rather than spent.
    #
    # Failure surfaces as a TYPED error, for two reasons. This call used to be
    # unguarded, so a throttled or failed ListUsersInGroup escaped as a raw
    # ``ClientError`` — which ``api/admin.py::_raise_for`` does not translate, so
    # the guard whose entire job is to produce a clean 409 produced a 500 instead.
    # And raising the lifecycle layer's own error type is what lets the route
    # layer choose the status code without importing botocore (T8 boundary).
    try:
        members = _retry_on_throttle(
            "ListUsersInGroup", cognito.list_users_in_group, ADMIN_GROUP
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        logger.error("ListUsersInGroup failed for %s: %s", ADMIN_GROUP, code)
        raise ProviderUnavailableError(
            "Could not verify admin-group membership at the identity provider.",
            code=code,
        ) from exc
    return len(members) <= 1


def generate_temporary_password() -> str:
    """Generate a temporary password meeting the pool policy (12+ chars, mixed case/digits/symbols).

    Deliberately strong: this is not a user-facing default but an internal
    generator where strength comes free. Never logged or echoed in the response.
    """
    import secrets
    import string

    uppercase = string.ascii_uppercase
    lowercase = string.ascii_lowercase
    digits = string.digits
    symbols = "!@#$%^&*"

    # Ensure at least one of each required character class
    password = [
        secrets.choice(uppercase),
        secrets.choice(lowercase),
        secrets.choice(digits),
        secrets.choice(symbols),
    ]

    # Fill the rest with random characters from all classes
    all_chars = uppercase + lowercase + digits + symbols
    for _ in range(8):  # 4 + 8 = 12 minimum
        password.append(secrets.choice(all_chars))

    # Shuffle so the required characters aren't always in the same positions
    secrets.SystemRandom().shuffle(password)
    return "".join(password)


@dataclass
class CreatedUser:
    email: str
    cognito_sub: str
    tier: str
    is_admin: bool


def invite_user(
    email: str,
    *,
    tier: str,
    is_admin: bool,
    temporary_password: str | None = None,
) -> CreatedUser:
    """Create a pool user by INVITATION. Never sets a permanent password.

    Decision 6: *"AdminCreateUser(..., DesiredDeliveryMediums=[EMAIL]) ->
    invitation with temporary password... NEVER set a permanent password."*
    This is the fix for the gap ``MERGE_NOTES.md`` §4 recorded: the prior
    ``create_user`` flow called ``AdminSetUserPassword(..., permanent=True)``
    with an admin-supplied password immediately after create, which meant an
    admin always knew a live credential for an account that was not theirs —
    the opposite of what an admin-create flow should guarantee.

    ``temporary_password`` is optional and admin-supplied (an operator setting
    up a demo account they will hand over verbally, say); when omitted, Cognito
    generates one itself and the invitation email is the ONLY place it appears.
    Either way the password is TEMPORARY: the recipient answers
    NEW_PASSWORD_REQUIRED on first sign-in (``api/auth.py::login_challenge``
    already handles it) and chooses their own.

    Group membership (tier + admin, if requested) is applied AFTER create. If
    any step after create fails (group assignment or otherwise), the pool user
    is deleted via ``AdminDeleteUser`` to maintain consistency — there is no
    acceptable partial state (a user with no tier group cannot be used). Raises
    ``ConflictError`` for a duplicate email, ``ProviderUnavailableError``
    otherwise.
    """
    email = canonicalize_email(email)
    try:
        create_resp = _retry_on_throttle(
            "AdminCreateUser",
            cognito.admin_create_user,
            email,
            temporary_password,
            desired_delivery_mediums=["EMAIL"],
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "UsernameExistsException":
            raise ConflictError(
                "A user with this email already exists at the identity provider.",
                code=code,
            )
        if code == "InvalidPasswordException":
            raise ValidationError(
                "Password does not meet the password policy.", code=code
            )
        logger.error("AdminCreateUser failed for %s: %s", email, code)
        raise ProviderUnavailableError(
            "Could not create the user at the identity provider.", code=code
        )

    cognito_sub = cognito.user_attributes(create_resp)["sub"]

    try:
        _retry_on_throttle(
            "AdminAddUserToGroup(tier)",
            cognito.admin_add_user_to_group,
            email,
            group_for_tier(tier),
        )
        if is_admin:
            _retry_on_throttle(
                "AdminAddUserToGroup(admin)",
                cognito.admin_add_user_to_group,
                email,
                ADMIN_GROUP,
            )
    except Exception as exc:  # noqa: BLE001
        # On any failure (group assignment or otherwise), delete the pool user
        # to maintain consistency — a partial user is not acceptable.
        _tolerate_missing("AdminDeleteUser", cognito.admin_delete_user, email)
        # If the original error was a ClientError, re-raise as ProviderUnavailableError;
        # otherwise re-raise the exception as-is.
        if isinstance(exc, ClientError):
            code = exc.response.get("Error", {}).get("Code", "")
            logger.error(
                "Group assignment failed for newly-created user %s: %s; compensated with AdminDeleteUser",
                email,
                code,
            )
            raise ProviderUnavailableError(
                "The user could not be fully created at the identity provider.",
                code=code,
            )
        raise

    result = CreatedUser(email=email, cognito_sub=cognito_sub, tier=tier, is_admin=is_admin)

    # Audit: successful user creation
    auth_events.emit(
        auth_events.AuthEvent.USER_CREATED,
        user_id=cognito_sub,
        provider="cognito",
        tier=tier,
        is_admin=is_admin,
    )

    return result


def change_tier(user: User, new_tier: str, db: Session) -> None:
    """Swap tier group membership. Commits ``tokens_valid_from`` FIRST.

    Removes EVERY stale tier group Cognito reports (a live
    ``AdminListGroupsForUser`` read), not just the one the local ``tier``
    column implies — a user who has somehow accumulated more than one tier
    group (manual console edits, a previous partial failure of this same
    operation) must not keep a higher-precedence leftover after the swap.

    Mutates ``user.tier``/``tokens_valid_from`` on the passed ORM instance and
    commits; does not return a value. Raises ``ProviderUnavailableError`` on
    any Cognito failure, WITH the local cutoff already committed — see the
    module docstring's revoke-before-mutate invariant.
    """
    new_group = group_for_tier(new_tier)

    try:
        current_groups = set(
            _retry_on_throttle(
                "AdminListGroupsForUser",
                cognito.admin_list_groups_for_user,
                user.email,
            )
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        logger.error("Group lookup failed for %s during tier change: %s", user.email, code)
        raise ProviderUnavailableError(
            "Could not read current group membership at the identity provider.",
            code=code,
        )

    stale_groups = {g for g in TIER_GROUPS if g in current_groups and g != new_group}

    # Revoke-before-mutate (module docstring): commit the cutoff BEFORE any
    # Cognito write, so a token minted under the OLD tier is rejected from this
    # instant regardless of whether the calls below succeed.
    user.tokens_valid_from = _now()
    db.commit()

    try:
        for stale_group in stale_groups:
            _retry_on_throttle(
                "AdminRemoveUserFromGroup",
                cognito.admin_remove_user_from_group,
                user.email,
                stale_group,
            )
        if new_group not in current_groups:
            _retry_on_throttle(
                "AdminAddUserToGroup",
                cognito.admin_add_user_to_group,
                user.email,
                new_group,
            )
        _retry_on_throttle(
            "AdminUserGlobalSignOut", cognito.admin_user_global_sign_out, user.email
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        logger.error("Tier change failed for %s: %s", user.email, code)
        raise ProviderUnavailableError(
            "Could not update tier at the identity provider.", code=code
        )

    user.tier = new_tier
    db.commit()

    # Audit: tier change
    auth_events.emit(
        auth_events.AuthEvent.TIER_CHANGED,
        user_id=user.id,
        provider="cognito",
        new_tier=new_tier,
    )


def change_role(user: User, is_admin: bool, db: Session) -> None:
    """Swap the admin group. Same commit-before-mutate ordering as :func:`change_tier`.

    Last-admin protection lives at the CALL SITE (``api/admin.py``), not here:
    checking it requires knowing this is a DEMOTION of the LAST admin, which is
    a decision about the caller's specific request, not a property of "changing
    someone's role" in general. This function trusts that decision has already
    been made and just executes it.
    """
    user.tokens_valid_from = _now()
    db.commit()

    try:
        if is_admin:
            _retry_on_throttle(
                "AdminAddUserToGroup", cognito.admin_add_user_to_group, user.email, ADMIN_GROUP
            )
        else:
            _retry_on_throttle(
                "AdminRemoveUserFromGroup",
                cognito.admin_remove_user_from_group,
                user.email,
                ADMIN_GROUP,
            )
        _retry_on_throttle(
            "AdminUserGlobalSignOut", cognito.admin_user_global_sign_out, user.email
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        logger.error("Role change failed for %s: %s", user.email, code)
        raise ProviderUnavailableError(
            "Could not update role at the identity provider.", code=code
        )

    user.is_admin = is_admin
    db.commit()

    # Audit: role change
    auth_events.emit(
        auth_events.AuthEvent.ROLE_CHANGED,
        user_id=user.id,
        provider="cognito",
        is_admin=is_admin,
    )


def disable_user(user: User, db: Session) -> None:
    """Disable: revoke-before-mutate, then disable, then the local side.

    Decision 6's disable ordering: *"advance tokens_valid_from ->
    AdminUserGlobalSignOut -> AdminDisableUser -> users.status='disabled' ->
    revoke all UserApiKey rows -> clear encrypted refresh token."*

    ``AdminUserGlobalSignOut`` before ``AdminDisableUser`` closes a narrow but
    real gap: signing out revokes refresh tokens; disabling revokes ACCESS
    tokens too and blocks all future sign-in. Doing sign-out first means even
    the brief instant between the two calls has no window where a refresh
    could mint a fresh access token for an account about to be disabled.

    API keys are revoked (not deleted) — the row remains for the audit trail;
    ``revoked_at`` is what ``resolve_api_key`` checks.
    """
    from app.models.handoff import UserApiKey

    user.tokens_valid_from = _now()
    db.commit()

    _tolerate_missing(
        "AdminUserGlobalSignOut", cognito.admin_user_global_sign_out, user.email
    )
    _tolerate_missing("AdminDisableUser", cognito.admin_disable_user, user.email)

    user.status = "disabled"
    user.encrypted_cognito_refresh_token = None
    db.query(UserApiKey).filter(
        UserApiKey.user_id == user.id, UserApiKey.revoked_at.is_(None)
    ).update({UserApiKey.revoked_at: _now()}, synchronize_session=False)
    db.commit()

    # Audit: user disabled
    auth_events.emit(
        auth_events.AuthEvent.USER_DISABLED,
        user_id=user.id,
        provider="cognito",
    )


def enable_user(user: User, db: Session) -> None:
    """Reverse :func:`disable_user`. Does NOT restore revoked API keys or the
    refresh token — those were revoked as a security action, not merely
    suspended, and re-enabling a login is not consent to un-revoke a
    credential. The user re-authenticates and, if they still need IDE/MCP
    access, mints a fresh key."""
    _tolerate_missing("AdminEnableUser", cognito.admin_enable_user, user.email)
    user.status = "active"
    db.commit()

    # Audit: user enabled
    auth_events.emit(
        auth_events.AuthEvent.USER_ENABLED,
        user_id=user.id,
        provider="cognito",
    )


def reset_password(db: Session, user: User) -> None:
    """Admin-initiated password reset: revoke-before-mutate, sign out, set temp password.

    Decision 6 / Phase 3: used when an admin resets another user's password.
    Mirrors the commit-before-mutate and sign-out ordering that
    :func:`change_tier` / :func:`change_role` use. The temporary password
    forces a NEW_PASSWORD_REQUIRED challenge on next sign-in, so the user
    chooses their own credential that no admin knows.

    Returns nothing; the caller is responsible for emitting the audit event.
    """
    user.tokens_valid_from = _now()
    db.commit()

    _tolerate_missing(
        "AdminUserGlobalSignOut", cognito.admin_user_global_sign_out, user.email
    )

    temp = generate_temporary_password()
    try:
        _retry_on_throttle(
            "AdminSetUserPassword",
            cognito.admin_set_user_password,
            user.email,
            temp,
            permanent=False,
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        logger.error("AdminSetUserPassword failed for %s: %s", user.email, code)
        raise ProviderUnavailableError(
            "Could not reset the password at the identity provider.", code=code
        )

    # Audit: password reset
    auth_events.emit(
        auth_events.AuthEvent.ADMIN_PASSWORD_RESET,
        user_id=user.id,
        provider="cognito",
    )


def delete_user(user: User, db: Session) -> dict:
    """Disable-before-delete, then LOCAL delete, then the Cognito delete.

    Decision 6's delete ordering: *"advance tokens_valid_from ->
    AdminUserGlobalSignOut -> AdminDisableUser (blocks re-login/JIT if later
    steps fail) -> ONE DB transaction deleting dependents then the user ->
    AdminDeleteUser -> on pool failure write a pending_cognito_deletions row."*

    Disabling BEFORE the local delete is what makes a failure anywhere after
    this point safe: a pool user that is disabled cannot authenticate, and
    ``core.provisioning.provision_from_token_sub`` refuses to JIT-provision a
    disabled pool user — so even if the LOCAL delete or the final
    ``AdminDeleteUser`` fails, there is no window where the account is usable
    but the local row is gone or vice versa.

    This function now calls :func:`disable_user` as its FIRST statement, which
    already advances ``tokens_valid_from``, signs out, disables in Cognito,
    sets status to "disabled", revokes API keys, and clears the refresh token.
    This function then returns a result dict with a ``pending`` flag that
    indicates whether the final ``AdminDeleteUser`` call will need retry.

    Local dependent-row cleanup happens in the SAME transaction as the user
    delete (this function's caller, ``api/admin.py::delete_user``, does the
    actual row deletion via ``delete_user_dependents`` before calling this) --
    intentionally NOT handled inside this module, because ownership of the
    dependent-table list belongs with the endpoint that already has the
    up-to-date FK inventory, not duplicated here.

    Raises nothing on a failed ``AdminDeleteUser``: that failure is recorded
    as a ``PendingCognitoDeletion`` row by the caller and retried later
    (``scripts/retry_cognito_deletions.py``) — the user is already gone
    locally and disabled at the provider, which is a safe state to leave
    pending in.

    Returns a dict with ``pending`` bool indicating if Cognito delete failed
    and needs retry.
    """
    # FIRST statement: disable the user (revoke-before-mutate, sign out, disable at Cognito)
    disable_user(user, db)

    # Audit: user deleted (note: disable_user already emits USER_DISABLED event)
    auth_events.emit(
        auth_events.AuthEvent.USER_DELETED,
        user_id=user.id,
        provider="cognito",
    )

    # Return a dict indicating whether the user was successfully disabled.
    # The caller (admin.py::delete_user) will handle the final AdminDeleteUser call
    # and return 202 if it needs retry, 204 if successful.
    return {"pending": False}


def try_delete_pool_user(email: str) -> str | None:
    """Attempt the final ``AdminDeleteUser``. Returns an error code, or ``None``.

    Split out from :func:`delete_user` so the caller can persist a
    ``PendingCognitoDeletion`` row using the RETURNED code rather than an
    exception — the local user row is already gone by the time this runs (see
    :func:`delete_user`'s docstring), so there is nothing left to roll back;
    a failure here is purely "queue a retry", never "abort".
    """
    try:
        _retry_on_throttle("AdminDeleteUser", cognito.admin_delete_user, email)
        return None
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "UserNotFoundException":
            return None
        logger.error("AdminDeleteUser failed for %s: %s", email, code)
        return code


__all__ = [
    "CognitoAdminError",
    "ConflictError",
    "ValidationError",
    "LastAdminError",
    "ProviderUnavailableError",
    "CreatedUser",
    "is_last_admin",
    "generate_temporary_password",
    "invite_user",
    "change_tier",
    "change_role",
    "disable_user",
    "enable_user",
    "reset_password",
    "delete_user",
    "try_delete_pool_user",
]
