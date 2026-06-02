"""agents/registry.py — Slim pipeline-to-agent-ID registry.

Contains ONLY pipeline-to-ID mappings and the get_pipeline_agents() function.
No AgentDefinition instances, no prompt strings, no DEEP_AGENT_CONFIG dicts.

Public API:
    SUPPORTED_PIPELINE_TYPES  — frozenset of valid pipeline type strings
    PIPELINE_AGENTS           — ordered agent ID lists per pipeline type
    REVISION_BASE_MAP         — maps revision pipeline types to their base types
    get_pipeline_agents(pipeline_type) -> list[AgentSpec]
"""

from agents.loader import (
    AgentSpec,
    SUPPORTED_PIPELINE_TYPES,
    list_agent_ids,
    load_agent_spec,
)

# ---------------------------------------------------------------------------
# Pipeline-to-agent-ID mappings
# ---------------------------------------------------------------------------

PIPELINE_AGENTS: dict[str, list[str]] = {
    # ── User Stories pipeline — 6 agents ──────────────────────────────────
    "user_stories": [
        "domain-analyst",
        "epic-architect",
        "story-estimator",
        "nfr-specialist",
        "backlog-reviewer",
        "backlog-compiler",
    ],

    # ── User Stories Revision pipeline — 1 agent ──────────────────────────
    "user_stories_revision": [
        "user-story-revision-agent",
    ],

    # ── PPT pipeline — 4 agents ───────────────────────────────────────────
    "ppt": [
        "od-ppt-brief-analyst",
        "od-ppt-composer",
        "od-ppt-validator",
    ],

    # ── od_ppt pipeline (alias — same agents, own runner) ─────────────────
    "od_ppt": [
        "od-ppt-brief-analyst",
        "od-ppt-composer",
        "od-ppt-validator",
    ],

    # ── od_ppt revision pipeline — 1 agent ────────────────────────────────
    "od_ppt_revision": [
        "od-ppt-revision-agent",
    ],

    # ── PPT Revision pipeline — 2 agents ─────────────────────────────────
    "ppt_revision": [
        "ppt-revision-agent",
        "ppt-revision-assembler",
    ],

    # ── Prototype pipeline — Spec Kit Approach 2+3 ────────────────────────
    # Phase 1: Spec Writer generates spec.md
    # Phase 2: Task Planner decomposes into atomic tasks
    # Phase 3: Build Agent executes tasks incrementally
    # Phase 4: Validation Agent runs P0/P1 checks
    "prototype": [
        "prototype-specify",
        "prototype-plan",
        "prototype-build",
        "prototype-validate",
    ],

    # ── Prototype Revision pipeline — 1 agent ─────────────────────────────
    "prototype_revision": [
        "prototype-revision-agent",
    ],

    # ── App Builder pipeline — 15 agents ──────────────────────────────────
    "app_builder": [
        "material-analyzer",
        "app-user-stories",
        "app-system-design",
        "app-security-architecture",
        "app-ux-design",
        "app-api-design",
        "app-database-design",
        "app-code-generator",
        "app-feature-implementation",
        "app-infra-generator",
        "app-code-compliance",
        "app-test-implementation",
        "app-test-compliance",
        "app-devops",
        "app-sdlc-governance",
    ],

    # ── App Builder Revision pipeline — 1 agent ───────────────────────────
    "app_builder_revision": [
        "app-builder-revision-agent",
    ],

    # ── Mulesoft → Spring Boot pipeline — 13 agents ───────────────────────
    "mulesoft_to_springboot": [
        "mulesoft-inventory",
        "mulesoft-user-stories",
        "mulesoft-decomposition",
        "mulesoft-security-architecture",
        "mulesoft-springboot-scaffold",
        "mulesoft-feature-coding",
        "mulesoft-dataweave-translator",
        "mulesoft-aws-infra",
        "mulesoft-code-compliance",
        "mulesoft-test-implementation",
        "mulesoft-test-compliance",
        "mulesoft-validation",
        "mulesoft-sdlc-governance",
    ],

    # ── .NET → Azure pipeline — 13 agents ────────────────────────────────
    "dotnet_to_azure": [
        "dotnet-inventory",
        "dotnet-user-stories",
        "dotnet-azure-target-mapping",
        "dotnet-security-architecture",
        "dotnet-modernization",
        "dotnet-feature-coding",
        "dotnet-azure-bicep",
        "dotnet-azure-ai",
        "dotnet-code-compliance",
        "dotnet-test-implementation",
        "dotnet-test-compliance",
        "dotnet-validation",
        "dotnet-sdlc-governance",
    ],

    # ── Custom pipeline — 8 utility agents ───────────────────────────────
    "custom": [
        "market-research-agent",
        "swot-analyst",
        "roadmap-planner",
        "security-auditor",
        "test-case-generator",
        "performance-optimizer",
        "documentation-agent",
        "report-generator",
    ],

    # ── Reverse Engineer pipeline — agents TBD ────────────────────────────
    # (populated when AGENT.md files are created for this pipeline)
    "reverse_engineer": [],
}


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
