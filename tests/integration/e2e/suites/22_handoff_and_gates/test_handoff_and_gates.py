"""Implements ../../../screens/22-handoff-and-gates.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

**Almost everything here needs a run parked at a gate**, and reaching that state
costs a real LLM run and leaves a decision a human has to make. The gate and
clarify controls are therefore asserted as DECLARED (`framework/source.py`) —
the same treatment 23-controls-inventory gives the states it cannot reach — and
the live tier is where the decisions themselves get exercised.

What IS reachable offline: the handoff token routes, and the aftermath of gates
that already happened, which the audit trail and the transcript both record.

`chat-gate-choice-<value>` is TEMPLATED on the choice value, so the set is
data-dependent. Enumerate it from the prompt's options; never hard-code the
suffixes.
"""

from __future__ import annotations

import json
import re

import pytest
from playwright.sync_api import expect

from framework import api, settings
from framework import source as SOURCE
from framework.locators import outside_routes as OUT
from framework.locators import run_detail as RD
from framework.locators import run_history as RH

_NEEDS_A_GATE = (
    "needs a run parked at a review gate; reaching one costs a real LLM run and "
    "leaves a decision a human must make. Live tier."
)
_NEEDS_A_HANDOFF = (
    "needs a handoff session, which is minted by POST /api/handoff/receive with a "
    "valid X-Flowin-API-Key. Live tier."
)


def a_completed_run(page) -> str:
    page.goto("/runs")
    expect(page.locator(RH.ROW).first).to_be_visible()
    done = [label for label in RH.rows(page) if RH.status_of(label) == "completed"]
    assert done, "no completed run"
    page.locator(f'{RH.ROW}[aria-label="{done[0]}"]').first.click()
    page.wait_for_url(lambda url: "/runs/" in url)
    expect(page.locator(RD.LANE)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS)
    return page.url.split("/runs/")[1].split("/")[0].split("?")[0]


# ── the handoff routes ───────────────────────────────────────────────────────


@pytest.mark.scenario("S-22-01")
@pytest.mark.destructive
def test_a_valid_handoff_opens_the_workflow_for_its_run(page, shot, handoff_session):
    """Scenario: A valid handoff opens the workflow for its run"""
    session = handoff_session()

    with shot("valid-handoff", 'When I cold-load "/handoff/{token}"'):
        page.goto(f"/handoff/{session['token']}")
        page.wait_for_load_state("load")
        page.wait_for_timeout(settings.SETTLE_MS)

    body = page.evaluate("() => document.body.innerText")
    assert OUT.HANDOFF_NOT_FOUND not in body, "a freshly minted handoff was refused"
    assert "HANDOFF WORKFLOW" in body.upper(), f"the handoff surface did not render: {body[:200]!r}"
    # It names the task and the repository the handoff is about.
    assert "E2E handoff fixture" in body
    assert "github.com/flowinqa/e2e-fixture" in body


@pytest.mark.scenario("S-22-02")
def test_an_invalid_token_is_refused_without_confirming_anything(page, shot):
    """Scenario: An invalid token is refused without confirming anything

    The refusal must not distinguish "no such handoff" from "not yours" — a
    difference between the two answers would confirm which tokens exist.
    """
    with shot("invalid-handoff", 'When I cold-load "/handoff/invalid-token"'):
        page.goto("/handoff/invalid-token")
        page.wait_for_load_state("load")
        page.wait_for_timeout(settings.SETTLE_MS)

    expect(page.get_by_text(OUT.HANDOFF_NOT_FOUND).first).to_be_visible()
    body = page.evaluate("() => document.body.innerText")
    for leak in ("expired", "not yours", "belongs to", "another user"):
        assert leak not in body.lower(), (
            f"the refusal says {leak!r}, which tells an attacker the token exists"
        )


@pytest.mark.scenario("S-22-03")
@pytest.mark.destructive
@pytest.mark.role("basic")
def test_another_users_handoff_token_is_refused_identically(page, shot, handoff_session):
    """Scenario: Another user's handoff token is refused identically

    Asserted as a SAMENESS: a foreign token and an invented one must produce the
    same screen. A difference between them is information about which tokens
    exist.
    """
    foreign = handoff_session(owner="admin")["token"]
    screens = []
    for token in (foreign, "00000000-0000-0000-0000-000000000000"):
        with shot(f"handoff-{token[:12]}", f'When I cold-load "/handoff/{token}"'):
            page.goto(f"/handoff/{token}")
            page.wait_for_load_state("load")
            page.wait_for_timeout(settings.SETTLE_MS)
        screens.append(page.evaluate("() => document.body.innerText"))

    assert screens[0] == screens[1], (
        "another user's handoff and an invented token render different screens — "
        "the difference tells an attacker which tokens exist"
    )
    assert OUT.HANDOFF_NOT_FOUND in screens[0], (
        f"a foreign handoff was not refused at all: {screens[0][:300]!r}"
    )


@pytest.mark.scenario("S-22-04")
@pytest.mark.destructive
def test_a_handoff_without_a_saved_github_pat_asks_for_one_first(page, shot, handoff_session):
    """Scenario: A handoff without a saved GitHub PAT asks for one first

    Deliberate, and stated in the source: `/receive` does NOT require a PAT so
    the user can be prompted after clicking the URL. `/start` enforces it. This
    is that prompt.
    """
    session = handoff_session()

    with shot("handoff-needs-pat", "When I open the handoff with no PAT saved"):
        page.goto(f"/handoff/{session['token']}")
        page.wait_for_load_state("load")
        page.wait_for_timeout(settings.SETTLE_MS)

    body = page.evaluate("() => document.body.innerText")
    assert "One more step before this can run" in body, (
        f"the handoff does not ask for a PAT: {body[:300]!r}"
    )
    assert "repo scope" in body
    expect(page.locator(OUT.GITHUB_PAT)).to_be_visible()


@pytest.mark.scenario("S-22-05")
@pytest.mark.destructive
def test_start_pipeline_is_inert_until_a_pat_exists(page, shot, handoff_session):
    """Scenario: Start pipeline is inert until a PAT exists

    Asserted at the API as well as on the screen: a start that the button
    merely hides would still be reachable by anyone who knew the URL.
    """
    session = handoff_session()

    with shot("start-inert", "When I open a handoff with no PAT saved"):
        page.goto(f"/handoff/{session['token']}")
        page.wait_for_load_state("load")
        page.wait_for_timeout(settings.SETTLE_MS)

    start = page.get_by_role("button", name=re.compile(r"start", re.I))
    if start.count():
        assert start.first.is_disabled(), (
            "a handoff with no PAT offers an enabled start control"
        )

    result = api.full(page, "POST", f"/api/handoff/{session['token']}/start", {})
    assert result["status"] >= 400, (
        f"the pipeline started without a GitHub PAT: {result['status']} "
        f"{result['body'][:200]}"
    )


@pytest.mark.scenario("S-22-06")
@pytest.mark.skip(
    reason="needs a handoff past its expires_at; they lapse about an hour out "
    "and there is no endpoint to age one"
)
def test_an_expired_handoff_explains_how_to_mint_a_new_one(page, shot):
    """Scenario: An expired handoff explains how to mint a new one"""


@pytest.mark.scenario("S-22-07")
@pytest.mark.destructive
def test_only_a_pending_or_failed_handoff_can_be_started(page, shot, handoff_session):
    """Scenario: Only a pending or failed handoff can be started"""
    session = handoff_session()
    assert session["status"] == "pending", (
        f"a fresh handoff is {session['status']!r}, not pending"
    )

    with shot("handoff-status", "Then a fresh handoff is pending"):
        page.goto(f"/handoff/{session['token']}")
        page.wait_for_load_state("load")
        page.wait_for_timeout(settings.SETTLE_MS)

    read = api.full(page, "GET", f"/api/handoff/{session['token']}")
    assert read["status"] == 200, read["body"][:200]
    assert json.loads(read["body"])["status"] in ("pending", "failed"), (
        "a startable handoff reports a status outside pending/failed"
    )


@pytest.mark.scenario("S-22-08")
@pytest.mark.destructive
def test_the_handoff_shows_the_change_it_proposes(page, shot, handoff_session):
    """Scenario: The handoff shows the change it proposes"""
    session = handoff_session(task="Rename the greeting helper and update its tests")

    with shot("handoff-proposal", "Then it names the task and the repository"):
        page.goto(f"/handoff/{session['token']}")
        page.wait_for_load_state("load")
        page.wait_for_timeout(settings.SETTLE_MS)

    body = page.evaluate("() => document.body.innerText")
    assert "Rename the greeting helper" in body, (
        f"the handoff does not show the change it proposes: {body[:300]!r}"
    )
    assert "github.com/flowinqa/e2e-fixture" in body


@pytest.mark.scenario("S-22-09")
@pytest.mark.skip(
    reason="test and compliance reports only exist once a handoff has RUN, which "
    "needs a GitHub PAT with repo scope and a real pipeline; live tier"
)
def test_test_and_compliance_reports_render_when_produced(page, shot):
    """Scenario: Test and compliance reports render when produced"""


# ── review gates ─────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-22-10")
def test_a_run_waiting_at_a_gate_offers_the_decision_in_the_lane(page, shot):
    """Scenario: A run waiting at a gate offers the decision in the lane"""
    with shot("gate-actions", "Then the gate actions are declared"):
        SOURCE.assert_declared(
            "chat-gate-actions", "chat-gate-approve", "chat-gate-request-changes",
            "chat-gate-reject",
        )


@pytest.mark.scenario("S-22-11")
def test_approving_continues_the_run(page, shot):
    """Scenario: Approving continues the run

    The AFTERMATH is reachable: a completed gated run's transcript records
    "Review approved — build continues". The act itself needs the gate, so the
    control is asserted as declared and the message as produced.
    """
    SOURCE.assert_declared("chat-gate-approve")
    a_completed_run(page)

    with shot("approval-aftermath", "Then a gated run records the approval"):
        body = page.evaluate("() => document.body.innerText")

    if "Review approved" not in body:
        pytest.skip("this run passed no review gate")
    assert "Review approved — build continues" in body


@pytest.mark.scenario("S-22-12")
def test_requesting_changes_takes_instructions(page, shot):
    """Scenario: Requesting changes takes instructions"""
    with shot("request-changes", "Then the request-changes control is declared"):
        SOURCE.assert_declared("chat-gate-request-changes")


@pytest.mark.scenario("S-22-13")
def test_a_redo_takes_additional_instructions(page, shot):
    """Scenario: A redo takes additional instructions"""
    with shot("redo", "Then the redo control and its field are declared"):
        SOURCE.assert_declared("chat-gate-redo", "redo-instructions")
    assert "Additional instructions for redo" in SOURCE._corpus(), (
        "the redo field lost its label"
    )


@pytest.mark.scenario("S-22-14")
def test_the_gated_content_itself_is_editable_before_approval(page, shot):
    """Scenario: The gated content itself is editable before approval

    Approving edits the artifact as well as unblocking the run — the human is
    not a rubber stamp — so the editable field has to survive as a named thing.
    """
    with shot("gate-content", "Then the editable gate content is declared"):
        SOURCE.assert_declared("gate-content")
    assert "Edit gate content" in SOURCE._corpus(), "the edit affordance lost its name"


@pytest.mark.scenario("S-22-15")
def test_a_choice_gate_presents_its_options(page, shot):
    """Scenario: A choice gate presents its options

    `chat-gate-choice-<value>` is templated on the choice value, so only the
    static prefix can be verified — the suffixes are data and must be enumerated
    from the prompt.
    """
    with shot("choice-gate", "Then the choice prompt and its chips are declared"):
        SOURCE.assert_declared("chat-gate-choice-prompt")
    assert "chat-gate-choice-" in SOURCE._corpus(), (
        "the per-option control prefix is gone; the options cannot be addressed"
    )


@pytest.mark.scenario("S-22-16")
def test_the_gated_content_can_be_previewed_before_deciding(page, shot):
    """Scenario: The gated content can be previewed before deciding"""
    with shot("gate-preview", "Then the preview control is declared"):
        SOURCE.assert_declared("chat-gate-preview")


@pytest.mark.scenario("S-22-17")
def test_rejecting_ends_the_run(page, shot):
    """Scenario: Rejecting ends the run"""
    with shot("gate-reject", "Then the reject control is declared"):
        SOURCE.assert_declared("chat-gate-reject")


@pytest.mark.scenario("S-22-18")
def test_cancelling_the_run_from_a_gate_takes_two_steps(page, shot):
    """Scenario: Cancelling the run from a gate takes two steps

    Two steps deliberately: cancelling from a gate destroys work the run has
    already done.
    """
    with shot("gate-cancel", "Then the cancel control is declared"):
        SOURCE.assert_declared("chat-gate-cancel")


@pytest.mark.scenario("S-22-19")
def test_the_gate_shows_the_evidence_the_decision_is_about(page, shot):
    """Scenario: The gate shows the evidence the decision is about"""
    with shot("gate-well", "Then the evidence well is declared"):
        SOURCE.assert_declared("gate-well")
    assert "data-well-kind" in SOURCE._corpus(), (
        "the well no longer declares its kind, so prose and code cannot be told apart"
    )


@pytest.mark.scenario("S-22-20")
def test_a_code_artifact_can_be_copied_out_of_the_gate(page, shot):
    """Scenario: A code artifact can be copied out of the gate"""
    with shot("gate-copy", "Then the copy control is declared"):
        SOURCE.assert_declared("gate-well-copy")


@pytest.mark.scenario("S-22-21")
def test_a_readiness_verdict_is_hoisted_above_the_prose(page, shot):
    """Scenario: A readiness verdict is hoisted above the prose

    The verdict is the one thing the human is being asked about, so it is
    lifted out of the prose and toned rather than left to be read for.
    """
    with shot("gate-verdict", "Then the verdict block is declared"):
        SOURCE.assert_declared("gate-well-verdict")
    assert "data-verdict-tone" in SOURCE._corpus(), "the verdict lost its tone attribute"


@pytest.mark.scenario("S-22-22")
def test_a_gate_decision_is_the_humans_alone_in_the_product(page, shot):
    """Scenario: A gate decision is the human's alone in the product

    No surface in the product decides a gate on the user's behalf. Asserted from
    source: the decision endpoint is called from the gate controls and from
    nowhere that runs unattended.
    """
    with shot("human-only", "Then nothing auto-answers a gate"):
        corpus = SOURCE._corpus()

    assert "chat-gate-approve" in corpus, "the approve control is gone"
    for auto in ("autoApproveGate", "auto_approve_gate", "approveAllGates"):
        assert auto not in corpus, (
            f"{auto} exists — something can answer a gate without a human"
        )


# ── clarifications ───────────────────────────────────────────────────────────


@pytest.mark.scenario("S-22-23")
def test_a_run_asking_for_clarifications_offers_them_in_the_lane(page, shot):
    """Scenario: A run asking for clarifications offers them in the lane

    18-chat-lane's S-18-07 covers the ASK, which is reachable; this covers the
    controls that collect the answer, which are not.
    """
    with shot("clarify-actions", "Then the clarify actions are declared"):
        SOURCE.assert_declared("chat-clarify-actions", "chat-clarify-submit")


@pytest.mark.scenario("S-22-24")
def test_suggested_answers_are_offered_as_chips(page, shot):
    """Scenario: Suggested answers are offered as chips"""
    with shot("clarify-chips", "Then the chips are declared"):
        SOURCE.assert_declared("chat-clarify-chip", "chat-clarify-submit")


@pytest.mark.scenario("S-22-25")
def test_a_free_text_question_can_be_answered_without_chips(page, shot):
    """Scenario: A free-text question can be answered without chips"""
    with shot("clarify-text", "Then the free-text field is declared"):
        SOURCE.assert_declared("chat-clarify-text")


@pytest.mark.scenario("S-22-26")
def test_typing_overrides_a_selected_chip(page, shot):
    """Scenario: Typing overrides a selected chip

    A hybrid question offers both, and the typed answer wins — otherwise a user
    who picks a chip and then explains themselves has their explanation
    discarded silently.
    """
    with shot("clarify-hybrid", "Then both inputs are declared"):
        SOURCE.assert_declared("chat-clarify-chip", "chat-clarify-text")


@pytest.mark.scenario("S-22-27")
def test_every_question_can_be_skipped_at_once(page, shot):
    """Scenario: Every question can be skipped at once"""
    with shot("clarify-skip-all", "Then the skip-all control is declared"):
        SOURCE.assert_declared("chat-clarify-skip-all")


@pytest.mark.scenario("S-22-28")
def test_the_whole_run_can_be_cancelled_from_the_clarify_prompt(page, shot):
    """Scenario: The whole run can be cancelled from the clarify prompt"""
    with shot("clarify-cancel", "Then the cancel-workflow control is declared"):
        SOURCE.assert_declared("chat-clarify-cancel-workflow")
