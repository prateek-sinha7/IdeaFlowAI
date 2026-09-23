"""ISS-695 — Upload custom template "From URL" fails for every external
HTTPS URL, on both /create/prototype and /create/ppt.

`fetch_url_for_template` (`backend/app/api/prototype_templates.py:349`)
builds `httpx.AsyncClient()` with no `verify=` override, so it trusts only
httpx's bundled certifi CA list. This environment sits behind a
TLS-intercepting proxy whose CA is outside that bundle, so every outbound
`https://` fetch fails TLS verification and the modal shows the generic
"Could not reach that URL. Check the address and try again." for a
perfectly reachable public URL. `example.com` reproduces this identically to
the reporter's `hexaware.com` (see ISS-695's card) — the fetcher fails for
100% of external targets in this environment, not a specific host.

Two tests, one per route — the card's own repro confirms both
`/create/prototype` and `/create/ppt` share the identical failure via the
same `CustomTemplateModal` / `/api/prototype/fetch-url` endpoint.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect


def _fetch_custom_template_url(page, route: str) -> None:
    page.goto(route)
    page.click('button:has-text("Upload custom")')
    page.click('button:has-text("From URL")')
    page.fill('input[name="template-url"]', "https://example.com/")
    page.click('button:has-text("Fetch")')


@pytest.mark.issue("ISS-695")
def test_upload_custom_template_from_url_succeeds_on_prototype(page, shot):
    """Fetching a valid, publicly reachable HTTPS URL as a custom template
    must succeed, not show "Could not reach that URL"."""
    with shot("fetch-url-prototype", 'When I fetch https://example.com/ as a custom template on /create/prototype'):
        _fetch_custom_template_url(page, "/create/prototype")

    expect(page.locator("text=Could not reach that URL")).not_to_be_visible()
    expect(page.locator("text=Fetched")).to_be_visible()


@pytest.mark.issue("ISS-695")
def test_upload_custom_template_from_url_succeeds_on_ppt(page, shot):
    """Same fetch, same expectation, on the sibling /create/ppt route —
    both wizards share CustomTemplateModal and the same backend endpoint."""
    with shot("fetch-url-ppt", 'When I fetch https://example.com/ as a custom template on /create/ppt'):
        _fetch_custom_template_url(page, "/create/ppt")

    expect(page.locator("text=Could not reach that URL")).not_to_be_visible()
    expect(page.locator("text=Fetched")).to_be_visible()
