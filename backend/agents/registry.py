"""agents/registry.py — Slim pipeline-to-agent-ID registry.

Contains ONLY pipeline-to-ID mappings and the get_pipeline_agents() function.
No AgentDefinition instances, no prompt strings, no DEEP_AGENT_CONFIG dicts.

Public API:
    SUPPORTED_PIPELINE_TYPES  — frozenset of valid pipeline type strings
    PIPELINE_AGENTS           — ordered agent ID lists per pipeline type
    PIPELINE_CONTEXT_MAPS     — non-linear context routing maps per pipeline type
    REVISION_BASE_MAP         — maps revision pipeline types to their base types
    get_pipeline_agents(pipeline_type) -> list[AgentSpec]
"""

from agents.loader import (
    AgentSpec,
    AgentSpecError,
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
        "ppt-content-strategist",
        "ppt-slide-architect",
        "ppt-code-generator",
        "ppt-assembler",
    ],

    # ── PPT Revision pipeline — 2 agents ─────────────────────────────────
    "ppt_revision": [
        "ppt-revision-agent",
        "ppt-revision-assembler",
    ],

    # ── Prototype pipeline — 4 agents ─────────────────────────────────────
    "prototype": [
        "requirements-analyst",
        "html-prototype-builder",
        "prototype-polisher",
        "prototype-finalizer",
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
# Non-linear context routing maps
# ---------------------------------------------------------------------------
# For pipelines where each agent needs a specific subset of prior-agent
# outputs (rather than all previous outputs), this map defines which upstream
# agent IDs each agent depends on.
#
# The app_builder pipeline has 15 agents. Without routing, context grows to
# 347K+ chars by agent 15, causing rate-limit / context-window errors.
# Each agent only receives the upstream outputs it actually needs.

PIPELINE_CONTEXT_MAPS: dict[str, dict[str, list[str]]] = {
    "app_builder": {
        # Agent 1: no upstream
        "material-analyzer": [],
        # Agent 2: needs architecture overview
        "app-user-stories": ["material-analyzer"],
        # Agent 3: needs architecture + user stories
        "app-system-design": ["material-analyzer", "app-user-stories"],
        # Agent 4: needs architecture + system design
        "app-security-architecture": ["material-analyzer", "app-system-design"],
        # Agent 5: needs architecture + user stories + system design
        # Prompt: "Using the user stories and the system design"
        "app-ux-design": ["material-analyzer", "app-user-stories", "app-system-design"],
        # Agent 6: needs architecture + user stories + system design
        # Prompt: "Using the user stories and system design"
        "app-api-design": ["material-analyzer", "app-user-stories", "app-system-design"],
        # Agent 7: needs architecture + system design + api contracts
        "app-database-design": ["material-analyzer", "app-system-design", "app-api-design"],
        # Agent 8: needs arch + system design + api + db (the four design pillars)
        "app-code-generator": [
            "material-analyzer",
            "app-system-design",
            "app-api-design",
            "app-database-design",
        ],
        # Agent 9: needs user stories + code scaffold (implements stories against code)
        "app-feature-implementation": ["app-user-stories", "app-code-generator"],
        # Agent 10: needs architecture + code scaffold (infra wraps the app)
        "app-infra-generator": ["material-analyzer", "app-code-generator"],
        # Agent 11: needs architecture (for stack/language) + code scaffold + feature impl
        # Prompt: "Tailor choices to the language and platform established by earlier agents"
        "app-code-compliance": [
            "material-analyzer",
            "app-code-generator",
            "app-feature-implementation",
        ],
        # Agent 12: needs user stories + code + feature impl (tests prove ACs)
        "app-test-implementation": [
            "app-user-stories",
            "app-code-generator",
            "app-feature-implementation",
        ],
        # Agent 13: needs test impl + compliance + security (for compliance test mapping)
        # Prompt: "for each in-scope regulation from the security agent's output"
        "app-test-compliance": [
            "app-test-implementation",
            "app-code-compliance",
            "app-security-architecture",
        ],
        # Agent 14: needs architecture (platform choice) + infra + code scaffold
        # Prompt: "Tailor the choice of platform to the materials-analysis agent's recommendation"
        "app-devops": ["material-analyzer", "app-infra-generator", "app-code-generator"],
        # Agent 15: needs arch + system design + security + code-compliance + devops + test-compliance
        # Prompt: "earlier agents produced design, implementation, infrastructure, security,
        #          code-compliance, test-compliance"
        "app-sdlc-governance": [
            "material-analyzer",
            "app-system-design",
            "app-security-architecture",
            "app-code-compliance",
            "app-devops",
            "app-test-compliance",
        ],
    },
}


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
