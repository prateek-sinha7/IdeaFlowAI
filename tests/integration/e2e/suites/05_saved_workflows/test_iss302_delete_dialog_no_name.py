"""BUG-20260828-052400-workflows — ISS-302.

The delete-workflow confirmation dialog on /workflows never identifies which
workflow it will delete: `deleteConfirmId` (`SavedWorkflowsPage.tsx:166`)
stores only the row's id, and the dialog (lines 408-444) renders fully
static JSX with no lookup back into the loaded rows for a name. See
`bug-hunter/ledger.md`'s `BUG-20260828-052400-workflows` entry.

Duplicates the seeded `L.OVERRIDE_TITLE` fixture and opens the delete dialog
on the DUPLICATE (never confirming), so no seeded fixture is touched and no
row is actually deleted.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework.locators import saved_workflows as L


@pytest.mark.issue("ISS-302")
@pytest.mark.destructive
def test_delete_confirmation_names_the_workflow_it_will_delete(page, shot):
    """ISS-302 — the delete confirmation dialog must state which workflow
    it is about to delete, not render generic text identical for every
    card."""
    page.goto("/workflows")
    expect(page.locator(L.CARD).first).to_be_visible()
    before = page.locator(L.CARD).count()

    with shot("duplicate", "Given I own a disposable saved workflow"):
        L.card(page, L.OVERRIDE_TITLE).locator(L.ACTIONS).click()
        page.get_by_role("menuitem", name="Duplicate").click()
        expect(page.locator(L.CARD)).to_have_count(before + 1)

    titles = page.locator(L.CARD).evaluate_all(
        "els => els.map(e => e.innerText.split('\\n').filter(Boolean)[2] || '')"
    )
    copy = next(t for t in titles if t not in ("", L.OVERRIDE_TITLE) and "presentation" in t.lower())

    try:
        with shot("delete-dialog", f'When I open the delete dialog for "{copy}"'):
            L.card(page, copy).locator(L.ACTIONS).click()
            page.get_by_role("menuitem", name="Delete").click()
            dialog = page.get_by_role("dialog")
            expect(dialog).to_be_visible()
            dialog_text = dialog.inner_text()

        assert copy in dialog_text, (
            f"the delete confirmation dialog never names the workflow it "
            f"will delete — expected {copy!r} somewhere in the dialog "
            f"text, got: {dialog_text!r}"
        )
    finally:
        # Clean up the duplicate regardless of outcome, via the actual
        # Delete confirm button, so the fixture count is restored.
        page.get_by_role("button", name="Delete", exact=True).last.click()
        expect(page.locator(L.CARD)).to_have_count(before)
