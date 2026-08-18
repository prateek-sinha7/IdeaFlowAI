"""Global Skills catalog API.

Distinct from ``/api/agents/skills`` (per-user saved skill overrides, see
``app/api/agents.py`` and ``app/agents/skills.py``): this is the read-only,
shared catalog of available Claude-Code-ecosystem skills (ECC/Superpowers)
shown in the Library UI. Sourced from ``skills/global/{skill_id}/SKILL.md``
via ``app.agents.skills_catalog.list_global_skills()`` — a folder scan, same
discovery pattern as ``agents/prompts/{agent_id}/AGENT.md`` (see
``agents/loader.py`` / FIX-051). Adding a skill is a folder-drop; nothing here
needs to change. Categories/sources are derived from the scanned entries, not
maintained as a separate list.
"""

import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends

from app.agents.skills_catalog import list_global_skills, _get_icon_for_category
from app.core.dependencies import get_current_user
from app.models.user import User

logger = logging.getLogger("app.api.skills")

router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.get("/library")
def get_skills_library(
    current_user: User = Depends(get_current_user),
):
    """Get the full global Skills catalog (mirrors GET /api/agents/library)."""
    entries = list_global_skills()

    categories = sorted({e.category for e in entries if e.category})

    return {
        "skills": [asdict(e) for e in entries],
        "total_count": len(entries),
        "categories": [{"id": "all", "label": "All"}]
        + [{"id": c, "label": c.replace("_", " ").title(), "icon": _get_icon_for_category(c)} for c in categories],
    }
