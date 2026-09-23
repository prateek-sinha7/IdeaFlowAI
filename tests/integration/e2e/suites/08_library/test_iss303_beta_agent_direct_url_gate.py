"""BUG-20260828-050115-library — ISS-303.

"Coming Soon" agents (ids inside `LibraryPage.tsx`'s `BETA_WORKFLOWS` set) are
rendered in the catalog grid as disabled cards — `opacity-60 cursor-not-allowed`,
a "Coming Soon" badge, no `Configure ->` link — so there is no click path that
reaches their detail drawer. The grid's own `onClick` guard (`LibraryPage.tsx`,
around line 815) correctly enforces this. But the cold-mount URL-seed effect
(`LibraryPage.tsx:589-614`) that opens the detail drawer directly from
`/library/agents/{id}` on a fresh load never consults `BETA_WORKFLOWS` at all —
so navigating straight to the URL for a "Coming Soon" agent opens the identical,
fully-interactive detail drawer (Overview/Skills/Hooks/Config tabs, live
Model/Validator/Gate/Retry controls, an enabled "Save agent" button) as a
released agent, with nothing indicating the agent is unreleased.

See `bug-hunter/ledger.md`'s `BUG-20260828-050115-library` entry and
`.knowledge/cards/20260828-1935-ISS-303.md` for the root-cause analysis.

Confirmed live 2026-08-28: cold-loading `/library/agents/dotnet-inventory` and
`/library/agents/mulesoft-springboot-scaffold` (two unrelated beta pipelines)
both opened the full detail dialog. The card validates this on both ids, so
this file carries a test per id, not one test with a loop.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework.locators import library as L

# Two unrelated "Coming Soon" (BETA_WORKFLOWS) agent ids the card reproduced on.
BETA_AGENT_IDS = [
    "dotnet-inventory",
    "mulesoft-springboot-scaffold",
]


def assert_beta_agent_url_stays_gated(page, agent_id: str) -> None:
    page.goto(f"/library/agents/{agent_id}")
    expect(page.get_by_role("heading", name=L.HEADING)).to_be_visible()
    # Let the cold-mount URL-seed effect run to completion (it fires once
    # `agentsStatus === "succeeded"`) before asserting the drawer's absence —
    # asserting immediately would pass vacuously before the effect has run.
    expect(page.locator(L.CARD).first).to_be_visible()
    page.wait_for_timeout(500)
    expect(page.locator(L.AGENT_DRAWER)).not_to_be_visible()


@pytest.mark.issue("ISS-303")
def test_direct_url_to_dotnet_inventory_does_not_open_the_full_drawer(page):
    """ISS-303 — a direct cold URL load to a Coming-Soon agent id must not
    open the fully-interactive detail drawer the catalog blocks by click.
    """
    assert_beta_agent_url_stays_gated(page, BETA_AGENT_IDS[0])


@pytest.mark.issue("ISS-303")
def test_direct_url_to_mulesoft_springboot_scaffold_does_not_open_the_full_drawer(page):
    """ISS-303 — same gate, a second unrelated Coming-Soon pipeline, confirming
    the fix must live in the shared cold-mount effect, not one agent's data.
    """
    assert_beta_agent_url_stays_gated(page, BETA_AGENT_IDS[1])
