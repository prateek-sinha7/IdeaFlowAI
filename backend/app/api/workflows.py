"""Workflow run CRUD API endpoints."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
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

    status: Optional[str] = None  # "completed" | "failed" | "cancelled"
    output: Optional[str] = None
    duration: Optional[float] = None
    error: Optional[str] = None


class ExportPptxRequest(BaseModel):
    """Request body for POST /api/workflows/export-pptx.

    All four fields are optional, but at least one of ``workflow_id``,
    ``js_code`` or ``html`` MUST be present (enforced inside the handler
    rather than via Pydantic, since the field that matters depends on the
    extraction strategy chosen).

    Caps exist to bound subprocess input and prevent trivial DoS via huge
    payloads — they are intentionally generous (a real PptxGenJS function
    is rarely > 100 KB) and not a substitute for the sandboxing work
    tracked separately under the pptx_export hardening item.
    """

    workflow_id: Optional[str] = Field(
        default=None,
        max_length=64,
        description="UUID of a WorkflowRun belonging to the caller; agent output is fetched server-side.",
    )
    js_code: Optional[str] = Field(
        default=None,
        max_length=512_000,
        description="Raw PptxGenJS JavaScript (the generatePresentation function body).",
    )
    html: Optional[str] = Field(
        default=None,
        max_length=2_000_000,
        description="An HTML preview containing a generatePresentation() function in a <script> block.",
    )
    title: str = Field(
        default="Presentation",
        max_length=120,
        description="Filename hint for the Content-Disposition response header.",
    )


class WorkflowRunResponse(BaseModel):
    """Workflow run data returned in API responses."""

    id: str
    title: str
    type: str
    status: str
    input: str
    output: Optional[str] = None
    agent_outputs: Optional[str] = None
    agent_count: int
    duration: Optional[float] = None
    error: Optional[str] = None
    token_usage: Optional[str] = None
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


@router.post("/export-pptx")
def export_pptx(
    request: ExportPptxRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a .pptx file from Agent 3's PptxGenJS code.

    Tries to get the code from:
    1. workflow_id → agent_outputs (the ppt-code-generator agent's output)
    2. js_code field directly
    3. html field → extract generatePresentation() from HTML

    Returns: .pptx binary download.
    """
    import json as _json
    from fastapi.responses import Response
    from app.services.pptx_export import generate_pptx_from_code

    js_code = request.js_code or ""
    html_content = request.html or ""
    workflow_id = request.workflow_id or ""
    title = request.title

    # The set of agent IDs whose `output` is canonical PptxGenJS source. The
    # previous substring scan (`"code" in aid or "generator" in aid or
    # "ppt-code" in aid`) had four false positives (`app-code-generator`,
    # `barcode-extractor`, `prototype-generator`, `code-reviewer`) — a user
    # who had run a non-PPT pipeline in the same workflow_id could silently
    # download a deck built from the wrong agent's output. Exact match
    # against the registered IDs eliminates that class of mistake.
    _PPT_CODE_AGENT_IDS = {"ppt-code-generator"}

    # Strategy 1: Get Agent 3 output from workflow DB
    if not js_code and workflow_id:
        wr = db.query(WorkflowRun).filter(
            WorkflowRun.id == workflow_id,
            WorkflowRun.user_id == current_user.id
        ).first()
        if wr and wr.agent_outputs:
            try:
                outputs = _json.loads(wr.agent_outputs)
                for agent in outputs:
                    if agent.get("agent_id", "") in _PPT_CODE_AGENT_IDS:
                        js_code = agent.get("output", "")
                        break
            except Exception:
                pass

    # Strategy 2: Extract from HTML
    if not js_code and html_content:
        import re as _re
        # Find generatePresentation function in script tags
        scripts = _re.findall(r'<script[^>]*>([\s\S]*?)</script>', html_content)
        for script in scripts:
            m = _re.search(r'((?:async\s+)?function\s+generatePresentation\s*\([^)]*\)\s*\{)', script)
            if m:
                start = m.start()
                depth = 0
                end = start
                for i in range(m.end() - 1, len(script)):
                    if script[i] == '{':
                        depth += 1
                    elif script[i] == '}':
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                if end > start:
                    js_code = script[start:end]
                    break

        # Also try full HTML search
        if not js_code:
            m = _re.search(r'((?:async\s+)?function\s+generatePresentation\s*\([^)]*\)\s*\{)', html_content)
            if m:
                start = m.start()
                depth = 0
                end = start
                for i in range(start, len(html_content)):
                    if html_content[i] == '{':
                        depth += 1
                    elif html_content[i] == '}':
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                if end > start:
                    js_code = html_content[start:end]

    if not js_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not find PptxGenJS code. Try re-running the pipeline.",
        )

    try:
        pptx_bytes = generate_pptx_from_code(js_code, title=title)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate PPTX: {str(e)[:200]}",
        )

    # Sanitize the filename to ASCII alphanumerics + `_-.` only. The previous
    # `title.replace(' ', '_')[:40]` did NOT strip CR/LF/control chars or
    # double-quote, which let a maliciously-crafted title smuggle additional
    # headers (HTTP response splitting). The Pydantic max_length on `title`
    # bounds the size; this re.sub bounds the alphabet.
    import re as _re
    safe_title = _re.sub(r"[^A-Za-z0-9._-]", "_", title)[:40] or "Presentation"
    filename = f"{safe_title}.pptx"
    return Response(
        content=pptx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
