"""ISS-326 — Escape must close the dashboard catalog's Inspect details modal.

Paired with `test_overlays.py::test_inspecting_a_catalog_workflow_describes_it_
without_launching`, which asserts today's wrong behaviour under
`@pytest.mark.defect`. This file asserts the desired behaviour and is expected
to fail until `WorkflowDialog.tsx` gets an Escape handler.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from framework import settings

DIALOG = '[role="dialog"]'


@pytest.mark.issue("ISS-326")
def test_escape_closes_the_catalog_inspect_dialog(page):
    """ISS-326 — Escape must close WorkflowDialog opened from a catalog card."""
    page.goto("/dashboard")
    expect(page.get_by_text("What would you like to build today?")).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS // 2)

    page.get_by_label(re.compile("^Inspect .* details$")).first.click()
    expect(page.locator(DIALOG).first).to_be_visible()

    page.keyboard.press("Escape")

    expect(page.locator(DIALOG)).to_have_count(0)
