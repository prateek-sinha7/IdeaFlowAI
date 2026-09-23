"""BUGS.md#qa-ps-046 — Custom workflow builder loads run history not needed
on the composer.

Cards:
- ISS-798 — original 3/3 cold-start reproduction of `/workflows/new` firing
  more requests than the composer needs, including `GET /api/runs?limit=50`
  (the composer shows no run history).
- ISS-832 — root-cause completion: the composer's own `/api/capabilities`
  duplication is already closed by FIX-617's `cachedGet()`. What remains is
  `page.tsx`'s unconditional `[isAuthenticated]` mount effect
  (`frontend/src/app/[...view]/page.tsx:990-1007`, already root-caused for
  `/dashboard` by ISS-808) firing `GET /api/runs?limit=50` on every
  authenticated route via the app's single catch-all — including
  `/workflows/new`, which renders no run list at all.

Not part of screens/04-composer-canvas.feature.md — no `scenario` marker.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework import settings
from framework.locators import composer as L


@pytest.mark.issue("ISS-798")
@pytest.mark.issue("ISS-832")
def test_workflows_new_does_not_fetch_run_history(page):
    """ISS-832 — a cold `/workflows/new` load must call
    `GET /api/runs?limit=50` AT MOST ONCE. The composer renders no run history,
    but decision 2026-09-23 (option a, ESCALATIONS.md#qa-ps-046) keeps the app
    shell's one run-list fetch (AppHeader's "N Running" badge, the SSE
    re-attach) on every route — only a duplicate is a defect."""
    requests: list[str] = []
    page.on(
        "request",
        lambda req: requests.append(req.url)
        if "/api/runs" in req.url
        else None,
    )

    page.goto("/workflows/new")
    expect(page.locator(L.HEADER_SUMMARY)).to_be_visible()
    expect(page.locator(L.BRIEF_NODE)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS)

    runs_50 = [u for u in requests if "limit=50" in u]

    assert len(runs_50) <= 1, (
        f"ISS-832: /workflows/new must fetch run history at most once "
        f"(the app shell's own fetch), saw: {runs_50} — "
        f"all /api/runs requests: {requests}"
    )
