"""Saved Workflows CRUD — owner-scoped ``/api/user-workflows`` (Phase 21).

A *saved workflow* is pure data — ``{base_pipeline_type, agent_ids,
model_overrides}`` — persisted by REUSING the dormant ``workflows`` table
(``WorkflowDefinition``) as a ``source="user"`` row (REUSE-TABLE-INV12). Launch
replays the saved composition through the EXISTING run path (SC-001); this
router adds NO engine edit and NO new capability grant (T-21-04 accept).

Security (every handler):
  * **Auth** — ``Depends(get_current_user)`` on every route (CRUD-OWNER-SCOPED).
  * **IDOR → 404** (T-21-01) — GET/PATCH/DELETE ``/{id}`` filter
    ``id == :id AND user_id == current_user.id``; a missing or cross-owner row
    resolves to 404, never 403/leak (the ``runs.py`` ownership pattern). The
    list query additionally scopes ``source == "user"`` so file-backed manifest
    rows in the shared table never surface here.
  * **Save == launch validation** (T-21-02 / SECURITY-REVALIDATE) — POST (and
    PATCH when ``model_overrides`` changes) re-uses the EXACT launch predicates:
    ``base_pipeline_type ∈ SUPPORTED_PIPELINE_TYPES``,
    ``agent_ids ⊆ allowed_custom_agent_ids(base)``,
    ``model_overrides`` validated by the same two-check allow-list the websocket
    launch path uses, and the ``can_run_pipeline`` entitlement gate. A saved row
    can never carry something launch would reject. The launch path itself stays
    UNCHANGED and re-validates at run time against the LIVE allow-list (T-21-03),
    so a since-disallowed agent/model is still rejected at launch.
  * **Self-id stamp** (T-21-05) — inserts stamp
    ``user_id = owner_id = workspace_id = current_user.id``, ``source="user"``,
    ``artifact_edges="[]"`` (no constraint relaxation). Name uniqueness is
    enforced per-user at the API (the shared table also holds ``source="file"``
    rows, so this is NOT a DB constraint).

Ports & Adapters (PORTS-ADAPTERS): this module lives in ``app.*`` and reads the
registry / loader / model-catalog / entitlements (the legal ``app → agents``
direction). It MUST NOT import ``agents.execution_engine``.
"""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.entitlements import can_run_pipeline
from app.models.database import get_db
from app.models.user import User
from app.models.workflow_definition import WorkflowDefinition

router = APIRouter(prefix="/api/user-workflows", tags=["user-workflows"])


# --- Request / Response Schemas -------------------------------------------


class SaveUserWorkflowRequest(BaseModel):
    """POST body — the saved composition (pure data)."""

    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    base_pipeline_type: str
    # WR-02: a saved workflow must carry ≥1 agent — an empty list persists an
    # unrunnable orphan row (the launch path can never run it). The subset check
    # below is trivially satisfied by an empty list, so guard it at the schema.
    agent_ids: list[str] = Field(min_length=1)
    model_overrides: dict[str, str] | None = None
    # EMP-03 (D-11): the compact per-step capability-selections map
    # ``{agent_id: {validators?, gates?, model?, retry?, ...}}`` (see
    # ``agents.workflows.selections``). Persisted into the reused
    # ``workflows.manifest_json`` column (zero migration). ``None`` / absent ==
    # "no selections" (parity with a P21 saved workflow). Re-validated at SAVE
    # (and again at LAUNCH) by compiling the synthesized manifest with
    # ``trust="user"`` — the CAP-03 server backstop (the FE lock is advisory only).
    selections: dict[str, dict] | None = None


class UpdateUserWorkflowRequest(BaseModel):
    """PATCH body — rename + optional description / model_overrides / selections edit.

    Every field is optional; an absent field leaves the stored value untouched.
    When ``model_overrides`` is supplied it is re-validated against the stored
    composition (save == launch); when ``selections`` is supplied it is
    re-synthesized + re-compiled with ``trust="user"`` (the CAP-03 backstop).
    """

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    model_overrides: dict[str, str] | None = None
    selections: dict[str, dict] | None = None


class UserWorkflowResponse(BaseModel):
    """The saved-workflow row projected for the API."""

    id: str
    name: str
    description: str | None = None
    base_pipeline_type: str | None = None
    agent_ids: list[str]
    model_overrides: dict[str, str] | None = None
    # EMP-03: the round-tripped compact selections map (None when the row never
    # persisted any — ``manifest_json IS NULL``).
    selections: dict[str, dict] | None = None
    created_at: datetime
    updated_at: datetime


# --- Helpers ---------------------------------------------------------------


def _validate_model_overrides(
    model_overrides: dict, run_agent_ids: set[str]
) -> str | None:
    """Allow-list-validate ``{agent_id → model_id}`` — the SAME two checks the
    launch path enforces (``websocket._validate_model_overrides``): every key is
    one of THIS composition's agents, every value is an authoritative
    ``ModelCatalog`` id. Returns ``None`` when valid (or empty), else a
    human-readable error naming the bad value (caller raises 422).
    """
    if not model_overrides:
        return None
    if not isinstance(model_overrides, dict):
        return (
            f"model_overrides must be an object mapping agent_id to model_id "
            f"(got {type(model_overrides).__name__!r})"
        )
    from agents.capabilities.model_catalog import ModelCatalog

    allowed_model_ids = set(ModelCatalog().ids())
    for agent_id, model_id in model_overrides.items():
        if not isinstance(agent_id, str) or not isinstance(model_id, str):
            return (
                f"model_overrides entries must be string agent_id → string "
                f"model_id; got {agent_id!r}: {model_id!r}"
            )
        if agent_id not in run_agent_ids:
            return (
                f"model_overrides targets agent {agent_id!r}, which is not part "
                f"of this saved workflow's agents"
            )
        if model_id not in allowed_model_ids:
            return (
                f"model_overrides for agent {agent_id!r} requests model "
                f"{model_id!r}, which is not an allowed model"
            )
    return None


def _compile_selections_trust_user(
    base_pipeline_type: str,
    agent_ids: list[str],
    selections: dict | None,
) -> None:
    """The CAP-03 server backstop — re-validate user-authored selections.

    Synthesizes a ``WorkflowManifest`` from ``{base_pipeline_type, agent_ids,
    selections}`` (the SINGLE synth seam, shared with the launch handler) and
    compiles it with ``trust="user"``. The dormant ``_check_trust`` path
    (compiler.py) rejects any reference that is registered but NOT ``user_allowed``
    (a smuggled ``gate: security`` / exec / spawn / filesystem-MCP), and
    ``_compile_limits`` rejects a ceiling-raising Limits cap — each as a
    ``CompilerError`` NAMING the offending ``(kind, name)``. The FE lock is NOT a
    security control; THIS is.

    Raises:
        HTTPException(422): when the selections reference a non-user-allowed
            capability (or otherwise fail the trust=user compile) — the detail
            carries the compiler's ``(kind, name)`` message.
    """
    if not selections:
        return  # no selections → nothing to re-validate (parity)

    from agents.capabilities.registry import CapabilityRegistry
    from agents.workflows.compiler import CompilerError, WorkflowCompiler
    from agents.workflows.selections import (
        has_selections,
        synthesize_manifest,
        validate_selection_model_ids,
    )

    if not has_selections(selections):
        return

    # CR-01 / WR-04: a per-step ``model`` selection bypasses the ``model_overrides``
    # chokepoint, so catalog-validate it here too (save == launch invariant). Reject
    # a disallowed / unknown model id at SAVE so it never persists as orphan config.
    _model_error = validate_selection_model_ids(selections)
    if _model_error is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Rejected selection: {_model_error}",
        )

    manifest = synthesize_manifest(base_pipeline_type, agent_ids, selections)
    try:
        WorkflowCompiler().compile(
            manifest, CapabilityRegistry(), trust="user"
        )
    except CompilerError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Rejected selection: {exc}",
        ) from exc


def _project(row: WorkflowDefinition) -> UserWorkflowResponse:
    """Project an ORM row to the API response (parse ``agents`` JSON)."""
    try:
        agent_ids = json.loads(row.agents) if row.agents else []
    except (ValueError, TypeError):
        agent_ids = []
    # EMP-03: the compact selections map round-trips through ``manifest_json``
    # (NULL → None == no selections).
    selections = row.manifest_json if isinstance(row.manifest_json, dict) else None
    return UserWorkflowResponse(
        id=row.id,
        name=row.name,
        description=row.description,
        base_pipeline_type=row.base_pipeline_type,
        agent_ids=agent_ids,
        model_overrides=row.model_overrides,
        selections=selections,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _owned(db: Session, workflow_id: str, user: User) -> WorkflowDefinition:
    """Return the caller-owned ``source="user"`` row or raise 404 (IDOR→404)."""
    row = (
        db.query(WorkflowDefinition)
        .filter(
            WorkflowDefinition.id == workflow_id,
            WorkflowDefinition.user_id == user.id,
            WorkflowDefinition.source == "user",
        )
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saved workflow not found",
        )
    return row


# --- Endpoints -------------------------------------------------------------


@router.post("", response_model=UserWorkflowResponse, status_code=status.HTTP_201_CREATED)
def create_user_workflow(
    body: SaveUserWorkflowRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Persist a saved workflow as a ``source="user"`` row (owner-stamped).

    Validates the composition with the EXACT launch predicates before any row is
    created (fail-fast, no orphan rows).
    """
    from agents.loader import SUPPORTED_PIPELINE_TYPES
    from agents.registry import allowed_custom_agent_ids

    # base_pipeline_type ∈ SUPPORTED_PIPELINE_TYPES (launch predicate).
    if body.base_pipeline_type not in SUPPORTED_PIPELINE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported base_pipeline_type: {body.base_pipeline_type!r}",
        )

    # Entitlement gate (custom needs enterprise) — fail-fast before insert.
    allowed, reason = can_run_pipeline(current_user.tier, body.base_pipeline_type)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=reason)

    # agent_ids ⊆ allowed_custom_agent_ids(base) (launch predicate).
    allowed_ids = allowed_custom_agent_ids(body.base_pipeline_type)
    rejected = [aid for aid in body.agent_ids if aid not in allowed_ids]
    if rejected:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"agent_ids not allowed for {body.base_pipeline_type!r}: {rejected}",
        )

    # model_overrides — same two-check allow-list as launch.
    err = _validate_model_overrides(body.model_overrides or {}, set(body.agent_ids))
    if err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=err)

    # EMP-02 (CAP-03): re-validate user-authored per-step selections with
    # trust="user" BEFORE any row is created — a smuggled non-user-allowed
    # capability (or ceiling-raising Limits) is server-rejected here (fail-fast,
    # no orphan row). The SAME check re-fires at launch (a tampered row).
    _compile_selections_trust_user(
        body.base_pipeline_type, body.agent_ids, body.selections
    )

    # Per-user name uniqueness (API-level; the shared table also holds file rows).
    existing = (
        db.query(WorkflowDefinition)
        .filter(
            WorkflowDefinition.user_id == current_user.id,
            WorkflowDefinition.source == "user",
            WorkflowDefinition.name == body.name,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A saved workflow named {body.name!r} already exists",
        )

    row = WorkflowDefinition(
        # Self-id stamp (T-21-05): owner == workspace == user == caller.
        user_id=current_user.id,
        owner_id=current_user.id,
        workspace_id=current_user.id,
        name=body.name,
        agents=json.dumps(body.agent_ids),
        artifact_edges="[]",
        description=body.description,
        source="user",
        base_pipeline_type=body.base_pipeline_type,
        model_overrides=body.model_overrides,
        # EMP-03 (D-11): persist the compact selections map into the reused
        # dormant ``manifest_json`` column (zero migration). NULL == no selections.
        manifest_json=(body.selections or None),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _project(row)


@router.get("", response_model=list[UserWorkflowResponse])
def list_user_workflows(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List the caller's saved workflows (``source="user"`` only), newest first."""
    rows = (
        db.query(WorkflowDefinition)
        .filter(
            WorkflowDefinition.user_id == current_user.id,
            WorkflowDefinition.source == "user",
        )
        .order_by(WorkflowDefinition.updated_at.desc())
        .all()
    )
    return [_project(r) for r in rows]


@router.get("/{workflow_id}", response_model=UserWorkflowResponse)
def get_user_workflow(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Read one saved workflow; cross-owner / missing → 404 (IDOR→404)."""
    return _project(_owned(db, workflow_id, current_user))


@router.patch("/{workflow_id}", response_model=UserWorkflowResponse)
def update_user_workflow(
    workflow_id: str,
    body: UpdateUserWorkflowRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Rename + optional description / model_overrides edit; cross-owner → 404."""
    row = _owned(db, workflow_id, current_user)

    if body.name is not None and body.name != row.name:
        dup = (
            db.query(WorkflowDefinition)
            .filter(
                WorkflowDefinition.user_id == current_user.id,
                WorkflowDefinition.source == "user",
                WorkflowDefinition.name == body.name,
                WorkflowDefinition.id != row.id,
            )
            .first()
        )
        if dup:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A saved workflow named {body.name!r} already exists",
            )
        row.name = body.name

    if body.description is not None:
        row.description = body.description

    if body.model_overrides is not None:
        try:
            current_agent_ids = set(json.loads(row.agents) if row.agents else [])
        except (ValueError, TypeError):
            current_agent_ids = set()
        err = _validate_model_overrides(body.model_overrides, current_agent_ids)
        if err:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=err
            )
        row.model_overrides = body.model_overrides

    if body.selections is not None:
        # EMP-02/03: a selections edit re-compiles trust="user" (CAP-03 backstop)
        # against the row's stored composition, then persists the new map into
        # ``manifest_json``. An empty map clears the persisted selections.
        try:
            current_agent_ids_list = (
                json.loads(row.agents) if row.agents else []
            )
        except (ValueError, TypeError):
            current_agent_ids_list = []
        _compile_selections_trust_user(
            row.base_pipeline_type or "custom",
            current_agent_ids_list,
            body.selections,
        )
        row.manifest_json = body.selections or None

    db.commit()
    db.refresh(row)
    return _project(row)


@router.delete(
    "/{workflow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_user_workflow(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete one saved workflow; cross-owner / missing → 404, success → 204."""
    row = _owned(db, workflow_id, current_user)
    db.delete(row)
    db.commit()
    return None
