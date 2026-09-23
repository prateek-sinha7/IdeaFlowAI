"""BUG-20260828-093757-library-hooks-id — ISS-594 (sibling of ISS-360, browser
Back button).

`hookSearch` (`frontend/src/components/library/LibraryPage.tsx:539`) has no
URL-derivation at all — it is wiped by the remount that fires the moment the
hook detail view is OPENED (`routes.libraryHook` pushes a bare path with no
query string). The T16 effect (`:643-665`) that reacts to a browser Back
navigation only clears the selected-item state; it never restores search
text. So even though the browser's own history mechanism restores the
`category` query param verbatim on Back, the search box stays empty —
`closeDetailModal` is not the only path to this loss.

See `bug-hunter/ledger.md`'s `BUG-20260828-093757-library-hooks-id` entry and
`.knowledge/cards/20260829-0117-ISS-594.md`.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from framework.locators import library as L


@pytest.mark.issue("ISS-594")
def test_back_button_from_hook_detail_preserves_search(page):
    """ISS-594 — pressing the browser Back button from a hook's detail view
    must return to the Hooks tab with the same search text active before the
    detail view was opened, not an emptied search box.
    """
    page.goto("/library?tab=hooks")
    expect(page.get_by_role("heading", name=L.HEADING)).to_be_visible()

    page.fill(L.SEARCH, "session")
    page.get_by_role("button", name="SessionStart", exact=True).first.click()
    expect(page).to_have_url(re.compile("category=SessionStart"))
    expect(page.locator(L.CARD)).to_have_count(1)

    page.locator(L.CARD).first.click()
    page.wait_for_url(re.compile(r"/library/hooks/"))
    expect(page.locator("[role='dialog']")).to_be_visible()

    page.go_back()
    expect(page.locator("[role='dialog']")).to_be_hidden()
    # The Back navigation, and the remount-recovery effect it triggers, both
    # settle asynchronously — an immediate expect() can catch a mid-transition
    # render and pass vacuously.
    page.wait_for_timeout(1000)

    assert page.locator(L.SEARCH).input_value() == "session", (
        "search text lost after using the browser Back button from a hook "
        "detail view"
    )
