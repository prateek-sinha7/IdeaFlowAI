"""ISS-315 — clicking "Save workflow" with an empty name must give the user a
visible signal, not a silent no-op.

`ComposerPage.tsx`'s Save-button `onClick` guards on `!name.trim()` and returns
after only `nameInputRef.current?.focus()` plus a hover-only `title` tooltip —
no `setSaveError`, no toast, no red border. The component already renders a
visible `saveError` banner (`text-status-failed`) for its other guard branches
(detached step, not authenticated); the empty-name guard alone skips it, so
the click produces zero observable feedback and no `POST /api/user-workflows`.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework.locators import composer as L


@pytest.mark.issue("ISS-315")
def test_save_with_empty_name_shows_visible_error(page):
    """Clicking Save workflow with the name field empty must surface a
    visible error, not silently do nothing."""
    page.goto("/workflows/new")
    expect(page.locator(L.HEADER_SUMMARY)).to_be_visible()

    # Add one agent so the only unmet precondition is the empty name.
    page.locator(L.ADD_AGENT).first.click()
    expect(page.locator(L.ADD_TO_PLAN).first).to_be_visible(timeout=15000)
    page.locator(L.ADD_TO_PLAN).first.click()
    page.keyboard.press("Escape")

    expect(page.locator(L.WORKFLOW_NAME)).to_have_value("")

    page.locator(L.SAVE_WORKFLOW).click()

    # A visible error must appear near the field — this is the assertion
    # that fails today (no such element is ever rendered; the click's only
    # effect is refocusing the name input).
    expect(page.locator(".text-status-failed")).to_be_visible(timeout=2000)
