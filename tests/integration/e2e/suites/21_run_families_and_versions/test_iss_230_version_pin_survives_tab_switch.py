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
# the Files tab's "Final output" hero. Computed from UTF-8 byte counts (not char
# counts): v1 = 247,691 bytes, v2 = 85,624 bytes. The app renders formatSize(utf8Bytes(...)).
V1_SIZE = "241.9 KB"
V2_SIZE = "83.6 KB"

# ISS-296 needs a family of THREE or more. In a 2-member family the only
# version you can switch to from v2 is v1, and v1 is the one case the menu
# deliberately expresses as the un-pinned route (see the test below), so a
# 2-member fixture cannot distinguish "the pin was written" from "the pin was
# dropped". This is the same 5-member family
# test_iss_607_610_611_612_base_route_revision_unreachable.py uses.
MID_FAMILY_ROOT_ID = "b868a6b6-ed11-4ae9-a512-6df2b1c5ad4e"


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


def _pick_version(page, label: str) -> None:
    page.locator(f"{RD.HEADER} button[aria-haspopup='listbox']").click()
    page.locator("[role='option']").filter(has_text=label).click()
    page.wait_for_timeout(settings.SETTLE_MS)


@pytest.mark.issue("ISS-296")
def test_picking_a_version_in_the_menu_writes_the_pin_into_the_url(page, shot):
    """Picking a version in RunHeader's "Version" menu must put the pin in the
    URL. Without it the pin lives only in one component's memory: unshareable,
    lost on refresh, and invisible to the route that carries it across tabs."""
    page.goto(f"/runs/{MID_FAMILY_ROOT_ID}/versions/2")
    expect(page.locator(RD.LANE)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS)
    assert page.url.endswith("/versions/2"), page.url

    with shot("version-menu-pick-v3", 'When I pick "Version v3" from the Version menu'):
        _pick_version(page, "Version v3")

    assert page.url.endswith(f"/runs/{MID_FAMILY_ROOT_ID}/versions/3"), (
        f"the Version menu did not write the pin into the URL — url is {page.url!r}"
    )


@pytest.mark.issue("ISS-296")
def test_picking_the_version_the_base_route_already_shows_drops_the_pin(page, shot):
    """The one version the menu does NOT write a segment for.

    `handleSelectVersion` keys its "no pin needed" shortcut on `unpinnedRunId`
    (PreviewPanel.tsx) — the run the un-versioned route already renders. A
    pinned deep link opens the family ROOT in the shell, so picking v1 lands on
    the bare `/runs/{root}`, which shows v1. The pin is redundant, not lost:
    the URL is still shareable and still survives a refresh, which is the whole
    of what ISS-296 asked for.

    Keying this on `unpinnedRunId` rather than on the family's newest member is
    what ISS-607/610/611 needed, so a change here silently breaks those.
    """
    page.goto(f"/runs/{MID_FAMILY_ROOT_ID}/versions/2")
    expect(page.locator(RD.LANE)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS)

    with shot("version-menu-pick-v1", 'When I pick "Version v1" from the Version menu'):
        _pick_version(page, "Version v1")

    assert page.url.endswith(f"/runs/{MID_FAMILY_ROOT_ID}"), (
        f"picking the version the base route already shows should drop the "
        f"redundant segment, not keep or change it — url is {page.url!r}"
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
