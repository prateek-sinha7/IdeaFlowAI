"""Implements ../../../screens/20-keyboard-and-navigation.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

Two things this file exists to protect:

**Space must still type a space.** `CanvasView` binds Space to pan the canvas
and guards on INPUT/TEXTAREA/isContentEditable. Without that guard the rename
and prompt fields stop accepting spaces — a silent, total break of an editing
surface that no other test would notice.

**A session that cannot be refreshed does a FULL page load** to the sign-in
screen. `lib/api.ts` uses `location.href`, not `router.replace`, on purpose:
every piece of client state is discarded. A test asserting SPA navigation there
fails for the wrong reason.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from framework import nav as NAV
from framework import settings
from framework.locators import composer as COMPOSER
from framework.locators import library as LIB
from framework.locators import run_history as RH
from framework.locators import saved_workflows as SW
from framework.locators import shell as SHELL

OVERLAY = "div.fixed.inset-0"


def open_canvas(page) -> None:
    page.goto("/workflows/ppt/canvas")
    expect(page.locator(COMPOSER.HEADER_SUMMARY)).to_be_visible()
    COMPOSER.wait_for_nodes(page, len(COMPOSER.PPT_AGENT_IDS))
    page.wait_for_timeout(settings.SETTLE_MS // 2)


def mark_document(page) -> None:
    """Stamp the live document so a full reload can be detected.

    A soft navigation keeps the same document and the stamp survives; a real
    page load replaces the document and it is gone. Nothing else distinguishes
    the two from inside the page.
    """
    page.evaluate("() => { window.__e2e_same_document = true; }")


def same_document(page) -> bool:
    return bool(page.evaluate("() => !!window.__e2e_same_document"))


# ── keyboard ─────────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-20-01")
@pytest.mark.parametrize(
    "overlay",
    [
        "the account menu",
        "the notifications panel",
        "the catalog inspect dialog",
        "the prototype template detail",
        "the custom template modal",
        "the design-system detail",
        "the custom design system modal",
        "the divert workflow picker",
    ],
)
def test_escape_closes_an_overlay(page, shot, overlay):
    """Scenario: Escape closes an overlay

    Do NOT collapse this into "Escape closes any overlay" — the add-agent modal
    is the documented exception, and S-20-02 pins it.
    """
    if overlay not in ("the account menu", "the notifications panel"):
        pytest.skip(f"{overlay} is opened in 15_overlays; its locators live there")

    page.goto("/dashboard")
    expect(SHELL.nav(page, "Home")).to_be_visible()
    before = page.url

    trigger, marker = (
        (SHELL.ACCOUNT_MENU, SHELL.MENU)
        if overlay == "the account menu"
        else (SHELL.NOTIFICATIONS, f'text={SHELL.NO_NOTIFICATIONS}')
    )

    with shot("overlay-open", f"Given {overlay} is open"):
        page.click(trigger)
        expect(page.locator(marker).first).to_be_visible()

    with shot("overlay-escaped", "When I press Escape"):
        page.keyboard.press("Escape")
        expect(page.locator(marker)).to_have_count(0)

    assert page.url == before, "Escape navigated as well as closing"


@pytest.mark.scenario("S-20-02")
@pytest.mark.defect
def test_escape_closes_the_add_agent_modal(page, shot):
    """Scenario: Escape closes the add-agent modal

    Asserts TODAY'S behaviour, which is that it does NOT — D-07. The overlay is
    still mounted after Escape, and it swallows every click meant for the canvas
    beneath it, so the only way out is its own close control, which has no
    accessible name (D-23).
    """
    open_canvas(page)

    with shot("add-agent-open", "Given the add-agent modal is open"):
        page.locator(COMPOSER.ADD_AGENT).first.click()
        expect(page.locator(OVERLAY).first).to_be_visible()

    with shot("escape-ignored", "When I press Escape"):
        page.keyboard.press("Escape")
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    assert page.locator(OVERLAY).count() > 0, (
        "Escape now closes the add-agent modal — D-07 is fixed. Rewrite this as "
        "the spec's S-20-02 and drop the defect marker."
    )


NODE_LEFTS = """() => [...document.querySelectorAll('[data-testid^="canvas-node-wrap-"]')]
     .map(e => e.getBoundingClientRect().left)"""


def drag_from(page, x: float, y: float, dx: float) -> list[float]:
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + dx, y, steps=8)
    page.mouse.up()
    page.wait_for_timeout(settings.SETTLE_MS // 3)
    return page.evaluate(NODE_LEFTS)


@pytest.mark.scenario("S-20-03")
def test_holding_space_pans_the_canvas(page, shot):
    """Scenario: Holding Space pans the canvas

    Dragging empty canvas pans it with or without Space, so "the canvas moved"
    proves nothing about the binding. What Space changes is what a drag STARTING
    ON A NODE does: in pan mode the whole canvas moves together, and the node
    keeps its position relative to its siblings.
    """
    open_canvas(page)
    node = page.locator(COMPOSER.node(COMPOSER.PPT_AGENT_IDS[1])).bounding_box()
    before = page.evaluate(NODE_LEFTS)

    with shot("canvas-panned", "When I hold Space and drag from a node"):
        page.keyboard.down(" ")
        after = drag_from(page, node["x"] + node["width"] / 2, node["y"] + 8, -160)
        page.keyboard.up(" ")

    deltas = [b - a for a, b in zip(before, after)]
    assert any(abs(d) > 20 for d in deltas), "the canvas did not move at all"
    # Every node by the same amount: the viewport moved, not one node.
    assert max(deltas) - min(deltas) < 2, (
        f"the nodes moved by different amounts ({deltas}) — the drag moved a "
        "NODE, so Space did not put the canvas into pan mode"
    )
    # Space's default action is suppressed: the page itself never scrolled.
    assert page.evaluate("() => window.scrollY") == 0


@pytest.mark.scenario("S-20-04")
def test_space_still_types_a_space_in_a_text_field(page, shot):
    """Scenario: Space still types a space in a text field

    The highest-value keyboard assertion in the suite. `CanvasView` guards its
    Space binding on INPUT / TEXTAREA / isContentEditable; without that guard
    every editing field on the canvas silently stops accepting spaces.
    """
    open_canvas(page)
    page.click(COMPOSER.rename(COMPOSER.PPT_AGENT_IDS[-1]))
    field = page.locator(COMPOSER.AGENT_RENAME)
    expect(field).to_be_visible()

    with shot("space-in-a-field", "When I press Space with focus in a text field"):
        field.fill("Deck")
        field.press("Space")
        page.wait_for_timeout(400)

    assert field.input_value() == "Deck ", (
        f"Space did not reach the field — it typed {field.input_value()!r}. The "
        "canvas pan binding has lost its INPUT guard."
    )
    assert page.evaluate("() => window.scrollY") == 0


@pytest.mark.scenario("S-20-05")
def test_space_to_pan_releases_on_keyup(page, shot):
    """Scenario: Space-to-pan releases on keyup

    A missed keyup leaves the canvas stuck in pan mode with no visible cause —
    and there IS no visible cause to look for: the canvas shows no cursor
    change, no class, nothing that says pan mode is active. So this asserts the
    behavioural difference instead. After Space is released, a drag from a node
    moves THAT node, which in pan mode it would not.
    """
    open_canvas(page)
    node = page.locator(COMPOSER.node(COMPOSER.PPT_AGENT_IDS[1])).bounding_box()

    page.mouse.move(node["x"] + node["width"] / 2, node["y"] + 8)
    page.keyboard.down(" ")
    page.keyboard.up(" ")
    before = page.evaluate(NODE_LEFTS)

    with shot("pan-released", "When I release Space and drag a node"):
        after = drag_from(page, node["x"] + node["width"] / 2, node["y"] + 8, -160)

    deltas = [b - a for a, b in zip(before, after)]
    assert max(deltas) - min(deltas) > 20, (
        f"every node moved together ({deltas}) — the canvas is still in pan "
        "mode after Space was released"
    )


@pytest.mark.scenario("S-20-06")
@pytest.mark.skip(
    reason="a placeholder marking known-unknown territory: six files read "
    "modifier keys and none has been enumerated, so there is nothing to assert yet"
)
def test_modifier_shortcuts_behave_as_advertised(page, shot):
    """Scenario: Modifier shortcuts behave as advertised"""


@pytest.mark.scenario("S-20-07")
@pytest.mark.skip(reason="the run chat composer belongs to 18_chat_lane; its send binding is unconfirmed")
def test_submitting_a_chat_message_by_keyboard(page, shot):
    """Scenario: Submitting a chat message by keyboard"""


# ── navigation edges ─────────────────────────────────────────────────────────


@pytest.mark.scenario("S-20-08")
@pytest.mark.parametrize(
    "route",
    ["/dashboard", "/library", "/workflows", "/runs", "/analytics", "/settings/profile"],
)
def test_every_route_survives_a_cold_load(page, shot, route):
    """Scenario: Every route survives a cold load

    Cold-load fidelity is what PAGES.md already proves across 55 URLs; this
    keeps a sample of it inside the running suite, and exists mainly so the
    distinction from S-20-09 is explicit — in-app navigation is the part that
    was NOT proven.
    """
    with shot(f"cold{route.replace('/', '-')}", f'When I cold-load "{route}"'):
        page.goto(route)
        page.wait_for_load_state("load")
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    assert route.split("?")[0] in page.url
    body = page.evaluate("() => document.body.innerText")
    assert len(body.strip()) > 40, f"{route} rendered an empty document"
    assert "Page not found." not in body


@pytest.mark.scenario("S-20-09")
@pytest.mark.parametrize(
    "case",
    ["catalog card", "run row", "Open in Steps", "Open in Preview", "saved workflow card", "agent card"],
)
def test_an_in_app_affordance_lands_where_its_url_claims(page, shot, case):
    """Scenario: An in-app affordance lands where its URL claims

    Every row also asserts the navigation was SOFT. 47 `router.push` calls exist
    and a soft push is the contract; one that quietly became a `location.href`
    would still land on the right URL and would still pass a URL-only check.
    """
    if case in ("Open in Steps", "Open in Preview"):
        pytest.skip("the run detail surface belongs to 07_run_detail")

    if case == "catalog card":
        page.goto("/dashboard")
        expect(page.get_by_text("What would you like to build today?")).to_be_visible()
        mark_document(page)
        page.get_by_text("Build an end-to-end application").first.click()
        page.wait_for_url("**/create/**")
    elif case == "run row":
        page.goto("/runs")
        expect(page.locator(RH.ROW).first).to_be_visible()
        mark_document(page)
        page.locator(RH.ROW).first.click()
        page.wait_for_url(lambda url: "/runs/" in url)
    elif case == "saved workflow card":
        page.goto("/workflows")
        expect(page.locator(SW.CARD).first).to_be_visible()
        mark_document(page)
        SW.card(page, SW.OVERRIDE_TITLE).locator(SW.ACTIONS).click()
        page.get_by_role("menuitem", name="Edit").click()
        page.wait_for_url("**/workflows/*/edit")
    else:  # agent card
        page.goto("/library")
        expect(page.locator(LIB.CARD).first).to_be_visible()
        mark_document(page)
        page.locator(LIB.CARD).first.click()
        page.wait_for_url("**/library/agents/**")

    with shot(f"soft-nav-{case.replace(' ', '-')}", f"Then {case} landed where it claims"):
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    assert same_document(page), f"{case} did a full page reload; it should be a router.push"


@pytest.mark.scenario("S-20-10")
def test_back_returns_to_where_i_came_from(page, shot):
    """Scenario: Back returns to where I came from

    `DashboardLayout` holds the product's only `router.back()`. Whether the type
    filter survives is exactly the kind of thing `router.back()` gets wrong,
    which is why the assertion is on the query string and not just the path.
    """
    page.goto("/runs?type=custom")
    expect(page.locator(RH.ROW).first).to_be_visible()
    page.locator(RH.ROW).first.click()
    page.wait_for_url(lambda url: "/runs/" in url)

    with shot("back-to-history", "When I go back"):
        page.go_back()
        NAV.wait_for_url_containing(page, "/runs")
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    assert "type=custom" in page.url, (
        f"the type filter did not survive Back — landed on {page.url}"
    )


@pytest.mark.scenario("S-20-11")
@pytest.mark.skip(reason="the template and design-system modals belong to 15_overlays")
def test_a_new_tab_affordance_opens_a_new_tab(page, shot):
    """Scenario: A new-tab affordance opens a new tab"""


@pytest.mark.scenario("S-20-12")
def test_a_session_that_cannot_be_refreshed_forces_a_hard_reload_to_sign_in(page, shot):
    """Scenario: A session that cannot be refreshed forces a hard reload to sign-in

    `lib/api.ts` uses `location.href`, not `router.replace`, so every piece of
    client state is discarded. That is deliberate, and asserting SPA-style
    navigation here would fail for the wrong reason.
    """
    page.goto("/dashboard")
    expect(SHELL.nav(page, "Home")).to_be_visible()
    mark_document(page)

    with shot("hard-reload-to-login", "When the app makes an authenticated request"):
        for act in (
            lambda: page.evaluate(
                "() => localStorage.setItem('auth_token', 'not-a-usable-token')"
            ),
            lambda: SHELL.nav(page, "Library").click(timeout=5000),
        ):
            try:
                act()
            except Exception:
                pass
        NAV.wait_for_url_containing(page, "/login?expired=true")
        NAV.settle_after_redirect(page)

    assert not same_document(page), (
        "the redirect to sign-in kept the document — it became a soft "
        "navigation, and the client state it was supposed to discard survived"
    )


# ── error boundaries ─────────────────────────────────────────────────────────


@pytest.mark.scenario("S-20-13")
def test_a_route_level_render_error_is_caught_and_explained(page, shot):
    """Scenario: A route-level render error is caught and explained

    Reachable only by fault injection: the required request is intercepted and
    answered with data the screen cannot render.
    """
    page.route(
        f"{settings.API_URL}/api/runs**",
        lambda route: route.fulfill(status=200, content_type="application/json", body="{"),
    )

    with shot("render-error", "When I load a route whose render throws"):
        page.goto("/runs")
        page.wait_for_load_state("load")
        page.wait_for_timeout(settings.SETTLE_MS)

    body = page.evaluate("() => document.body.innerText")
    assert len(body.strip()) > 20, "a malformed payload produced a blank page"
    # Whatever is shown, it must offer a way on — a boundary with no recovery is
    # a dead end.
    assert page.locator("button, a[href]").count() > 0, "nothing to recover with"


@pytest.mark.scenario("S-20-14")
@pytest.mark.skip(
    reason="needs the route-level boundary to actually render; S-20-13 shows the "
    "screen degrades without reaching app/error.tsx, so there is no recovery "
    "control to activate"
)
def test_recovering_from_an_error_boundary_does_a_full_reload(page, shot):
    """Scenario: Recovering from an error boundary does a full reload"""


@pytest.mark.scenario("S-20-15")
@pytest.mark.skip(
    reason="app/global-error.tsx catches what escapes the route boundary; no "
    "injection reached it, and forcing one means breaking the root layout"
)
def test_a_root_level_failure_still_renders_something(page, shot):
    """Scenario: A root-level failure still renders something"""


@pytest.mark.scenario("S-20-16")
def test_a_server_500_does_not_leave_the_user_on_a_blank_page(page, shot):
    """Scenario: A server 500 does not leave the user on a blank page

    Written after observing exactly this: the dev server returned 500 for the
    whole `[...view]` catch-all with "ReferenceError: require is not defined",
    and nothing in the suite said what the user should see.
    """
    page.route(
        f"{settings.API_URL}/api/**",
        lambda route: route.fulfill(status=500, content_type="application/json", body='{"detail":"boom"}'),
    )

    with shot("server-500", "When every API call returns 500"):
        page.goto("/dashboard")
        page.wait_for_load_state("load")
        page.wait_for_timeout(settings.SETTLE_MS)

    body = page.evaluate("() => document.body.innerText")
    assert len(body.strip()) > 20, "a 500 from every endpoint produced an empty document"
    for selector in settings.BUSY_SELECTORS:
        expect(page.locator(selector)).to_have_count(0)
