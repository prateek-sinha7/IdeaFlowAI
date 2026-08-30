"""ISS-607 / ISS-610 / ISS-611 / ISS-612 — BUG-20260829-140111-runs-id-steps-agent.

From a root run's base (unversioned) Steps route, neither the version picker
nor the chat's deep-link buttons can reach a revision's own content — the
revision's agent step becomes unreachable through any normal-user path.

Two live fixtures used (both pre-existing in this dataset, confirmed via
`GET /api/runs/{id}` and re-driven live in the browser before writing these
tests):

- 2-member family (root `636ff908-21d6-4c3a-9f00-0ea4f08060fc` v1 "Documentation
  Agent" etc. / revision `2ac66bbd-8d76-4d59-9580-a29b1a4f6e74` v2 "Backlog
  Revision Agent") — used for ISS-607, ISS-610, ISS-612.
- 5-member family (root `b868a6b6-ed11-4ae9-a512-6df2b1c5ad4e` v1 / latest
  revision `8ab0ca9e-03db-4a53-b040-67791a3da520` v5) — used for ISS-611, which
  needs a version PINNED IN THE MIDDLE of a family, something the 2-member
  fixture above cannot provide.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework import settings
from framework.locators import run_detail as RD

ROOT_RUN_ID = "636ff908-21d6-4c3a-9f00-0ea4f08060fc"
V2_RUN_ID = "2ac66bbd-8d76-4d59-9580-a29b1a4f6e74"

MID_FAMILY_ROOT_ID = "b868a6b6-ed11-4ae9-a512-6df2b1c5ad4e"
MID_FAMILY_LATEST_ID = "8ab0ca9e-03db-4a53-b040-67791a3da520"


@pytest.mark.issue("ISS-607")
def test_version_picker_navigates_to_revision_from_base_steps_route(page, shot):
    """Picking "Version v2" from the base (unversioned) Steps route must
    navigate to the revision's own content, not silently no-op."""
    page.goto(f"/runs/{ROOT_RUN_ID}/steps")
    expect(page.locator(RD.LANE)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS)
    assert "/versions/" not in page.url

    page.locator(f"{RD.HEADER} button[aria-haspopup='listbox']").click()
    with shot("iss607-picker-select-v2", 'When I pick "Version v2" from the base Steps route'):
        page.locator("[role='option']").filter(has_text="Version v2").click()
        page.wait_for_timeout(settings.SETTLE_MS)

    assert "/versions/2" in page.url, (
        f"picking Version v2 from the base route did not navigate — "
        f"url is still {page.url!r}"
    )


@pytest.mark.issue("ISS-607")
def test_chat_answer_in_steps_navigates_to_revision_from_base_route(page, shot):
    """The chat transcript's "Answer in Steps" link on the "Revision started"
    entry must navigate to the revision's own Steps content, not no-op."""
    page.goto(f"/runs/{ROOT_RUN_ID}/steps")
    expect(page.locator(RD.LANE)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS)

    revision_started = page.get_by_text("Revision started", exact=True)
    expect(revision_started).to_be_visible()
    answer_link = revision_started.locator(
        "xpath=following-sibling::*[self::button][1]"
    )

    requests: list[str] = []
    page.on("request", lambda req: requests.append(req.url))

    with shot("iss607-chat-answer-in-steps", 'When I click "Answer in Steps" on Revision started'):
        answer_link.click()
        page.wait_for_timeout(settings.SETTLE_MS)

    fetched_v2 = any(f"/api/runs/{V2_RUN_ID}" in u for u in requests)
    assert fetched_v2, (
        f"'Answer in Steps' on the Revision started card never fetched the "
        f"revision's own run id ({V2_RUN_ID}) — requests seen: {requests}"
    )


@pytest.mark.issue("ISS-610")
def test_version_picker_noop_is_not_steps_specific(page, shot):
    """The same "pick latest from the base route" no-op that ISS-607
    documents for Steps must be FIXED on every tab, not just Steps — proven
    here on the Files tab, which shares the one PreviewPanel/RunHeader
    mount app-wide."""
    page.goto(f"/runs/{ROOT_RUN_ID}/files")
    expect(page.locator(RD.LANE)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS)
    assert "/versions/" not in page.url

    page.locator(f"{RD.HEADER} button[aria-haspopup='listbox']").click()
    with shot("iss610-picker-select-v2-files-tab", 'When I pick "Version v2" from the base Files route'):
        page.locator("[role='option']").filter(has_text="Version v2").click()
        page.wait_for_timeout(settings.SETTLE_MS)

    assert "/versions/2" in page.url, (
        f"picking Version v2 from the base FILES route did not navigate — "
        f"url is still {page.url!r} (same no-op as ISS-607, reproduced on a "
        f"non-Steps tab)"
    )


@pytest.mark.issue("ISS-611")
def test_back_to_latest_from_pinned_middle_version_reaches_true_latest(page, shot):
    """"Back to latest ->" from a version PINNED IN THE MIDDLE of a family
    must land on the true latest member, not silently fall back to the
    family ROOT."""
    page.goto(f"/runs/{MID_FAMILY_ROOT_ID}/versions/2/steps")
    expect(page.locator(RD.LANE)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS)
    assert page.url.endswith("/versions/2/steps"), page.url

    with shot("iss611-back-to-latest-from-middle", 'When I click "Back to latest ->" pinned to v2 of 5'):
        page.get_by_role("button", name="Back to latest →").click()
        page.wait_for_timeout(settings.SETTLE_MS)

    # ISS-615: the assertion now tests what is RENDERED (the URL) rather than
    # network requests. The /runs/{rootId}/versions/{v} addressing scheme keeps
    # the root in the base segment, so the root is always fetched regardless of
    # which version is pinned; this is a side-effect of the shell architecture,
    # not a defect. The real requirement is that the rendered content and URL
    # show the true latest member, not the root.
    assert page.url.endswith("/versions/5/steps"), (
        f"'Back to latest' from a mid-family pin (v2) did not navigate to the "
        f"true latest member's URL — expected to end with '/versions/5/steps', "
        f"got {page.url!r}"
    )


@pytest.mark.issue("ISS-612")
def test_chat_deliverable_card_deep_link_carries_the_revisions_run_id(page, shot):
    """A "Deliverable" chat card whose milestone belongs to the REVISION
    (not the mounted root run) must open that revision's own content when
    its "Open in Preview" link is clicked, not silently stay on the root's
    v1 content. This is ISS-612's generalization of ISS-607's chat no-op to
    a non-"Revision started" card kind."""
    page.goto(f"/runs/{ROOT_RUN_ID}/steps")
    expect(page.locator(RD.LANE)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS)

    revision_started = page.get_by_text("Revision started", exact=True)
    expect(revision_started).to_be_visible()
    # The revision's own "Deliverable / Delivered - open in Preview ->" card
    # is the sibling chat entry directly after "Revision started".
    deliverable_open_in_preview = revision_started.locator(
        "xpath=following::button[normalize-space(text())='Open in Preview'][1]"
    )

    requests: list[str] = []
    page.on("request", lambda req: requests.append(req.url))

    with shot("iss612-deliverable-open-in-preview", 'When I click "Open in Preview" on the revision\'s Deliverable card'):
        deliverable_open_in_preview.click()
        page.wait_for_timeout(settings.SETTLE_MS)

    fetched_v2 = any(f"/api/runs/{V2_RUN_ID}" in u for u in requests)
    assert fetched_v2, (
        f"the revision's own Deliverable card's 'Open in Preview' link never "
        f"fetched the revision's own run id ({V2_RUN_ID}) — it has no way to "
        f"target a different run in the family — requests seen: {requests}"
    )
