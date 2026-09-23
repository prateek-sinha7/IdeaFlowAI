"""ISS-729 (QA-SG-002) — the "Run workflow" button on the simple launch
panel has no in-flight guard. `handleRun` (IdeaInputPage.tsx:1480) sets no
submitting flag, and the button's `disabled` prop (IdeaInputPage.tsx:1888)
never checks one, so a same-tick double-click re-enters `handleRun` and
fires two independent `POST /api/runs`.

Confirmed live 3/3 (see `.knowledge/cards/20260922-1338-ISS-729.md`): two
synchronous `.click()` calls inside one `page.evaluate()` land two POSTs
with two distinct `run_id`s.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from framework.locators import launch_panels as L

BRIEF_TEXT = "One slide saying hello. Nothing else."


@pytest.mark.issue("ISS-729")
def test_run_workflow_double_click_starts_only_one_run(page, shot):
    """ISS-729 — a double-click on Run workflow before the SPA route push
    lands must start exactly one run, not two."""
    with shot("brief-typed", 'Given a valid brief on "/create/user-stories"'):
        page.goto("/create/user-stories")
        page.fill(L.BRIEF, BRIEF_TEXT)
        expect(page.locator(L.RUN_WORKFLOW)).to_be_enabled()

    run_posts = []
    page.on(
        "request",
        lambda req: run_posts.append(req)
        if req.method == "POST" and "/api/runs" in req.url
        else None,
    )

    with shot("double-click", 'When I fire two synchronous clicks on "Run workflow"'):
        # Mirrors the card's confirmed repro: two synchronous .click() calls
        # inside one page.evaluate(), before React can commit a disabled state.
        page.eval_on_selector(L.RUN_WORKFLOW, "el => { el.click(); el.click(); }")
        expect(page).to_have_url(re.compile(r"/runs/[^/]+"), timeout=60_000)

    assert len(run_posts) == 1, (
        f"ISS-729: a double-click on Run workflow fired {len(run_posts)} "
        f"POST /api/runs requests, expected exactly 1 — the button has no "
        f"in-flight guard: {[r.url for r in run_posts]}"
    )
