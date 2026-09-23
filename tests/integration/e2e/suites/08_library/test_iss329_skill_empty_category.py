"""BUG-20260828-021300-library-skills — ISS-329.

`backend/app/agents/skills_catalog.py:112` defaults a skill's `category` to
`""` when its `SKILL.md` frontmatter omits the field. `html-deck-to-pptx` is
the one skill missing it: its card renders a blank category-badge line
(`LibraryPage.tsx:928`'s `<p ...capitalize">{skill.category}</p>` with an
empty string), and `backend/app/api/skills.py:35`
(`categories = sorted({e.category for e in entries if e.category})`) drops
the empty string out of the pill list entirely, so no specific category pill
ever selects it — only "All" or a name search surfaces the card.

See `bug-hunter/ledger.md`'s `BUG-20260828-021300-library-skills` entry and
`.knowledge/cards/20260828-1838-ISS-329.md`.
"""

from __future__ import annotations

import json
import re

import pytest
from playwright.sync_api import expect

from framework import api
from framework.locators import library as L

SKILL_ID = "html-deck-to-pptx"

CATEGORY_BADGE = 'p.uppercase.tracking-\\[0\\.1em\\].font-semibold.capitalize'


def _open_skills_tab_and_search(page, query: str):
    page.goto("/library?tab=skills")
    expect(page.get_by_role("heading", name=L.HEADING)).to_be_visible()
    page.fill(L.SEARCH, query)


@pytest.mark.issue("ISS-329")
def test_skill_category_badge_is_not_blank(page):
    """ISS-329 — every skill's category badge must render a real value, not
    an empty string.
    """
    _open_skills_tab_and_search(page, SKILL_ID)
    card = page.locator(L.CARD).filter(has_text="html-deck-to-pptx")
    expect(card).to_have_count(1)

    badge_text = card.locator(CATEGORY_BADGE).first.inner_text()
    assert badge_text.strip() != "", (
        f"{SKILL_ID}'s category badge is blank — expected a real category "
        "value like every other skill card"
    )


@pytest.mark.issue("ISS-329")
def test_skill_is_reachable_via_its_own_category_pill(page):
    """ISS-329 — a skill must be reachable by clicking the category pill
    matching its own `category` value, not only via "All" or search.
    """
    page.goto("/library?tab=skills")
    res = api.full(page, "GET", "/api/skills/library", limit=2_000_000)
    assert res["status"] < 400, f"GET /api/skills/library -> {res['status']}"
    body = json.loads(res["body"])
    entry = next(s for s in body["skills"] if s["id"] == SKILL_ID)
    category = entry["category"]
    assert category, (
        f"{SKILL_ID} still has an empty category via the API — cannot "
        "determine which pill should reach it"
    )

    page.goto("/library?tab=skills")
    expect(page.get_by_role("heading", name=L.HEADING)).to_be_visible()
    # Skills pills render their label alone, with no count suffix (unlike
    # agent pills, which L.pill()'s "^{label}\s" regex is built for) — an
    # exact-text role match is the right locator here.
    page.get_by_role("button", name=category.capitalize(), exact=True).first.click()
    # A leading `*` glob never matches across the `/` in the URL's path in
    # this Playwright version (confirmed against test_iss360's identical
    # pattern too) — a regex sidesteps that glob quirk.
    expect(page).to_have_url(re.compile(rf"category={category}"))

    card = page.locator(L.CARD).filter(has_text="html-deck-to-pptx")
    expect(card).to_have_count(
        1, timeout=3000
    ), f"{SKILL_ID} is not present under its own {category!r} category pill"
