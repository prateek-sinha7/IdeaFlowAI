"""ISS-277 — /runs/{id}/steps/{agentId} must open that agent's detail pane.

Companion to S-07-10 (`test_an_agent_row_is_addressable_by_url`) in
test_run_detail.py, which only checks that the Steps tab itself is selected.
This file checks the thing the URL segment actually promises: the named
agent's own detail pane (breadcrumb "Steps / <Agent Name>") renders on a
fresh navigation, without any manual click.

Root cause (ISS-277): `reopenTabFor()` in `frontend/src/app/[...view]/page.tsx`
is typed to return only a tab name, dropping `ParsedView.agentId` before it
ever reaches `AgentThinkingTab`'s `selectedAgentId` state.
"""

from __future__ import annotations

import json
import re

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


@pytest.mark.issue("ISS-277")
def test_a_fresh_deeplink_to_steps_agent_opens_that_agents_detail_pane(page, shot):
    """A cold nav to /runs/{id}/steps/{agentId} must render that agent's
    detail pane (the "Steps / <Agent Name>" breadcrumb), not the bare
    unfiltered lane list — matching what a manual row click produces."""
    run_id = a_completed_run(page)
    # The Steps rows carry no data-agent-id (a separate gap, see S-07-10's own
    # fallback/skip). Resolve a real agent id from the API instead, per
    # velocity.json's documented recipe for this exact data shape.
    detail = api.json_body(page, "GET", f"/api/runs/{run_id}")
    outputs = json.loads(detail["agent_outputs"])
    assert outputs, "run has no agent_outputs to build a deep-link from"
    agent_id = outputs[0]["agent_id"]

    with shot("agent-deeplink-detail", 'When I cold-load "/runs/{id}/steps/{agentId}"'):
        page.goto(f"/runs/{run_id}/steps/{agent_id}")
        expect(page.locator(L.HEADER)).to_be_visible()
        expect(page.locator(L.tab("tab-thinking"))).to_have_attribute("aria-selected", "true")

    # This is the promise the URL makes: that specific agent's detail pane,
    # surfaced as the "Steps / <Agent Name>" breadcrumb — not the bare list.
    breadcrumb = page.get_by_text(re.compile(r"^Steps\s*/"))
    expect(breadcrumb).to_be_visible(timeout=5000)
