"""BUGS.md#qa-ps-039 — Dashboard fires 10 API requests with analytics/summary
called 4x and runs?limit=50 called 2x on a single cold /dashboard load — 6
redundant fetches waste 81 KB.

Cards:
- ISS-784 — `HomeLaunchGrid.tsx`'s own unguarded mount effect (no dedupe
  guard) double-fires `GET /api/analytics/summary?range=all` under `next
  dev`'s StrictMode double-invoke.
- ISS-808 — `page.tsx:990-1007`'s unguarded `[isAuthenticated]` effect (not
  a HomeLaunchGrid-local fetch) is the actual source of the
  `runs?limit=50` doubling.
- ISS-807 — that same `page.tsx` effect's `getWorkflowDefinitions()` call
  feeds a `homeWorkflows` prop `DashboardLayout` accepts and never reads —
  a wholly wasted `GET /api/workflows` round trip, additive to ISS-808's
  doubling.
- ISS-811 — `HomeLaunchGrid` unmounts/remounts on every `mainView` toggle
  back to Home (`DashboardLayout.tsx:2872`), so ISS-784's doubled
  `analytics/summary` fetch likely recurs on a warm revisit too, not only
  a cold `/dashboard` load.

Not part of screens/02-home-catalog.feature.md — no `scenario` marker.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework import settings
from framework.locators import home_catalog as L
from framework.locators import shell as SHELL


def _collect_requests(page) -> list[str]:
    seen: list[str] = []
    page.on("request", lambda req: seen.append(req.url))
    return seen


def _count(urls: list[str], fragment: str) -> int:
    return sum(1 for u in urls if fragment in u)


@pytest.mark.issue("ISS-784")
def test_dashboard_fetches_analytics_summary_once_on_cold_load(page):
    """ISS-784 — a cold `/dashboard` load must call
    `GET /api/analytics/summary?range=all` exactly once, not twice."""
    requests = _collect_requests(page)

    page.goto("/dashboard")
    expect(page.get_by_text(L.HEADING)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS)

    count = _count(requests, "/api/analytics/summary")

    assert count == 1, (
        f"expected one call to /api/analytics/summary, saw {count} — "
        f"requests: {requests}"
    )


@pytest.mark.issue("ISS-808")
def test_dashboard_fetches_runs_limit_50_once_on_cold_load(page):
    """ISS-808 — `page.tsx`'s `[isAuthenticated]` mount effect must call
    `GET /api/runs?limit=50` exactly once per `/dashboard` load, not
    twice."""
    requests = _collect_requests(page)

    page.goto("/dashboard")
    expect(page.get_by_text(L.HEADING)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS)

    count = _count(requests, "/api/runs?limit=50")

    assert count == 1, (
        f"expected one call to /api/runs?limit=50, saw {count} — "
        f"requests: {requests}"
    )


@pytest.mark.issue("ISS-807")
def test_dashboard_fetches_workflows_once_with_no_discarded_call(page):
    """ISS-807 — `page.tsx`'s `getWorkflowDefinitions()` call computes
    `homeWorkflows` and hands it to `DashboardLayout`, which never reads it.
    That call is additive to whatever fetches the catalog for real
    (`globalSlice`'s `fetchWorkflows` thunk, consumed by `HomeLaunchGrid`
    via `state.global.workflows`), so a cold `/dashboard` load must settle
    to exactly one `GET /api/workflows` call — the used one — not one used
    plus one wasted (times however many StrictMode doubles each)."""
    requests = _collect_requests(page)

    page.goto("/dashboard")
    expect(page.get_by_text(L.HEADING)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS)

    count = _count(requests, "/api/workflows")

    assert count == 1, (
        f"expected one call to /api/workflows, saw {count} — "
        f"requests: {requests}"
    )


@pytest.mark.issue("ISS-811")
def test_dashboard_fetches_analytics_summary_once_on_warm_revisit(page):
    """ISS-811 — `HomeLaunchGrid` mounts only while `mainView === "home"`
    (`DashboardLayout.tsx:2872`), so switching to another tab and back
    unmounts and remounts it. Its own `analytics/summary` fetch
    (ISS-784's confirmed effect) must still fire at most once per Home
    visit, not twice, on a WARM revisit — no full page reload in between.

    `at most once`, not `exactly once`: ISS-811's own "Impact if confirmed"
    prescribes "a cache/dedup layer keyed by request ... not component-local
    state", and that is what landed (`api.ts`'s `cachedGet`, 30 s
    `SHARED_GET_TTL_MS` — FIX-617). A revisit inside the TTL is therefore
    correctly served with ZERO requests, and `== 1` would flip to `== 0`
    purely on whether the tab toggle outran a wall clock (`SETTLE_MS` is
    env-tunable). The defect this test guards is the DOUBLING."""
    page.goto("/dashboard")
    expect(page.get_by_text(L.HEADING)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS)

    # Leave Home for another tab, then come back — client-side, no reload.
    SHELL.nav(page, "Library").click()
    page.wait_for_timeout(settings.SETTLE_MS)

    requests = _collect_requests(page)

    SHELL.nav(page, "Home").click()
    expect(page.get_by_text(L.HEADING)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS)

    count = _count(requests, "/api/analytics/summary")

    assert count <= 1, (
        f"expected at most one call to /api/analytics/summary on the warm "
        f"revisit, saw {count} — requests: {requests}"
    )
