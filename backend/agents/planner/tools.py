"""agents/planner/tools.py — Deep_Planner_Agent LangChain tools.

These tools are used by the Deep_Planner_Agent (ReAct loop, max_iterations=20)
to proactively analyze a user brief, infer hidden constraints, assess readiness,
build an execution plan, and produce a Planning_Context artifact.

Tool set name: "planning" (referenced in deep-planner/AGENT.md frontmatter)

All tools are synchronous (LangChain @tool) — the DeepAgent's ReAct loop
calls them via tool invocation. The ArtifactStore writes are async and are
handled by the engine after the planner completes.
"""

from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool: analyze_request
# ---------------------------------------------------------------------------


@tool
def analyze_request(brief: str) -> str:
    """Analyze a user brief and extract explicit requirements.

    Args:
        brief: The raw user input / pipeline brief.

    Returns:
        JSON string with extracted explicit requirements:
        {
          "stated_goal": str,
          "explicit_constraints": list[str],
          "pipeline_type_hint": str,
          "user_personas": list[str],
          "deliverable_type": str
        }
    """
    # The actual analysis is performed by the LLM via the ReAct loop.
    # This tool stub provides the schema contract — the LLM fills in the values
    # by calling this tool with the brief and interpreting the return schema.
    result = {
        "stated_goal": brief[:200] if brief else "",
        "explicit_constraints": [],
        "pipeline_type_hint": "unknown",
        "user_personas": [],
        "deliverable_type": "unknown",
        "_tool": "analyze_request",
        "_note": "LLM should populate all fields based on brief analysis",
    }
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: infer_constraints
# ---------------------------------------------------------------------------


@tool
def infer_constraints(brief: str, stated_goal: str) -> str:
    """Proactively infer hidden constraints not stated by the user.

    Infers: personas, NFRs (performance, security, accessibility),
    tech stack assumptions, compliance requirements, scale assumptions.

    Args:
        brief: The raw user brief.
        stated_goal: The stated goal extracted by analyze_request.

    Returns:
        JSON string with inferred constraints:
        {
          "implicit_constraints": list[str],
          "inferred_personas": list[str],
          "inferred_nfrs": list[str],
          "inferred_tech_stack": list[str],
          "inferred_compliance": list[str],
          "missing_information": list[str]
        }
    """
    result = {
        "implicit_constraints": [],
        "inferred_personas": [],
        "inferred_nfrs": [],
        "inferred_tech_stack": [],
        "inferred_compliance": [],
        "missing_information": [],
        "_tool": "infer_constraints",
        "_note": "LLM should populate all fields based on domain knowledge and brief analysis",
    }
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: assess_readiness
# ---------------------------------------------------------------------------


@tool
def assess_readiness(
    explicit_constraints: str,
    implicit_constraints: str,
    missing_information: str,
) -> str:
    """Assess whether the brief is ready to proceed or requires clarification.

    Issues PROCEED if the brief is sufficiently complete for domain agents
    to produce high-quality output. Issues CLARIFY_REQUIRED if critical
    information is missing that would materially affect the output.

    Args:
        explicit_constraints: JSON list of explicit constraints from analyze_request.
        implicit_constraints: JSON list of implicit constraints from infer_constraints.
        missing_information: JSON list of missing information items.

    Returns:
        JSON string:
        {
          "gate_verdict": "PROCEED" | "CLARIFY_REQUIRED",
          "readiness_score": float (0.0-1.0),
          "blocking_gaps": list[str],
          "clarification_topics": list[str]
        }
    """
    # Default to PROCEED — the LLM overrides this based on its analysis
    result = {
        "gate_verdict": "PROCEED",
        "readiness_score": 0.8,
        "blocking_gaps": [],
        "clarification_topics": [],
        "_tool": "assess_readiness",
        "_note": "LLM should set gate_verdict to CLARIFY_REQUIRED if blocking_gaps is non-empty",
    }
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: build_execution_plan
# ---------------------------------------------------------------------------


@tool
def build_execution_plan(
    stated_goal: str,
    gate_verdict: str,
    pipeline_type_hint: str,
) -> str:
    """Build an execution strategy for the workflow.

    Args:
        stated_goal: The stated goal from analyze_request.
        gate_verdict: PROCEED or CLARIFY_REQUIRED from assess_readiness.
        pipeline_type_hint: Suggested pipeline type from analyze_request.

    Returns:
        JSON string:
        {
          "execution_strategy": "sequential" | "parallel" | "conditional",
          "recommended_pipeline_type": str,
          "agent_focus_areas": list[str],
          "quality_targets": list[str]
        }
    """
    result = {
        "execution_strategy": "sequential",
        "recommended_pipeline_type": pipeline_type_hint or "user_stories",
        "agent_focus_areas": [],
        "quality_targets": [],
        "_tool": "build_execution_plan",
        "_note": "LLM should populate based on goal and constraints",
    }
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Tool: store_planning_context
# ---------------------------------------------------------------------------


@tool
def store_planning_context(planning_context_json: str) -> str:
    """Store the completed Planning_Context for use by downstream agents.

    This tool signals to the ExecutionEngine that the planner has completed
    its analysis. The engine reads the planning_context from the tool result
    and stores it in the ArtifactStore.

    Args:
        planning_context_json: Complete Planning_Context as a JSON string with fields:
          {
            "inferred_intent": str,
            "explicit_constraints": list[str],
            "implicit_constraints": list[str],
            "missing_information": list[str],
            "execution_strategy": str,
            "execution_gate": "PROCEED" | "CLARIFY_REQUIRED",
            "inferred_personas": list[str],
            "inferred_nfrs": list[str],
            "quality_targets": list[str]
          }

    Returns:
        Confirmation string with the gate verdict.
    """
    try:
        ctx = json.loads(planning_context_json)
        gate = ctx.get("execution_gate", "PROCEED")
        return f"Planning context stored. Gate verdict: {gate}"
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("store_planning_context: invalid JSON — %s", exc)
        return f"Planning context stored (parse warning: {exc}). Gate verdict: PROCEED"


# ---------------------------------------------------------------------------
# Tool: retrieve_planning_context
# ---------------------------------------------------------------------------


@tool
def retrieve_planning_context(pipeline_run_id: str) -> str:
    """Retrieve a previously stored Planning_Context by pipeline run ID.

    Used by revision pipelines to retrieve the original planning context
    without re-running the planner.

    Args:
        pipeline_run_id: The UUID of the pipeline run.

    Returns:
        JSON string of the Planning_Context, or an error message if not found.
    """
    # Phase 2: returns a placeholder — Phase 3 reads from ArtifactStore
    return json.dumps({
        "error": "Planning context not found in Phase 2 in-memory store",
        "pipeline_run_id": pipeline_run_id,
        "_note": "Phase 3 will read from DB-backed ArtifactStore",
    })


# ---------------------------------------------------------------------------
# Tool registry — maps tool set name to list of tool objects
# ---------------------------------------------------------------------------

PLANNING_TOOLS: list = [
    analyze_request,
    infer_constraints,
    assess_readiness,
    build_execution_plan,
    store_planning_context,
    retrieve_planning_context,
]
