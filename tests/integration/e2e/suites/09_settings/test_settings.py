"""Implements ../../../screens/09-settings.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

**Five of these scenarios describe a state this pool cannot produce.** The
security tab branches on `status.supported`, and every seeded QA account is
Cognito-managed, so the screen renders "Not available for this account" and the
method rows never mount. Rather than assert the branch that is reachable and
call it coverage, S-09-14..S-09-18 read `/api/auth/mfa` first and skip with the
reason — they will start running the moment the pool grows a local account.

The destructive scenarios restore what they changed in a `finally`. The
constitution is the one that matters: it is prepended to EVERY agent on EVERY
run, so a leftover fixture value would contaminate the live tier.
"""

from __future__ import annotations

import json

import pytest
from playwright.sync_api import expect

from framework import accounts, api, settings
from framework.locators import settings_page as L


def open_settings(page, route: str = "/settings/profile") -> None:
    page.goto(route)
    expect(page.get_by_text(L.HEADING).first).to_be_visible()


def open_model_tab(page) -> None:
    """The AI-model tab, waited on until its data has actually landed.

    The `<select>` mounts EMPTY and is filled by a fetch that arrives later —
    and that fetch sets `pendingModel` as well as `selectedModel`. Selecting
    an option before it lands is therefore silently UNDONE, which leaves
    `selectedModel === pendingModel` and Save disabled for good: a 30s click
    timeout on a button that is present, visible, and never going to enable.

    Waiting for a real option to be attached is what proves the fetch
    returned; `wait_for()` on the select itself returns far too early.
    """
    page.goto("/settings/ai-model")
    expect(page.locator(f"{L.MODEL_SELECT} option").nth(1)).to_be_attached(
        timeout=15_000
    )
    page.wait_for_timeout(settings.SETTLE_MS)


def save_model(page, value: str) -> None:
    """Pick `value` and save it, from a tab that is already loaded.

    Save is `disabled={savingModel || selectedModel === pendingModel}`, so
    waiting for it to ENABLE is the assertion that the selection took.
    """
    page.select_option(L.MODEL_SELECT, value)
    expect(page.locator(L.SAVE_MODEL)).to_be_enabled(timeout=10_000)
    page.click(L.SAVE_MODEL)
    expect(page.get_by_text("Model preference saved")).to_be_visible(timeout=15_000)


def mfa_status(page) -> dict:
    """The pool's MFA capability, as the security tab itself reads it.

    Returned as a plain dict rather than asserted on here: several scenarios
    only make sense for one branch of it, and they need to say so in their skip
    reason rather than fail as if the screen were wrong.
    """
    import json

    res = api.request(page, "GET", "/api/auth/mfa")
    assert res["status"] == 200, f"/api/auth/mfa returned {res['status']}: {res['body']}"
    return json.loads(res["body"])


# ── shared chrome ────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-09-01")
@pytest.mark.parametrize(
    ("testid", "label", "route"), L.TABS, ids=[t[0] for t in L.TABS]
)
def test_every_tab_is_addressable_by_url(page, shot, testid, label, route):
    """Scenario: Every tab is addressable by URL"""
    with shot(f"tab-{testid}", f'When I cold-load "{route}"'):
        open_settings(page, route)

    expect(page.get_by_text(L.SUBTITLE)).to_be_visible()
    # aria-selected is the tab strip's own statement about which panel is live;
    # a visible-looking tab is not the same claim.
    expect(page.locator(L.tab(testid))).to_have_attribute("aria-selected", "true")
    assert page.url.endswith(route), f"{route} settled at {page.url}"


@pytest.mark.scenario("S-09-02")
@pytest.mark.parametrize(
    ("testid", "label", "route"),
    [t for t in L.TABS if t[0] != "tab-profile"] + [L.TABS[0]],
    ids=lambda v: v if isinstance(v, str) else "",
)
def test_clicking_a_tab_pushes_its_url(page, shot, testid, label, route):
    """Scenario: Clicking a tab pushes its URL"""
    with shot(f"click-{testid}", f'Given I am on "/settings/profile"'):
        open_settings(page)

    with shot(f"pushed-{testid}", f'When I click "{testid}"'):
        page.click(L.tab(testid))
        page.wait_for_url(f"**{route}")

    assert page.url.endswith(route)


@pytest.mark.scenario("S-09-03")
def test_a_bare_settings_lands_on_profile(page, shot):
    """Scenario: A bare /settings lands on Profile"""
    with shot("bare-settings", 'When I cold-load "/settings"'):
        page.goto("/settings")
        # The redirect is client-side, so the SETTLED url is the claim — the
        # first paint is /settings and asserting on it reads as a 404.
        page.wait_for_url("**/settings/profile")

    expect(page.locator(L.tab("tab-profile"))).to_have_attribute("aria-selected", "true")
    expect(page.get_by_text(L.PASSWORD_SECTION, exact=True)).to_be_visible()


# ── Profile ──────────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-09-04")
def test_profile_shows_identity_and_plan_with_email_read_only(page, shot):
    """Scenario: Profile shows identity and plan, with email read-only"""
    with shot("profile", 'When I cold-load "/settings/profile"'):
        open_settings(page)

    expect(page.get_by_text(accounts.ADMIN).first).to_be_visible()
    # "read only" is a caption, not the `readonly` attribute — the field is
    # rendered as text, so there is no input to interrogate.
    expect(page.get_by_text("Email · read only")).to_be_visible()
    expect(page.get_by_text("Plan", exact=True)).to_be_visible()
    expect(page.get_by_text(L.PASSWORD_SECTION, exact=True)).to_be_visible()

    for sel in (L.CURRENT_PASSWORD, L.NEW_PASSWORD, L.CONFIRM_PASSWORD):
        field = page.locator(sel)
        expect(field).to_be_visible()
        expect(field).to_have_attribute("type", "password")
    expect(page.locator(L.CHANGE_PASSWORD)).to_be_visible()


@pytest.mark.scenario("S-09-05")
@pytest.mark.destructive
def test_changing_the_password_requires_the_current_one_and_a_confirmation(page, shot):
    """Scenario: Changing the password requires the current one and a confirmation

    Marked destructive because the screen it drives can change a shared
    account's password — but only the REFUSAL paths are exercised, and neither
    reaches the server. Nothing is written, which is why this one does not need
    a disposable account.
    """
    with shot("password-form", 'When I cold-load "/settings/profile"'):
        open_settings(page)

    submit = page.locator(L.CHANGE_PASSWORD)

    with shot("no-current-password", "And I submit a new password without the current one"):
        page.fill(L.NEW_PASSWORD, "a-brand-new-password")
        page.fill(L.CONFIRM_PASSWORD, "a-brand-new-password")

    # The refusal is the DISABLED button, not the "All fields are required"
    # banner: `disabled` already covers every empty field, so that branch of
    # handleChangePassword cannot be reached through the UI at all.
    expect(submit).to_be_disabled()

    with shot("mismatched-confirmation", "When the confirmation does not match"):
        page.fill(L.CURRENT_PASSWORD, accounts.PASSWORD)
        page.fill(L.CONFIRM_PASSWORD, "a-different-password")
        expect(submit).to_be_enabled()
        submit.click()

    expect(page.get_by_text(L.PASSWORDS_DO_NOT_MATCH)).to_be_visible()
    # Belt and braces: a success banner here would mean the password DID change
    # and every later test in the run is about to fail authentication.
    expect(page.get_by_text("Password changed successfully")).to_have_count(0)


@pytest.mark.issue("ISS-338")
def test_confirm_new_password_has_a_show_hide_toggle_like_its_siblings(page, shot):
    """ISS-338 — "Confirm new password" must offer the same show/hide toggle

    as its "Current password" and "New password" siblings on the same form.
    Today `AccountSettings.tsx` wires a `showCurrent`/`showNew` boolean and an
    eye-icon button to those two fields but never adds a matching `showConfirm`
    for Confirm new password, so it has no toggle button and can never be
    revealed — reproduced 3/3 on a cold /settings/profile load, no other axis
    needed.
    """
    with shot("confirm-password-toggle", 'When I cold-load "/settings/profile"'):
        open_settings(page)

    confirm_field = page.locator(L.CONFIRM_PASSWORD)
    expect(confirm_field).to_be_visible()
    # A sibling toggle button, the same shape the Current/New password fields
    # have — asserted by DOM adjacency rather than a specific selector, since
    # the fix may add any `<button>` sibling.
    sibling_button = confirm_field.locator("xpath=following-sibling::button[1]")
    expect(sibling_button).to_be_visible()


# ── AI Model ─────────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-09-06")
def test_the_model_preference_lists_the_available_models(page, shot):
    """Scenario: The model preference lists the available models"""
    with shot("ai-model", 'When I cold-load "/settings/ai-model"'):
        open_settings(page, "/settings/ai-model")

    expect(page.locator(L.MODEL_SELECT)).to_be_visible()
    expect(page.get_by_text(L.MODEL_NOTE)).to_be_visible()

    labels = page.locator(f"{L.MODEL_SELECT} option").all_text_contents()
    assert any("System Default" in t for t in labels), labels
    # The three tiers, not the exact model list: models are added and retired
    # far more often than the tiers are.
    for tier in ("Haiku", "Sonnet", "Opus"):
        assert any(tier in t for t in labels), f"no {tier} option among {labels}"


@pytest.mark.scenario("S-09-07")
def test_selecting_a_model_shows_its_description(page, shot):
    """Scenario: Selecting a model shows its description"""
    with shot("model-select", 'When I cold-load "/settings/ai-model"'):
        open_settings(page, "/settings/ai-model")

    values = page.locator(f"{L.MODEL_SELECT} option").evaluate_all(
        "opts => opts.map(o => o.value).filter(Boolean)"
    )
    assert values, "the selector offered nothing but System Default"

    with shot("model-described", "And I select a model"):
        page.select_option(L.MODEL_SELECT, values[0])

    # The description sits in a block with the tier badge; assert the block
    # gained prose rather than pinning one model's marketing copy.
    described = page.locator(f"{L.MODEL_SELECT} ~ div p").first
    expect(described).to_be_visible()
    assert len(described.inner_text().strip()) > 20
    expect(page.locator(L.SAVE_MODEL)).to_be_visible()


@pytest.mark.scenario("S-09-08")
@pytest.mark.destructive
def test_saving_a_model_preference_persists_it(page, shot):
    """Scenario: Saving a model preference persists it"""
    open_model_tab(page)
    original = page.locator(L.MODEL_SELECT).input_value()

    values = page.locator(f"{L.MODEL_SELECT} option").evaluate_all(
        "opts => opts.map(o => o.value)"
    )
    target = next(v for v in values if v != original)

    try:
        with shot("model-saved", f"When I select a different model and save"):
            save_model(page, target)

        with shot("model-after-reload", "And I reload the page"):
            page.reload()
            expect(page.locator(L.MODEL_SELECT)).to_be_visible()

        expect(page.locator(L.MODEL_SELECT)).to_have_value(target)
    finally:
        # Restore, or every later run in the suite uses whatever this test left
        # behind — including the live tier.
        #
        # Conditional, and re-reading the value rather than assuming it: if the
        # try block failed BEFORE the save, the preference is already `original`
        # and Save is disabled — restoring unconditionally would then time out
        # and bury the real failure under a teardown error.
        open_model_tab(page)
        if page.locator(L.MODEL_SELECT).input_value() != original:
            save_model(page, original)


@pytest.mark.issue("ISS-292")
@pytest.mark.destructive
@pytest.mark.role("basic")
def test_basic_tier_cannot_persist_a_powerful_model(page, shot):
    """ISS-292 — a basic-tier account must not be able to select and persist
    a "powerful"-tier (premium) model such as Claude Opus 4.6.

    ISS-430 changed the affordance: the API now returns an ``allowed`` flag per
    model, and the selector renders non-entitled options as ``disabled``.
    The test therefore asserts the affordance (option is offered but disabled)
    AND the outcome (even if somehow selected, it must not survive a reload).
    """
    open_model_tab(page)
    original = page.locator(L.MODEL_SELECT).input_value()

    options = page.locator(f"{L.MODEL_SELECT} option").evaluate_all(
        "opts => opts.map(o => ({value: o.value, text: o.textContent, disabled: o.disabled}))"
    )
    opus = next((o for o in options if "Opus" in (o["text"] or "")), None)
    assert opus, f"no Opus (powerful-tier) option offered at all: {options}"

    # ISS-430 key assertion: the option must be present but disabled for basic tier,
    # giving a clear affordance instead of a silent 403 after Save.
    assert opus.get("disabled"), (
        f"ISS-430: Opus option is offered and ENABLED for a basic-tier account — "
        f"non-entitled models must be rendered disabled so the gate is visible "
        f"before Save, not only as a 403 banner after it. option={opus}"
    )

    try:
        with shot(
            "basic-opus-blocked",
            "When a basic-tier account tries to select a powerful model",
        ):
            # The option is disabled, so select_option raises error:optionnotenabled.
            # Force-set via JS to verify the backend 403 also fires (defence-in-depth).
            page.evaluate(
                "(v) => { const s = document.querySelector('[name=\"default-model\"]'); "
                "if (s) s.value = v; }",
                opus["value"],
            )
            page.locator(L.MODEL_SELECT).dispatch_event("change")
            expect(page.locator(L.SAVE_MODEL)).to_be_enabled(timeout=10_000)
            page.click(L.SAVE_MODEL)
            page.wait_for_timeout(settings.SETTLE_MS)

        with shot("basic-opus-reload", "And I reload the page"):
            page.reload()
            expect(page.locator(L.MODEL_SELECT)).to_be_visible()

        assert page.locator(L.MODEL_SELECT).input_value() != opus["value"], (
            "a basic-tier account's powerful-tier model selection "
            f"({opus['value']}) survived a reload — no tier gating enforced"
        )
    finally:
        open_model_tab(page)
        if page.locator(L.MODEL_SELECT).input_value() != original:
            save_model(page, original)


# ── Usage & Limits ───────────────────────────────────────────────────────────


@pytest.mark.scenario("S-09-09")
def test_usage_shows_the_plan_and_its_deliverable_access(page, shot):
    """Scenario: Usage shows the plan and its deliverable access"""
    with shot("usage", 'When I cold-load "/settings/usage"'):
        open_settings(page, "/settings/usage")

    expect(page.get_by_text("Enterprise plan")).to_be_visible()
    expect(
        page.get_by_text(
            "Your plan determines which deliverables you can run and the "
            "features available to you."
        )
    ).to_be_visible()
    expect(page.locator(L.MANAGE_PLAN)).to_be_visible()
    expect(page.get_by_text(L.DELIVERABLE_ACCESS)).to_be_visible()


@pytest.mark.scenario("S-09-10")
@pytest.mark.parametrize(
    ("role", "included", "excluded"),
    [
        ("basic", "Product Requirements", "Custom Workflow"),
        ("enterprise", "Custom Workflow", None),
    ],
)
def test_deliverable_access_reflects_the_tier(page_as, shot, role, included, excluded):
    """Scenario: Deliverable access reflects the tier"""
    page = page_as(role)
    with shot(f"usage-{role}", f'When I cold-load "/settings/usage" as {role}'):
        open_settings(page, "/settings/usage")
        expect(page.get_by_text(L.DELIVERABLE_ACCESS)).to_be_visible()

    expect(page.get_by_text(included, exact=True)).to_be_visible()
    if excluded is not None:
        expect(page.get_by_text(excluded, exact=True)).to_have_count(0)


# ── Constitution ─────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-09-11")
def test_the_constitution_editor_enforces_its_limit(page, shot):
    """Scenario: The constitution editor enforces its limit"""
    with shot("constitution", 'When I cold-load "/settings/constitution"'):
        open_settings(page, "/settings/constitution")

    editor = page.locator(L.CONSTITUTION)
    expect(editor).to_be_visible()
    expect(page.locator(L.SAVE_CONSTITUTION)).to_be_visible()

    before = len(editor.input_value())
    expect(page.get_by_text(f"{before} / {L.CONSTITUTION_CEILING} chars")).to_be_visible()

    typed = "counter check"
    with shot("constitution-typed", "When I type into it"):
        # `type`, not `fill`: the counter is driven by onChange and fill sets the
        # value without one in some builds.
        editor.type(typed)

    expect(
        page.get_by_text(f"{before + len(typed)} / {L.CONSTITUTION_CEILING} chars")
    ).to_be_visible()
    # Not saved — reloading discards it, so nothing to restore.


@pytest.mark.scenario("S-09-12")
@pytest.mark.destructive
def test_a_saved_constitution_persists_across_a_reload(page, shot):
    """Scenario: A saved constitution persists across a reload"""
    open_settings(page, "/settings/constitution")
    editor = page.locator(L.CONSTITUTION)
    expect(editor).to_be_visible()
    original = editor.input_value()

    marker = "E2E S-09-12: answer in exactly one sentence."
    try:
        with shot("constitution-saved", "When I enter an instruction and save it"):
            editor.fill(marker)
            page.click(L.SAVE_CONSTITUTION)
            expect(page.get_by_text("Constitution saved")).to_be_visible()

        with shot("constitution-after-reload", "And I reload the page"):
            page.reload()
            expect(page.locator(L.CONSTITUTION)).to_be_visible()

        expect(page.locator(L.CONSTITUTION)).to_have_value(marker)
    finally:
        # THE contaminating fixture in this suite — the constitution is
        # prepended to every agent on every run, so leaving it set would change
        # the output of every live scenario that follows.
        page.goto("/settings/constitution")
        page.locator(L.CONSTITUTION).wait_for()
        page.locator(L.CONSTITUTION).fill(original)
        if original.strip():
            page.click(L.SAVE_CONSTITUTION)
            expect(page.get_by_text("Constitution saved")).to_be_visible()
        else:
            # Save is disabled for empty content, so an account that started
            # with no constitution is restored by Clear — which only exists
            # while there IS something to clear.
            page.click(L.CLEAR_CONSTITUTION)
            expect(page.get_by_text("Constitution cleared")).to_be_visible()


@pytest.mark.issue("ISS-320")
@pytest.mark.xfail(reason="ISS-320 unfixed", strict=True)
@pytest.mark.destructive
def test_clear_constitution_requires_confirmation_before_deleting(page, shot):
    """ISS-320 — "Clear" must not delete the saved constitution on a single,

    unconfirmed click. Today `handleDelete` fires `DELETE
    /api/settings/constitution` synchronously with no confirm dialog and no
    dependency on "Save constitution" — a misclick permanently destroys the
    standing instructions prepended to every future agent run. The correct
    behaviour requires an explicit confirmation step before the delete
    reaches the backend; dismissing that confirmation must leave the
    persisted value untouched.
    """
    open_settings(page, "/settings/constitution")
    editor = page.locator(L.CONSTITUTION)
    expect(editor).to_be_visible()
    original = editor.input_value()

    marker = "E2E ISS-320: do not delete me without asking."
    try:
        with shot("iss320-saved", "When I save a constitution"):
            editor.fill(marker)
            page.click(L.SAVE_CONSTITUTION)
            expect(page.get_by_text("Constitution saved")).to_be_visible()

        with shot("iss320-clear-clicked", "And I click Clear without confirming"):
            # The autouse dismiss_native_dialogs fixture (conftest.py) already
            # dismisses every native dialog — no second handler needed here.
            # ISS-581: adding a redundant page.on() caused Playwright to raise
            # "Cannot dismiss dialog which is already handled!" when both fired.
            page.click(L.CLEAR_CONSTITUTION)
            page.wait_for_timeout(settings.SETTLE_MS)

        res = api.request(page, "GET", "/api/settings/constitution")
        body = json.loads(res["body"])
        assert body.get("content") == marker, (
            "Clear deleted the saved constitution with no confirmation gate — "
            f"expected an unconfirmed Clear to leave the persisted value "
            f"untouched, got {body!r}"
        )
    finally:
        # The bug under test leaves "Save constitution" disabled after a
        # Clear (its own repro notes this), so restoring via the UI's Save
        # button is unreliable here — go straight to the API, the same way
        # the app's own PUT does, and reload to confirm.
        if original.strip():
            api.request(page, "PUT", "/api/settings/constitution", {"content": original})
        else:
            api.request(page, "DELETE", "/api/settings/constitution")
        page.goto("/settings/constitution")
        expect(page.locator(L.CONSTITUTION)).to_have_value(original)


@pytest.mark.issue("ISS-293")
@pytest.mark.destructive
def test_the_constitution_editor_rejects_content_over_its_stated_limit(page, shot):
    """ISS-293 — the "X / 4000 chars" counter is styled as a hard cap; content

    well over 4000 chars must not save and persist un-truncated. Today the
    textarea has no `maxLength`, Save never disables past the ceiling, and the
    backend accepts and persists the full payload verbatim (1 MiB cap, not
    4000) — so a save of over-limit content survives a reload at full length.
    """
    open_settings(page, "/settings/constitution")
    editor = page.locator(L.CONSTITUTION)
    expect(editor).to_be_visible()
    original = editor.input_value()

    over_limit = "M" * (L.CONSTITUTION_CEILING + 500)
    try:
        with shot("constitution-over-limit", "When I enter content past the stated limit"):
            editor.fill(over_limit)
            page.click(L.SAVE_CONSTITUTION)
            expect(page.get_by_text("Constitution saved")).to_be_visible()

        with shot("constitution-over-limit-reload", "And I reload the page"):
            page.reload()
            expect(page.locator(L.CONSTITUTION)).to_be_visible()
            # The fetched value lands after the initial paint; wait for it to
            # actually arrive (short placeholder text is not the loaded state)
            # rather than reading whatever is in the textarea at reload-instant.
            page.wait_for_function(
                "document.querySelector('textarea[name=\"constitution\"]').value.length > 50"
            )

        persisted_length = len(page.locator(L.CONSTITUTION).input_value())
        assert persisted_length <= L.CONSTITUTION_CEILING, (
            f"saved constitution is {persisted_length} chars, over the stated "
            f"{L.CONSTITUTION_CEILING}-char limit — the counter's cap is not enforced"
        )
    finally:
        page.goto("/settings/constitution")
        page.locator(L.CONSTITUTION).wait_for()
        page.locator(L.CONSTITUTION).fill(original)
        if original.strip():
            page.click(L.SAVE_CONSTITUTION)
            expect(page.get_by_text("Constitution saved")).to_be_visible()
        else:
            page.click(L.CLEAR_CONSTITUTION)
            expect(page.get_by_text("Constitution cleared")).to_be_visible()


@pytest.mark.issue("ISS-482")
@pytest.mark.destructive
def test_switching_tabs_away_from_constitution_requires_confirmation_for_unsaved_draft(page, shot):
    """ISS-482 — switching settings tabs away from Constitution with an unsaved draft
    must ask before discarding it, and must preserve the draft if the user cancels.

    Fixed by FIX-386: Tabs onChange now gates on dirty draft state and calls
    window.confirm before unmounting ConstitutionSection. The draft state was
    lifted from ConstitutionSection's local useState to the parent's
    constitutionContent/constitutionLoadedValue pair so the handler can see it.

    Root cause (AccountSettings.tsx:230-234): `setSection(next)` was called
    unconditionally, immediately turning the `{section === "constitution" && ...}`
    guard false and discarding the component's local `content` state with no warning.
    Clicking back to Constitution re-mounted a fresh component that re-fetched from
    the backend — the typed draft was gone.

    See .knowledge/cards/20260828-2322-ISS-482.md and FIX-386 (20260831-1020).
    """
    # ISS-482: a recognisable sentinel that will never accidentally match any
    # real user constitution. Must NOT be the empty string — an empty textarea
    # may be indistinguishable from "nothing loaded yet" in some UI states.
    _UNSAVED_DRAFT = "ISS-482 e2e sentinel: tab-switch must ask before discarding"

    open_settings(page, "/settings/constitution")
    editor = page.locator(L.CONSTITUTION)
    expect(editor).to_be_visible()
    original = editor.input_value()

    try:
        with shot("before-draft", "Given the Constitution editor is open and clean"):
            # Baseline: confirm the editor is in its saved state before we type.
            expect(page.get_by_text("Constitution saved")).to_have_count(0)

        with shot("draft-typed", "When I type an unsaved draft into Constitution"):
            editor.fill(_UNSAVED_DRAFT)
            # Draft is local-only — "Constitution saved" must NOT appear, proving
            # we are genuinely in an unsaved state before the tab switch.
            expect(page.get_by_text("Constitution saved")).to_have_count(0)

        with shot("tab-switch-attempted", "And I click the Profile tab"):
            # The autouse dismiss_native_dialogs fixture (conftest.py) already
            # handles every dialog and records each message into page.native_dialogs.
            # ISS-581: adding a page.once() here conflicted with that handler —
            # both fired and Playwright raised "Cannot dismiss dialog which is
            # already handled!". Read page.native_dialogs instead.
            dialogs_before = len(page.native_dialogs)
            page.click(L.tab("tab-profile"))
            page.wait_for_timeout(settings.SETTLE_MS)
            dialogs_captured = page.native_dialogs[dialogs_before:]

        # ASSERTION 1 (ISS-482 core): a confirm dialog must have fired before the
        # tab switch committed. Without the fix, none fires and the draft is gone.
        assert dialogs_captured, (
            "ISS-482: no confirm dialog appeared when switching away from "
            "Constitution with an unsaved draft — draft was silently discarded"
        )

        # ASSERTION 2: the dialog message must reference unsaved work so the user
        # understands what they are being asked to confirm.
        assert any(
            "unsaved" in msg.lower() or "discard" in msg.lower()
            for msg in dialogs_captured
        ), (
            f"ISS-482: dialog appeared but message did not mention unsaved work "
            f"or discard: {dialogs_captured}"
        )

        with shot("dismissed-stayed-on-constitution", "Then dismissing the dialog keeps me on Constitution"):
            # Dismissing (Cancel) must NOT navigate to Profile.
            expect(page.locator(L.tab("tab-profile"))).not_to_have_attribute(
                "aria-selected", "true"
            )

        with shot("back-to-constitution", "And the draft is still in the editor"):
            # The Constitution tab should still be visible — no re-mount needed.
            editor = page.locator(L.CONSTITUTION)
            expect(editor).to_be_visible()

        # ASSERTION 3 (ISS-482 key invariant): dismissing the dialog must have
        # preserved the in-memory draft. Without the fix, unmount discards it and
        # re-mounting re-fetches the backend value — the draft is gone forever.
        assert editor.input_value() == _UNSAVED_DRAFT, (
            f"ISS-482: draft lost after dismissing confirm dialog — "
            f"expected sentinel value, got {editor.input_value()!r}. "
            f"The confirm appeared but the state-lift did not preserve the draft."
        )

    finally:
        # Restore the original constitution so a leftover sentinel value never
        # contaminates live runs. The constitution is prepended to EVERY agent.
        page.goto("/settings/constitution")
        page.locator(L.CONSTITUTION).wait_for()
        page.locator(L.CONSTITUTION).fill(original)
        if original.strip():
            page.click(L.SAVE_CONSTITUTION)
            expect(page.get_by_text("Constitution saved")).to_be_visible()
        else:
            if page.locator(L.CLEAR_CONSTITUTION).count() > 0:
                page.click(L.CLEAR_CONSTITUTION)
                expect(page.get_by_text("Constitution cleared")).to_be_visible()


# ── Security ─────────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-09-13")
def test_mfa_is_unavailable_for_an_externally_managed_account(page, shot):
    """Scenario: MFA is unavailable for an externally-managed account"""
    with shot("security", 'When I cold-load "/settings/security"'):
        open_settings(page, "/settings/security")

    expect(page.get_by_text(L.SECURITY_INTRO)).to_be_visible()

    if mfa_status(page).get("supported"):
        pytest.skip("this pool reports MFA as supported — see S-09-14 for that branch")

    expect(page.get_by_text(L.NOT_AVAILABLE)).to_be_visible()
    expect(page.get_by_text(L.LOCAL_ACCOUNT_NO_MFA)).to_be_visible()
    expect(page.get_by_text(L.EMAIL_CODES)).to_have_count(0)
    expect(page.get_by_text(L.AUTHENTICATOR)).to_have_count(0)


@pytest.mark.scenario("S-09-14")
def test_security_lists_both_second_factor_methods(page, shot):
    """Scenario: Security lists both second-factor methods"""
    with shot("security-methods", 'When I cold-load "/settings/security"'):
        open_settings(page, "/settings/security")

    status = mfa_status(page)
    if not status.get("supported"):
        pytest.skip("every seeded account is Cognito-managed; no method rows render")
    if not status.get("email_available"):
        pytest.skip("the pool offers no email MFA, so only one row can render")

    expect(page.get_by_text(L.EMAIL_CODES)).to_be_visible()
    expect(page.get_by_text(L.AUTHENTICATOR)).to_be_visible()
    # "whether it is active" is an Active badge or its absence — assert the row
    # states one of the two rather than which.
    for title in (L.EMAIL_CODES, L.AUTHENTICATOR):
        row = page.locator(f'div:has(> div p:text-is("{title}"))').first
        assert row.inner_text().strip(), f"the {title} row said nothing"


@pytest.mark.scenario("S-09-15")
def test_email_codes_are_a_toggle_not_a_wizard(page, shot):
    """Scenario: Email codes are a toggle, not a wizard"""
    with shot("security-email-toggle", 'When I cold-load "/settings/security"'):
        open_settings(page, "/settings/security")

    status = mfa_status(page)
    if not status.get("email_available"):
        pytest.skip("email MFA is not available for this pool")

    on = "EMAIL_OTP" in status.get("factors", [])
    expect(page.get_by_role("button", name="Turn off" if on else "Turn on")).to_be_visible()
    # No secret, no QR, no confirmation step — the absence IS the scenario.
    assert page.locator('input[type="text"]').count() == 0
    assert page.locator("svg[aria-label*='QR' i], img[alt*='QR' i], canvas").count() == 0


@pytest.mark.scenario("S-09-16")
def test_the_authenticator_row_offers_no_control_at_all(page, shot):
    """Scenario: The authenticator row offers no control at all"""
    with shot("security-totp", 'When I cold-load "/settings/security"'):
        open_settings(page, "/settings/security")

    if not mfa_status(page).get("supported"):
        pytest.skip("every seeded account is Cognito-managed; no method rows render")

    row = page.locator(f'div:has(> div p:text-is("{L.AUTHENTICATOR}"))').first
    expect(row).to_be_visible()
    # /api/auth/mfa/totp/associate and /verify both exist. This screen
    # deliberately calls neither, and that decision is asserted so its absence
    # does not get filed as a bug.
    assert row.locator("button").count() == 0, "the authenticator row grew a control"


@pytest.mark.scenario("S-09-17")
def test_an_environment_with_no_methods_says_so(page, shot):
    """Scenario: An environment with no methods says so"""
    with shot("security-no-methods", 'When I cold-load "/settings/security"'):
        open_settings(page, "/settings/security")

    status = mfa_status(page)
    if not status.get("supported"):
        pytest.skip("every seeded account is Cognito-managed; the panel never mounts")
    if status.get("email_available") or "SOFTWARE_TOKEN_MFA" in status.get("factors", []):
        pytest.skip("this pool has a method available, so the empty state cannot render")

    expect(page.get_by_text(L.NO_METHODS)).to_be_visible()
    expect(page.get_by_text("Contact your administrator if you need one.")).to_be_visible()


@pytest.mark.scenario("S-09-18")
def test_email_mfa_changes_the_account_recovery_story(page, shot):
    """Scenario: Email MFA changes the account-recovery story"""
    with shot("security-recovery", 'When I cold-load "/settings/security"'):
        open_settings(page, "/settings/security")

    if not mfa_status(page).get("email_available"):
        pytest.skip("email MFA is not available for this pool, so the note is correctly absent")

    expect(page.get_by_text(L.RECOVERY_NOTE)).to_be_visible()


@pytest.mark.scenario("S-09-19")
def test_security_is_a_tab_not_a_page(page, shot):
    """Scenario: Security is a tab, not a page"""
    with shot("security-is-a-tab", 'When I cold-load "/settings/security"'):
        open_settings(page, "/settings/security")

    # The chrome belongs to the parent: one heading, one subtitle, one tab strip
    # — the standalone page was removed precisely because it rendered a second
    # copy of each.
    expect(page.get_by_role("heading", name=L.HEADING)).to_have_count(1)
    expect(page.get_by_text(L.SUBTITLE)).to_have_count(1)
    expect(page.get_by_role("tablist")).to_have_count(1)
    for testid, _label, _route in L.TABS:
        expect(page.locator(L.tab(testid))).to_be_visible()
