"""Authentication API endpoints for registration, login, and user info."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.dependencies import (
    get_current_user,
    get_user_for_logout,
)
from app.core.security import create_access_token, hash_password, verify_password
from app.models.database import get_db
from app.models.revoked_token import RevokedToken
from app.models.schemas import AuthResponse, LoginRequest, RegisterRequest, UserResponse
from app.models.user import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    """Register a new user account.

    Validates email format and password length (≥8 chars) via Pydantic schema.
    Returns 409 if email is already registered.
    On success, creates user with hashed password and returns JWT + user info.
    """
    # Check for duplicate email
    existing_user = db.query(User).filter(User.email == request.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Hash password and create user
    hashed = hash_password(request.password)
    user = User(email=request.email, password_hash=hashed)
    db.add(user)
    db.commit()
    db.refresh(user)

    # Generate JWT token
    token = create_access_token(user.id)

    return AuthResponse(
        token=token,
        user=UserResponse(id=user.id, email=user.email),
    )


@router.post("/login", response_model=AuthResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate a user and return a JWT token.

    Returns a generic 401 on failure — does not distinguish between
    wrong email and wrong password.
    """
    # Look up user by email
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Verify password against stored bcrypt hash
    if not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Generate JWT token with 24h expiry
    token = create_access_token(user.id)

    return AuthResponse(
        token=token,
        user=UserResponse(id=user.id, email=user.email),
    )


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Return the current authenticated user's info from JWT."""
    return UserResponse(id=current_user.id, email=current_user.email)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    auth: tuple[User, dict] = Depends(get_user_for_logout),
    db: Session = Depends(get_db),
):
    """Revoke the JWT used to make this request.

    Inserts a row in ``revoked_tokens`` keyed by the JWT's ``jti`` so any
    further request presenting the same token is rejected by ``get_current_user``.

    Idempotent: hitting this endpoint with an already-revoked token still
    returns 204 — the client wanted to log out, the token is revoked,
    desired state is satisfied. Uses :func:`get_user_for_logout` (rather
    than the standard ``get_current_user``) precisely so an already-revoked
    JWT doesn't 401 on its own /logout call.
    """
    user, payload = auth
    jti = payload.get("jti")
    exp = payload.get("exp")

    # Defence in depth: if the token somehow has no jti (legacy token issued
    # before this change), there's nothing we can revoke at the per-token
    # level. The blanket-revoke on password change still protects the user;
    # treat this as a successful no-op.
    if not jti or not exp:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # ``exp`` comes back from python-jose as an int (seconds since epoch).
    if isinstance(exp, (int, float)):
        expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
    elif isinstance(exp, datetime):
        expires_at = exp if exp.tzinfo else exp.replace(tzinfo=timezone.utc)
    else:
        # Unknown shape — bail out as a no-op rather than 500.
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    revocation = RevokedToken(
        jti=jti,
        user_id=user.id,
        expires_at=expires_at,
    )
    db.add(revocation)
    try:
        db.commit()
    except IntegrityError:
        # Already revoked — idempotent path. Roll back the failed insert and
        # report success: the caller's intent (this token must be revoked)
        # is satisfied.
        db.rollback()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


class ChangePasswordRequest(BaseModel):
    """Request body for changing password."""
    current_password: str
    new_password: str


@router.post("/change-password", status_code=status.HTTP_200_OK)
def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change the authenticated user's password.

    Requires the current password for verification. New password must be at
    least 8 characters. Stamping ``password_changed_at`` blanket-revokes every
    JWT this user previously had outstanding (see ``get_current_user``) without
    needing to enumerate them.
    """
    # Verify current password
    if not verify_password(request.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )

    # Validate new password length
    if len(request.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 8 characters",
        )

    # Update password and stamp the rotation time. Any JWT issued before this
    # instant will be rejected by get_current_user as a blanket revocation.
    current_user.password_hash = hash_password(request.new_password)
    current_user.password_changed_at = datetime.now(timezone.utc)
    db.commit()

    return {"message": "Password changed successfully"}
