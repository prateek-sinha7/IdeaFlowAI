"""ISS-218 / ISS-235 — "Edit brief & run again" on a failed run must open the
composer with the FAILED RUN'S OWN brief pre-filled, never blank and never a
leftover value from somewhere else.

`handleEditBrief` (frontend/src/components/layout/DashboardLayout.tsx:2151-2157)
does a bare `router.push(createRouteForType(effectiveReviseType))` with zero
brief handoff — `IdeaInputPage`'s only prefill source, `pendingHomeBrief`, is
never touched. ISS-218 pins the reproduced case: the composer opens blank.

ISS-235 is the sibling: if `pendingHomeBrief` already held a stale value the
composer would show THAT instead of blank. The originally-imagined trigger for
that stale value (typing into the Home page's own brief textbox) is no longer
reachable — that textarea was removed from the Home screen by FIX-181
(`frontend/src/components/catalog/HomeLaunchGrid.tsx:216-217`), so
`homeBrief` can never become non-empty via the current UI. This suite proves
the same underlying property ISS-235 cares about — the brief shown must always
belong to the run currently being edited, never leak from elsewhere — using
two different failed runs clicked in the same session instead.

Two seeded failed `ppt_v2` runs with distinct, non-trivial briefs:
- 72e2f445-2149-4623-b39b-f85d42f24f6a: "Create a pitch deck to propose a
  bespoke facebook for a client"
- 826d09f0-21b0-4b8f-a79f-843fc5c82adb: "A pitch deck for a vintage record
  shop's crowdfunding campaign. ..."
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework import settings
from framework.locators import run_detail as RD

RUN_A = "72e2f445-2149-4623-b39b-f85d42f24f6a"
RUN_A_BRIEF = "Create a pitch deck to propose a bespoke facebook for a client"

RUN_B = "826d09f0-21b0-4b8f-a79f-843fc5c82adb"
RUN_B_BRIEF = (
    "A pitch deck for a vintage record shop's crowdfunding campaign. Use a "
    "scrapbook/corkboard mood-board aesthetic throughout"
)


def _click_edit_brief_and_run_again(page, run_id: str) -> None:
    page.goto(f"/runs/{run_id}")
    expect(page.locator(RD.LANE)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS)
    page.locator('[data-testid="chat-relaunch-secondary"]').click()
    page.wait_for_url(lambda url: "/create/" in url)
    page.wait_for_timeout(settings.SETTLE_MS)


@pytest.mark.issue("ISS-218")
def test_edit_brief_and_run_again_prefills_the_original_brief(page, shot):
    """The composer opened by "Edit brief & run again" on a FAILED run must
    show that run's own brief text, not a blank textarea."""
    with shot("edit-brief-prefill", 'When I click "Edit brief & run again" on a failed run'):
        _click_edit_brief_and_run_again(page, RUN_A)

    textarea_value = page.locator("textarea").first.input_value()
    assert textarea_value == RUN_A_BRIEF, (
        f"expected the failed run's own brief to be pre-filled, got {textarea_value!r}"
    )


@pytest.mark.issue("ISS-235")
def test_edit_brief_shows_the_currently_viewed_runs_own_brief_not_a_leftover(page, shot):
    """Clicking "Edit brief & run again" on one failed run and then on a
    DIFFERENT failed run must show each run's OWN brief every time — never a
    value left over from the previous run's edit-brief click."""
    _click_edit_brief_and_run_again(page, RUN_A)
    first_value = page.locator("textarea").first.input_value()
    assert first_value == RUN_A_BRIEF, f"setup failed: got {first_value!r} for run A"

    with shot(
        "edit-brief-second-run",
        'When I then click "Edit brief & run again" on a DIFFERENT failed run',
    ):
        _click_edit_brief_and_run_again(page, RUN_B)

    second_value = page.locator("textarea").first.input_value()
    assert second_value.startswith(RUN_B_BRIEF[:40]), (
        f"expected run B's own brief, got {second_value!r} — "
        f"(run A's brief was {first_value!r})"
    )
    assert second_value != first_value, (
        "the second run's composer shows the SAME value as the first run's — "
        "the brief is leaking across edit-brief clicks instead of tracking the "
        "currently viewed run"
    )
