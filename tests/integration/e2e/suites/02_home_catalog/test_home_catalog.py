"""Implements ../../../screens/02-home-catalog.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

Signed in as admin by default. Tier-specific scenarios use
`@pytest.mark.role(...)`, which swaps the injected session rather than driving
the login form again.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from framework import api
from framework.locators import home_catalog as L


@pytest.mark.scenario("S-02-01")
def test_the_catalog_renders_on_a_cold_dashboard_load(page, shot):
    """Scenario: The catalog renders on a cold dashboard load"""
    with shot("catalog", 'When I cold-load "/dashboard"'):
        page.goto("/dashboard")
        expect(page.get_by_text(L.HEADING)).to_be_visible()
        expect(page.locator(L.COMING_SOON_HEADING)).to_be_visible()

    # Every launchable card carries its inspect affordance. Asserted across the
    # whole set, not a sample: a card that renders without one is unreachable
    # for anyone wanting its detail before committing to a run.
    for title in L.LAUNCHABLE_TITLES:
        expect(page.locator(L.inspect(title))).to_have_count(1)


@pytest.mark.scenario("S-02-02")
def test_create_renders_the_identical_catalog(page, shot):
    """Scenario: /create renders the identical catalog"""
    page.goto("/dashboard")
    # Wait for a CARD, not just the heading: the heading paints before the
    # catalog data arrives, and collecting then returns an empty set that
    # compares equal to another empty set — a test that passes on nothing.
    expect(page.locator(L.card("Pitch an idea"))).to_be_visible()
    dashboard_titles = page.locator("h2").all_inner_texts()

    with shot("create", 'When I cold-load "/create"'):
        page.goto("/create")
        expect(page.locator(L.card("Pitch an idea"))).to_be_visible()

    # Both routes map to MainView "home" on purpose. Asserting the SET rather
    # than the markup means a refactor cannot split them without failing here.
    assert set(page.locator("h2").all_inner_texts()) == set(dashboard_titles)


@pytest.mark.scenario("S-02-03")
def test_coming_soon_cards_are_present_but_not_launchable(page, shot):
    """Scenario: Coming Soon cards are present but not launchable"""
    with shot("coming-soon", 'Then I see "Reverse engineer a codebase" under Coming Soon'):
        page.goto("/dashboard")
        card = page.locator(L.card("Reverse engineer a codebase"))
        expect(card).to_be_visible()
        expect(card).to_be_disabled()

    # A disabled button cannot be clicked by a user, so `force` is the only way
    # to prove the guard rather than the pointer-events styling.
    card.click(force=True)
    expect(page).to_have_url(re.compile(r"/dashboard"))


@pytest.mark.scenario("S-02-04")
def test_a_launchable_card_opens_that_workflows_launch_surface(page, shot):
    """Scenario: A launchable card opens that workflow's launch surface"""
    with shot("catalog", 'When I cold-load "/dashboard"'):
        page.goto("/dashboard")
        expect(page.locator(L.card("Generate product requirements"))).to_be_enabled()

    with shot("launch-surface", 'Then I land on a launch surface for "user_stories"'):
        page.click(L.card("Generate product requirements"))
        expect(page).not_to_have_url(re.compile(r"/dashboard$"))

    # The surface must name THAT workflow. A launch panel that opens the wrong
    # pipeline is the failure this scenario exists for, and the URL alone does
    # not always say which one loaded.
    assert re.search(r"user[_-]?stories", page.url + page.content(), re.I), (
        f"launch surface at {page.url} does not name user_stories"
    )


@pytest.mark.scenario("S-02-05")
def test_the_inspect_affordance_opens_details_without_launching(page, shot):
    """Scenario: The inspect affordance opens details without launching"""
    page.goto("/dashboard")
    expect(page.get_by_text(L.HEADING)).to_be_visible()

    with shot("inspect-open", 'When I click "Inspect Pitch an idea details"'):
        page.click(L.inspect("Pitch an idea"))
        expect(page.get_by_role("dialog")).to_be_visible()

    # No run started: still on the dashboard, not on a run surface.
    assert not re.search(r"/runs/", page.url), "inspecting a card started a run"


@pytest.mark.scenario("S-02-06")
@pytest.mark.role("basic")
def test_every_catalog_card_renders_regardless_of_tier(page, shot):
    """Scenario: Every catalog card renders regardless of tier"""
    # CORRECTED after the tier sweep (D-09). Cards are NEVER hidden by tier —
    # every card renders for every user and entitlement shows as a badge. The
    # first draft of this spec asserted ABSENCE, which would have passed
    # vacuously and tested nothing.
    with shot("basic-tier-catalog", "Then I see all 13 launchable card titles"):
        page.goto("/dashboard")
        expect(page.get_by_text(L.HEADING)).to_be_visible()
        for title in L.LAUNCHABLE_TITLES:
            expect(page.locator(L.card(title))).to_have_count(1)

    # And at least one is badged rather than hidden.
    assert page.get_by_text(re.compile(r"Requires \w+ plan")).count() > 0, (
        "a basic account saw no entitlement badge — either the tier or the badge broke"
    )


@pytest.mark.scenario("S-02-07")
@pytest.mark.parametrize(
    ("role", "card_title", "lock"),
    [
        ("basic", "Generate product requirements", None),
        # spec 017 entitled ppt and ppt_v2 on EVERY tier — the deck is the
        # entry-level product now. The spec's matrix predates that merge.
        ("basic", "Pitch an idea", None),
        ("basic", "Pitch an idea (v2)", None),
        ("basic", "Build an interactive prototype", "Pro"),
        ("basic", "Compose a custom workflow", "Enterprise"),
        ("pro", "Pitch an idea", None),
        ("pro", "Build an end-to-end application", None),
        ("pro", "Compose a custom workflow", "Enterprise"),
        ("pro", "Branch by Language", "Enterprise"),
        ("enterprise", "Compose a custom workflow", None),
        ("enterprise", "Branch by Language", None),
    ],
)
def test_the_lock_badge_names_the_tier_a_card_needs(page_as, shot, role, card_title, lock):
    """Scenario Outline: The lock badge names the tier a card needs"""
    # Source of truth is TIER_PIPELINES in BOTH frontend/src/lib/entitlements.ts
    # and backend/app/core/entitlements.py. test_entitlement_parity keeps them
    # equal; FIX-315 exists because they had drifted. This is the end-to-end
    # half of that guard.
    page = page_as(role)
    page.goto("/dashboard")
    card = page.locator(L.card(card_title))
    expect(card).to_have_count(1)

    if lock is None:
        expect(card).to_be_enabled()
        expect(card.get_by_text(re.compile(r"Requires \w+ plan"))).to_have_count(0)
    else:
        expect(card).to_be_disabled()
        expect(card.get_by_text(f"Requires {lock} plan")).to_be_visible()


@pytest.mark.scenario("S-02-08")
@pytest.mark.role("basic")
def test_a_locked_card_cannot_be_launched(page, shot):
    """Scenario: A locked card cannot be launched"""
    with shot("locked-card", "When I click a card badged Requires Enterprise plan"):
        page.goto("/dashboard")
        card = page.locator(L.card("Compose a custom workflow"))
        expect(card).to_be_disabled()
        card.click(force=True)

    expect(page).to_have_url(re.compile(r"/dashboard"))
    assert not re.search(r"/runs/", page.url), "a locked card started a run"


@pytest.mark.scenario("S-02-09")
@pytest.mark.role("basic")
def test_the_backend_refuses_a_launch_the_badge_says_is_locked(page, shot):
    """Scenario: The backend refuses a launch the badge says is locked"""
    # The badge is presentation. ISS-055 recorded a period where launch never
    # checked entitlement at all, so the server half needs its own assertion.
    #
    # The request is made INSIDE the browser so the bearer token never reaches
    # this process — see framework/api.py.
    with shot("dashboard", "Given I hold a valid token for a basic account"):
        page.goto("/dashboard")
        expect(page.get_by_text(L.HEADING)).to_be_visible()

    # `message` and `pipeline_type` are LaunchCommand's required fields. Sending
    # anything else 422s on schema and would pass this assertion for entirely
    # the wrong reason.
    res = api.request(
        page, "POST", "/api/runs",
        {"message": "entitlement probe — must be refused", "pipeline_type": "custom"},
    )
    assert res["status"] in (401, 402, 403), (
        "a basic account was NOT refused a custom-workflow launch "
        f"— got {res['status']}: {res['body'][:200]}"
    )


@pytest.mark.scenario("S-02-10")
@pytest.mark.defect
@pytest.mark.role("enterprise")
def test_spec_014_test_fixtures_appear_as_launchable_product_cards(page, shot):
    """Scenario: spec-014 test fixtures appear as launchable product cards"""
    # D-04 / ISS-187. Recorded as CURRENT behaviour, not correct behaviour: seven
    # spec-014 test fixtures sit in the product catalog beside real workflows.
    # If they are hidden, rewrite this to assert their absence and drop the tag.
    fixtures = [
        "Retry Until It Passes",
        "Branch by Language",
        "Spanish Greeter",
        "Dutch Greeter",
        "Hand Off to Another Workflow",
        "Ask a Human, Then Hand Off",
        "Ask a Human, Then Decide",
    ]
    with shot("fixtures-in-catalog", "Then I see the test fixtures as launchable cards"):
        page.goto("/dashboard")
        for title in fixtures:
            expect(page.locator(L.card(title))).to_be_enabled()

    # The internal id leaks into user-facing copy, which is the sharper half of
    # this defect — a customer reads "ex_A3_divert" on a product card.
    expect(page.locator(L.card("Spanish Greeter"))).to_contain_text("ex_A3_divert")


@pytest.mark.scenario("S-02-11")
def test_jump_back_in_lists_recent_runs_and_opens_them(page, shot):
    """Scenario: Jump back in lists recent runs and opens them"""
    with shot("recent-runs", "Then each entry shows a status, an age and a brief"):
        page.goto("/dashboard")
        expect(page.get_by_text(L.JUMP_BACK_IN)).to_be_visible()

    entry = page.locator(L.RECENT_RUN).first
    expect(entry).to_be_visible()
    # Status, age and a brief excerpt — the three things that make the strip
    # worth having. A card showing only a title is a regression, not a style.
    expect(entry).to_contain_text(re.compile(r"DONE|FAILED|CANCELLED|RUNNING|WAITING", re.I))
    expect(entry).to_contain_text(re.compile(r"\d+\s*(m|h|d)\s*ago", re.I))

    with shot("run-detail", "Then I land on that run's detail surface"):
        entry.click()
        expect(page).to_have_url(re.compile(r"/runs/[^/]+"))


@pytest.mark.scenario("S-02-12")
@pytest.mark.skip(reason="fixture: no run parked in waiting_for_user")
def test_a_live_run_is_distinguishable_from_a_finished_one(page, shot):
    """Scenario: A live run is distinguishable from a finished one"""
    # Needs a run held at a human gate. Producing one costs a live Bedrock run
    # that then has to stay unanswered, which no sweep has produced.


@pytest.mark.scenario("S-02-13")
@pytest.mark.defect
@pytest.mark.skip(reason="fixture: needs a saved 1-step override of app_builder on one account only")
def test_a_saved_override_changes_the_catalog_cards_agent_estimate(page, shot):
    """Scenario: A saved override changes the catalog card's agent estimate"""
    # D-10. The same card advertises a different agent count depending on
    # whether the signed-in user has a saved override of that built-in.
    # Recorded, not judged — possibly intended (the card predicts YOUR run),
    # possibly per-user state leaking into a catalog estimate.
