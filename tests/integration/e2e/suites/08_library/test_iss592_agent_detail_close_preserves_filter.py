"""BUG-20260828-093757-library-hooks-id — ISS-592 (sibling of ISS-360, Agents tab).

Same mechanism as ISS-360, different call site: `routes.libraryAgent(slug)`
(`frontend/src/lib/routes.ts:127`) builds a bare `/library/agents/<id>` path
with no query string, so the `router.push` remounts `LibraryPage` and wipes
`activeCategory`/`searchQuery` before `closeDetailModal` (`:635-641`) ever
runs.

See `bug-hunter/ledger.md`'s `BUG-20260828-093757-library-hooks-id` entry and
`.knowledge/cards/20260829-0117-ISS-592.md`.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from framework.locators import library as L

# AgentCapabilitiesModal's close button — a different shell/size (h-7 w-7)
# than the Hooks/Skills detail modals (h-8 w-8), see AgentsPopup.tsx:642.
CLOSE_BUTTON = "[role='dialog'] button.h-7.w-7"


@pytest.mark.issue("ISS-592")
def test_closing_agent_detail_preserves_search_and_category(page):
    """ISS-592 — closing an agent's detail view must return to the Agents
    tab with the same search text and category filter the user left active,
    not a reset to the default unfiltered "All" state.
    """
    page.goto("/library?tab=agents")
    expect(page.get_by_role("heading", name=L.HEADING)).to_be_visible()

    page.fill(L.SEARCH, "Architecture")
    L.pill(page, "App Builder").first.click()
    expect(page).to_have_url(re.compile("category=app_builder"))
    card_count_before = page.locator(L.CARD).count()
    assert card_count_before > 0

    page.locator(L.CARD).first.click()
    expect(page.locator("[role='dialog']")).to_be_visible()

    page.locator(CLOSE_BUTTON).click()
    expect(page.locator("[role='dialog']")).to_be_hidden()
    # The close navigation, and the remount it triggers, both settle
    # asynchronously — an immediate expect() can catch the old page's
    # about-to-be-discarded state mid-transition and pass vacuously.
    page.wait_for_timeout(1000)

    assert "category=app_builder" in page.url, (
        f"category filter lost after closing agent detail view: {page.url}"
    )
    assert page.locator(L.SEARCH).input_value() == "Architecture", (
        "search text lost after closing agent detail view"
    )
    assert page.locator(L.CARD).count() == card_count_before, (
        "card list reset to unfiltered after closing agent detail view"
    )
