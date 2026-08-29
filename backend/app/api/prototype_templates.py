"""REST endpoints backing the new OpenDesign-style prototype flow.

Read-only catalogue for templates and design systems. Generation lives
elsewhere (Agent pipeline, Phase 4); this module exists so the frontend
gallery page can render without the backend agents being built yet.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import re
import socket
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from agents.execution_engine.ndjson_adapter import run_prototype_pipeline
from app.core.config import settings
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
    has_thumbnail: bool = False


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
    has_preview: bool = False


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
    "/templates/{template_id}/thumbnail",
    summary="Serve the template's pre-rendered thumbnail image for the gallery card",
    response_class=FileResponse,
)
def get_template_thumbnail(template_id: str) -> FileResponse:
    """Return the pre-rendered ``thumbnail.jpg`` (a screenshot of example.html).

    Intentionally unauthenticated and static, same rationale as ``/preview``:
    the gallery embeds it directly via ``<img src>``. Only ever serves
    ``skills/opendesign/design-templates/<id>/thumbnail.jpg`` (the path is built
    by the loader), so there is no path-traversal surface.
    """
    path = od_loader.get_template_thumbnail_path(template_id)
    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Thumbnail not available for template '{template_id}'",
        )
    return FileResponse(
        path=path,
        media_type="image/jpeg",
        # Cache aggressively — content only changes when we redeploy.
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get(
    "/templates/{template_id}/assets/{asset_path:path}",
    summary="Serve a template preview asset (e.g. assets/template.html) for the iframe",
    response_class=FileResponse,
)
def get_template_asset(template_id: str, asset_path: str) -> FileResponse:
    """Serve a static file from a template's ``assets/`` directory.

    A template's ``example.html`` (served at ``/preview``) may be a thin wrapper
    that references sibling assets with relative URLs — e.g.
    ``<iframe src="./assets/template.html">`` or ``<script src="assets/deck-stage.js">``.
    The browser resolves those against the preview path, so they land here.

    Intentionally unauthenticated (like ``/preview``) so the sandboxed iframe can
    load the asset without propagating the JWT into static requests. Read-only and
    strictly confined to the template's ``assets/`` dir — ``od_loader.get_template_asset_path``
    rejects any path-traversal, so there is no escape surface. The media type is
    inferred from the filename by ``FileResponse``.
    """
    path = od_loader.get_template_asset_path(template_id, asset_path)
    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset '{asset_path}' not found for template '{template_id}'",
        )
    return FileResponse(
        path=path,
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


@router.get(
    "/design-systems/{ds_id}/preview",
    summary="Serve the design system's components.html for iframe rendering",
    response_class=FileResponse,
)
def get_design_system_preview(ds_id: str) -> FileResponse:
    """Returns the raw components.html for the design system.

    Intentionally unauthenticated (same pattern as template preview) so the
    frontend can embed it in a sandboxed iframe without JWT plumbing.
    Only serves files inside ``skills/opendesign/design-systems/<id>/components.html``.
    """
    path = od_loader.get_design_system_preview_path(ds_id)
    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Preview not available for design system '{ds_id}'",
        )
    return FileResponse(
        path=path,
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "public, max-age=3600"},
    )


# ---------------------------------------------------------------------------
# Generation run (Phase 4)
# ---------------------------------------------------------------------------


class RunRequest(BaseModel):
    template_id: str = Field(..., min_length=1)
    design_system_id: str = Field(..., min_length=1)
    brief: str = Field(..., min_length=1, max_length=settings.BRIEF_MAX_CHARS)
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
            async for event in run_prototype_pipeline(
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


# ---------------------------------------------------------------------------
# URL fetch proxy — avoids CORS when user pastes a website URL as a custom
# template. Auth-gated, size-limited, private-IP blocked.
# ---------------------------------------------------------------------------

def _is_private_url(url: str) -> bool:
    """Return True if the URL resolves to a private/loopback address."""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        if hostname.lower() in ("localhost", "127.0.0.1", "::1"):
            return True
        # Resolve to IP and check private ranges
        ip_str = socket.gethostbyname(hostname)
        ip = ipaddress.ip_address(ip_str)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except Exception:
        # If we can't resolve, treat as safe (let httpx handle the error)
        return False


@router.get(
    "/fetch-url",
    summary="Proxy-fetch a URL and return its HTML content (for custom template upload)",
)
async def fetch_url_for_template(
    url: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Fetch an external URL and return its HTML body.

    Used by the CustomTemplateModal when the user pastes a website URL.
    Validates the URL, blocks private IPs, enforces a 10s timeout and 2MB
    size limit, and returns ``{ "html": "<content>" }`` on success or
    ``{ "error": "<reason>" }`` on failure.
    """
    import httpx

    # Basic scheme validation
    if not re.match(r"^https?://", url, re.IGNORECASE):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")

    # Block private/loopback addresses (SSRF prevention)
    if _is_private_url(url):
        raise HTTPException(status_code=400, detail="Private or loopback URLs are not allowed")

    MAX_BYTES = 2 * 1024 * 1024  # 2 MB

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            response = await client.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; FlowIn/1.0; +https://flowin.ai)"},
            )
            response.raise_for_status()

            # Read up to MAX_BYTES — don't buffer the whole response
            content = b""
            async for chunk in response.aiter_bytes(chunk_size=8192):
                content += chunk
                if len(content) > MAX_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail="Response too large (max 2 MB)",
                    )

            # Decode — try charset from Content-Type, fall back to utf-8
            charset = "utf-8"
            ct = response.headers.get("content-type", "")
            if "charset=" in ct:
                charset = ct.split("charset=")[-1].split(";")[0].strip()
            try:
                html = content.decode(charset, errors="replace")
            except (LookupError, UnicodeDecodeError):
                html = content.decode("utf-8", errors="replace")

            return {"html": html}

    except HTTPException:
        raise
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="URL fetch timed out (10s limit)")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Remote server returned {exc.response.status_code}",
        )
    except Exception as exc:
        logger.warning("fetch-url failed for %s: %s", url, exc)
        raise HTTPException(
            status_code=502,
            detail="Could not reach that URL. Check the address and try again.",
        )
