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


# A page-spec section: from its `### Name (`#/route`)` heading to the next
# `### ` heading (or end of document). The heading part is `[^\n]*`, never
# `.*` — under DOTALL a dot crosses newlines and one "heading" swallows the
# whole document, which is how this check first shipped seeing 1 section
# where there were 4.
_PAGE_SECTION_RE = re.compile(
    r"^###\s+([^\n]*\(`#/[^`]+`\))[ \t]*$(.*?)(?=^###\s|\Z)",
    re.MULTILINE | re.DOTALL,
)

# The two blocks the agent's own OUTPUT FORMAT mandates per page. A page
# without them is exactly the "thin page" failure the judge kept waving
# through at 90: it exists, it is named, and it tells the build agent nothing.
_REQUIRED_PAGE_BLOCKS = ("Components", "Interactions")


def check(response: str) -> tuple[bool, str]:
    """Verify nav-table routes match page sections, and each page is specified.

    Two checks, both structural:

    - every route in the Pages & Navigation table has a matching page section
      (``### {Page Name} (`#/{route}`)``);
    - every page section carries the ``Components`` and ``Interactions`` blocks
      the agent's own output format mandates — a page heading with neither is
      a stub wearing a route, and the build agent receives nothing to build.

    Returns (passed, reason). The reason is recorded on pass as well as fail —
    on pass it names how many routes and page bodies were actually inspected,
    which is how you confirm the check ran rather than silently matching nothing.
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

    thin = _underspecified_pages(response)
    if thin:
        return False, (
            "page section(s) missing their "
            f"{' / '.join(_REQUIRED_PAGE_BLOCKS)} blocks: {thin} — a page "
            "heading without them gives the build agent nothing to build"
        )

    pages = sum(1 for _ in _PAGE_SECTION_RE.finditer(response))
    return True, (
        f"all {len(table_routes)} nav target(s) have a matching page section; "
        f"all {pages} page section(s) carry Components and Interactions"
    )


def _underspecified_pages(response: str) -> list[str]:
    """Page-section headings whose body lacks a required block."""
    thin = []
    for match in _PAGE_SECTION_RE.finditer(response):
        heading, body = match.group(1).strip(), match.group(2)
        missing = [block for block in _REQUIRED_PAGE_BLOCKS if block not in body]
        if missing:
            thin.append(heading)
    return thin
