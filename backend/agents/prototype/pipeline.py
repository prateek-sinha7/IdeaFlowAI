"""agents/prototype/pipeline.py — Prototype pipeline constants and registry.

Single source of truth for:
  - Which agent IDs belong to the prototype pipeline
  - Which pipeline types are prototype pipelines
  - The SKIP_PLANNER_CLARIFY flag (prototype uses spec-phase instead)
  - Helper to check if a pipeline_type is a prototype pipeline

Approach 2+3 (Spec Kit style) is now ACTIVE:
  Phase 1: prototype-specify  → spec document (pages, components, interactions)
  Phase 2: prototype-plan     → atomic task list
  Phase 3: prototype-build    → HTML built task-by-task (incremental)
  Phase 4: prototype-validate → P0/P1 structural validation
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Pipeline type constants
# ---------------------------------------------------------------------------

#: All pipeline_type values that are prototype pipelines.
PROTOTYPE_PIPELINE_TYPES: frozenset[str] = frozenset({
    "od_prototype",
    "prototype",
    "prototype_revision",
})

#: The base pipeline type used for agent registry lookup.
PROTOTYPE_BASE_TYPE = "prototype"

# ---------------------------------------------------------------------------
# Agent IDs
# ---------------------------------------------------------------------------

#: Approach 2+3 — Spec Kit style (ACTIVE).
#: Phase 1: specify → Phase 2: plan → Phase 3: build → Phase 4: validate
PROTOTYPE_AGENTS_V2: list[str] = [
    "prototype-specify",   # Phase 1: generates spec document
    "prototype-plan",      # Phase 2: decomposes spec into atomic tasks
    "prototype-build",     # Phase 3: executes tasks incrementally
    "prototype-validate",  # Phase 4: P0/P1 structural validation
]

#: Revision pipeline — single agent.
PROTOTYPE_REVISION_AGENTS: list[str] = [
    "prototype-revision-agent",
]

# ---------------------------------------------------------------------------
# Pipeline behaviour flags
# ---------------------------------------------------------------------------

#: When True, the SmartPlanner + ClarifyEngine are skipped for prototype
#: pipelines (the prototype-specify agent handles planning/clarification in its
#: spec phase). When False, the planner + clarifier run before the prototype
#: agents — exactly like every other pipeline — so the user gets the clarifying
#: questionnaire up front (with ALWAYS_CLARIFY=True in the engine, on every run).
#:
#: NOTE: this flag ONLY controls the front-end planner/clarifier. The prototype
#: agents themselves are always Approach 2+3 / spec-kit (specify → plan → build →
#: validate) regardless of this value.
SKIP_PLANNER_FOR_PROTOTYPE = False

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def is_prototype_pipeline(pipeline_type: str) -> bool:
    """Return True if the pipeline_type is a prototype pipeline."""
    return pipeline_type in PROTOTYPE_PIPELINE_TYPES


def get_prototype_agents(pipeline_type: str) -> list[str]:
    """Return the agent ID list for the given prototype pipeline type."""
    if pipeline_type == "prototype_revision":
        return PROTOTYPE_REVISION_AGENTS
    return PROTOTYPE_AGENTS_V2
