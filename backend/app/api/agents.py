"""Agent Pipeline API — REST endpoints for agent management and workflow execution.

Skills are namespaced per user (see WORKFLOWS.md §B6 for the rationale and the
storage layout in ``app/agents/skills.py``). Every skill endpoint requires
``get_current_user`` and only ever reads/writes that user's own files; no
endpoint here can touch another user's skill or the admin-managed global tier.

Phase B G1-C7 (prompt-injection via per-user skill content): user-controllable
skill payloads are capped at ``MAX_SKILL_BYTES`` at save time. The orchestrator
applies sanitisation + a backstop truncation at load time — see
``app.agents.skills.sanitize_user_skill_content``.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from agents.registry import get_pipeline_agents, get_all_agents_flat, get_agent_by_id
from app.models.database import get_db
from app.models.user_agent import UserAgent
from app.agents.skills import (
    MAX_SKILL_BYTES,
    delete_custom_skill,
    get_skill_content,
    list_user_skills,
    read_user_skill,
    save_custom_skill,
)
from app.agents.prompt_overrides import (
    MAX_PROMPT_OVERRIDE_BYTES,
    read_user_prompt_override,
    save_user_prompt_override,
    delete_user_prompt_override,
    has_user_prompt_override,
)
from app.core.dependencies import get_current_user
from app.models.user import User

logger = logging.getLogger("app.api.agents")

router = APIRouter(prefix="/api/agents", tags=["agents"])


# --- Response Models ---

class AgentResponse(BaseModel):
    id: str
    name: str
    role: str
    description: str
    pipeline_type: str
    order: int
    icon: str
    estimated_duration: float
    has_skill: bool
    # Static HITL review-gate marker from the agent's AGENT.md frontmatter
    # ("Human_Gate" / "Validation_Gate" / None). Surfaced so the frontend's
    # per-agent review-gate toggle (Phase 6b) can pre-check the default-gated
    # agents. ``None`` means the agent is not gated by default.
    gate: str | None = None
    # Full AGENT.md prompt body (the markdown text after the YAML frontmatter).
    # Surfaced so the Library + workflow info views can display it (KAN-76).
    prompt_body: str = ""


class PipelineResponse(BaseModel):
    pipeline_type: str
    agents: list[AgentResponse]
    total_estimated_duration: float


class SkillRequest(BaseModel):
    agent_id: str
    # Pydantic ``max_length`` is a *character* cap (defence in depth). The
    # authoritative byte-level cap is the explicit check in ``create_skill``
    # using ``MAX_SKILL_BYTES`` — Pydantic counts code points, not UTF-8
    # bytes, so for multi-byte text the byte check is stricter and is what
    # actually returns HTTP 413. Keep these in sync: ``max_length`` is the
    # number of bytes (since 1 ASCII char == 1 byte) and only differs for
    # non-ASCII content, where the byte check will fire first anyway.
    content: str = Field(..., max_length=MAX_SKILL_BYTES)


class SkillResponse(BaseModel):
    agent_id: str
    content: str


class PromptOverrideRequest(BaseModel):
    content: str = Field(..., max_length=MAX_PROMPT_OVERRIDE_BYTES)


class AgentPromptResponse(BaseModel):
    agent_id: str
    prompt_body: str          # base AGENT.md prompt
    override: str | None      # per-user override (None if not set)
    has_override: bool        # whether the user has saved an override


# --- Helpers ---

def _agent_has_resolvable_skill(agent_id: str, user_id: str) -> bool:
    """Return True if any skill (user, global, pptx, or default) resolves for
    the given agent under the calling user. Used purely as a UI hint."""
    return bool(get_skill_content(agent_id, user_id=user_id))


# --- Endpoints ---

@router.get("/pipelines/{pipeline_type}", response_model=PipelineResponse)
def get_pipeline(
    pipeline_type: str,
    current_user: User = Depends(get_current_user),
):
    """Get all agents for a specific pipeline type."""
    agents = get_pipeline_agents(pipeline_type)

    agent_responses = [
        AgentResponse(
            id=a.id,
            name=a.name,
            role=a.role,
            description=a.description,
            pipeline_type=a.pipeline_type,
            order=a.order,
            icon=a.icon,
            estimated_duration=a.estimated_duration,
            has_skill=_agent_has_resolvable_skill(a.id, current_user.id),
            gate=a.gate,
            prompt_body=a.prompt_body,
        )
        for a in agents
    ]

    total_duration = sum(a.estimated_duration for a in agents)

    return PipelineResponse(
        pipeline_type=pipeline_type,
        agents=agent_responses,
        total_estimated_duration=total_duration,
    )


@router.get("/library")
def get_agent_library(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all available agents across all pipelines, plus the caller's saved ones."""
    all_agents = get_all_agents_flat()

    # ── The caller's saved custom agents (0031 / app/api/user_agents.py) ──────
    # Queried per request, not folded into `get_all_agents_flat()`: that walks
    # disk-derived tables built once at import, and `_SPEC_CACHE` has no eviction,
    # so a row created or edited after start-up would never be seen.
    #
    # LIBRARY ENTRIES, not runnable ids. The `user-agent:` prefix cannot collide
    # with an agent folder, so mistaking one for a loadable id fails at
    # load_agent_spec rather than silently resolving something else. The composer
    # copies a saved agent as a template — nothing resolves an agent THROUGH this
    # table (see app/api/user_agents.py for why launch-by-reference wasn't built).
    #
    # FAIL SOFT, DELIBERATELY: saved agents are additive, so a read failure must
    # degrade to "no saved agents" rather than 500 the built-in roster away.
    # Written for code-ahead-of-database deploys, where a missing `user_agents`
    # table surfaced in the browser as an unrelated CORS error (a 500 from the
    # exception middleware carries no CORS headers). `db.rollback()` matters:
    # without it every later query on the failed session raises PendingRollbackError.
    try:
        saved_rows = (
            db.query(UserAgent)
            .filter(UserAgent.user_id == current_user.id)
            .order_by(UserAgent.created_at.desc())
            .all()
        )
    except SQLAlchemyError:
        db.rollback()
        logger.warning(
            "agents/library: could not read saved agents (is migration 0031 "
            "applied?) — serving the filesystem roster only",
            exc_info=True,
        )
        saved_rows = []
    saved_agents = [
        {
            "id": f"user-agent:{r.id}",
            "name": r.name,
            "role": "Custom agent",
            "description": r.description or "",
            # Surfaces in the same bucket the composer already treats as
            # user-composable (useAgentLibrary splits on pipeline_type ==
            # "custom"), so no frontend routing change is needed to show it.
            "pipeline_type": "custom",
            "order": 0,
            "icon": r.icon or "🧩",
            "estimated_duration": 0.0,
            "has_skill": bool(r.skills),
            "gate": None,
            "prompt_body": r.prompt,
            # Extra fields, absent on filesystem agents — the composer reads
            # these to pre-fill a new node. Additive, so existing consumers that
            # do not know about them are unaffected.
            "is_user_agent": True,
            "skills": list(r.skills or []),
        }
        for r in saved_rows
    ]

    return {
        "agents": [
            {
                "id": a.id,
                "name": a.name,
                "role": a.role,
                "description": a.description,
                "pipeline_type": a.pipeline_type,
                "order": a.order,
                "icon": a.icon,
                "estimated_duration": a.estimated_duration,
                "has_skill": _agent_has_resolvable_skill(a.id, current_user.id),
                "gate": a.gate,
                "prompt_body": a.prompt_body,
            }
            for a in all_agents
        ]
        + saved_agents,
        "total_count": len(all_agents) + len(saved_agents),
        "pipelines": {
            "user_stories": len(get_pipeline_agents("user_stories")),
            "ppt": len(get_pipeline_agents("ppt")),
            "prototype": len(get_pipeline_agents("prototype")),
        },
    }


@router.get("/skills")
def get_all_skills_endpoint(
    current_user: User = Depends(get_current_user),
):
    """List the calling user's own custom skills only.

    Returns user-saved skills under ``backend/skills/users/{user_id}/``. Does
    not include other users' skills, the admin global tier, or the in-code
    DEFAULT_SKILLS — those are implementation details exposed only at runtime
    via ``get_skill_content``.
    """
    skills = list_user_skills(current_user.id)
    return {
        "skills": [
            {"agent_id": agent_id, "content_preview": content[:200]}
            for agent_id, content in skills.items()
        ],
        "total_count": len(skills),
    }


@router.get("/skills/{agent_id}", response_model=SkillResponse)
def get_skill(
    agent_id: str,
    current_user: User = Depends(get_current_user),
):
    """Read the calling user's own custom skill for an agent.

    Returns an empty string when the user has not saved a custom skill for
    this agent — this matches the pre-existing "no custom skill yet" UX and
    deliberately does not fall back to other users' files or to defaults.
    """
    content = read_user_skill(agent_id, user_id=current_user.id)
    return SkillResponse(agent_id=agent_id, content=content or "")


@router.post("/skills")
def create_skill(
    request: SkillRequest,
    current_user: User = Depends(get_current_user),
):
    """Create or update the calling user's custom skill for an agent.

    - Validates ``agent_id`` against the registry (rejects unknown IDs with 400).
    - Caps content at ``MAX_SKILL_BYTES`` (8 KB) — oversized payloads return
      HTTP 413. This is the primary defence against the Phase B G1-C7
      prompt-injection vector (see module docstring).
    - Writes to ``backend/skills/users/{current_user.id}/{agent_id}/SKILL.md``.
    - Audit-logs the save (user, agent, byte count) so a malicious tenant
      churning skill content shows up in the application log.
    """
    if get_agent_by_id(request.agent_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown agent_id: {request.agent_id}",
        )

    content_bytes = request.content.encode("utf-8")
    if len(content_bytes) > MAX_SKILL_BYTES:
        # The Pydantic ``max_length=MAX_SKILL_BYTES`` cap on the request
        # schema returns 422 for the easy case (ASCII content); this branch
        # catches the multi-byte case where len(content) <= MAX_SKILL_BYTES
        # but len(content.encode('utf-8')) > MAX_SKILL_BYTES. Either way the
        # user-visible contract is "oversize gets rejected"; we use 413 for
        # the byte-overflow path because it's the canonical
        # payload-too-large signal.
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"Skill content exceeds maximum size of {MAX_SKILL_BYTES} bytes"
            ),
        )

    path = save_custom_skill(request.agent_id, request.content, user_id=current_user.id)
    logger.info(
        "Skill saved: user=%s agent=%s bytes=%d",
        current_user.id,
        request.agent_id,
        len(content_bytes),
    )
    return {"status": "saved", "agent_id": request.agent_id, "path": path}


@router.delete("/skills/{agent_id}")
def remove_skill(
    agent_id: str,
    current_user: User = Depends(get_current_user),
):
    """Delete the calling user's own custom skill.

    Idempotent — returns ``{status: "not_found"}`` with HTTP 200 when no
    custom skill exists, instead of raising 404, so the frontend can call
    DELETE without checking first.
    """
    deleted = delete_custom_skill(agent_id, user_id=current_user.id)
    return {"status": "deleted" if deleted else "not_found", "agent_id": agent_id}


# ── Prompt override endpoints (KAN-76) ──────────────────────────────────────


@router.get("/{agent_id}/prompt", response_model=AgentPromptResponse)
def get_agent_prompt(
    agent_id: str,
    current_user: User = Depends(get_current_user),
):
    """Return an agent's base AGENT.md prompt body plus the caller's override.

    - ``prompt_body``: the read-only base prompt from AGENT.md (always present)
    - ``override``: the user's saved override text, or ``None`` if not set
    - ``has_override``: convenience boolean for the frontend toggle
    """
    spec = get_agent_by_id(agent_id)
    if spec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent not found: {agent_id}",
        )
    override = read_user_prompt_override(agent_id, user_id=current_user.id)
    return AgentPromptResponse(
        agent_id=agent_id,
        prompt_body=spec.prompt_body,
        override=override,
        has_override=override is not None,
    )


@router.put("/{agent_id}/prompt")
def save_agent_prompt_override(
    agent_id: str,
    request: PromptOverrideRequest,
    current_user: User = Depends(get_current_user),
):
    """Save (create or replace) the caller's per-user prompt override.

    The override is stored at ``backend/skills/users/{user_id}/{agent_id}/PROMPT_OVERRIDE.md``
    and is injected at runtime ahead of the base AGENT.md prompt body when the
    user runs a pipeline. The canonical AGENT.md is never mutated.

    Returns HTTP 413 when the content exceeds ``MAX_PROMPT_OVERRIDE_BYTES``.
    """
    if get_agent_by_id(agent_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown agent_id: {agent_id}",
        )

    content_bytes = request.content.encode("utf-8")
    if len(content_bytes) > MAX_PROMPT_OVERRIDE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Prompt override exceeds maximum size of {MAX_PROMPT_OVERRIDE_BYTES} bytes",
        )

    path = save_user_prompt_override(agent_id, request.content, user_id=current_user.id)
    logger.info(
        "Prompt override saved: user=%s agent=%s bytes=%d",
        current_user.id, agent_id, len(content_bytes),
    )
    return {"status": "saved", "agent_id": agent_id, "path": path}


@router.delete("/{agent_id}/prompt")
def remove_agent_prompt_override(
    agent_id: str,
    current_user: User = Depends(get_current_user),
):
    """Delete the caller's per-user prompt override, reverting to the base AGENT.md.

    Idempotent — returns ``{status: "not_found"}`` with HTTP 200 when no override exists.
    """
    deleted = delete_user_prompt_override(agent_id, user_id=current_user.id)
    return {"status": "deleted" if deleted else "not_found", "agent_id": agent_id}
