"""Keyboard-operability proofs for BUG-20260828-025521-library-hooks.

Not part of screens/08-library.feature.md — no `scenario` marker. Each test
here proves one ISS card from that bug and is paired with
`@pytest.mark.xfail(strict=True)` until the fix lands.

Card selector matches `framework/locators/library.py`'s note: `.cursor-pointer`
alone under-matches (beta cards use `cursor-not-allowed`) and over-matches
against layout chrome, so each grid is scoped to its own known card class.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

CARD = "div.bg-surface-card.group"


def open_library(page, query: str = "") -> None:
    page.goto(f"/library{query}")
    expect(page.get_by_role("heading", name="Library")).to_be_visible()
    expect(page.locator(CARD).first).to_be_visible()


@pytest.mark.issue("ISS-222")
def test_hook_card_is_reachable_and_activatable_by_keyboard(page):
    """ISS-222 — Hooks tab cards must be Tab-reachable and Enter-activatable."""
    open_library(page, "?tab=hooks")
    first = page.locator(CARD).first

    expect(first).to_have_attribute("tabindex", "0")

    first.focus()
    expect(first).to_be_focused()

    page.keyboard.press("Enter")
    page.wait_for_url("**/library/hooks/**")


@pytest.mark.issue("ISS-270")
def test_agent_card_is_reachable_and_activatable_by_keyboard(page):
    """ISS-270 — Agents tab cards share the same missing keyboard affordance."""
    open_library(page)
    first = page.locator(CARD).first

    expect(first).to_have_attribute("tabindex", "0")

    first.focus()
    expect(first).to_be_focused()

    page.keyboard.press("Enter")
    page.wait_for_url("**/library/agents/**")


@pytest.mark.issue("ISS-271")
def test_skill_card_is_reachable_and_activatable_by_keyboard(page):
    """ISS-271 — Skills tab active-skills cards share the same gap."""
    open_library(page, "?tab=skills")
    first = page.locator(CARD).first

    expect(first).to_have_attribute("tabindex", "0")

    first.focus()
    expect(first).to_be_focused()

    page.keyboard.press("Enter")
    page.wait_for_url("**/library/skills/**")


@pytest.mark.issue("ISS-272")
def test_escape_closes_the_hook_detail_modal(page):
    """ISS-272 — the hook detail modal must close on Escape."""
    open_library(page, "?tab=hooks")
    page.locator(CARD).first.click()
    page.wait_for_url("**/library/hooks/**")

    # The modal's Copy button is the one stable marker that the detail view
    # is open (module docstring corrects the spec: this route renders a
    # scrim-and-panel modal, not a role="dialog" drawer).
    copy_button = page.get_by_role("button", name="Copy", exact=True)
    expect(copy_button).to_be_visible()

    page.keyboard.press("Escape")
    expect(copy_button).to_be_hidden()
