"""ISS-258 — the Advanced modal's "Cancel" button does not discard an edit
made to a conditional-gate outcome's route.

On `/create/ex_A2_branch` ("Branch by Language"), the "Pick Language" step's
Config tab exposes a route editor for its three outcomes (english/spanish/
dutch). Changing the `english` outcome's Type from "Step" to "Workflow" and
picking a target workflow ("Spanish Greeter") adds a live "Diverts run" node
to the canvas — a live, un-saved edit (no network request fires for it).
Clicking the modal's own "Cancel" button is the documented way to discard
such an edit without saving. Instead, the edit (and its canvas node) survives
Cancel + reopen, because `AgentsPopup`'s route/outcome editor writes straight
into the parent's `pipelineAgents` state with no snapshot taken on open and
no restore in the Cancel handler.

See BUG-20260828-001100-create-ex-a2-branch in bug-hunter/ledger.md.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework.locators import launch_panels as L

DIVERT_NODE = '[data-testid="canvas-external-workflow-ex_A3_b_spanish"]'


@pytest.mark.issue("ISS-258")
def test_advanced_modal_cancel_discards_a_conditional_gate_route_edit(page, shot):
    """Editing a conditional-gate outcome's route and clicking Cancel must
    leave the canvas exactly as it was before the modal opened — no divert
    node, and the outcome's Type/Target reset to their original values."""
    page.goto("/create/ex_A2_branch")
    expect(page.get_by_text(L.SIMPLE_HEADING)).to_be_visible()

    with shot("advanced-open", 'When I open "Advanced 5 agents"'):
        page.click(L.ADVANCED)
        expect(page.locator(L.CANVAS_VIEW)).to_be_visible()
        expect(page.locator(DIVERT_NODE)).to_have_count(0)

    with shot("edit-route", "And I change the english outcome's route to a workflow"):
        # `canvas-node-{agent.id}` where agent.id is the step's INSTANCE id
        # (CanvasNode.tsx) — "language", not "custom-agent:language". The
        # agent-qualified form stopped existing when the canvas began keying
        # nodes on the instance, and the selector then timed out for 30s
        # pointing at the node rather than at its own name.
        page.click('[data-testid="canvas-node-language"]')
        # The rail's tabs are ROLE-based — there is no `data-testid="tab-config"`
        # anywhere in the composer (the run-detail tabs that do carry testids are
        # a different surface). Clicking a selector that matches nothing is not an
        # error in Playwright, so the Config panel simply never opened and the
        # failure surfaced one step later, on `get_by_label("Type")`.
        # test_launch_panels.py already selects these tabs by role.
        page.get_by_role("tab", name="Config").click()
        # exact=True. `get_by_label` matches a SUBSTRING by default, and the
        # Config tab now also carries a "Node type" select (AI agent / Code)
        # that did not exist when this was written — so `get_by_label("Type")`
        # matched it too, `.first` resolved to IT rather than the outcome's
        # "Type", and `select_option("Workflow")` sat in a 30s timeout against a
        # select whose only options are "AI agent…" and "Code…".
        page.get_by_label("Type", exact=True).first.select_option("Workflow")
        page.click('[data-testid="workflow-target-button"]')
        page.click('[data-testid="workflow-picker-row-ex_A3_b_spanish"]')
        page.click('[data-testid="workflow-picker-confirm"]')
        expect(page.locator(DIVERT_NODE)).to_be_visible()

    with shot("cancel-and-reopen", 'And I click "Cancel" then reopen "Advanced"'):
        page.click(L.CANVAS_CANCEL)
        page.click(L.ADVANCED)
        expect(page.locator(L.CANVAS_VIEW)).to_be_visible()

    assert page.locator(DIVERT_NODE).count() == 0, (
        "ISS-258: the divert node from the cancelled route edit is still on "
        "the canvas after Cancel + reopen — the edit was not discarded"
    )

    page.click('[data-testid="canvas-node-language"]')
    page.get_by_role("tab", name="Config").click()
    expect(page.get_by_label("Type", exact=True).first).to_have_value("step", timeout=5_000)
