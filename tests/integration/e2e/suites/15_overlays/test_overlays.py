"""Implements ../../../screens/15-overlays.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

**Two overlays no user can open** are recorded here rather than tested:
`SkillManager`'s only mount root is the orphaned `/workflow` builder whose agent
picker is empty (D-17), and `PrototypePreview` never mounts because the Preview
tab renders the wrong file (D-18). Both are asserted as unreachable, so the day
either becomes reachable the test says so.

Close controls are the recurring theme. The add-agent modal's has no accessible
name and ignores Escape (D-07); the create-user dialog has no Cancel at all
(D-23); the template modal's three icon controls have no text and no aria-label
but DO have a title, which is the only handle they offer.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from framework import accounts, settings
from framework.locators import admin as ADMIN
from framework.locators import composer as COMPOSER
from framework.locators import library as LIB
from framework.locators import run_detail as RD
from framework.locators import run_history as RH
from framework.locators import saved_workflows as SW
from framework.locators import shell as SHELL

DIALOG = '[role="dialog"]'
OVERLAY = "div.fixed.inset-0"
# `input[name="agent-search"]`, not a testid — the spec says testid and the
# app uses a name.
AGENT_SEARCH = 'input[name="agent-search"]'


def dialogs(page) -> int:
    return page.locator(DIALOG).count()


def open_advanced(page, route: str = "/create/user-stories"):
    page.goto(route)
    expect(page.locator('textarea[name="brief"]')).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS // 2)
    page.get_by_role("button", name=re.compile(r"^Advanced\s")).first.click()
    expect(page.get_by_text("Advanced Workflow Configuration")).to_be_visible(timeout=20000)


def a_completed_run(page) -> str:
    page.goto("/runs")
    expect(page.locator(RH.ROW).first).to_be_visible()
    done = [label for label in RH.rows(page) if RH.status_of(label) == "completed"]
    assert done
    page.locator(f'{RH.ROW}[aria-label="{done[0]}"]').first.click()
    page.wait_for_url(lambda url: "/runs/" in url)
    expect(page.locator(RD.HEADER)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS)
    return page.url.split("/runs/")[1].split("/")[0].split("?")[0]


# ── the catalog inspect dialog ───────────────────────────────────────────────


@pytest.mark.scenario("S-15-01")
@pytest.mark.defect
def test_inspecting_a_catalog_workflow_describes_it_without_launching(page, shot):
    """Scenario: Inspecting a catalog workflow describes it without launching

    The description half holds. The Escape half does NOT — the dialog stays open
    — which is the same shape as D-07 on the add-agent modal, and why S-20-01
    must never be collapsed into "Escape closes any overlay".
    """
    page.goto("/dashboard")
    expect(page.get_by_text("What would you like to build today?")).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS // 2)
    before_url = page.url

    with shot("inspect-dialog", "When I inspect a catalog workflow"):
        page.get_by_label(re.compile("^Inspect .* details$")).first.click()
        expect(page.locator(DIALOG).first).to_be_visible()

    body = page.evaluate("() => document.body.innerText")
    for section in ("CONTEXT PROVIDERS", "CAPABILITIES", "COMPACTION"):
        assert section in body, f"the dialog has no {section} section"
    # A section with nothing to show says so rather than rendering empty.
    assert re.search(r"No .* declared\.", body), "an empty section says nothing"
    assert page.url == before_url, "inspecting started a run"

    with shot("inspect-escape-ignored", "When I press Escape"):
        page.keyboard.press("Escape")
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    assert dialogs(page) > 0, (
        "Escape now closes the inspect dialog — the spec's S-15-01 can be "
        "asserted in full, and S-20-01 gains a row"
    )


# ── the Advanced layer ───────────────────────────────────────────────────────


@pytest.mark.scenario("S-15-02")
def test_the_advanced_control_opens_the_full_agent_configuration(page, shot):
    """Scenario: The Advanced control opens the full agent configuration"""
    with shot("advanced", 'When I click "Advanced 7 agents"'):
        open_advanced(page)

    expect(page.get_by_text("Advanced Workflow Configuration — User Stories")).to_be_visible()
    expect(page.locator(SW.USE_MY_VERSION)).to_be_visible(timeout=15000)
    expect(page.get_by_text("Open in full canvas")).to_be_visible()
    # Uppercased by CSS; the DOM text is "Core = locked".
    expect(page.get_by_text(re.compile(r"core\s*=\s*locked", re.I))).to_be_visible()

    label = page.get_by_role("button", name=re.compile(r"^Advanced\s")).first.inner_text()
    promised = int(re.search(r"(\d+)", label.replace("\n", " ")).group(1))
    assert COMPOSER.node_order(page) and len(COMPOSER.node_order(page)) == promised, (
        f'the control says {promised} agents; the layer lists '
        f"{len(COMPOSER.node_order(page))}"
    )


@pytest.mark.scenario("S-15-03")
def test_the_advanced_layers_workflow_tab_exposes_the_deliverable_settings(page, shot):
    """Scenario: The Advanced layer's Workflow tab exposes the deliverable settings

    CORRECTED on where they live. The deliverable settings are on the layer's
    DEFAULT view, present the moment it opens. The layer's own "Workflow" tab is
    a different thing entirely — it lists the validator catalogue — and clicking
    it navigates AWAY from these controls.
    """
    with shot("advanced-deliverable", "When the Advanced layer opens"):
        open_advanced(page)

    expect(page.locator(COMPOSER.DELIVERABLE_STRATEGY)).to_be_attached()
    expect(page.locator(COMPOSER.OUTPUT_FILENAME)).to_be_attached()
    expect(page.locator(COMPOSER.OUTPUT_FORMAT)).to_be_attached()
    for name in COMPOSER.SWITCHES:
        expect(COMPOSER.switch(page, name)).to_be_attached()

    with shot("advanced-workflow-tab", 'When I select its "Workflow" tab'):
        page.locator(COMPOSER.RAIL_WORKFLOW).first.click()
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    assert page.locator(COMPOSER.DELIVERABLE_STRATEGY).count() == 0, (
        "the layer's Workflow tab now keeps the deliverable settings — the "
        "spec's S-15-03 is true as written again"
    )


@pytest.mark.scenario("S-15-04")
def test_open_in_full_canvas_escalates_to_the_composer(page, shot):
    """Scenario: Open in full canvas escalates to the composer"""
    open_advanced(page)

    with shot("full-canvas", 'When I click "Open in full canvas"'):
        page.get_by_text("Open in full canvas").first.click()
        page.wait_for_url(re.compile(r"/workflows/"))
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    assert "/workflows/" in page.url
    expect(page.locator(COMPOSER.HEADER_SUMMARY)).to_be_visible()


@pytest.mark.scenario("S-15-05")
@pytest.mark.destructive
@pytest.mark.skip(reason="saving from the Advanced layer creates a real workflow row; S-04-17 covers the save path with cleanup")
def test_saving_from_the_advanced_layer_names_the_new_workflow(page, shot):
    """Scenario: Saving from the Advanced layer names the new workflow"""


# ── the add-agent modal ──────────────────────────────────────────────────────


@pytest.mark.scenario("S-15-06")
def test_the_add_agent_modal_lists_agents_by_category(page, shot):
    """Scenario: The add-agent modal lists agents by category"""
    page.goto("/workflows/new")
    expect(page.locator(COMPOSER.HEADER_SUMMARY)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS // 2)

    with shot("add-agent-modal", 'When I click the "Add agent" control'):
        page.locator(COMPOSER.ADD_AGENT).first.click()
        expect(page.locator(COMPOSER.ADD_TO_PLAN).first).to_be_visible(timeout=15000)

    body = page.evaluate("() => document.body.innerText")
    for category in ("All", "User Stories", "PPT", "Prototype", "App Builder", "Custom"):
        assert category in body, f"the category rail has no {category!r}"
    expect(page.locator(AGENT_SEARCH)).to_be_visible()
    assert page.locator('[data-testid^="library-card-"]').count() > 0


@pytest.mark.scenario("S-15-07")
def test_each_agent_card_is_individually_addressable(page, shot):
    """Scenario: Each agent card is individually addressable

    The per-card testid removes the ambiguity that the older
    clickNear-on-title workaround existed for — "+ Add" repeats once per card.
    """
    page.goto("/workflows/new")
    expect(page.locator(COMPOSER.HEADER_SUMMARY)).to_be_visible()
    page.locator(COMPOSER.ADD_AGENT).first.click()
    expect(page.locator(COMPOSER.ADD_TO_PLAN).first).to_be_visible(timeout=15000)

    card = page.locator('[data-testid^="library-card-"]').first
    agent_id = (card.get_attribute("data-testid") or "").replace("library-card-", "")
    assert agent_id

    with shot("add-one-agent", f"When I add exactly {agent_id}"):
        card.locator(COMPOSER.ADD_TO_PLAN).first.click()
        COMPOSER.wait_for_nodes(page, 1)

    assert COMPOSER.node_order(page) == [agent_id], (
        f"adding {agent_id} produced {COMPOSER.node_order(page)}"
    )


@pytest.mark.scenario("S-15-08")
@pytest.mark.defect
def test_the_add_agent_modal_cannot_be_closed_by_name_or_by_escape(page, shot):
    """Scenario: The add-agent modal cannot be closed by name or by Escape

    Asserts TODAY'S behaviour — D-07. This also corrects the ba-browser
    definition's `addAgentModalStaysOpen` quirk, which described the symptom
    without the cause.
    """
    page.goto("/workflows/new")
    expect(page.locator(COMPOSER.HEADER_SUMMARY)).to_be_visible()
    page.locator(COMPOSER.ADD_AGENT).first.click()
    expect(page.locator(COMPOSER.ADD_TO_PLAN).first).to_be_visible(timeout=15000)

    with shot("escape-ignored", "When I press Escape"):
        page.keyboard.press("Escape")
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    assert page.locator(OVERLAY).count() > 0, "Escape now closes it — D-07 is fixed"

    named = page.get_by_role("button", name=re.compile("close", re.I)).count()
    assert named == 0, (
        "the modal now has a close control with an accessible name — D-07's "
        "other half is fixed too"
    )


# ── the library drawer ───────────────────────────────────────────────────────


@pytest.mark.scenario("S-15-09")
@pytest.mark.defect
def test_the_library_item_drawer_opens_beside_the_list_not_over_it(page, shot):
    """Scenario: The library item drawer opens beside the list, not over it

    CORRECTED on one clause, as in S-08-17: the drawer DOES carry
    `role="dialog"`. The substance — it sits beside the list rather than over it
    — holds, and is what this asserts.
    """
    with shot("agent-drawer", 'When I cold-load an agent drawer'):
        page.goto(f"/library/agents/{LIB.AGENT_SLUG}")
        expect(page.locator(LIB.AGENT_DRAWER)).to_be_visible()
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    assert page.locator(LIB.CARD).count() > 0, "the library list unmounted behind the drawer"
    assert dialogs(page) > 0, (
        "the drawer no longer carries role=dialog — the spec's original claim is "
        "true again"
    )


@pytest.mark.scenario("S-15-10")
@pytest.mark.parametrize("drawer_tab", LIB.DRAWER_TABS)
def test_the_agent_drawers_tabs_each_show_their_own_panel(page, shot, drawer_tab):
    """Scenario: The agent drawer's tabs each show their own panel"""
    page.goto(f"/library/agents/{LIB.AGENT_SLUG}")
    drawer = page.locator(LIB.AGENT_DRAWER)
    expect(drawer).to_be_visible()

    with shot(f"drawer-{drawer_tab.lower()}", f'When I click "{drawer_tab}"'):
        drawer.get_by_role("tab", name=drawer_tab, exact=True).click()
        page.wait_for_timeout(settings.SETTLE_MS // 3)

    body = drawer.inner_text()
    assert len(body.strip()) > len(" ".join(LIB.DRAWER_TABS)) + 20, (
        f'the "{drawer_tab}" panel rendered nothing'
    )


@pytest.mark.scenario("S-15-11")
def test_an_agent_with_no_suggested_hooks_says_so(page, shot):
    """Scenario: An agent with no suggested hooks says so"""
    page.goto(f"/library/agents/{LIB.AGENT_SLUG}")
    drawer = page.locator(LIB.AGENT_DRAWER)
    expect(drawer).to_be_visible()

    with shot("drawer-hooks", "When I open the Hooks tab"):
        drawer.get_by_role("tab", name="Hooks", exact=True).click()
        page.wait_for_timeout(settings.SETTLE_MS // 3)

    body = drawer.inner_text()
    if "No suggested hooks" not in body:
        pytest.skip("this agent has suggested hooks, so the empty state does not render")
    assert "No suggested hooks" in body


@pytest.mark.scenario("S-15-12")
def test_the_agent_config_tab_exposes_the_gate_overrides(page, shot):
    """Scenario: The agent Config tab exposes the gate overrides"""
    page.goto(f"/library/agents/{LIB.AGENT_SLUG}")
    drawer = page.locator(LIB.AGENT_DRAWER)
    expect(drawer).to_be_visible()

    with shot("drawer-config", 'When I open the Config tab'):
        drawer.get_by_role("tab", name="Config", exact=True).click()
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    body = drawer.inner_text()
    for control in ("System Prompt", "Model", "Validator", "Retry"):
        assert control in body, f"the Config tab offers no {control!r}: {body[:300]!r}"
    for phase in ("BEFORE EXECUTE", "AFTER EXECUTE"):
        assert phase.lower() in body.lower(), f"no {phase} section"


# ── row menus ────────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-15-13")
def test_the_workflow_actions_menu_offers_the_four_row_operations(page, shot):
    """Scenario: The workflow actions menu offers the four row operations"""
    page.goto("/workflows")
    expect(page.locator(SW.CARD).first).to_be_visible()

    with shot("workflow-actions", "When I open a card's actions menu"):
        SW.card(page, SW.OVERRIDE_TITLE).locator(SW.ACTIONS).click()
        expect(page.get_by_role("menuitem").first).to_be_visible()

    items = [t.strip() for t in page.get_by_role("menuitem").all_text_contents()]
    assert items == SW.MENU_ITEMS, f"the menu offers {items}, not {SW.MENU_ITEMS}"


@pytest.mark.scenario("S-15-14")
def test_the_run_actions_menu_offers_only_delete(page, shot):
    """Scenario: The run actions menu offers only delete"""
    page.goto("/runs")
    expect(page.locator(RH.ROW).first).to_be_visible()
    label = RH.rows(page)[0]

    with shot("run-actions", "When I open a row's actions menu"):
        page.locator(f'{RH.ROW}[aria-label="{label}"]').first.locator(RH.RUN_ACTIONS).click()
        expect(page.get_by_role("menuitem").first).to_be_visible()

    items = [t.strip() for t in page.get_by_role("menuitem").all_text_contents()]
    assert items == ["Delete"], f"the run menu offers {items}"


# ── run header overlays ──────────────────────────────────────────────────────


@pytest.mark.scenario("S-15-15")
def test_the_version_picker_lists_a_runs_artifact_versions(page, shot):
    """Scenario: The version picker lists a run's artifact versions

    A scrim covers the page while it is open — dismiss it before clicking
    anything else in the header, or the click is intercepted.
    """
    a_completed_run(page)

    with shot("version-picker", "When I click the version control"):
        page.get_by_label(re.compile(r"^Version .*choose version$")).first.click()
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    body = page.evaluate("() => document.body.innerText")
    assert re.search(r"Version\s+v?\d", body), f"no versions listed: {body[-300:]!r}"
    page.keyboard.press("Escape")


@pytest.mark.scenario("S-15-16")
def test_share_copies_a_link_rather_than_opening_a_dialog(page, shot):
    """Scenario: Share copies a link rather than opening a dialog"""
    run_id = a_completed_run(page)
    share = page.get_by_label("Copy a link to this run")
    expect(share).to_be_visible()
    before = dialogs(page)

    with shot("share", "When I activate Share"):
        share.click()
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    assert dialogs(page) == before, "Share opened a dialog"
    # Read back through the page rather than the system clipboard, which a
    # headless browser does not share.
    copied = page.evaluate("() => navigator.clipboard.readText().catch(() => '')")
    if copied:
        assert run_id in copied, f"the clipboard holds {copied!r}"


# ── the wizard galleries ─────────────────────────────────────────────────────


@pytest.mark.scenario("S-15-17")
def test_a_template_tile_opens_a_detail_modal_with_a_live_preview(page, shot):
    """Scenario: A template tile opens a detail modal with a live preview

    The modal's three icon controls have no text and no aria-label. They DO have
    a title, unlike the add-agent modal's close control (D-07) — use title here;
    there is nothing else.
    """
    page.goto("/create/prototype")
    expect(page.locator("button:has(iframe)").first).to_be_visible(timeout=30000)
    page.wait_for_timeout(settings.SETTLE_MS)

    with shot("template-modal", "When I click a template tile"):
        page.locator("button:has(iframe)").first.click()
        page.wait_for_timeout(settings.SETTLE_MS)

    body = page.evaluate("() => document.body.innerText")
    assert "Use this template" in body, f"the modal offers no way to use it: {body[-300:]!r}"
    for title in ("Open in new tab", "Fullscreen", "Close"):
        assert page.locator(f'[title="{title}"]').count() > 0, (
            f"the modal has no control titled {title!r}"
        )


@pytest.mark.scenario("S-15-18")
def test_the_gallery_mounts_one_live_iframe_per_tile(page, shot):
    """Scenario: The gallery mounts one live iframe per tile

    Dozens of iframes on one page. This screen is slow to settle and a naive
    "wait for network idle" may never resolve — which is why nothing in this
    suite uses networkidle.
    """
    with shot("gallery", 'When I cold-load "/create/prototype"'):
        page.goto("/create/prototype")
        expect(page.locator("button:has(iframe)").first).to_be_visible(timeout=30000)
        page.wait_for_timeout(settings.SETTLE_MS * 2)

    tiles = page.locator("button:has(iframe)").count()
    frames = page.locator("button:has(iframe) iframe").count()
    assert tiles > 10, f"only {tiles} template tiles rendered"
    assert frames == tiles, f"{tiles} tiles but {frames} iframes"


@pytest.mark.scenario("S-15-19")
@pytest.mark.parametrize("route", ["/create/prototype", "/create/ppt"])
def test_custom_upload_is_offered_on_both_wizards_html_only(page, shot, route):
    """Scenario: Custom upload is offered on both wizards, HTML only

    The PRESENTATION wizard's custom upload accepts .html, not .pptx — it is the
    prototype modal reused verbatim. Recorded as observed; whether a deck wizard
    should take an HTML file is a product question.
    """
    page.goto(route)
    expect(page.get_by_text("Upload custom").first).to_be_visible(timeout=30000)
    page.wait_for_timeout(settings.SETTLE_MS)

    with shot(f"upload-custom{route.replace('/', '-')}", 'When I click "Upload custom"'):
        page.get_by_text("Upload custom").first.click()
        page.wait_for_timeout(settings.SETTLE_MS)

    body = page.evaluate("() => document.body.innerText")
    assert "Upload custom template" in body, body[-300:]
    for tab in ("Upload HTML file", "From URL"):
        assert tab in body, f"the modal has no {tab!r} tab"

    accept = page.locator('input[type="file"]').last.get_attribute("accept") or ""
    assert ".html" in accept, f"the file input accepts {accept!r}"
    assert ".pptx" not in accept, (
        f"{route} now accepts .pptx — the modal is no longer the prototype one"
    )


@pytest.mark.scenario("S-15-20")
def test_a_design_system_tile_shows_its_full_design_md(page, shot):
    """Scenario: A design-system tile shows its full DESIGN.md"""
    page.goto("/create/prototype")
    expect(page.get_by_text("Design System").first).to_be_visible(timeout=30000)
    page.wait_for_timeout(settings.SETTLE_MS)

    with shot("design-systems", 'When I open the "Design System" tab'):
        page.get_by_text("Design System", exact=True).first.click()
        page.wait_for_timeout(settings.SETTLE_MS)

    tiles = page.locator("button:has(iframe)")
    if tiles.count() == 0:
        pytest.skip("the Design System tab offers no tiles in this environment")

    with shot("design-system-modal", "When I click a design-system tile"):
        tiles.first.click()
        page.wait_for_timeout(settings.SETTLE_MS)

    assert "Use this system" in page.evaluate("() => document.body.innerText")


@pytest.mark.scenario("S-15-21")
def test_a_custom_design_system_is_pasted_not_uploaded(page, shot):
    """Scenario: A custom design system is pasted, not uploaded

    Note the asymmetry: templates are uploaded as a FILE, design systems are
    pasted as TEXT. Two modals, two input models.
    """
    page.goto("/create/prototype")
    expect(page.get_by_text("Design System").first).to_be_visible(timeout=30000)
    page.wait_for_timeout(settings.SETTLE_MS)
    page.get_by_text("Design System", exact=True).first.click()
    page.wait_for_timeout(settings.SETTLE_MS)

    if page.get_by_text("Upload custom").count() == 0:
        pytest.skip("the Design System tab offers no custom upload here")

    with shot("custom-design-system", 'When I click "Upload custom"'):
        page.get_by_text("Upload custom").first.click()
        page.wait_for_timeout(settings.SETTLE_MS)

    body = page.evaluate("() => document.body.innerText")
    assert "Add custom design system" in body, body[-300:]
    assert page.locator("textarea").count() > 0, "a design system is pasted, not uploaded"
    assert "Load example" in body


# ── admin ────────────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-15-22")
def test_add_user_collects_credentials_plan_and_the_admin_flag(page, shot):
    """Scenario: Add user collects credentials, plan and the admin flag"""
    page.goto("/admin")
    expect(page.get_by_text(ADMIN.HEADING)).to_be_visible()

    with shot("create-user", 'When I click "Add user"'):
        page.click(ADMIN.ADD_USER)
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    assert "Create New User" in page.evaluate("() => document.body.innerText")
    expect(page.locator('select[name="new-user-tier"]')).to_be_visible()
    expect(page.locator('input[name="new-user-is-admin"]')).to_be_attached()
    options = page.locator('select[name="new-user-tier"] option').all_text_contents()
    for tier in ("basic", "pro", "enterprise", "hexaware"):
        assert any(tier in o.lower() for o in options), f"no {tier} option: {options}"


@pytest.mark.scenario("S-15-23")
@pytest.mark.defect
def test_the_create_user_dialog_can_be_abandoned(page, shot):
    """Scenario: The create-user dialog can be abandoned

    Asserts TODAY'S behaviour, which is that it cannot be abandoned by any
    NAMED control — there is no Cancel, and the close control has no text, no
    aria-label and no title. The same shape as D-07.
    """
    page.goto("/admin")
    expect(page.get_by_text(ADMIN.HEADING)).to_be_visible()
    page.click(ADMIN.ADD_USER)
    page.wait_for_timeout(settings.SETTLE_MS // 2)

    with shot("create-user-dismissal", "Then look for a named way out"):
        named = page.get_by_role("button", name=re.compile(r"cancel|close", re.I)).count()

    assert named == 0, (
        "the create-user dialog now offers a named way out — the spec's S-15-23 "
        "can be asserted in full"
    )


# ── the divert target picker ─────────────────────────────────────────────────


@pytest.mark.scenario("S-15-24")
@pytest.mark.skip(reason="the divert picker sits below the rail's fold on a ROUTE node's Config sub-tab; 22_handoff_and_gates owns that surface")
def test_the_divert_picker_opens_from_the_config_rail_not_the_canvas(page, shot):
    """Scenario: The divert picker opens from the config rail, not the canvas"""


@pytest.mark.scenario("S-15-25")
@pytest.mark.skip(reason="needs the divert picker open; see S-15-24")
def test_the_divert_picker_groups_and_searches_the_catalogue(page, shot):
    """Scenario: The divert picker groups and searches the catalogue"""


@pytest.mark.scenario("S-15-26")
@pytest.mark.skip(reason="needs the divert picker open before the workflow fetch can be failed; see S-15-24")
def test_a_failed_workflow_fetch_degrades_to_free_text(page, shot):
    """Scenario: A failed workflow fetch degrades to free text"""


# ── two overlays no user can open ────────────────────────────────────────────


@pytest.mark.scenario("S-15-27")
@pytest.mark.defect
def test_the_skill_manager_is_reachable(page, shot):
    """Scenario: The skill manager is reachable

    INVERTED. It is not — D-17. `SkillManager`'s only mount root is `/workflow`,
    the orphaned legacy builder, whose "Add Agent" picker returns "No agents
    found" for every category. With no node there is no "Manage skill" button,
    so this overlay cannot be opened by anyone, by any route.
    """
    with shot("skill-manager-unreachable", 'When I cold-load "/workflow"'):
        page.goto("/workflow")
        page.wait_for_load_state("load")
        page.wait_for_timeout(settings.SETTLE_MS)

    assert page.get_by_text("Manage skill").count() == 0, (
        "a Manage skill control exists — D-17 is fixed and the skill manager "
        "can finally be tested"
    )
    page.get_by_role("button", name="Add Agent", exact=True).click()
    expect(page.get_by_text("No agents found")).to_be_visible()


@pytest.mark.scenario("S-15-28")
def test_a_prototype_deliverable_offers_source_and_tweaks(page, shot):
    """Scenario: A prototype deliverable offers source and tweaks

    **D-18 is FIXED.** `PrototypePreview` mounts: the deliverable renders in an
    iframe and the three icon controls are in the DOM. The spec records the
    overlay as uncapturable "because the feature under it is broken"; it is not
    any more, so this asserts the scenario as written.
    """
    page.goto("/runs")
    expect(page.locator(RH.ROW).first).to_be_visible()
    RH.chip(page, "Prototype").first.click()
    page.wait_for_url("**type=prototype")
    page.wait_for_timeout(settings.SETTLE_MS // 2)
    done = [label for label in RH.rows(page) if RH.status_of(label) == "completed"]
    if not done:
        pytest.skip("no completed prototype run")

    page.locator(f'{RH.ROW}[aria-label="{done[0]}"]').first.click()
    page.wait_for_url(lambda url: "/runs/" in url)
    expect(page.locator(RD.HEADER)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS)

    with shot("prototype-preview", 'When I select the "Prototype" renderer'):
        switch = page.locator(RD.RENDERER_SWITCH)
        if switch.get_by_text("Prototype", exact=True).count():
            switch.get_by_text("Prototype", exact=True).first.click()
            page.wait_for_timeout(settings.SETTLE_MS)

    assert page.locator("iframe").count() > 0, (
        "the prototype renders no iframe — D-18 has regressed"
    )
    for title in ("View source", "Open tweaks panel"):
        assert page.locator(f'[title="{title}"]').count() > 0, (
            f"no control titled {title!r}"
        )


# ── dismissal without navigation ─────────────────────────────────────────────


@pytest.mark.scenario("S-15-29")
@pytest.mark.parametrize(
    "overlay",
    ["the account menu", "the notifications panel", "the workflow actions menu", "the run actions menu"],
)
def test_menus_and_drawers_close_without_navigating(page, shot, overlay):
    """Scenario: Menus and drawers close without navigating"""
    if overlay == "the account menu":
        page.goto("/dashboard")
        expect(SHELL.nav(page, "Home")).to_be_visible()
        opener, marker = lambda: page.click(SHELL.ACCOUNT_MENU), SHELL.MENU
    elif overlay == "the notifications panel":
        page.goto("/dashboard")
        expect(SHELL.nav(page, "Home")).to_be_visible()
        opener, marker = (
            lambda: page.click(SHELL.NOTIFICATIONS),
            f"text={SHELL.NO_NOTIFICATIONS}",
        )
    elif overlay == "the workflow actions menu":
        page.goto("/workflows")
        expect(page.locator(SW.CARD).first).to_be_visible()
        opener, marker = (
            lambda: SW.card(page, SW.OVERRIDE_TITLE).locator(SW.ACTIONS).click(),
            '[role="menuitem"]',
        )
    else:
        page.goto("/runs")
        expect(page.locator(RH.ROW).first).to_be_visible()
        opener, marker = (
            lambda: page.locator(RH.RUN_ACTIONS).first.click(),
            '[role="menuitem"]',
        )

    before = page.url

    with shot(f"open-{overlay.replace(' ', '-')}", f"Given {overlay} is open"):
        opener()
        expect(page.locator(marker).first).to_be_visible()

    with shot(f"dismiss-{overlay.replace(' ', '-')}", "When I dismiss it"):
        page.keyboard.press("Escape")
        page.wait_for_timeout(settings.SETTLE_MS // 3)
        if page.locator(marker).count():
            # Not every menu answers Escape; clicking away is the other gesture
            # a user has.
            page.mouse.click(6, 6)
            page.wait_for_timeout(settings.SETTLE_MS // 3)

    expect(page.locator(marker)).to_have_count(0)
    assert page.url == before, f"dismissing {overlay} navigated to {page.url}"
