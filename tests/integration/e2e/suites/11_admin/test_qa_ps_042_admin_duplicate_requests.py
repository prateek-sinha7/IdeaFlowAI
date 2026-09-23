"""BUGS.md#qa-ps-042 — Admin page calls GET /api/me twice and
GET /api/users twice — 2 redundant calls on page load.

Cards:
- ISS-789 — root. `admin/page.tsx:177-198`'s mount effect has no in-flight
  guard, so a client-side (SPA) navigation into `/admin` StrictMode
  double-invokes it, firing `getMe`/`adminListUsers` twice each. A cold
  reload does not reproduce it — only SPA nav does.
- ISS-816 — completes the root cause: confirms `adminListUsers` has exactly
  one call site (no blast radius beyond this page) and that the fix belongs
  in the shared `request()`/`fetchWithAuth()` layer in `lib/api.ts`, not a
  per-component guard. No separately observable behaviour beyond ISS-789's
  duplicate-count assertion — the same test proves both.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework import settings
from framework.locators import admin as L
from framework.locators import shell as SHELL


def _count(urls: list[str], path: str) -> int:
    return sum(1 for u in urls if path in u)


def _spa_nav_to_admin(page) -> list[str]:
    """Reach /admin via a client-side navigation, not a cold load — the
    duplication only reproduces on SPA nav (ISS-789). Requests are only
    collected from the click onward, so /dashboard's own boot fetches
    (a different, unrelated call site) don't contaminate the count."""
    page.goto("/dashboard")
    page.wait_for_timeout(settings.SETTLE_MS)

    requests: list[str] = []
    page.on("request", lambda req: requests.append(req.url))

    page.click(SHELL.ACCOUNT_MENU)
    expect(page.locator(SHELL.MENU)).to_be_visible()
    SHELL.menu_item(page, SHELL.ADMIN_MENU_ITEM).click()
    expect(page.get_by_text(L.HEADING)).to_be_visible()
    page.wait_for_timeout(1500)
    return requests


@pytest.mark.issue("ISS-789")
def test_admin_page_fetches_users_once_on_spa_nav(page):
    """ISS-789/ISS-816 — navigating into `/admin` from the account menu must
    fetch `GET /api/admin/users` exactly once, not twice. (`GET /api/auth/me`
    duplicates the same way per ISS-789's own network capture, but the
    browser's own HTTP cache can mask a same-tick duplicate `me` request at
    the Playwright `request` event level, so `adminListUsers` — which has no
    such caching and reliably reproduces 2x on every run — is the
    deterministic assertion for this shared mount-effect defect.)"""
    requests = _spa_nav_to_admin(page)

    users_count = _count(requests, "/api/admin/users")

    assert users_count == 1, (
        f"SPA nav into /admin fetched /api/admin/users {users_count}x, "
        f"expected 1x — requests: {requests}"
    )
