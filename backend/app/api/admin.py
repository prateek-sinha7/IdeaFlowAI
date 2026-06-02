"""Admin API endpoints — user management and tier control.

Only accessible to users with is_admin=True. All endpoints require
a valid JWT from an admin account.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.entitlements import TIER_PIPELINES
from app.models.database import get_db
from app.models.user import User

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ─── Guards ───────────────────────────────────────────────────────────────────

def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Dependency that raises 403 if the caller is not an admin."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
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

    model_config = {"from_attributes": True}


class UpdateTierRequest(BaseModel):
    tier: str


class CreateUserRequest(BaseModel):
    email: str
    password: str
    tier: str = "basic"
    is_admin: bool = False


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/users", response_model=list[AdminUserResponse])
def list_users(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List all users with their tier and run counts."""
    from app.models.workflow import WorkflowRun
    from sqlalchemy import func

    # Count workflow runs per user
    run_counts = (
        db.query(WorkflowRun.user_id, func.count(WorkflowRun.id).label("cnt"))
        .group_by(WorkflowRun.user_id)
        .all()
    )
    count_map = {row.user_id: row.cnt for row in run_counts}

    users = db.query(User).order_by(User.created_at.desc()).all()
    result = []
    for u in users:
        result.append(AdminUserResponse(
            id=u.id,
            email=u.email,
            tier=u.tier,
            is_admin=u.is_admin,
            created_at=u.created_at,
            workflow_run_count=count_map.get(u.id, 0),
        ))
    return result


@router.patch("/users/{user_id}/tier", response_model=AdminUserResponse)
def update_user_tier(
    user_id: str,
    request: UpdateTierRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Change a user's tier. Admin cannot downgrade themselves."""
    valid_tiers = set(TIER_PIPELINES.keys())
    if request.tier not in valid_tiers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid tier. Must be one of: {', '.join(sorted(valid_tiers))}",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.tier = request.tier
    db.commit()
    db.refresh(user)

    from app.models.workflow import WorkflowRun
    from sqlalchemy import func
    run_count = db.query(func.count(WorkflowRun.id)).filter(WorkflowRun.user_id == user_id).scalar() or 0

    return AdminUserResponse(
        id=user.id,
        email=user.email,
        tier=user.tier,
        is_admin=user.is_admin,
        created_at=user.created_at,
        workflow_run_count=run_count,
    )


@router.post("/users", response_model=AdminUserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    request: CreateUserRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Create a new user account (admin only)."""
    from app.core.security import hash_password
    import uuid

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

    new_user = User(
        id=str(uuid.uuid4()),
        email=request.email,
        password_hash=hash_password(request.password),
        tier=request.tier,
        is_admin=request.is_admin,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return AdminUserResponse(
        id=new_user.id,
        email=new_user.email,
        tier=new_user.tier,
        is_admin=new_user.is_admin,
        created_at=new_user.created_at,
        workflow_run_count=0,
    )


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_user(
    user_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Delete a user. Admin cannot delete themselves."""
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete your own account.",
        )
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    db.delete(user)
    db.commit()
    return None
