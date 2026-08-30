"""Implements ../../../screens/05-saved-workflows.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

**Counts are read, never assumed.** The seeded database holds 31 workflows
including stress-test rows, and any scenario that saves one moves the number.

The destructive scenario duplicates a row and deletes the duplicate — it never
touches a seeded fixture, and it restores the count it started from.
"""

from __future__ import annotations

import json
import re

import pytest
from playwright.sync_api import expect

from framework import api
from framework import settings
from framework import age
from framework.locators import saved_workflows as L


def saved_row(page, wid: str) -> dict:
    """A saved workflow's own record, straight from the API.

    "Counts are read, never assumed" applies to the ROSTER too: which agents a
    row holds is data that any save can change, so the expected value comes
    from the record rather than from a constant that goes stale the first time
    someone edits the row. `report-generator` was on `My presentation` until
    2026-08-29 and is not any more.
    """
    rows = json.loads(api.full(page, "GET", "/api/user-workflows")["body"])
    if not isinstance(rows, list):
        rows = rows.get("items") or rows.get("workflows") or []
    row = next((r for r in rows if r.get("id") == wid), None)
    assert row, f"the API does not list the workflow {wid}"
    return row


def roster_count(page) -> int:
    """The `N agents` caption on a detail view.

    Case-insensitive: the caption is uppercased by CSS, so its DOM text is
    "3 agents" while the screen reads "3 AGENTS".
    """
    m = re.search(r"(\d+)\s+agents", page.evaluate("() => document.body.innerText"), re.I)
    assert m, "the detail view reports no agent count"
    return int(m.group(1))


def open_list(page) -> None:
    page.goto("/workflows")
    expect(page.get_by_role("heading", name=L.HEADING)).to_be_visible()
    expect(page.locator(L.CARD).first).to_be_visible()


def workflow_id(page, title: str) -> str:
    """The id of a saved row, taken from the route its own Edit item builds.

    The list exposes the id nowhere in the DOM, and the card body does not
    navigate, so the menu is the only way to learn it.
    """
    open_list(page)
    L.card(page, title).locator(L.ACTIONS).click()
    page.get_by_role("menuitem", name="Edit").click()
    page.wait_for_url("**/workflows/*/edit")
    return page.url.split("/workflows/")[1].split("/")[0]


@pytest.mark.scenario("S-05-01")
def test_the_list_renders_with_stats_and_a_create_affordance(page, shot):
    """Scenario: The list renders with stats and a create affordance"""
    with shot("saved-workflows", 'When I cold-load "/workflows"'):
        open_list(page)

    expect(page.get_by_text(L.SUBTITLE)).to_be_visible()
    assert L.stat(page, "workflows") >= 1
    assert L.stat(page, "total agents") >= 1
    expect(page.locator(L.NEW_WORKFLOW)).to_be_visible()
    expect(page.locator(L.SEARCH)).to_be_visible()


@pytest.mark.scenario("S-05-02")
def test_the_stats_agree_with_the_cards(page, shot):
    """Scenario: The stats agree with the cards"""
    with shot("stats", 'When I cold-load "/workflows"'):
        open_list(page)

    texts = page.locator(L.CARD).evaluate_all("els => els.map(e => e.innerText)")
    assert L.stat(page, "workflows") == len(texts)

    per_card = [L.agent_count(t) for t in texts]
    assert all(n is not None for n in per_card), "a card reports no agent count"
    assert L.stat(page, "total agents") == sum(per_card), (
        f"the header claims {L.stat(page, 'total agents')} agents, the cards sum to {sum(per_card)}"
    )


@pytest.mark.scenario("S-05-03")
def test_every_card_exposes_its_own_actions(page, shot):
    """Scenario: Every card exposes its own actions"""
    with shot("card-actions", 'When I cold-load "/workflows"'):
        open_list(page)

    cards = page.locator(L.CARD)
    count = cards.count()
    assert page.locator(L.ACTIONS).count() == count
    assert page.locator(L.RUN_WORKFLOW).count() == count

    for text in cards.evaluate_all("els => els.map(e => e.innerText)"):
        assert L.agent_count(text) is not None, f"no agent count on: {text[:60]!r}"
        assert age.has_age(text), f"no age on: {text[:60]!r}"


@pytest.mark.scenario("S-05-04")
def test_search_narrows_the_list_by_title(page, shot):
    """Scenario: Search narrows the list by title"""
    open_list(page)
    before = page.locator(L.CARD).count()

    with shot("search", 'When I type "presentation" into the search'):
        page.fill(L.SEARCH, "presentation")
        page.wait_for_timeout(settings.SETTLE_MS // 3)

    matched = page.locator(L.CARD).evaluate_all("els => els.map(e => e.innerText)")
    assert 0 < len(matched) < before
    for text in matched:
        assert "presentation" in text.lower()

    with shot("search-cleared", "When I clear the search"):
        page.fill(L.SEARCH, "")
        page.wait_for_timeout(settings.SETTLE_MS // 3)

    assert page.locator(L.CARD).count() == before


@pytest.mark.scenario("S-05-05")
def test_new_workflow_opens_the_empty_composer(page, shot):
    """Scenario: New workflow opens the empty composer"""
    open_list(page)

    with shot("new-workflow", 'When I click "New workflow"'):
        page.click(L.NEW_WORKFLOW)
        page.wait_for_url("**/workflows/new")

    expect(page.get_by_text("0 agents")).to_be_visible()
    expect(page.get_by_text("CUSTOM · COMPOSER")).to_be_visible()


@pytest.mark.scenario("S-05-06")
def test_a_card_opens_its_detail_view(page, shot):
    """Scenario: A card opens its detail view

    CORRECTED. No card affordance opens it — `SavedWorkflowsPage` attaches
    `onClick` to the actions menu and to `Run workflow` only, so the read-only
    detail view is reachable by URL alone. This deep-links instead, and asserts
    everything the scenario says the view holds.
    """
    wid = workflow_id(page, L.OVERRIDE_TITLE)

    with shot("workflow-detail", f'When I cold-load "/workflows/{{id}}"'):
        page.goto(f"/workflows/{wid}")
        expect(page.get_by_role("heading", name=L.OVERRIDE_TITLE)).to_be_visible()

    # Case-insensitive: the badge and the roster caption are uppercased by CSS,
    # so their DOM text is "Presentation" and "3 agents".
    expect(page.get_by_text(re.compile(r"^Presentation$", re.I))).to_be_visible()
    # The roster the scenario asks for, counted rather than assumed: the caption
    # must agree with the agents this row is actually saved with.
    saved = saved_row(page, wid)
    assert roster_count(page) == len(saved["agent_ids"]), (
        f"the roster caption disagrees with the saved roster {saved['agent_ids']}"
    )
    expect(page.locator(L.EDIT)).to_be_visible()
    expect(page.locator(L.RUN)).to_be_visible()

    # Clicking the card really does nothing — asserted so the correction above
    # is a checked claim rather than a comment.
    open_list(page)
    before = page.url
    L.card(page, L.OVERRIDE_TITLE).click()
    page.wait_for_timeout(settings.SETTLE_MS // 4)
    assert page.url == before, "a card now navigates; restore the spec's S-05-06"


@pytest.mark.scenario("S-05-07")
def test_the_detail_view_resolves_agent_ids_to_display_names(page, shot):
    """Scenario: The detail view resolves agent IDs to display names

    INVERTED BY ISS-327, which found the raw id to BE the defect: the Library
    and Composer name the same agents, and this view alone printed
    `agentIds.map((id) => id)`. It resolves them now, falling back to the raw
    id only when the catalog cannot name one — so an unfamiliar agent is still
    listed rather than dropped.

    Every agent is read off the saved record, so this does not care which
    agents the row currently holds.
    """
    wid = workflow_id(page, L.OVERRIDE_TITLE)

    with shot("roster", 'When I cold-load the detail view'):
        page.goto(f"/workflows/{wid}")
        expect(page.get_by_role("heading", name=L.OVERRIDE_TITLE)).to_be_visible()

    saved = saved_row(page, wid)
    body = page.evaluate("() => document.body.innerText")
    assert saved["agent_ids"], "the saved row holds no agents to render"

    resolved = 0
    for agent_id in saved["agent_ids"]:
        name = L.AGENT_DISPLAY_NAMES.get(agent_id)
        if name:
            assert name in body, f"the roster did not resolve {agent_id} to {name!r}"
            assert agent_id not in body, (
                f"the roster printed the raw id {agent_id} beside its name — "
                "ISS-327 replaced the id with the name, it did not add to it"
            )
            resolved += 1
        else:
            # No catalog entry: the id itself is the fallback, and appearing as
            # itself is better than not appearing at all.
            assert agent_id in body, f"an unresolvable agent vanished: {agent_id}"
    assert resolved, (
        f"none of {saved['agent_ids']} is a known agent — "
        "framework.locators.saved_workflows.AGENT_DISPLAY_NAMES needs the entry"
    )


@pytest.mark.scenario("S-05-08")
def test_edit_opens_the_composer_bound_to_this_row(page, shot):
    """Scenario: Edit opens the composer bound to this row"""
    with shot("edit", 'When I click "Edit"'):
        wid = workflow_id(page, L.OVERRIDE_TITLE)

    assert page.url.endswith(f"/workflows/{wid}/edit")
    # A saved row is overwritable, so the primary action saves in place. A
    # built-in offers "Save as my version" instead.
    expect(page.locator(L.SAVE_WORKFLOW)).to_be_visible()
    expect(page.get_by_text("Save as copy")).to_have_count(0)


@pytest.mark.scenario("S-05-09")
def test_run_opens_the_base_workflows_launch_panel(page, shot):
    """Scenario: Run opens the base workflow's launch panel"""
    wid = workflow_id(page, L.OVERRIDE_TITLE)

    with shot("saved-run", 'When I cold-load "/workflows/{id}/run"'):
        page.goto(f"/workflows/{wid}/run")
        expect(page.get_by_text("NEW PRESENTATION")).to_be_visible()

    expect(page.get_by_text("Configure your presentation")).to_be_visible()
    # The ppt wizard's template gallery — a template tile is the only button
    # holding a preview iframe.
    assert page.locator("button:has(iframe)").count() > 0


@pytest.mark.scenario("S-05-10")
@pytest.mark.defect
def test_a_saved_overrides_run_panel_reports_the_base_agent_count(page, shot):
    """Scenario: A saved override's run panel reports the base agent count

    Asserts TODAY'S behaviour — D-05. The roster says 4, the launch panel says
    3, and 3 is the BASE ppt manifest's count.

    **What this does NOT settle** is whether the launch then dispatches 4 steps
    or 3. That needs a real run, so it belongs to the live tier — see
    03_launch_panels. If it dispatches 3, the override is ignored at launch and
    D-05 is severe rather than cosmetic.
    """
    wid = workflow_id(page, L.OVERRIDE_TITLE)

    with shot("roster-count", "When I cold-load the detail view"):
        page.goto(f"/workflows/{wid}")
        expect(page.get_by_text(re.compile(r"\d+\s+agents", re.I)).first).to_be_visible()

    roster = roster_count(page)

    with shot("panel-count", 'When I cold-load "/workflows/{id}/run"'):
        page.goto(f"/workflows/{wid}/run")
        expect(page.get_by_text("NEW PRESENTATION")).to_be_visible()

    advanced = page.locator('button:has-text("Advanced")').first.inner_text().replace("\n", " ")
    m = re.search(r"(\d+)\s+agents", advanced, re.I)
    assert m, f"the launch panel reports no agent count: {advanced!r}"
    panel = int(m.group(1))

    if roster == panel:
        pytest.skip(
            f"D-05 is not observable: {L.OVERRIDE_TITLE!r} holds {roster} agents, "
            f"which is its base manifest's own count, so there is no override for "
            "the panel to ignore. It had one — `report-generator` on top of the "
            "3-agent ppt base — until a run overwrote the row on 2026-08-29. "
            "Restore that 4th agent, or point this at another row whose saved "
            "roster differs from its base, and the defect becomes assertable again."
        )

    assert panel < roster, (
        f"the roster says {roster} and the panel says {panel} — D-05 is the "
        "panel reporting FEWER (the base manifest's count) than the saved "
        "override. If they now agree, D-05 is fixed and this should assert that."
    )


@pytest.mark.scenario("S-05-11")
@pytest.mark.destructive
def test_a_workflow_can_be_deleted_from_its_card_menu(page, shot):
    """Scenario: A workflow can be deleted from its card menu

    Duplicates a row first and deletes the DUPLICATE, so no seeded fixture is
    touched and the count ends where it began.
    """
    open_list(page)
    before = page.locator(L.CARD).count()

    with shot("duplicate", "Given I own a disposable saved workflow"):
        L.card(page, L.OVERRIDE_TITLE).locator(L.ACTIONS).click()
        page.get_by_role("menuitem", name="Duplicate").click()
        expect(page.locator(L.CARD)).to_have_count(before + 1)

    titles = page.locator(L.CARD).evaluate_all(
        "els => els.map(e => e.innerText.split('\\n').filter(Boolean)[2] || '')"
    )
    copy = next(t for t in titles if t not in ("", L.OVERRIDE_TITLE) and "presentation" in t.lower())

    with shot("delete", f'When I delete "{copy}" from its own card menu'):
        # Scoped by the duplicate's title. "Workflow actions" repeats once per
        # card and the menu's last item is Delete — an unscoped click deletes
        # someone else's workflow.
        L.card(page, copy).locator(L.ACTIONS).click()
        page.get_by_role("menuitem", name="Delete").click()
        page.get_by_role("button", name="Delete", exact=True).last.click()
        expect(page.locator(L.CARD)).to_have_count(before)

    assert L.card(page, copy).count() == 0


@pytest.mark.scenario("S-05-12")
@pytest.mark.destructive
def test_running_from_a_card_starts_a_run_of_that_workflow(page, shot):
    """Scenario: Running from a card starts a run of that workflow

    Reaches the launch surface and stops there — nothing is dispatched, so this
    costs no tokens. Actually launching is the live tier's job.
    """
    open_list(page)

    with shot("run-from-card", 'When I click "Run workflow" on a specific card'):
        # Scoped by title for the same reason the actions menu is.
        L.card(page, L.OVERRIDE_TITLE).locator(L.RUN_WORKFLOW).click()
        page.wait_for_url("**/create/**")

    expect(page.get_by_text("NEW PRESENTATION")).to_be_visible()
    # It lands on the BASE wizard's own route — `/create/ppt`, carrying no
    # reference to the saved row at all, where `/workflows/{id}/run` at least
    # keeps the id in the URL. More evidence for D-05: launching a saved
    # override from its card drops the binding before the panel even renders.
    assert page.url.endswith("/create/ppt"), page.url


@pytest.mark.scenario("S-05-13")
def test_an_override_can_be_reverted_to_the_original_built_in(page, shot):
    """Scenario: An override can be reverted to the original built-in

    CORRECTED on the direction. The launch surface shows the BUILT-IN's steps by
    default and offers "Use my version" to switch to the saved override — not
    the other way round. Per user, per built-in (spec 016); only the STEPS are
    overridden.
    """
    with shot("built-in-launch", "When I open that built-in's launch surface"):
        page.goto("/create/user-stories")
        expect(page.get_by_text("Provide the brief")).to_be_visible()

    with shot("override-control", "Then a control is offered to switch versions"):
        page.get_by_role("button", name=re.compile(r"^Advanced\s")).first.click()
        expect(page.get_by_text("Advanced Workflow Configuration")).to_be_visible()

    # The override control arrives after the modal does — it waits on a fetch of
    # the user's saved version, so the default expect timeout is too short.
    expect(page.locator(L.USE_MY_VERSION)).to_be_visible(timeout=15000)
    # The steps on screen before switching are the built-in's own.
    expect(page.get_by_text(re.compile(r"core\s*=\s*locked", re.I))).to_be_visible()
