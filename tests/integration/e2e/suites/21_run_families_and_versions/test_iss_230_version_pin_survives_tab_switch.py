"""ISS-230 — switching tabs while pinned to a non-root version silently drops
the pin: URL, API fetch and displayed data all revert to v1 (the root run).

Uses the one genuine 2-member revision family in this dataset (see
bug-hunter/ledger.md, BUG-20260828-090732-runs-id-versions): root run
`77f74563-fa19-4f0b-84fd-d0224f89a54a` (v1), revision
`ef86e750-bbcd-404f-855a-fb0d5bee63f5` (v2). `21_run_families_and_versions`'s
own `a_run()` helper cannot be used here — every other run in the seed
history is a family of one, so it would never land on `/versions/2`.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework import settings
from framework.locators import run_detail as RD

ROOT_RUN_ID = "77f74563-fa19-4f0b-84fd-d0224f89a54a"
V2_RUN_ID = "ef86e750-bbcd-404f-855a-fb0d5bee63f5"

# The two members' persisted `.output` lengths, as `formatSize` renders them in
# the Files tab's "Final output" hero. Fetched from the API to prove the sizes
# are not stale fixture folklore: v1 = 247,394 chars, v2 = 85,529.
V1_SIZE = "241.6 KB"
V2_SIZE = "83.5 KB"


def _pin_to_v2(page) -> None:
    page.goto(f"/runs/{ROOT_RUN_ID}/versions/2")
    expect(page.locator(RD.LANE)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS)
    assert page.url.endswith("/versions/2"), page.url


@pytest.mark.issue("ISS-230")
@pytest.mark.parametrize("testid,suffix", [("tab-files", "/files"), ("tab-thinking", "/steps")])
def test_tab_switch_keeps_the_version_pin_in_the_url(page, shot, testid, suffix):
    """Clicking Files or Steps while pinned to /versions/2 must keep the pin
    in the URL, not silently collapse it back to the un-versioned root route."""
    _pin_to_v2(page)

    with shot(f"tab-switch-{testid}", f'When I click the "{testid}" tab while pinned to v2'):
        page.locator(f"[data-testid='{testid}']").click()
        page.wait_for_timeout(settings.SETTLE_MS)

    assert "/versions/2" in page.url, (
        f"the version pin was dropped on tab switch — url is now {page.url!r}"
    )
    assert page.url.endswith(suffix) or page.url.endswith(f"/versions/2{suffix}"), page.url


@pytest.mark.issue("ISS-230")
def test_tab_switch_keeps_fetching_the_pinned_revisions_run_id(page, shot):
    """Clicking Files while pinned to v2 must keep fetching the pinned
    revision's own run id, not silently re-fetch the root run."""
    _pin_to_v2(page)

    requests: list[str] = []
    page.on("request", lambda req: requests.append(req.url))

    with shot("tab-switch-refetch", 'When I click the "Files" tab while pinned to v2'):
        page.locator("[data-testid='tab-files']").click()
        page.wait_for_timeout(settings.SETTLE_MS)

    fetched_root = any(f"/api/runs/{ROOT_RUN_ID}" in u for u in requests)
    fetched_v2 = any(f"/api/runs/{V2_RUN_ID}" in u for u in requests)

    assert fetched_v2, (
        f"tab switch never re-fetched the pinned revision {V2_RUN_ID} — "
        f"requests seen: {requests}"
    )
    assert not fetched_root, (
        f"tab switch fell back to fetching the ROOT run {ROOT_RUN_ID} instead of "
        f"the pinned revision {V2_RUN_ID}"
    )


@pytest.mark.issue("ISS-296")
def test_picking_a_version_in_the_menu_writes_the_pin_into_the_url(page, shot):
    """Picking a version in RunHeader's "Version" menu must put the pin in the
    URL. Without it the pin lives only in one component's memory: unshareable,
    lost on refresh, and invisible to the route that carries it across tabs."""
    _pin_to_v2(page)

    page.locator(f"{RD.HEADER} button[aria-haspopup='listbox']").click()
    with shot("version-menu-pick-v1", 'When I pick "Version v1" from the Version menu'):
        page.locator("[role='option']").filter(has_text="Version v1").click()
        page.wait_for_timeout(settings.SETTLE_MS)

    assert page.url.endswith(f"/runs/{ROOT_RUN_ID}/versions/1"), (
        f"the Version menu did not write the pin into the URL — url is {page.url!r}"
    )


@pytest.mark.issue("ISS-300")
def test_the_files_tab_shows_the_pinned_versions_own_deliverable(page, shot):
    """The Files tab's "Final output" must describe the PINNED version's
    deliverable, not the live/root run's. This is the bug's own reproduction
    step 5 — the axis on which it was reopened after FIX-328."""
    page.goto(f"/runs/{ROOT_RUN_ID}/versions/2/files")
    expect(page.locator(RD.LANE)).to_be_visible()
    expect(page.get_by_text(RD.FINAL_OUTPUT).first).to_be_visible(timeout=20000)
    page.wait_for_timeout(settings.SETTLE_MS)

    with shot("files-final-output-pinned-v2", "When I cold-load the Files tab pinned to v2"):
        body = page.evaluate("() => document.body.innerText")

    final = body.split(RD.FINAL_OUTPUT, 1)[1].split(RD.AGENT_OUTPUTS, 1)[0]
    assert V2_SIZE in final, (
        f"Final output does not report the pinned v2 deliverable ({V2_SIZE}): {final[:300]!r}"
    )
    assert V1_SIZE not in final, (
        f"Final output still reports the ROOT run's v1 deliverable ({V1_SIZE}): {final[:300]!r}"
    )
