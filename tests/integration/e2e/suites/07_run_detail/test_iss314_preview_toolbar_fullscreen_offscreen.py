"""ISS-314 — the Preview toolbar's "Full Screen" button must stay reachable
at narrow (mobile) viewport widths.

`PPTTabActions`'s wrapper div (`frontend/src/components/preview/PreviewPanel.tsx`,
around line 1540) is `flex items-center gap-1.5 flex-shrink-0` with no
`flex-wrap`/`overflow-x` anywhere in its ancestor chain. At a 375px viewport
the row's ~493px of content has nowhere to go, so "Full Screen" (title="Open
in new tab") is pushed entirely outside the visible/interactive viewport with
no scroll affordance to reach it.

Run used: b9feac1c-ec21-4531-8ba7-bb391786993e (completed run with a
deliverable, Preview tab auto-selected) — same run id the ISS-314 card
reproduced against.
"""

from __future__ import annotations

import pytest

COMPLETED_RUN_WITH_DELIVERABLE = "b9feac1c-ec21-4531-8ba7-bb391786993e"


@pytest.mark.issue("ISS-314")
def test_fullscreen_button_reachable_at_mobile_viewport(page):
    """At a 375px-wide viewport, the "Full Screen" button must be fully
    within the viewport's horizontal bounds — reachable by click, not pushed
    off to the right with no way to scroll it into view."""
    page.goto(f"/runs/{COMPLETED_RUN_WITH_DELIVERABLE}/preview/full")
    page.wait_for_load_state("networkidle")
    page.set_viewport_size({"width": 375, "height": 700})

    fullscreen_button = page.locator('button[title="Open in new tab"]', has_text="Full Screen")
    fullscreen_button.wait_for(state="attached")

    inner_width = page.evaluate("window.innerWidth")
    box = fullscreen_button.bounding_box()
    assert box is not None, "Full Screen button has no bounding box"
    assert box["x"] + box["width"] <= inner_width, (
        f"Full Screen button's right edge ({box['x'] + box['width']}) is outside the "
        f"{inner_width}px viewport — it is unreachable by click and there is no "
        f"scroll affordance to bring it into view."
    )
