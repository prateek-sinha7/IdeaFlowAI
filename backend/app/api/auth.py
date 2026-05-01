"""Authentication API endpoints for registration, login, and user info."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.models.database import get_db
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
