"""BUGS.md#qa-ps-049 — Clicking/deep-linking to any agent in the Steps tab
fires GET /api/runs/{id}/artifacts TWICE (24ms apart, identical 13.4 KB
responses) instead of once.

Card:
- ISS-802 — `ArtifactVersionPicker.tsx:104-119`'s list-fetch effect has no
  StrictMode dedupe guard. `next dev`'s default React StrictMode
  (`reactStrictMode` unset in `next.config.ts` -> Next 16's `true` default)
  mounts the component twice, and the effect's `cancelled` flag guards only
  the post-resolution `setState`, never the fetch call itself, so both
  mounts each call `getRunArtifacts` once. Confirmed 3/3 live cold-start
  cycles in the card's own Reproduction section.

Same recipe as test_run_detail_agent_deeplink.py: resolve a real agent id
from the API, cold-navigate directly to /runs/{id}/steps/{agentId} (avoids
the documented Steps-tab row-click interception quirk), and count network
requests to the artifacts endpoint.

Matches the card's own validation recipe: a FRESH `page.goto` to /dashboard
before each cold-start navigation to the steps/{agentId} URL, not a
client-side (soft) router transition from an already-loaded page — a soft
nav can reuse the already-mounted fiber tree and skip StrictMode's
mount->cleanup->mount remount entirely.
"""

from __future__ import annotations

import json

import pytest
from playwright.sync_api import expect

from framework import api
from framework.locators import run_detail as L
from framework.locators import run_history as RH


def a_completed_run(page) -> str:
    page.goto("/runs")
    expect(page.locator(RH.ROW).first).to_be_visible()
    done = [label for label in RH.rows(page) if RH.status_of(label) == "completed"]
    assert done, "no completed run to open"
    page.locator(f'{RH.ROW}[aria-label="{done[0]}"]').first.click()
    page.wait_for_url(lambda url: "/runs/" in url)
    return page.url.split("/runs/")[1].split("/")[0].split("?")[0]


@pytest.mark.issue("ISS-802")
def test_opening_an_agent_in_steps_tab_fetches_artifacts_once(page):
    """ISS-802 — opening an agent's detail pane in the Steps tab must fetch
    GET /api/runs/{id}/artifacts once, not twice."""
    run_id = a_completed_run(page)
    detail = api.json_body(page, "GET", f"/api/runs/{run_id}")
    outputs = json.loads(detail["agent_outputs"])
    assert outputs, "run has no agent_outputs to build a deep-link from"
    agent_id = outputs[0]["agent_id"]

    # Hard cold-start, per the card's own validated recipe: a soft (client-side)
    # router transition from the already-loaded /runs page can reuse the
    # existing fiber tree and skip StrictMode's mount->cleanup->mount remount.
    page.goto("/dashboard")
    page.wait_for_timeout(500)

    requests: list[str] = []
    page.on("request", lambda req: requests.append(req.url))

    page.goto(f"/runs/{run_id}/steps/{agent_id}")
    expect(page.locator(L.HEADER)).to_be_visible()
    page.wait_for_timeout(1500)

    artifact_calls = [u for u in requests if f"/api/runs/{run_id}/artifacts" in u]

    assert len(artifact_calls) <= 1, (
        "opening an agent's Steps detail pane should fetch "
        f"/api/runs/{run_id}/artifacts once, saw {len(artifact_calls)}: {artifact_calls}"
    )
