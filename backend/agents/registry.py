"""agents/registry.py — Slim pipeline-to-agent-ID registry.

Contains ONLY pipeline-to-ID mappings and the get_pipeline_agents() function.
No AgentDefinition instances, no prompt strings, no DEEP_AGENT_CONFIG dicts.

Public API:
    PIPELINE_AGENTS           — ordered agent ID lists per pipeline type
    REVISION_BASE_MAP         — maps revision pipeline types to their base types
    get_pipeline_agents(pipeline_type) -> list[AgentSpec]
"""

import logging

from agents.loader import (
    AgentSpec,
    AgentSpecError,
    SUPPORTED_PIPELINE_TYPES,
    TEMPLATE_AGENT_IDS_BY_FLAG,
    list_agent_ids,
    load_agent_spec,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pipeline-to-agent-ID mappings (FIX-051 / ISS-035)
# ---------------------------------------------------------------------------
#
# PIPELINE_AGENTS is DERIVED, not hand-maintained: it is built once at import
# time by scanning agents/prompts/ for every pipeline_type any AGENT.md
# actually declares, then loading each one's agents (via the loader's
# list_agent_ids). This is the same dynamic scan get_pipeline_agents()
# already trusts. Before FIX-051 this was a ~150-line
# hand-typed literal that agent-library listing (get_all_agents_flat),
# security allow-listing (allowed_custom_agent_ids), and workflow discovery
# (app/api/workflows.py) all read directly — so an agent added on disk with
# correct AGENT.md frontmatter (pipeline_type + order) was live for pipeline
# EXECUTION but invisible everywhere else until someone remembered to also
# hand-edit this dict. Now adding an AGENT.md is sufficient; there is nothing
# left to forget.


# od_* pipeline aliases that are NOT real PIPELINE_AGENTS keys — resolved to a
# base pipeline (by callers, before ever indexing PIPELINE_AGENTS) rather than
# scanned for agents. No AGENT.md declares pipeline_type: od_prototype (they
# declare pipeline_type: prototype); od_prototype is purely a run-label alias.
#
# NOTE: "ppt"/"od_ppt" and "ppt_revision"/"od_ppt_revision" used to be a
# SECOND, different kind of dual-id situation — two really-distinct manifests
# (not an alias) that both happened to produce presentation decks. That has
# been collapsed: the real od_ppt/od_ppt_revision agent sets now declare
# pipeline_type: ppt / ppt_revision directly (their AGENT.md frontmatter was
# edited), and the legacy ppt/ppt_revision manifests + agents were DELETED.
# So "ppt" and "ppt_revision" are ordinary, non-aliased PIPELINE_AGENTS keys —
# WR-01 is closed at the root instead of papered over with an alias line.
#
# No od_ppt/od_ppt_revision alias is kept: v1 has not shipped, so no persisted
# run carries those labels and there is nothing to stay compatible with. They
# are gone from the tier entitlements and from SUPPORTED_PIPELINE_TYPES too.
# ``od_prototype`` is gone for the same reason, and by the same method. It was
# the last alias, and it cost more than it saved: the label owned the LAUNCH
# half of the prototype lifecycle (only ``od_prototype`` loaded template context
# — see the eligibility note that used to live in app/api/launch_context.py)
# while ``prototype_revision`` owned the REVISION half, and the two were bridged
# by hand-written remap tables in the API layer that existed in only one of the
# two revision entry points. A run launched as ``od_prototype`` therefore could
# not be revised over REST at all. Collapsing the label to ``prototype`` deletes
# the split, both remap tables, and the registry-vs-compiler disagreement it
# caused (``get_pipeline_agents`` never resolved aliases; ``compile_for_run``
# did, so one label meant "5 agents" to one and "unknown" to the other).
#
# Persisted rows carrying the old label are migrated in-place — see
# alembic/versions/0037_collapse_od_prototype_label.py — so nothing needs to
# stay compatible with it at runtime. (That migration was authored as ``0032``
# and re-homed to ``0037`` after the ID collided with the cognito branch's own
# ``0032``; the file name here is the corrected one.)
#
# The dict stays (empty) rather than being deleted: ``resolve_alias`` is a
# declared port with real callers, and an empty table makes it the identity
# function. A future legacy label gets one line here and nothing else changes.
_OD_ALIAS_BASE: dict[str, str] = {}


def _discover_pipeline_agents() -> dict[str, list[str]]:
    """Scan agents/prompts/ once and bucket agents by their own pipeline_type.

    Single source of truth: each AGENT.md's own `pipeline_type` + `order`
    frontmatter. Replaces the former hand-maintained literal dict.

    The KEY set is ``SUPPORTED_PIPELINE_TYPES``, which is itself DERIVED from
    disk (workflow.yaml dirs ∪ pipeline_types declared by AGENT.md files ∪ the
    two run-label aliases — see agents/loader.py). Nothing here is
    hand-maintained; the allow-list this loop used to iterate is gone.

    Deriving the keys from the DECLARED pipeline_types alone was tried and is
    WRONG: it silently drops every AGENT-LESS pipeline. `reverse_engineer`
    (a manifest with no agents) and `od_prototype_revision` (a pure run-label
    alias) have no AGENT.md declaring them, so they vanished from the dict
    entirely — turning ``PIPELINE_AGENTS[pt]`` from an empty list into a
    KeyError for callers that reasonably expect every supported type to be a
    key. The empty list is meaningful: "this pipeline exists and has no
    agents", which is not the same as "this pipeline does not exist".

    Per-pipeline behaviour (ascending-order sort, duplicate-order
    AgentSpecError, `template: true` skip) is whatever ``list_agent_ids``
    implements — nothing is reimplemented here.
    """
    return {
        pt: list_agent_ids(pt)
        for pt in sorted(SUPPORTED_PIPELINE_TYPES)
        if pt not in _OD_ALIAS_BASE
    }


PIPELINE_AGENTS: dict[str, list[str]] = _discover_pipeline_agents()


# ---------------------------------------------------------------------------
# Internal (non-user-runnable) pipelines
# ---------------------------------------------------------------------------
#
# Pipelines present in PIPELINE_AGENTS that are driven by a dedicated runtime
# (NOT the user-facing `run_pipeline` WS path / the ExecutionEngine), and must
# therefore never be selectable as a `run_pipeline` pipeline_type nor have their
# agents accepted in `run_pipeline.agent_ids`. `allowed_custom_agent_ids` returns
# ∅ for these (the security fallback), so any client supplying them is rejected.
#   - "chat": the free-chat `user_message` path → ChatRunner (Phase 7b).
_INTERNAL_PIPELINES: frozenset[str] = frozenset({"chat"})


# ---------------------------------------------------------------------------
# Non-linear context routing maps  — REMOVED (T014)
# ---------------------------------------------------------------------------
# PIPELINE_CONTEXT_MAPS has been retired. The Universal Execution_Engine now
# resolves inter-agent context routing via the typed produces/consumes
# contracts declared in each AGENT.md (see WorkflowResolver). The former
# app_builder context map was migrated into the `consumes` contracts on the
# 15 app_builder AGENT.md files by scripts/migrate_agent_contracts.py.


# ---------------------------------------------------------------------------
# Revision pipeline → base pipeline mapping
# ---------------------------------------------------------------------------

REVISION_BASE_MAP: dict[str, str] = {
    "ppt_revision": "ppt",
    "user_stories_revision": "user_stories",
    "prototype_revision": "prototype",
    "prototype_large_revision": "prototype",    # tiered large-revision manifest
    "prototype_feature_revision": "prototype",  # tiered feature-revision manifest
    "app_builder_revision": "app_builder",
    "custom_revision": "custom",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_pipeline_agents(pipeline_type: str) -> list[AgentSpec]:
    """Return AgentSpec objects for the pipeline, sorted by ascending order.

    Calls list_agent_ids(pipeline_type) from the Loader to discover agents,
    then loads each AgentSpec via load_agent_spec(). Results are sorted by
    AgentSpec.order in ascending order.

    Returns an empty list for unknown or unsupported pipeline types.

    Raises:
        FileNotFoundError: propagated from loader if an agent directory or
            AGENT.md file is missing.
        AgentSpecError: propagated from loader if an AGENT.md file is
            malformed or has invalid fields.
    """
    ids = list_agent_ids(pipeline_type)
    specs = [load_agent_spec(aid) for aid in ids]
    return sorted(specs, key=lambda s: s.order)


# ---------------------------------------------------------------------------
# Flat-list / by-id / allow-list helpers
# ---------------------------------------------------------------------------
#
# These three helpers replicate the contract the legacy
# ``app.agents.registry`` provided (``get_agent_by_id`` /
# ``get_all_agents_flat`` / ``allowed_custom_agent_ids``) but source their
# data from the REAL pipeline-to-ID maps above + the on-disk AGENT.md files
# (via the loader), so there is a single source of truth. Phase 6 (T3)
# repoints ``app/api/agents.py`` and ``app/api/websocket.py`` here.

def get_agent_by_id(agent_id: str) -> AgentSpec | None:
    """Return the AgentSpec for ``agent_id``, or ``None`` if it does not exist.

    Thin guard around ``load_agent_spec``: a missing agent directory/AGENT.md
    (``FileNotFoundError``) or a malformed AGENT.md (``AgentSpecError``) yields
    ``None`` rather than propagating. Matches the legacy contract used by
    ``app/api/agents.py`` (POST /skills) to validate that a client-supplied
    agent id actually exists.

    Note: ``PermissionError`` is intentionally NOT swallowed — an unreadable
    file is an operational fault, not a "no such agent" answer.
    """
    try:
        return load_agent_spec(agent_id)
    except (FileNotFoundError, AgentSpecError):
        return None


def get_all_agents_flat() -> list[AgentSpec]:
    """Return every pipeline agent as a flat, de-duplicated list of AgentSpecs.

    Iterates every pipeline in ``PIPELINE_AGENTS`` (base + revision + custom),
    loads each agent id via ``load_agent_spec``, and de-duplicates by ``id``
    (an agent may in principle appear in more than one pipeline). This spans
    ALL pipelines to match the intent of the legacy flat list (the full agent
    pool).

    Ordering is stable and deterministic: pipeline insertion order in
    ``PIPELINE_AGENTS``, then ascending ``order`` within each pipeline; the
    first pipeline to contribute a given id fixes that id's position.

    An id present in ``PIPELINE_AGENTS`` whose AGENT.md is missing or malformed
    is skipped with a warning (it cannot appear in a list of specs); this
    mirrors the loader's own tolerant scan in ``list_agent_ids``.
    """
    specs: list[AgentSpec] = []
    seen: set[str] = set()

    for pipeline_type, agent_ids in PIPELINE_AGENTS.items():
        # Load + sort this pipeline's agents by order for a stable contribution.
        pipeline_specs: list[AgentSpec] = []
        for agent_id in agent_ids:
            if agent_id in seen:
                continue
            try:
                pipeline_specs.append(load_agent_spec(agent_id))
            except (FileNotFoundError, AgentSpecError):
                logger.warning(
                    "get_all_agents_flat: skipping agent %r in pipeline %r "
                    "(load failed)",
                    agent_id,
                    pipeline_type,
                )
                continue

        for spec in sorted(pipeline_specs, key=lambda s: s.order):
            if spec.id in seen:
                continue
            seen.add(spec.id)
            specs.append(spec)

    # Template agents (spec 012): excluded from PIPELINE_AGENTS membership — the
    # engine asserts compiled-steps == membership, and a template is never a step
    # — but they belong in the FLAT pool, because that is what the composer's
    # agent picker reads. A blank custom agent the user cannot select is useless.
    # Sourced from the loader's cached TEMPLATE_AGENT_IDS_BY_FLAG (computed once
    # at import time — replaces the former hand-maintained template-id name
    # list, see AgentSpec.template) rather than re-scanning disk per call.
    for template_id in sorted(TEMPLATE_AGENT_IDS_BY_FLAG):
        if template_id in seen:
            continue
        try:
            specs.append(load_agent_spec(template_id))
            seen.add(template_id)
        except (FileNotFoundError, AgentSpecError):
            logger.warning(
                "get_all_agents_flat: skipping template agent %r (load failed)",
                template_id,
            )

    return specs


def allowed_custom_agent_ids(pipeline_type: str) -> set[str]:
    """Return the agent IDs a client may legitimately supply in
    ``run_pipeline.agent_ids`` for ``pipeline_type``.

    Replicates the legacy ``app.agents.registry.allowed_custom_agent_ids``
    branch semantics, but sourced from the REAL ``PIPELINE_AGENTS`` + the real
    ``"custom"`` pipeline, and with the od_ gaps fixed. The branch partition is
    DERIVED from the registry (revision = ``*_revision`` suffix; base = the
    remaining non-empty, non-custom pipelines) rather than a hand-maintained
    list, so adding/removing a pipeline does not require editing this function.

    Branches:
      * od_ alias (``od_prototype``) → resolved to its base pipeline
        (``prototype``) and re-evaluated.
      * base pipeline (user_stories / ppt / prototype / app_builder /
        mulesoft_to_springboot / dotnet_to_azure):
        ``set(PIPELINE_AGENTS[base]) | set(PIPELINE_AGENTS["custom"])`` — the
        pipeline's own agents plus the custom-utility pool the UI exposes.
        Deliberately NOT unioned with any OTHER base pipeline's own agents:
        each base pipeline's tier entitlement (``can_run_pipeline``) is
        checked against its OWN ``pipeline_type`` only, never against the
        origin pipeline of an individual ``agent_id`` — so unioning in e.g.
        ``app_builder``'s or ``custom``'s own agents here would let a
        lower-tier user reach pro/enterprise-only agents through a
        basic-tier pipeline's ``run_pipeline``/save-workflow call. This was
        tried (KAN-75, 2026-06-24) and reverted: it is a real cross-pipeline
        injection / entitlement bypass, not a supported feature.
      * revision pipeline (any ``*_revision``):
        ``set(PIPELINE_AGENTS[that_revision])`` only. Revisions are
        intentionally tight (the revision flow assumes a fixed agent shape and
        the UI does not let the user inject agents into a revision run).
      * ``"custom"``: the custom-utility pool ONLY —
        ``set(PIPELINE_AGENTS["custom"])``. A ``custom`` run is assembled by
        the user from the agent library; base-pipeline agents (ppt-composer,
        app-code-generator, …) run only inside their own pipeline. (Same
        entitlement-bypass reasoning as the base-pipeline branch above:
        unioning in every base pipeline's agents here would let ANY tier
        reach ``app_builder``-only agents merely by naming ``custom`` as the
        pipeline type, regardless of whether that tier is entitled to
        ``app_builder`` itself.)
      * unknown / unsupported (incl. the empty ``reverse_engineer`` pipeline):
        ``set()`` — the security fallback. The caller is still expected to
        reject unknown pipeline types up-front; this empty-set guarantees no
        agent_ids can be smuggled through under an unrecognized type.
    """
    # Resolve od_ aliases that are not real registry keys (od_prototype).
    pipeline_type = _OD_ALIAS_BASE.get(pipeline_type, pipeline_type)

    # Internal pipelines (e.g. "chat") are driven by a dedicated runtime, never
    # the user-facing run_pipeline path. They are present in PIPELINE_AGENTS
    # (single source of truth for membership), so the generic "base pipeline"
    # branch below would otherwise expose their agents as valid run_pipeline
    # agent_ids. Short-circuit to ∅ (the security fallback) so no chat agent can
    # be smuggled into a run_pipeline run.
    if pipeline_type in _INTERNAL_PIPELINES:
        return set()

    # Revision pipelines (tight): driven by the *_revision suffix so every
    # REVISION_BASE_MAP entry is covered generically. Their own agents only.
    if pipeline_type.endswith("_revision"):
        return set(PIPELINE_AGENTS.get(pipeline_type, []))

    if pipeline_type == "custom":
        # OPEN BY DESIGN: composing across pipelines is the point of the custom
        # workflow builder (spec 012), so this branch stays wide.
        #
        # Not an entitlement bypass TODAY only because `custom` is enterprise-only
        # (entitlements.py::TIER_PIPELINES) and enterprise already holds every
        # pipeline unioned here. LOAD-BEARING: granting `custom` to a tier that
        # lacks any of them turns this into a real bypass — narrow it to the
        # custom pool plus a per-agent origin-tier check before that happens.
        out: set[str] = set()
        for pt, ids in PIPELINE_AGENTS.items():
            if pt.endswith("_revision") or pt in _INTERNAL_PIPELINES:
                continue
            out |= set(ids)
        return out

    # Base pipelines (own agents ∪ custom pool). Derived: a present,
    # non-revision, non-custom, NON-EMPTY pipeline. The non-empty guard keeps
    # the agentless reverse_engineer pipeline out (→ falls through to ∅,
    # matching the legacy security fallback). od_ppt naturally lands here.
    base_agents = PIPELINE_AGENTS.get(pipeline_type)
    if base_agents:  # present and non-empty
        return set(base_agents) | set(PIPELINE_AGENTS.get("custom", []))

    # Unknown / unsupported / empty → security fallback.
    return set()
