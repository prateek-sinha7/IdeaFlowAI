"""Global Hooks catalog API.

This is the read-only, shared catalog of available behavioral hooks
shown in the Library UI. Sourced from ``hooks/global/{hook_id}/HOOK.md``
via ``app.agents.hooks_catalog.list_global_hooks()`` — a folder scan, same
discovery pattern as ``agents/prompts/{agent_id}/AGENT.md`` (see
``agents/loader.py``). Adding a hook is a folder-drop; nothing here
needs to change. Events/tags are derived from the scanned entries, not
maintained as a separate list.
"""

import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends

from app.agents.hooks_catalog import list_global_hooks, _get_icon_for_event
from app.core.dependencies import get_current_user
from app.models.user import User

logger = logging.getLogger("app.api.hooks")

router = APIRouter(prefix="/api/hooks", tags=["hooks"])


@router.get("/library")
def get_hooks_library(
    current_user: User = Depends(get_current_user),
):
    """Get the full global Hooks catalog (mirrors GET /api/skills/library)."""
    entries = list_global_hooks()

    events = sorted({e.event for e in entries if e.event})

    return {
        "hooks": [asdict(e) for e in entries],
        "total_count": len(entries),
        "events": [{"id": "all", "label": "All"}]
        + [{"id": e, "label": e.replace("_", " "), "icon": _get_icon_for_event(e)} for e in events],
    }
