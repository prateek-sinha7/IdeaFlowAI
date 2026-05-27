"""REST endpoints for the OpenDesign-style PPT/deck flow.

Read-only catalogue for PPT templates. Generation goes through the WebSocket
pipeline (od_ppt pipeline type).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from app.core.dependencies import get_current_user
from app.models.user import User
from app.services import od_loader

logger = logging.getLogger("app.api.ppt_templates")

router = APIRouter(prefix="/api/ppt", tags=["ppt"])


# ---------------------------------------------------------------------------
# Response models (reuse same shape as prototype templates)
# ---------------------------------------------------------------------------

from pydantic import BaseModel


class PPTTemplateListItem(BaseModel):
    id: str
    name: str
    description: str
    mode: str | None = None
    platform: str | None = None
    scenario: str | None = None
    triggers: list[str] = []
    craft_required: list[str] = []
    example_prompt: str | None = None
    has_preview: bool = False
    design_system: dict[str, Any] = {}


class PPTTemplateDetail(PPTTemplateListItem):
    inputs: list[dict[str, Any]] | dict[str, Any] = []
    outputs: dict[str, Any] = {}
    body: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/templates",
    response_model=list[PPTTemplateListItem],
    summary="List deck/slides mode OpenDesign templates",
)
def list_ppt_templates(_: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    """Gallery list filtered to ``od.mode == 'deck'`` or ``'slides'``."""
    return od_loader.list_ppt_templates()


@router.get(
    "/templates/{template_id}",
    response_model=PPTTemplateDetail,
    summary="Full PPT template payload incl. SKILL.md body",
)
def get_ppt_template(template_id: str, _: User = Depends(get_current_user)) -> dict[str, Any]:
    template = od_loader.get_ppt_template(template_id)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"PPT template '{template_id}' not found",
        )
    return template


@router.get(
    "/templates/{template_id}/preview",
    summary="Serve the PPT template's example.html for iframe rendering",
    response_class=FileResponse,
)
def get_ppt_template_preview(template_id: str) -> FileResponse:
    """Returns the raw example.html. Intentionally unauthenticated so the
    frontend can embed it in a sandboxed iframe without JWT plumbing."""
    path = od_loader.get_template_preview_path(template_id)
    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Preview not available for PPT template '{template_id}'",
        )
    return FileResponse(
        path=path,
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "public, max-age=3600"},
    )
