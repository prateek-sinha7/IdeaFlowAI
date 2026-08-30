"""ISS-340 / ISS-580 — Simple and Canvas must agree on a workflow's deliverable
type.

`ComposerPage.tsx:478` hardcodes `deliverableLabel = PIPELINE_LABEL.custom`
for the Simple tab's read-only "Deliverable type" field
(`IdentityCard.tsx`, `data-testid="composer-deliverable-type"`), never
derived from `runConfig`. `CanvasView.tsx:1574`'s "Deliverable strategy"
combobox, rendering the SAME in-memory workflow, derives its value from the
real `runConfig?.deliverable?.strategy`. The two views therefore never agree.

ISS-340 covers the ppt built-in (entered via `/workflows/ppt/canvas`).
ISS-580 covers the sibling entry path: a saved custom workflow opened from
"My Workflows" (`/workflows/{id}/edit`) whose own declared strategy is not
the generic default.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework.locators import composer as L
from framework.locators import saved_workflows as W


def _canvas_selected_deliverable_text(page) -> str:
    """The visible text of the currently-selected <option> in the Canvas
    tab's Deliverable strategy combobox."""
    expect(page.locator(L.DELIVERABLE_STRATEGY)).to_be_visible()
    return page.locator(L.DELIVERABLE_STRATEGY).locator("option:checked").inner_text()


@pytest.mark.issue("ISS-340")
def test_simple_and_canvas_agree_on_ppt_deliverable_type(page):
    """Simple's "Deliverable type" field and Canvas's "Deliverable strategy"
    combobox, read on the same unmodified ppt built-in load, must describe
    the same deliverable — not "Custom" vs whatever Canvas derives."""
    page.goto("/workflows/ppt/canvas")
    expect(page.locator(L.HEADER_SUMMARY)).to_be_visible()

    canvas_text = _canvas_selected_deliverable_text(page)

    page.click(L.SIMPLE)
    simple_field = page.locator('[data-testid="composer-deliverable-type"]')
    expect(simple_field).to_be_visible()
    simple_text = simple_field.inner_text().strip()

    # Today Simple is an unconditional "Custom" regardless of what Canvas
    # shows for the real `ppt` strategy — this fails on that mismatch.
    assert simple_text == canvas_text, (
        f"Simple shows {simple_text!r} but Canvas shows {canvas_text!r} "
        "for the identical unmodified workflow"
    )


@pytest.mark.issue("ISS-580")
def test_simple_and_canvas_agree_on_saved_custom_workflow_deliverable_type(page):
    """The same Simple-vs-Canvas disagreement reproduces for a saved custom
    workflow (not a built-in): start from a blank composer, pick a
    non-default strategy on the Canvas tab, save it, reopen it, and confirm
    Simple's label still tracks the real saved strategy instead of the
    hardcoded "Custom"."""
    title = "ISS-580 deliverable check"
    page.goto("/workflows/new")
    expect(page.locator(L.HEADER_SUMMARY)).to_be_visible()

    page.fill(L.WORKFLOW_NAME, title)
    # A save with zero steps 422s ("List should have at least 1 item") —
    # add one agent so the only thing under test is the deliverable label.
    page.locator(L.ADD_AGENT).first.click()
    expect(page.locator(L.ADD_TO_PLAN).first).to_be_visible(timeout=15000)
    page.locator(L.ADD_TO_PLAN).first.click()
    page.keyboard.press("Escape")
    L.wait_for_nodes(page, 1)

    page.locator(L.DELIVERABLE_STRATEGY).select_option(
        L.STRATEGY_VALUES["Single file"]
    )
    page.wait_for_timeout(500)

    page.locator(L.SAVE_WORKFLOW).click()
    expect(page.get_by_text("Saved", exact=False)).to_be_visible(timeout=10_000)

    try:
        # handleSave does not navigate — it stays on /workflows/new with the
        # freshly-assigned id in state. Reopen the saved row from "My
        # Workflows" the same way a real user would, mirroring
        # `open_override_editor` in test_composer_canvas.py.
        page.goto("/workflows")
        expect(page.locator(W.CARD).first).to_be_visible()
        W.card(page, title).locator(W.ACTIONS).click()
        page.get_by_role("menuitem", name="Edit").click()
        page.wait_for_url("**/workflows/*/edit")
        expect(page.locator(L.HEADER_SUMMARY)).to_be_visible()

        canvas_text = _canvas_selected_deliverable_text(page)

        page.click(L.SIMPLE)
        simple_field = page.locator('[data-testid="composer-deliverable-type"]')
        expect(simple_field).to_be_visible()
        simple_text = simple_field.inner_text().strip()

        assert simple_text == canvas_text, (
            f"Simple shows {simple_text!r} but Canvas shows {canvas_text!r} "
            "for the same saved custom workflow"
        )
    finally:
        # Delete the workflow this test created so repeated runs don't
        # accumulate rows in "My Workflows".
        page.goto("/workflows")
        if W.card(page, title).count():
            W.card(page, title).locator(W.ACTIONS).click()
            page.get_by_role("menuitem", name="Delete").click()
            page.get_by_role("button", name="Delete", exact=True).last.click()
            page.wait_for_timeout(1000)
