"""Implements ../../../screens/08-library.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

**Three of the spec's claims are stale, and are corrected here rather than
asserted:**

1. `div.cursor-pointer.p-4` matches no agent card at all — see
   `framework/locators/library.py`.
2. Agent cards DO navigate from a body click. The `onClick` is on the card, and
   `Configure →` is a `<span>`, not a control (S-08-11).
3. The drawer DOES carry `role="dialog"` (S-08-17). The scenario's substance —
   the list stays rendered behind it and the URL is pushed — still holds.

The category pills cannot account for every agent, so S-08-05's "the counts sum
to All" is false here. That is D-26, and S-08-05 asserts the invariant that does
hold instead: each pill's count equals what its filter renders.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework import settings
from framework.locators import library as L


def open_library(page, query: str = "") -> None:
    page.goto(f"/library{query}")
    expect(page.get_by_role("heading", name=L.HEADING)).to_be_visible()
    # The grid arrives after the page does; the first card is the signal that
    # counting is safe.
    expect(page.locator(L.CARD).first).to_be_visible()


def card_texts(page) -> list[str]:
    """Every card's full text.

    `textContent`, not `innerText`: descriptions are `line-clamp`-ed, so the
    visible text is a truncation of what search actually matched against.
    """
    return page.locator(L.CARD).evaluate_all("cards => cards.map(c => c.textContent || '')")


# ── tabs ─────────────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-08-01")
def test_the_library_opens_on_agents_by_default(page, shot):
    """Scenario: The library opens on Agents by default"""
    with shot("library", 'When I cold-load "/library"'):
        open_library(page)

    agents = L.badge_count(page, "tab-agents")
    skills = L.badge_count(page, "tab-skills")
    hooks = L.badge_count(page, "tab-hooks")
    expect(
        page.get_by_text(
            f"{agents} agents · {skills} skills · {hooks} hooks · "
            "tap any item to see its capabilities"
        )
    ).to_be_visible()

    expect(page.locator(L.tab("tab-agents"))).to_have_attribute("aria-selected", "true")
    # routes.library() omits the default tab, so the clean URL is the assertion.
    assert "tab=" not in page.url, f"the default tab leaked into the URL: {page.url}"


@pytest.mark.scenario("S-08-02")
@pytest.mark.parametrize(("tab_param", "testid"), [("skills", "tab-skills"), ("hooks", "tab-hooks")])
def test_each_tab_is_addressable_by_query_param(page, shot, tab_param, testid):
    """Scenario: Each tab is addressable by query param"""
    with shot(f"tab-{tab_param}", f'When I cold-load "/library?tab={tab_param}"'):
        open_library(page, f"?tab={tab_param}")

    expect(page.locator(L.tab(testid))).to_have_attribute("aria-selected", "true")
    assert page.locator(L.CARD).count() == L.badge_count(page, testid)


@pytest.mark.scenario("S-08-03")
def test_tab_badge_counts_agree_with_the_rendered_cards(page, shot):
    """Scenario: Tab badge counts agree with the rendered cards"""
    with shot("badges-agents", 'When I cold-load "/library"'):
        open_library(page)
    assert page.locator(L.CARD).count() == L.badge_count(page, "tab-agents")

    for testid, label, param in L.TABS[1:]:
        with shot(f"badges-{param}", f"When I switch to {label}"):
            page.click(L.tab(testid))
            page.wait_for_url(f"**tab={param}")
            expect(page.locator(L.CARD).first).to_be_visible()

        rendered, badge = page.locator(L.CARD).count(), L.badge_count(page, testid)
        assert rendered == badge, f"{label}: {rendered} cards, badge says {badge}"


@pytest.mark.scenario("S-08-04")
def test_switching_a_tab_updates_the_url(page, shot):
    """Scenario: Switching a tab updates the URL

    CORRECTED on the Back clause. The tab strip calls `router.replace`, so
    switching a tab writes NO history entry and Back cannot return to the
    previous tab — it leaves the library entirely. Recorded as D-27; asserted
    here as the behaviour that exists.
    """
    page.goto("/dashboard")
    open_library(page)

    with shot("tab-pushed", "When I click the second tab"):
        # By testid, not text: the label carries its count ("Skills  186").
        page.click(L.tab("tab-skills"))
        page.wait_for_url("**/library?tab=skills")

    with shot("tab-back", "When I press browser Back"):
        page.go_back()
        page.wait_for_load_state("load")

    assert "/library" not in page.url, (
        "Back returned inside the library — the tab strip now pushes history, "
        "which is the spec's original claim. Re-check D-27 and restore S-08-04."
    )


# ── categories ───────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-08-05")
def test_category_counts_sum_to_the_all_count(page, shot):
    """Scenario: Category counts sum to the All count

    CORRECTED. They do not sum, and cannot: the pills are built from
    `workflows.filter(user_launchable && !is_beta)`, while the grid renders
    every agent. Roughly half the agents therefore belong to a workflow that has
    no pill and are unreachable by any filter — D-26.

    What IS an invariant, and what this asserts: the All pill equals the grid,
    and no named pill claims more than All.
    """
    with shot("categories", 'When I cold-load "/library"'):
        open_library(page)

    total = page.locator(L.CARD).count()
    all_count = L.pill_count(page, "All")
    assert all_count == total, f'the "All" pill says {all_count}, the grid shows {total}'

    named = [
        L.pill_count(page, label)
        for label in ("App Builder", "PPT v2", "Prototype", "User Stories", "Custom")
    ]
    assert sum(named) <= all_count, (
        f"the named categories claim {sum(named)} of {all_count} agents — a pill "
        "cannot hold more agents than the library has"
    )


@pytest.mark.scenario("S-08-06")
def test_filtering_by_category_narrows_the_grid(page, shot):
    """Scenario: Filtering by category narrows the grid"""
    open_library(page)
    expected = L.pill_count(page, "App Builder")

    with shot("category-app-builder", 'When I click the category "App Builder"'):
        L.pill(page, "App Builder").click()
        page.wait_for_url("**category=app_builder")
        page.wait_for_timeout(settings.SETTLE_MS // 4)

    rendered = page.locator(L.CARD).count()
    assert rendered == expected, f"the pill promised {expected} cards, the grid drew {rendered}"
    for text in card_texts(page):
        assert "APP BUILDER" in text.upper(), f"a foreign card survived the filter: {text[:80]!r}"


@pytest.mark.scenario("S-08-07")
def test_the_category_is_addressable_by_url(page, shot):
    """Scenario: The category is addressable by URL"""
    with shot("category-cold", 'When I cold-load "/library?category=ppt"'):
        open_library(page, "?category=ppt")

    assert "category=ppt" in page.url
    expected = L.pill_count(page, "PPT")
    assert page.locator(L.CARD).count() == expected
    for text in card_texts(page):
        assert "PPT" in text.upper()


@pytest.mark.scenario("S-08-08")
@pytest.mark.defect
def test_seven_agent_categories_are_empty_test_fixtures(page, shot):
    """Scenario: Seven agent categories are empty test fixtures

    Asserts TODAY'S behaviour, not the desired one — D-04 / ISS-187. Half the
    agent filters on this page are spec-014 conditional-gate fixtures with
    nothing behind them.
    """
    with shot("empty-categories", 'When I cold-load "/library"'):
        open_library(page)

    for label in L.EMPTY_AGENT_CATEGORIES:
        expect(L.pill(page, label).first).to_be_visible()
        assert L.pill_count(page, label) == 0, f"{label} is no longer empty — update D-04"

    with shot("empty-category-selected", 'When I click "Retry Loop"'):
        L.pill(page, "Retry Loop").click()
        expect(page.locator(L.CARD)).to_have_count(0)


# ── search ───────────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-08-09")
def test_search_filters_the_current_tab(page, shot):
    """Scenario: Search filters the current tab"""
    open_library(page)
    before = page.locator(L.CARD).count()

    with shot("search", 'When I type "architecture" into the library search'):
        page.fill(L.SEARCH, "architecture")
        page.wait_for_timeout(settings.SETTLE_MS // 4)

    matched = card_texts(page)
    assert 0 < len(matched) < before
    for text in matched:
        assert "architecture" in text.lower(), f"unmatched card survived: {text[:80]!r}"

    with shot("search-cleared", "When I clear the search"):
        page.fill(L.SEARCH, "")
        page.wait_for_timeout(settings.SETTLE_MS // 4)

    assert page.locator(L.CARD).count() == before


@pytest.mark.scenario("S-08-10")
def test_search_is_scoped_to_the_active_tab(page, shot):
    """Scenario: Search is scoped to the active tab"""
    open_library(page, "?tab=skills")

    with shot("search-scoped", "When I type a term that matches an agent but no skill"):
        # An agent role, not a skill name — the three tabs hold separate search
        # state behind the one input.
        page.fill(L.SEARCH, "material-analyzer")
        page.wait_for_timeout(settings.SETTLE_MS // 4)

    expect(page.locator(L.CARD)).to_have_count(0)
    expect(page.locator(L.tab("tab-skills"))).to_have_attribute("aria-selected", "true")


# ── detail views ─────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-08-11")
def test_an_agent_opens_from_its_configure_affordance_not_its_card_body(page, shot):
    """Scenario: An agent opens from its Configure affordance, not its card body

    CORRECTED. The card body DOES navigate: the `onClick` is on the card itself
    and `Configure →` is a `<span>`, not a control. Agent cards behave exactly
    like skill and hook cards, so a shared page-object method IS safe — the
    opposite of what the spec warns.
    """
    open_library(page)
    first = page.locator(L.CARD).first
    name = first.locator("p").first.inner_text()

    with shot("agent-body-click", "When I click the card body of the first agent"):
        first.click()
        page.wait_for_url("**/library/agents/**")

    assert "/library/agents/" in page.url
    expect(page.locator(L.AGENT_DRAWER)).to_be_visible()
    expect(page.get_by_role("heading", name=name)).to_be_visible()


@pytest.mark.scenario("S-08-12")
def test_an_agents_drawer_exposes_its_configuration_tabs(page, shot):
    """Scenario: An agent's drawer exposes its configuration tabs"""
    with shot("agent-drawer", f'When I cold-load "/library/agents/{L.AGENT_SLUG}"'):
        page.goto(f"/library/agents/{L.AGENT_SLUG}")
        expect(page.locator(L.AGENT_DRAWER)).to_be_visible()

    # The slug is the agent ID and need not resemble the name — material-analyzer
    # IS Architecture Agent.
    expect(page.get_by_role("heading", name=L.AGENT_NAME)).to_be_visible()
    for label in L.DRAWER_TABS:
        expect(page.locator(L.AGENT_DRAWER).get_by_role("tab", name=label, exact=True)).to_be_visible()
    expect(page.locator(L.SYSTEM_PROMPT)).to_be_visible()


@pytest.mark.scenario("S-08-13")
@pytest.mark.parametrize("drawer_tab", L.DRAWER_TABS)
def test_each_agent_drawer_tab_shows_its_own_content(page, shot, drawer_tab):
    """Scenario: Each agent drawer tab shows its own content"""
    page.goto(f"/library/agents/{L.AGENT_SLUG}")
    drawer = page.locator(L.AGENT_DRAWER)
    expect(drawer).to_be_visible()

    with shot(f"drawer-{drawer_tab.lower()}", f'When I click the drawer tab "{drawer_tab}"'):
        drawer.get_by_role("tab", name=drawer_tab, exact=True).click()
        page.wait_for_timeout(settings.SETTLE_MS // 5)

    # The panel is whatever sits below the tab strip; assert it carries content
    # rather than pinning one tab's copy, which differs per agent.
    body = drawer.inner_text()
    assert len(body.strip()) > len(" ".join(L.DRAWER_TABS)) + 20, (
        f'the "{drawer_tab}" panel rendered nothing'
    )


@pytest.mark.scenario("S-08-14")
def test_a_skill_opens_from_a_card_click_and_renders_its_document(page, shot):
    """Scenario: A skill opens from a card click and renders its document"""
    open_library(page, "?tab=skills")
    first = page.locator(L.CARD).first
    name = first.locator("p").first.inner_text()

    with shot("skill-drawer", "When I click the first skill card"):
        first.click()
        page.wait_for_url("**/library/skills/**")

    # The document repeats the name as an uppercase H3, so an accessible-name
    # match is ambiguous — pin the drawer's own H2.
    expect(page.locator("h2").filter(has_text=name)).to_be_visible()
    # WHEN TO USE is the one section every skill document has; the rest vary.
    expect(page.get_by_text("WHEN TO USE").first).to_be_visible()
    expect(page.get_by_role("button", name="Copy content")).to_be_visible()


@pytest.mark.scenario("S-08-15")
def test_a_hook_opens_from_a_card_click(page, shot):
    """Scenario: A hook opens from a card click"""
    open_library(page, "?tab=hooks")
    first = page.locator(L.CARD).first
    name = first.locator("p").first.inner_text()

    with shot("hook-drawer", "When I click the first hook card"):
        first.click()
        page.wait_for_url("**/library/hooks/**")

    expect(page.locator("h2").filter(has_text=name)).to_be_visible()
    expect(page.get_by_role("button", name="Copy", exact=True)).to_be_visible()


@pytest.mark.scenario("S-08-16")
def test_hook_categories_are_lifecycle_events(page, shot):
    """Scenario: Hook categories are lifecycle events"""
    with shot("hook-events", 'When I cold-load "/library?tab=hooks"'):
        open_library(page, "?tab=hooks")

    for event in L.HOOK_EVENTS:
        expect(page.get_by_role("button", name=event, exact=True)).to_be_visible()


@pytest.mark.scenario("S-08-17")
def test_a_detail_view_is_a_drawer_not_a_modal(page, shot):
    """Scenario: A detail view is a drawer, not a modal

    CORRECTED on one clause. The drawer DOES carry `role="dialog"` — the spec
    says it carries none. The substance of the scenario is unaffected and is
    what this asserts: the list is still rendered behind it, the tab badges are
    still readable, and the URL was pushed rather than replaced.
    """
    open_library(page, "?tab=skills")
    behind = page.locator(L.CARD).count()

    with shot("drawer-not-modal", "When I open a skill"):
        page.locator(L.CARD).first.click()
        page.wait_for_url("**/library/skills/**")

    assert page.locator(L.CARD).count() == behind, "the list unmounted behind the drawer"
    for testid, _label, _param in L.TABS:
        expect(page.locator(L.tab(testid))).to_be_visible()


@pytest.mark.scenario("S-08-18")
def test_closing_a_detail_returns_to_the_list_url(page, shot):
    """Scenario: Closing a detail returns to the list URL"""
    open_library(page, "?tab=hooks")
    page.locator(L.CARD).first.click()
    page.wait_for_url("**/library/hooks/**")

    with shot("drawer-closed", "When I close the drawer"):
        page.go_back()
        page.wait_for_url("**/library?tab=hooks")

    expect(page.locator(L.tab("tab-hooks"))).to_have_attribute("aria-selected", "true")
    expect(page.locator(L.CARD).first).to_be_visible()


@pytest.mark.scenario("S-08-19")
def test_deep_linking_a_detail_view_works_cold(page, shot):
    """Scenario: Deep-linking a detail view works cold"""
    open_library(page, "?tab=hooks")
    page.locator(L.CARD).first.click()
    page.wait_for_url("**/library/hooks/**")
    deep = page.url

    with shot("deep-link", f"When I cold-load a hook's own URL"):
        page.goto("/dashboard")
        page.goto(deep)
        page.wait_for_load_state("load")

    # A shared link must land on the right item AND the right tab.
    expect(page.locator(L.tab("tab-hooks"))).to_have_attribute("aria-selected", "true")
    assert page.url == deep


@pytest.mark.scenario("S-08-20")
def test_the_library_is_read_only(page, shot):
    """Scenario: The library is read-only"""
    with shot("read-only", 'When I cold-load "/library"'):
        open_library(page)

    labels = [
        (t or "").strip().lower()
        for t in page.locator("main button, button").all_text_contents()
    ]
    forbidden = [
        t
        for t in labels
        if any(verb in t for verb in ("create ", "new agent", "new skill", "new hook", "delete", "edit "))
    ]
    assert not forbidden, f"the library offers write controls: {forbidden}"
