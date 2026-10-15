"""ISS-1137 (QA-KB-106) — a launch the backend refuses must show the API
error text and release the Run once latch. Today the page.tsx `.catch` shows
nothing and ComposerPage's FIX-614 submitting latch is never released.

POST /api/runs is stubbed (never reaches the backend, no run is minted).
See `.knowledge/cards/20261009-0304-ISS-1137.md`.
"""

from __future__ import annotations

import json

import pytest
from playwright.sync_api import expect

from framework import settings
from framework.locators import composer as L

BRIEF_TEXT = "One slide saying hello. Nothing else."

CASES = [
    (503, "model_provider_unavailable", "Provider ZZ is unavailable right now"),
    (403, "tier_not_entitled", "Your tier is not entitled to ZZ launches"),
    (422, "invalid_workflow_manifest", "Manifest ZZ is invalid"),
]


@pytest.mark.parametrize("status,code,text", CASES, ids=[c[1] for c in CASES])
@pytest.mark.issue("ISS-1137")
def test_rejected_launch_shows_message_and_releases_run_once(page, status, code, text):
    """ISS-1137 — a refused POST /api/runs shows the backend error text and
    leaves Run once enabled (a second click sends a second POST)."""
    posts = []

    def handler(route):
        if route.request.method == "POST":
            posts.append(route.request)
            route.fulfill(
                status=status,
                content_type="application/json",
                body=json.dumps(
                    {"detail": {"error": text, "code": code, "recoverable": False}}
                ),
            )
        else:
            route.continue_()

    page.route("**/api/runs", handler)
    page.goto("/workflows/ppt/canvas")
    expect(page.locator(L.HEADER_SUMMARY)).to_be_visible()
    L.wait_for_nodes(page, len(L.PPT_AGENT_IDS))
    page.wait_for_timeout(settings.SETTLE_MS)
    page.fill(L.BRIEF, BRIEF_TEXT)
    expect(page.locator(L.RUN_ONCE)).to_be_enabled()
    page.click(L.RUN_ONCE)
    page.wait_for_timeout(3_000)

    assert len(posts) == 1, f"expected the first click to POST once, got {len(posts)}"
    expect(page.get_by_text(text)).to_be_visible(timeout=3_000)
    expect(page.locator(L.RUN_ONCE)).to_be_enabled(timeout=3_000)
    page.click(L.RUN_ONCE)
    page.wait_for_timeout(2_000)
    assert len(posts) == 2, (
        f"ISS-1137: after a {status} {code} refusal Run once did not fire "
        f"a second POST ({len(posts)} total): the latch was never released"
    )
