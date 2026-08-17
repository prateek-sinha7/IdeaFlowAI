"""Saved custom agents — owner-scoped ``/api/user-agents``.

A *saved agent* is pure data: ``{name, prompt, skills, icon, description}``. It
is what a user authored on the workflow canvas as a ``custom-agent`` instance
(spec 012) and wants back in a later workflow instead of retyping.

REUSE BY COPY, NOT BY REFERENCE. Selecting a saved agent seeds a NEW canvas node
whose ``display_name``/``prompt``/``skills`` are pre-filled from the row; the
workflow that results still compiles to an ordinary
``custom-agent:<instance_id>`` step. Nothing in the engine, the loader, the
compiler or ``allowed_custom_agent_ids`` learns about this table, and no run
ever resolves an agent id *through* it.

That is a deliberate boundary, not an oversight. Making a saved agent
launchable BY REFERENCE would mean teaching ``load_agent_spec`` to read the
database — a function called from ~14 sites across the engine hot path
(``engine.py``, ``kernel_services.py``, ``factory.py``, ``registry.py``) none of
which carry a DB session, plus an owner-scoping question at every one of them,
plus cache invalidation for ``_SPEC_CACHE`` (which has no eviction path) and for
``SUPPORTED_PIPELINE_TYPES``/``TEMPLATE_AGENT_IDS_BY_FLAG`` (computed once at
import, so a row created at runtime would be invisible to both). Copy-on-compose
delivers the user-visible feature — save it, see it in the library, drop it into
a new workflow — with none of that. Launch-by-reference is a separate decision
to take on its own merits.

Security (every handler):
  * **Auth** — ``Depends(get_current_user)`` on every route.
  * **IDOR → 404** — ``_owned`` filters ``id == :id AND user_id == :caller``; a
    missing OR cross-owner row is 404, never 403, so the endpoint never confirms
    that another user's agent exists (the ``user_workflows.py`` pattern).
  * **Self-id stamp** — inserts stamp ``user_id = owner_id = workspace_id =
    current_user.id`` (AUTHZ-01).
  * **Bounded input** — name/description/prompt are length-capped and the skill
    list is capped and validated against the live catalog, so a save cannot
    write an unbounded blob or smuggle an unknown id into a future manifest.

Ports & Adapters: this module lives in ``app.*`` and reads the skills catalog
(the legal ``app → agents`` direction). It MUST NOT import
``agents.execution_engine``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.models.database import get_db
from app.models.user import User
from app.models.user_agent import UserAgent

router = APIRouter(prefix="/api/user-agents", tags=["user-agents"])

# Bounds. A saved agent is a name, a prompt and a handful of skill ids — these
# caps are generous for that and still keep a single row from becoming a blob.
_MAX_NAME = 120
_MAX_DESCRIPTION = 500
_MAX_PROMPT = 20_000
_MAX_SKILLS = 32


class UserAgentBody(BaseModel):
    """Create/update payload."""

    name: str = Field(min_length=1, max_length=_MAX_NAME)
    prompt: str = Field(min_length=1, max_length=_MAX_PROMPT)
    skills: list[str] = Field(default_factory=list)
    icon: str | None = Field(default=None, max_length=16)
    description: str | None = Field(default=None, max_length=_MAX_DESCRIPTION)


class UserAgentResponse(BaseModel):
    """One saved agent as returned to the client."""

    id: str
    name: str
    prompt: str
    skills: list[str]
    icon: str | None = None
    description: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


def _owned(db: Session, agent_id: str, user: User) -> UserAgent:
    """Return the caller-owned row or raise 404 (IDOR→404).

    A cross-owner id is indistinguishable from a nonexistent one by design — a
    403 would confirm that some other user has an agent with this id.
    """
    row = (
        db.query(UserAgent)
        .filter(UserAgent.id == agent_id, UserAgent.user_id == user.id)
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saved agent not found",
        )
    return row


def _validate_skills(skills: list[str]) -> list[str]:
    """Reject unknown skill ids at save time, de-duplicating and preserving order.

    Skill ids are resolved against the catalog again at COMPOSE time
    (``agents/factory.py::_resolve_step_skills``), so an id that disappears from
    the catalog later degrades to "not staged" rather than breaking a run. This
    check exists for feedback, not for safety: saving a typo'd id would
    otherwise fail silently much later, inside a run, as a skill the model never
    saw.
    """
    if len(skills) > _MAX_SKILLS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"At most {_MAX_SKILLS} skills may be attached to one agent",
        )

    try:
        from app.agents.skills_catalog import list_global_skills

        known = {entry.id for entry in list_global_skills()}
    except Exception:  # noqa: BLE001 - a catalog read failure must not block a save
        return list(dict.fromkeys(skills))

    deduped = list(dict.fromkeys(skills))
    unknown = [s for s in deduped if s not in known]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown skill ids: {sorted(unknown)}",
        )
    return deduped


def _to_response(row: UserAgent) -> UserAgentResponse:
    return UserAgentResponse(
        id=row.id,
        name=row.name,
        prompt=row.prompt,
        skills=list(row.skills or []),
        icon=row.icon,
        description=row.description,
        created_at=row.created_at.isoformat() if row.created_at else None,
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
    )


def _reject_duplicate_name(
    db: Session, user: User, name: str, *, exclude_id: str | None = None
) -> None:
    """Per-user name uniqueness, enforced at the API rather than the DB.

    Two users may each have an agent called "Summariser"; one user may not have
    two. A DB unique constraint on (user_id, name) would express this, but the
    existing saved-workflow precedent enforces it here and a mismatch between
    the two would be more confusing than the duplication.
    """
    q = db.query(UserAgent).filter(
        UserAgent.user_id == user.id, UserAgent.name == name
    )
    if exclude_id is not None:
        q = q.filter(UserAgent.id != exclude_id)
    if q.first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A saved agent named {name!r} already exists",
        )


@router.post("", response_model=UserAgentResponse, status_code=status.HTTP_201_CREATED)
def create_user_agent(
    body: UserAgentBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserAgentResponse:
    name = body.name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="name must not be blank",
        )
    _reject_duplicate_name(db, current_user, name)
    skills = _validate_skills(body.skills)

    row = UserAgent(
        user_id=current_user.id,
        owner_id=current_user.id,
        workspace_id=current_user.id,
        name=name,
        prompt=body.prompt,
        skills=skills,
        icon=body.icon,
        description=body.description,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_response(row)


@router.get("", response_model=list[UserAgentResponse])
def list_user_agents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[UserAgentResponse]:
    rows = (
        db.query(UserAgent)
        .filter(UserAgent.user_id == current_user.id)
        .order_by(UserAgent.created_at.desc())
        .all()
    )
    return [_to_response(r) for r in rows]


@router.get("/{agent_id}", response_model=UserAgentResponse)
def get_user_agent(
    agent_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserAgentResponse:
    return _to_response(_owned(db, agent_id, current_user))


@router.patch("/{agent_id}", response_model=UserAgentResponse)
def update_user_agent(
    agent_id: str,
    body: UserAgentBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserAgentResponse:
    row = _owned(db, agent_id, current_user)
    name = body.name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="name must not be blank",
        )
    _reject_duplicate_name(db, current_user, name, exclude_id=agent_id)

    row.name = name
    row.prompt = body.prompt
    row.skills = _validate_skills(body.skills)
    row.icon = body.icon
    row.description = body.description
    db.commit()
    db.refresh(row)
    return _to_response(row)


@router.delete(
    "/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    # `response_class=Response` is required, not stylistic — without it FastAPI
    # infers a response model from the `-> None` annotation and asserts at import
    # that a 204 must carry no body. Same as delete_user_workflow.
    response_class=Response,
)
def delete_user_agent(
    agent_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete one saved agent; cross-owner / missing -> 404, success -> 204."""
    row = _owned(db, agent_id, current_user)
    db.delete(row)
    db.commit()
    return None
