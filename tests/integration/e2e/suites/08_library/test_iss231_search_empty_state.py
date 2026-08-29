"""BUG-20260827-221730-library — ISS-231.

Typing a search term into the library search box that matches no items
leaves the grid area completely blank on all three tabs — no "no results"
message, no icon, no affordance. See `bug-hunter/ledger.md`'s
`BUG-20260827-221730-library` entry and
`.knowledge/cards/20260828-1630-ISS-231.md` for the root-cause analysis
(`LibraryPage.tsx`'s three grids each render via a bare `.map()` over the
filtered array with no `length === 0` branch).

Confirmed live 2026-08-28: after typing `qqqqnomatch12345` into
`input[name="library-search"]` on the Agents tab, `div.bg-surface-card.group`
count is 0 and no text matching `/no .*match|no .*found|no results/i` is
present anywhere on the page.

The card reproduces this identically across all three tabs with three
different non-matching queries — three tests, not one with a loop.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from framework.locators import library as L

NO_RESULTS_TEXT = re.compile(r"no .*match|no .*found|no results", re.I)


def open_library(page, query: str = "") -> None:
    page.goto(f"/library{query}")
    expect(page.get_by_role("heading", name=L.HEADING)).to_be_visible()
    expect(page.locator(L.CARD).first).to_be_visible()


@pytest.mark.issue("ISS-231")
def test_agents_tab_shows_empty_state_for_a_nonmatching_search(page):
    """ISS-231 — a non-matching search on the Agents tab must show empty-state text."""
    open_library(page)
    page.fill(L.SEARCH, "qqqqnomatch12345")
    expect(page.locator(L.CARD)).to_have_count(0)
    expect(page.get_by_text(NO_RESULTS_TEXT)).to_be_visible()


@pytest.mark.issue("ISS-231")
def test_skills_tab_shows_empty_state_for_a_nonmatching_search(page):
    """ISS-231 — a non-matching search on the Skills tab must show empty-state text."""
    open_library(page, "?tab=skills")
    page.fill(L.SEARCH, "zzzznonexistentquery")
    expect(page.locator(L.CARD)).to_have_count(0)
    expect(page.get_by_text(NO_RESULTS_TEXT)).to_be_visible()


@pytest.mark.issue("ISS-231")
def test_hooks_tab_shows_empty_state_for_a_nonmatching_search(page):
    """ISS-231 — a non-matching search on the Hooks tab must show empty-state text."""
    open_library(page, "?tab=hooks")
    page.fill(L.SEARCH, "xyznohooksmatch999")
    expect(page.locator(L.CARD)).to_have_count(0)
    expect(page.get_by_text(NO_RESULTS_TEXT)).to_be_visible()
