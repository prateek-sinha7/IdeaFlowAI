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
import logging
import re
from datetime import datetime

import yaml
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.entitlements import can_run_pipeline
from app.models.database import get_db
from app.models.user import User
from app.models.workflow_definition import WorkflowDefinition

logger = logging.getLogger("app.api.user_workflows")

router = APIRouter(prefix="/api/user-workflows", tags=["user-workflows"])


def _reject_both(body):
    """Refuse a request carrying BOTH ``manifest`` and ``selections`` (T36).

    They persist into the same ``manifest_json`` column, so accepting both means
    silently dropping one — the caller would get a 200 and a row that disagrees
    with what it sent. Naming both fields makes the conflict actionable.
    """
    if body.manifest is not None and body.selections is not None:
        raise ValueError(
            "'manifest' and 'selections' are mutually exclusive — they persist "
            "into the same column. Send the full step manifest, or the compact "
            "selections map, not both."
        )
    return body


_INSTANCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _compile_check_manifest(manifest: dict, source_label: str) -> None:
    """Compile the manifest the way the ENGINE will — reject it here if it won't.

    Not a re-implementation of any compiler rule: the manifest is handed to the
    real ``build_manifest_from_dict`` + ``WorkflowCompiler.compile`` pair, so the
    DAG topo-validation (``_validate_dag`` — duplicate agent ids, cycles), the
    fan-out upstream guard, the per-step capability checks and every other rule
    run exactly once, in the compiler, and can never drift from what the launch
    path enforces.

    The four top-level keys a canvas manifest never carries (``id`` /
    ``deliverable`` / ``planner`` / ``clarify``) are synthesized here with the
    SAME fallbacks the launch path uses (``run_commands.py`` — the
    USER_WORKFLOW_MANIFEST branch), which is what makes compiling at save time
    possible at all. ``trust="db"`` matches the launch path too, so a save can
    never pass a check the run would fail.
    """
    from agents.execution_engine.engine import (
        _CAPABILITY_REGISTRY,
        _WORKFLOW_COMPILER,
    )
    from agents.workflows.compiler import CompilerError
    from agents.workflows.manifest import (
        ManifestValidationError,
        build_manifest_from_dict,
    )

    raw = dict(manifest)
    raw.setdefault("id", "user-workflow-validate")
    raw.setdefault("deliverable", {"strategy": "streamed_text", "name": "output.md"})
    raw.setdefault("planner", "skip")
    raw.setdefault("clarify", {"mode": "skip", "defaults": []})
    raw.setdefault("capabilities", {})

    step_count = len(raw.get("steps") or [])
    try:
        parsed = build_manifest_from_dict(raw, source_label)
        _WORKFLOW_COMPILER.compile(parsed, _CAPABILITY_REGISTRY, trust="db")
    except (ManifestValidationError, CompilerError) as exc:
        # WARNING, not exception(): a refused save is the gate working, not a
        # crash — the user gets the same message in the 422. Log the compiler's
        # reason and the manifest SHAPE only; step prompts are user content and
        # must never reach the logs (LOG_LEVEL_APP / prod-INFO discipline).
        logger.warning(
            "manifest rejected at save: source=%s steps=%d reason=%s: %s",
            source_label,
            step_count,
            type(exc).__name__,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid workflow manifest ({source_label}): {exc}",
        ) from exc
    logger.debug(
        "manifest compiled at save: source=%s steps=%d", source_label, step_count
    )


def _validated_manifest(manifest: dict | None, source_label: str) -> dict | None:
    """Structurally validate a 012 step manifest before storing it (T36).

    Deliberately NOT a full ``build_manifest_from_dict`` round-trip. That parser
    requires ``id``/``deliverable``/``planner``/``clarify``, and what the canvas
    saves — like what T23's migration writes — is the partial ``{"steps": [...]}``
    shape; the missing keys are synthesized at LAUNCH from the base pipeline,
    which is the only point where they are known. Compiling here would reject
    every legitimate save.

    What IS checked here is the part that must not reach disk unvalidated:
    ``instance_id`` is the token ``artifact_name`` builds a filename from and the
    compiler mints ``custom-agent:<instance_id>`` from, so a traversal or a colon
    in it is F-02. ``artifact_name`` refuses those too — this is the earlier of
    the two gates, so the user sees it at save time.
    """
    if not manifest:
        return None
    steps = manifest.get("steps")
    if not isinstance(steps, list) or not steps:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid workflow manifest ({source_label}): "
            "'steps' must be a non-empty list",
        )

    def _check(step: object, depth: int = 0) -> None:
        if not isinstance(step, dict):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"invalid workflow manifest ({source_label}): "
                "every step must be a mapping",
            )
        instance_id = step.get("instance_id")
        if instance_id is not None and (
            not isinstance(instance_id, str) or not _INSTANCE_ID_RE.match(instance_id)
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"invalid workflow manifest ({source_label}): "
                f"instance_id {instance_id!r} must match ^[a-z0-9][a-z0-9-]*$",
            )
        subagents = step.get("subagents")
        # Walk exactly as deep as the compiler will accept, no deeper: the compiler
        # rejects anything past _MAX_SUBAGENTS_DEPTH nesting levels a moment later in
        # _compile_check_manifest, so recursing further here only risks the two bounds
        # drifting apart. Reading its constant rather than repeating the number is what
        # keeps them from drifting.
        from agents.workflows.compiler import _MAX_SUBAGENTS_DEPTH

        if isinstance(subagents, dict) and depth < _MAX_SUBAGENTS_DEPTH:
            for child in subagents.get("steps") or []:
                _check(child, depth + 1)

    for step in steps:
        _check(step)
    # A manifest that would fail the compiler's topo-validation must never reach
    # disk: the save would 200 and the FIRST RUN would be the thing that failed,
    # long after the edit that caused it.
    _compile_check_manifest(manifest, source_label)
    return manifest


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
    # Spec 012 (R-27/R-29, T36): the full step-based manifest ``{"steps": [...]}``
    # produced by the canvas once a node carries a skill, a prompt, or children.
    # It is a SIBLING of ``selections``, not a widening of it: both write the same
    # ``manifest_json`` column, but they are different shapes with different
    # validators, and one field carrying both told apart by sniffing is the
    # ambiguity FINDING-02 records. Supplying both is a 422 (see the validator).
    manifest: dict | None = None
    # Persisted UI-attached skills/hooks — same shape as the launch path's
    # attached_skills/attached_hooks (list[dict], see app/api/run_commands.py).
    # None/absent == none attached.
    attached_skills: list[dict] | None = None
    attached_hooks: list[dict] | None = None
    # Spec 016 — the BUILT-IN id this save overrides for its owner ("ppt").
    # Absent for an ordinary "save as a new workflow", which is what keeps the
    # mechanism inert for everyone who has not opted in. When present, the POST
    # UPSERTS: a second save of the same built-in updates the same row rather
    # than 409ing, which is the "once, or overwritten always" the feature needs.
    # A partial unique index on (user_id, overrides_pipeline_type) makes that a
    # database guarantee rather than a racy pre-check.
    overrides_pipeline_type: str | None = None
    # The base manifest's `version` at save time, so a later "the original has
    # changed since you customised it" notice has something to compare against.
    base_version: int | None = None

    @model_validator(mode="after")
    def _reject_manifest_and_selections(self) -> SaveUserWorkflowRequest:
        return _reject_both(self)


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
    # T36 — see SaveUserWorkflowRequest.manifest.
    manifest: dict | None = None
    attached_skills: list[dict] | None = None
    attached_hooks: list[dict] | None = None
    # Spec 016 — the override checkbox. The ONE flag both the read endpoints and
    # the launch resolve consult, so the screen and the run can never disagree
    # about which plan is in force. Only meaningful on a row that actually
    # overrides a built-in; setting it on an ordinary saved workflow is a no-op
    # by construction (nothing looks the row up without
    # `overrides_pipeline_type`), so it needs no extra guard.
    override_enabled: bool | None = None

    @model_validator(mode="after")
    def _reject_manifest_and_selections(self) -> UpdateUserWorkflowRequest:
        return _reject_both(self)


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
    # T36: the 012 manifest shape, populated when ``manifest_json`` holds a
    # step-based manifest instead of a selections map. Exactly one of
    # ``selections`` / ``manifest`` is ever non-None — they are the two shapes
    # the one column can hold.
    manifest: dict | None = None
    attached_skills: list[dict] | None = None
    attached_hooks: list[dict] | None = None
    # Spec 016 — None/False on every ordinary saved workflow.
    overrides_pipeline_type: str | None = None
    override_enabled: bool = False
    base_version: int | None = None
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
    selections: dict[str, dict] | None,
) -> None:
    """The CAP-03 server backstop — re-validate user-authored selections.

    Wizard-specific config stored under the ``_wizard`` key is stripped before
    compilation — it is pure FE metadata (templateId, designSystemId, brief,
    gateAgentIds) and is not a capability-selector, so the compiler must never
    see it.  The stripped map is compiled with ``trust="user"`` as normal.
    """
    if not selections:
        return  # no selections → nothing to re-validate (parity)

    # Strip the _wizard metadata key before capability-selector compilation.
    # This key is written by the PPT/Prototype wizard "Save workflow" button
    # and must round-trip untouched — it is NOT a capability reference.
    compile_selections = {k: v for k, v in selections.items() if k != "_wizard"}

    from agents.capabilities.registry import CapabilityRegistry
    from agents.workflows.compiler import CompilerError, WorkflowCompiler
    from agents.workflows.selections import (
        has_selections,
        synthesize_manifest,
        validate_selection_model_ids,
    )

    if not has_selections(compile_selections):
        return

    # CR-01 / WR-04: a per-step ``model`` selection bypasses the ``model_overrides``
    # chokepoint, so catalog-validate it here too (save == launch invariant). Reject
    # a disallowed / unknown model id at SAVE so it never persists as orphan config.
    _model_error = validate_selection_model_ids(compile_selections)
    if _model_error is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Rejected selection: {_model_error}",
        )

    manifest = synthesize_manifest(base_pipeline_type, agent_ids, compile_selections)
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
    # (NULL → None == no selections). Spec 012 (R-27/R-29) overloads the SAME
    # column with a full step-based manifest ({"steps": [...]}) once a per-step
    # migration (T23) or a custom-agent save has populated it — that shape is
    # NOT a `dict[str, dict]` selections map, so it is excluded here rather than
    # raising a pydantic validation error on this response field. The full
    # manifest is exposed separately via the ``workflow.yaml`` export (T22).
    stored = row.manifest_json
    _is_manifest = isinstance(stored, dict) and "steps" in stored
    selections = stored if isinstance(stored, dict) and not _is_manifest else None
    manifest = stored if _is_manifest else None
    return UserWorkflowResponse(
        id=row.id,
        name=row.name,
        description=row.description,
        base_pipeline_type=row.base_pipeline_type,
        agent_ids=agent_ids,
        model_overrides=row.model_overrides,
        selections=selections,
        manifest=manifest,
        attached_skills=row.attached_skills,
        attached_hooks=row.attached_hooks,
        overrides_pipeline_type=row.overrides_pipeline_type,
        override_enabled=bool(row.override_enabled),
        base_version=row.base_version,
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


def _migrate_attached_skills_to_steps(db: Session, row: WorkflowDefinition) -> None:
    """R-29 / AC-15 / F-07 — one-time fan-out of the legacy run-level
    ``attached_skills`` into every step's per-step ``skills`` list inside
    ``manifest_json``.

    Guard (F-07, the whole idempotency story): migrate ONLY when
    ``row.attached_skills`` is non-empty AND every step in ``manifest_json``
    has no ``skills`` key yet. That guard is what makes this safe to call on
    every read — a legacy row migrates exactly once (the first read adds the
    key to every step, so the second read's "every step absent" check fails
    and it becomes a no-op), and a row that already carries per-step skills
    (partially or fully) is left completely untouched.

    ``attached_skills`` is list[dict] (``{"id", "name", "content"}``, the
    run-level payload shape — see ``app/agents/skill_staging.py``); per-step
    ``manifest_json["steps"][i]["skills"]`` is list[str] of skill IDS (see
    ``agents/workflows/compiler.py`` and ``agents/factory.py::_resolve_step_skills``).
    The migration maps the former to the latter by pulling each payload's
    ``"id"``.

    ``attached_skills`` is RETAINED on the row afterwards (never dropped or
    nulled) but is no longer read at launch once migrated — per-step
    ``skills`` is authoritative from here on (Q3).
    """
    if not row.attached_skills:
        return
    manifest = row.manifest_json
    if not isinstance(manifest, dict):
        return
    steps = manifest.get("steps")
    if not isinstance(steps, list) or not steps:
        return
    if not all(isinstance(step, dict) and "skills" not in step for step in steps):
        return  # at least one step already carries a `skills` key — no-op (F-07)

    skill_ids = [
        payload["id"]
        for payload in row.attached_skills
        if isinstance(payload, dict) and payload.get("id")
    ]
    if not skill_ids:
        return

    new_steps = [
        {**step, "skills": list(skill_ids)} if isinstance(step, dict) else step
        for step in steps
    ]
    # Reassign a NEW dict (not mutate in place): the ORM's JSON column only
    # detects change via attribute reassignment, not in-place mutation of the
    # existing Python object.
    row.manifest_json = {**manifest, "steps": new_steps}
    db.commit()
    db.refresh(row)


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
    # This used to route through a one-entry "normalisation" map that mapped
    # od_prototype to itself — an identity function shaped like a translation.
    # With the od_ labels collapsed there is nothing to normalise: the declared
    # base type IS the entitlement key.
    allowed, reason = can_run_pipeline(current_user.tier, body.base_pipeline_type)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=reason)

    # agent_ids ⊆ allowed_custom_agent_ids(base) (launch predicate) — ONLY for an
    # agent_ids-backed row. A manifest-backed composition (spec 012: custom-agent
    # template instances, sub-agent trees) carries SYNTHETIC instance ids
    # (`agent-1`, `agent-2`, ...) minted client-side (`generateInstanceId`) —
    # they were never meant to satisfy this coarse "is this a real catalog
    # agent" allow-list, and rejecting them here made every composition with a
    # blank custom-agent node un-savable. The manifest's own steps are the real
    # security boundary for that shape (`_validated_manifest` here, and the
    # compiler's `trust="user"` step-by-step capability checks at launch) — this
    # allow-list stays load-bearing for the OTHER shape (a flat `agent_ids` list
    # naming real library agents directly), where it's the only check there is.
    if body.manifest is None:
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

    # CWF-001 D1: order-independent produces/consumes satisfiability check +
    # producer-first pre-sort (via the app-layer helper — this module honors its
    # "MUST NOT import agents.execution_engine" convention by going through
    # composition_order, not the resolver directly). A consumer-before-producer
    # order is repaired to a runnable producer-first order and PERSISTED sorted; a
    # genuinely-unsatisfiable set (a consumed non-exempt type no selected agent
    # produces, or a real cycle) is rejected 422 BEFORE any row is created — so a
    # saved row can never launch into a runtime "Workflow DAG is unsatisfiable"
    # death. The guard lives at CREATE + LAUNCH; the PATCH sibling cannot change
    # agent order (its request model omits agent_ids), so there is nothing to
    # reorder there.
    # `presort_agent_ids` resolves every id through `load_agent_spec` (a real
    # `AGENT.md` disk lookup) to read its produces/consumes for the DAG sort —
    # the same reason the allow-list above is skipped for a manifest-backed row,
    # this would raise on a synthetic `agent-1` id too. The manifest's own
    # `steps` order (as arranged in the canvas) is already the run order; there
    # is no separate producer/consumer resort to do for this shape.
    if body.manifest is None:
        from app.api.composition_order import (
            UnsatisfiableComposition,
            presort_agent_ids,
        )

        try:
            sorted_ids = presort_agent_ids(body.agent_ids)
        except UnsatisfiableComposition as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
    else:
        sorted_ids = body.agent_ids

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
    # ── Spec 016: an OVERRIDE save UPSERTS rather than 409ing ─────────────────
    # "Save once, or overwrite always": a second save of the same built-in must
    # update the same row. The partial unique index on
    # (user_id, overrides_pipeline_type) makes at-most-one a database guarantee;
    # this is the path that keeps the user from having to delete-then-resave.
    #
    # Deliberately BEFORE the duplicate-name check: an override is identified by
    # the built-in it overrides, never by its name, so re-saving under the same
    # name is the NORMAL case here and must not 409.
    _ov_target = body.overrides_pipeline_type
    if _ov_target:
        if _ov_target not in SUPPORTED_PIPELINE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown workflow to override: {_ov_target!r}",
            )
        prior = (
            db.query(WorkflowDefinition)
            .filter(
                WorkflowDefinition.user_id == current_user.id,
                WorkflowDefinition.source == "user",
                WorkflowDefinition.overrides_pipeline_type == _ov_target,
            )
            .first()
        )
        if prior is not None:
            prior.name = body.name
            prior.description = body.description
            prior.agents = json.dumps(sorted_ids)
            prior.base_pipeline_type = body.base_pipeline_type
            prior.model_overrides = body.model_overrides
            prior.manifest_json = (
                _validated_manifest(body.manifest, f"workflow:{body.name}")
                or body.selections
                or None
            )
            prior.attached_skills = body.attached_skills or None
            prior.attached_hooks = body.attached_hooks or None
            prior.base_version = body.base_version
            # Re-saving an override turns it back ON: the user just chose to
            # keep these steps, so leaving it switched off would silently
            # discard the save they were looking at.
            prior.override_enabled = True
            db.commit()
            db.refresh(prior)
            logger.info(
                "override: user %s updated their %s override (row %s)",
                current_user.id, _ov_target, prior.id,
            )
            return _project(prior)

    if existing and not _ov_target:
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
        # CWF-001 D1: persist the producer-first pre-sorted order (model_overrides /
        # selections are keyed by agent_id, so the reorder is safe).
        agents=json.dumps(sorted_ids),
        artifact_edges="[]",
        description=body.description,
        source="user",
        base_pipeline_type=body.base_pipeline_type,
        model_overrides=body.model_overrides,
        # EMP-03 (D-11): persist the compact selections map into the reused
        # dormant ``manifest_json`` column (zero migration). NULL == no selections.
        # T36: the column holds EITHER the compact selections map (EMP-03) or a
        # full step manifest (012). The request validator guarantees at most one
        # was supplied, so this `or` chain can never silently discard the other.
        manifest_json=(
            _validated_manifest(body.manifest, f"workflow:{body.name}")
            or body.selections
            or None
        ),
        attached_skills=(body.attached_skills or None),
        attached_hooks=(body.attached_hooks or None),
        # Spec 016 — NULL/False for every ordinary saved workflow.
        overrides_pipeline_type=_ov_target,
        override_enabled=bool(_ov_target),
        base_version=body.base_version,
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
    row = _owned(db, workflow_id, current_user)
    _migrate_attached_skills_to_steps(db, row)
    return _project(row)


@router.get("/{workflow_id}/workflow.yaml")
def export_user_workflow_yaml(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Render the stored manifest as YAML for viewing/download (R-28).

    Same ownership/authz guard as ``GET /{workflow_id}`` (``_owned`` — IDOR→404).
    A row with no ``manifest_json`` returns an empty YAML document (``""``)
    rather than 404 — the row itself exists and is owned by the caller, it
    simply has nothing to export yet (e.g. a workflow saved via
    ``agent_ids``/``selections`` only, before any per-step manifest was
    synthesized).
    """
    row = _owned(db, workflow_id, current_user)
    _migrate_attached_skills_to_steps(db, row)
    if not row.manifest_json:
        body = ""
    else:
        body = yaml.safe_dump(row.manifest_json, sort_keys=False)
    return Response(content=body, media_type="text/yaml")


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

    if body.override_enabled is not None:
        row.override_enabled = body.override_enabled

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

    if body.manifest is not None:
        # T36: a manifest edit replaces the column outright. An empty dict clears
        # it, mirroring the selections branch above.
        row.manifest_json = _validated_manifest(body.manifest, f"workflow:{row.id}")

    if body.attached_skills is not None:
        row.attached_skills = body.attached_skills or None

    if body.attached_hooks is not None:
        row.attached_hooks = body.attached_hooks or None

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
