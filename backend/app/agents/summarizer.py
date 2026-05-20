"""Agent output summarizer.

After each agent completes, this module generates a detailed summary of its
output. The summary is passed as context to downstream agents instead of the
full raw output, reducing token usage while preserving all critical information.

Key design decisions:
- Uses BaseAgent (single LLM call, no tool loop) — fast and cheap
- Always produces a DETAILED summary — no information is dropped
- Pipeline-aware prompts — each pipeline type gets a tailored summary format
- Short outputs (< 2000 chars) are returned as-is — no summarization needed
- HTML outputs (prototype pipeline) are never summarized — structure must be preserved
- DeepAgent architecture is not touched — summarization is purely a context-building concern
"""

from __future__ import annotations

import logging

logger = logging.getLogger("app.agents.summarizer")

# Outputs shorter than this threshold are passed verbatim — no summarization needed.
_MIN_CHARS_TO_SUMMARIZE = 2000

# Pipeline types whose outputs must never be summarized (HTML artifacts, etc.)
_SKIP_SUMMARIZATION_PIPELINES = {"od_prototype", "prototype", "prototype_revision"}

# ---------------------------------------------------------------------------
# Pipeline-aware summary system prompts
# ---------------------------------------------------------------------------

_BASE_SUMMARY_INSTRUCTION = """You are a technical summarizer working inside a multi-agent AI pipeline.

Your job: produce a DETAILED SUMMARY of the agent output below.

CRITICAL RULES:
- NEVER omit any decision, named item, specific value, constraint, or technical detail
- NEVER use vague phrases like "various items" or "several components" — name them all
- Preserve ALL: names, IDs, numbers, percentages, URLs, field names, method names, file paths
- Preserve ALL: architecture decisions, ADRs, acceptance criteria, story points, dependencies
- Use structured markdown with the same section headers as the original
- Target length: 600–1200 words. Go longer if needed to preserve all detail.
- If the original has lists, preserve every list item
- If the original has tables, preserve every row
- Do NOT add commentary, opinions, or new information — only summarize what is there
"""

_PIPELINE_PROMPTS: dict[str, str] = {
    "ppt": _BASE_SUMMARY_INSTRUCTION + """

PIPELINE CONTEXT: This is a presentation (PPT) pipeline.
For each slide, preserve: slide number, title, key message, all content points, any data/stats/numbers.
Preserve the narrative arc and the exact content plan structure.""",

    "ppt_revision": _BASE_SUMMARY_INSTRUCTION + """

PIPELINE CONTEXT: This is a presentation revision pipeline.
Preserve all revision instructions, slide references, specific changes requested, and constraints.""",

    "user_stories": _BASE_SUMMARY_INSTRUCTION + """

PIPELINE CONTEXT: This is a user stories / product backlog pipeline.
For each epic: preserve the epic title, priority (P0/P1/P2), business value statement.
For each story: preserve the full "As a / I want / So that" text, ALL acceptance criteria
(Given/When/Then), story points, dependencies, and any reviewer feedback.
Preserve the backlog summary totals.""",

    "user_stories_revision": _BASE_SUMMARY_INSTRUCTION + """

PIPELINE CONTEXT: This is a user stories revision pipeline.
Preserve all changes made, stories added/removed/modified, updated story points and priorities.""",

    "app_builder": _BASE_SUMMARY_INSTRUCTION + """

PIPELINE CONTEXT: This is a full-stack application builder pipeline.
Preserve ALL of:
- Component names, responsibilities, and ownership
- API endpoint paths, methods, request/response shapes
- Database table names, field names, types, relationships, constraints
- Architecture Decision Records (ADRs) — status, decision, consequences
- Tech stack choices (framework, language, database, auth, hosting)
- Security requirements, compliance items, test coverage targets
- File paths, function names, class names in any generated code
- Infrastructure resources, deployment topology
- CI/CD pipeline steps, quality gates""",

    "app_builder_revision": _BASE_SUMMARY_INSTRUCTION + """

PIPELINE CONTEXT: This is an app builder revision pipeline.
Preserve all files changed, functions modified, new endpoints added, schema changes.""",

    "mulesoft_to_springboot": _BASE_SUMMARY_INSTRUCTION + """

PIPELINE CONTEXT: This is a Mulesoft → Spring Boot migration pipeline.
Preserve ALL of:
- Mule application names, flow names, connector types
- Migration decisions and rationale
- Spring Boot component names, package structure
- DataWeave → Java translation decisions
- AWS infrastructure resources (queues, topics, services)
- Security architecture, compliance requirements
- Test coverage targets, validation gates
- ADRs, risk items, open questions""",

    "dotnet_to_azure": _BASE_SUMMARY_INSTRUCTION + """

PIPELINE CONTEXT: This is a .NET → Azure migration pipeline.
Preserve ALL of:
- .NET project names, service names, component names
- Azure service choices (App Service, Functions, SQL, Cosmos, etc.)
- Migration decisions and rationale
- C# class names, interface names, namespace structure
- Azure Bicep resource names and configurations
- Security architecture, managed identity setup
- Test coverage targets, compliance requirements
- ADRs, risk items, open questions""",

    "custom": _BASE_SUMMARY_INSTRUCTION + """

PIPELINE CONTEXT: This is a custom AI workflow pipeline.
Preserve ALL findings, recommendations, action items, metrics, data points,
named entities, and any structured output (tables, lists, frameworks).""",
}

# Default prompt for any pipeline type not explicitly listed
_DEFAULT_PROMPT = _BASE_SUMMARY_INSTRUCTION


def _get_summary_prompt(pipeline_type: str) -> str:
    """Return the pipeline-appropriate summary system prompt."""
    return _PIPELINE_PROMPTS.get(pipeline_type, _DEFAULT_PROMPT)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def summarize_agent_output(
    agent_name: str,
    agent_role: str,
    pipeline_type: str,
    output: str,
) -> str:
    """Generate a detailed summary of an agent's output for use as downstream context.

    Returns the original output unchanged if:
    - The output is shorter than _MIN_CHARS_TO_SUMMARIZE (already concise)
    - The pipeline type is in _SKIP_SUMMARIZATION_PIPELINES (HTML artifacts)
    - The summarization LLM call fails (graceful fallback to full output)

    Args:
        agent_name: Human-readable agent name (e.g. "Architecture Agent")
        agent_role: Agent role description (e.g. "Solution & System Design")
        pipeline_type: Pipeline type string (e.g. "app_builder")
        output: The full raw output text from the agent

    Returns:
        A detailed summary string, or the original output if summarization
        is skipped or fails.
    """
    # Skip for short outputs — already concise enough
    if len(output) < _MIN_CHARS_TO_SUMMARIZE:
        logger.debug(
            "Skipping summarization for %s — output too short (%d chars)",
            agent_name, len(output),
        )
        return output

    # Skip for pipelines with HTML/binary artifacts
    if pipeline_type in _SKIP_SUMMARIZATION_PIPELINES:
        logger.debug(
            "Skipping summarization for %s — pipeline %s uses artifact outputs",
            agent_name, pipeline_type,
        )
        return output

    system_prompt = _get_summary_prompt(pipeline_type)

    user_message = (
        f"AGENT: {agent_name} ({agent_role})\n"
        f"PIPELINE: {pipeline_type}\n"
        f"OUTPUT LENGTH: {len(output)} characters\n\n"
        f"=== AGENT OUTPUT TO SUMMARIZE ===\n\n"
        f"{output}\n\n"
        f"=== END OF OUTPUT ===\n\n"
        f"Produce a detailed summary following the rules in your system prompt."
    )

    try:
        from app.agents.base import BaseAgent

        summarizer = BaseAgent(
            system_prompt=system_prompt,
            max_tokens=4000,  # Enough for a thorough 600–1200 word summary
        )
        summary = await summarizer.run(user_message)

        if not summary or not summary.strip():
            logger.warning(
                "Summarizer returned empty output for %s — falling back to full output",
                agent_name,
            )
            return output

        logger.info(
            "Summarized %s: %d chars → %d chars (%.0f%% reduction)",
            agent_name, len(output), len(summary),
            (1 - len(summary) / len(output)) * 100,
        )
        return summary

    except Exception as exc:
        # Never let summarization failure break the pipeline — fall back to full output
        logger.warning(
            "Summarization failed for %s: %s — falling back to full output",
            agent_name, exc,
        )
        return output
