"""BUG-20260828-031600-settings-usage — ISS-291.

`/settings/usage`'s "Manage plan" button (`AccountSettings.tsx:457-459`) is
rendered enabled and styled, but has no `onClick` prop bound at all — clicking
it fires no network request, opens no modal, and navigates nowhere. This
leaves a basic-tier account with no in-app path toward the backend's already
modelled `UPGRADE_PATH: basic -> pro` (`backend/app/core/entitlements.py`).

See `bug-hunter/ledger.md`'s `BUG-20260828-031600-settings-usage` entry and
`.knowledge/cards/20260828-1917-ISS-291.md`.

Not part of screens/09-settings.feature.md — no `scenario` marker.

Confirmed live 2026-08-28 (lane9): clicking "Manage plan" on a basic-tier
account produced no dialog, no new network request, and no change to
`document.body.innerText`.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import expect

from framework.locators import settings_page as L


@pytest.mark.issue("ISS-291")
def test_manage_plan_opens_an_upgrade_affordance(page_as, shot):
    """ISS-291 — clicking "Manage plan" on a basic-tier account must open some
    plan-management/upgrade affordance (modal, page, or contact-sales flow),
    not silently do nothing.
    """
    page = page_as("basic")
    page.goto("/settings/usage")
    expect(page.get_by_text("Basic plan")).to_be_visible()

    manage_plan = page.locator(L.MANAGE_PLAN)
    expect(manage_plan).to_be_visible()

    with shot("iss291-after-click", 'When I click "Manage plan"'):
        manage_plan.click()

    # A real affordance: a dialog opens, OR the URL changes away from the
    # bare usage tab. Today neither happens — the button is a pure no-op.
    try:
        page.get_by_role("dialog").wait_for(state="visible", timeout=3_000)
        opened_dialog = True
    except PlaywrightTimeoutError:
        opened_dialog = False

    assert opened_dialog or not page.url.endswith("/settings/usage"), (
        "Manage plan produced neither a dialog nor a navigation"
    )
