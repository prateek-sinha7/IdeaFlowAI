"""Navigation waits that survive a redirect chain.

`page.wait_for_url` attaches to the in-flight navigation and RAISES
`net::ERR_ABORTED` when a second navigation cancels the first. That is exactly
what a session-expiry redirect does — `/login` arrives, decides it has a
`?expired=true` to honour, and navigates again — so a test asserting on the
destination fails intermittently on the way to it.

Polling `page.url` reads the frame's current address without attaching to
anything, so a redirect chain is invisible to it.
"""

from __future__ import annotations

from framework import settings


def wait_for_url_containing(page, fragment: str, timeout_ms: int | None = None) -> None:
    """Block until the address bar contains `fragment`."""
    remaining = settings.LOGIN_TIMEOUT_MS if timeout_ms is None else timeout_ms
    while remaining > 0:
        if fragment in page.url:
            return
        page.wait_for_timeout(250)
        remaining -= 250
    raise AssertionError(f"the page never reached {fragment!r}; it is at {page.url}")


def settle_after_redirect(page) -> None:
    """Wait for the page to stop navigating, tolerating aborted loads.

    `wait_for_load_state` raises the same ERR_ABORTED when it is the cancelled
    navigation being waited on, so it is retried rather than trusted.
    """
    for _ in range(4):
        try:
            page.wait_for_load_state("load")
            break
        except Exception:
            page.wait_for_timeout(500)
    page.wait_for_timeout(settings.SETTLE_MS // 2)
