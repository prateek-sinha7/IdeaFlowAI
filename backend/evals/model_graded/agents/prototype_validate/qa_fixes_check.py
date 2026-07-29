"""The ONE narrow custom precheck hook for prototype-validate — the checks
the generic, config-driven model_graded/precheck.py cannot express: NONE of
the known SEED-DEFAULT ``:root`` token values (the exact placeholder colors
named in prototype-validate's own AGENT.md "CRITICAL CHECK 0") may remain,
and no ``<section data-page="...">`` may still be empty. This needs real
parsing (extracting each section's inner content, checking specific token
values), not a count/substring check.

Every dataset.json entry in this branch seeds a prototype.html with BOTH of
these defects deliberately injected — this hook verifies the validate agent
actually fixed them, not just that its response is well-formed HTML.
"""

from __future__ import annotations

import re

# The exact seed-template default token values prototype-validate's own
# AGENT.md names as the #1 failure mode ("CRITICAL CHECK 0") — if these
# survive into the fixed output, the DS tokens were never actually applied.
_SEED_DEFAULT_TOKENS = {
    "--bg": "#fafaf7",
    "--fg": "#141413",
    "--accent": "#c96442",
}

_SECTION_RE = re.compile(
    r'<section\s+data-page="([^"]+)"[^>]*>(.*?)</section>', re.DOTALL
)


def check(response: str) -> tuple[bool, str]:
    """Verify no seed-default :root token values remain, and no
    <section data-page="..."> is empty."""
    root_match = re.search(r":root\s*\{([^}]*)\}", response, re.DOTALL)
    if not root_match:
        return False, "no ':root { }' block found"
    root_body = root_match.group(1)

    surviving_defaults = [
        f"{var}: {value}" for var, value in _SEED_DEFAULT_TOKENS.items() if value in root_body
    ]
    if surviving_defaults:
        return False, f"seed-default token value(s) still present: {surviving_defaults}"

    sections = _SECTION_RE.findall(response)
    if not sections:
        return False, "no <section data-page=...> elements found"

    empty_pages = [page_id for page_id, body in sections if len(body.strip()) < 20]
    if empty_pages:
        return False, f"page(s) still empty/near-empty: {empty_pages}"

    return True, f"no seed-default tokens survived, all {len(sections)} page(s) have content"
