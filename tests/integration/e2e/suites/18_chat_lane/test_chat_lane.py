"""Implements ../../../screens/18-chat-lane.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

Stubs below are SKIPPED rather than passing — a test that asserts nothing
but reports green is worse than no test at all.
"""

from __future__ import annotations

import pytest


@pytest.mark.scenario("S-18-01")
@pytest.mark.skip(reason="not yet implemented")
def test_the_lane_is_present_on_every_run_detail_surface(page, shot):
    """Scenario: The lane is present on every run-detail surface"""


@pytest.mark.scenario("S-18-02")
@pytest.mark.skip(reason="not yet implemented")
def test_the_lane_survives_every_tab(page, shot):
    """Scenario: The lane survives every tab"""


@pytest.mark.scenario("S-18-03")
@pytest.mark.skip(reason="not yet implemented")
def test_run_status_is_read_from_the_lane_not_the_tab_pane(page, shot):
    """Scenario: Run status is read from the lane, not the tab pane"""


@pytest.mark.scenario("S-18-04")
@pytest.mark.skip(reason="not yet implemented")
def test_back_returns_to_run_history_without_losing_the_filter(page, shot):
    """Scenario: Back returns to run history without losing the filter"""


@pytest.mark.scenario("S-18-05")
@pytest.mark.skip(reason="not yet implemented")
def test_every_message_declares_its_role_and_a_stable_id(page, shot):
    """Scenario: Every message declares its role and a stable id"""


@pytest.mark.scenario("S-18-06")
@pytest.mark.skip(reason="not yet implemented")
def test_the_narrator_names_each_lifecycle_event(page, shot):
    """Scenario: The narrator names each lifecycle event"""


@pytest.mark.scenario("S-18-07")
@pytest.mark.skip(reason="not yet implemented")
def test_a_clarification_request_points_at_steps(page, shot):
    """Scenario: A clarification request points at Steps"""


@pytest.mark.scenario("S-18-08")
@pytest.mark.defect
@pytest.mark.skip(reason="not yet implemented")
def test_the_clarification_exchange_is_not_duplicated(page, shot):
    """Scenario: The clarification exchange is not duplicated"""


@pytest.mark.scenario("S-18-09")
@pytest.mark.skip(reason="not yet implemented")
def test_a_diverted_run_links_to_the_workflow_it_handed_off_to(page, shot):
    """Scenario: A diverted run links to the workflow it handed off to"""


@pytest.mark.scenario("S-18-10")
@pytest.mark.skip(reason="not yet implemented")
def test_the_run_summary_collapses_and_expands(page, shot):
    """Scenario: The run summary collapses and expands"""


@pytest.mark.scenario("S-18-11")
@pytest.mark.skip(reason="not yet implemented")
def test_the_summary_label_does_not_announce_its_own_state(page, shot):
    """Scenario: The summary label does not announce its own state"""


@pytest.mark.scenario("S-18-12")
@pytest.mark.skip(reason="not yet implemented")
def test_send_is_gated_on_non_empty_input(page, shot):
    """Scenario: Send is gated on non-empty input"""


@pytest.mark.scenario("S-18-13")
@pytest.mark.skip(reason="not yet implemented")
def test_the_composer_offers_attachments_and_voice(page, shot):
    """Scenario: The composer offers attachments and voice"""


@pytest.mark.scenario("S-18-14")
@pytest.mark.skip(reason="not yet implemented")
def test_whether_the_user_can_reply_depends_on_the_run_s_state(page, shot):
    """Scenario: Whether the user can reply depends on the run's state"""


@pytest.mark.scenario("S-18-15")
@pytest.mark.defect
@pytest.mark.skip(reason="not yet implemented")
def test_terminal_runs_agree_on_whether_they_can_be_replied_to(page, shot):
    """Scenario: Terminal runs agree on whether they can be replied to"""


@pytest.mark.scenario("S-18-16")
@pytest.mark.destructive
@pytest.mark.skip(reason="not yet implemented")
def test_sending_a_message_adds_a_user_turn_and_a_reply(page, shot):
    """Scenario: Sending a message adds a user turn and a reply"""


@pytest.mark.scenario("S-18-17")
@pytest.mark.skip(reason="not yet implemented")
def test_a_chainable_run_offers_follow_on_workflows(page, shot):
    """Scenario: A chainable run offers follow-on workflows"""


@pytest.mark.scenario("S-18-18")
@pytest.mark.skip(reason="not yet implemented")
def test_the_unavailable_chip_has_its_own_testid(page, shot):
    """Scenario: The unavailable chip has its own testid"""


@pytest.mark.scenario("S-18-19")
@pytest.mark.skip(reason="not yet implemented")
def test_chain_suggestions_appear_only_where_they_are_meaningful(page, shot):
    """Scenario: Chain suggestions appear only where they are meaningful"""
