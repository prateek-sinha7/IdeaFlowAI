"""The custom precheck hook for prototype-specify.

The one structural check the config-driven `precheck` block in
prototype_specify_rubric.yaml cannot express: every navigation target in the
"Pages & Navigation" table must have a matching page specification section.
That needs real parsing — matching route strings across two different sections
of the document — not a count or substring match.

A dangling nav target is a genuine downstream break, not a style opinion: the
build agent will emit a nav link to a route with no `<section data-page>` to
show, and the prototype dead-ends on click.

Referenced from the rubric as `./prototype_specify_validate.py:check`.
"""

from __future__ import annotations

import re

# A "Pages & Navigation" table row's route cell:
#   "| dashboard | `#/dashboard` | ... |"  ->  "#/dashboard"
_TABLE_ROUTE_RE = re.compile(r"^\|[^|\n]*\|\s*`(#/[^`]+)`", re.MULTILINE)

# A page spec section heading:
#   "### Dashboard (`#/dashboard`)"  ->  "#/dashboard"
_SECTION_ROUTE_RE = re.compile(r"^###\s+.*\(`(#/[^`]+)`\)", re.MULTILINE)


def check(response: str) -> tuple[bool, str]:
    """Verify every route in the Pages & Navigation table has a matching page
    section (``### {Page Name} (`#/{route}`)``).

    Returns (passed, reason). The reason is recorded on pass as well as fail —
    on pass it names how many routes were actually cross-referenced, which is
    how you confirm the check is running rather than silently matching nothing.
    """
    table_routes = list(dict.fromkeys(_TABLE_ROUTE_RE.findall(response)))
    section_routes = set(_SECTION_ROUTE_RE.findall(response))

    # Matching nothing must FAIL, never silently pass. A spec with no parseable
    # nav table is malformed, and treating "no routes" as "no dangling routes"
    # is how a precheck stops checking anything without anyone noticing.
    if not table_routes:
        return False, "no routes found in the Pages & Navigation table"

    dangling = [route for route in table_routes if route not in section_routes]
    if dangling:
        return False, f"nav target(s) with no matching page section: {dangling}"

    return True, f"all {len(table_routes)} nav target(s) have a matching page section"
