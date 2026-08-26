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
``get_pipeline_agents``), never run-history DB rows.

The one DB read (spec 016) is the caller's own workflow OVERRIDES: a user may
save an edited copy of a built-in and have it served in place of the file
version. That read is owner-scoped, returns nothing for anyone who has not
saved one, and only ever replaces a plan's ``steps`` — every workflow-level
field still comes from the compiled manifest.

Security:
  * JWT-only (``Depends(get_current_user)``) — same posture as every other
    read endpoint.
  * Path traversal (T-04-13 / ASVS V5): ``{id}`` is resolved against the
    in-memory KNOWN manifest-id set (every id under ``agents/workflows/``
    that has a ``workflow.yaml``); an unknown id raises 404. The router NEVER
    opens a filesystem path built from an unvalidated id — ``compile_for_run``
    itself resolves a closed id-alias set before touching the filesystem.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from agents.execution_engine.engine import (
    _CAPABILITY_REGISTRY,
    _WORKFLOWS_DIR,
    compile_for_run,
)
from agents.execution_engine.overrides import merge_override_steps
from agents.loader import SUPPORTED_PIPELINE_TYPES, load_agent_spec
from agents.registry import get_pipeline_agents
from agents.workflows.manifest import load_manifest
from app.api._workflow_override import (
    find_override,
    list_overrides,
    override_steps,
)
from app.core.dependencies import get_current_user
from app.models.database import get_db
from app.models.user import User

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


# ---------------------------------------------------------------------------
# Known manifest-id set (closed allow-list) — the resolution target for {id}.
# ---------------------------------------------------------------------------
#
# FIX-051 / ISS-035: a "workflow" is defined by having an AUTHORED MANIFEST
# (agents/workflows/<id>/workflow.yaml) for a REAL pipeline type — the exact
# precondition compile_for_run() requires to succeed — not by PIPELINE_AGENTS
# having a key for it. PIPELINE_AGENTS is now itself derived from a folder
# scan (see agents/registry.py) and can contain a pipeline_type with real
# agents but no manifest yet (e.g. spec_kit): that's an in-progress pipeline,
# not a launchable workflow, and must not be exposed as one here. The
# SUPPORTED_PIPELINE_TYPES guard also keeps out non-pipeline manifest dirs
# under agents/workflows/ (e.g. the sample_* test fixtures used only by
# tests/agents/test_sample_*_workflow.py — ISS-015's documented invariant
# that they carry no product launch surface). This set is computed once from
# the filesystem at import time, still never from a user-supplied id, so a
# user-supplied id can never reach a filesystem read.


_logger = logging.getLogger(__name__)


def _discover_manifest_ids() -> frozenset[str]:
    """Discover authored manifest ids whose manifest ACTUALLY COMPILES.

    A dir can satisfy the folder-shape check (real pipeline type + a
    workflow.yaml present) while still authoring fields the compiler doesn't
    support yet (e.g. in-progress spec fixtures using `gates`/`route` ahead of
    compiler support). Such a manifest must never enter `_KNOWN_WORKFLOW_IDS`:
    every id in that set is later fed straight to `compile_for_run` by
    `list_workflows`, so a bad manifest bad here would 500 the whole listing
    for every user. Validate by compiling once at import time and drop (with
    a warning) any id that fails — flagged and excluded, not loaded.
    """
    candidates = (
        p.name
        for p in _WORKFLOWS_DIR.iterdir()
        if p.is_dir()
        and p.name in SUPPORTED_PIPELINE_TYPES
        and (p / "workflow.yaml").exists()
    )
    valid_ids = []
    for workflow_id in candidates:
        try:
            compile_for_run(workflow_id)
        except Exception as exc:
            _logger.warning(
                "Skipping workflow manifest %r — failed to compile: %s",
                workflow_id,
                exc,
            )
            continue
        valid_ids.append(workflow_id)
    return frozenset(valid_ids)


_KNOWN_WORKFLOW_IDS: frozenset[str] = _discover_manifest_ids()


# --- Response Schemas ---


class WorkflowStepSummary(BaseModel):
    """One step in the lightweight list view (id + display name + gate flag)."""

    agent_id: str
    name: str
    gate: Optional[str] = None


class ChainSource(BaseModel):
    """One entry of a workflow's ``chained_from`` consent list (Plan 34-01).

    ``id`` is the SOURCE workflow id allowed to offer "chain into me" after
    its own run completes. ``beta`` is an EDGE-level override (default
    False): True marks this ONE source->target relationship as "Coming
    Soon" even when the target workflow's own ``is_beta`` is False and it is
    otherwise fully launchable on its own catalog card. ``text`` is the action
    label for the chain-suggestion UI (e.g., "Ship the code").
    """

    id: str
    beta: bool = False
    text: str = ""


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
    is_beta: bool = False
    display_name: Optional[str] = None
    # short_name: a concise, noun-phrase label for tight UI surfaces (chiefly
    # the chain-suggestion chips) where display_name's full action-phrase
    # sentence is too long. Presentation only (Plan 34-01).
    short_name: Optional[str] = None
    icon: Optional[str] = None
    launch_surface: Optional[str] = None
    # chained_from: this workflow's own consent list (Plan 34-01) — REPLACES
    # the formerly frontend-hardcoded CHAIN_OPTIONS/CHAINABLE_FROM_TYPES
    # (frontend/src/lib/workflowChaining.ts). Backend is the sole source of
    # truth: a source workflow may only offer "chain into me" if MY manifest
    # lists it here. Empty list == nobody may chain into this workflow.
    chained_from: list[ChainSource] = Field(default_factory=list)
    # Spec 016 — this caller's override of this built-in, if any. Additive:
    # False/None for every user who has never saved one, so an older client and
    # an un-overridden workflow both see the payload they see today.
    # `is_overridden` reflects the ENABLED flag (what actually runs);
    # `has_override` is true for a saved-but-switched-off row, so the UI can
    # still render the checkbox unticked instead of losing the way back on.
    is_overridden: bool = False
    has_override: bool = False
    override_id: Optional[str] = None


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
    # skills: spec 012 per-step skills (R-01). Already compiled onto the Step
    # dataclass (agents/workflows/plan.py) but previously never left the
    # backend — a saved workflow's per-step skills were invisible to every
    # render surface, so they could only be seen by re-opening the composer.
    skills: list[str] = Field(default_factory=list)


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
    # The manifest's raw step dicts, verbatim (WorkflowManifest.steps). `steps`
    # above is the COMPILED projection — good for display, but lossy: it carries
    # no prompt, tools, instance_id, depends_on or route, so it cannot be turned
    # back into an editable workflow. The composer needs the authoring shape to
    # open an existing pipeline on its canvas; without it "open in canvas" either
    # starts blank or silently drops every step's prompt on save. Pure data,
    # already parsed and validated by load_manifest — no new derivation.
    # None when the manifest could not be read (the compiled view still returns).
    manifest_steps: list[dict] | None = None
    # Spec 016 — see WorkflowSummary for the flag semantics. `showing_original`
    # says WHICH plan this payload carries: true when the caller asked for
    # ?original=true, so the UI knows the steps below are the system version
    # even though `is_overridden` is true.
    is_overridden: bool = False
    has_override: bool = False
    override_id: Optional[str] = None
    showing_original: bool = False


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


def _spec_by_id(workflow_id: str, step_ids: list[str] | None = None) -> dict:
    """Map agent_id -> AgentSpec for a workflow's declared AGENT.md metadata.

    Sourced from ``get_pipeline_agents`` (discovery by ``pipeline_type``
    frontmatter), then completed from ``step_ids`` when the caller has the
    compiled plan.

    Discovery alone is INCOMPLETE for a workflow that REUSES an agent from
    another pipeline: an ``AGENT.md`` declares exactly one ``pipeline_type``, so
    ``ppt_v2``'s two reused ``ppt`` steps are absent from
    ``get_pipeline_agents("ppt_v2")`` and the screen reported "2 agents" for a
    four-step workflow (spec 017). Loading the missing ids directly is safe —
    they are the plan's own steps, already compiled and about to run.

    A step whose spec cannot be loaded is skipped, exactly as before: the caller
    degrades to the bare agent id rather than failing the whole listing.
    """
    by_id = {s.id: s for s in get_pipeline_agents(workflow_id)}
    for agent_id in step_ids or []:
        if agent_id in by_id:
            continue
        try:
            by_id[agent_id] = load_agent_spec(agent_id)
        except Exception:  # noqa: BLE001 — mirrors the caller's degrade-to-id posture
            _logger.debug("workflow %s: no AGENT.md for step %s", workflow_id, agent_id)
    return by_id


# --- Endpoints ---


def _overridden_plan(compiled, row):
    """``compiled`` with the override's steps, or ``compiled`` unchanged.

    The single place the two read endpoints and the launch path agree on what
    "the override's plan" means. ``compiled`` is the lru_cached, process-shared
    object — ``merge_override_steps`` returns a NEW one and never mutates it.
    """
    steps = override_steps(row)
    if not steps:
        return compiled
    return merge_override_steps(compiled, steps, _CAPABILITY_REGISTRY)


@router.get("", response_model=list[WorkflowSummary])
def list_workflows(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List every authored workflow with manifest-derived metadata (API-01).

    One entry per authored manifest id (id, name, description, step summary) —
    see ``_KNOWN_WORKFLOW_IDS`` (FIX-051). The step summary derives from the
    COMPILED plan (the same source the detail endpoint uses) so the
    count/steps match the manifest. AGENT.md names/gates come from
    ``_spec_by_id``, falling back to the agent id when no spec is available.
    Reads only the compiled manifests + registry — no DB query.
    """
    # Spec 016: one query for the caller's overrides, not one per built-in.
    # Empty for everyone who has never saved one, which makes every lookup below
    # a dict miss and the whole listing byte-identical to before.
    overrides = list_overrides(db, current_user)

    out: list[WorkflowSummary] = []
    for workflow_id in sorted(_KNOWN_WORKFLOW_IDS):
        compiled = compile_for_run(workflow_id)
        _ov_row = overrides.get(workflow_id)
        _ov_enabled = bool(_ov_row is not None and _ov_row.override_enabled)
        if _ov_enabled:
            compiled = _overridden_plan(compiled, _ov_row)
        spec_by_id = _spec_by_id(workflow_id, [st.agent_id for st in compiled.steps])
        # Additive manifest read for the declared catalog metadata (Plan 20-01).
        # list_workflows iterates the real manifest ids (never aliases), so we
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
                name=(manifest.name if manifest else None) or _display_name(workflow_id),
                description=(
                    (manifest.description if manifest else None)
                    or _describe(workflow_id, step_specs)
                ),
                step_count=len(compiled.steps),
                steps=steps,
                user_launchable=bool(manifest and manifest.user_launchable),
                is_beta=bool(manifest and manifest.is_beta),
                # Carry ONLY the manifest's EXPLICIT display_name (None unless a
                # YAML declares one). Do NOT coalesce to _display_name(id): the
                # title-cased raw id ("Mulesoft To Springboot") must NEVER be the
                # rendered label (UI-SPEC §4 / WR-01). When None, the FE falls
                # back to the friendly WORKFLOW_LABELS map; an authored
                # display_name still wins.
                display_name=(manifest.display_name if manifest else None),
                short_name=(manifest.short_name if manifest else None),
                icon=manifest.icon if manifest else None,
                launch_surface=manifest.launch_surface if manifest else None,
                chained_from=(
                    [
                        ChainSource(id=entry.id, beta=entry.beta, text=entry.text)
                        for entry in manifest.chained_from
                    ]
                    if manifest
                    else []
                ),
                is_overridden=_ov_enabled,
                has_override=_ov_row is not None,
                override_id=(_ov_row.id if _ov_row is not None else None),
            )
        )
    return out


@router.get("/{workflow_id}", response_model=WorkflowDetail)
def get_workflow(
    workflow_id: str,
    original: bool = Query(
        False,
        description=(
            "Force the SYSTEM version even when this caller has an enabled "
            "override — the read-only 'compare with original' view. Never use "
            "it to decide which plan RUNS; that is override_enabled on the row."
        ),
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the full compiled definition for a known workflow id (API-01).

    Resolves ``{id}`` against the in-memory KNOWN manifest-id set; an unknown
    id raises 404 (path-traversal mitigation, T-04-13 — never reads a
    filesystem path built from an unvalidated id). For a known id, compiles the manifest and
    projects the per-step configs (strategy, gates, validators, skills, task_source),
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

    # Spec 016 — this caller's override. `find_override` (not `resolve_override`)
    # so a saved-but-switched-off row still reports has_override and the UI can
    # render the checkbox unticked instead of losing the way back on.
    _ov_row = find_override(db, current_user, workflow_id)
    _ov_enabled = bool(_ov_row is not None and _ov_row.override_enabled)
    _showing_original = bool(_ov_enabled and original)
    if _ov_enabled and not original:
        compiled = _overridden_plan(compiled, _ov_row)

    # Map agent_id -> AgentSpec for the AGENT.md-declared metadata (name/role/
    # order/gate) that complements the compiled Step (strategy/gates/etc.).
    spec_by_id = _spec_by_id(workflow_id, [st.agent_id for st in compiled.steps])
    # Ordered by the PLAN, not by dict insertion: the reused-agent completion
    # above appends after the discovered ones, so ppt_v2's four steps would
    # otherwise read qa, code-gen, analyst, composer — the run order inverted.
    step_specs = [spec_by_id[st.agent_id] for st in compiled.steps if st.agent_id in spec_by_id]

    # Load manifest for authored metadata (name, display_name, description)
    try:
        manifest = load_manifest(workflow_id, _WORKFLOWS_DIR)
    except Exception:
        manifest = None

    steps: list[WorkflowStepDetail] = []
    for idx, step in enumerate(compiled.steps, start=1):
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
                # A COMPOSED step is an instance of the `custom-agent` template
                # (`custom-agent:<instance_id>`) and has no AGENT.md, so `spec` is
                # None for it and every field below used to collapse to the raw id /
                # "" / 0 — a launch panel built from this projection showed five rows
                # called "custom-agent:emoji" with no ordering. The manifest's own
                # label lives on the compiled step as `display_name` (the same field
                # the engine overlays onto the runtime AgentSpec), so prefer it, and
                # fall back to the AGENT.md spec for ordinary declared agents.
                name=(getattr(step, "display_name", "") or (spec.name if spec else step.agent_id)),
                role=spec.role if spec else "",
                # Read top-to-bottom: `compiled.steps` IS the execution sequence, so
                # a step's position in it is its order. Previously this returned the
                # AGENT.md `order` for declared agents and 0 for composed ones — two
                # different ordering systems in one list, with every composed step
                # tied at 0. The position is both consistent and closer to the truth,
                # since the compiled sequence is what actually runs.
                order=idx,
                strategy=step.strategy,
                gates=list(step.gates),
                validators=list(step.validators),
                compaction=step.compaction,
                task_source=ts,
                declared_gate=spec.gate if spec else None,
                skills=list(getattr(step, "skills", None) or []),
            )
        )

    return WorkflowDetail(
        id=compiled.id,
        name=(manifest.name if manifest else None) or _display_name(workflow_id),
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
        # When the override is in force, the raw steps must be ITS steps: this is
        # the authoring shape the composer reopens from and the wizard projects
        # into its Advanced roster (spec 016 T8). Serving the file's steps here
        # while `steps` above shows the override's would put the two halves of
        # the same payload in disagreement.
        manifest_steps=(
            list(override_steps(_ov_row) or [])
            if (_ov_enabled and not original)
            else (list(manifest.steps) if manifest else None)
        ),
        is_overridden=_ov_enabled,
        has_override=_ov_row is not None,
        override_id=(_ov_row.id if _ov_row is not None else None),
        showing_original=_showing_original,
    )
