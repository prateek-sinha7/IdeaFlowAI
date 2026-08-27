"""Implements ../../../screens/16-pages-outside-routes.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

These five pages are outside the routing contract, so nothing else in the suite
exercises them. `/handoff/settings` stores a credential that grants repo access,
which makes S-16-11 and S-16-14 — "the token is never echoed back" and "one user
cannot see another's" — the highest-value assertions in this file.

The credential scenarios write a deliberately invalid token
(`ghp_` + a marker string) and delete it again. An invalid value still proves
the storage contract, and cannot grant anything if the cleanup ever fails.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from framework import accounts, api, settings
from framework.locators import auth as AUTH
from framework.locators import composer as COMPOSER
from framework.locators import outside_routes as L
from framework.locators import run_history as RH

FAKE_PAT = "ghp_E2ES1611NotARealTokenAndNeverWasAAAAAAAA"


def cold(page, route: str) -> None:
    page.goto(route)
    page.wait_for_load_state("load")
    page.wait_for_timeout(settings.SETTLE_MS // 2)


# ── /workflow ────────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-16-01")
def test_the_legacy_workflow_builder_is_reachable_by_url(page, shot):
    """Scenario: The legacy workflow builder is reachable by URL"""
    with shot("legacy-builder", 'When I cold-load "/workflow"'):
        cold(page, "/workflow")

    expect(page.get_by_text(L.LEGACY_HEADING)).to_be_visible()
    for label in L.LEGACY_CONTROLS:
        expect(page.get_by_role("button", name=label, exact=True)).to_be_visible()
    expect(page.locator("textarea")).to_have_count(1)


@pytest.mark.scenario("S-16-02")
def test_the_legacy_builder_is_not_the_composer(page, shot):
    """Scenario: The legacy builder is not the composer"""
    with shot("legacy-not-composer", 'When I cold-load "/workflow"'):
        cold(page, "/workflow")

    # A parallel implementation with its own chrome. None of the composer's own
    # controls exist here, which is the whole point of recording the page.
    expect(page.get_by_text("CUSTOM · COMPOSER")).to_have_count(0)
    expect(page.locator(COMPOSER.SIMPLE)).to_have_count(0)
    expect(page.locator(COMPOSER.CANVAS_TAB)).to_have_count(0)
    expect(page.locator(COMPOSER.SAVE_WORKFLOW)).to_have_count(0)


@pytest.mark.scenario("S-16-03")
@pytest.mark.defect
def test_the_legacy_builder_cannot_add_an_agent(page, shot):
    """Scenario: The legacy builder cannot add an agent

    INVERTED. The spec writes this one as it SHOULD behave, so that it turns
    green when the page is fixed. A suite where a scenario is red by design
    cannot tell a regression from a known gap, so this asserts today's behaviour
    instead — D-17 — and fails the day an agent appears, which is the same
    signal one step later.

    The picker answers "No agents found" for every category, so the builder can
    never hold a node and `Run Workflow` can never run anything. It also strands
    `SkillManager`, whose only mount root is this page's `AgentNode`: no node,
    no "Manage skill" button, and that overlay is unreachable by any route.
    """
    cold(page, "/workflow")

    with shot("legacy-picker", 'When I click "Add Agent"'):
        page.get_by_role("button", name="Add Agent", exact=True).click()
        expect(page.get_by_text(L.NO_AGENTS_FOUND)).to_be_visible()

    for category in L.LEGACY_CATEGORIES:
        page.get_by_role("button", name=category, exact=True).click()
        page.wait_for_timeout(300)
        assert page.get_by_text(L.NO_AGENTS_FOUND).count() == 1, (
            f'"{category}" now offers agents — D-17 is fixed. Rewrite this as '
            "the spec's S-16-03."
        )


# ── /workflow/create ─────────────────────────────────────────────────────────


@pytest.mark.scenario("S-16-04")
@pytest.mark.parametrize("mode", ["ppt", "prototype"])
def test_the_legacy_wizard_path_redirects_to_the_named_create_route(page, shot, mode):
    """Scenario: The legacy wizard path redirects to the named create route"""
    with shot(f"legacy-wizard-{mode}", f'When I cold-load "/workflow/create?mode={mode}"'):
        page.goto(f"/workflow/create?mode={mode}")
        page.wait_for_url(f"**/create/{mode}")

    # The routes.ts comment saying the redirect had not landed yet is stale; the
    # code is not.
    assert page.url.endswith(f"/create/{mode}")
    expect(page.locator('textarea[name="brief"]')).to_be_visible()


# ── /preview-fullscreen ──────────────────────────────────────────────────────


@pytest.mark.scenario("S-16-05")
def test_a_runid_deep_link_redirects_to_the_runs_full_preview(page, shot):
    """Scenario: A runId deep-link redirects to the run's full preview"""
    page.goto("/runs")
    expect(page.locator(RH.ROW).first).to_be_visible()
    completed = [
        label for label in RH.rows(page) if RH.status_of(label) == "completed"
    ]
    assert completed, "no completed run to deep-link"
    page.locator(f'{RH.ROW}[aria-label="{completed[0]}"]').click()
    page.wait_for_url(lambda url: "/runs/" in url)
    run_id = page.url.split("/runs/")[1].split("/")[0].split("?")[0]

    with shot("preview-deeplink", 'When I cold-load "/preview-fullscreen?runId={id}"'):
        page.goto(f"/preview-fullscreen?runId={run_id}")
        page.wait_for_url(f"**/runs/{run_id}/preview/full")

    assert page.url.endswith(f"/runs/{run_id}/preview/full")


@pytest.mark.scenario("S-16-06")
def test_the_bare_path_with_no_payload_falls_back_to_run_history(page, shot):
    """Scenario: The bare path with no payload falls back to run history"""
    with shot("preview-bare", 'When I cold-load "/preview-fullscreen" with no payload'):
        page.goto("/preview-fullscreen")
        page.wait_for_url("**/runs")

    # Not a blank screen: the history really rendered.
    expect(page.get_by_role("heading", name=RH.HEADING)).to_be_visible()


@pytest.mark.scenario("S-16-07")
def test_an_oversized_project_explains_itself_and_offers_a_way_out(page, shot):
    """Scenario: An oversized project explains itself and offers a way out"""
    with shot("preview-quota", 'When I cold-load "/preview-fullscreen?error=quota"'):
        cold(page, "/preview-fullscreen?error=quota")

    expect(page.get_by_text(L.QUOTA_HEADING)).to_be_visible()
    expect(page.get_by_text(L.QUOTA_BODY)).to_be_visible()


@pytest.mark.scenario("S-16-08")
@pytest.mark.live
@pytest.mark.skip(reason="needs an App Builder run with an open preview; live tier")
def test_the_app_builder_full_screen_button_hands_files_over_in_sessionstorage(page, shot):
    """Scenario: The App Builder full-screen button hands files over in sessionStorage"""


# ── /handoff/settings ────────────────────────────────────────────────────────


@pytest.mark.scenario("S-16-09")
def test_handoff_settings_offers_the_install_command(page, shot):
    """Scenario: Handoff settings offers the install command"""
    with shot("handoff-settings", 'When I cold-load "/handoff/settings"'):
        cold(page, "/handoff/settings")

    expect(page.get_by_text(L.HANDOFF_HEADING).first).to_be_visible()
    expect(page.get_by_text(re.compile(re.escape(L.SLASH_COMMAND))).first).to_be_visible()
    expect(page.get_by_text(re.compile(re.escape(L.INSTALL_LINE))).first).to_be_visible()
    expect(page.get_by_role("button", name="Copy", exact=True)).to_be_visible()
    expect(page.get_by_text(re.compile(re.escape(L.IDEMPOTENT))).first).to_be_visible()


@pytest.mark.scenario("S-16-10")
def test_a_github_token_can_be_saved_and_is_never_read_back(page, shot):
    """Scenario: A GitHub token can be saved and is never read back"""
    with shot("handoff-token-field", 'When I cold-load "/handoff/settings"'):
        cold(page, "/handoff/settings")

    expect(page.locator(L.GITHUB_PAT)).to_be_visible()
    expect(page.get_by_text(L.GITHUB_PAT_HELP)).to_be_visible()
    # "when no token is saved I am told so explicitly" — an empty field is not
    # the same statement as one that says nothing is stored.
    body = page.evaluate("() => document.body.innerText")
    assert L.NO_TOKEN in body or "token saved" in body.lower(), body[:200]


@pytest.mark.scenario("S-16-11")
@pytest.mark.destructive
def test_a_saved_github_token_is_not_echoed_to_the_client(page, shot):
    """Scenario: A saved GitHub token is not echoed to the client

    NARROWED, deliberately. The backend verifies a PAT against GitHub before
    storing it — `PUT /api/settings/github-pat` answers 400 with "GitHub
    rejected the PAT (401)" for anything it cannot authenticate — so the
    "reload after a successful save" half of this scenario needs a real,
    repo-scoped credential. This suite will not hold one, and a test that
    stores a working repo token to prove a storage contract would be creating
    the risk it is checking for.

    What IS reachable, and what this asserts: the value never reaches storage
    unverified, the page keeps saying no token is saved, and the submitted
    string appears in no response body on the way through. The last of those is
    the same network-layer check the full scenario wanted.
    """
    cold(page, "/handoff/settings")

    bodies: list[str] = []
    statuses: list[int] = []

    def capture(response):
        if "/api/" in response.url and "github-pat" in response.url:
            statuses.append(response.status)
            try:
                bodies.append(response.text())
            except Exception:
                pass

    page.on("response", capture)

    with shot("token-refused", "When I submit a token GitHub cannot authenticate"):
        page.fill(L.GITHUB_PAT, FAKE_PAT)
        page.click(L.SAVE)
        expect(page.get_by_text(re.compile(re.escape(L.PAT_REJECTED)))).to_be_visible()

    assert statuses and all(s >= 400 for s in statuses), (
        f"an unverifiable PAT was accepted: {statuses}"
    )
    for body in bodies:
        assert FAKE_PAT not in body, "the endpoint echoed the submitted token back"

    with shot("token-not-stored", 'When I reload "/handoff/settings"'):
        cold(page, "/handoff/settings")

    assert L.NO_TOKEN in page.evaluate("() => document.body.innerText")
    assert FAKE_PAT not in page.content()
    assert page.locator(L.GITHUB_PAT).input_value() != FAKE_PAT


@pytest.mark.scenario("S-16-12")
@pytest.mark.destructive
def test_an_api_key_is_shown_once_and_never_again(page, shot):
    """Scenario: An API key is shown once and never again

    Revokes the key it creates, so the account ends with the key list it
    started with.
    """
    name = "e2e-s-16-12"
    cold(page, "/handoff/settings")

    try:
        with shot("key-created", "When I create an API key with a name"):
            page.fill(L.API_KEY_NAME, name)
            page.click(L.CREATE_KEY)
            expect(page.get_by_text(name)).to_be_visible()

        shown = page.evaluate("() => document.body.innerText")
        # The plaintext is a long opaque string shown exactly once. Capture any
        # token-shaped run so the reload can prove it is gone — the list itself
        # shows only a masked prefix.
        secrets = [s for s in re.findall(r"\b[A-Za-z0-9_\-]{24,}\b", shown) if name not in s]

        with shot("key-not-reshown", "When I reload the page"):
            cold(page, "/handoff/settings")

        after = page.evaluate("() => document.body.innerText")
        assert name in after, "the key vanished from the list entirely"
        assert L.KEY_MASK in after, "the list does not mask the key at all"
        for secret in secrets:
            assert secret not in after, f"the plaintext key was shown again: {secret[:8]}…"
    finally:
        revoke_key(page, name)


def revoke_key(page, name: str) -> None:
    """Revoke a named API key, if it is still listed."""
    cold(page, "/handoff/settings")
    row = page.locator("div").filter(has_text=re.compile(re.escape(name))).last
    button = row.locator(L.REVOKE)
    if button.count():
        page.once("dialog", lambda d: d.accept())
        button.first.click()
        page.wait_for_timeout(settings.SETTLE_MS // 2)


@pytest.mark.scenario("S-16-13")
@pytest.mark.anonymous
def test_handoff_settings_requires_authentication(page, shot):
    """Scenario: Handoff settings requires authentication"""
    with shot("handoff-anonymous", 'When I cold-load "/handoff/settings" with no session'):
        page.goto("/handoff/settings")
        page.wait_for_url("**/login**", timeout=settings.LOGIN_TIMEOUT_MS)

    expect(page.locator(L.GITHUB_PAT)).to_have_count(0)
    expect(page.locator(L.API_KEY_NAME)).to_have_count(0)
    expect(page.get_by_text(AUTH.WELCOME_HEADING)).to_be_visible()


@pytest.mark.scenario("S-16-14")
@pytest.mark.destructive
@pytest.mark.role("basic")
def test_one_user_cannot_see_anothers_handoff_credentials(page, shot, page_as):
    """Scenario: One user cannot see another's handoff credentials

    The assertion that matters most in this file: this surface stores
    credentials that grant repo access.

    The fixture is an API KEY rather than a GitHub token, because the PAT
    endpoint verifies against GitHub before storing and so cannot be seeded with
    a safe value (see S-16-11). The isolation being checked is the same one —
    both live on the same screen, behind the same account scope.

    qa-pro's key is revoked in the teardown.
    """
    name = "e2e-s-16-14-pro"
    pro = page_as("pro")
    pro.goto("/handoff/settings")
    pro.wait_for_load_state("load")
    pro.wait_for_timeout(settings.SETTLE_MS // 2)

    try:
        with shot("pro-creates-a-key", 'Given "qa-pro" has created an API key'):
            pro.fill(L.API_KEY_NAME, name)
            pro.click(L.CREATE_KEY)
            expect(pro.get_by_text(name)).to_be_visible()

        with shot("basic-sees-nothing", 'When I cold-load "/handoff/settings" as qa-basic'):
            cold(page, "/handoff/settings")

        body = page.evaluate("() => document.body.innerText")
        assert name not in body, (
            "qa-basic is shown an API key belonging to qa-pro — cross-account "
            "isolation is broken on /handoff/settings"
        )
        assert L.NO_TOKEN in body, (
            f"qa-basic is shown a GitHub token it does not own. Page said: {body[:200]!r}"
        )
    finally:
        revoke_key(pro, name)


# ── /handoff/{token} ─────────────────────────────────────────────────────────


@pytest.mark.scenario("S-16-15")
def test_an_invalid_handoff_token_is_refused_clearly(page, shot):
    """Scenario: An invalid handoff token is refused clearly"""
    with shot("handoff-invalid", 'When I cold-load "/handoff/invalid-token"'):
        cold(page, "/handoff/invalid-token")

    expect(page.get_by_text(L.HANDOFF_NOT_FOUND).first).to_be_visible()
    expect(page.get_by_text(L.BACK_TO_DASHBOARD)).to_be_visible()


@pytest.mark.scenario("S-16-16")
@pytest.mark.skip(reason="needs a fixture that mints a valid handoff token; 22_handoff_and_gates")
def test_a_valid_handoff_token_opens_the_handoff_workflow(page, shot):
    """Scenario: A valid handoff token opens the handoff workflow"""


@pytest.mark.scenario("S-16-17")
@pytest.mark.skip(reason="needs a handoff token issued to another user; 22_handoff_and_gates")
def test_a_handoff_token_belonging_to_another_user_is_refused(page, shot):
    """Scenario: A handoff token belonging to another user is refused"""
