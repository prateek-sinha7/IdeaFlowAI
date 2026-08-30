"""BUG-20260828-052800-create-ppt-r2 — ISS-226 / ISS-279 / ISS-280.

"Save as my version" always POSTs a static, hardcoded `name`/`description`/
`manifest` to `/api/user-workflows`, regardless of the brief text the user
actually typed. `handleSaveAsOverride` in `LaunchWizard.tsx:727` (the wizard
shell, shared unconditionally by `/create/ppt`, `/create/prototype` and
`/create/ppt_v2` — ISS-226 / ISS-279) and the separate `handleSaveAsOverride`
in `IdeaInputPage.tsx:1460` (the simple panel shell — ISS-280) both build the
save payload from hardcoded literals and `pipelineAgents`/`selectionsRef`,
never from the live brief state each component already tracks.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from framework.locators import launch_panels as L


def _save_and_capture_body(page) -> str:
    expect(page.locator(L.SAVE_AS_MY_VERSION)).to_be_enabled(timeout=15_000)
    with page.expect_response(re.compile(r"/api/user-workflows$")) as resp_info:
        page.click(L.SAVE_AS_MY_VERSION)
    response = resp_info.value
    assert response.status < 400, (
        f"Save as my version failed outright: {response.status} {response.text()[:300]}"
    )
    return response.request.post_data or ""


@pytest.mark.issue("ISS-226")
def test_save_as_my_version_persists_the_brief_on_ppt(page, shot):
    """ISS-226 — the wizard's "Save as my version" on /create/ppt must
    persist the brief the user actually typed, not a static payload."""
    brief = "ISS-226 distinctive brief marker aa11bb22"
    with shot("brief-filled", 'When I fill the brief on "/create/ppt"'):
        page.goto("/create/ppt")
        page.fill(L.BRIEF, brief)

    with shot("saved", 'And I click "Save as my version"'):
        body = _save_and_capture_body(page)

    assert brief in body, (
        f"POST /api/user-workflows body does not contain the entered brief "
        f"— save discarded it: {body[:400]}"
    )


@pytest.mark.issue("ISS-279")
def test_save_as_my_version_persists_the_brief_on_prototype(page, shot):
    """ISS-279 — the same wizard shell's "Save as my version" on
    /create/prototype must also persist the brief, since it shares
    LaunchWizard.tsx's one handleSaveAsOverride with /create/ppt."""
    brief = "ISS-279 distinctive brief marker cc33dd44 prototype"
    with shot("brief-filled", 'When I fill the brief on "/create/prototype"'):
        page.goto("/create/prototype")
        page.fill(L.BRIEF, brief)

    with shot("saved", 'And I click "Save as my version"'):
        body = _save_and_capture_body(page)

    assert brief in body, (
        f"POST /api/user-workflows body does not contain the entered brief "
        f"— save discarded it: {body[:400]}"
    )


@pytest.mark.issue("ISS-279")
def test_save_as_my_version_persists_the_brief_on_ppt_v2(page, shot):
    """ISS-279 — and again on /create/ppt_v2, the third URL that renders
    the same LaunchWizard component and the same broken
    handleSaveAsOverride."""
    brief = "ISS-279 distinctive brief marker ee55ff66 ppt_v2"
    with shot("brief-filled", 'When I fill the brief on "/create/ppt_v2"'):
        page.goto("/create/ppt_v2")
        page.fill(L.BRIEF, brief)

    with shot("saved", 'And I click "Save as my version"'):
        body = _save_and_capture_body(page)

    assert brief in body, (
        f"POST /api/user-workflows body does not contain the entered brief "
        f"— save discarded it: {body[:400]}"
    )


@pytest.mark.issue("ISS-280")
def test_save_as_my_version_persists_the_brief_via_idea_input(page, shot):
    """ISS-280 — IdeaInputPage.tsx's own, separately-implemented
    handleSaveAsOverride (used by every non-custom simple-panel workflow,
    e.g. /create/user-stories) must also persist the entered brief, not a
    hardcoded description with no trace of it. /create/user-stories does not
    declare `route:` on any step, so this sidesteps ISS-225's unrelated 422."""
    brief = "ISS-280 distinctive brief marker gg77hh88 idea-input"
    with shot("brief-filled", 'When I fill the brief on "/create/user-stories"'):
        page.goto("/create/user-stories")
        page.fill(L.BRIEF, brief)

    with shot("saved", 'And I click "Save as my version"'):
        body = _save_and_capture_body(page)

    assert brief in body, (
        f"POST /api/user-workflows body does not contain the entered brief "
        f"— save discarded it: {body[:400]}"
    )
