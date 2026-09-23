"""Admin API endpoints — user management, tier control, and lifecycle.

Only accessible to users with is_admin=True. All endpoints require a valid
bearer credential from an admin account.

Rewritten for Phase 3 of the Cognito-only auth migration
(``.kiro/specs/login/prompt.md``, Decision 6). Every Cognito Admin* SEQUENCE
now lives in ``core/cognito_admin.py`` — this module is a thin FastAPI-shaped
caller: parse the request, resolve the target row, delegate the ordering
decision, shape the response, emit the audit event. See that module's
docstring for the ordering invariants (revoke-before-mutate,
disable-before-delete, idempotent ``UserNotFoundException``) every mutation
here relies on but does not re-implement.

User creation is now INVITATION-ONLY: ``POST /users`` no longer accepts a
password at all (the prior flow set a PERMANENT password an admin then knew —
see ``MERGE_NOTES.md`` §4). ``POST /users/{id}/disable`` and
``POST /users/{id}/enable`` are new (Decision 6's disable/enable lifecycle).
Every privilege-reducing or account-ending action that could remove the last
administrator now checks ``cognito_admin.is_last_admin`` first.
"""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core import auth_events, cognito_admin
from app.core.auth_events import AuthEvent
from app.core.email_identity import canonicalize_email
from app.core.cognito_admin import (
    ConflictError,
    LastAdminError,
    ProviderUnavailableError,
    ValidationError,
)
from app.core.dependencies import get_current_user_with_payload
from app.core.entitlements import TIER_PIPELINES
from app.core.identity import (
    AdminMfaRequired,
    Principal,
    effective_is_admin,
    enforce_admin_mfa,
)
from app.core.user_deletion import delete_user_dependents
from app.models.database import get_db
from app.models.schemas import CanonicalEmail
from app.models.pending_cognito_deletion import PendingCognitoDeletion
from app.models.user import User

router = APIRouter(prefix="/api/admin", tags=["admin"])
logger = logging.getLogger("app.api.admin")


def _raise_for(exc: Exception) -> None:
    """Map a ``cognito_admin`` typed error to the matching ``HTTPException``.

    ONE mapping, used by every route below, so a new failure mode added to
    ``cognito_admin.py`` needs its status code decided once here rather than
    at each of the (currently six) call sites that could raise it. Any
    exception that is not one of ``cognito_admin``'s own types is re-raised
    UNCHANGED -- this function only translates known failure modes, it never
    swallows or reshapes a genuine bug into a misleading 503.
    """
    if isinstance(exc, LastAdminError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, ConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, ValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, ProviderUnavailableError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        )
    raise exc


# ─── Guards ───────────────────────────────────────────────────────────────────


def require_admin(
    auth: tuple[User, dict] = Depends(get_current_user_with_payload),
) -> User:
    """Dependency that raises 403 if the caller is not an admin.

    Also applies the admin-MFA gate (Phase 6 item 1). The gate is a no-op
    unless ``ADMIN_MFA_REQUIRED`` is enabled.

    Reads ``cognito:groups`` off the verified token (authoritative), not the
    advisory ``is_admin`` DB column -- see core/identity.py's precedence
    rule.
    """
    current_user, payload = auth

    principal = Principal(
        provider="cognito",
        sub=payload.get("sub", current_user.id),
        jti=payload.get("jti"),
        iat=payload.get("iat"),
        groups=payload.get("groups", []),
    )

    if not effective_is_admin(current_user, principal):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )

    try:
        enforce_admin_mfa(current_user, principal)
    except AdminMfaRequired as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            # Machine-readable code so the frontend can route to enrolment
            # instead of rendering a dead end: a bare 403 is indistinguishable
            # from "you are not an admin", which has no remedy, whereas this one
            # does and the server names the path to it.
            detail={
                "code": "admin_mfa_required",
                "enroll_path": "/api/auth/mfa/totp/associate",
            },
        ) from exc

    return current_user


# ─── Schemas ──────────────────────────────────────────────────────────────────


class AdminUserResponse(BaseModel):
    id: str
    email: str
    tier: str
    is_admin: bool
    # Phase 5 (frontend) addition: exposes disable/enable state so the admin
    # UI can render it and gate its own disable/enable button on it. Every
    # existing caller of _to_response() already has this column loaded on
    # the ORM `User` it was given, so this is response-shape-only -- no new
    # query, no new endpoint.
    status: str
    created_at: datetime
    workflow_run_count: int = 0

    model_config = {"from_attributes": True}


class UpdateTierRequest(BaseModel):
    """Body for ``PATCH /users/{id}/tier``. ``extra=forbid`` (Phase 3 item 8):
    this endpoint is the ONLY sanctioned way to change tier, so a client that
    also POSTs ``is_admin`` here — hoping a looser handler mixes the two
    concerns — gets a 422, not a mass-assignment foothold."""

    model_config = {"extra": "forbid"}

    tier: str


class UpdateRoleRequest(BaseModel):
    """Body for ``PATCH /users/{id}/role``. ``extra=forbid`` — the mirror of
    ``UpdateTierRequest``'s note: this is the only sanctioned way to change
    role, and role/tier are deliberately two separate endpoints (Decision 6),
    each accepting only its own field."""

    model_config = {"extra": "forbid"}

    is_admin: bool


class CreateUserRequest(BaseModel):
    """Body for admin-driven user creation.

    NO PASSWORD FIELD (Phase 3, Decision 6). The prior schema carried
    ``password: str`` and the handler set it as a PERMANENT Cognito password —
    meaning an admin always knew a live credential for someone else's account
    (``MERGE_NOTES.md`` §4). Creation is now invitation-only:
    ``core.cognito_admin.invite_user`` calls ``AdminCreateUser`` with
    ``DesiredDeliveryMediums=[EMAIL]`` and a Cognito-generated TEMPORARY
    password that only ever reaches the recipient's inbox. Removing the field
    from the schema — not just from the handler's use of it — is deliberate:
    a client that still POSTs a ``password`` gets a 422 from Pydantic's extra-
    field rejection, not a silently-ignored value, so no caller can believe
    they set a password that was never actually used (mass-assignment
    hardening, Phase 3 item 8).
    """

    model_config = {"extra": "forbid"}

    email: CanonicalEmail
    tier: str = "basic"
    is_admin: bool = False


class ResetPasswordRequest(BaseModel):
    """Body for an admin-driven password reset.

    This endpoint issues a TEMPORARY password, forcing the user through the
    NEW_PASSWORD_REQUIRED challenge on next sign-in so they choose their own
    credential that no admin knows. No password is supplied by the admin.
    """

    model_config = ConfigDict(extra="forbid")


def _run_count(db: Session, user_id: str) -> int:
    from app.models.workflow import WorkflowRun
    from sqlalchemy import func

    return (
        db.query(func.count(WorkflowRun.id))
        .filter(WorkflowRun.user_id == user_id)
        .scalar()
        or 0
    )


def _to_response(user: User, db: Session) -> AdminUserResponse:
    return AdminUserResponse(
        id=user.id,
        email=user.email,
        tier=user.tier,
        is_admin=user.is_admin,
        status=user.status,
        created_at=user.created_at,
        workflow_run_count=_run_count(db, user.id),
    )


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/users", response_model=list[AdminUserResponse])
def list_users(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List all users with their tier and run counts.

    Tier/role come from the local projection (refreshed on every login and
    every admin write below) -- migration plan §5.4 point 1: sourcing this
    from live AdminListGroupsForUser calls would mean N AWS round-trips per
    page render.
    """
    from app.models.workflow import WorkflowRun
    from sqlalchemy import func

    run_counts = (
        db.query(WorkflowRun.user_id, func.count(WorkflowRun.id).label("cnt"))
        .group_by(WorkflowRun.user_id)
        .all()
    )
    count_map = {row.user_id: row.cnt for row in run_counts}

    users = db.query(User).order_by(User.created_at.desc()).all()
    return [
        AdminUserResponse(
            id=u.id,
            email=u.email,
            tier=u.tier,
            is_admin=u.is_admin,
            status=u.status,
            created_at=u.created_at,
            workflow_run_count=count_map.get(u.id, 0),
        )
        for u in users
    ]


@router.patch("/users/{user_id}/tier", response_model=AdminUserResponse)
def update_user_tier(
    user_id: str,
    request: UpdateTierRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Change a user's tier.

    Self-action guard (Phase 3): an admin cannot change their OWN tier. This
    was a real gap — ``update_user_role`` and ``delete_user`` both already
    blocked acting on ``admin.id``, but ``update_user_tier`` did not (recorded
    in ``MERGE_NOTES.md`` §11, confirmed against the clean baseline as a
    pre-existing bug rather than a Phase 2 regression). Tier is not
    privilege-equivalent to role, but an admin downgrading their own tier is
    still a self-action a second admin should confirm rather than one person
    doing to themselves without review — the same rationale
    ``update_user_role`` already documents.

    The actual group-swap ordering (live ``AdminListGroupsForUser`` read,
    stale-group sweep, commit-before-mutate) lives in
    ``core.cognito_admin.change_tier``; see that function's docstring.
    """
    # Self-action policy (Requirement 5.9) — mirrors the self-demote guard on
    # `update_user_role` and the self-delete guard on `delete_user`. An admin
    # changing their OWN tier is a privilege mutation with no second pair of
    # eyes: the same account authorises the change and receives it, and a
    # downgrade also strips the entitlements the admin may need to undo it.
    # Ask another admin, as the two sibling endpoints already require.
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot change your own tier. Ask another administrator.",
        )

    valid_tiers = set(TIER_PIPELINES.keys())
    if request.tier not in valid_tiers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid tier. Must be one of: {', '.join(sorted(valid_tiers))}",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    try:
        cognito_admin.change_tier(user, request.tier, db)
    except Exception as exc:  # noqa: BLE001 - re-raised as HTTPException below
        _raise_for(exc)

    db.refresh(user)

    auth_events.emit(
        AuthEvent.TIER_CHANGED,
        user_id=user.id,
        provider="cognito",
        actor_id=admin.id,
        new_tier=request.tier,
    )
    # ISS-471: report the tier THIS request committed, not the post-`db.refresh`
    # re-read of the row. A concurrent admin write landing between our own
    # `commit()` and `refresh()` would otherwise be echoed back as ours — a
    # false-success 200 on a privilege field. Same shape as FIX-382 in
    # `settings.py`; `request.tier` is the value already validated against
    # `valid_tiers` above, so nothing unvalidated can be echoed.
    return _to_response(user, db).model_copy(update={"tier": request.tier})


@router.patch("/users/{user_id}/role", response_model=AdminUserResponse)
def update_user_role(
    user_id: str,
    request: UpdateRoleRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Set a user's admin flag. First real settable-role endpoint (migration
    plan §7 Phase 3) -- previously `is_admin` was settable only at creation.

    Admin cannot demote themselves (mirrors the existing self-delete guard) --
    a lone admin locking themselves out with no other admin to fix it is a
    worse failure mode than the inconvenience of asking another admin.

    Last-admin protection (Phase 3, Decision 6): demoting the LAST remaining
    member of the admin group is refused with 409, even when it is not a
    self-action -- two admins could otherwise demote each other in sequence
    and leave zero. Checked with a LIVE ``ListUsersInGroup`` read
    (``cognito_admin.is_last_admin``), not the local ``is_admin`` projection,
    because the projection can under-count relative to the pool's real
    membership.
    """
    if user_id == admin.id and not request.is_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot remove your own admin access.",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    if not request.is_admin:
        # Always check via Cognito (is_last_admin), never rely on DB projection.
        # T6: Unconditional check for demotion; is_last_admin returns False if user
        # is not in the admin group (catching drift where user.is_admin=True but not in Cognito).
        try:
            is_last = cognito_admin.is_last_admin(user)
        except ProviderUnavailableError as exc:
            logger.error(
                "Admin-group membership check failed for %s: %s", user.email, exc
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not verify admin-group membership at the identity provider.",
            ) from exc
        if is_last:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This is the last remaining administrator. Promote "
                    "another user to admin before removing this one."
                ),
            )

    try:
        cognito_admin.change_role(user, request.is_admin, db)
    except Exception as exc:  # noqa: BLE001 - re-raised as HTTPException below
        _raise_for(exc)

    db.refresh(user)

    # Privilege changes are the highest-value audit events in the system:
    # `actor_id` records WHO granted/revoked, not just who was affected.
    auth_events.emit(
        AuthEvent.ROLE_CHANGED,
        user_id=user.id,
        provider="cognito",
        actor_id=admin.id,
        is_admin=request.is_admin,
    )
    # ISS-471: as in `update_user_tier` above — report the `is_admin` flag THIS
    # request committed, never the post-`db.refresh` re-read that a concurrent
    # role write could have replaced.
    return _to_response(user, db).model_copy(update={"is_admin": request.is_admin})


@router.post(
    "/users", response_model=AdminUserResponse, status_code=status.HTTP_201_CREATED
)
def create_user(
    request: CreateUserRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Create a new user account (admin only), by INVITATION.

    ``core.cognito_admin.invite_user`` calls ``AdminCreateUser`` with
    ``DesiredDeliveryMediums=[EMAIL]`` -- Cognito generates a TEMPORARY
    password and emails it directly to the new account; this backend never
    sees it and the admin never learns it (Phase 3, Decision 6; fixes the gap
    ``MERGE_NOTES.md`` §4 recorded). The recipient answers
    NEW_PASSWORD_REQUIRED on first sign-in.

    THEN the local row (with the ``cognito_sub`` the create call returned). On
    a local-insert failure, the pool user is deleted to avoid an orphan
    (compensating ``AdminDeleteUser``) -- unchanged from before.
    """
    email = canonicalize_email(request.email)
    existing = db.query(User).filter(func.lower(User.email) == email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists.",
        )

    valid_tiers = set(TIER_PIPELINES.keys())
    if request.tier not in valid_tiers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid tier. Must be one of: {', '.join(sorted(valid_tiers))}",
        )

    try:
        created = cognito_admin.invite_user(
            email, tier=request.tier, is_admin=request.is_admin
        )
    except Exception as exc:  # noqa: BLE001 - re-raised as HTTPException below
        _raise_for(exc)

    new_user = User(
        id=str(uuid.uuid4()),
        email=created.email,
        cognito_sub=created.cognito_sub,
        tier=created.tier,
        is_admin=created.is_admin,
        roles_synced_at=datetime.now(timezone.utc),
    )
    db.add(new_user)
    try:
        db.commit()
    except Exception:
        db.rollback()
        # Compensating delete: don't leave an orphaned pool user with no
        # local row (migration plan R7).
        try:
            cognito_admin.try_delete_pool_user(email)
        except Exception:  # noqa: BLE001 - best-effort cleanup
            logger.error("Failed to compensate-delete orphaned Cognito user %s", email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist the new user locally; the identity-provider account was rolled back.",
        )
    db.refresh(new_user)

    auth_events.emit(
        AuthEvent.USER_CREATED,
        user_id=new_user.id,
        provider="cognito",
        actor_id=admin.id,
        tier=request.tier,
        is_admin=request.is_admin,
    )
    return _to_response(new_user, db)


@router.post("/users/{user_id}/reset-password", status_code=status.HTTP_200_OK)
def reset_user_password(
    user_id: str,
    request: ResetPasswordRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Set a temporary password for another user (admin only).

    This is the ONLY reset path when the pool uses email MFA. AWS forbids email
    being both a second factor and the account-recovery channel, so such a pool
    is created with ``account_recovery_setting = admin_only`` and
    ``/api/auth/forgot-password`` correctly refuses to pretend otherwise. Without
    this endpoint, a forgotten password in that configuration would need a
    console operator or a CLI runbook.

    Issues a TEMPORARY password (internally generated, never exposed to the admin),
    forcing the user through the NEW_PASSWORD_REQUIRED challenge on next sign-in
    so they choose their own credential the admin never knew. Mirrors the
    self-service reset's revocation: stamps ``tokens_valid_from`` so every access
    token issued before now is rejected on its next request.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    try:
        cognito_admin.reset_password(db, user)
    except Exception as exc:  # noqa: BLE001 - re-raised as HTTPException below
        _raise_for(exc)

    db.refresh(user)

    # actor_id records WHO performed the reset. An admin resetting another
    # user's credential is a privilege-adjacent action and belongs in the audit
    # trail with the same weight as a role change.
    auth_events.emit(
        AuthEvent.ADMIN_PASSWORD_RESET,
        user_id=user.id,
        provider="cognito",
        actor_id=admin.id,
    )

    return {"status": "temporary_password_set"}


@router.post("/users/{user_id}/disable", response_model=AdminUserResponse)
def disable_user(
    user_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Disable a user account (Phase 3, Decision 6 -- new).

    Reversible via ``/enable``, unlike delete. Revokes the account's API keys
    and stored refresh token, disables sign-in at Cognito, and globally signs
    out every outstanding session -- see ``core.cognito_admin.disable_user``
    for the exact ordering and why it matters.

    Self-action and last-admin protection mirror ``update_user_role``: an
    admin cannot disable themselves, and disabling the last remaining admin
    is refused.
    """
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot disable your own account.",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    try:
        is_last = cognito_admin.is_last_admin(user)
    except ProviderUnavailableError as exc:
        logger.error("Admin-group membership check failed for %s: %s", user.email, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not verify admin-group membership at the identity provider.",
        ) from exc
    if is_last:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This is the last remaining administrator. Promote "
                "another user to admin before disabling this one."
            ),
        )

    if user.status == "disabled":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="User is already disabled."
        )

    cognito_admin.disable_user(user, db)
    db.refresh(user)

    auth_events.emit(
        AuthEvent.USER_DISABLED,
        user_id=user.id,
        provider="cognito",
        actor_id=admin.id,
    )
    return _to_response(user, db)


@router.post("/users/{user_id}/enable", response_model=AdminUserResponse)
def enable_user(
    user_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Re-enable a disabled user account. Reverses ``/disable``.

    Does NOT restore API keys or the refresh token that were revoked on
    disable (``cognito_admin.enable_user``'s docstring explains why) -- the
    user re-authenticates through the normal login flow.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    if user.status != "disabled":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="User is not disabled."
        )

    try:
        cognito_admin.enable_user(user, db)
    except Exception as exc:  # noqa: BLE001 - re-raised as HTTPException below
        _raise_for(exc)
    db.refresh(user)

    auth_events.emit(
        AuthEvent.USER_ENABLED,
        user_id=user.id,
        provider="cognito",
        actor_id=admin.id,
    )
    return _to_response(user, db)


@router.delete(
    "/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
def delete_user(
    user_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Delete a user. Admin cannot delete themselves.

    Ordering (Phase 3, Decision 6 -- see ``core.cognito_admin.delete_user``'s
    docstring for the full rationale):

      1. Last-admin check (live ``ListUsersInGroup`` read) if the target is an
         admin -- refused with 409 before anything is touched.
      2. ``AdminUserGlobalSignOut`` + ``AdminDisableUser`` at Cognito, both
         tolerating ``UserNotFoundException`` (the pool user may already be
         absent from a prior partial run).
      3. ONE local transaction: delete every dependent row this user owns
         (``delete_user_dependents`` -- nine run-fanout tables, saved
         workflows, custom agents, chat history, in dependency order), then
         the ``User`` row itself. Per-table counts land in the audit event.
      4. ``AdminDeleteUser`` LAST. On failure, a ``PendingCognitoDeletion`` row
         records it for ``app/scripts/retry_cognito_deletions.py`` -- safe to
         defer because the account is already disabled and gone locally.

    Returns:
      - 202 Accepted if the user was disabled and deleted locally but Cognito
        pool deletion is pending retry.
      - 204 No Content if fully successful.
    """
    from fastapi.responses import JSONResponse

    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete your own account.",
        )
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    try:
        is_last = cognito_admin.is_last_admin(user)
    except ProviderUnavailableError as exc:
        logger.error("Admin-group membership check failed for %s: %s", user.email, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not verify admin-group membership at the identity provider.",
        ) from exc
    if is_last:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This is the last remaining administrator. Promote "
                "another user to admin before deleting this one."
            ),
        )

    # Step 1-2: Disable the user (sign out, disable at Cognito, update local status)
    cognito_admin.delete_user(user, db)

    # Step 3: one local transaction -- dependents, then the row itself.
    deleted_id = user.id
    deleted_email = user.email
    deleted_cognito_sub = user.cognito_sub
    dependent_counts = delete_user_dependents(db, user_id)
    db.delete(user)
    db.commit()

    # Step 4: the final Cognito delete, LAST and OUTSIDE the local transaction
    # -- the local state is already committed and correct either way.
    failure_code = cognito_admin.try_delete_pool_user(deleted_email)
    if failure_code is not None:
        pending = PendingCognitoDeletion(
            user_id_snapshot=deleted_id,
            cognito_sub=deleted_cognito_sub,
            email_hash=auth_events.hash_email(deleted_email),
            attempts=1,
            last_error=failure_code,
        )
        db.add(pending)
        db.commit()
        logger.warning(
            "AdminDeleteUser failed for deleted local user %s; queued for retry "
            "(pending_cognito_deletions id=%s)",
            deleted_id,
            pending.id,
        )

    auth_events.emit(
        AuthEvent.USER_DELETED,
        user_id=deleted_id,
        provider="cognito",
        actor_id=admin.id,
        dependent_counts=dependent_counts,
        pool_delete_pending=failure_code is not None,
    )

    # Return 202 if Cognito deletion is pending retry; 204 if fully successful
    if failure_code is not None:
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"pending_cognito_deletion": True},
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
