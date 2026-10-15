"""ISS-917 — QA-KB-058: the launch wizard's header Back
(`LaunchWizard.tsx:1078`, a bare `goBackOr`) navigates away at once and drops
the typed brief. The wizard mounts outside DashboardLayout, so the shared
unsaved-work guard and its in-app "Leave without saving?" dialog never apply.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework.locators import launch_panels as L


@pytest.mark.issue("ISS-917")
def test_wizard_back_with_typed_brief_opens_leave_dialog(page, shot):
    """ISS-917 — with a typed brief, Back must open the in-app
    "Leave without saving?" dialog instead of navigating away."""
    page.goto("/dashboard")
    page.goto("/create/prototype")
    page.fill(L.BRIEF, "ISS-917 unsaved brief marker")

    with shot("back-with-brief", "When I click Back with a typed brief"):
        page.click(L.BACK_TO_DASHBOARD)
        page.wait_for_timeout(1500)

    dialog = page.get_by_role("dialog").filter(has_text="Leave without saving?")
    assert "/create/prototype" in page.url and dialog.count() > 0, (
        f"Back left the wizard ({page.url!r}) with no in-app leave dialog; "
        "the typed brief was discarded silently"
    )
    expect(dialog.get_by_role("button", name="Stay")).to_be_visible()
