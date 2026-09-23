"""BUG-20260828-025950-library-agents-id — ISS-287.

The Library agent detail drawer's Config tab presents a "Model" override
selector and a "Save agent" button captioned "Overrides for this agent.
Defaults inherit from the workflow." Clicking "Save agent" after changing the
Model fires NO network request at all (`AgentsPopup.tsx:772-793` only calls
`onSelectionsChange?.(localSelections)`, which — per `LibraryPage.tsx:1030-1043`
— reaches nothing more durable than an in-memory `useRef`). The button flashes
"Saved" and closes the drawer regardless. Reopening the same agent (a fresh
navigation) shows the Model reverted to "Default" — the edit was silently
discarded.

See `bug-hunter/ledger.md`'s `BUG-20260828-025950-library-agents-id` entry and
`.knowledge/cards/20260828-1712-ISS-287.md` (superseded on root-cause mechanism
by `.knowledge/cards/20260828-2250-ISS-392.md`, whose corrected mechanism is
the same defect: no backend endpoint exists for this data at all).

Not part of screens/08-library.feature.md — no `scenario` marker.

Confirmed live 2026-08-28 (lane9): selecting "Claude Sonnet 4.5" in the Model
combobox and clicking "Save agent" fired zero PUT/POST/PATCH requests — only
routine GETs and the `/library?_rsc=...` navigation from the drawer closing.
A fresh navigation back to `/library/agents/material-analyzer` -> Config tab
showed the Model button still reading "Default".
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from framework.locators import library as L

MODEL_OPTION = "Claude Sonnet 4.5"
PERSIST_METHODS = re.compile(r"^(PUT|POST|PATCH)$")


def open_agent_config_tab(page):
    page.goto(f"/library/agents/{L.AGENT_SLUG}")
    drawer = page.locator(L.AGENT_DRAWER)
    expect(drawer).to_be_visible()
    drawer.get_by_role("tab", name="Config", exact=True).click()
    model_button = drawer.get_by_role("button", name=re.compile(f"^Model for {L.AGENT_NAME}$"))
    expect(model_button).to_be_visible()
    return drawer, model_button


@pytest.mark.issue("ISS-287")
@pytest.mark.xfail(reason="ISS-287 unfixed", strict=True)
def test_save_agent_fires_a_persistence_request(page):
    """ISS-287 — clicking "Save agent" after changing the Model override must
    fire a real persistence request (PUT/POST/PATCH), not zero network calls.
    """
    drawer, model_button = open_agent_config_tab(page)

    model_button.click()
    page.get_by_role("option", name=MODEL_OPTION, exact=True).click()
    expect(model_button).to_contain_text(MODEL_OPTION)

    persist_requests = []
    page.on("request", lambda req: persist_requests.append(req) if PERSIST_METHODS.match(req.method) else None)

    drawer.get_by_role("button", name="Save agent").click()
    page.wait_for_timeout(1200)  # Save agent's own 900ms close delay + margin

    assert persist_requests, (
        "Save agent fired no PUT/POST/PATCH request — the Model override "
        "change was discarded with no attempt to persist it"
    )


@pytest.mark.issue("ISS-287")
@pytest.mark.xfail(reason="ISS-287 unfixed", strict=True)
def test_saved_model_override_survives_a_fresh_navigation(page):
    """ISS-287 — a Model override saved via "Save agent" must survive
    navigating away and back to the same agent's Config tab.
    """
    _, model_button = open_agent_config_tab(page)

    model_button.click()
    page.get_by_role("option", name=MODEL_OPTION, exact=True).click()
    expect(model_button).to_contain_text(MODEL_OPTION)

    page.get_by_role("button", name="Save agent").click()
    page.wait_for_url("**/library")

    _, model_button_after = open_agent_config_tab(page)
    expect(model_button_after).to_contain_text(MODEL_OPTION, timeout=3000)
