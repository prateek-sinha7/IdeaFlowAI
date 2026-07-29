"""The custom precheck hook for prototype-build.

What the config-driven `precheck` block cannot express: every nav route must
resolve to a real `<section data-page>`, and no page section may be empty. Both
need parsing — cross-referencing hrefs against sections, and reading each
section's body — not a count or a substring match.

Referenced from the rubric as `./prototype_build_validate.py:check`.
"""

from __future__ import annotations

import re

from app.agents.static_check import static_check

# The opening tag of a page section, wherever `data-page` sits among its
# attributes. `<section class="page" data-page="roster">` is as common as the
# attribute-first form, so the tag is matched, not a fixed attribute order.
SECTION_TAG = re.compile(
    r"<section\b[^>]*\bdata-page\s*=\s*[\"']([^\"']+)[\"'][^>]*>",
    re.IGNORECASE,
)

# Content that carries meaning without contributing text: an empty-looking
# section holding only one of these is still a real page.
MEDIA_TAG = re.compile(r"<(svg|img|canvas|input|select|textarea|iframe)\b", re.IGNORECASE)

COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
ANY_TAG = re.compile(r"<[^>]+>")
SCRIPT_OR_STYLE = re.compile(r"<(script|style)\b.*?</\1>", re.DOTALL | re.IGNORECASE)


def check(response: str) -> tuple[bool, str]:
    """Verify nav routes resolve to real sections and every section has content.

    Returns (passed, reason). The reason is recorded on pass as well as fail —
    on pass it names how many sections were actually inspected, which is how you
    confirm the check ran rather than silently matching nothing.
    """
    sections = _sections(response)

    # Matching nothing must FAIL, never silently pass. An HTML document with no
    # parseable page sections is not a prototype, and treating "no sections" as
    # "no dead links" is how a precheck stops checking anything unnoticed.
    if not sections:
        return False, "no <section data-page=...> elements found in the deliverable"

    # Reused rather than restated: static_check is the SAME production validator
    # the build loop runs after every task (routes<->sections, routes-map
    # completeness, undefined handlers, one is-active page). Re-implementing its
    # dead-link logic here would let the eval and production disagree about what
    # a broken prototype is.
    result = static_check(response)
    if not result.ok:
        return False, f"static_check: {'; '.join(result.issues)}"

    empty = [page_id for page_id, body in sections.items() if not _has_content(body)]
    if empty:
        return False, f"page section(s) with no content: {sorted(empty)}"

    return (
        True,
        f"static_check clean and all {len(sections)} page section(s) have content",
    )


def _sections(html: str) -> dict[str, str]:
    """Map each `data-page` id to its body text.

    A page's body runs from its opening tag to the next page section's opening
    tag (or end of document) rather than to the next `</section>`, so a nested
    `<section>` inside a page cannot truncate it.
    """
    matches = list(SECTION_TAG.finditer(html))
    bodies: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(html)
        bodies[match.group(1).strip()] = html[match.end() : end]
    return bodies


def _has_content(body: str) -> bool:
    """True when a section renders something — visible text or a media/form element.

    static_check deliberately allows empty sections because content grows per
    task and emptiness is normal mid-build. At grading time the build is
    finished, so an empty section is a page the user can navigate to and find
    blank — a real failure, and the reason this check is here rather than there.
    """
    if MEDIA_TAG.search(body):
        return True

    text = COMMENT.sub("", body)
    text = SCRIPT_OR_STYLE.sub("", text)
    text = ANY_TAG.sub(" ", text)
    return bool(text.strip())
