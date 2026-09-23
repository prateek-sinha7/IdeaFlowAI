"""ISS-782 (QA-PS-036, `BUGS.md#qa-ps-036`). `/analytics` fires duplicate
requests for `/api/analytics/summary`, `/api/settings/preferences` and
`/api/capabilities` (one call site each in `AnalyticsPage.tsx`, but no shared
request cache so React StrictMode's mount→unmount→remount doubles every one
of them), plus unused `/api/runs` and `/api/workflows` calls that come from
the always-mounted `RunConnectionProvider`/`app/[...view]/page.tsx` pre-fetch,
not from anything `/analytics` itself displays.

See `.knowledge/cards/20260922-1610-ISS-782.md`.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework.locators import analytics as L


@pytest.mark.issue("ISS-782")
def test_analytics_fetches_each_endpoint_once_and_skips_unused_data(page, shot):
    """ISS-782 — a cold `/analytics` load must call
    analytics/summary, settings/preferences and capabilities exactly once
    each, and /api/runs and /api/workflows AT MOST ONCE each. Decision
    2026-09-23 (option a, ESCALATIONS.md#qa-ps-036): those two are the app
    shell's own fetches (AppHeader's badge and labels, the SSE re-attach),
    intended on every route — only a duplicate is a defect."""
    requests: list[str] = []
    page.on(
        "request",
        lambda req: requests.append(req.url) if "/api/" in req.url else None,
    )

    with shot("analytics", 'When I cold-load "/analytics"'):
        page.goto("/analytics")
        expect(page.get_by_text(L.HEADING).first).to_be_visible()
        expect(page.get_by_text("TOTAL RUNS")).to_be_visible()
        page.wait_for_timeout(2_000)

    def count(fragment: str) -> int:
        return sum(1 for u in requests if fragment in u)

    summary_n = count("/api/analytics/summary")
    prefs_n = count("/api/settings/preferences")
    caps_n = count("/api/capabilities")
    runs_n = count("/api/runs")
    workflows_n = count("/api/workflows")

    assert summary_n == 1 and prefs_n == 1 and caps_n == 1, (
        f"ISS-782: /analytics should call each shared endpoint exactly once, "
        f"got summary={summary_n} preferences={prefs_n} capabilities={caps_n}: "
        f"{requests}"
    )
    assert runs_n <= 1 and workflows_n <= 1, (
        f"ISS-782: /analytics should call /api/runs and /api/workflows at most "
        f"once each (the app shell's own fetches), got runs={runs_n} "
        f"workflows={workflows_n}: {requests}"
    )
