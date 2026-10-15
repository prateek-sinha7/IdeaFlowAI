"""ISS-607 / ISS-610 / ISS-611 / ISS-612 — BUG-20260829-140111-runs-id-steps-agent.

From a root run's base (unversioned) Steps route, neither the version picker
nor the chat's deep-link buttons can reach a revision's own content — the
revision's agent step becomes unreachable through any normal-user path.

One family, discovered at runtime (`a_revised_family`), mounted at its root.

These checks deliberately do NOT name a member or a version number. Revising
the root again adds a member and renumbers nothing, but it does change which
member is NEWEST — and the header's version menu is driven by GIT TAGS
(`GET /api/runs/{id}/sandbox/refs`), not by the family, so a member that never
reached `completed` with a sandbox carries no `vN` tag at all (a family's
tags can run v1 / untagged / v3). Naming "v2" asserts the fixture rather than
the behaviour, and the behaviour is all ISS-607/610/612 claim: a deep link from
an un-pinned route must reach SOME other member instead of silently no-opping
on the root.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from framework import settings
from framework.locators import run_detail as RD

from .test_run_families_and_versions import a_revised_family


def _newest_revision_card(page):
    """The LAST "Revision started" card in the transcript.

    Not ``get_by_text(...)`` unscoped: this family now carries several
    revisions, so that locator resolves to N elements and Playwright raises a
    strict-mode violation before any assertion runs. The original test was
    written against a transcript holding exactly one such card.

    The NEWEST is chosen deliberately — the transcript is chronological, so the
    last card is the most recent revision, which is the one whose run id these
    checks can predict without pinning a specific member that a later revision
    would displace.
    """
    cards = page.get_by_text("Revision started", exact=True)
    count = cards.count()
    assert count > 0, (
        "no 'Revision started' card in the transcript — this run has no "
        "revision, so neither ISS-607's nor ISS-612's deep link can be exercised"
    )
    card = cards.nth(count - 1)
    expect(card).to_be_visible()
    return card


def _assert_targeted_a_revision(page, requests: list[str], what: str, root: str) -> None:
    """The deep link must reach a DIFFERENT family member, not stay on the root.

    ISS-607/ISS-612 are both "the link silently no-ops and the root's content
    stays on screen". The signature of that bug is: the URL never gains a
    version segment and no run but the root is ever fetched. Asserting a
    specific revision id instead would pin the fixture — the family's newest
    member changes every time someone revises the run — while testing nothing
    more, since any non-root member proves the link can target one.
    """
    assert "/versions/" in page.url, (
        f"{what} did not navigate to a version — url is still {page.url!r}"
    )
    others = {
        m.group(1)
        for u in requests
        if (m := re.search(r"/api/runs/([0-9a-f-]{36})", u))
        and m.group(1) != root
    }
    assert others, (
        f"{what} never fetched any run but the ROOT ({root}) — the card "
        f"has no way to target a different run in the family. "
        f"requests seen: {requests}"
    )


def _pick_a_tagged_version(page, shot, shot_name: str, where: str) -> None:
    """Open the run-header version menu and pick the first real version.

    Deliberately NOT keyed on a specific version number or run id. The menu is
    driven by GIT TAGS (``GET /api/runs/{id}/sandbox/refs``), not by the run
    family — a run only earns a ``vN`` tag when it reaches ``completed`` with a
    sandbox, so a family can carry permanent gaps (this dataset's own family is
    v1 / untagged / v3). Asking for "v2" by name therefore asserts the fixture,
    not the behaviour. What ISS-607/610 actually claim is that picking ANY
    version from an un-pinned route navigates instead of silently no-opping.

    Also not keyed on the label "Version v2": commit e4eecb705 (2026-09-12,
    "one version selector for the whole run") replaced the family-walking menu
    with this tag-driven one, and its options render the bare tag (``v3``).
    """
    page.locator(f"{RD.HEADER} button[aria-haspopup='listbox']").click()
    page.wait_for_timeout(settings.SETTLE_MS)
    # Option 0 is always "Latest (live)" — the un-pin shortcut, which by design
    # does NOT write a version segment. Every option after it is a real tag.
    options = page.locator("[role='option']")
    tags = [
        options.nth(i).inner_text().strip()
        for i in range(options.count())
        if options.nth(i).inner_text().strip() != "Latest (live)"
    ]
    assert tags, (
        f"the version menu on {where} offers no version at all — only "
        f'"Latest (live)". A tagged family member is required for this check; '
        f"see the docstring on why a gap is possible."
    )
    with shot(shot_name, f'When I pick "{tags[0]}" from the base {where} route'):
        options.filter(has_text=tags[0]).first.click()
        page.wait_for_timeout(settings.SETTLE_MS)


@pytest.mark.issue("ISS-607")
def test_version_picker_navigates_to_revision_from_base_steps_route(page, shot):
    """Picking a version from the base (unversioned) Steps route must
    navigate to the revision's own content, not silently no-op."""
    root, _ = a_revised_family(page)
    page.goto(f"/runs/{root}/steps")
    expect(page.locator(RD.LANE)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS)
    assert "/versions/" not in page.url

    _pick_a_tagged_version(page, shot, "iss607-picker-select-version", "Steps")

    assert "/versions/" in page.url, (
        f"picking a version from the base route did not navigate — "
        f"url is still {page.url!r}"
    )
    assert page.url.endswith("/steps"), (
        f"navigating to the version left the Steps tab — url is {page.url!r}"
    )


@pytest.mark.issue("ISS-607")
def test_chat_answer_in_steps_navigates_to_revision_from_base_route(page, shot):
    """The chat transcript's "Answer in Steps" link on the "Revision started"
    entry must navigate to the revision's own Steps content, not no-op."""
    root, _ = a_revised_family(page)
    page.goto(f"/runs/{root}/steps")
    expect(page.locator(RD.LANE)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS)

    revision_started = _newest_revision_card(page)
    answer_link = revision_started.locator(
        "xpath=following-sibling::*[self::button][1]"
    )

    requests: list[str] = []
    page.on("request", lambda req: requests.append(req.url))

    with shot("iss607-chat-answer-in-steps", 'When I click "Answer in Steps" on Revision started'):
        answer_link.click()
        page.wait_for_timeout(settings.SETTLE_MS)

    _assert_targeted_a_revision(page, requests, "'Answer in Steps'", root)


@pytest.mark.issue("ISS-610")
def test_version_picker_noop_is_not_steps_specific(page, shot):
    """The same "pick latest from the base route" no-op that ISS-607
    documents for Steps must be FIXED on every tab, not just Steps — proven
    here on the Files tab, which shares the one PreviewPanel/RunHeader
    mount app-wide."""
    root, _ = a_revised_family(page)
    page.goto(f"/runs/{root}/files")
    expect(page.locator(RD.LANE)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS)
    assert "/versions/" not in page.url

    _pick_a_tagged_version(page, shot, "iss610-picker-select-version-files-tab", "Files")

    assert "/versions/" in page.url, (
        f"picking a version from the base FILES route did not navigate — "
        f"url is still {page.url!r} (same no-op as ISS-607, reproduced on a "
        f"non-Steps tab)"
    )
    assert page.url.endswith("/files"), (
        f"navigating to the version left the Files tab — url is {page.url!r}"
    )


@pytest.mark.issue("ISS-611")
@pytest.mark.skip(
    reason="needs a family with 3+ versions (specifically v2 pinned in the middle); only 2-member families exist"
)
def test_back_to_latest_from_pinned_middle_version_reaches_true_latest(page, shot):
    """"Back to latest ->" from a version PINNED IN THE MIDDLE of a family
    must land on the true latest member, not silently fall back to the
    family ROOT."""


@pytest.mark.issue("ISS-612")
def test_chat_deliverable_card_deep_link_carries_the_revisions_run_id(page, shot):
    """A "Deliverable" chat card whose milestone belongs to the REVISION
    (not the mounted root run) must open that revision's own content when
    its "Open in Preview" link is clicked, not silently stay on the root's
    v1 content. This is ISS-612's generalization of ISS-607's chat no-op to
    a non-"Revision started" card kind."""
    root, _ = a_revised_family(page)
    page.goto(f"/runs/{root}/steps")
    expect(page.locator(RD.LANE)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS)

    revision_started = _newest_revision_card(page)
    # The revision's own "Deliverable / Delivered - open in Preview ->" card
    # is the chat entry directly after this "Revision started".
    deliverable_open_in_preview = revision_started.locator(
        "xpath=following::button[normalize-space(text())='Open in Preview'][1]"
    )

    requests: list[str] = []
    page.on("request", lambda req: requests.append(req.url))

    with shot("iss612-deliverable-open-in-preview", 'When I click "Open in Preview" on the revision\'s Deliverable card'):
        deliverable_open_in_preview.click()
        page.wait_for_timeout(settings.SETTLE_MS)

    _assert_targeted_a_revision(
        page, requests, "the revision's Deliverable card's 'Open in Preview'", root
    )
