"""Implements ../../../screens/04-composer-canvas.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

**`Save workflow` vs `Save as copy` is the whole point of this surface.** One
component serves three routes and only the Save label separates them, so every
mode test asserts the exact label and the absence of the other. A built-in that
became overwritable in place would still pass a test that only checked "a save
button exists".

The reorder, remove and rename scenarios mutate composer state without saving,
so they leave nothing behind. The two that DO write clean up after themselves.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from framework import settings
from framework.locators import composer as L
from framework.locators import saved_workflows as W


def open_composer(page, route: str, nodes: int | None = None) -> list[str]:
    """Open a composer route and wait until its roster is actually drawn.

    `nodes` is the count to wait for — `None` means "at least one", `0` means
    "expect none". Without this the header summary and the BRIEF node arrive
    first and a test reads an empty roster.
    """
    page.goto(route)
    expect(page.locator(L.HEADER_SUMMARY)).to_be_visible()
    expect(page.locator(L.BRIEF_NODE)).to_be_visible()
    order = L.wait_for_nodes(page, nodes)
    # The canvas animates its nodes into place. Clicking a per-node control
    # before that settles fails on "element is not stable", and reading the
    # order mid-animation can return it in flight.
    page.wait_for_timeout(settings.SETTLE_MS // 2)
    return order


def open_override_editor(page) -> str:
    """The saved ppt override's composer, and its id."""
    page.goto("/workflows")
    expect(page.locator(W.CARD).first).to_be_visible()
    W.card(page, W.OVERRIDE_TITLE).locator(W.ACTIONS).click()
    page.get_by_role("menuitem", name="Edit").click()
    page.wait_for_url("**/workflows/*/edit")
    expect(page.locator(L.HEADER_SUMMARY)).to_be_visible()
    L.wait_for_nodes(page)
    return page.url.split("/workflows/")[1].split("/")[0]


# ── the three modes ──────────────────────────────────────────────────────────


@pytest.mark.scenario("S-04-01")
def test_a_brand_new_composer_opens_empty(page, shot):
    """Scenario: A brand-new composer opens empty"""
    with shot("composer-new", 'When I cold-load "/workflows/new"'):
        open_composer(page, "/workflows/new", nodes=0)

    expect(page.get_by_text("CUSTOM · COMPOSER")).to_be_visible()
    summary = page.locator(L.HEADER_SUMMARY).inner_text().replace("\n", " ")
    assert "0 agents" in summary and "0 review gates" in summary, summary
    # A bare mount really does render an empty composer: ComposerPage seeds its
    # agents only from initialManifestSteps/initialAgentIds.
    assert L.node_order(page) == []
    expect(page.locator(L.SAVE_WORKFLOW)).to_be_visible()
    expect(page.locator(L.SAVE_AS_COPY)).to_have_count(0)


@pytest.mark.scenario("S-04-02")
def test_editing_a_saved_workflow_loads_its_steps(page, shot):
    """Scenario: Editing a saved workflow loads its steps"""
    with shot("composer-edit", 'When I cold-load "/workflows/{id}/edit"'):
        open_override_editor(page)

    assert L.agent_count(page) == 4
    assert len(L.node_order(page)) == 4
    expect(page.locator(L.SAVE_WORKFLOW)).to_be_visible()
    expect(page.locator(L.SAVE_AS_COPY)).to_have_count(0)


@pytest.mark.scenario("S-04-03")
def test_a_built_in_opens_read_to_copy_not_read_to_overwrite(page, shot):
    """Scenario: A built-in opens read-to-copy, not read-to-overwrite

    ADR-0014, and the single most important assertion on this surface: a
    built-in is a file on disk with nothing to write back to, so it must never
    offer an in-place save.
    """
    with shot("composer-canvas", 'When I cold-load "/workflows/ppt/canvas"'):
        open_composer(page, "/workflows/ppt/canvas", nodes=len(L.PPT_AGENT_IDS))

    expect(page.get_by_text("PPT · COPY")).to_be_visible()
    expect(page.locator(L.SAVE_AS_COPY)).to_be_visible()
    expect(page.locator(L.SAVE_WORKFLOW)).to_have_count(0)

    # Uppercased by CSS; the DOM text is "Core".
    assert page.get_by_text("Core", exact=True).count() == len(L.PPT_AGENT_IDS)


@pytest.mark.scenario("S-04-04")
def test_a_built_in_canvas_survives_a_hard_refresh(page, shot):
    """Scenario: A built-in canvas survives a hard refresh"""
    before = open_composer(page, "/workflows/ppt/canvas", nodes=len(L.PPT_AGENT_IDS))

    with shot("canvas-refreshed", "When I reload the page"):
        page.reload()
        expect(page.locator(L.HEADER_SUMMARY)).to_be_visible()
        L.wait_for_nodes(page, len(L.PPT_AGENT_IDS))

    # The pipeline_type travels in the URL precisely so the composer can rebuild
    # from the API on any mount — there is no sessionStorage handoff.
    expect(page.get_by_text("PPT · COPY")).to_be_visible()
    assert L.node_order(page) == before


@pytest.mark.scenario("S-04-05")
def test_switching_between_simple_and_canvas_keeps_the_roster(page, shot):
    """Scenario: Switching between Simple and Canvas keeps the roster"""
    before = open_composer(page, "/workflows/ppt/canvas", nodes=len(L.PPT_AGENT_IDS))

    with shot("simple-view", 'When I click "Simple"'):
        page.click(L.SIMPLE)
        page.wait_for_timeout(settings.SETTLE_MS // 3)

    for name in L.PPT_DISPLAY_NAMES:
        expect(page.get_by_text(name).first).to_be_visible()

    with shot("canvas-view", 'When I click "Canvas"'):
        page.click(L.CANVAS_TAB)
        expect(page.locator(L.CANVAS)).to_be_visible()

    assert L.node_order(page) == before


# ── editing the plan ─────────────────────────────────────────────────────────


@pytest.mark.scenario("S-04-06")
def test_adding_an_agent_from_the_library_modal(page, shot):
    """Scenario: Adding an agent from the library modal

    CORRECTED twice.

    The panel offers no blank "Custom Agent" entry at all — on `/workflows/new`
    as much as on an override — so this adds the first agent it does offer.

    And the panel CLOSES after an add. The spec records the opposite as quirk
    `addAgentModalStaysOpen`; today the "+ Add" buttons are gone the moment the
    node appears, which is why S-04-08 re-opens it for every agent it adds.
    """
    open_composer(page, "/workflows/new", nodes=0)

    with shot("add-agent-modal", 'When I click the "Add agent" control'):
        page.locator(L.ADD_AGENT).first.click()
        expect(page.locator(L.ADD_TO_PLAN).first).to_be_visible(timeout=15000)

    with shot("agent-added", "When I add the first agent offered"):
        # Scoped to one card's own "+ Add": the label repeats once per card.
        page.locator(L.ADD_TO_PLAN).first.click()
        L.wait_for_nodes(page, 1)

    assert L.agent_count(page) == 1
    expect(page.locator(L.ADD_TO_PLAN)).to_have_count(0)

    with shot("modal-closed", "When I press Escape"):
        # Already closed by the add; Escape must not undo it.
        page.keyboard.press("Escape")
        page.wait_for_timeout(settings.SETTLE_MS // 4)

    assert len(L.node_order(page)) == 1


@pytest.mark.scenario("S-04-07")
def test_reordering_a_node_moves_it_in_the_plan(page, shot):
    """Scenario: Reordering a node moves it in the plan"""
    original = open_composer(page, "/workflows/ppt/canvas", nodes=len(L.PPT_AGENT_IDS))
    middle = original[1]

    swapped = [original[1], original[0], *original[2:]]

    with shot("moved-earlier", "When I move the second node earlier"):
        page.click(L.move_earlier(middle))
        L.wait_for_order(page, swapped)

    with shot("moved-later", "When I move it later again"):
        page.click(L.move_later(middle))
        L.wait_for_order(page, original)


@pytest.mark.scenario("S-04-08")
@pytest.mark.defect
def test_removing_a_node_drops_it_from_the_summary(page, shot):
    """Scenario: Removing a node drops it from the summary

    Asserts TODAY'S behaviour, which is that a node CANNOT be removed — D-30.

    On a brand-new custom composition, every agent added from the library comes
    back with its Remove control `disabled` and titled "Core agents can't be
    removed", while only one of the three renders a Core badge. The lock does
    not match the badge, and it leaves an author able to add agents to their own
    workflow and unable to take any of them out again.

    The built-in canvas is the wrong place to test this — there the lock is
    correct, since every ppt step really is core.
    """
    open_composer(page, "/workflows/new", nodes=0)
    for n in range(1, 4):
        # Escape between adds. The overlay stays mounted after an add, and a
        # second "Add agent" click stacks another one on top — the new overlay
        # then intercepts every click meant for the cards underneath.
        page.locator(L.ADD_AGENT).first.click()
        expect(page.locator(L.ADD_TO_PLAN).first).to_be_visible(timeout=15000)
        page.locator(L.ADD_TO_PLAN).first.click()
        L.wait_for_nodes(page, n)
        page.keyboard.press("Escape")
        page.wait_for_timeout(settings.SETTLE_MS // 3)

    with shot("no-node-can-be-removed", "When I try to remove a node I just added"):
        assert L.agent_count(page) == 3

    removes = page.evaluate(
        """() => [...document.querySelectorAll('[aria-label^="Remove "]')]
             .map(e => ({ label: e.getAttribute('aria-label'), disabled: e.disabled }))"""
    )
    assert len(removes) == 3
    assert all(r["disabled"] for r in removes), (
        "a node became removable — D-30 is fixed. Rewrite this test as the "
        f"spec's S-04-08: remove one and assert the summary drops to 2. {removes}"
    )
    # The badge and the lock disagree: one Core badge, three locked controls.
    assert page.get_by_text("Core", exact=True).count() < len(removes)


@pytest.mark.scenario("S-04-09")
def test_renaming_a_node_updates_its_label_and_its_control_names(page, shot):
    """Scenario: Renaming a node updates its label and its control names"""
    open_composer(page, "/workflows/ppt/canvas", nodes=len(L.PPT_AGENT_IDS))
    old, new = L.PPT_DISPLAY_NAMES[-1], "Deck Review"
    agent_id = L.PPT_AGENT_IDS[-1]

    with shot("node-renamed", f'When I rename "{old}" to "{new}"'):
        page.click(L.rename(agent_id))
        # A PAGE-level input, not one inside the node.
        field = page.locator(L.AGENT_RENAME)
        field.fill(new)
        field.press("Enter")
        page.wait_for_timeout(settings.SETTLE_MS // 3)

    expect(page.locator(L.node(agent_id))).to_contain_text(new)
    # The per-node aria-labels are DERIVED from the display name, so a helper
    # that cached them before the rename is now addressing nothing. Note the
    # renamed control loses the " Agent" suffix the seeded names carry — the
    # label is `Rename <name>`, and the built-in's name ends in "Agent".
    expect(page.locator(f'[aria-label="Rename {new}"]')).to_have_count(1)
    expect(page.locator(f'[aria-label="Rename {old} Agent"]')).to_have_count(0)


# ── the config rail ──────────────────────────────────────────────────────────


@pytest.mark.scenario("S-04-10")
def test_the_config_rails_agent_tab_has_five_sub_tabs_of_its_own(page, shot):
    """Scenario: The config rail's Agent tab has five sub-tabs of its own"""
    open_composer(page, "/workflows/ppt/canvas", nodes=len(L.PPT_AGENT_IDS))

    with shot("rail-agent", 'When I click the rail tab "Agent"'):
        page.click(L.RAIL_AGENT)
        expect(page.locator(L.AGENT_NAME)).to_be_visible()

    # "step 1 of 3", not the display name: the heading uses the agent's ROLE
    # ("Slide Plan & Content Architecture"), not its canvas label.
    expect(page.get_by_text(re.compile(r"Agent · step 1 of \d"))).to_be_visible()
    for sub in L.AGENT_SUBTABS:
        expect(page.get_by_text(sub, exact=True).first).to_be_visible()


@pytest.mark.scenario("S-04-11")
def test_the_agent_skills_picker_is_part_of_the_rail_not_a_modal(page, shot):
    """Scenario: The agent Skills picker is part of the rail, not a modal

    Recorded because the surface manifest classified this as an overlay from a
    `fixed inset-0` match in the source. At runtime it is inline, and a helper
    that waits for a dialog here waits forever.
    """
    open_composer(page, "/workflows/ppt/canvas", nodes=len(L.PPT_AGENT_IDS))
    page.click(L.RAIL_AGENT)
    expect(page.locator(L.AGENT_NAME)).to_be_visible()
    dialogs_before = page.locator('[role="dialog"]').count()

    with shot("rail-skills", 'When I click the sub-tab "Skills"'):
        page.get_by_text("Skills", exact=True).first.click()
        page.wait_for_timeout(settings.SETTLE_MS // 3)

    assert page.locator('[role="dialog"]').count() == dialogs_before, (
        "the Skills picker opened a dialog; it is supposed to render inline"
    )
    expect(page.locator(L.AGENT_NAME)).to_be_visible()


@pytest.mark.scenario("S-04-12")
@pytest.mark.parametrize("label", L.SWITCHES)
def test_each_capability_toggle_flips_independently(page, shot, label):
    """Scenario: Each capability toggle flips independently"""
    open_composer(page, "/workflows/new", nodes=0)
    before = {name: L.switch(page, name).get_attribute("aria-checked") for name in L.SWITCHES}

    with shot(f"toggle-{label.split()[0].lower()}", f'When I toggle "{label}"'):
        L.switch(page, label).click()
        # React batches clicks fired together and keeps only the last, so a
        # toggle test must click one at a time and let it settle.
        page.wait_for_timeout(500)

    after = {name: L.switch(page, name).get_attribute("aria-checked") for name in L.SWITCHES}
    assert after[label] != before[label], f"{label} did not flip"
    for name in L.SWITCHES:
        if name != label:
            assert after[name] == before[name], f"toggling {label} also moved {name}"


@pytest.mark.scenario("S-04-13")
@pytest.mark.parametrize(("strategy", "helper"), list(L.STRATEGY_HELPERS.items()))
def test_choosing_a_deliverable_strategy_reveals_its_own_fields(page, shot, strategy, helper):
    """Scenario: Choosing a deliverable strategy reveals its own fields"""
    open_composer(page, "/workflows/new", nodes=0)

    with shot(f"strategy-{strategy.split()[0].lower()}", f'When I select "{strategy}"'):
        page.locator(L.DELIVERABLE_STRATEGY).select_option(L.STRATEGY_VALUES[strategy])
        page.wait_for_timeout(settings.SETTLE_MS // 4)

    expect(page.get_by_text(helper).first).to_be_visible()


@pytest.mark.scenario("S-04-14")
@pytest.mark.defect
def test_run_is_gated_on_a_long_enough_brief(page, shot):
    """Scenario: Run is gated on a long-enough brief

    Asserts TODAY'S behaviour, which is weaker than the spec's — D-29. `Run
    once` is NOT `disabled` while the brief is too short; it stays clickable and
    carries `title="Add a brief first"`. The hint below the field is the only
    thing that says so, and a title attribute is invisible to a keyboard or
    screen-reader user until they have already pressed it.
    """
    with shot("run-gated", 'When I cold-load "/workflows/new"'):
        open_composer(page, "/workflows/new", nodes=0)

    run_once = page.locator(L.RUN_ONCE)
    expect(page.get_by_text(L.RUN_GATE_HINT)).to_be_visible()
    assert run_once.get_attribute("title") == L.RUN_GATE_TITLE
    assert not run_once.is_disabled(), (
        "Run once is disabled now — D-29 is fixed; assert to_be_disabled() here "
        "and delete the defect marker"
    )

    with shot("run-enabled", "When I type a brief of at least 3 characters"):
        page.fill(L.BRIEF, "hello world")
        page.wait_for_timeout(settings.SETTLE_MS // 4)

    expect(page.get_by_text(L.RUN_GATE_HINT)).to_have_count(0)
    expect(run_once).to_be_enabled()


@pytest.mark.scenario("S-04-15")
def test_a_last_streamed_built_in_refuses_an_append_after_final_step_slot(page, shot):
    """Scenario: A last-streamed built-in refuses an append-after-final-step slot"""
    with shot("last-step-guard", 'When I cold-load "/workflows/ppt/canvas"'):
        open_composer(page, "/workflows/ppt/canvas", nodes=len(L.PPT_AGENT_IDS))

    expect(page.get_by_text(L.LAST_STEP_GUARD)).to_be_visible()
    # The last node offers no "move later" target beyond itself: appending after
    # it would silently replace output.md.
    last = L.node_order(page)[-1]
    expect(page.locator(L.move_later(last))).to_be_disabled()


@pytest.mark.scenario("S-04-16")
@pytest.mark.defect
def test_a_ppt_based_overrides_editor_calls_itself_custom(page, shot):
    """Scenario: A ppt-based override's editor calls itself CUSTOM

    Asserts TODAY'S behaviour — ISS-183. `ComposerPage` hardcodes
    `base_pipeline_type` to "custom", because `workflowType` is a shared mutable
    other screens set and trusting it here once persisted a stale type as a
    saved workflow's permanent base.
    """
    with shot("override-header", 'When I cold-load "/workflows/{id}/edit"'):
        open_override_editor(page)

    expect(page.get_by_text("CUSTOM · COMPOSER")).to_be_visible()
    expect(page.get_by_text("PRESENTATION · COMPOSER")).to_have_count(0)


# ── the writes ───────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-04-17")
@pytest.mark.destructive
def test_saving_a_copy_of_a_built_in_creates_a_new_row_and_leaves_the_original_alone(page, shot):
    """Scenario: Saving a copy of a built-in creates a new row and leaves the original alone

    Deletes the copy afterwards, so the saved-workflow count ends where it
    began.
    """
    name = "E2E S-04-17 copy"
    original = open_composer(page, "/workflows/ppt/canvas", nodes=len(L.PPT_AGENT_IDS))

    try:
        with shot("save-as-copy", 'When I rename the workflow and click "Save as copy"'):
            page.fill(L.WORKFLOW_NAME, name)
            page.click(L.SAVE_AS_COPY)
            page.wait_for_timeout(settings.SETTLE_MS)

        page.goto("/workflows")
        expect(page.locator(W.CARD).first).to_be_visible()
        assert W.card(page, name).count() == 1, "the copy was not saved"

        with shot("built-in-untouched", "Then the built-in still shows its own steps"):
            after = open_composer(page, "/workflows/ppt/canvas", nodes=len(L.PPT_AGENT_IDS))

        assert after == original
        expect(page.locator(L.SAVE_AS_COPY)).to_be_visible()
    finally:
        page.goto("/workflows")
        if W.card(page, name).count():
            W.card(page, name).locator(W.ACTIONS).click()
            page.get_by_role("menuitem", name="Delete").click()
            page.get_by_role("button", name="Delete", exact=True).last.click()
            page.wait_for_timeout(settings.SETTLE_MS // 2)


@pytest.mark.scenario("S-04-18")
def test_the_blank_custom_agent_template_is_withheld_when_authoring_an_override(page, shot):
    """Scenario: The blank custom-agent template is withheld when authoring an override

    FIX-306. A blank custom agent mints a dynamic id with no AGENT.md on disk,
    so such an override saves and renders and then 400s with `invalid_agent_ids`
    on every launch. Withholding the template is the guard.

    Noted while checking it: the template is not offered on `/workflows/new`
    either, so the guard is broader than FIX-306 describes. This asserts the
    scenario's own claim — the override — rather than the contrast the spec
    expected to be able to draw.
    """
    with shot("override-add-agent", "When I open the add-agent panel on an override"):
        open_override_editor(page)
        page.locator(L.ADD_AGENT).first.click()
        page.wait_for_timeout(settings.SETTLE_MS)

    expect(page.get_by_text("Custom Agent", exact=True)).to_have_count(0)


@pytest.mark.scenario("S-04-19")
@pytest.mark.live
@pytest.mark.destructive
@pytest.mark.skip(reason="dispatches a real run; belongs to the live tier")
def test_a_saved_composition_can_be_launched_from_the_composer(page, shot):
    """Scenario: A saved composition can be launched from the composer"""


@pytest.mark.issue("ISS-275")
def test_back_button_confirms_before_discarding_unsaved_work(page, shot):
    """ISS-275 — the composer's own Back control must warn before it discards
    unsaved name+agent state.

    `handleBackNav` (DashboardLayout.tsx) is wired to `ComposerPage`'s Back
    button with no dirty-check, so today it navigates away silently. The
    correct behaviour is a confirmation (native `confirm()` or an in-app
    dialog) before any unsaved work is thrown away.
    """
    open_composer(page, "/workflows/new", nodes=0)

    with shot("unsaved-draft", "When I name a workflow and add an agent, unsaved"):
        page.fill(L.WORKFLOW_NAME, "Unsaved Draft ISS-275")
        page.locator(L.ADD_AGENT).first.click()
        expect(page.locator(L.ADD_TO_PLAN).first).to_be_visible(timeout=15000)
        page.locator(L.ADD_TO_PLAN).first.click()
        L.wait_for_nodes(page, 1)

    assert L.agent_count(page) == 1

    dialog_seen = {"fired": False}

    def on_dialog(dialog):
        dialog_seen["fired"] = True
        dialog.dismiss()

    page.on("dialog", on_dialog)

    with shot("back-with-unsaved-work", 'When I click "Back" with unsaved work present'):
        page.click(L.BACK)
        page.wait_for_timeout(settings.SETTLE_MS)

    assert dialog_seen["fired"], (
        "Back discarded the unsaved workflow name and agent with no "
        "confirmation dialog of any kind"
    )
