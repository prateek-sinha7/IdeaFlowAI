"""Implements ../../../screens/18-chat-lane.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

**The lane is the left column, not a tab.** A page object that models the run
page as a tab strip misses half the screen, which is what S-18-02 pins.

**The lane ASKS for clarifications but does not COLLECT them.** The answer is
given in Steps, so any test that expects to type it into the lane composer is
wrong about the surface.

Seeded runs only ever produce `data-role="narrator"`. The user and assistant
branches need a live turn and are unverified.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from framework import settings
from framework.locators import run_detail as L
from framework.locators import run_history as RH

ADORNMENTS_TOGGLE = '[data-testid="lane-adornments-toggle"]'
CHAIN_CHIP = '[data-testid="chat-chain-suggestion-chip"]'
CHAIN_CHIP_BETA = '[data-testid="chat-chain-suggestion-chip-beta"]'
CHAIN_HEADING = "TAKE THIS FURTHER"

CLARIFY_ASK = "Before I build, I need to lock a few things down."
CLARIFY_ANSWERED = "Clarifications answered"


def a_run_with_status(page, status: str) -> str:
    page.goto("/runs")
    expect(page.locator(RH.ROW).first).to_be_visible()
    match = next((label for label in RH.rows(page) if RH.status_of(label) == status), None)
    if not match:
        pytest.skip(f"no run in this history has status {status!r}")
    page.locator(f'{RH.ROW}[aria-label="{match}"]').first.click()
    page.wait_for_url(lambda url: "/runs/" in url)
    expect(page.locator(L.LANE)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS)
    return page.url.split("/runs/")[1].split("/")[0].split("?")[0]


def a_run_with(page, predicate, description: str) -> str:
    """The first completed run for which `predicate(page)` holds once opened."""
    page.goto("/runs")
    expect(page.locator(RH.ROW).first).to_be_visible()
    done = [label for label in RH.rows(page) if RH.status_of(label) == "completed"]
    for label in done[:8]:
        page.goto("/runs")
        expect(page.locator(RH.ROW).first).to_be_visible()
        page.locator(f'{RH.ROW}[aria-label="{label}"]').first.click()
        page.wait_for_url(lambda url: "/runs/" in url)
        expect(page.locator(L.LANE)).to_be_visible()
        page.wait_for_timeout(settings.SETTLE_MS)
        if predicate(page):
            return page.url.split("/runs/")[1].split("/")[0].split("?")[0]
    pytest.skip(f"no completed run {description}")


# ── structure ────────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-18-01")
def test_the_lane_is_present_on_every_run_detail_surface(page, shot):
    """Scenario: The lane is present on every run-detail surface"""
    with shot("lane", 'When I cold-load "/runs/{id}"'):
        a_run_with_status(page, "completed")

    expect(page.locator(L.LANE)).to_be_visible()
    for selector in (L.RUN_TYPE, L.RUN_STATUS, L.RUN_TITLE, L.RUN_META):
        expect(page.locator(selector)).not_to_be_empty()


@pytest.mark.scenario("S-18-02")
@pytest.mark.parametrize(("testid", "label", "suffix"), L.TABS, ids=[t[0] for t in L.TABS])
def test_the_lane_survives_every_tab(page, shot, testid, label, suffix):
    """Scenario: The lane survives every tab"""
    run_id = a_run_with_status(page, "completed")
    transcript = page.locator(L.MESSAGE).count()

    with shot(f"lane-on-{testid}", f'When I cold-load "/runs/{{id}}{suffix}"'):
        page.goto(f"/runs/{run_id}{suffix}")
        expect(page.locator(L.LANE)).to_be_visible()
        page.wait_for_timeout(settings.SETTLE_MS)

    assert page.locator(L.MESSAGE).count() == transcript, (
        "the transcript changed when the tab did"
    )
    expect(page.locator(L.tab(testid))).to_have_attribute("aria-selected", "true")


@pytest.mark.scenario("S-18-03")
def test_run_status_is_read_from_the_lane_not_the_tab_pane(page, shot):
    """Scenario: Run status is read from the lane, not the tab pane"""
    with shot("lane-status", "When I cold-load a failed run"):
        a_run_with_status(page, "failed")

    expect(page.locator(L.RUN_STATUS)).to_have_text(re.compile("failed", re.I))


@pytest.mark.scenario("S-18-04")
def test_back_returns_to_run_history_without_losing_the_filter(page, shot):
    """Scenario: Back returns to run history without losing the filter"""
    page.goto("/runs?type=custom")
    expect(page.locator(RH.ROW).first).to_be_visible()
    page.locator(RH.ROW).first.click()
    page.wait_for_url(lambda url: "/runs/" in url)
    expect(page.locator(L.LANE)).to_be_visible()

    with shot("lane-back", 'When I activate "lane-back"'):
        page.click(L.BACK)
        page.wait_for_url("**/runs**")
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    assert "/runs" in page.url
    expect(page.locator(RH.ROW).first).to_be_visible()


# ── transcript ───────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-18-05")
def test_every_message_declares_its_role_and_a_stable_id(page, shot):
    """Scenario: Every message declares its role and a stable id

    Seeded runs only ever produce `narrator`, so the ATTRIBUTE is asserted and
    the value is not — until a user turn exists there is nothing else to see.
    """
    with shot("messages", 'When I cold-load "/runs/{id}"'):
        a_run_with_status(page, "completed")

    messages = page.locator(L.MESSAGE).evaluate_all(
        "els => els.map(e => ({ role: e.dataset.role, id: e.dataset.messageId }))"
    )
    assert messages, "the transcript is empty"
    for message in messages:
        assert message["role"], f"a message declares no role: {message}"
        assert (message["id"] or "").startswith("chat_reply:"), (
            f"a message id is not a chat_reply: {message}"
        )
    assert len({m["id"] for m in messages}) == len(messages), "two messages share an id"


@pytest.mark.scenario("S-18-06")
@pytest.mark.parametrize(
    ("state", "message", "action"),
    [
        ("completed", "Run started", "Open in Steps"),
        ("completed", "Delivered — open in Preview →", "Open in Preview"),
        ("cancelled", "Cancelled by you", "Open in Steps"),
        ("failed", "What went wrong", "Open in Steps"),
    ],
)
def test_the_narrator_names_each_lifecycle_event(page, shot, state, message, action):
    """Scenario: The narrator names each lifecycle event"""
    with shot(f"narrator-{state}-{abs(hash(message)) % 1000}", f"When I open a {state} run"):
        a_run_with_status(page, state)

    body = page.evaluate("() => document.body.innerText")
    assert message in body, f"a {state} run's transcript never says {message!r}"
    assert action in body, f"{message!r} offers no {action!r}"


@pytest.mark.scenario("S-18-07")
def test_a_clarification_request_points_at_steps(page, shot):
    """Scenario: A clarification request points at Steps

    The lane ASKS but does not COLLECT — the answer is given in Steps.
    """
    run_id = a_run_with(
        page,
        lambda p: p.get_by_text(CLARIFY_ASK).count() > 0,
        "asked for clarifications",
    )

    with shot("clarify", "Then the transcript asks and points at Steps"):
        expect(page.get_by_text(CLARIFY_ASK).first).to_be_visible()

    expect(page.get_by_text(L.ANSWER_IN_STEPS).first).to_be_visible()

    with shot("clarify-opens-steps", 'When I activate "Answer in Steps"'):
        # A `chat-result-card-link` carrying `data-target-tab="thinking"`. It
        # selects the tab; whether it also pushes the URL is not the scenario's
        # claim, so the TAB is what this waits on.
        page.locator('[data-testid="chat-result-card-link"]').filter(
            has_text=L.ANSWER_IN_STEPS
        ).first.click()
        expect(page.locator(L.tab("tab-thinking"))).to_have_attribute(
            "aria-selected", "true"
        )

    assert run_id in page.url


@pytest.mark.scenario("S-18-08")
@pytest.mark.defect
def test_the_clarification_exchange_is_not_duplicated(page, shot):
    """Scenario: The clarification exchange is not duplicated

    INVERTED. The spec writes this as it SHOULD be and accepts being red; a
    suite where a scenario is red by design cannot tell a regression from a
    known gap, so this asserts the duplication — D-21 — and fails when it stops.

    Both halves appear TWICE on the affected runs, with different
    `data-message-id`s and identical text and actions. Two clarification rounds
    would explain it; two identical rounds reading as a repeat is the defect.
    """
    a_run_with(
        page,
        lambda p: p.get_by_text(CLARIFY_ASK).count() > 1,
        "shows a duplicated clarification exchange",
    )

    with shot("clarify-duplicated", "Then the exchange appears twice"):
        asks = page.get_by_text(CLARIFY_ASK).count()
        answered = page.get_by_text(CLARIFY_ANSWERED).count()

    assert asks > 1 and answered > 1, (
        f"the exchange no longer repeats ({asks} asks, {answered} answers) — "
        "D-21 is fixed; rewrite this as the spec's S-18-08"
    )
    # Different ids, identical text — which is what makes it a repeat rather
    # than two rounds rendered once each.
    ids = page.locator(L.MESSAGE).evaluate_all("els => els.map(e => e.dataset.messageId)")
    assert len(set(ids)) == len(ids), "the duplicate messages share an id"


@pytest.mark.scenario("S-18-09")
@pytest.mark.skip(reason="needs a diverted run; 22_handoff_and_gates creates one in the live tier")
def test_a_diverted_run_links_to_the_workflow_it_handed_off_to(page, shot):
    """Scenario: A diverted run links to the workflow it handed off to"""


# ── adornments ───────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-18-10")
def test_the_run_summary_collapses_and_expands(page, shot):
    """Scenario: The run summary collapses and expands

    `lane-adornments` is in the DOM in BOTH states, so its presence proves
    nothing — `aria-expanded` and the mini-map are the signal.
    """
    a_run_with(
        page,
        lambda p: p.locator(ADORNMENTS_TOGGLE).count() > 0,
        "renders a run-summary toggle",
    )
    toggle = page.locator(ADORNMENTS_TOGGLE).first

    with shot("adornments-collapsed", "Then the summary starts collapsed"):
        expect(toggle).to_have_attribute("aria-expanded", "false")

    with shot("adornments-expanded", "When I activate it"):
        toggle.click()
        expect(toggle).to_have_attribute("aria-expanded", "true")

    expect(page.locator(L.PIPELINE_MINI)).to_be_visible()
    # The card is what has to appear, not a filename in it: some runs render
    # "deliverable / open in preview →" with the name only on the Files tab.
    expect(page.locator(L.DELIVERABLE)).to_be_visible()
    expect(page.locator(L.DELIVERABLE)).to_contain_text(
        re.compile(r"preview|deliverable", re.I)
    )


@pytest.mark.scenario("S-18-11")
def test_the_summary_label_does_not_announce_its_own_state(page, shot):
    """Scenario: The summary label does not announce its own state

    The same trap as the "Dark mode" control in 17-theme-and-tiers: the label
    names the thing, not the state.
    """
    a_run_with(
        page,
        lambda p: p.locator(ADORNMENTS_TOGGLE).count() > 0,
        "renders a run-summary toggle",
    )
    toggle = page.locator(ADORNMENTS_TOGGLE).first

    with shot("summary-label", "When the adornments are expanded"):
        toggle.click()
        expect(toggle).to_have_attribute("aria-expanded", "true")

    assert "Run summary" in toggle.inner_text(), (
        f"the toggle now reads {toggle.inner_text()!r} — if it names its state, "
        "every test reading the label has to change"
    )


# ── composer ─────────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-18-12")
def test_send_is_gated_on_non_empty_input(page, shot):
    """Scenario: Send is gated on non-empty input"""
    a_run_with_status(page, "completed")
    send = page.locator(L.SEND).first

    with shot("send-disabled", "Then chat-send is disabled"):
        expect(send).to_be_disabled()

    with shot("send-enabled", 'When I type "a"'):
        page.fill(L.COMPOSER_INPUT, "a")
        expect(send).to_be_enabled()

    with shot("send-disabled-again", "When I clear the input"):
        page.fill(L.COMPOSER_INPUT, "")
        expect(send).to_be_disabled()


@pytest.mark.scenario("S-18-13")
@pytest.mark.defect
def test_the_composer_offers_attachments_and_voice(page, shot):
    """Scenario: The composer offers attachments and voice

    Attachments only. The lane's composer has a file input and NO voice control
    — the "Voice · transcribe" affordance the spec names exists on the launch
    panels, not here. Asserted as it is, so the day the lane gains one this test
    says so.
    """
    a_run_with_status(page, "completed")

    with shot("composer-controls", 'When I cold-load "/runs/{id}"'):
        expect(page.locator(L.COMPOSER)).to_be_visible()

    lane = page.locator(L.LANE)
    assert lane.locator('input[type="file"]').count() > 0, "no attachment input"
    assert lane.get_by_text("Voice", exact=False).count() == 0, (
        "the lane composer now offers a voice control — the spec's S-18-13 can "
        "be asserted in full"
    )


@pytest.mark.scenario("S-18-14")
@pytest.mark.parametrize(
    ("state", "present"),
    [("completed", True), ("failed", True), ("cancelled", False), ("diverted", False)],
)
def test_whether_the_user_can_reply_depends_on_the_runs_state(page, shot, state, present):
    """Scenario: Whether the user can reply depends on the run's state"""
    with shot(f"composer-{state}", f"When I open a {state} run"):
        a_run_with_status(page, state)

    count = page.locator(L.COMPOSER_INPUT).count()
    assert (count > 0) is present, (
        f"a {state} run {'has no' if present else 'has a'} chat message input"
    )


@pytest.mark.scenario("S-18-15")
@pytest.mark.defect
def test_terminal_runs_agree_on_whether_they_can_be_replied_to(page, shot):
    """Scenario: Terminal runs agree on whether they can be replied to

    INVERTED, for the same reason as S-18-08. Today a FAILED run has a fully
    enabled composer while a CANCELLED one has none — three terminal states, two
    contracts, no visible rule (D-19). `chat-composer` is in the DOM for both,
    so the container is not the signal; the input is.
    """
    with shot("failed-composer", "When I open a failed run"):
        a_run_with_status(page, "failed")
    failed = page.locator(L.COMPOSER_INPUT).count() > 0

    with shot("cancelled-composer", "When I open a cancelled run"):
        a_run_with_status(page, "cancelled")
    cancelled = page.locator(L.COMPOSER_INPUT).count() > 0

    assert failed != cancelled, (
        "failed and cancelled runs now agree on the reply affordance — D-19 is "
        "fixed; rewrite this as the spec's S-18-15"
    )
    assert failed and not cancelled, (
        f"the asymmetry reversed: failed={failed}, cancelled={cancelled}"
    )


@pytest.mark.scenario("S-18-16")
@pytest.mark.live
@pytest.mark.destructive
@pytest.mark.skip(
    reason="sending triggers a live LLM turn, and on a gated workflow it can "
    "create a gate only a human should answer; live tier"
)
def test_sending_a_message_adds_a_user_turn_and_a_reply(page, shot):
    """Scenario: Sending a message adds a user turn and a reply"""


# ── chaining ─────────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-18-17")
def test_a_chainable_run_offers_follow_on_workflows(page, shot):
    """Scenario: A chainable run offers follow-on workflows"""
    a_run_with(
        page,
        lambda p: p.get_by_text(CHAIN_HEADING).count() > 0,
        "offers chain suggestions",
    )

    with shot("chain-suggestions", 'Then I see "TAKE THIS FURTHER"'):
        expect(page.get_by_text(CHAIN_HEADING)).to_be_visible()

    chips = page.locator(f"{CHAIN_CHIP}, {CHAIN_CHIP_BETA}").all_text_contents()
    assert chips, "the heading is shown with no chips under it"
    # Which follow-ons a run offers depends on its deliverable, so an
    # unavailable one is not guaranteed here — S-18-18 goes looking for a run
    # that has one and asserts its own testid.
    assert all(text.strip() for text in chips), f"a chain chip is blank: {chips}"


@pytest.mark.scenario("S-18-18")
def test_the_unavailable_chip_has_its_own_testid(page, shot):
    """Scenario: The unavailable chip has its own testid

    A selector on the base testid silently misses it — use a prefix selector to
    count and an exact one to click.
    """
    a_run_with(
        page,
        lambda p: p.locator(CHAIN_CHIP_BETA).count() > 0,
        "offers an unavailable chain suggestion",
    )

    with shot("chain-beta-chip", "Then the SOON chip carries its own testid"):
        beta = page.locator(CHAIN_CHIP_BETA)
        expect(beta.first).to_be_visible()

    assert "SOON" in beta.first.inner_text()
    # The exact base testid must NOT match it.
    base_ids = page.locator(CHAIN_CHIP).evaluate_all(
        "els => els.map(e => e.dataset.testid)"
    )
    assert all(i == "chat-chain-suggestion-chip" for i in base_ids), base_ids


@pytest.mark.scenario("S-18-19")
@pytest.mark.skip(
    reason="what governs chain suggestions was never established — they showed "
    "on 1 of 6 runs and 'the run completed' is not the rule, so asserting their "
    "absence anywhere would be asserting a guess"
)
def test_chain_suggestions_appear_only_where_they_are_meaningful(page, shot):
    """Scenario: Chain suggestions appear only where they are meaningful"""
