"""Workflow-definitions API endpoints (API-01 / D-01).

This router serves **manifest-derived workflow definitions** — the static
declaration of every authored workflow, NOT run-history. The run-history CRUD
that previously lived here was relocated to ``app/api/runs.py`` (Plan 04-05
Task 1 / D-02); this module was reclaimed for the composer, which reads the
available workflows dynamically from the compiled manifests instead of a
hardcoded type list (API-01).

Endpoints:
  * ``GET /api/workflows``        — list one entry per authored workflow
    (id, name, description, step summary), derived from the compiled manifests.
  * ``GET /api/workflows/{id}``   — the full compiled step configs (per-step
    agent_id, strategy, gates, validators, task_source; deliverable; declared
    context_providers) for a known workflow; 404 on an unknown id.

Source of truth is the **compiled manifests** (``compile_for_run`` +
``get_pipeline_agents``), never run-history DB rows — this router issues no
DB query at all.

Security:
  * JWT-only (``Depends(get_current_user)``) — same posture as every other
    read endpoint.
  * Path traversal (T-04-13 / ASVS V5): ``{id}`` is resolved against the
    in-memory KNOWN manifest-id set (the ``PIPELINE_AGENTS`` keys); an unknown
    id raises 404. The router NEVER opens a filesystem path built from an
    unvalidated id — ``compile_for_run`` itself resolves a closed id-alias
    set before touching the filesystem.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from agents.execution_engine.engine import _WORKFLOWS_DIR, compile_for_run
from agents.loader import load_agent_spec
from agents.registry import PIPELINE_AGENTS, get_pipeline_agents
from agents.workflows.manifest import load_manifest
from app.core.dependencies import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


# ---------------------------------------------------------------------------
# Known manifest-id set (closed allow-list) — the resolution target for {id}.
# Sourced from the single source of truth (PIPELINE_AGENTS keys); never a
# filesystem scan, so a user-supplied id can never reach a filesystem read.
# ---------------------------------------------------------------------------

_KNOWN_WORKFLOW_IDS: frozenset[str] = frozenset(PIPELINE_AGENTS.keys())


# --- Response Schemas ---


class WorkflowStepSummary(BaseModel):
    """One step in the lightweight list view (id + display name + gate flag)."""

    agent_id: str
    name: str
    gate: Optional[str] = None


class WorkflowSummary(BaseModel):
    """List-view metadata for one authored workflow.

    The catalog fields (Plan 20-01) are sourced from the DECLARED manifest flag —
    ``user_launchable`` gates whether the user-facing catalog shows the row (it
    does NOT authorize a run; launch stays tier-gated server-side, T-20-02). The
    sibling per-item trust-flag pattern is ``capabilities.py``'s ``user_allowed``.
    """

    id: str
    name: str
    description: str
    step_count: int
    steps: list[WorkflowStepSummary] = Field(default_factory=list)
    user_launchable: bool = False
    display_name: Optional[str] = None
    icon: Optional[str] = None
    launch_surface: Optional[str] = None


class WorkflowStepDetail(BaseModel):
    """Full compiled config for one step of a workflow definition."""

    agent_id: str
    name: str
    role: str
    order: int
    strategy: str
    gates: list[str] = Field(default_factory=list)
    validators: list[str] = Field(default_factory=list)
    compaction: Optional[str] = None
    task_source: Optional[dict] = None
    declared_gate: Optional[str] = None  # the AGENT.md frontmatter gate, if any


class WorkflowDeliverable(BaseModel):
    """The compiled deliverable spec for a workflow."""

    strategy: Optional[str] = None
    name: Optional[str] = None


class WorkflowDetail(BaseModel):
    """Full compiled definition for one workflow (GET /api/workflows/{id})."""

    id: str
    name: str
    description: str
    planner: str
    clarify_mode: str
    clarify_defaults: list[str] = Field(default_factory=list)
    context_providers: list[str] = Field(default_factory=list)
    deliverable: WorkflowDeliverable
    steps: list[WorkflowStepDetail] = Field(default_factory=list)


# --- Derivation helpers ---


def _display_name(workflow_id: str) -> str:
    """Turn a snake_case manifest id into a human-readable display name.

    e.g. ``mulesoft_to_springboot`` -> ``Mulesoft To Springboot``. The composer
    UI uses this; there is no separate name field on the manifest (INV-5 — the
    manifest is pure data, no presentation strings).
    """
    return workflow_id.replace("_", " ").title()


def _describe(workflow_id: str, step_specs: list) -> str:
    """Build a one-line step-summary description from the ordered agents.

    Empty-plan workflows (reverse_engineer, D-05) describe their TBD state.
    """
    if not step_specs:
        return "Workflow defined; agents TBD."
    names = " -> ".join(s.name for s in step_specs)
    return f"{len(step_specs)}-step workflow: {names}"


def _spec_by_id(workflow_id: str) -> dict:
    """Map agent_id -> AgentSpec for a workflow's declared AGENT.md metadata.

    Prefers ``get_pipeline_agents`` (discovery by ``pipeline_type`` frontmatter),
    but falls back to loading each agent by ``PIPELINE_AGENTS`` membership when
    discovery yields nothing — this handles ``ppt``, whose agents physically
    declare ``pipeline_type: od_ppt`` (shared with the od_ppt pipeline), so
    ``get_pipeline_agents("ppt")`` is empty. The same fallback the engine /
    WebSocket layer applies (WR-01). A spec that fails to load is skipped so a
    single bad AGENT.md never breaks the whole listing.
    """
    by_id = {s.id: s for s in get_pipeline_agents(workflow_id)}
    if by_id:
        return by_id
    for agent_id in PIPELINE_AGENTS.get(workflow_id, []):
        try:
            by_id[agent_id] = load_agent_spec(agent_id)
        except Exception:
            continue
    return by_id


# --- Endpoints ---


@router.get("", response_model=list[WorkflowSummary])
def list_workflows(
    current_user: User = Depends(get_current_user),
):
    """List every authored workflow with manifest-derived metadata (API-01).

    One entry per ``PIPELINE_AGENTS`` id (id, name, description, step summary).
    The step summary derives from the COMPILED plan (the same source the detail
    endpoint uses) so the count/steps match the manifest even when
    ``get_pipeline_agents`` is empty — e.g. ``ppt``, whose agents declare
    ``pipeline_type: od_ppt`` (WR-01). AGENT.md names/gates come from
    ``_spec_by_id`` (with the same membership fallback), falling back to the
    agent id when no spec is available. Reads only the compiled manifests +
    registry — no DB query.
    """
    out: list[WorkflowSummary] = []
    for workflow_id in PIPELINE_AGENTS:
        compiled = compile_for_run(workflow_id)
        spec_by_id = _spec_by_id(workflow_id)
        # Additive manifest read for the declared catalog metadata (Plan 20-01).
        # list_workflows iterates real PIPELINE_AGENTS keys (never aliases), so we
        # load by the real id directly. A single bad manifest must NOT break the
        # listing — degrade to defaults (mirrors the _spec_by_id try/except posture).
        try:
            manifest = load_manifest(workflow_id, _WORKFLOWS_DIR)
        except Exception:
            manifest = None
        step_specs = [
            spec_by_id[s.agent_id]
            for s in compiled.steps
            if s.agent_id in spec_by_id
        ]
        steps = [
            WorkflowStepSummary(
                agent_id=step.agent_id,
                name=(
                    spec_by_id[step.agent_id].name
                    if step.agent_id in spec_by_id
                    else step.agent_id
                ),
                gate=(
                    spec_by_id[step.agent_id].gate
                    if step.agent_id in spec_by_id
                    else None
                ),
            )
            for step in compiled.steps
        ]
        out.append(
            WorkflowSummary(
                id=workflow_id,
                name=_display_name(workflow_id),
                description=(
                    (manifest.description if manifest else None)
                    or _describe(workflow_id, step_specs)
                ),
                step_count=len(compiled.steps),
                steps=steps,
                user_launchable=bool(manifest and manifest.user_launchable),
                # Carry ONLY the manifest's EXPLICIT display_name (None unless a
                # YAML declares one). Do NOT coalesce to _display_name(id): the
                # title-cased raw id ("Mulesoft To Springboot") must NEVER be the
                # rendered label (UI-SPEC §4 / WR-01). When None, the FE falls
                # back to the friendly WORKFLOW_LABELS map; an authored
                # display_name still wins. `name` keeps _display_name for
                # back-compat consumers.
                display_name=(manifest.display_name if manifest else None),
                icon=manifest.icon if manifest else None,
                launch_surface=manifest.launch_surface if manifest else None,
            )
        )
    return out


@router.get("/{workflow_id}", response_model=WorkflowDetail)
def get_workflow(
    workflow_id: str,
    current_user: User = Depends(get_current_user),
):
    """Return the full compiled definition for a known workflow id (API-01).

    Resolves ``{id}`` against the in-memory KNOWN manifest-id set; an unknown
    id raises 404 (path-traversal mitigation, T-04-13 — never reads a
    filesystem path built from an unvalidated id). For a known id, compiles the manifest and
    projects the per-step configs (strategy, gates, validators, task_source),
    the deliverable, the clarify policy, and the declared context_providers.

    The ``prototype`` payload matches its manifest exactly (agents in
    registry order, gates, deliverable).
    """
    if workflow_id not in _KNOWN_WORKFLOW_IDS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown workflow id: {workflow_id}",
        )

    compiled = compile_for_run(workflow_id)
    # Map agent_id -> AgentSpec for the AGENT.md-declared metadata (name/role/
    # order/gate) that complements the compiled Step (strategy/gates/etc.).
    # Uses the membership fallback so 'ppt' (agents declare pipeline_type:
    # od_ppt) returns real names/roles/orders rather than agent-id stubs (WR-01).
    spec_by_id = _spec_by_id(workflow_id)
    step_specs = list(spec_by_id.values())

    steps: list[WorkflowStepDetail] = []
    for step in compiled.steps:
        spec = spec_by_id.get(step.agent_id)
        ts = None
        if step.task_source is not None:
            ts = {
                "kind": step.task_source.kind,
                "parser": step.task_source.parser,
                "target": step.task_source.target,
            }
        steps.append(
            WorkflowStepDetail(
                agent_id=step.agent_id,
                name=spec.name if spec else step.agent_id,
                role=spec.role if spec else "",
                order=spec.order if spec else 0,
                strategy=step.strategy,
                gates=list(step.gates),
                validators=list(step.validators),
                compaction=step.compaction,
                task_source=ts,
                declared_gate=spec.gate if spec else None,
            )
        )

    return WorkflowDetail(
        id=compiled.id,
        name=_display_name(workflow_id),
        description=_describe(workflow_id, step_specs),
        planner=compiled.planner,
        clarify_mode=compiled.clarify.mode,
        clarify_defaults=list(compiled.clarify.defaults),
        context_providers=list(compiled.context_providers),
        deliverable=WorkflowDeliverable(
            strategy=compiled.deliverable.strategy,
            name=compiled.deliverable.name,
        ),
        steps=steps,
    )
