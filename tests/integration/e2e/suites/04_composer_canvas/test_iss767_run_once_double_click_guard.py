"""ISS-767 — sibling of ISS-729 (QA-SG-002). ComposerPage's "Run once"
button has the identical missing-guard shape: `handleRunOnce`
(ComposerPage.tsx:984) sets no submitting flag, and the button's `disabled`
prop (ComposerPage.tsx:1315, `disabled={!onRun}`) never checks one, so a
same-tick double-click re-enters `handleRunOnce` and fires two independent
`POST /api/runs`.

See `.knowledge/cards/20260922-1445-ISS-767.md`. `/workflows/ppt/canvas`
opens the composer pre-loaded with 3 agents (no add-agent step needed).
`wait_for_nodes` + the framework settle delay is required: the canvas nodes
paint before the `pipelineAgents` state the button's gate reads is actually
populated, so an early click sees "Add at least one agent first" and does
nothing at all — that is a load-order race, not this defect.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework import settings
from framework.locators import composer as L

BRIEF_TEXT = "One slide saying hello. Nothing else."


@pytest.mark.issue("ISS-767")
def test_run_once_double_click_starts_only_one_run(page, shot):
    """ISS-767 — a double-click on Run once must start exactly one run,
    not two."""
    with shot("brief-typed", 'Given a valid brief on "/workflows/ppt/canvas"'):
        page.goto("/workflows/ppt/canvas")
        expect(page.locator(L.HEADER_SUMMARY)).to_be_visible()
        expect(page.locator(L.BRIEF_NODE)).to_be_visible()
        L.wait_for_nodes(page, len(L.PPT_AGENT_IDS))
        page.wait_for_timeout(settings.SETTLE_MS)
        page.fill(L.BRIEF, BRIEF_TEXT)
        expect(page.locator(L.RUN_ONCE)).to_be_visible()
        expect(page.locator(L.RUN_ONCE)).to_have_js_property("title", "")

    run_posts = []
    page.on(
        "request",
        lambda req: run_posts.append(req)
        if req.method == "POST" and "/api/runs" in req.url
        else None,
    )

    with shot("double-click", 'When I fire two synchronous clicks on "Run once"'):
        # Same recipe ISS-729's twin used: two synchronous .click() calls
        # inside one page.evaluate(), before React can commit any guard state.
        page.eval_on_selector(L.RUN_ONCE, "el => { el.click(); el.click(); }")
        page.wait_for_timeout(3_000)

    assert len(run_posts) == 1, (
        f"ISS-767: a double-click on Run once fired {len(run_posts)} "
        f"POST /api/runs requests, expected exactly 1 — handleRunOnce has "
        f"no in-flight guard: {[r.url for r in run_posts]}"
    )
