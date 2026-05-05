"""Workflow run CRUD API endpoints."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.models.database import get_db
from app.models.user import User
from app.models.workflow import WorkflowRun

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


# --- Request/Response Schemas ---


class CreateWorkflowRequest(BaseModel):
    """Request body for creating a new workflow run."""

    type: str  # "user_stories" | "ppt" | "prototype"
    input: str
    title: Optional[str] = None
    agent_count: int = 12


class UpdateWorkflowRequest(BaseModel):
    """Request body for updating a workflow run status."""

    status: Optional[str] = None  # "completed" | "failed"
    output: Optional[str] = None
    duration: Optional[float] = None
    error: Optional[str] = None


class WorkflowRunResponse(BaseModel):
    """Workflow run data returned in API responses."""

    id: str
    title: str
    type: str
    status: str
    input: str
    output: Optional[str] = None
    agent_count: int
    duration: Optional[float] = None
    error: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# --- Endpoints ---


@router.post("", response_model=WorkflowRunResponse, status_code=status.HTTP_201_CREATED)
def create_workflow(
    request: CreateWorkflowRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new workflow run.

    Called when a user starts a pipeline from the Creation Hub.
    """
    # Validate type
    valid_types = ("user_stories", "ppt", "prototype")
    if request.type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid workflow type. Must be one of: {', '.join(valid_types)}",
        )

    # Generate title from input if not provided
    title = request.title or request.input[:60].strip()

    workflow_run = WorkflowRun(
        user_id=current_user.id,
        title=title,
        type=request.type,
        status="running",
        input=request.input,
        agent_count=request.agent_count,
    )
    db.add(workflow_run)
    db.commit()
    db.refresh(workflow_run)

    return workflow_run


@router.get("", response_model=list[WorkflowRunResponse])
def list_workflows(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
    type: Optional[str] = None,
    status_filter: Optional[str] = None,
):
    """List workflow runs for the authenticated user.

    Ordered by created_at descending (most recent first).
    Supports optional filtering by type and status.
    """
    query = db.query(WorkflowRun).filter(WorkflowRun.user_id == current_user.id)

    if type:
        query = query.filter(WorkflowRun.type == type)
    if status_filter:
        query = query.filter(WorkflowRun.status == status_filter)

    runs = (
        query
        .order_by(WorkflowRun.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return runs


@router.get("/{workflow_id}", response_model=WorkflowRunResponse)
def get_workflow(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a specific workflow run by ID.

    Returns 404 if the workflow does not exist or does not belong to the user.
    """
    workflow_run = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.id == workflow_id, WorkflowRun.user_id == current_user.id)
        .first()
    )
    if not workflow_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found",
        )

    return workflow_run


@router.patch("/{workflow_id}", response_model=WorkflowRunResponse)
def update_workflow(
    workflow_id: str,
    request: UpdateWorkflowRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a workflow run (status, output, duration, error).

    Used by the pipeline executor to mark completion or failure.
    """
    workflow_run = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.id == workflow_id, WorkflowRun.user_id == current_user.id)
        .first()
    )
    if not workflow_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found",
        )

    if request.status:
        workflow_run.status = request.status
        if request.status in ("completed", "failed"):
            workflow_run.completed_at = datetime.now(timezone.utc)

    if request.output is not None:
        workflow_run.output = request.output

    if request.duration is not None:
        workflow_run.duration = request.duration

    if request.error is not None:
        workflow_run.error = request.error

    db.commit()
    db.refresh(workflow_run)

    return workflow_run


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workflow(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a workflow run.

    Returns 204 No Content on success.
    Returns 404 if the workflow does not exist or does not belong to the user.
    """
    workflow_run = (
        db.query(WorkflowRun)
        .filter(WorkflowRun.id == workflow_id, WorkflowRun.user_id == current_user.id)
        .first()
    )
    if not workflow_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow run not found",
        )

    db.delete(workflow_run)
    db.commit()

    return None
