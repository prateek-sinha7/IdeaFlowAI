"""ISS-314 — the Preview toolbar's "Full Screen" button must stay reachable
at narrow (mobile) viewport widths.

`PPTTabActions`'s wrapper div (`frontend/src/components/preview/PreviewPanel.tsx`)
is `flex items-center gap-1.5 flex-shrink-0` with no `flex-wrap`/`overflow-x`
anywhere in its ancestor chain. At a 375px viewport the row's content has
nowhere to go, so "Full Screen" (title="Open in new tab") is pushed entirely
outside the visible/interactive viewport with no scroll affordance to reach it.

That toolbar is PPT-ONLY: PreviewPanel renders `PPTTabActions` behind
`activeTab === "preview" && renderType === "ppt" && (pptContent || pptxCode)`.
So the run has to be a completed deck run or the button never mounts and the
layout this scenario measures does not exist on screen.

The run is discovered rather than pinned. This used to name
`b9feac1c-ec21-4531-8ba7-bb391786993e`, which has since been pruned — the page
rendered nothing and the scenario died on a 30s locator timeout that pointed at
the button rather than at the missing run.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework import api, settings

from framework.locators import run_history as RH

FULLSCREEN = 'button[title="Open in new tab"]'


def _a_completed_deck_run(page) -> str:
    """A completed ppt-family run — the only kind that mounts PPTTabActions."""
    page.goto("/runs")
    expect(page.locator(RH.ROW).first).to_be_visible()
    for index, label in enumerate(RH.rows(page)):
        if RH.status_of(label) != "completed":
            continue
        page.goto("/runs")
        expect(page.locator(RH.ROW).first).to_be_visible()
        page.locator(RH.ROW).nth(index).click()
        page.wait_for_url(lambda url: "/runs/" in url)
        run_id = page.url.split("/runs/")[1].split("/")[0].split("?")[0]
        run_type = api.json_body(page, "GET", f"/api/runs/{run_id}").get("type") or ""
        # Keyed on the deck FAMILY, not one literal id: ppt, ppt_v2 and
        # ppt_revision all render the same HTML deck through the same toolbar.
        if run_type.startswith("ppt"):
            return run_id
    pytest.skip(
        "no completed ppt-family run in this history, so the PPT preview "
        "toolbar this scenario measures never mounts"
    )


@pytest.mark.issue("ISS-314")
def test_fullscreen_button_reachable_at_mobile_viewport(page):
    """At a 375px-wide viewport, the "Full Screen" button must be fully
    within the viewport's horizontal bounds — reachable by click, not pushed
    off to the right with no way to scroll it into view."""
    run_id = _a_completed_deck_run(page)

    page.goto(f"/runs/{run_id}/preview/full")
    page.wait_for_load_state("networkidle")
    page.set_viewport_size({"width": 375, "height": 700})
    page.wait_for_timeout(settings.SETTLE_MS)

    fullscreen_button = page.locator(FULLSCREEN, has_text="Full Screen")
    fullscreen_button.wait_for(state="attached")

    inner_width = page.evaluate("window.innerWidth")
    box = fullscreen_button.bounding_box()
    assert box is not None, "Full Screen button has no bounding box"
    assert box["x"] + box["width"] <= inner_width, (
        f"Full Screen button's right edge ({box['x'] + box['width']}) is outside the "
        f"{inner_width}px viewport — it is unreachable by click and there is no "
        f"scroll affordance to bring it into view."
    )
