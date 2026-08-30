"""BUG-20260828-093757-library-hooks-id — ISS-360.

Opening a hook's detail view pushes a bare `/library/hooks/<id>` URL with no
query string (`routes.libraryHook`, `frontend/src/lib/routes.ts:131`). That
navigation remounts `LibraryPage`, which resets `hookSearch`/`hookEvent`
before `closeDetailModal` ever runs — so closing the detail view always lands
back on `/library?tab=hooks` with the search box empty and the "All" category
pill active, discarding whatever filter/search the user had active.

See `bug-hunter/ledger.md`'s `BUG-20260828-093757-library-hooks-id` entry and
`.knowledge/cards/20260828-1917-ISS-360.md`.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from framework.locators import library as L

CLOSE_BUTTON = "[role='dialog'] button.h-8.w-8"


@pytest.mark.issue("ISS-360")
def test_closing_hook_detail_preserves_search_and_category(page):
    """ISS-360 — closing a hook's detail view must return to the Hooks tab
    with the same search text and category filter the user left active, not
    a reset to the default unfiltered "All" state.
    """
    page.goto("/library?tab=hooks")
    expect(page.get_by_role("heading", name=L.HEADING)).to_be_visible()

    page.fill(L.SEARCH, "session")
    # Hook pills render their label alone, with no count suffix (unlike
    # agent pills, which L.pill()'s "^{label}\s" regex is built for) — an
    # exact-text role match is the right locator here.
    page.get_by_role("button", name="SessionStart", exact=True).first.click()
    expect(page).to_have_url(re.compile("category=SessionStart"))
    expect(page.locator(L.CARD)).to_have_count(1)

    page.locator(L.CARD).first.click()
    page.wait_for_url(re.compile(r"/library/hooks/"))
    expect(page.locator("[role='dialog']")).to_be_visible()

    page.locator(CLOSE_BUTTON).click()
    expect(page.locator("[role='dialog']")).to_be_hidden()
    # The close navigation, and the remount it triggers, both settle
    # asynchronously — an immediate expect() can catch the old page's
    # about-to-be-discarded state mid-transition and pass vacuously.
    page.wait_for_timeout(1000)

    assert "category=SessionStart" in page.url, (
        f"category filter lost after closing hook detail view: {page.url}"
    )
    assert page.locator(L.SEARCH).input_value() == "session", (
        "search text lost after closing hook detail view"
    )
    assert page.locator(L.CARD).count() == 1, (
        "card list reset to unfiltered after closing hook detail view"
    )
