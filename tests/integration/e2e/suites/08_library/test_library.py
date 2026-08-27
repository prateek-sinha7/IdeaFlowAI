"""Implements ../../../screens/08-library.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

Stubs below are SKIPPED rather than passing — a test that asserts nothing
but reports green is worse than no test at all.
"""

from __future__ import annotations

import pytest


@pytest.mark.scenario("S-08-01")
@pytest.mark.skip(reason="not yet implemented")
def test_the_library_opens_on_agents_by_default(page, shot):
    """Scenario: The library opens on Agents by default"""


@pytest.mark.scenario("S-08-02")
@pytest.mark.skip(reason="not yet implemented")
def test_each_tab_is_addressable_by_query_param(page, shot):
    """Scenario: Each tab is addressable by query param"""


@pytest.mark.scenario("S-08-03")
@pytest.mark.skip(reason="not yet implemented")
def test_tab_badge_counts_agree_with_the_rendered_cards(page, shot):
    """Scenario: Tab badge counts agree with the rendered cards"""


@pytest.mark.scenario("S-08-04")
@pytest.mark.skip(reason="not yet implemented")
def test_switching_a_tab_updates_the_url(page, shot):
    """Scenario: Switching a tab updates the URL"""


@pytest.mark.scenario("S-08-05")
@pytest.mark.skip(reason="not yet implemented")
def test_category_counts_sum_to_the_all_count(page, shot):
    """Scenario: Category counts sum to the All count"""


@pytest.mark.scenario("S-08-06")
@pytest.mark.skip(reason="not yet implemented")
def test_filtering_by_category_narrows_the_grid(page, shot):
    """Scenario: Filtering by category narrows the grid"""


@pytest.mark.scenario("S-08-07")
@pytest.mark.skip(reason="not yet implemented")
def test_the_category_is_addressable_by_url(page, shot):
    """Scenario: The category is addressable by URL"""


@pytest.mark.scenario("S-08-08")
@pytest.mark.defect
@pytest.mark.skip(reason="not yet implemented")
def test_seven_agent_categories_are_empty_test_fixtures(page, shot):
    """Scenario: Seven agent categories are empty test fixtures"""


@pytest.mark.scenario("S-08-09")
@pytest.mark.skip(reason="not yet implemented")
def test_search_filters_the_current_tab(page, shot):
    """Scenario: Search filters the current tab"""


@pytest.mark.scenario("S-08-10")
@pytest.mark.skip(reason="not yet implemented")
def test_search_is_scoped_to_the_active_tab(page, shot):
    """Scenario: Search is scoped to the active tab"""


@pytest.mark.scenario("S-08-11")
@pytest.mark.skip(reason="not yet implemented")
def test_an_agent_opens_from_its_configure_affordance_not_its_card_body(page, shot):
    """Scenario: An agent opens from its Configure affordance, not its card body"""


@pytest.mark.scenario("S-08-12")
@pytest.mark.skip(reason="not yet implemented")
def test_an_agent_s_drawer_exposes_its_configuration_tabs(page, shot):
    """Scenario: An agent's drawer exposes its configuration tabs"""


@pytest.mark.scenario("S-08-13")
@pytest.mark.skip(reason="not yet implemented")
def test_each_agent_drawer_tab_shows_its_own_content(page, shot):
    """Scenario: Each agent drawer tab shows its own content"""


@pytest.mark.scenario("S-08-14")
@pytest.mark.skip(reason="not yet implemented")
def test_a_skill_opens_from_a_card_click_and_renders_its_document(page, shot):
    """Scenario: A skill opens from a card click and renders its document"""


@pytest.mark.scenario("S-08-15")
@pytest.mark.skip(reason="not yet implemented")
def test_a_hook_opens_from_a_card_click(page, shot):
    """Scenario: A hook opens from a card click"""


@pytest.mark.scenario("S-08-16")
@pytest.mark.skip(reason="not yet implemented")
def test_hook_categories_are_lifecycle_events(page, shot):
    """Scenario: Hook categories are lifecycle events"""


@pytest.mark.scenario("S-08-17")
@pytest.mark.skip(reason="not yet implemented")
def test_a_detail_view_is_a_drawer_not_a_modal(page, shot):
    """Scenario: A detail view is a drawer, not a modal"""


@pytest.mark.scenario("S-08-18")
@pytest.mark.skip(reason="not yet implemented")
def test_closing_a_detail_returns_to_the_list_url(page, shot):
    """Scenario: Closing a detail returns to the list URL"""


@pytest.mark.scenario("S-08-19")
@pytest.mark.skip(reason="not yet implemented")
def test_deep_linking_a_detail_view_works_cold(page, shot):
    """Scenario: Deep-linking a detail view works cold"""


@pytest.mark.scenario("S-08-20")
@pytest.mark.skip(reason="not yet implemented")
def test_the_library_is_read_only(page, shot):
    """Scenario: The library is read-only"""
