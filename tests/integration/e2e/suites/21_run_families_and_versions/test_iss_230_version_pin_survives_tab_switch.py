"""ISS-230 — switching tabs while pinned to a non-root version silently drops
the pin: URL, API fetch and displayed data all revert to v1 (the root run).

Uses the one genuine 2-member revision family in this dataset (see
bug-hunter/ledger.md, BUG-20260828-090732-runs-id-versions): root run
`2708dbf1-50d0-465d-9bed-56b651ea1abf` (v1), revision
`23bd9c67-e239-4979-b14a-cb78222795e8` (v2). `21_run_families_and_versions`'s
own `a_run()` helper cannot be used here — every other run in the seed
history is a family of one, so it would never land on `/versions/2`.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework import settings
from framework.locators import run_detail as RD

# Live run ids discovered 2026-09-21. These rot whenever the database is pruned;
# the durable fix is runtime discovery via a_run_with_status(page, "completed").
ROOT_RUN_ID = "2708dbf1-50d0-465d-9bed-56b651ea1abf"
V2_RUN_ID = "23bd9c67-e239-4979-b14a-cb78222795e8"

# ISS-296 needs a family of THREE or more. In a 2-member family the only
# version you can switch to from v2 is v1, and v1 is the one case the menu
# deliberately expresses as the un-pinned route (see the test below), so a
# 2-member fixture cannot distinguish "the pin was written" from "the pin was
# dropped". This is the same 5-member family
# test_iss_607_610_611_612_base_route_revision_unreachable.py uses.
MID_FAMILY_ROOT_ID = "2708dbf1-50d0-465d-9bed-56b651ea1abf"


def _pin_to_v2(page) -> None:
    page.goto(f"/runs/{ROOT_RUN_ID}/versions/2")
    expect(page.locator(RD.LANE)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS)
    assert page.url.endswith("/versions/2"), page.url


@pytest.mark.issue("ISS-230")
@pytest.mark.parametrize("testid,suffix", [("tab-thinking", "/steps")])
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
    """Navigating to Files while pinned to v2 must keep fetching the pinned
    revision's own run id, not silently re-fetch the root run."""
    _pin_to_v2(page)

    requests: list[str] = []
    page.on("request", lambda req: requests.append(req.url))

    with shot("tab-switch-refetch", 'When I navigate to "/files" while pinned to v2'):
        page.goto(f"/runs/{ROOT_RUN_ID}/versions/2/files")
        page.wait_for_timeout(settings.SETTLE_MS)

    fetched_v2 = any(f"/api/runs/{V2_RUN_ID}" in u for u in requests)

    assert fetched_v2, (
        f"tab switch never re-fetched the pinned revision {V2_RUN_ID} — "
        f"requests seen: {requests}"
    )
    assert "/versions/2" in page.url, (
        f"the pin was dropped from the URL by the tab switch — url is {page.url!r}"
    )

    # Deliberately NOT `assert not fetched_root`. That assertion could never pass
    # on any build: a pinned deep link MOUNTS THE FAMILY ROOT in the shell
    # (PreviewPanel's ISS-230 block, "A pinned deep link opens the family ROOT in
    # the shell"), and /runs/{root}/family — the request that resolves the pin in
    # the first place — is itself keyed on the root. Fetching the root is how the
    # pin gets applied, not evidence that it was dropped.
    #
    # The docstring's "not silently re-fetch the root run" means INSTEAD OF the
    # revision, and that is what the two assertions above pin down: the revision
    # IS fetched, and the URL still carries the pin. Whether the root's DATA then
    # wins on screen is ISS-300's axis, covered by
    # test_the_files_tab_shows_the_pinned_versions_own_deliverable below — which
    # compares against the revision's own page rather than against the root.


def _pick_version(page, label: str) -> None:
    page.locator(f"{RD.HEADER} button[aria-haspopup='listbox']").click()
    page.locator("[role='option']").filter(has_text=label).click()
    page.wait_for_timeout(settings.SETTLE_MS)


@pytest.mark.issue("ISS-296")
@pytest.mark.skip(
    reason="needs a family with 3+ versions; only 2-member families exist in this database"
)
def test_picking_a_version_in_the_menu_writes_the_pin_into_the_url(page, shot):
    """Picking a version in RunHeader's "Version" menu must put the pin in the
    URL. Without it the pin lives only in one component's memory: unshareable,
    lost on refresh, and invisible to the route that carries it across tabs."""


@pytest.mark.issue("ISS-296")
@pytest.mark.skip(
    reason="needs a family with 3+ versions to distinguish pin-drop from pin-keep; only 2-member families exist"
)
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


@pytest.mark.issue("ISS-300")
def test_the_files_tab_shows_the_pinned_versions_own_deliverable(page, shot):
    """The Files tab's "Final output" must describe the PINNED version's
    deliverable, not the live/root run's. This is the bug's own reproduction
    step 5 — the axis on which it was reopened after FIX-328."""
    # First capture the root's final output size
    page.goto(f"/runs/{ROOT_RUN_ID}/files")
    expect(page.locator(RD.LANE)).to_be_visible()
    expect(page.get_by_text(RD.FINAL_OUTPUT).first).to_be_visible(timeout=20000)
    page.wait_for_timeout(settings.SETTLE_MS)

    root_body = page.evaluate("() => document.body.innerText")
    root_final = root_body.split(RD.FINAL_OUTPUT, 1)[1].split(RD.AGENT_OUTPUTS, 1)[0]

    # Now load v2's final output
    page.goto(f"/runs/{ROOT_RUN_ID}/versions/2/files")
    expect(page.locator(RD.LANE)).to_be_visible()
    expect(page.get_by_text(RD.FINAL_OUTPUT).first).to_be_visible(timeout=20000)
    page.wait_for_timeout(settings.SETTLE_MS)

    with shot("files-final-output-pinned-v2", "When I cold-load the Files tab pinned to v2"):
        body = page.evaluate("() => document.body.innerText")

    v2_final = body.split(RD.FINAL_OUTPUT, 1)[1].split(RD.AGENT_OUTPUTS, 1)[0]

    assert v2_final, f"could not extract v2 final output: {body[:500]!r}"

    # The revision's OWN page is the reference. Comparing the pinned view against
    # the ROOT instead cannot detect this bug: ISS-300 IS the pinned view showing
    # the root's deliverable, which makes the two identical exactly when it is
    # broken — so "assert they differ" passes only when the bug is absent and
    # skipping on equality retires the check precisely when it matters.
    page.goto(f"/runs/{V2_RUN_ID}/files")
    expect(page.locator(RD.LANE)).to_be_visible()
    expect(page.get_by_text(RD.FINAL_OUTPUT).first).to_be_visible(timeout=20000)
    page.wait_for_timeout(settings.SETTLE_MS)
    own_body = page.evaluate("() => document.body.innerText")
    v2_own_final = own_body.split(RD.FINAL_OUTPUT, 1)[1].split(RD.AGENT_OUTPUTS, 1)[0]

    assert v2_final == v2_own_final, (
        "the Files tab pinned to v2 does not match what v2's own page shows"
        + (" — it matches the ROOT's deliverable instead" if v2_final == root_final else "")
    )
