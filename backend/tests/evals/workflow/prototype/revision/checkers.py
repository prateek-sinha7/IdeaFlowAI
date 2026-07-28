"""Checkers for the prototype/revision live scenarios — pass/fail LOGIC has
to be code (it inspects the delivered HTML); everything else about a
scenario is data, declared in scenarios/*.yaml and resolved against this
module's CHECKERS registry by name.
"""

from __future__ import annotations

import re

# prototype_multi_issue_repair's fixture is a small (~8KB) prototype, so its
# real page content (~140-250 chars/page) is well below example1's ~2KB-per-
# page floor — this scenario gets its own much smaller floor scaled to its
# own content. It's set to clear real dashboard/settings/roles/mfa/audit
# content while still catching the fixture's "No data available" placeholder
# (~20 chars) — the copy a real browser actually renders, per
# document.querySelector's first-match semantics (see the fixture's own
# comments).
_MULTI_ISSUE_PAGES = ("dashboard", "settings", "roles", "mfa", "audit")
_MULTI_ISSUE_MIN_CONTENT_CHARS = 60


def save_button_wired(final_html: str) -> tuple[bool, str]:
    """Is the Save button (#save-btn) actually wired — inline onclick or JS listener?"""
    btn_match = re.search(r'<button[^>]*id="save-btn"[^>]*>', final_html)
    if not btn_match:
        return False, "Save button disappeared from the delivered file"
    btn_tag = btn_match.group(0)

    inline = re.search(r'onclick="([A-Za-z_$][\w$]*)\s*\(', btn_tag)
    script_bound = re.search(
        r"(getElementById\(['\"]save-btn['\"]\)|querySelector\(['\"]#save-btn['\"]\))"
        r"[\s\S]{0,120}addEventListener",
        final_html,
    )
    wired = False
    if inline:
        fn = inline.group(1)
        wired = bool(
            re.search(rf"function\s+{re.escape(fn)}\s*\(", final_html)
            or re.search(rf"{re.escape(fn)}\s*=\s*(async\s*)?\(", final_html)
        )
    wired = wired or bool(script_bound)
    if not wired:
        return False, "Save button has no working handler (neither inline nor script-bound)"
    return True, ""


def reports_page_reachable(final_html: str) -> tuple[bool, str]:
    """Is there a Reports page (section + route) reachable via a sidebar nav link?"""
    has_section = bool(re.search(r'<section[^>]*data-page="reports"', final_html))
    has_route = bool(re.search(r"reports\s*:\s*['\"]#/reports['\"]", final_html))
    has_nav_link = bool(
        re.search(r'<a[^>]*class="nav-item"[^>]*href="#/reports"', final_html)
    )
    if not has_section:
        return False, "no <section data-page=\"reports\"> in delivered file"
    if not has_route:
        return False, "no 'reports' entry in the routes map"
    if not has_nav_link:
        return False, "Reports page exists but has NO sidebar nav link (unreachable)"
    return True, ""


def _duplicated_pages_have_real_content(
    final_html: str, page_ids: tuple[str, ...], min_content_chars: int
) -> tuple[bool, str]:
    """Every page in ``page_ids`` exists EXACTLY ONCE and has substantive content.

    The fixture's whole document is DUPLICATED end-to-end: every
    ``<section data-page="...">`` appears twice. With a duplicate section per
    page and a single ``document.querySelector`` (not ``querySelectorAll``)
    toggling ``is-active``, which copy actually renders is undefined/fragile
    — a genuine rendering bug this static check cannot directly observe
    (would need ``render_check``/headless Chromium for that), but the
    STRUCTURAL half of the fix (dedup + real content surviving) is checkable
    here.
    """
    for page_id in page_ids:
        matches = re.findall(
            rf'<section[^>]*data-page="{page_id}"[^>]*>([\s\S]*?)</section>',
            final_html,
        )
        if not matches:
            return False, f"page '{page_id}' is missing entirely from the delivered file"
        if len(matches) > 1:
            return False, (
                f"page '{page_id}' still appears {len(matches)} times — the "
                f"duplicated-document defect was not cleaned up"
            )
        body = re.sub(r"<h2[^>]*>.*?</h2>", "", matches[0], flags=re.S).strip()
        if len(body) < min_content_chars:
            return False, (
                f"page '{page_id}' has only {len(body)} chars of content after "
                f"its heading — looks blank/placeholder, not real data"
            )
    return True, ""


def audit_nav_link_matches_route(final_html: str) -> tuple[bool, str]:
    """Does the Audit sidebar link's href actually match the Audit page?"""
    m = re.search(r'<a[^>]*data-page-link="audit"[^>]*>', final_html)
    if not m:
        return False, 'no sidebar nav link for the Audit page (data-page-link="audit")'
    href_m = re.search(r'href="([^"]+)"', m.group(0))
    href = href_m.group(1) if href_m else None
    if href != "#/audit":
        return False, (
            f"Audit nav link points to '{href}', not '#/audit' — clicking it "
            f"never shows the Audit page"
        )
    return True, ""


def roles_route_matches_nav_href(final_html: str) -> tuple[bool, str]:
    """Does the routes map's 'roles' entry match the sidebar's '#/roles' href?"""
    m = re.search(r"roles\s*:\s*['\"]([^'\"]+)['\"]", final_html)
    if not m:
        return False, "no 'roles' entry in the routes map"
    if m.group(1) != "#/roles":
        return False, (
            f"routes map's 'roles' entry is '{m.group(1)}', not '#/roles' — "
            f"stale, doesn't match the sidebar link"
        )
    return True, ""


# Native browser globals a fixed onclick may legitimately call directly —
# not "undefined" just because there's no local `function` declaration for
# them. Caught a real false positive: a live run's onclick="alert(...)" for
# a wired Export button was flagged as calling an "undefined function".
_JS_GLOBALS = frozenset({"alert", "confirm", "prompt"})


def no_undefined_onclick_handlers(final_html: str) -> tuple[bool, str]:
    """Does every onclick="fn(...)" reference an actually-defined function?"""
    fn_names = sorted(set(re.findall(r'onclick="([A-Za-z_$][\w$]*)\s*\(', final_html)))
    missing = [
        fn
        for fn in fn_names
        if fn not in _JS_GLOBALS
        and not re.search(rf"function\s+{re.escape(fn)}\s*\(", final_html)
    ]
    if missing:
        return False, f"onclick handler(s) reference undefined function(s): {missing}"
    return True, ""


def no_placeholder_lorem_ipsum_text(final_html: str) -> tuple[bool, str]:
    """Is the MFA page's placeholder 'Lorem ipsum' text gone?"""
    if re.search(r"lorem ipsum", final_html, re.IGNORECASE):
        return False, "placeholder 'Lorem ipsum' text still present — MFA page needs real content"
    return True, ""


def org_input_id_not_duplicated(final_html: str) -> tuple[bool, str]:
    """Does id="org" appear exactly once (not duplicated, not deleted)?"""
    count = len(re.findall(r'id="org"', final_html))
    if count == 0:
        return False, 'the organization-name input (id="org") is missing entirely'
    if count > 1:
        return False, f'id="org" appears {count} times — duplicate id breaks getElementById(\'org\')'
    return True, ""


def no_dead_placeholder_links(final_html: str) -> tuple[bool, str]:
    """Is the Audit page's dead href="#" placeholder link gone?"""
    if re.search(r'href="#"', final_html):
        return False, (
            'a link still points to the placeholder href="#" (e.g. Audit\'s '
            "'View all activity') instead of a real target"
        )
    return True, ""


def page_title_element_and_wiring_present(final_html: str) -> tuple[bool, str]:
    """Does an id="page-title" element exist AND get read/updated by the script?"""
    if not re.search(r'id="page-title"', final_html):
        return False, (
            'no element with id="page-title" — the top bar title can never '
            "update (check for a typo'd id)"
        )
    if not re.search(r"getElementById\(['\"]page-title['\"]\)", final_html):
        return False, 'no script wiring reads/updates id="page-title" — title updates are dead code'
    return True, ""


def prototype_multi_issue_repair(final_html: str) -> tuple[bool, str]:
    """All 10 issues baked into prototype_multi_issue_repair.html, fixed.

    Runs every sub-check (not short-circuiting on the first failure) and
    reports the FULL list of what's still broken — the point of this
    scenario is validating whether a single revision turn fixes everything
    in a realistic multi-bug punch list, not just the first bug it hits.
    """
    checks = [
        (
            "1. whole-document duplication cleaned up, real content survives",
            lambda h: _duplicated_pages_have_real_content(
                h, _MULTI_ISSUE_PAGES, _MULTI_ISSUE_MIN_CONTENT_CHARS
            ),
        ),
        ("2. Save button wired (S1)", save_button_wired),
        ("3. Reports page reachable (S2)", reports_page_reachable),
        ("4. Audit nav link matches its route", audit_nav_link_matches_route),
        ("5. Roles route matches its nav href", roles_route_matches_nav_href),
        ("6. no undefined onclick handlers", no_undefined_onclick_handlers),
        ("7. no placeholder Lorem ipsum text", no_placeholder_lorem_ipsum_text),
        ("8. organization-name input id not duplicated", org_input_id_not_duplicated),
        ('9. no dead href="#" placeholder links', no_dead_placeholder_links),
        ("10. page-title element + wiring present", page_title_element_and_wiring_present),
    ]
    failures = []
    for label, fn in checks:
        ok, detail = fn(final_html)
        if not ok:
            failures.append(f"  - {label}: {detail}")
    if failures:
        return False, f"{len(failures)}/10 issue(s) still unresolved:\n" + "\n".join(failures)
    return True, "all 10 issues resolved"


CHECKERS = {
    "prototype_multi_issue_repair": prototype_multi_issue_repair,
}
