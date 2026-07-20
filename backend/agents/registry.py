"""agents/registry.py — Slim pipeline-to-agent-ID registry.

Contains ONLY pipeline-to-ID mappings and the get_pipeline_agents() function.
No AgentDefinition instances, no prompt strings, no DEEP_AGENT_CONFIG dicts.

Public API:
    SUPPORTED_PIPELINE_TYPES  — frozenset of valid pipeline type strings
    PIPELINE_AGENTS           — ordered agent ID lists per pipeline type
    REVISION_BASE_MAP         — maps revision pipeline types to their base types
    get_pipeline_agents(pipeline_type) -> list[AgentSpec]
"""

import logging

from agents.loader import (
    AgentSpec,
    AgentSpecError,
    SUPPORTED_PIPELINE_TYPES,
    list_agent_ids,
    load_agent_spec,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pipeline-to-agent-ID mappings (FIX-051 / ISS-035)
# ---------------------------------------------------------------------------
#
# PIPELINE_AGENTS is DERIVED, not hand-maintained: it is built once at import
# time by scanning agents/prompts/ (via the loader's list_agent_ids) for every
# SUPPORTED_PIPELINE_TYPES value. This is the same dynamic scan
# get_pipeline_agents() already trusts. Before FIX-051 this was a ~150-line
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
# Declared here (ahead of _discover_pipeline_agents, which excludes these
# keys) so the two "alias" concepts — this one and the ppt/od_ppt one below —
# live together. (od_ppt and od_ppt_revision ARE real registry keys, handled
# by the general base/revision logic in allowed_custom_agent_ids, not here.)
_OD_ALIAS_BASE: dict[str, str] = {
    "od_prototype": "prototype",
}


def _discover_pipeline_agents() -> dict[str, list[str]]:
    """Scan agents/prompts/ for every SUPPORTED_PIPELINE_TYPES value.

    Single source of truth: each AGENT.md's own `pipeline_type` + `order`
    frontmatter. Replaces the former hand-maintained literal dict.
    """
    agents_map = {
        pt: list_agent_ids(pt)
        for pt in sorted(SUPPORTED_PIPELINE_TYPES)
        if pt not in _OD_ALIAS_BASE
    }
    # "ppt" is a legacy pipeline-id ALIAS for the od_ppt agent set: no AGENT.md
    # declares pipeline_type: ppt (they declare od_ppt, shared by both ids).
    # This is an id-aliasing decision, not agent data, so it stays one explicit
    # line here instead of being duplicated onto 3 AGENT.md files. Closes WR-01
    # at the root — the PIPELINE_AGENTS.get("ppt", []) fallbacks in engine.py,
    # websocket.py, and workflows.py now resolve correctly instead of hitting a
    # hand-typed duplicate list that could silently drift from the real
    # od_ppt agent set.
    agents_map["ppt"] = agents_map.get("od_ppt", [])
    return agents_map


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
    "app_builder_revision": "app_builder",
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
    if pipeline_type not in SUPPORTED_PIPELINE_TYPES:
        return []

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
    (an agent may appear in more than one pipeline — e.g. the od-ppt agents are
    shared by the ``ppt`` and ``od_ppt`` pipelines). This spans ALL pipelines
    to match the intent of the legacy flat list (the full agent pool).

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
      * base pipeline (real equivalents of user_stories / ppt / prototype /
        app_builder / mulesoft_to_springboot / dotnet_to_azure, AND ``od_ppt``):
        ``set(PIPELINE_AGENTS[base]) | set(PIPELINE_AGENTS["custom"])`` — the
        pipeline's own agents plus the custom-utility pool the UI exposes.
        Treating ``od_ppt`` as a base pipeline FIXES the legacy ``od_ppt → ∅``
        bug that rejected every od_ppt run supplying ``agent_ids``.
      * revision pipeline (any ``*_revision`` — incl. ``od_ppt_revision``):
        ``set(PIPELINE_AGENTS[that_revision])`` only. Revisions are
        intentionally tight (the revision flow assumes a fixed agent shape and
        the UI does not let the user inject agents into a revision run).
      * ``"custom"``: ``set(PIPELINE_AGENTS["custom"])`` — the custom-utility
        pool. (NOTE: the legacy implementation returned the union of ALL agents
        across ALL pipelines here; Phase 6 deliberately tightens this to the
        real ``custom`` pipeline per the migration spec. ``custom`` is therefore
        NOT part of the legacy-parity guarantee — base + revision pipelines are.)
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

    # Revision pipelines (tight): driven by the *_revision suffix so that BOTH
    # the REVISION_BASE_MAP entries AND od_ppt_revision (absent from that map)
    # are covered. Their own agents only.
    if pipeline_type.endswith("_revision"):
        return set(PIPELINE_AGENTS.get(pipeline_type, []))

    if pipeline_type == "custom":
        # The custom pipeline allows agents from the custom utility pool AND
        # from any base pipeline — this enables the "compose a custom workflow"
        # UI to include prototype, user_stories, ppt, app_builder agents.
        # We union ALL non-revision, non-internal pipeline agent lists.
        all_agents: set[str] = set(PIPELINE_AGENTS.get("custom", []))
        for pt, agent_list in PIPELINE_AGENTS.items():
            if pt.endswith("_revision") or pt in _INTERNAL_PIPELINES or pt == "custom":
                continue
            all_agents.update(agent_list)
        return all_agents

    # Base pipelines (own agents ∪ custom pool ∪ all other base pipeline agents).
    # The AgentLibrary UI allows adding any agent from any pipeline into any
    # base pipeline run, so we must accept cross-pipeline agent ids here.
    # This mirrors the "custom" branch behaviour for base pipelines.
    base_agents = PIPELINE_AGENTS.get(pipeline_type)
    if base_agents:  # present and non-empty
        all_allowed: set[str] = set(base_agents) | set(PIPELINE_AGENTS.get("custom", []))
        # Add agents from all other base (non-revision, non-internal, non-custom) pipelines
        for pt, agent_list in PIPELINE_AGENTS.items():
            if pt.endswith("_revision") or pt in _INTERNAL_PIPELINES or pt == "custom":
                continue
            all_allowed.update(agent_list)
        return all_allowed

    # Unknown / unsupported / empty → security fallback.
    return set()
