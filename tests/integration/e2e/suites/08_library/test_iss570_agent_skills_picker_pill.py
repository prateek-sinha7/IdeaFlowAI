"""BUG-20260828-021300-library-skills — ISS-570.

`AgentSkillsPicker.tsx` — "the ONLY skill-attachment UI in the app" per its
own docstring, mounted from `CanvasConfigRail`, the Simple-view `AgentRow`,
and the Library agent drawer's `AgentCapabilitiesModal` — shares ISS-329's
exact mechanism: `AgentSkillsPicker.tsx:82`'s
`s.category === category` can never match `html-deck-to-pptx`'s empty
`category`, and `AgentSkillsPicker.tsx:169`'s pill-visibility filter never
renders a pill whose `id` is `""`. Since the skill declares no
`compatible_agents`, it is included as "compatible" with every agent
(R-33), so this is reachable on any agent's Skills tab, not just one.

Drives the composer's Canvas rail mount (editable), not the Library agent
drawer's `AgentCapabilitiesModal` (readOnly — every pill there renders
`disabled`, per that component's own docstring, so a click could never
reach this skill regardless of the fix).

See `bug-hunter/ledger.md`'s `BUG-20260828-021300-library-skills` entry and
`.knowledge/cards/20260829-0004-ISS-570.md`.
"""

from __future__ import annotations

import json

import pytest
from playwright.sync_api import expect

from framework import api, settings
from framework.locators import composer as L

SKILL_ID = "html-deck-to-pptx"


@pytest.mark.issue("ISS-570")
def test_skill_with_empty_category_is_unreachable_via_a_composer_pill(page):
    """ISS-570 — a skill must be reachable via the category pill matching
    its own `category`, in the Skills picker AgentSkillsPicker.tsx shares
    across the Canvas rail, Simple view, and the Library agent drawer — not
    only via the default "all" pill.
    """
    page.goto("/workflows/ppt/canvas")
    expect(page.locator(L.HEADER_SUMMARY)).to_be_visible()

    res = api.full(page, "GET", "/api/skills/library", limit=2_000_000)
    assert res["status"] < 400, f"GET /api/skills/library -> {res['status']}"
    body = json.loads(res["body"])
    entry = next(s for s in body["skills"] if s["id"] == SKILL_ID)
    category = entry["category"]
    assert category, (
        f"{SKILL_ID} still has an empty category via the API — cannot "
        "determine which pill should reach it in the picker"
    )

    expect(page.locator(L.BRIEF_NODE)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS // 2)

    page.click(L.node(L.PPT_AGENT_IDS[0]))
    page.click(L.RAIL_AGENT)
    expect(page.locator(L.AGENT_NAME)).to_be_visible()
    page.get_by_text("Skills", exact=True).first.click()

    label = category.replace("_", " ").title()
    pill = page.get_by_role("button", name=label, exact=True)
    expect(pill).to_be_visible()
    pill.click()

    row = page.get_by_text("Turn a finished HTML slide deck")
    expect(row.first).to_be_visible(
        timeout=3000
    ), f"{SKILL_ID} is not present in the picker once the {label!r} pill is active"
