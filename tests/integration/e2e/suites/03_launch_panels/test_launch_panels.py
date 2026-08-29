"""Implements ../../../screens/03-launch-panels.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

Two shells reach the same launch — the wizard (`/create/ppt`,
`/create/prototype`) and the simple panel (everything else). The simple panel
carries no testids, so its controls are matched on visible text.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from framework.locators import launch_panels as L
from framework.locators import composer as C


def agent_count(page) -> int:
    """The number in the `Advanced <N> agents` label.

    The roster loads asynchronously and the control renders "Advanced 0 agents"
    until it arrives, so wait for a non-zero count first. Reading it immediately
    yields 0 and then fails against the canvas, which reports the real roster —
    a race that looks exactly like a product bug.
    """
    expect(page.locator(L.ADVANCED)).to_contain_text(
        re.compile(r"[1-9]\d*\s*agents"), timeout=15_000
    )
    # The label is "Advanced\n<N> agents" — a newline, not a space.
    label = page.locator(L.ADVANCED).inner_text()
    m = re.search(r"(\d+)\s*agents", label)
    assert m, f"Advanced control has no count in its label: {label!r}"
    return int(m.group(1))


def loaded_tiles(page) -> int:
    """Tile count, once the gallery has actually rendered.

    Every gallery assertion needs this: the wizard's heading, pills and search
    paint before the templates arrive, so an immediate count is 0 and any
    before/after comparison silently compares nothing.
    """
    expect(page.locator(L.TEMPLATE_TILE).first).to_be_visible(timeout=20_000)
    return page.locator(L.TEMPLATE_TILE).count()


# ── shell A: the wizard ──────────────────────────────────────────────────────


@pytest.mark.scenario("S-03-01")
def test_the_presentation_wizard_renders_its_template_gallery(page, shot):
    """Scenario: The presentation wizard renders its template gallery"""
    with shot("ppt-wizard", 'When I cold-load "/create/ppt"'):
        page.goto("/create/ppt")
        expect(page.get_by_text(L.PPT_HEADING)).to_be_visible()

    expect(page.locator(L.BRIEF)).to_be_visible()
    expect(page.locator(L.TAB_TEMPLATE)).to_be_visible()
    expect(page.locator(L.PPT_SEARCH)).to_be_visible()

    with shot("categories", "And I see every category pill"):
        for name in L.PPT_CATEGORIES:
            expect(page.locator(L.category_pill(name))).to_be_visible()

    # The gallery is not empty — a wizard whose gallery fails to load still
    # renders its pills and search, and would pass everything above.
    assert loaded_tiles(page) > 0, "the template gallery rendered no tiles"


@pytest.mark.scenario("S-03-02")
def test_filtering_the_template_gallery_by_category_narrows_it(page, shot):
    """Scenario: Filtering the template gallery by category narrows it"""
    page.goto("/create/ppt")
    expect(page.get_by_text(L.PPT_HEADING)).to_be_visible()
    before = loaded_tiles(page)

    with shot("minimal-only", 'When I click the category pill "Minimal"'):
        page.click(L.category_pill("Minimal"))
        # Poll rather than read once: filtering is client-side and the count
        # changes a frame after the click.
        expect(page.locator(L.TEMPLATE_TILE)).not_to_have_count(before)

    after = page.locator(L.TEMPLATE_TILE).count()
    assert 0 < after < before, f"Minimal showed {after} of {before} tiles"


@pytest.mark.scenario("S-03-03")
def test_searching_templates_filters_by_name(page, shot):
    """Scenario: Searching templates filters by name"""
    page.goto("/create/ppt")
    expect(page.get_by_text(L.PPT_HEADING)).to_be_visible()
    before = loaded_tiles(page)

    with shot("search-keynote", 'When I type "keynote" into the template search'):
        page.fill(L.PPT_SEARCH, "keynote")
        expect(page.locator(L.TEMPLATE_TILE)).not_to_have_count(before)

    names = [n.replace("\n", " ") for n in page.locator(L.TEMPLATE_TILE).all_inner_texts()]
    assert names, "searching for a known template name returned nothing"
    assert len(names) < before, f"search did not narrow the gallery ({len(names)} of {before})"

    # CORRECTION to the spec. It claimed "every visible tile's NAME contains the
    # term". It does not: "keynote" also returns "Neo Grid Bold" and "Atelier
    # Brand Deck", so the field searches description or tags too. Asserting the
    # spec's version would fail against correct behaviour.
    #
    # What is worth pinning is that the search NARROWS and that an obvious match
    # survives it — a search returning everything, or dropping the very template
    # whose name you typed, are both real regressions.
    assert any("keynote" in n.lower() for n in names), (
        f"searching 'keynote' dropped every name containing it: {names}"
    )


@pytest.mark.scenario("S-03-04")
def test_the_prototype_wizard_offers_three_tabs_and_a_blank_canvas_option(page, shot):
    """Scenario: The prototype wizard offers three tabs and a blank-canvas option"""
    with shot("prototype-wizard", 'When I cold-load "/create/prototype"'):
        page.goto("/create/prototype")
        expect(page.locator(L.TAB_TEMPLATE)).to_be_visible()
        expect(page.locator(L.TAB_DESIGN_SYSTEM)).to_be_visible()
        expect(page.locator(L.TAB_DISCOVERY)).to_be_visible()

    with shot("blank-canvas", 'And a "No template" tile tagged BLANK CANVAS'):
        expect(page.get_by_text("BLANK CANVAS").first).to_be_visible()

    # The prototype wizard ships with one review gate pre-set, unlike the simple
    # panel which starts at "no gates".
    expect(page.locator(L.REVIEW_GATES)).to_contain_text(re.compile(r"1 agent|pause for review"))


@pytest.mark.scenario("S-03-05")
def test_the_prototype_template_search_uses_its_own_field_name(page, shot):
    """Scenario: The prototype template search uses its own field name"""
    with shot("prototype-search", "Then a search input named template-search exists"):
        page.goto("/create/prototype")
        expect(page.locator(L.PROTOTYPE_SEARCH)).to_be_visible()

    # These two wizards do NOT share a search selector. Pinned here so a phase-2
    # page object cannot quietly unify them and silently break one.
    expect(page.locator(L.PPT_SEARCH)).to_have_count(0)


@pytest.mark.scenario("S-03-06")
@pytest.mark.parametrize(
    ("tab", "shown"),
    [
        ("Template", L.TAB_TEMPLATE),
        ("Design System", L.TAB_DESIGN_SYSTEM),
        ("Discovery", L.TAB_DISCOVERY),
    ],
)
def test_each_wizard_tab_reveals_its_own_panel(page, shot, tab, shown):
    """Scenario Outline: Each wizard tab reveals its own panel"""
    page.goto("/create/prototype")
    expect(page.locator(L.TAB_TEMPLATE)).to_be_visible()

    with shot(f"tab-{tab}", f'When I click the tab "{tab}"'):
        page.click(shown)
        # Selection is carried on aria-selected, so assert the ARIA state rather
        # than a class: a styling change must not fail this, a broken tab must.
        expect(page.locator(shown)).to_have_attribute("aria-selected", "true")

    others = {L.TAB_TEMPLATE, L.TAB_DESIGN_SYSTEM, L.TAB_DISCOVERY} - {shown}
    for other in others:
        expect(page.locator(other)).to_have_attribute("aria-selected", "false")


# ── shell B: the simple launch panel ─────────────────────────────────────────


@pytest.mark.scenario("S-03-07")
def test_the_user_stories_panel_names_its_own_workflow(page, shot):
    """Scenario: The user-stories panel names its own workflow"""
    with shot("user-stories-panel", 'When I cold-load "/create/user-stories"'):
        page.goto("/create/user-stories")
        expect(page.get_by_text(L.SIMPLE_HEADING)).to_be_visible()

    expect(page.locator(L.ADVANCED)).to_contain_text("7 agents")
    for control in (L.SAVE_WORKFLOW, L.SAVE_AS_MY_VERSION, L.RUN_WORKFLOW):
        expect(page.locator(control)).to_be_visible()


@pytest.mark.scenario("S-03-08")
def test_a_catalog_workflow_cold_loads_onto_the_right_panel(page, shot):
    """Scenario: A catalog workflow cold-loads onto the right panel"""
    # This is the create-workflow branch of parseViewPath, which carries the raw
    # pipelineType through initialWorkflowTypeFor. It is the ONLY create route
    # that resolves its type correctly on a cold load — see S-03-09.
    with shot("branch-by-language", 'When I cold-load "/create/ex_A2_branch"'):
        page.goto("/create/ex_A2_branch")
        expect(page.get_by_text(L.SIMPLE_HEADING)).to_be_visible()

    assert agent_count(page) == 5, (
        f"ex_A2_branch should show 5 agents, showed {agent_count(page)} — "
        "the cold-load type resolution has changed"
    )


@pytest.mark.scenario("S-03-09")
@pytest.mark.defect
def test_cold_loading_create_app_shows_the_user_stories_panel(page, shot):
    """Scenario: Cold-loading /create/app shows the user-stories panel"""
    # D-01, asserted AS-IS. /create/app is supposed to launch app_builder. It
    # renders the user_stories panel instead, because initialWorkflowTypeFor
    # returns a type only for `create-workflow`, so the two hand-written screens
    # reach the panel with no type and fall back to the default.
    #
    # When it is fixed this test turns red, which is the point: the eyebrow
    # should read BUILD AN END-TO-END APPLICATION and the count should be 1.
    with shot("create-app", 'When I cold-load "/create/app"'):
        page.goto("/create/app")
        expect(page.get_by_text(L.SIMPLE_HEADING)).to_be_visible()

    assert agent_count(page) == 7, (
        "D-01 appears to be FIXED — /create/app no longer shows the user_stories "
        "roster. Rewrite this scenario to assert the correct behaviour and drop "
        "the @defect tag."
    )


# ── shared behaviour ─────────────────────────────────────────────────────────


@pytest.mark.scenario("S-03-10")
def test_run_is_disabled_until_the_brief_is_long_enough(page, shot):
    """Scenario: Run is disabled until the brief is long enough"""
    with shot("empty-brief", 'Then "Run workflow" is disabled'):
        page.goto("/create/user-stories")
        expect(page.locator(L.RUN_WORKFLOW)).to_be_disabled()

    with shot("brief-typed", "When I type a brief"):
        page.fill(L.BRIEF, "Build a hello world service")
        expect(page.locator(L.RUN_WORKFLOW)).to_be_enabled()


@pytest.mark.scenario("S-03-11")
def test_the_advanced_control_opens_the_agent_roster(page, shot):
    """Scenario: The Advanced control opens the agent roster"""
    page.goto("/create/user-stories")
    expect(page.get_by_text(L.SIMPLE_HEADING)).to_be_visible()
    claimed = agent_count(page)

    with shot("roster-open", 'When I click "Advanced 7 agents"'):
        page.click(L.ADVANCED)
        expect(page.get_by_text(L.ADVANCED_HEADING)).to_be_visible()
        expect(page.locator(L.CANVAS_VIEW)).to_be_visible()

    # The label must EQUAL the roster it opens, not merely be near it. A control
    # advertising a count it does not deliver is D-05's shape.
    nodes = page.locator(L.CANVAS_NODE).count()
    assert nodes == claimed, (
        f"Advanced says {claimed} agents but the canvas renders {nodes} nodes"
    )

    # D-22, asserted AS-IS. The spec says Escape closes this modal. It does not:
    # the overlay is `fixed inset-0 z-50` and swallows the key, so the roster
    # stays open. Pinned so that fixing it turns this red rather than passing
    # silently — and because 20-keyboard-and-navigation's Escape matrix claims
    # every overlay is dismissable that way.
    with shot("escape-ignored", "When I press Escape the modal does NOT close"):
        page.keyboard.press("Escape")
        expect(page.locator(L.CANVAS_VIEW)).to_have_count(1)

    with shot("roster-closed", 'When I click "Cancel" then the modal closes'):
        page.click(L.CANVAS_CANCEL)
        expect(page.locator(L.CANVAS_VIEW)).to_have_count(0)


@pytest.mark.scenario("S-03-12")
def test_review_gates_can_be_set_before_launch(page, shot):
    """Scenario: Review gates can be set before launch"""
    with shot("no-gates", 'Then the review-gates control reads "no gates"'):
        page.goto("/create/user-stories")
        expect(page.locator(L.REVIEW_GATES)).to_contain_text("no gates")

    with shot("gates-open", "When I open the review-gates control"):
        page.click(L.REVIEW_GATES)
        expect(page.get_by_text("Review gates")).to_be_visible()


@pytest.mark.scenario("S-03-13")
def test_attaching_a_file_is_offered_on_every_launch_panel(page, shot):
    """Scenario: Attaching a file is offered on every launch panel"""
    with shot("attach-offered", 'Then I see "+ Attach file"'):
        page.goto("/create/user-stories")
        expect(page.locator(L.ATTACH_FILE)).to_be_visible()

    # The visible affordance is a button; the real input is hidden behind it.
    # Assert the input exists, or the button is decoration.
    assert page.locator(L.FILE_INPUT).count() > 0, (
        '"+ Attach file" is shown but there is no file input behind it'
    )


@pytest.mark.scenario("S-03-14")
@pytest.mark.destructive
@pytest.mark.live
@pytest.mark.timeout(600)
def test_launching_a_run_navigates_to_its_live_surface(page, shot):
    """Scenario: Launching a run navigates to its live surface"""
    # FIX-302's regression guard: a freshly launched run must not render as
    # "USER STORIES" when it is something else. Launched as ppt deliberately —
    # the bug only showed on a non-default type.
    with shot("brief-typed", "Given a disposable brief"):
        page.goto("/create/ppt")
        expect(page.get_by_text(L.PPT_HEADING)).to_be_visible()
        page.fill(L.BRIEF, "One slide saying hello. Nothing else.")
        expect(page.locator(L.RUN_WORKFLOW)).to_be_enabled()

    with shot("launched", 'When I click "Run workflow"'):
        page.click(L.RUN_WORKFLOW)
        expect(page).to_have_url(re.compile(r"/runs/[^/]+"), timeout=60_000)

    with shot("run-surface", "Then the header names the workflow I launched"):
        expect(page.get_by_text(re.compile(r"PPT|PRESENTATION|Pitch", re.I)).first).to_be_visible()

    assert not re.search(r"USER[ _]STORIES", page.content(), re.I), (
        "FIX-302 regression: a ppt run is rendering as USER STORIES"
    )


@pytest.mark.scenario("S-03-15")
@pytest.mark.destructive
def test_save_as_my_version_creates_a_user_override_of_a_built_in(page, shot):
    """Scenario: Save as my version creates a user override of a built-in"""
    # Spec 016. Only the STEPS are the user's — deliverable, context providers,
    # planner, clarify and limits always come from the file manifest.
    with shot("panel", 'When I cold-load "/create/user-stories"'):
        page.goto("/create/user-stories")
        expect(page.locator(L.SAVE_AS_MY_VERSION)).to_be_visible()

    with shot("saved", 'And I click "Save as my version"'):
        page.click(L.SAVE_AS_MY_VERSION)
        # Either a toast, a rename affordance, or a revert control appears — the
        # panel must acknowledge the save somehow rather than silently no-op.
        expect(
            page.get_by_text(re.compile(r"saved|my version|revert|original", re.I)).first
        ).to_be_visible(timeout=15_000)


@pytest.mark.issue("ISS-247")
def test_checking_a_review_gate_sets_that_agents_gate_in_the_advanced_modal(page, shot):
    """ISS-247 — checking an agent in the "Review gates" checklist must be
    reflected as that same agent's Gate in the Advanced modal's Config tab.

    ReviewGatesSection writes a separate `gateAgentIds` ref; CanvasConfigRail's
    Gate combobox reads only `agent.gates`. The two never sync.
    """
    with shot("fresh", 'Given a fresh "/create/app" load'):
        page.goto("/create/app")
        expect(page.locator(L.REVIEW_GATES)).to_contain_text("no gates")

    with shot("checked", 'When I check "Domain Discovery Agent" in Review gates'):
        page.click(L.REVIEW_GATES)
        page.get_by_text("Domain Discovery Agent", exact=True).click()
        expect(page.locator(L.REVIEW_GATES)).to_contain_text("1 agent")
        page.keyboard.press("Escape")

    with shot("advanced-config", 'Then its Advanced modal Gate combobox is not "No gate"'):
        page.click(L.ADVANCED)
        page.click(C.node("domain-analyst"))
        page.get_by_text("Config", exact=True).first.click()
        gate = page.locator('select[aria-label="Gate"]')
        expect(gate).to_be_visible()
        assert gate.input_value() != "", (
            "Review gates checklist marked Domain Discovery Agent as gated, but "
            "the Advanced modal's Config tab still shows Gate = 'No gate'"
        )


@pytest.mark.issue("ISS-306")
def test_seeded_before_human_gate_shows_in_review_gates_checklist_on_fresh_load(page, shot):
    """ISS-306 — a manifest-seeded before-human gate must be visible in the
    "Review gates" checklist on a completely fresh load, zero interaction.

    /create/ex_A4_human_gate's "Pick Language" step declares
    gates: [before-human, conditional] server-side, but ReviewGatesSection's
    checkedIds seed never reads a custom-agent step's manifest gates — only a
    saved run's initialGateIds or a static per-AGENT.md `gate` field, neither
    of which this fixture has. The pill reads "no gates" instead.
    """
    with shot("fresh", 'Given a fresh "/create/ex_A4_human_gate" load'):
        page.goto("/create/ex_A4_human_gate")
        expect(page.locator(L.REVIEW_GATES)).to_be_visible()

    with shot("checklist", 'Then "Pick Language" is checked in Review gates'):
        page.click(L.REVIEW_GATES)
        assert page.get_by_role("checkbox", name="Pick Language").is_checked(), (
            "manifest declares Pick Language gates: [before-human, conditional], "
            "but the Review gates checklist shows it unchecked on fresh load"
        )


@pytest.mark.issue("ISS-306")
def test_seeded_before_human_gate_activates_prompt_user_toggle_on_fresh_load(page, shot):
    """ISS-306 — the "Prompt User" toggle, the control built to represent a
    before-human gate, must be active for a step carrying one on fresh load.

    normaliseRoute() maps outcomes[*].target/default_next through nodeIdOf but
    never route.condition_agent itself, so the bare manifest value ("ask")
    never equals the normalized comparison id ("custom-agent:ask") and
    promptUser is always false, even though the manifest genuinely declares
    condition_agent: ask and gates: [before-human, ...] for this step.
    """
    with shot("fresh", 'Given a fresh "/create/ex_A4_human_gate" load'):
        page.goto("/create/ex_A4_human_gate")

    with shot("config", 'When I open the Advanced modal on "Pick Language"'):
        page.click(L.ADVANCED)
        page.click(C.node("custom-agent:pick-language"))
        page.get_by_role("tab", name="Config").click()

    with shot("prompt-user", 'Then "Prompt User" is on'):
        toggle = C.switch(page, "Prompt User")
        expect(toggle).to_be_visible()
        assert toggle.get_attribute("aria-checked") == "true", (
            "Pick Language declares gates: [before-human, ...] and "
            "route.condition_agent: ask, but the Prompt User toggle — the "
            "control meant to represent before-human — is off on fresh load"
        )
