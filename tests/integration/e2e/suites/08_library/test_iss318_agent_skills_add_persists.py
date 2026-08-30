"""BUG-20260828-092630-library-agents-id — ISS-318.

The Library agent detail drawer's Skills tab renders full interactive
success feedback for "Add" — the row's button flips from "Add <skill>" to a
filled "Remove <skill>" checkmark, and a count badge appears next to the
"Skills" section header — for an action that fires ZERO network requests and
has no Save/Cancel affordance anywhere on the tab (unlike the Config tab).
`LibraryPage.tsx` supplies `onSkillsChange` to `AgentCapabilitiesModal`, which
flips `AgentSkillsPicker`'s `readOnly` to `false` even though the picker's own
documented contract names this exact mount as having "nowhere to write back".
The callback only writes a `useRef` (`savedSkillsRef`) scoped to
`LibraryPage`'s own mount lifetime, so a reload silently discards it with no
warning.

See `bug-hunter/ledger.md`'s `BUG-20260828-092630-library-agents-id` entry and
`.knowledge/cards/20260828-1956-ISS-318.md`.

Not part of screens/08-library.feature.md — no `scenario` marker.

Confirmed live 2026-08-28 (lane9): clicking "Add .NET Backend Expert" flips
the button to `aria-label="Remove .NET Backend Expert"` and the "Skills"
header badge shows "1", with zero PUT/POST/PATCH/GET requests fired for the
click. A fresh navigation back to the same agent's Skills tab shows the badge
gone and the button reading "Add .NET Backend Expert" again.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from framework.locators import library as L

SKILL_NAME = ".NET Backend Expert"
PERSIST_METHODS = re.compile(r"^(GET|PUT|POST|PATCH)$")


def open_agent_skills_tab(page):
    page.goto(f"/library/agents/{L.AGENT_SLUG}")
    drawer = page.locator(L.AGENT_DRAWER)
    expect(drawer).to_be_visible()
    drawer.get_by_role("tab", name="Skills", exact=True).click()
    add_button = drawer.get_by_role("button", name=f"Add {SKILL_NAME}", exact=True)
    expect(add_button).to_be_visible()
    return drawer, add_button


@pytest.mark.issue("ISS-318")
@pytest.mark.xfail(reason="ISS-318 unfixed", strict=True)
def test_add_skill_fires_a_persistence_request(page):
    """ISS-318 — clicking "Add" on a skill in the drawer's Skills tab must
    fire a real network request (its own /api/agents* or /api/skills* call),
    not zero — the button flips to a filled "Remove" checkmark with no
    request ever sent.
    """
    drawer, add_button = open_agent_skills_tab(page)

    requests = []
    page.on("request", lambda req: requests.append(req) if PERSIST_METHODS.match(req.method) else None)

    add_button.click()
    expect(drawer.get_by_role("button", name=f"Remove {SKILL_NAME}", exact=True)).to_be_visible()
    page.wait_for_timeout(500)

    agent_or_skill_requests = [r for r in requests if "/api/agents" in r.url or "/api/skills" in r.url]
    assert agent_or_skill_requests, (
        "Add fired no /api/agents or /api/skills request — the skill grant "
        "was rendered as successful (checkmark) with nothing sent to persist it"
    )


@pytest.mark.issue("ISS-318")
@pytest.mark.xfail(reason="ISS-318 unfixed", strict=True)
def test_added_skill_survives_a_fresh_navigation(page):
    """ISS-318 — a skill added via the drawer's "Add" button must survive
    navigating away and back to the same agent's Skills tab.
    """
    drawer, add_button = open_agent_skills_tab(page)

    add_button.click()
    expect(drawer.get_by_role("button", name=f"Remove {SKILL_NAME}", exact=True)).to_be_visible()

    page.goto("/library")
    page.goto(f"/library/agents/{L.AGENT_SLUG}")
    drawer_after = page.locator(L.AGENT_DRAWER)
    expect(drawer_after).to_be_visible()
    drawer_after.get_by_role("tab", name="Skills", exact=True).click()
    expect(
        drawer_after.get_by_role("button", name=f"Remove {SKILL_NAME}", exact=True)
    ).to_be_visible(timeout=3000)
