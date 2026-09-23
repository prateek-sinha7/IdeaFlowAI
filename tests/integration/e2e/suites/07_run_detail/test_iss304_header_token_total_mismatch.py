"""ISS-304 — the run-detail chat header's token total must equal the run's
own API `token_usage.total_tokens`, not a different, smaller figure.

A reopened run's totals are rebuilt by replaying its durable events, and
`useWorkflow`'s `agent_complete` case sums the per-agent numbers. Work that
never lands on a top-level agent row — wave workers, sub-agents — is missing
from that sum, so the header undercounts. Measured on one run here: the header
read 13.6M against a persisted `total_tokens` of 19.7M.

The expected figure is READ FROM THE API, never frozen into this file. It used
to assert a literal "10.4K" against a pinned run id; the database was reseeded,
that id came to name a different run, and the scenario then failed with
`expected '10.4K', actual '13.6M'` — which looks like the very mismatch it
exists to detect, while telling you nothing about whether one was real. A test
for "these two numbers agree" has to read both numbers.
"""

from __future__ import annotations

import json
import re

import pytest
from playwright.sync_api import expect

from framework import api, settings
from framework.locators import run_detail as L
from framework.locators import run_history as RH


def _format_token_count(n: int) -> str:
    """The header's own rendering of a token count.

    Mirrors `formatTokenCount` in the frontend: thousands as `N.NK`, millions as
    `N.NM`. Kept as a tiny reimplementation rather than asserting on a raw digit
    string, because the header never shows raw digits above 1000 and a substring
    check for "19717875" would fail on a correct header.
    """
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _a_completed_run_with_tokens(page) -> tuple[str, int]:
    """A completed run whose API reports a non-zero `token_usage.total_tokens`."""
    page.goto("/runs")
    expect(page.locator(RH.ROW).first).to_be_visible()
    for index, label in enumerate(RH.rows(page)):
        if RH.status_of(label) != "completed":
            continue
        page.goto("/runs")
        expect(page.locator(RH.ROW).first).to_be_visible()
        page.locator(RH.ROW).nth(index).click()
        page.wait_for_url(lambda url: "/runs/" in url)
        run_id = page.url.split("/runs/")[1].split("/")[0].split("?")[0]
        usage = api.json_body(page, "GET", f"/api/runs/{run_id}").get("token_usage") or {}
        # The column is JSON-typed but the API hands it back as a STRING on this
        # endpoint — decode rather than assume, so a future shape change surfaces
        # as a decode error rather than a silent skip.
        if isinstance(usage, str):
            usage = json.loads(usage) if usage.strip() else {}
        total = usage.get("total_tokens") or 0
        if total > 0:
            return run_id, total
    pytest.skip("no completed run reports a token_usage.total_tokens to compare against")


@pytest.mark.issue("ISS-304")
def test_run_detail_header_token_total_matches_api(page):
    """The chat header's token figure must match token_usage.total_tokens from
    the run's own API response, not disagree with it."""
    run_id, total_tokens = _a_completed_run_with_tokens(page)
    expected = _format_token_count(total_tokens)

    page.goto(f"/runs/{run_id}")
    meta = page.locator(L.RUN_META)
    expect(meta).to_contain_text(re.compile(r"tokens"))
    page.wait_for_timeout(settings.SETTLE_MS)

    shown = meta.inner_text()
    assert expected in shown, (
        f"header token total disagrees with the run's own API: header says "
        f"{shown!r}, but GET /api/runs/{run_id} reports total_tokens="
        f"{total_tokens} ({expected})"
    )
