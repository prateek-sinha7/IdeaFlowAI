"""app/agents/revision_analyzer.py — single source for ``parse_analyzer_output`` and ``run_analyzer``.

``parse_analyzer_output`` is a **pure function** (no I/O, no LLM calls) that
extracts the ``## Solution Plan`` body from the raw Markdown string emitted
by the ``prototype-revision-analyzer`` agent.  Returns a plain ``str``.

``run_analyzer`` is the async orchestrator that invokes the LLM, calls
``parse_analyzer_output``, emits SSE events onto the caller's event queue, and
returns ``(tier, solution)``.  It is **deprecated dead code** as of the
revision-pipeline-refactor — the engine now drives the analyzer as a manifest
step and calls ``parse_analyzer_output`` directly.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time

logger = logging.getLogger("app.agents.revision_analyzer")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Regex that matches an H2 heading line at the start of a line.
_H2_PATTERN = re.compile(r"^## (.+)$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _split_h2_sections(raw: str) -> dict[str, str]:
    """Split *raw* into a mapping of ``{header_text: section_body}``.

    Each section body is the text between two consecutive ``## `` headings
    (or between a heading and the end of the document).  Leading/trailing
    newlines on each body are NOT stripped — the ``## Solution Plan`` body is
    captured verbatim so downstream agents receive faithful whitespace.

    The returned dict preserves insertion order (Python 3.7+).
    """
    sections: dict[str, str] = {}
    matches = list(_H2_PATTERN.finditer(raw))
    for i, match in enumerate(matches):
        header = match.group(1).strip()
        body_start = match.end()  # position just after the heading line
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        sections[header] = raw[body_start:body_end]
    return sections


def _find_section(sections: dict[str, str], target: str) -> str | None:
    """Return the body of the section whose header matches *target* (case-insensitive).

    Returns ``None`` if no matching header is found.
    """
    target_lower = target.strip().lower()
    for header, body in sections.items():
        if header.strip().lower() == target_lower:
            return body
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_analyzer_output(raw: str) -> str:
    """Extract the ## Solution Plan body from the analyzer's raw output.

    Returns the solution body string, or "" if the section is absent (logs WARNING).
    Tier parsing logic (_VALID_TIERS, _DEFAULT_TIER, ## Tier section extraction) is removed.

    Returns:
        The full ``## Solution Plan`` section body (preserving interior whitespace),
        or ``""`` if the section is absent.
    """
    sections = _split_h2_sections(raw)
    body = _find_section(sections, "Solution Plan")
    if body is None:
        logger.warning("parse_analyzer_output: ## Solution Plan section not found in output")
        return ""
    return body


# ---------------------------------------------------------------------------
# Async orchestrator
# ---------------------------------------------------------------------------

_ANALYZER_PROMPT_TEMPLATE = """\
You are the Prototype Revision Analyzer. Your job is to read a revision instruction
and the current prototype HTML, then output a structured analysis.

=== REVISION INSTRUCTION ===
{instruction}

=== CURRENT PROTOTYPE HTML ===
{existing_html}

Output ONLY this Markdown structure — no preamble, no closing remarks:

## Tier
[one word: small, large, or feature]

## Solution Plan
[detailed description of what needs to change, naming exact element ids, routes, functions, and CSS classes]\
"""


_ANALYZER_AGENT_ID = "prototype-revision-analyzer"


def _resolve_analyzer_model(session_model_id: str | None) -> str | None:
    """Resolve the effective model id for the analyzer agent (D-02 abridged).

    The analyzer is an app-layer pre-pipeline agent — it bypasses the engine's
    ``ModelResolver`` — so we replicate the relevant D-02 tiers here:

      tier-3  AGENT.md ``model`` field   (wins over user session selection)
      tier-5a session_model_id           (user's per-run model preference)
      tier-5b None                       (let build_model use the provider default)

    Tier-1 (user override map) and tier-2 (step.model) have no meaning for a
    pre-pipeline agent, so they are omitted.
    """
    try:
        from agents.loader import load_agent_spec  # noqa: PLC0415

        spec = load_agent_spec(_ANALYZER_AGENT_ID)
        if spec.model:
            logger.info(
                "run_analyzer: using AGENT.md model=%r (tier-3) for agent=%r",
                spec.model,
                _ANALYZER_AGENT_ID,
            )
            return spec.model
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "run_analyzer: could not load AGENT.md for %r (%s) — falling back to session model",
            _ANALYZER_AGENT_ID,
            exc,
        )

    if session_model_id:
        logger.info(
            "run_analyzer: using session model=%r (tier-5a) for agent=%r",
            session_model_id,
            _ANALYZER_AGENT_ID,
        )
    return session_model_id


# DEPRECATED (revision-pipeline-refactor): run_analyzer is dead code.
# The engine now drives prototype-revision-analyzer as a manifest step and calls
# parse_analyzer_output directly after the step completes. This function can be
# removed in a follow-up cleanup once callers are confirmed gone.
async def run_analyzer(
    instruction: str,
    existing_html: str,
    event_queue: asyncio.Queue,
    parent_run_id: str,
    model_id: str | None = None,
) -> tuple[str, str]:
    """Async orchestrator for the Prototype Revision Analyzer agent.

    Emits ``agent_start``, ``agent_complete``, and ``revision_analyzer_complete``
    events onto *event_queue*, invokes the LLM, parses the output via
    ``parse_analyzer_output``, and returns ``(tier, solution)``.

    Falls back to ``_classify_revision_tier`` (from ``app.api.run_commands``)
    on any exception, and to ``("large", "")`` if that also fails.

    Args:
        instruction: The revision instruction text.
        existing_html: The current prototype HTML.
        event_queue: Async queue to emit SSE-style events onto.
        parent_run_id: The parent workflow run ID (used by the fallback classifier).
        model_id: Optional session model id (user's per-run preference, tier-5a).
            The AGENT.md ``model`` field (tier-3) takes precedence when set.

    Returns:
        ``(tier, solution)`` where *tier* is one of ``{"small", "large", "feature"}``
        and *solution* is the full Solution Plan body (may be empty on fallback).
    """
    try:
        prompt = _ANALYZER_PROMPT_TEMPLATE.format(
            instruction=instruction,
            existing_html=existing_html,
        )

        await event_queue.put({
            "type": "agent_start",
            "data": {
                "agent_id": "prototype-revision-analyzer",
                "name": "Prototype Revision Analyzer",
                "role": "analyzer",
                "icon": "🔍",
                "index": 1,
                "total": 1,
            },
        })

        # Lazy imports to avoid circular dependencies at module load time.
        from app.agents.model_factory import build_model  # noqa: PLC0415
        from langchain_core.messages import HumanMessage  # noqa: PLC0415

        # Resolve model honoring D-02 tier precedence: AGENT.md (tier-3) wins
        # over the caller-supplied session model (tier-5a).
        effective_model_id = _resolve_analyzer_model(model_id)
        llm = build_model(effective_model_id, max_tokens=4096)

        t_start = time.monotonic()
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        duration = time.monotonic() - t_start

        # Bedrock Converse returns content as a list of blocks
        # (e.g. [{"type": "text", "text": "..."}]) while Anthropic direct
        # returns a plain string. Normalise to str before parsing.
        raw_content = response.content
        if isinstance(raw_content, list):
            raw_content = "\n".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in raw_content
                if not isinstance(block, dict) or block.get("type") == "text"
            )

        # NOTE: parse_analyzer_output now returns str (solution only) — tier classification
        # is handled upstream by _classify_revision_tier. This function is deprecated dead
        # code (revision-pipeline-refactor); tier is set to a placeholder here.
        solution = parse_analyzer_output(raw_content)
        tier = "large"  # tier no longer extracted here; run_analyzer is deprecated dead code

        await event_queue.put({
            "type": "agent_complete",
            "data": {
                "agent_id": "prototype-revision-analyzer",
                "name": "Prototype Revision Analyzer",
                "duration": duration,
                "output_length": len(response.content),
                "input_tokens": (
                    getattr(response.usage_metadata, "input_tokens", 0)
                    if hasattr(response, "usage_metadata") and response.usage_metadata
                    else 0
                ),
                "output_tokens": (
                    getattr(response.usage_metadata, "output_tokens", 0)
                    if hasattr(response, "usage_metadata") and response.usage_metadata
                    else 0
                ),
                "total_tokens": (
                    getattr(response.usage_metadata, "total_tokens", 0)
                    if hasattr(response, "usage_metadata") and response.usage_metadata
                    else 0
                ),
            },
        })

        await event_queue.put({
            "type": "revision_analyzer_complete",
            "data": {
                "tier": tier,
                "solution_preview": solution[:200],
            },
        })

        return (tier, solution)

    except Exception as exc:
        logger.error(
            "run_analyzer failed (%s) — falling back to _classify_revision_tier",
            exc,
            exc_info=True,
        )
        try:
            from app.api.run_commands import _classify_revision_tier  # noqa: PLC0415
            tier = await _classify_revision_tier(instruction, parent_run_id, model_id)
            return (tier, "")
        except Exception as exc2:
            logger.error(
                "_classify_revision_tier fallback also failed (%s) — defaulting to large",
                exc2,
            )
            return ("large", "")
