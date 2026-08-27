"""Launching real runs, and answering the gates they stop at.

The live tier does what the offline tier cannot: it starts work, waits for it,
and makes the human decision the product asks for. Everything here is only
reached under `-m live`.

**"Run workflow" does not navigate.** It starts the run and leaves you on the
launch panel — the header's running-pipeline badge and the run history are how
a user finds what they just started. `launch()` therefore posts the brief and
then goes looking, rather than waiting for a URL that never comes.

Briefs are hello-world scale on purpose. These are smoke tests: the question is
whether the pipeline runs, gates, resumes and delivers, not whether the model
wrote anything good.
"""

from __future__ import annotations

import re
import time

from playwright.sync_api import expect

from framework import settings
from framework.locators import home_catalog as HOME
from framework.locators import run_detail as RD
from framework.locators import run_history as RH

# Ollama-backed and local, but a five-agent pipeline still takes minutes.
LAUNCH_TIMEOUT_MS = 120_000
RUN_TIMEOUT_MS = 600_000

BRIEF = "Say hello to the world. Keep it to one short sentence."

GATE_ACTIONS = '[data-testid="chat-gate-actions"]'
GATE_PROMPT = '[data-testid="chat-gate-choice-prompt"]'
GATE_CANCEL = '[data-testid="chat-gate-cancel"]'
GATE_APPROVE = '[data-testid="chat-gate-approve"]'
GATE_REJECT = '[data-testid="chat-gate-reject"]'
GATE_STATUS = '[data-testid="lane-gate-status"]'
CHOICE_PREFIX = "chat-gate-choice-"


def launch(page, title: str, brief: str = BRIEF) -> str:
    """Start `title` from the catalogue and return the new run's id.

    The brief is made unique so the run can be found again in a history that
    may hold several started by the same fixture.
    """
    stamp = f"{brief} [{int(time.time() * 1000) % 10_000_000}]"

    page.goto("/dashboard")
    expect(page.get_by_text(HOME.HEADING)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS // 2)
    page.locator(HOME.card(title)).click()
    expect(page.locator('textarea[name="brief"]')).to_be_visible(timeout=30_000)
    page.wait_for_timeout(settings.SETTLE_MS // 2)

    page.fill('textarea[name="brief"]', stamp)
    page.wait_for_timeout(600)
    page.get_by_role("button", name="Run workflow").click()

    # No navigation follows. Find the run in the history instead.
    deadline = time.time() + LAUNCH_TIMEOUT_MS / 1000
    while time.time() < deadline:
        page.goto("/runs")
        expect(page.locator(RH.ROW).first).to_be_visible()
        page.wait_for_timeout(settings.SETTLE_MS // 2)
        match = next((label for label in RH.rows(page) if stamp[:50] in label), None)
        if match:
            page.locator(f'{RH.ROW}[aria-label="{match}"]').first.click()
            wait_for_url_containing(page, "/runs/")
            return page.url.split("/runs/")[1].split("/")[0].split("?")[0]
        page.wait_for_timeout(3000)
    raise AssertionError(f"the run for {title!r} never appeared in the history")


def wait_for_url_containing(page, fragment: str, timeout_ms: int = 60_000) -> None:
    remaining = timeout_ms
    while remaining > 0:
        if fragment in page.url:
            return
        page.wait_for_timeout(250)
        remaining -= 250
    raise AssertionError(f"the page never reached {fragment!r}; it is at {page.url}")


def status(page) -> str:
    return page.locator(RD.RUN_STATUS).inner_text().strip() if page.locator(RD.RUN_STATUS).count() else ""


def wait_until(page, predicate, what: str, timeout_ms: int = RUN_TIMEOUT_MS) -> None:
    """Poll the run surface until `predicate(page)` holds.

    Polls rather than waiting on an event: the run streams over a websocket the
    test does not own, and a missed frame would hang a wait that never times
    out on its own.
    """
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        if predicate(page):
            return
        if status(page).lower() in ("failed", "cancelled"):
            raise AssertionError(
                f"the run ended as {status(page)!r} while waiting for {what}"
            )
        page.wait_for_timeout(5000)
        page.reload()
        page.wait_for_timeout(settings.SETTLE_MS)
    raise AssertionError(f"timed out after {timeout_ms / 1000:.0f}s waiting for {what}")


def at_gate(page) -> bool:
    return page.locator(GATE_ACTIONS).count() > 0


def is_done(page) -> bool:
    return status(page).lower() in ("done", "completed")


def choices(page) -> list[str]:
    """The choice values this gate offers, read from its own testids.

    `chat-gate-choice-<value>` is templated on the value, so the set is
    data-dependent — enumerate it, never hard-code the suffixes.
    """
    return page.evaluate(
        """(prefix) => [...document.querySelectorAll('[data-testid^="' + prefix + '"]')]
             .map(e => e.dataset.testid.slice(prefix.length))
             .filter(v => v && v !== 'prompt')""",
        CHOICE_PREFIX,
    )


def answer_choice(page, value: str) -> None:
    """Make the human decision this gate is waiting for."""
    page.locator(f'[data-testid="{CHOICE_PREFIX}{value}"]').click()
    page.wait_for_timeout(settings.SETTLE_MS)


def approve(page) -> None:
    page.locator(GATE_APPROVE).first.click()
    page.wait_for_timeout(settings.SETTLE_MS)
