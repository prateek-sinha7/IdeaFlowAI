"""BUGS.md#qa-ps-035 — Account Settings fires redundant duplicate API calls
and fetches run history / workflow data it never displays.

Cards:
- ISS-781 — `/settings/profile` fires `GET /api/runs` and `GET /api/workflows`
  on a page that shows neither run history nor a workflow catalog
  (`RunConnectionProvider`/`getWorkflows()` naming bug, mounted app-wide).
- ISS-801 — `AccountSettings.tsx`'s own unguarded `Promise.all` mount effect
  double-fires `getMe`/`getPreferences`/`getCapabilities` under `next dev`.
- ISS-799 — the Security and Constitution tabs repeat the same unguarded
  mount-effect shape for `GET /api/auth/mfa` and
  `GET /api/settings/constitution`.

Not part of screens/09-settings.feature.md — no `scenario` marker.
"""

from __future__ import annotations

import pytest

from framework import settings


def _collect_requests(page) -> list[str]:
    seen: list[str] = []
    page.on("request", lambda req: seen.append(req.url))
    return seen


def _count(urls: list[str], path: str) -> int:
    return sum(1 for u in urls if path in u)


@pytest.mark.issue("ISS-781")
def test_settings_profile_does_not_fetch_runs_or_workflows(page):
    """ISS-781 — `/settings/profile` shows no run history and no workflow
    catalog. Decision 2026-09-23 (option a, ESCALATIONS.md#qa-ps-035): the app
    shell's one `/api/runs?limit=50` (AppHeader's "N Running" badge, the SSE
    re-attach) and one `/api/workflows` (header labels) are intended on every
    route, so it may fetch each AT MOST ONCE — a second call is a duplicate."""
    requests = _collect_requests(page)

    page.goto("/settings/profile")
    page.wait_for_timeout(settings.SETTLE_MS)

    runs_calls = [u for u in requests if "/api/runs" in u]
    workflows_calls = [u for u in requests if "/api/workflows" in u]

    assert len(runs_calls) <= 1 and len(workflows_calls) <= 1, (
        "settings/profile fetched the shell's run list / workflow catalog "
        f"more than once: runs={runs_calls} workflows={workflows_calls}"
    )


@pytest.mark.issue("ISS-801")
def test_settings_profile_fetches_me_preferences_capabilities_once_each(page):
    """ISS-801 — `AccountSettings.tsx`'s mount effect must call
    `getMe`/`getPreferences`/`getCapabilities` exactly once each, not
    duplicate them via an unguarded re-run."""
    requests = _collect_requests(page)

    page.goto("/settings/profile")
    page.wait_for_timeout(settings.SETTLE_MS)

    me_count = _count(requests, "/api/auth/me")
    prefs_count = _count(requests, "/api/settings/preferences")
    caps_count = _count(requests, "/api/capabilities")

    assert (me_count, prefs_count, caps_count) == (1, 1, 1), (
        f"expected one call each, saw /api/auth/me={me_count} "
        f"/api/settings/preferences={prefs_count} /api/capabilities={caps_count} "
        f"— requests: {requests}"
    )


@pytest.mark.issue("ISS-799")
def test_settings_security_tab_fetches_mfa_status_once(page):
    """ISS-799 — the Security tab's mount effect (`SecuritySection.tsx`)
    must fetch `/api/auth/mfa` exactly once per cold load."""
    requests = _collect_requests(page)

    page.goto("/settings/security")
    page.wait_for_timeout(settings.SETTLE_MS)

    mfa_count = _count(requests, "/api/auth/mfa")

    assert mfa_count == 1, (
        f"expected one call to /api/auth/mfa, saw {mfa_count} — requests: {requests}"
    )


@pytest.mark.issue("ISS-799")
def test_settings_constitution_tab_fetches_constitution_once(page):
    """ISS-799 — the Constitution tab's mount effect
    (`AccountSettings.tsx`'s `ConstitutionSection`) must fetch
    `/api/settings/constitution` exactly once per cold load."""
    requests = _collect_requests(page)

    page.goto("/settings/constitution")
    page.wait_for_timeout(settings.SETTLE_MS)

    constitution_count = _count(requests, "/api/settings/constitution")

    assert constitution_count == 1, (
        f"expected one call to /api/settings/constitution, saw "
        f"{constitution_count} — requests: {requests}"
    )
