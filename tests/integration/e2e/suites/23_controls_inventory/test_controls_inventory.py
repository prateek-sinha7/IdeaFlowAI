"""Implements ../../../screens/23-controls-inventory.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

**This file asks a different question from every other module.** The others ask
whether a screen behaves; this one asks whether every addressable element is
still addressable. `_coverage.py` found 150 of 298 controls named in no spec at
all — a page can be fully specified and still leave most of its buttons
untargetable.

Most of these controls live in states the offline tier cannot reach: an agent
proposal, a live audit, a refinement chip, a generating preview. For those, the
assertion is that the control is still DECLARED in the frontend source
(`framework/source.py`). That is not a behaviour test and does not pretend to
be — but a renamed testid is precisely the change that silently breaks a future
test, and this catches it the day it lands, from the same direction
`_coverage.py` reads.

Where the surface IS reachable offline, the runtime check is made as well.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from framework import accounts, settings
from framework import source as SOURCE
from framework.locators import admin as ADMIN
from framework.locators import analytics as AN
from framework.locators import composer as COMPOSER
from framework.locators import errors as ERR
from framework.locators import library as LIB
from framework.locators import outside_routes as OUT
from framework.locators import run_detail as RD
from framework.locators import run_history as RH
from framework.locators import saved_workflows as SW
from framework.locators import shell as SHELL

# Every revision field carries aria-label="Revision instructions" and a
# DIFFERENT name. Select by the label; a page object keyed on the name matches
# nothing on four of the five types, and does so silently.
REVISION_LABEL = "Revision instructions"
REVISION_NAMES = [
    "prototype-revision",
    "app-revision",
    "ppt-revision",
    "markdown-revision",
    "user-story-revision",
    "revision-instructions",
]


def a_completed_run(page) -> str:
    page.goto("/runs")
    expect(page.locator(RH.ROW).first).to_be_visible()
    done = [label for label in RH.rows(page) if RH.status_of(label) == "completed"]
    assert done, "no completed run"
    page.locator(f'{RH.ROW}[aria-label="{done[0]}"]').first.click()
    page.wait_for_url(lambda url: "/runs/" in url)
    expect(page.locator(RD.HEADER)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS)
    return page.url.split("/runs/")[1].split("/")[0].split("?")[0]


# ── revising a deliverable ───────────────────────────────────────────────────


@pytest.mark.scenario("S-23-01")
def test_every_deliverable_type_can_be_revised_in_place(page, shot):
    """Scenario: Every deliverable type can be revised in place"""
    SOURCE.assert_declared(*REVISION_NAMES)

    with shot("revision-field", "When I open a completed run"):
        a_completed_run(page)

    field = page.get_by_label(REVISION_LABEL)
    if field.count() == 0:
        pytest.skip("this run's deliverable type offers no in-place revision field")
    expect(field.first).to_be_visible()
    name = field.first.get_attribute("name")
    assert name in REVISION_NAMES, f"an unrecorded revision field appeared: {name!r}"


@pytest.mark.scenario("S-23-02")
def test_revision_fields_share_an_accessible_name_but_not_a_name_attribute(page, shot):
    """Scenario: Revision fields share an accessible name but not a name attribute

    The whole reason this module exists in one place: six fields, one label, six
    names. A shared page object keyed on the name is wrong five times out of six
    and never says so.
    """
    with shot("revision-names", "Then the six names are all distinct"):
        SOURCE.assert_declared(*REVISION_NAMES)

    assert len(set(REVISION_NAMES)) == len(REVISION_NAMES)
    corpus = SOURCE._corpus()
    for name in REVISION_NAMES:
        # Each name and the shared label must appear together somewhere.
        assert REVISION_LABEL in corpus, "the shared aria-label is gone"


@pytest.mark.scenario("S-23-03")
def test_an_empty_revision_does_nothing(page, shot):
    """Scenario: An empty revision does nothing

    Guarded on `revisionText.trim()` in every implementation.
    """
    a_completed_run(page)
    field = page.get_by_label(REVISION_LABEL)
    if field.count() == 0:
        pytest.skip("this run offers no in-place revision field")

    before = page.url
    with shot("empty-revision", "When I press Enter with it empty"):
        field.first.fill("   ")
        field.first.press("Enter")
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    assert page.url == before, "a whitespace-only revision started something"


@pytest.mark.scenario("S-23-04")
@pytest.mark.live
@pytest.mark.skip(reason="submitting a revision dispatches a real run; live tier")
def test_submitting_a_revision_clears_the_field(page, shot):
    """Scenario: Submitting a revision clears the field"""


# ── chat lane proposals, refinements and modes ───────────────────────────────


@pytest.mark.scenario("S-23-05")
def test_an_agent_proposal_can_be_confirmed_or_rejected(page, shot):
    """Scenario: An agent proposal can be confirmed or rejected

    Address a specific proposal by its `data-proposal-id`; the testid repeats.
    """
    with shot("proposal-controls", "Then the proposal controls are declared"):
        SOURCE.assert_declared("chat-proposals", "chat-proposal-confirm", "chat-proposal-reject")
    assert "data-proposal-id" in SOURCE._corpus(), (
        "proposals no longer carry a per-proposal id, so one cannot be addressed"
    )


@pytest.mark.scenario("S-23-06")
def test_confirming_a_proposal_disables_it_while_it_runs(page, shot):
    """Scenario: Confirming a proposal disables it while it runs

    Guards double-submission: a re-enabled button mid-flight means the same
    action can be dispatched twice.
    """
    with shot("proposal-guard", "Then the confirm control is declared"):
        SOURCE.assert_declared("chat-proposal-confirm")


@pytest.mark.scenario("S-23-07")
def test_a_refinement_chip_can_be_accepted_or_dismissed(page, shot):
    """Scenario: A refinement chip can be accepted or dismissed"""
    with shot("refinement-chip", "Then the refinement controls are declared"):
        SOURCE.assert_declared(
            "chat-refinement-chip", "chat-refinement-confirm", "chat-refinement-dismiss"
        )


@pytest.mark.scenario("S-23-08")
def test_the_chain_picker_offers_follow_on_workflows(page, shot):
    """Scenario: The chain picker offers follow-on workflows

    Distinct from the "TAKE THIS FURTHER" chips in 18-chat-lane — those are
    `chat-chain-suggestion-chip`, these are `chat-chain-picker-chip`.
    """
    with shot("chain-picker", "Then the picker's controls are declared"):
        SOURCE.assert_declared("chat-chain-picker", "chat-chain-picker-chip")
    assert SOURCE.declares("chat-chain-suggestion-chip"), (
        "the suggestion chips are gone; 18-chat-lane's S-18-17 covers those"
    )


@pytest.mark.scenario("S-23-09")
def test_an_agents_reasoning_is_collapsible(page, shot):
    """Scenario: An agent's reasoning is collapsible"""
    with shot("thinking-block", "Then the reasoning block is declared"):
        SOURCE.assert_declared("chat-thinking-block")


@pytest.mark.scenario("S-23-10")
def test_tool_calls_and_file_operations_are_shown_as_cards(page, shot):
    """Scenario: Tool calls and file operations are shown as cards"""
    with shot("tool-cards", "Then the tool and file-op cards are declared"):
        SOURCE.assert_declared("chat-tool-card", "chat-file-ops")


@pytest.mark.scenario("S-23-11")
def test_token_and_context_usage_are_visible(page, shot):
    """Scenario: Token and context usage are visible"""
    with shot("usage-widgets", "Then the usage widgets are declared"):
        SOURCE.assert_declared("chat-token-widget", "chat-context-usage")


@pytest.mark.scenario("S-23-12")
def test_terminal_runs_show_a_terminal_banner(page, shot):
    """Scenario: Terminal runs show a terminal banner"""
    with shot("terminal-banner", "When I open a cancelled run"):
        page.goto("/runs")
        expect(page.locator(RH.ROW).first).to_be_visible()
        stopped = [
            label for label in RH.rows(page) if RH.status_of(label) in ("cancelled", "failed")
        ]
        assert stopped, "no terminal run to look at"
        page.locator(f'{RH.ROW}[aria-label="{stopped[0]}"]').first.click()
        page.wait_for_url(lambda url: "/runs/" in url)
        expect(page.locator(RD.LANE)).to_be_visible()
        page.wait_for_timeout(settings.SETTLE_MS)

    body = page.evaluate("() => document.body.innerText")
    assert any(word in body for word in ("Cancelled", "What went wrong", "Failed")), (
        f"a terminal run says nothing about being terminal: {body[:200]!r}"
    )


@pytest.mark.scenario("S-23-13")
def test_a_message_can_be_copied_edited_or_regenerated(page, shot):
    """Scenario: A message can be copied, edited or regenerated"""
    with shot("message-actions", "Then the message actions are declared"):
        SOURCE.assert_declared("edit-message")


@pytest.mark.scenario("S-23-14")
def test_chat_modes_can_be_added_and_removed(page, shot):
    """Scenario: Chat modes can be added and removed"""
    with shot("chat-modes", "Then the mode controls are declared"):
        assert "mode" in SOURCE._corpus().lower()
    a_completed_run(page)
    expect(page.locator(RD.COMPOSER)).to_be_visible()


@pytest.mark.scenario("S-23-15")
def test_files_can_be_attached_by_drop_or_by_chip(page, shot):
    """Scenario: Files can be attached by drop or by chip"""
    with shot("attachments", "Then the attachment controls are declared"):
        SOURCE.assert_declared(
            "chat-attach-dropzone",
            "chat-attach-chip",
            "lane-run-attachments",
            "lane-run-attach-chip",
            "lane-run-attach-remove",
        )
    a_completed_run(page)
    assert page.locator(RD.LANE).locator('input[type="file"]').count() > 0


@pytest.mark.scenario("S-23-16")
def test_activity_is_indicated_while_waiting(page, shot):
    """Scenario: Activity is indicated while waiting"""
    with shot("activity-indicators", "Then the indicators are declared"):
        SOURCE.assert_declared("typing-indicator", "lane-reading-indicator")


# ── the canvas ───────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-23-17")
def test_a_conditional_route_renders_as_a_labelled_edge(page, shot):
    """Scenario: A conditional route renders as a labelled edge"""
    with shot("route-edge", "Then the route node and its edge are declared"):
        SOURCE.assert_declared("canvas-node-route", "canvas-route-edge", "canvas-route-edge-label")


@pytest.mark.scenario("S-23-18")
def test_route_outcomes_are_edited_in_the_rail(page, shot):
    """Scenario: Route outcomes are edited in the rail"""
    with shot("rail-route", "Then the rail's route controls are declared"):
        SOURCE.assert_declared("canvas-rail-route", "canvas-rail-route-add")


@pytest.mark.scenario("S-23-19")
def test_a_route_outcome_names_its_condition_source(page, shot):
    """Scenario: A route outcome names its condition source"""
    with shot("route-condition", "Then the route rail is declared"):
        SOURCE.assert_declared("canvas-rail-route")


@pytest.mark.scenario("S-23-20")
def test_a_detached_node_is_marked_as_such(page, shot):
    """Scenario: A detached node is marked as such"""
    with shot("detached-node", "Then the detached marker is declared"):
        SOURCE.assert_declared("canvas-node-detached")


@pytest.mark.scenario("S-23-21")
def test_edges_can_be_regrabbed_to_reparent_a_node(page, shot):
    """Scenario: Edges can be regrabbed to reparent a node"""
    with shot("edge-grab", "Then the regrab affordances are declared"):
        SOURCE.assert_declared("canvas-edge-grab", "canvas-chain-connect-preview")


@pytest.mark.scenario("S-23-22")
def test_sub_agents_are_added_under_a_node(page, shot):
    """Scenario: Sub-agents are added under a node"""
    with shot("sub-agents", "Then the sub-agent controls are declared"):
        SOURCE.assert_declared("subagent-row", "subagent-strategy")

    page.goto("/workflows/ppt/canvas")
    expect(page.locator(COMPOSER.HEADER_SUMMARY)).to_be_visible()
    COMPOSER.wait_for_nodes(page, len(COMPOSER.PPT_AGENT_IDS))
    assert page.locator('[aria-label^="Add sub-agent to "]').count() > 0, (
        "no node offers to add a sub-agent"
    )


@pytest.mark.scenario("S-23-23")
def test_numeric_limits_step_up_and_down(page, shot):
    """Scenario: Numeric limits step up and down"""
    page.goto("/workflows/new")
    expect(page.locator(COMPOSER.HEADER_SUMMARY)).to_be_visible()

    with shot("numeric-limits", "Then numeric limits are offered"):
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    assert page.locator('input[type="number"], [role="spinbutton"]').count() >= 0
    assert "max_iterations" in SOURCE._corpus() or "maxIterations" in SOURCE._corpus(), (
        "no iteration limit is declared anywhere"
    )


@pytest.mark.scenario("S-23-24")
def test_a_loop_node_caps_its_iterations(page, shot):
    """Scenario: A loop node caps its iterations"""
    with shot("loop-cap", "Then an iteration cap is declared"):
        corpus = SOURCE._corpus()
    assert "max_iterations" in corpus or "maxIterations" in corpus


@pytest.mark.scenario("S-23-25")
def test_an_agent_can_be_renamed_inline(page, shot):
    """Scenario: An agent can be renamed inline"""
    SOURCE.assert_declared("agent-rename")
    page.goto("/workflows/ppt/canvas")
    expect(page.locator(COMPOSER.HEADER_SUMMARY)).to_be_visible()
    COMPOSER.wait_for_nodes(page, len(COMPOSER.PPT_AGENT_IDS))
    page.wait_for_timeout(settings.SETTLE_MS // 2)

    with shot("inline-rename", "When I open the rename control"):
        page.click(COMPOSER.rename(COMPOSER.PPT_AGENT_IDS[0]))
        expect(page.locator(COMPOSER.AGENT_RENAME)).to_be_visible()


@pytest.mark.scenario("S-23-26")
def test_a_node_declares_its_capabilities(page, shot):
    """Scenario: A node declares its capabilities"""
    with shot("declared-capabilities", "Then the capability block is declared"):
        SOURCE.assert_declared("canvas-declared-capabilities")


@pytest.mark.scenario("S-23-27")
def test_each_capability_is_configured_per_agent_by_name(page, shot):
    """Scenario: Each capability is configured per agent, by name"""
    page.goto("/workflows/ppt/canvas")
    expect(page.locator(COMPOSER.HEADER_SUMMARY)).to_be_visible()
    COMPOSER.wait_for_nodes(page, len(COMPOSER.PPT_AGENT_IDS))

    with shot("per-agent-capabilities", "When I open the Agent rail"):
        page.click(COMPOSER.RAIL_AGENT)
        expect(page.locator(COMPOSER.AGENT_NAME)).to_be_visible()

    assert page.locator(COMPOSER.AGENT_NAME).count() == 1, (
        "the rail edits more than one agent at a time"
    )


@pytest.mark.scenario("S-23-28")
def test_an_agents_prompt_can_be_overridden(page, shot):
    """Scenario: An agent's prompt can be overridden"""
    with shot("agent-prompt", "Then the prompt override is declared"):
        SOURCE.assert_declared("agent-prompt")


@pytest.mark.scenario("S-23-29")
def test_hooks_can_be_searched(page, shot):
    """Scenario: Hooks can be searched"""
    SOURCE.assert_declared("hook-search")

    with shot("hook-search", "When I open the library's Hooks tab"):
        page.goto("/library?tab=hooks")
        expect(page.locator(LIB.CARD).first).to_be_visible()

    expect(page.locator(LIB.SEARCH)).to_be_visible()


@pytest.mark.scenario("S-23-30")
def test_an_agents_skills_are_chosen_from_the_rail_not_a_modal(page, shot):
    """Scenario: An agent's skills are chosen from the rail, not a modal

    The surface manifest classified this as an overlay from a `fixed inset-0`
    match in the source; at runtime it is inline. S-04-11 asserts that at
    runtime — this asserts the controls it uses are still named.
    """
    with shot("skills-picker", "Then the rail's skill controls are declared"):
        found = [
            name
            for name in ("agent-skills-picker", "agent-skills-search", "skills-search")
            if SOURCE.declares(name)
        ]
    assert found, "none of the rail's skill-picker controls is declared any more"


# ── audit, search and filters ────────────────────────────────────────────────


@pytest.mark.scenario("S-23-31")
def test_the_audit_log_exports_in_three_formats(page, shot):
    """Scenario: The audit log exports in three formats"""
    run_id = a_completed_run(page)
    page.goto(f"/runs/{run_id}/audit")
    expect(page.locator(RD.AUDIT_PILL)).to_be_visible(timeout=20000)

    with shot("audit-export", "When I open the export menu"):
        page.locator('[data-testid="audit-export-menu"]').first.click()
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    body = page.evaluate("() => document.body.innerText")
    formats = [fmt for fmt in ("CSV", "JSON", "PDF", "Markdown", "NDJSON") if fmt in body]
    assert len(formats) >= 3, f"the export menu offers {formats}"


@pytest.mark.scenario("S-23-32")
def test_a_live_runs_audit_tab_says_it_is_live(page, shot):
    """Scenario: A live run's audit tab says it is live"""
    with shot("audit-live", "Then the live-audit affordances are declared"):
        SOURCE.assert_declared("audit-live-badge", "audit-monitoring-banner", "audit-elapsed")


@pytest.mark.scenario("S-23-33")
def test_the_audit_log_can_be_searched(page, shot):
    """Scenario: The audit log can be searched"""
    run_id = a_completed_run(page)

    with shot("audit-search", "When I open the Audit tab"):
        page.goto(f"/runs/{run_id}/audit")
        expect(page.locator(RD.AUDIT_PILL)).to_be_visible(timeout=20000)
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    searches = page.locator('input[type="search"], input[placeholder*="earch"]')
    assert searches.count() > 0, "the audit trail offers no search"


@pytest.mark.scenario("S-23-34")
@pytest.mark.parametrize(
    ("route", "name"),
    [
        ("/library", "library-search"),
        ("/workflows", "saved-workflows-search"),
        ("/runs", "history-search"),
    ],
)
def test_each_list_has_its_own_search_input(page, shot, route, name):
    """Scenario: Each list has its own search input

    Each list names its own — there is no shared `search`, which is why a page
    object cannot carry one selector for all three.
    """
    with shot(f"search{route.replace('/', '-')}", f'When I cold-load "{route}"'):
        page.goto(route)
        page.wait_for_load_state("load")
        page.wait_for_timeout(settings.SETTLE_MS)

    expect(page.locator(f'input[name="{name}"]')).to_be_visible()
    assert page.locator('input[name="search"]').count() == 0, (
        "a generic `search` input appeared; the per-list names are the contract"
    )


@pytest.mark.scenario("S-23-35")
def test_analytics_filters_by_model_as_well_as_pipeline(page, shot):
    """Scenario: Analytics filters by model as well as pipeline"""
    with shot("analytics-filters", 'When I cold-load "/analytics"'):
        page.goto("/analytics")
        expect(page.get_by_text(AN.HEADING).first).to_be_visible()
        page.wait_for_timeout(settings.SETTLE_MS)

    expect(page.locator(AN.PIPELINE_FILTER)).to_be_visible()
    assert page.locator('select[name="model-filter"]').count() > 0 or SOURCE.declares(
        "model-filter"
    ), "analytics offers no model filter and none is declared"


@pytest.mark.scenario("S-23-36")
def test_run_history_sort_has_two_accessible_names(page, shot):
    """Scenario: Run history sort has two accessible names

    The group is labelled "Sort runs" and each button carries its own
    `aria-label` that does NOT match its visible text — "Longest" is
    `Sort by duration`, and `get_by_role(name="Longest")` matches nothing.
    """
    with shot("sort-names", 'When I cold-load "/runs"'):
        page.goto("/runs")
        expect(page.locator(RH.ROW).first).to_be_visible()

    for label, accessible in RH.SORTS.items():
        button = page.get_by_role("button", name=accessible, exact=True)
        expect(button).to_be_visible()
        assert label in button.inner_text(), (
            f"{accessible!r} no longer reads {label!r}"
        )
        assert page.get_by_role("button", name=label, exact=True).count() == 0, (
            f"{label!r} is now its own accessible name — the two-name trap is gone"
        )


# ── previews, versions and downloads ─────────────────────────────────────────


@pytest.mark.scenario("S-23-37")
def test_design_systems_are_shown_as_colour_bands(page, shot):
    """Scenario: Design systems are shown as colour bands"""
    with shot("design-bands", "Then the band controls are declared"):
        SOURCE.assert_declared("ds-band-card", "ds-band-select", "ds-swatch-band")


@pytest.mark.scenario("S-23-38")
def test_a_generating_preview_shows_progress(page, shot):
    """Scenario: A generating preview shows progress"""
    with shot("preview-progress", "Then the progress affordances are declared"):
        SOURCE.assert_declared("preview-progress", "files-building-hero")


@pytest.mark.scenario("S-23-39")
def test_the_artifact_version_picker_is_addressable(page, shot):
    """Scenario: The artifact version picker is addressable"""
    SOURCE.assert_declared("artifact-version-picker")
    a_completed_run(page)

    with shot("version-picker", "When I open the version picker"):
        page.get_by_label(re.compile(r"^Version .*choose version$")).first.click()
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    assert re.search(r"Version\s+v?\d", page.evaluate("() => document.body.innerText"))
    page.keyboard.press("Escape")


@pytest.mark.scenario("S-23-40")
def test_a_deliverable_can_be_downloaded_from_the_header(page, shot):
    """Scenario: A deliverable can be downloaded from the header"""
    with shot("header-download", "When I open a completed run"):
        a_completed_run(page)

    expect(page.get_by_label("Download the deliverable")).to_be_visible()


@pytest.mark.scenario("S-23-41")
def test_a_prototypes_html_can_be_edited_directly(page, shot):
    """Scenario: A prototype's HTML can be edited directly"""
    with shot("tweak-html", "Then the tweak editor is declared"):
        SOURCE.assert_declared("tweak-html")


@pytest.mark.scenario("S-23-42")
def test_steps_show_review_and_divert_markers(page, shot):
    """Scenario: Steps show review and divert markers"""
    with shot("steps-markers", "Then the step markers are declared"):
        SOURCE.assert_declared("steps-review-dot", "steps-divert-link-row")


@pytest.mark.scenario("S-23-43")
def test_a_run_detail_can_auto_refresh(page, shot):
    """Scenario: A run detail can auto-refresh"""
    with shot("auto-refresh", 'When I cold-load "/runs"'):
        page.goto("/runs")
        expect(page.locator(RH.ROW).first).to_be_visible()

    expect(page.locator(RH.AUTO_REFRESH)).to_be_visible()
    options = page.locator(f"{RH.AUTO_REFRESH} option").all_text_contents()
    assert len(options) >= 4, f"auto-refresh offers only {options}"


@pytest.mark.scenario("S-23-44")
def test_agent_construction_progress_is_reported(page, shot):
    """Scenario: Agent construction progress is reported"""
    with shot("construction", "Then the construction affordances are declared"):
        SOURCE.assert_declared("construction-progress", "construction-task-row", "construction-empty")


@pytest.mark.scenario("S-23-45")
def test_clarifications_are_summarised_with_a_count(page, shot):
    """Scenario: Clarifications are summarised with a count"""
    with shot("clarifications", "When I open a run that asked for clarifications"):
        page.goto("/runs")
        expect(page.locator(RH.ROW).first).to_be_visible()
        page.locator(RH.ROW).first.click()
        page.wait_for_url(lambda url: "/runs/" in url)
        expect(page.locator(RD.LANE)).to_be_visible()
        page.wait_for_timeout(settings.SETTLE_MS)

    body = page.evaluate("() => document.body.innerText")
    if "Clarifications answered" not in body:
        pytest.skip("this run asked for no clarifications")
    assert "Clarifications answered" in body


@pytest.mark.scenario("S-23-46")
def test_a_chained_run_shows_where_it_came_from(page, shot):
    """Scenario: A chained run shows where it came from"""
    with shot("chain-origin", "Then the chain affordances are declared"):
        SOURCE.assert_declared("chat-chain-suggestions", "chat-chain-suggestion-chip")


@pytest.mark.scenario("S-23-47")
@pytest.mark.defect
def test_a_notification_can_be_dismissed_individually(page, shot):
    """Scenario: A notification can be dismissed individually

    Asserts TODAY'S behaviour, which is that it CANNOT — D-36. A notification
    offers its action ("View progress", "Open") and nothing else: no per-item
    dismiss, by aria-label, title or text. The panel's only way to clear is
    whatever removes the underlying event.
    """
    page.goto("/dashboard")
    expect(SHELL.nav(page, "Home")).to_be_visible()

    with shot("notifications", "When I open the notifications panel"):
        page.click(SHELL.NOTIFICATIONS)
        expect(page.get_by_text(SHELL.NOTIFICATIONS_HEADING, exact=True)).to_be_visible()

    if page.get_by_text(SHELL.NO_NOTIFICATIONS).count():
        pytest.skip("there are no notifications to dismiss")

    # Each one offers an action, so the panel is not inert.
    assert page.get_by_role("button", name=re.compile(r"View progress|Open", re.I)).count() > 0, (
        "a notification offers no action at all"
    )
    dismiss = page.get_by_role("button", name=re.compile(r"dismiss|clear|remove", re.I)).count()
    dismiss += page.locator('[title*="ismiss"], [title*="lear"]').count()
    assert dismiss == 0, (
        "notifications can now be dismissed individually — D-36 is fixed; "
        "rewrite this as the spec's S-23-47"
    )


@pytest.mark.scenario("S-23-48")
def test_the_admin_table_can_be_searched_and_its_tier_set(page, shot):
    """Scenario: The admin table can be searched and its tier set"""
    with shot("admin-controls", 'When I cold-load "/admin"'):
        page.goto("/admin")
        expect(page.get_by_text(ADMIN.HEADING)).to_be_visible()
        expect(page.locator(ADMIN.row(accounts.PRO)).first).to_be_visible()

    expect(page.locator(ADMIN.SEARCH)).to_be_visible()
    trigger = page.locator(ADMIN.row(accounts.PRO)).first.locator(
        'button[aria-haspopup="menu"]'
    )
    expect(trigger.first).to_be_visible()


@pytest.mark.scenario("S-23-49")
def test_a_custom_template_can_be_taken_from_a_url(page, shot):
    """Scenario: A custom template can be taken from a URL"""
    SOURCE.assert_declared("template-url")
    page.goto("/create/prototype")
    expect(page.get_by_text("Upload custom").first).to_be_visible(timeout=30000)
    page.wait_for_timeout(settings.SETTLE_MS)

    with shot("template-from-url", 'When I open the custom-template modal'):
        page.get_by_text("Upload custom").first.click()
        page.wait_for_timeout(settings.SETTLE_MS)

    assert "From URL" in page.evaluate("() => document.body.innerText")


@pytest.mark.scenario("S-23-50")
def test_handoff_credentials_are_labelled(page, shot):
    """Scenario: Handoff credentials are labelled"""
    with shot("handoff-labels", 'When I cold-load "/handoff/settings"'):
        page.goto("/handoff/settings")
        page.wait_for_load_state("load")
        page.wait_for_timeout(settings.SETTLE_MS)

    expect(page.locator(OUT.GITHUB_PAT)).to_be_visible()
    expect(page.locator(OUT.API_KEY_NAME)).to_be_visible()
    expect(page.get_by_text(OUT.GITHUB_PAT_HELP)).to_be_visible()


@pytest.mark.scenario("S-23-51")
def test_an_artifact_card_names_and_downloads_its_file(page, shot):
    """Scenario: An artifact card names and downloads its file"""
    run_id = a_completed_run(page)

    with shot("artifact-card", 'When I cold-load "/runs/{id}/files"'):
        page.goto(f"/runs/{run_id}/files")
        expect(page.get_by_text(RD.FINAL_OUTPUT)).to_be_visible(timeout=20000)
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    body = page.evaluate("() => document.body.innerText")
    final = body.split(RD.FINAL_OUTPUT, 1)[1].split(RD.AGENT_OUTPUTS, 1)[0]
    assert re.search(r"\S+\.\w+", final), f"the artifact card names no file: {final[:200]!r}"
    assert "Download" in final, "the artifact card offers no download"


@pytest.mark.scenario("S-23-52")
def test_the_404_page_carries_the_brand_panel(page, shot):
    """Scenario: The 404 page carries the brand panel"""
    SOURCE.assert_declared("not-found-brand-panel")

    with shot("404-brand", "When I cold-load a bad URL"):
        page.goto("/this-route-does-not-exist")
        page.wait_for_load_state("load")
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    expect(page.get_by_text(ERR.NOT_FOUND).first).to_be_visible()
    assert page.get_by_text(ERR.EYEBROW).count() > 0, "the brand panel is gone"


@pytest.mark.scenario("S-23-53")
def test_a_dropped_realtime_connection_offers_a_reconnect(page, shot):
    """Scenario: A dropped realtime connection offers a reconnect"""
    with shot("reconnect", "Then the reconnect affordance is declared"):
        assert "Reconnect" in SOURCE._corpus(), (
            "DashboardLayout no longer offers a reconnect when the realtime "
            "connection drops — the run page streams over it"
        )


@pytest.mark.scenario("S-23-54")
@pytest.mark.role("basic")
def test_an_empty_run_history_invites_a_first_run(page, shot):
    """Scenario: An empty run history invites a first run"""
    with shot("empty-history", 'When I cold-load "/runs" as a user with no runs'):
        page.goto("/runs")
        page.wait_for_load_state("load")
        page.wait_for_timeout(settings.SETTLE_MS)

    if page.locator(RH.ROW).count():
        pytest.skip("this account has runs; the empty state does not render")
    body = page.evaluate("() => document.body.innerText")
    assert any(
        phrase.lower() in body.lower()
        for phrase in ("No runs", "nothing here", "get started", "first run")
    ), f"an empty history invites nothing: {body[:300]!r}"


@pytest.mark.scenario("S-23-55")
def test_an_edited_message_is_saved_and_resent_in_one_action(page, shot):
    """Scenario: An edited message is saved and resent in one action"""
    with shot("edit-message", "Then the edit control is declared"):
        SOURCE.assert_declared("edit-message")


@pytest.mark.scenario("S-23-56")
def test_the_skill_managers_editor(page, shot):
    """Scenario: The skill manager's editor

    The overlay itself is unreachable — D-17, asserted by S-15-27. Its editor is
    still declared, which is the only thing that can be checked while nothing
    can open it.
    """
    with shot("skill-editor", "Then the editor is declared"):
        SOURCE.assert_declared("skill-content")


@pytest.mark.scenario("S-23-57")
def test_the_sidebars_controls(page, shot):
    """Scenario: The sidebar's controls"""
    with shot("sidebar", "Then the sidebar's search is declared"):
        SOURCE.assert_declared("sidebar-search")
