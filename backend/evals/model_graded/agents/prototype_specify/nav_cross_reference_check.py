"""The ONE narrow custom precheck hook for prototype-specify — the single
check the generic, config-driven model_graded/precheck.py cannot express:
every navigation target referenced in the "Pages & Navigation" table must
have a corresponding page specification section. This needs real parsing
(matching route strings across two different document sections), not a
count/substring check.

Everything else about grading a prototype-specify response is data
(the scenario YAML's precheck:/rubric: blocks) — this is the only Python
file in this agent's folder.
"""

from __future__ import annotations

import re

# Matches a "Pages & Navigation" table row's route cell, e.g.
# "| dashboard | `#/dashboard` | ... |" -> "#/dashboard".
_TABLE_ROUTE_RE = re.compile(r"^\|[^|\n]*\|\s*`(#/[^`]+)`", re.MULTILINE)

# Matches a page spec section heading, e.g.
# "### Dashboard (`#/dashboard`)" -> "#/dashboard".
_SECTION_ROUTE_RE = re.compile(r"^###\s+.*\(`(#/[^`]+)`\)", re.MULTILINE)


def check(response: str) -> tuple[bool, str]:
    """Verify every route referenced in the Pages & Navigation table has a
    matching page specification section (``### {Page Name} (`#/{route}`)``).
    """
    table_routes = list(dict.fromkeys(_TABLE_ROUTE_RE.findall(response)))
    section_routes = set(_SECTION_ROUTE_RE.findall(response))

    if not table_routes:
        return (False, "no routes found in the Pages & Navigation table")

    dangling = [r for r in table_routes if r not in section_routes]
    if dangling:
        return (
            False,
            f"nav target(s) with no matching page section: {dangling}",
        )

    return (
        True,
        f"all {len(table_routes)} nav target(s) have a matching page section",
    )
