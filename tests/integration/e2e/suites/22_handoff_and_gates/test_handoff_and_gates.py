"""Implements ../../../screens/22-handoff-and-gates.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

Stubs below are SKIPPED rather than passing — a test that asserts nothing
but reports green is worse than no test at all.
"""

from __future__ import annotations

import pytest


@pytest.mark.scenario("S-22-01")
@pytest.mark.skip(reason="not yet implemented")
def test_a_valid_handoff_opens_the_workflow_for_its_run(page, shot):
    """Scenario: A valid handoff opens the workflow for its run"""


@pytest.mark.scenario("S-22-02")
@pytest.mark.skip(reason="not yet implemented")
def test_an_invalid_token_is_refused_without_confirming_anything(page, shot):
    """Scenario: An invalid token is refused without confirming anything"""


@pytest.mark.scenario("S-22-03")
@pytest.mark.skip(reason="not yet implemented")
def test_another_user_s_handoff_token_is_refused_identically(page, shot):
    """Scenario: Another user's handoff token is refused identically"""


@pytest.mark.scenario("S-22-04")
@pytest.mark.skip(reason="not yet implemented")
def test_a_handoff_without_a_saved_github_pat_asks_for_one_first(page, shot):
    """Scenario: A handoff without a saved GitHub PAT asks for one first"""


@pytest.mark.scenario("S-22-05")
@pytest.mark.skip(reason="not yet implemented")
def test_start_pipeline_is_inert_until_a_pat_exists(page, shot):
    """Scenario: Start pipeline is inert until a PAT exists"""


@pytest.mark.scenario("S-22-06")
@pytest.mark.skip(reason="not yet implemented")
def test_an_expired_handoff_explains_how_to_mint_a_new_one(page, shot):
    """Scenario: An expired handoff explains how to mint a new one"""


@pytest.mark.scenario("S-22-07")
@pytest.mark.skip(reason="not yet implemented")
def test_only_a_pending_or_failed_handoff_can_be_started(page, shot):
    """Scenario: Only a pending or failed handoff can be started"""


@pytest.mark.scenario("S-22-08")
@pytest.mark.skip(reason="not yet implemented")
def test_the_handoff_shows_the_change_it_proposes(page, shot):
    """Scenario: The handoff shows the change it proposes"""


@pytest.mark.scenario("S-22-09")
@pytest.mark.skip(reason="not yet implemented")
def test_test_and_compliance_reports_render_when_produced(page, shot):
    """Scenario: Test and compliance reports render when produced"""


@pytest.mark.scenario("S-22-10")
@pytest.mark.skip(reason="not yet implemented")
def test_a_run_waiting_at_a_gate_offers_the_decision_in_the_lane(page, shot):
    """Scenario: A run waiting at a gate offers the decision in the lane"""


@pytest.mark.scenario("S-22-11")
@pytest.mark.skip(reason="not yet implemented")
def test_approving_continues_the_run(page, shot):
    """Scenario: Approving continues the run"""


@pytest.mark.scenario("S-22-12")
@pytest.mark.skip(reason="not yet implemented")
def test_requesting_changes_takes_instructions(page, shot):
    """Scenario: Requesting changes takes instructions"""


@pytest.mark.scenario("S-22-13")
@pytest.mark.skip(reason="not yet implemented")
def test_a_redo_takes_additional_instructions(page, shot):
    """Scenario: A redo takes additional instructions"""


@pytest.mark.scenario("S-22-14")
@pytest.mark.skip(reason="not yet implemented")
def test_the_gated_content_itself_is_editable_before_approval(page, shot):
    """Scenario: The gated content itself is editable before approval"""


@pytest.mark.scenario("S-22-15")
@pytest.mark.skip(reason="not yet implemented")
def test_a_choice_gate_presents_its_options(page, shot):
    """Scenario: A choice gate presents its options"""


@pytest.mark.scenario("S-22-16")
@pytest.mark.skip(reason="not yet implemented")
def test_the_gated_content_can_be_previewed_before_deciding(page, shot):
    """Scenario: The gated content can be previewed before deciding"""


@pytest.mark.scenario("S-22-17")
@pytest.mark.skip(reason="not yet implemented")
def test_rejecting_ends_the_run(page, shot):
    """Scenario: Rejecting ends the run"""


@pytest.mark.scenario("S-22-18")
@pytest.mark.destructive
@pytest.mark.skip(reason="not yet implemented")
def test_cancelling_the_run_from_a_gate_takes_two_steps(page, shot):
    """Scenario: Cancelling the run from a gate takes two steps"""


@pytest.mark.scenario("S-22-19")
@pytest.mark.skip(reason="not yet implemented")
def test_the_gate_shows_the_evidence_the_decision_is_about(page, shot):
    """Scenario: The gate shows the evidence the decision is about"""


@pytest.mark.scenario("S-22-20")
@pytest.mark.skip(reason="not yet implemented")
def test_a_code_artifact_can_be_copied_out_of_the_gate(page, shot):
    """Scenario: A code artifact can be copied out of the gate"""


@pytest.mark.scenario("S-22-21")
@pytest.mark.skip(reason="not yet implemented")
def test_a_readiness_verdict_is_hoisted_above_the_prose(page, shot):
    """Scenario: A readiness verdict is hoisted above the prose"""


@pytest.mark.scenario("S-22-22")
@pytest.mark.skip(reason="not yet implemented")
def test_a_gate_decision_is_the_human_s_alone_in_the_product(page, shot):
    """Scenario: A gate decision is the human's alone in the product"""


@pytest.mark.scenario("S-22-23")
@pytest.mark.skip(reason="not yet implemented")
def test_a_run_asking_for_clarifications_offers_them_in_the_lane(page, shot):
    """Scenario: A run asking for clarifications offers them in the lane"""


@pytest.mark.scenario("S-22-24")
@pytest.mark.skip(reason="not yet implemented")
def test_suggested_answers_are_offered_as_chips(page, shot):
    """Scenario: Suggested answers are offered as chips"""


@pytest.mark.scenario("S-22-25")
@pytest.mark.skip(reason="not yet implemented")
def test_a_free_text_question_can_be_answered_without_chips(page, shot):
    """Scenario: A free-text question can be answered without chips"""


@pytest.mark.scenario("S-22-26")
@pytest.mark.skip(reason="not yet implemented")
def test_typing_overrides_a_selected_chip(page, shot):
    """Scenario: Typing overrides a selected chip"""


@pytest.mark.scenario("S-22-27")
@pytest.mark.skip(reason="not yet implemented")
def test_every_question_can_be_skipped_at_once(page, shot):
    """Scenario: Every question can be skipped at once"""


@pytest.mark.scenario("S-22-28")
@pytest.mark.destructive
@pytest.mark.skip(reason="not yet implemented")
def test_the_whole_run_can_be_cancelled_from_the_clarify_prompt(page, shot):
    """Scenario: The whole run can be cancelled from the clarify prompt"""
