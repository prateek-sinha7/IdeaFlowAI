"""REST endpoints backing the new OpenDesign-style prototype flow.

Read-only catalogue for templates and design systems. Generation lives
elsewhere (Agent pipeline, Phase 4); this module exists so the frontend
gallery page can render without the backend agents being built yet.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.agents.od_runner import run_od_prototype_pipeline
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services import od_loader

logger = logging.getLogger("app.api.prototype_templates")

router = APIRouter(prefix="/api/prototype", tags=["prototype"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class TemplateListItem(BaseModel):
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


class TemplateDetail(TemplateListItem):
    design_system: dict[str, Any] = {}
    inputs: list[dict[str, Any]] | dict[str, Any] = []
    outputs: dict[str, Any] = {}
    body: str


class DesignSystemListItem(BaseModel):
    id: str
    name: str
    category: str
    description: str


class DesignSystemDetail(DesignSystemListItem):
    body: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/templates",
    response_model=list[TemplateListItem],
    summary="List prototype-mode OpenDesign templates",
)
def list_templates(_: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    """Gallery list. Filtered to ``od.mode == "prototype"`` (43 templates as
    of 2026-Q2)."""
    return od_loader.list_prototype_templates()


@router.get(
    "/templates/{template_id}",
    response_model=TemplateDetail,
    summary="Full template payload incl. SKILL.md body",
)
def get_template(template_id: str, _: User = Depends(get_current_user)) -> dict[str, Any]:
    template = od_loader.get_template(template_id)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template '{template_id}' not found",
        )
    return template


@router.get(
    "/templates/{template_id}/preview",
    summary="Serve the template's example.html for iframe rendering",
    response_class=FileResponse,
)
def get_template_preview(template_id: str) -> FileResponse:
    """Returns the raw example.html.

    Intentionally unauthenticated so the frontend can embed the preview in
    a sandboxed iframe via ``<iframe src=".../preview" sandbox>`` without
    propagating the JWT into static asset requests. The endpoint only ever
    serves files inside ``skills/opendesign/design-templates/<id>/example.html``
    so there is no path-traversal surface.
    """
    path = od_loader.get_template_preview_path(template_id)
    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Preview not available for template '{template_id}'",
        )
    return FileResponse(
        path=path,
        media_type="text/html; charset=utf-8",
        # Cache aggressively — content only changes when we redeploy.
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get(
    "/design-systems",
    response_model=list[DesignSystemListItem],
    summary="List OpenDesign design systems (152 brands)",
)
def list_design_systems(_: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    return od_loader.list_design_systems()


@router.get(
    "/design-systems/{ds_id}",
    response_model=DesignSystemDetail,
    summary="Full DESIGN.md body for a design system",
)
def get_design_system(ds_id: str, _: User = Depends(get_current_user)) -> dict[str, Any]:
    ds = od_loader.get_design_system(ds_id)
    if ds is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Design system '{ds_id}' not found",
        )
    return ds


# ---------------------------------------------------------------------------
# Generation run (Phase 4)
# ---------------------------------------------------------------------------


class RunRequest(BaseModel):
    template_id: str = Field(..., min_length=1)
    design_system_id: str = Field(..., min_length=1)
    brief: str = Field(..., min_length=1, max_length=8000)
    # The DiscoveryAnswers shape from the frontend is open-ended (`template`
    # plus a handful of optional fields); accept it as a free dict and let
    # the prompt composer decide what to inject.
    discovery: dict[str, Any] | None = None


@router.post(
    "/run",
    summary="Stream a prototype generation run as NDJSON events",
    response_class=StreamingResponse,
)
async def run_prototype(
    payload: RunRequest,
    _: User = Depends(get_current_user),
) -> StreamingResponse:
    """Run the 4-stage OpenDesign-style pipeline.

    Returns ``application/x-ndjson``: one JSON event per line, terminated by
    ``\\n``. Frontend reads with ``fetch().body.getReader()`` and parses
    each line. See ``od_pipeline.run_od_prototype_pipeline`` for the full
    list of event shapes.
    """
    if od_loader.get_template(payload.template_id) is None:
        raise HTTPException(status_code=404, detail=f"Template '{payload.template_id}' not found")
    if od_loader.get_design_system(payload.design_system_id) is None:
        raise HTTPException(status_code=404, detail=f"Design system '{payload.design_system_id}' not found")

    async def event_stream():
        try:
            async for event in run_od_prototype_pipeline(
                template_id=payload.template_id,
                design_system_id=payload.design_system_id,
                brief=payload.brief,
                discovery=payload.discovery,
            ):
                yield json.dumps(event) + "\n"
        except Exception as exc:  # noqa: BLE001 — last-chance: surface as a JSON event
            logger.exception("OD prototype pipeline crashed")
            yield json.dumps({"type": "pipeline_error", "error": str(exc)}) + "\n"

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={
            # Disable proxy buffering so chunks reach the browser as they're
            # produced. Nginx in particular will hold the entire response if
            # this header is missing.
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache",
        },
    )
