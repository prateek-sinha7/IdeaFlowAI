"""ISS-374 — corrects ISS-253: the dead-end 0-agent composer for an
unrecognized `/create/{slug}` is `IdeaInputPage.tsx`, not `ComposerPage.tsx`.

`getWorkflowDetail` 404s for a slug that maps to no real workflow. The
`.catch()` at `IdeaInputPage.tsx:1172-1181` swallows it with no visible error
state, and the roster effect at `IdeaInputPage.tsx:1228-1264` then computes
`pipelineAgents = manifestAgents ?? fromLibrary` = `[]` (both empty for an
unknown slug), so `Save workflow` / `Save as my version` / the run button
("Add agents first") stay permanently disabled — even after a full, valid
brief is typed — with zero error text anywhere on the page.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework.locators import launch_panels as L

BRIEF_TEXT = "Build a test app with enough characters to satisfy validation"


@pytest.mark.issue("ISS-374")
def test_unrecognized_slug_surfaces_error_instead_of_silent_dead_end(page, shot):
    """An unrecognized /create/{slug} must show a visible not-found/error
    state, not swallow the 404 and dead-end the composer silently."""
    with shot("load", 'When I navigate to "/create/nonsense" (unrecognized slug)'):
        page.goto("/create/nonsense")
        expect(page.get_by_text(L.SIMPLE_HEADING)).to_be_visible()

    with shot("brief-filled", 'And I type a full, valid brief'):
        page.fill(L.BRIEF, BRIEF_TEXT)

    body_text = page.inner_text("body")
    assert any(
        kw in body_text.lower()
        for kw in ("not found", "doesn't exist", "does not exist", "failed to load", "error")
    ), (
        "ISS-374: the 404 for an unrecognized slug is completely invisible in "
        f"the UI — document.body.innerText contained no error/not-found text: {body_text!r}"
    )


@pytest.mark.issue("ISS-374")
@pytest.mark.xfail(reason="ISS-374 unfixed", strict=True)
def test_unrecognized_slug_does_not_permanently_disable_save_after_brief(page, shot):
    """Once a valid brief is provided, Save workflow must not remain stuck
    disabled forever just because the initial slug lookup 404d."""
    with shot("load", 'When I navigate to "/create/nonsense" (unrecognized slug)'):
        page.goto("/create/nonsense")
        expect(page.get_by_text(L.SIMPLE_HEADING)).to_be_visible()

    with shot("brief-filled", 'And I type a full, valid brief'):
        page.fill(L.BRIEF, BRIEF_TEXT)

    expect(page.locator(L.SAVE_WORKFLOW)).to_be_enabled(timeout=15_000)
