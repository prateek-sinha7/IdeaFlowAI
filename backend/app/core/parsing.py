"""Shared parsing utilities for workflow analysis and output extraction."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger("app.core.parsing")

# Regex that matches an H2 heading line at the start of a line.
_H2_PATTERN = re.compile(r"^## (.+)$", re.MULTILINE)


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
        logger.warning(
            "parse_analyzer_output: ## Solution Plan section not found in output"
        )
        return ""
    return body
