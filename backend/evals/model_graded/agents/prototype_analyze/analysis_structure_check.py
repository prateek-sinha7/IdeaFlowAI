"""The ONE narrow custom precheck hook for prototype-analyze — the checks
the generic, config-driven model_graded/precheck.py cannot express: the SIX
required subsection headers (not just "6 headings, any text"), a valid
Readiness verdict enum value, and a markdown table under Findings. This
needs real parsing (locating specific header text, extracting the line
after a header, scanning for a table), not a count/substring check.

Everything else about grading a prototype-analyze response is data (the
scenario YAML's precheck:/rubric: blocks) — this is the only Python file in
this agent's folder.
"""

from __future__ import annotations

import re

_REQUIRED_HEADERS = (
    "### Summary",
    "### Findings",
    "### Issues requiring attention",
    "### Risk register",
    "### Suggested next actions",
    "### Readiness verdict",
)

_VALID_VERDICTS = ("READY TO BUILD", "READY WITH CAUTION", "NEEDS REVISION")


def check(response: str) -> tuple[bool, str]:
    """Verify all six required subsection headers are present verbatim, the
    Readiness verdict line names one of the three allowed values, and the
    Findings section contains a markdown table."""
    missing = [h for h in _REQUIRED_HEADERS if h not in response]
    if missing:
        return False, f"missing required section header(s): {missing}"

    verdict_match = re.search(r"### Readiness verdict\s*\n+(.+)", response)
    if not verdict_match:
        return False, "no content found after '### Readiness verdict'"
    verdict_line = verdict_match.group(1).strip()
    if not any(v in verdict_line for v in _VALID_VERDICTS):
        return False, f"readiness verdict line names no valid verdict: {verdict_line!r}"

    findings_match = re.search(r"### Findings\n(.*?)(?=\n### )", response, re.DOTALL)
    if not findings_match or "|" not in findings_match.group(1):
        return False, "'### Findings' section has no markdown table"

    return True, "all 6 required sections present, valid verdict, findings table found"
