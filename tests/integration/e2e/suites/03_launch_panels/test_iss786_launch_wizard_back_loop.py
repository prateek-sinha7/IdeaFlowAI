"""ISS-786 — sibling of ISS-741: `LaunchWizard`'s "Back to dashboard" button
(`frontend/src/components/workflow/LaunchWizard.tsx:1037-1038`) does an
unconditional `router.push(routes.home())` instead of routing through the
`window.history.length > 1 ? router.back() : router.push(...)` guard that
`DashboardLayout.handleBackNav` already establishes. Reaching `/workflow/create`
from Home (`CreationHub.tsx:31`) pushes `/workflow/create` onto the stack;
clicking "Back to dashboard" then pushes a SECOND `/dashboard` entry instead of
popping the existing one, so the stack reads
`[..., /dashboard, /workflow/create, /dashboard]`. The browser's own native
Back button then does not continue past Home — it lands right back on
`/workflow/create`, the same loop shape QA-SG-003 / ISS-741 shows for run
detail/history.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

BACK_TO_DASHBOARD = '[aria-label="Back to dashboard"]'


@pytest.mark.issue("ISS-786")
@pytest.mark.xfail(reason="ISS-786 unfixed", strict=True)
def test_native_back_after_launch_wizard_back_does_not_reloop_to_wizard(page, shot):
    """Open /workflow/create from Home, click its "Back to dashboard" button
    (lands on /dashboard, as expected), then use the browser's own native Back.
    That must continue backward past /workflow/create, not re-land on it."""
    page.goto("/dashboard")
    page.get_by_role("button", name="Build an interactive prototype").click()
    page.wait_for_url(lambda url: "/workflow/create" in url)
    expect(page.locator(BACK_TO_DASHBOARD)).to_be_visible()

    with shot("back-to-dashboard", 'When I click "Back to dashboard" on the launch wizard'):
        page.locator(BACK_TO_DASHBOARD).click()
        page.wait_for_url(lambda url: url.rstrip("/").endswith("/dashboard"))

    with shot("native-back", "And I click the browser's own native Back button"):
        page.go_back()

    assert "/workflow/create" not in page.url, (
        f"Native Back looped back into the launch wizard ({page.url!r}) instead "
        "of continuing backward past it"
    )
