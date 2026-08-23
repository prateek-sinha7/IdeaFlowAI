"""app/agents/revision_analyzer.py — single source for ``parse_analyzer_output`` and ``run_analyzer``.

``parse_analyzer_output`` is a **pure function** (no I/O, no LLM calls) that
extracts a tier label and a solution plan from the raw Markdown string emitted
by the ``prototype-revision-analyzer`` agent.

``run_analyzer`` is the async orchestrator that invokes the LLM, calls
``parse_analyzer_output``, emits SSE events onto the caller's event queue, and
returns ``(tier, solution)``.  It is added in task 2.3.
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

_VALID_TIERS: frozenset[str] = frozenset({"small", "large", "feature"})
_DEFAULT_TIER: str = "large"

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


def parse_analyzer_output(raw: str) -> tuple[str, str]:
    """Pure parser — no I/O, no LLM calls.

    Extracts:
      - **tier**: first non-blank line under ``## Tier``, lowercased and
        validated against ``{"small", "large", "feature"}``.
        Defaults to ``"large"`` + WARNING if absent or unrecognised.
      - **solution**: full text of the ``## Solution Plan`` section body,
        preserving interior whitespace.
        Defaults to ``""`` + WARNING if absent.

    Error table:

    =========================================================  ===========  ================  ===========
    Condition                                                  tier result  solution result   Log level
    =========================================================  ===========  ================  ===========
    Both sections present, tier valid                          extracted    extracted         DEBUG
    ``## Tier`` absent                                         ``"large"``  extracted or ""   WARNING
    ``## Tier`` present but value unrecognised                 ``"large"``  extracted or ""   WARNING
    ``## Solution Plan`` absent                                extracted    ``""``            WARNING
    Both sections absent                                       ``"large"``  ``""``            WARNING
    =========================================================  ===========  ================  ===========

    Returns:
        ``(tier, solution)`` — *tier* is always one of ``{"small", "large", "feature"}``;
        *solution* may be an empty string.
    """
    sections = _split_h2_sections(raw)

    # ── Tier extraction ──────────────────────────────────────────────────────
    tier_body = _find_section(sections, "Tier")

    if tier_body is None:
        logger.warning(
            "parse_analyzer_output: '## Tier' section absent — defaulting to %r. "
            "Raw output (first 500 chars): %r",
            _DEFAULT_TIER,
            raw[:500],
        )
        tier = _DEFAULT_TIER
    else:
        # Find the first non-blank line in the tier section body.
        first_nonblank = next(
            (line.strip() for line in tier_body.splitlines() if line.strip()),
            None,
        )
        if first_nonblank is None:
            # Section exists but is entirely blank.
            logger.warning(
                "parse_analyzer_output: '## Tier' section has no non-blank content — "
                "defaulting to %r. Raw output (first 500 chars): %r",
                _DEFAULT_TIER,
                raw[:500],
            )
            tier = _DEFAULT_TIER
        else:
            normalised = first_nonblank.lower()
            if normalised in _VALID_TIERS:
                tier = normalised
                logger.debug(
                    "parse_analyzer_output: extracted tier=%r", tier
                )
            else:
                logger.warning(
                    "parse_analyzer_output: unrecognised tier value %r (normalised: %r) — "
                    "defaulting to %r. Raw output (first 500 chars): %r",
                    first_nonblank,
                    normalised,
                    _DEFAULT_TIER,
                    raw[:500],
                )
                tier = _DEFAULT_TIER

    # ── Solution Plan extraction ─────────────────────────────────────────────
    solution_body = _find_section(sections, "Solution Plan")

    if solution_body is None:
        logger.warning(
            "parse_analyzer_output: '## Solution Plan' section absent — "
            "setting solution to empty string."
        )
        solution = ""
    else:
        solution = solution_body

    return (tier, solution)


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
        model_id: Optional model override; passed to ``build_model``.

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

        llm = build_model(model_id, max_tokens=4096)

        t_start = time.monotonic()
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        duration = time.monotonic() - t_start

        tier, solution = parse_analyzer_output(response.content)

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
