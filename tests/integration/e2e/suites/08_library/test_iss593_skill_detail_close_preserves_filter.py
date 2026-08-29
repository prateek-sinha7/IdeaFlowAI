"""BUG-20260828-093757-library-hooks-id — ISS-593 (sibling of ISS-360, Skills tab).

Same mechanism as ISS-360, different call site: `routes.librarySkill(slug)`
(`frontend/src/lib/routes.ts:129`) builds a bare `/library/skills/<id>` path
with no query string, so the `router.push` remounts `LibraryPage` and wipes
`skillCategory`/`skillSearch` before `closeDetailModal` (`:635-641`) ever
runs.

See `bug-hunter/ledger.md`'s `BUG-20260828-093757-library-hooks-id` entry and
`.knowledge/cards/20260829-0117-ISS-593.md`.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from framework.locators import library as L

CLOSE_BUTTON = "[role='dialog'] button.h-8.w-8"


@pytest.mark.issue("ISS-593")
@pytest.mark.xfail(reason="ISS-593 unfixed", strict=True)
def test_closing_skill_detail_preserves_search_and_category(page):
    """ISS-593 — closing a skill's detail view must return to the Skills
    tab with the same search text and category filter the user left active,
    not a reset to the default unfiltered "All" state.
    """
    page.goto("/library?tab=skills")
    expect(page.get_by_role("heading", name=L.HEADING)).to_be_visible()

    page.fill(L.SEARCH, "html-deck")
    # Skills pills render their label alone, with no count suffix — see
    # test_iss329_skill_empty_category.py.
    page.get_by_role("button", name="Uncategorized", exact=True).click()
    expect(page).to_have_url(re.compile("category=uncategorized"))
    expect(page.locator(L.CARD)).to_have_count(1)

    page.locator(L.CARD).first.click()
    page.wait_for_url(re.compile(r"/library/skills/"))
    expect(page.locator("[role='dialog']")).to_be_visible()

    page.locator(CLOSE_BUTTON).click()
    expect(page.locator("[role='dialog']")).to_be_hidden()
    # The close navigation, and the remount it triggers, both settle
    # asynchronously — an immediate expect() can catch the old page's
    # about-to-be-discarded state mid-transition and pass vacuously.
    page.wait_for_timeout(1000)

    assert "category=uncategorized" in page.url, (
        f"category filter lost after closing skill detail view: {page.url}"
    )
    assert page.locator(L.SEARCH).input_value() == "html-deck", (
        "search text lost after closing skill detail view"
    )
    assert page.locator(L.CARD).count() == 1, (
        "card list reset to unfiltered after closing skill detail view"
    )
