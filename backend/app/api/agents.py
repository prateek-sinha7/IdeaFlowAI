"""Agent Pipeline API — REST endpoints for agent management and workflow execution."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.agents.registry import get_pipeline_agents, get_all_agents_flat, get_agent_by_id
from app.agents.skills import get_skill_content, save_custom_skill, list_all_skills, delete_custom_skill
from app.core.dependencies import get_current_user
from app.models.user import User

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


class PipelineResponse(BaseModel):
    pipeline_type: str
    agents: list[AgentResponse]
    total_estimated_duration: float


class SkillRequest(BaseModel):
    agent_id: str
    content: str


class SkillResponse(BaseModel):
    agent_id: str
    content: str


# --- Endpoints ---

@router.get("/pipelines/{pipeline_type}", response_model=PipelineResponse)
def get_pipeline(
    pipeline_type: str,
    current_user: User = Depends(get_current_user),
):
    """Get all agents for a specific pipeline type."""
    agents = get_pipeline_agents(pipeline_type)
    skills = list_all_skills()

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
            has_skill=a.id in skills,
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
):
    """Get all available agents across all pipelines."""
    all_agents = get_all_agents_flat()
    skills = list_all_skills()

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
                "has_skill": a.id in skills,
            }
            for a in all_agents
        ],
        "total_count": len(all_agents),
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
    """Get all available skills."""
    skills = list_all_skills()
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
    """Get the skill content for a specific agent."""
    content = get_skill_content(agent_id)
    if content is None:
        content = ""
    return SkillResponse(agent_id=agent_id, content=content)


@router.post("/skills")
def create_skill(
    request: SkillRequest,
    current_user: User = Depends(get_current_user),
):
    """Create or update a custom skill for an agent."""
    path = save_custom_skill(request.agent_id, request.content)
    return {"status": "saved", "agent_id": request.agent_id, "path": path}


@router.delete("/skills/{agent_id}")
def remove_skill(
    agent_id: str,
    current_user: User = Depends(get_current_user),
):
    """Delete a custom skill."""
    deleted = delete_custom_skill(agent_id)
    return {"status": "deleted" if deleted else "not_found", "agent_id": agent_id}
