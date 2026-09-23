"""ISS-375 — a manifest-only workflow (zero library-declared agents) opened
via /create/{id} dead-ends on ANY `getWorkflowDetail` failure, not only a
nonexistent slug.

`/create/custom` is a REAL, existing workflow (`GET /api/workflows/custom`
normally returns 200 with 9 manifest steps) whose `base_pipeline_type`
("custom") has zero `AGENT.md`-declared library agents
(`fromLibrary.length === 0` for it, per `IdeaInputPage.tsx:1248-1254`'s own
comment about composed workflows). `IdeaInputPage.tsx:1172-1181`'s
`.catch()` never branches on `ApiError.status` — it treats "unknown id
(404)" and "transient error" identically, per its own comment. So a single
dropped/failed request for this otherwise-healthy, real workflow reproduces
the exact same dead end as [ISS-374](ISS-374): `pipelineAgents = []`, the
Save/Run actions permanently disabled, and zero error text anywhere on the
page — even though the workflow itself is fine and a retry would succeed.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from framework.locators import launch_panels as L


@pytest.mark.issue("ISS-375")
def test_transient_fetch_failure_on_real_workflow_surfaces_error(page, shot):
    """A single failed GET /api/workflows/custom (simulating a transient
    network blip on a REAL, existing workflow) must show a visible
    error/retry state, not swallow it into the same silent 0-agent dead end
    as a nonexistent slug."""
    # Fail exactly the one getWorkflowDetail request for this real workflow,
    # simulating a transient/network failure rather than a bad slug.
    page.route(
        re.compile(r"/api/workflows/custom(\?.*)?$"),
        lambda route: route.abort("failed"),
    )

    with shot("load", 'When I navigate to "/create/custom" (real workflow, forced transient failure)'):
        page.goto("/create/custom")
        expect(page.locator(L.BRIEF)).to_be_visible()

    body_text = page.inner_text("body")
    assert any(
        kw in body_text.lower()
        for kw in ("not found", "doesn't exist", "does not exist", "failed to load", "error", "retry")
    ), (
        "ISS-375: a transient failure fetching a REAL workflow's detail is "
        "completely invisible in the UI — document.body.innerText contained "
        f"no error/retry text: {body_text!r}"
    )


@pytest.mark.issue("ISS-375")
@pytest.mark.xfail(reason="ISS-375 unfixed", strict=True)
def test_transient_fetch_failure_on_real_workflow_does_not_dead_end(page, shot):
    """The same forced transient failure must not permanently disable Save
    for a workflow that genuinely exists and normally has agents."""
    page.route(
        re.compile(r"/api/workflows/custom(\?.*)?$"),
        lambda route: route.abort("failed"),
    )

    with shot("load", 'When I navigate to "/create/custom" (real workflow, forced transient failure)'):
        page.goto("/create/custom")
        expect(page.locator(L.BRIEF)).to_be_visible()

    # A retry (or the app itself recovering) should eventually populate the
    # roster; today it never does because manifestAgents stays undefined and
    # fromLibrary is empty for "custom" by design.
    expect(page.locator(L.SAVE_WORKFLOW)).to_be_enabled(timeout=15_000)
