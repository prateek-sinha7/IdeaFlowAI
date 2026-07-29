"""The custom precheck hook for prototype-analyze.

The structural checks the config-driven `precheck` block in
prototype_analyze_rubric.yaml cannot express: the `### Readiness verdict`
section must carry EXACTLY ONE of the three permitted verdict strings, and the
`### Findings` table must have at least one data row under its header. Both need
per-section parsing, not a whole-document count or substring match.

The verdict is what a human gate reads first and what any downstream automation
would branch on, so a missing or invented one ("LOOKS FINE") makes the whole
report unusable even when every heading is present. An empty Findings table is
the same failure wearing correct formatting: a verdict with nothing behind it.

Referenced from the rubric as `./prototype_analyze_validate.py:check`.
"""

from __future__ import annotations

import re

# The exact verdicts AGENT.md permits. No two are substrings of one another, so
# counting them independently cannot double-count a single verdict.
PERMITTED_VERDICTS = ("READY TO BUILD", "READY WITH CAUTION", "NEEDS REVISION")

# A Findings table DATA row starts with the numbered `#` column:
#   "| 1 | Consistency | ✅ Clear | ... |"
# The header and its `|---|` separator have no leading number, so they cannot
# satisfy this on their own.
_FINDINGS_ROW_RE = re.compile(r"^\|\s*\d+\s*\|", re.MULTILINE)


def check(response: str) -> tuple[bool, str]:
    """Verify the readiness verdict is one permitted value and Findings has rows.

    Returns (passed, reason). The reason is recorded on pass as well as fail —
    on pass it names the verdict found and the number of finding rows actually
    counted, which is how you confirm the check is running rather than silently
    matching nothing.
    """
    verdict_section = _section(response, "Readiness verdict")
    if verdict_section is None:
        return False, "no '### Readiness verdict' section"

    found = [v for v in PERMITTED_VERDICTS if v in verdict_section]
    if not found:
        return False, f"readiness verdict is none of {list(PERMITTED_VERDICTS)}"
    if len(found) > 1:
        return False, f"readiness verdict is ambiguous — {found} all present"

    findings_section = _section(response, "Findings")
    if findings_section is None:
        return False, "no '### Findings' section"

    row_count = len(_FINDINGS_ROW_RE.findall(findings_section))
    # Matching nothing must FAIL, never silently pass. A Findings table that is
    # only a header is not "no issues found" — it is a report with no analysis
    # in it, and treating it as a pass is how a gate stops gating.
    if row_count == 0:
        return False, "Findings table has a header but no data rows"

    return True, f"verdict '{found[0]}' with {row_count} finding row(s)"


def _section(response: str, title: str) -> str | None:
    """Return the body of the `### {title}` section, or None if it is absent.

    The body runs to the next `### ` heading (or end of response), so a value
    quoted in a later section can never be mistaken for this section's own.
    """
    pattern = re.compile(
        rf"^###\s+{re.escape(title)}\s*$(.*?)(?=^###\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(response)
    return match.group(1) if match else None
