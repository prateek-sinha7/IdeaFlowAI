"""The custom precheck hook for prototype-validate.

Two structural facts the config-driven `precheck` block cannot express: no
`<section data-page>` may be empty or comment-only (the #1 failure this agent
exists to prevent), and every nav route must resolve to a real section.

Referenced from the rubric as `./prototype_validate_validate.py:check`.
"""

from __future__ import annotations

import re

# Reused rather than restated: this is the SAME structural checker production
# runs on this exact HTML family, so the gate and the pipeline cannot disagree
# about what a dead nav link is. `app` is importable wherever grading runs —
# dispatch.py already imports app.agents.model_factory at module level.
from app.agents.static_check import static_check

# `<section data-page="issues" class="...">...</section>` -> ("issues", body).
# Non-greedy to the first `</section>`: a page that nests another <section> ends
# the match early, which can only UNDER-report content, never invent it.
_SECTION_RE = re.compile(
    r'<section\b[^>]*\bdata-page\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</section\s*>',
    re.IGNORECASE | re.DOTALL,
)

_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

# static_check emits many issue kinds; only these two are "a nav link goes
# nowhere". The rest (undefined handlers, missing routes entries) are real but
# are judgement-adjacent P1s, and a precheck that fails on them would reject
# output a human would call correct.
_DEAD_NAV_PREFIXES = ("dead nav link:", "router-dead nav link:")


def check(response: str) -> tuple[bool, str]:
    """Verify no page section is empty and every nav route resolves to a section.

    Returns (passed, reason). The reason is recorded on pass as well as fail —
    on pass it names how many sections were inspected and how many nav routes
    were resolved, which is how you confirm the check ran rather than silently
    matching nothing.
    """
    sections = _SECTION_RE.findall(response)

    # Matching nothing must FAIL. An HTML file with no parseable page section is
    # not "a prototype with no empty pages" — it is a prototype the validator
    # destroyed, and treating it as clean is how a gate stops gating.
    if not sections:
        return False, "no <section data-page=...> elements found in the deliverable"

    empty = [page_id for page_id, body in sections if _is_empty(body)]
    if empty:
        return False, (
            f"empty <section data-page> — a P0 this agent exists to fix: {empty}"
        )

    result = static_check(response)
    dead = [issue for issue in result.issues if issue.startswith(_DEAD_NAV_PREFIXES)]
    if dead:
        return False, f"navigation does not resolve: {dead}"

    return True, (
        f"all {len(sections)} <section data-page> have content, "
        f"{len(result.nav_hrefs)} nav link(s) resolve to real sections"
    )


def _is_empty(body: str) -> bool:
    """Is a section body empty once HTML comments are removed?

    Comment-only counts as empty on purpose: AGENT.md defines a filled page as
    "more than just the opening tag or a comment", and a leftover
    `<!-- TODO: settings form -->` is exactly the defect this stage must repair.
    """
    return not _COMMENT_RE.sub("", body).strip()
