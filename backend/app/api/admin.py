"""Admin API endpoints — user management and tier control.

Only accessible to users with is_admin=True. All endpoints require
a valid bearer credential from an admin account.

Rewired for the Cognito Authentication & Authorization Migration
(``.planning/COGNITO-MIGRATION-PLAN.md`` §7 Phase 3): user create/delete now
provision/deprovision the Cognito pool user in lockstep with the local row
(compensating delete on a failed local insert); tier changes swap group
membership + stamp ``tokens_valid_from`` + call ``AdminUserGlobalSignOut``
(so the change takes effect on the user's very next request, not after the
access-token TTL expires); a new ``PATCH /users/{id}/role`` endpoint is the
first real settable-role surface, now that role lives in a Cognito group
rather than only being settable at creation time.
"""

import logging
import uuid
from datetime import datetime, timezone

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core import auth_events, cognito
from app.core.auth_events import AuthEvent
from app.core.dependencies import get_current_user_with_payload
from app.core.entitlements import ADMIN_GROUP, TIER_PIPELINES
from app.core.identity import (
    AdminMfaRequired,
    Principal,
    effective_is_admin,
    enforce_admin_mfa,
)
from app.models.database import get_db
from app.models.user import User

router = APIRouter(prefix="/api/admin", tags=["admin"])
logger = logging.getLogger("app.api.admin")

# Maps a tier name to its fixed Cognito group name (COGNITO-MIGRATION-PLAN
# §5.1). Kept local to this module (not entitlements.py) because it is only
# ever needed on the admin WRITE path — entitlements.py's own
# resolve_tier_from_groups is the READ-path inverse and lives with the other
# read-path group logic.
_TIER_TO_GROUP = {
    "basic": "flowin-tier-basic",
    "pro": "flowin-tier-pro",
    "enterprise": "flowin-tier-enterprise",
}


# ─── Guards ───────────────────────────────────────────────────────────────────

def require_admin(auth: tuple[User, dict] = Depends(get_current_user_with_payload)) -> User:
    """Dependency that raises 403 if the caller is not an admin.

    Also applies the admin-MFA gate (Phase 6 item 1). The gate is a no-op unless
    ``ADMIN_MFA_REQUIRED`` is enabled, and is skipped for the break-glass local
    admin by construction -- see ``core.identity.enforce_admin_mfa`` for why
    that exemption exists and why the gate fails open on a Cognito lookup error.

    NOTE: reads the raw ``is_admin`` DB column, which is the ADVISORY
    projection for a Cognito-authenticated caller (core/identity.py's
    precedence rule). This is acceptable here specifically because the
    projection is refreshed on every login (api/auth.py
    ``_refresh_role_projection``) and on every role/tier admin write below —
    it is never more than one login cycle stale, and a demoted admin's
    outstanding token is ALSO rejected by ``tokens_valid_from`` well before
    this guard would matter. A stricter per-request ``cognito:groups`` read
    would need the raw token payload threaded through every admin route;
    deferred as a Phase 6 hardening item if this staleness window proves
    too wide in practice.
    """
    current_user, payload = auth

    principal = Principal(
        provider="cognito" if current_user.auth_provider == "cognito" else "local",
        sub=payload.get("sub", current_user.id),
        jti=payload.get("jti"),
        iat=payload.get("iat"),
        groups=payload.get("groups", []),
    )

    # On the Cognito path this reads cognito:groups (authoritative) rather than
    # the advisory DB column -- closing the staleness window the previous
    # implementation documented as an accepted tradeoff.
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
            # instead of rendering a dead end.
            detail={"code": "admin_mfa_required", "message": str(exc)},
        )

    return current_user


# ─── Schemas ──────────────────────────────────────────────────────────────────

class AdminUserResponse(BaseModel):
    id: str
    email: str
    tier: str
    is_admin: bool
    created_at: datetime
    workflow_run_count: int = 0
    auth_provider: str = "local"

    model_config = {"from_attributes": True}


class UpdateTierRequest(BaseModel):
    tier: str


class UpdateRoleRequest(BaseModel):
    is_admin: bool


class CreateUserRequest(BaseModel):
    email: str
    password: str
    tier: str = "basic"
    is_admin: bool = False


class ResetPasswordRequest(BaseModel):
    """Body for an admin-driven password reset.

    ``permanent`` defaults to False so the reset issues a TEMPORARY password and
    the user is forced to choose their own at next sign-in. Defaulting the other
    way would leave the admin knowing a working credential for someone else's
    account, which is a needless standing risk when the safe option costs the
    user one extra prompt.
    """

    new_password: str
    permanent: bool = False


def _run_count(db: Session, user_id: str) -> int:
    from app.models.workflow import WorkflowRun
    from sqlalchemy import func

    return db.query(func.count(WorkflowRun.id)).filter(WorkflowRun.user_id == user_id).scalar() or 0


def _to_response(user: User, db: Session) -> AdminUserResponse:
    return AdminUserResponse(
        id=user.id,
        email=user.email,
        tier=user.tier,
        is_admin=user.is_admin,
        created_at=user.created_at,
        workflow_run_count=_run_count(db, user.id),
        auth_provider=user.auth_provider,
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
            created_at=u.created_at,
            workflow_run_count=count_map.get(u.id, 0),
            auth_provider=u.auth_provider,
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

    Cognito path: swap group membership (remove old tier group, add the new
    one), stamp ``tokens_valid_from``, and ``AdminUserGlobalSignOut`` -- the
    combination that makes the change effective on the user's VERY NEXT
    request rather than waiting out the access-token TTL (migration plan
    §5.3). Local/break-glass path: unchanged -- just the DB column, which IS
    authoritative for that account.
    """
    valid_tiers = set(TIER_PIPELINES.keys())
    if request.tier not in valid_tiers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid tier. Must be one of: {', '.join(sorted(valid_tiers))}",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.auth_provider == "cognito":
        old_group = _TIER_TO_GROUP.get(user.tier)
        new_group = _TIER_TO_GROUP[request.tier]
        try:
            if old_group and old_group != new_group:
                cognito.admin_remove_user_from_group(user.email, old_group)
            cognito.admin_add_user_to_group(user.email, new_group)
            cognito.admin_user_global_sign_out(user.email)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            logger.error("Cognito tier update failed for %s: %s", user.email, code)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not update tier at the identity provider.",
            )
        user.tokens_valid_from = datetime.now(timezone.utc)

    user.tier = request.tier
    db.commit()
    db.refresh(user)

    auth_events.emit(
        AuthEvent.TIER_CHANGED,
        user_id=user.id,
        provider=user.auth_provider,
        actor_id=admin.id,
        new_tier=request.tier,
    )
    return _to_response(user, db)


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
    """
    if user_id == admin.id and not request.is_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot remove your own admin access.",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.auth_provider == "cognito":
        try:
            if request.is_admin:
                cognito.admin_add_user_to_group(user.email, ADMIN_GROUP)
            else:
                cognito.admin_remove_user_from_group(user.email, ADMIN_GROUP)
            cognito.admin_user_global_sign_out(user.email)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            logger.error("Cognito role update failed for %s: %s", user.email, code)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not update role at the identity provider.",
            )
        user.tokens_valid_from = datetime.now(timezone.utc)

    user.is_admin = request.is_admin
    db.commit()
    db.refresh(user)

    # Privilege changes are the highest-value audit events in the system:
    # `actor_id` records WHO granted/revoked, not just who was affected.
    auth_events.emit(
        AuthEvent.ROLE_CHANGED,
        user_id=user.id,
        provider=user.auth_provider,
        actor_id=admin.id,
        is_admin=request.is_admin,
    )
    return _to_response(user, db)


@router.post("/users", response_model=AdminUserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    request: CreateUserRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Create a new user account (admin only).

    Cognito path: ``AdminCreateUser`` + ``AdminSetUserPassword`` (permanent,
    so the account is immediately usable without a forced first-login
    challenge) + ``AdminAddUserToGroup`` for the tier and, if requested, the
    admins group -- THEN the local row (with ``cognito_sub`` from the create
    response). On a local-insert failure, the pool user is deleted to avoid
    an orphan (migration plan §7 Phase 3 "compensating AdminDeleteUser").
    Local/break-glass creation (``auth_provider not configured for Cognito``)
    is unchanged.
    """
    existing = db.query(User).filter(User.email == request.email).first()
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

    if len(request.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters.",
        )

    from app.core.config import settings

    if settings.AUTH_PROVIDER.lower() != "cognito":
        from app.core.security import hash_password

        new_user = User(
            id=str(uuid.uuid4()),
            email=request.email,
            password_hash=hash_password(request.password),
            tier=request.tier,
            is_admin=request.is_admin,
            auth_provider="local",
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return _to_response(new_user, db)

    # Cognito path.
    try:
        create_resp = cognito.admin_create_user(request.email)
        cognito.admin_set_user_password(request.email, request.password, permanent=True)
        cognito.admin_add_user_to_group(request.email, _TIER_TO_GROUP[request.tier])
        if request.is_admin:
            cognito.admin_add_user_to_group(request.email, ADMIN_GROUP)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "UsernameExistsException":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists at the identity provider.",
            )
        if code == "InvalidPasswordException":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password does not meet the password policy.",
            )
        logger.error("Cognito AdminCreateUser flow failed for %s: %s", request.email, code)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not create the user at the identity provider.",
        )

    cognito_sub = next(
        (attr["Value"] for attr in create_resp["User"]["Attributes"] if attr["Name"] == "sub"),
        None,
    )

    new_user = User(
        id=str(uuid.uuid4()),
        email=request.email,
        password_hash=None,
        cognito_sub=cognito_sub,
        auth_provider="cognito",
        tier=request.tier,
        is_admin=request.is_admin,
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
            cognito.admin_delete_user(request.email)
        except Exception:  # noqa: BLE001 - best-effort cleanup
            logger.error("Failed to compensate-delete orphaned Cognito user %s", request.email)
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
    """Set a new password for another user (admin only).

    This is the ONLY reset path when the pool uses email MFA. AWS forbids email
    being both a second factor and the account-recovery channel, so such a pool
    is created with ``account_recovery_setting = admin_only`` and
    ``/api/auth/forgot-password`` correctly refuses to pretend otherwise. Without
    this endpoint, a forgotten password in that configuration would need a
    console operator or a CLI runbook.

    Uses ``AdminSetUserPassword``. ``permanent=False`` (the default) issues a
    TEMPORARY password, so the user is forced through the NEW_PASSWORD_REQUIRED
    challenge on next sign-in and chooses something the admin never knew -- an
    admin who sets a permanent password knows a live credential for an account
    that is not theirs. ``permanent=True`` remains available for the case where
    an admin is provisioning on someone's behalf, but it is opt-in.

    Mirrors the self-service reset's revocation: stamps ``tokens_valid_from`` so
    every access token issued before now is rejected on its next request, and
    clears the stored refresh token. A reset that leaves an attacker's session
    alive defeats the point of resetting.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if len(request.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters.",
        )

    if user.auth_provider != "cognito":
        # The break-glass account is administered out-of-band from a secret
        # store, by design (plan §5.6). Letting it be reset through the ordinary
        # admin API would put the one credential that must survive a Cognito
        # outage back inside the system that outage would take down.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This account's password is managed outside the application and "
                "cannot be reset here."
            ),
        )

    try:
        cognito.admin_set_user_password(
            user.email, request.new_password, permanent=request.permanent
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "InvalidPasswordException":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password does not meet the password policy.",
            )
        if code == "UserNotFoundException":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found at the identity provider.",
            )
        logger.error("Cognito AdminSetUserPassword failed for %s: %s", user.email, code)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not reset the password at the identity provider.",
        )

    now = datetime.now(timezone.utc)
    user.password_changed_at = now
    user.tokens_valid_from = now
    user.encrypted_cognito_refresh_token = None
    db.commit()

    # actor_id records WHO performed the reset. An admin resetting another
    # user's credential is a privilege-adjacent action and belongs in the audit
    # trail with the same weight as a role change.
    auth_events.emit(
        AuthEvent.ADMIN_PASSWORD_RESET,
        user_id=user.id,
        provider="cognito",
        actor_id=admin.id,
        permanent=request.permanent,
    )

    return {
        "message": (
            "Password reset. The user can sign in with it immediately."
            if request.permanent
            else "Password reset. The user must choose a new password at next sign-in."
        ),
        "requires_new_password_at_next_login": not request.permanent,
    }


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_user(
    user_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Delete a user. Admin cannot delete themselves.

    Cognito path: ``AdminDeleteUser`` first, tolerating
    ``UserNotFoundException`` (the pool user may already be absent -- an
    inconsistent-but-recoverable prior state, not a reason to block the
    local delete); then the local row.
    """
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete your own account.",
        )
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.auth_provider == "cognito":
        try:
            cognito.admin_delete_user(user.email)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code != "UserNotFoundException":
                logger.error("Cognito AdminDeleteUser failed for %s: %s", user.email, code)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Could not delete the user at the identity provider.",
                )

    deleted_id, deleted_provider = user.id, user.auth_provider
    db.delete(user)
    db.commit()
    auth_events.emit(
        AuthEvent.USER_DELETED,
        user_id=deleted_id,
        provider=deleted_provider,
        actor_id=admin.id,
    )
    return None
