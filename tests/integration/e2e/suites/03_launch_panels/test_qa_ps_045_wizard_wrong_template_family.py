"""BUGS.md#qa-ps-045 — Create Prototype wizard fires duplicate GETs and loads
PPT template assets on a prototype-only page. Root cause:
`LaunchWizard.tsx:617-654`'s mount effect calls both `listPrototypeTemplates`
and `listPPTTemplates` unconditionally, regardless of `mode`.

Cards:
- ISS-793 — root cause card for QA-PS-045. `/create/prototype` (mode
  "prototype", web family) must not fetch `GET /api/ppt/templates` — that
  template family is never read on this route.
- ISS-828 — sibling of ISS-793: the same unguarded effect also loads the
  wrong family on `/create/ppt` (mode "ppt", deck family), which must not
  fetch `GET /api/prototype/templates`.

Not part of a screens/*.feature.md file — no `scenario` marker.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from framework import settings


def _collect_requests(page) -> list[str]:
    seen: list[str] = []
    page.on("request", lambda req: seen.append(req.url))
    return seen


def _count(urls: list[str], fragment: str) -> int:
    return sum(1 for u in urls if fragment in u)


@pytest.mark.issue("ISS-793")
def test_prototype_wizard_does_not_fetch_ppt_templates(page):
    """ISS-793 — opening /create/prototype (web family) must not call
    GET /api/ppt/templates; that catalog is never rendered on this route."""
    requests = _collect_requests(page)

    page.goto("/create/prototype")
    expect(page.get_by_text("Configure your prototype")).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS)

    count = _count(requests, "/api/ppt/templates")

    assert count == 0, (
        f"expected no calls to /api/ppt/templates on /create/prototype, "
        f"saw {count} — requests: {requests}"
    )


@pytest.mark.issue("ISS-828")
def test_ppt_wizard_does_not_fetch_prototype_templates(page):
    """ISS-828 — opening /create/ppt (deck family) must not call
    GET /api/prototype/templates; that catalog is never rendered on this
    route — the inverse of ISS-793's prototype-loads-PPT-templates finding."""
    requests = _collect_requests(page)

    page.goto("/create/ppt")
    expect(page.get_by_text("Configure your")).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS)

    count = _count(requests, "/api/prototype/templates")

    assert count == 0, (
        f"expected no calls to /api/prototype/templates on /create/ppt, "
        f"saw {count} — requests: {requests}"
    )
