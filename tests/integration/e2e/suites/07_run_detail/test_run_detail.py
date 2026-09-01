"""Implements ../../../screens/07-run-detail.feature.md.

Every test carries the `scenario` marker naming the Gherkin scenario it
implements; `capture/_scenarios.py` checks both directions of that link.

**S-07-04 and S-07-05 are why this suite exists.** FIX-302: the tab-route effect
re-seeded the run refs and returned early, restoring WHICH run the tab drives
but none of its DATA. A run parked at `waiting_for_user` emits nothing, so the
screen was left with no type, no clarify panel and no way to answer —
permanently unreachable. Nothing about that is visible without clicking through
the tabs and looking at the header again.

The Steps tab's testid is `tab-thinking`. Legacy naming, still live.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from framework import api, settings
from framework.locators import run_detail as L
from framework.locators import run_history as RH


def a_completed_run(page) -> str:
    """The id of a completed single-version run this account owns.

    A family row opens its LATEST MEMBER (a revision) whose type header reads
    differently from the root. ISS-628: filter to n == 1 so the caller always
    lands on the run whose label it matched.
    """
    page.goto("/runs")
    expect(page.locator(RH.ROW).first).to_be_visible()
    rows_info = page.locator(RH.ROW).evaluate_all(
        """els => els.map((e, i) => {
            const badge = e.querySelector('span[aria-label$=" versions"]');
            return [i, e.getAttribute("aria-label"),
                    badge ? parseInt(badge.getAttribute("aria-label"), 10) : 1];
        })"""
    )
    done = [
        (idx, label)
        for idx, label, n in rows_info
        if n == 1 and RH.status_of(label) == "completed"
    ]
    assert done, "no single-version completed run to open"
    idx, label = done[0]
    page.locator(RH.ROW).nth(idx).click()
    page.wait_for_url(lambda url: "/runs/" in url)
    return page.url.split("/runs/")[1].split("/")[0].split("?")[0]


def a_run_with_files(page) -> str:
    """A completed run whose workspace actually holds files.

    The Workspace tab renders nothing to select when the sandbox is empty, and
    which run `a_completed_run` lands on depends on the history's current
    ordering — so the workspace scenarios ask the API first rather than hoping.
    """
    page.goto("/runs")
    expect(page.locator(RH.ROW).first).to_be_visible()
    done = [label for label in RH.rows(page) if RH.status_of(label) == "completed"]
    page.goto("/dashboard")
    for label in done[:8]:
        page.goto("/runs")
        expect(page.locator(RH.ROW).first).to_be_visible()
        page.locator(f'{RH.ROW}[aria-label="{label}"]').first.click()
        page.wait_for_url(lambda url: "/runs/" in url)
        run_id = page.url.split("/runs/")[1].split("/")[0].split("?")[0]
        listing = api.json_body(page, "GET", f"/api/runs/{run_id}/sandbox")
        if listing.get("files"):
            return run_id
    pytest.skip("no completed run has a populated workspace")


def open_run(page, run_id: str, suffix: str = "") -> None:
    page.goto(f"/runs/{run_id}{suffix}")
    expect(page.locator(L.LANE)).to_be_visible()
    expect(page.locator(L.HEADER)).to_be_visible()
    page.wait_for_timeout(settings.SETTLE_MS)


def header_identity(page) -> tuple[str, str]:
    """The workflow type and title the lane is showing right now."""
    return (
        page.locator(L.RUN_TYPE).inner_text().strip(),
        page.locator(L.RUN_TITLE).inner_text().strip(),
    )


# ── the surface ──────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-07-01")
def test_a_cold_load_of_a_run_shows_its_header_and_deliverable(page, shot):
    """Scenario: A cold load of a run shows its header and deliverable"""
    run_id = a_completed_run(page)

    with shot("run-detail", 'When I cold-load "/runs/{id}"'):
        open_run(page, run_id)

    for selector in (L.RUN_TYPE, L.RUN_STATUS, L.RUN_TITLE, L.RUN_META):
        expect(page.locator(selector)).not_to_be_empty()

    mini = page.locator(L.PIPELINE_MINI).inner_text()
    roster = L.counts(mini.replace("\n", " "), "AGENTS")
    assert roster and roster > 0, f"the mini-map reports no roster size: {mini!r}"
    expect(page.locator(L.DELIVERABLE)).to_contain_text(".")


@pytest.mark.scenario("S-07-02")
@pytest.mark.parametrize(("testid", "label", "suffix"), L.TABS, ids=[t[0] for t in L.TABS])
def test_every_tab_has_an_addressable_url(page, shot, testid, label, suffix):
    """Scenario: Every tab has an addressable URL"""
    run_id = a_completed_run(page)

    with shot(f"cold-{testid}", f'When I cold-load "/runs/{{id}}{suffix}"'):
        open_run(page, run_id, suffix)

    expect(page.locator(L.tab(testid))).to_have_attribute("aria-selected", "true")
    assert page.url.endswith(f"/runs/{run_id}{suffix}")


@pytest.mark.scenario("S-07-03")
@pytest.mark.parametrize(
    ("testid", "label", "suffix"), L.TABS[1:] + L.TABS[:1], ids=[t[0] for t in L.TABS[1:] + L.TABS[:1]]
)
def test_clicking_a_tab_pushes_its_url(page, shot, testid, label, suffix):
    """Scenario: Clicking a tab pushes its URL"""
    run_id = a_completed_run(page)
    open_run(page, run_id)
    identity = header_identity(page)

    with shot(f"click-{testid}", f'When I click "{testid}"'):
        page.click(L.tab(testid))
        page.wait_for_url(f"**/runs/{run_id}{suffix}")
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    assert page.url.endswith(f"/runs/{run_id}{suffix}")
    assert header_identity(page) == identity, "the header changed with the tab"


# ── the regression guards ────────────────────────────────────────────────────


@pytest.mark.scenario("S-07-04")
def test_switching_tabs_does_not_wipe_run_state(page, shot):
    """Scenario: Switching tabs does not wipe run state

    FIX-302. The header must name the SAME workflow after every tab click, and
    must never fall back to "USER STORIES" — the default a run with no data
    lands on.
    """
    run_id = a_completed_run(page)
    open_run(page, run_id)
    identity = header_identity(page)
    deliverable = page.locator(L.DELIVERABLE).inner_text().strip()
    assert deliverable, "this run has no deliverable card to lose"

    for testid, label, suffix in L.TABS[1:] + L.TABS[:1]:
        with shot(f"state-after-{testid}", f"When I click {label}"):
            page.click(L.tab(testid))
            page.wait_for_url(f"**/runs/{run_id}{suffix}")
            page.wait_for_timeout(settings.SETTLE_MS // 2)

        assert header_identity(page) == identity, (
            f"the header became {header_identity(page)} after clicking {label} — "
            f"it was {identity}"
        )
        assert page.locator(L.DELIVERABLE).inner_text().strip() == deliverable, (
            f"the deliverable card emptied after clicking {label}"
        )

    if identity[0].upper() != "USER STORIES":
        assert "USER STORIES" not in page.locator(L.RUN_TYPE).inner_text().upper()


@pytest.mark.scenario("S-07-05")
def test_a_run_parked_at_a_human_gate_stays_answerable_after_a_tab_click(page, shot):
    """Scenario: A run parked at a human gate stays answerable after a tab click

    The exact FIX-302 reproduction: `questionnaire_ready` already fired before
    the click, so nothing re-emits it — a remount that does not refetch loses it
    for good.
    """
    page.goto("/runs")
    expect(page.locator(RH.ROW).first).to_be_visible()
    waiting = [
        label
        for label in RH.rows(page)
        if RH.status_of(label) in ("waiting_for_user", "waiting", "paused")
    ]
    if not waiting:
        # The affordance survives on a completed run too — the transcript keeps
        # it — so fall back to that rather than skipping the FIX-302 shape
        # entirely.
        run_id = a_completed_run(page)
        open_run(page, run_id)
        if page.get_by_text(L.ANSWER_IN_STEPS).count() == 0:
            pytest.skip("no run is parked at a human gate and none shows the clarify prompt")
    else:
        page.locator(f'{RH.ROW}[aria-label="{waiting[0]}"]').first.click()
        page.wait_for_url(lambda url: "/runs/" in url)
        run_id = page.url.split("/runs/")[1].split("/")[0].split("?")[0]
        open_run(page, run_id)

    with shot("clarify-before", "Then I see the clarify affordance"):
        before = page.get_by_text(L.ANSWER_IN_STEPS).count()

    assert before > 0

    with shot("clarify-after-tabs", "When I click Steps and come back to Preview"):
        page.click(L.tab("tab-thinking"))
        page.wait_for_url(f"**/runs/{run_id}/steps")
        page.wait_for_timeout(settings.SETTLE_MS // 2)
        page.click(L.tab("tab-preview"))
        page.wait_for_url(f"**/runs/{run_id}")
        page.wait_for_timeout(settings.SETTLE_MS)

    assert page.get_by_text(L.ANSWER_IN_STEPS).count() > 0, (
        "the clarify affordance is gone after a tab round-trip — FIX-302 has "
        "regressed and the run is now unanswerable"
    )


@pytest.mark.scenario("S-07-06")
def test_browser_back_and_forward_move_between_tabs_without_remounting_the_run(page, shot):
    """Scenario: Browser back and forward move between tabs without remounting the run

    BUG-030. Tab navigation must be a shallow pushState, not a remount.
    """
    run_id = a_completed_run(page)
    open_run(page, run_id)
    identity = header_identity(page)

    page.click(L.tab("tab-thinking"))
    page.wait_for_url(f"**/runs/{run_id}/steps")
    page.click(L.tab("tab-files"))
    page.wait_for_url(f"**/runs/{run_id}/files")

    with shot("tabs-back", "When I press browser Back"):
        page.go_back()
        page.wait_for_url(f"**/runs/{run_id}/steps")
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    assert header_identity(page) == identity

    with shot("tabs-forward", "When I press browser Forward"):
        page.go_forward()
        page.wait_for_url(f"**/runs/{run_id}/files")
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    assert header_identity(page) == identity


@pytest.mark.scenario("S-07-07")
def test_a_hard_refresh_on_any_tab_restores_that_tab(page, shot):
    """Scenario: A hard refresh on any tab restores that tab"""
    run_id = a_completed_run(page)
    open_run(page, run_id, "/audit")

    with shot("audit-refreshed", "When I reload the page"):
        page.reload()
        expect(page.locator(L.HEADER)).to_be_visible()
        page.wait_for_timeout(settings.SETTLE_MS)

    expect(page.locator(L.tab("tab-audit"))).to_have_attribute("aria-selected", "true")
    expect(page.locator(L.AUDIT_PILL)).to_be_visible()


@pytest.mark.scenario("S-07-08")
def test_the_workspace_tab_is_in_the_routing_contract(page, shot):
    """Scenario: The Workspace tab is in the routing contract

    D-02, resolved at 9b0fb8c79: the URL was rendered while `parseViewPath`
    returned `unknown` for it and `routes.ts` had no builder. ADR-0018 says
    every URL is both built and parsed there; this one was neither.
    """
    run_id = a_run_with_files(page)

    with shot("workspace-route", 'When I cold-load "/runs/{id}/workspace"'):
        open_run(page, run_id, "/workspace")

    expect(page.locator(L.tab("tab-workspace"))).to_have_attribute("aria-selected", "true")
    expect(page.get_by_text("Page not found.")).to_have_count(0)
    expect(L.pane(page, L.ARTIFACTS_PANE)).to_be_visible(timeout=20000)


# ── per-tab content ──────────────────────────────────────────────────────────


@pytest.mark.scenario("S-07-09")
def test_steps_lists_every_roster_agent_and_marks_the_untaken_branches(page, shot):
    """Scenario: Steps lists every roster agent and marks the untaken branches

    `3 / 5 agents` is CORRECT on a conditional run — 5 in the roster, 3
    dispatched, 2 skipped by a gate. FIX-308 was the opposite failure: a
    composed agent silently not dispatched while the run reported
    `pipeline_complete`. The invariant either way is dispatched + skipped =
    roster.
    """
    run_id = a_completed_run(page)

    with shot("steps", 'When I cold-load "/runs/{id}/steps"'):
        open_run(page, run_id, "/steps")

    body = page.evaluate("() => document.body.innerText")
    progress = L.steps_progress(body)
    assert progress, f"the steps header reports no progress: {body[:200]!r}"
    dispatched, roster = progress

    rows = page.locator(L.AGENT_ROW)
    assert rows.count() == roster, (
        f"the header says {roster} roster agents and {rows.count()} rows are drawn"
    )

    texts = rows.evaluate_all("els => els.map(e => e.innerText)")
    skipped = [t for t in texts if "skipped" in t.lower()]
    assert dispatched + len(skipped) == roster, (
        f"{dispatched} dispatched + {len(skipped)} skipped != {roster} roster"
    )


@pytest.mark.scenario("S-07-10")
def test_an_agent_row_is_addressable_by_url(page, shot):
    """Scenario: An agent row is addressable by URL"""
    run_id = a_completed_run(page)
    open_run(page, run_id, "/steps")
    rows = page.locator(L.AGENT_ROW)
    assert rows.count() > 0
    first = rows.first.get_attribute("data-agent-id") or ""
    if not first:
        # No agent id on the row — fall back to the first row's own click, which
        # is what a user has.
        rows.first.click()
        page.wait_for_timeout(settings.SETTLE_MS // 2)
        assert f"/runs/{run_id}/steps" in page.url
        pytest.skip("the rows carry no agent id, so the /steps/{agentId} URL cannot be built")

    with shot("agent-deeplink", 'When I cold-load "/runs/{id}/steps/{agentId}"'):
        open_run(page, run_id, f"/steps/{first}")

    expect(page.locator(L.tab("tab-thinking"))).to_have_attribute("aria-selected", "true")


@pytest.mark.scenario("S-07-11")
def test_the_starting_point_shows_the_brief(page, shot):
    """Scenario: The starting point shows the brief"""
    run_id = a_completed_run(page)

    with shot("starting-point", 'When I cold-load "/runs/{id}/steps"'):
        open_run(page, run_id, "/steps")

    expect(page.get_by_text(L.STARTING_POINT).first).to_be_visible()
    # The brief on the Steps tab is the same text the lane's title excerpts.
    excerpt = page.locator(L.RUN_TITLE).inner_text().strip()[:30]
    assert excerpt and excerpt in page.evaluate("() => document.body.innerText")


@pytest.mark.scenario("S-07-12")
def test_files_groups_the_deliverable_apart_from_intermediates(page, shot):
    """Scenario: Files groups the deliverable apart from intermediates"""
    run_id = a_completed_run(page)

    with shot("files", 'When I cold-load "/runs/{id}/files"'):
        open_run(page, run_id, "/files")

    body = page.evaluate("() => document.body.innerText")
    for group in (L.FINAL_OUTPUT, L.AGENT_OUTPUTS, L.RUN_INPUT):
        assert group in body, f"the {group} group is missing"

    total = L.counts(body, "files available")
    deliverables = L.counts(body, "deliverable")
    assert total and total > 0, body[:200]
    assert deliverables == 1, f"FINAL OUTPUT should hold exactly one file, header says {deliverables}"

    agent_outputs = re.search(r"AGENT OUTPUTS \((\d+)\)", body)
    assert agent_outputs, "AGENT OUTPUTS carries no count"
    expect(page.locator(L.DOWNLOAD_ALL)).to_be_visible()
    assert "prompt.md" in body, "RUN INPUT does not contain prompt.md"


@pytest.mark.scenario("S-07-13")
def test_the_deliverable_reports_its_own_validation_state(page, shot):
    """Scenario: The deliverable reports its own validation state"""
    run_id = a_completed_run(page)

    with shot("deliverable-row", 'When I cold-load "/runs/{id}/files"'):
        open_run(page, run_id, "/files")

    body = page.evaluate("() => document.body.innerText")
    final = body.split(L.FINAL_OUTPUT, 1)[1].split(L.AGENT_OUTPUTS, 1)[0]
    assert re.search(r"\(\.[a-z0-9]+\)", final), f"no format on the deliverable row: {final[:200]!r}"
    assert re.search(r"\d+(\.\d+)?\s*(B|KB|MB)", final), f"no size: {final[:200]!r}"
    assert "validated" in final.lower(), f"no validation state: {final[:200]!r}"


# A seeded ppt_v2 run (4 agents: strategist, engineer, QA, PPTX Code Generator)
# whose backend already confirms two legitimate deliverable candidates —
# GET /api/runs/<id> deliverable_filename="presentation.html", and
# GET /api/runs/<id>/sandbox lists presentation.pptx (binary, deliverable:true)
# — used by ISS-199/ISS-215 below. BUG-20260828-012900-runs-id-files.
PPT_V2_RUN_ID = "b9feac1c-ec21-4531-8ba7-bb391786993e"


@pytest.mark.issue("ISS-199")
def test_a_ppt_v2_runs_final_output_is_the_declared_deliverable_not_a_tmp_scratch_file(page, shot):
    """ISS-199 — Files tab's Final output must be the backend-declared
    deliverable (presentation.html), never a mid-pipeline tmp/ scratch file
    picked up because the last agent to stream happens to match its content."""
    with shot("ppt-v2-final-output", 'When I cold-load the ppt_v2 run\'s Files tab'):
        open_run(page, PPT_V2_RUN_ID, "/files")

    # The seeded run's own sandbox listing is the ground truth: presentation.pptx
    # (binary) and presentation.html are both flagged deliverable:true, and
    # tmp/kindred-pitch-deck.html is a scratch file also flagged deliverable:true
    # (the bug's whole premise — the flag alone can't disambiguate).
    listing = api.json_body(page, "GET", f"/api/runs/{PPT_V2_RUN_ID}/sandbox")
    paths = {f["path"] for f in listing["files"]}
    assert "presentation.pptx" in paths and "tmp/kindred-pitch-deck.html" in paths, (
        f"fixture drifted — expected both the real deliverable and the tmp scratch file on disk: {sorted(paths)}"
    )

    body = page.evaluate("() => document.body.innerText")
    final = body.split(L.FINAL_OUTPUT, 1)[1].split(L.AGENT_OUTPUTS, 1)[0]
    assert "tmp" not in final.lower(), f"Final output still names the tmp/ scratch file: {final[:200]!r}"
    assert "presentation" in final.lower(), (
        f"Final output does not name the declared deliverable (presentation.html): {final[:200]!r}"
    )


@pytest.mark.issue("ISS-276")
def test_header_relative_age_is_not_frozen_on_just_now_for_a_completed_run(page, shot):
    """ISS-276 — a cold load of a long-completed run's detail page must show the
    header's real relative age (e.g. "1d ago"), not a hydration-time-stamped
    "just now". This fixture run (`b9feac1c-ec21-4531-8ba7-bb391786993e`)
    finished well over 45s ago (BUG-20260828-011700-runs-id validated it at
    11h+, later 1d+), so "just now" can only mean the header is deriving its
    age from client load time instead of the run's real created_at/completed_at
    — exactly what the version picker in the same header row gets right."""
    with shot("header-relative-age", 'When I cold-load a long-completed run\'s detail page'):
        open_run(page, PPT_V2_RUN_ID)

    meta_text = page.locator(L.RUN_META).inner_text()
    assert "just now" not in meta_text.lower(), (
        f"header still reads 'just now' for a run completed long ago: {meta_text!r}"
    )


# ── Workspace ────────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-07-14")
def test_workspace_lists_the_runs_files_and_starts_unselected(page, shot):
    """Scenario: Workspace lists the run's files and starts unselected"""
    run_id = a_run_with_files(page)

    with shot("workspace", 'When I cold-load "/runs/{id}/workspace"'):
        open_run(page, run_id, "/workspace")

    body = page.evaluate("() => document.body.innerText")
    files = L.counts(body, "files")
    assert files is not None, f"the rail header reports no file count: {body[:300]!r}"

    listing = api.json_body(page, "GET", f"/api/runs/{run_id}/sandbox")
    assert files == len(listing["files"]), (
        f"the rail says {files} files, /sandbox lists {len(listing['files'])}"
    )
    expect(page.get_by_text(L.WORKSPACE_EMPTY)).to_be_visible()


@pytest.mark.scenario("S-07-15")
def test_artifacts_opens_expanded_all_files_opens_collapsed(page, shot):
    """Scenario: Artifacts opens expanded, All files opens collapsed

    Deliberate: five groups and 36 rows is a wall, so the directory set is the
    first answer on All files. Switching panes RESETS the collapse state either
    way.

    Read from the group headers' own `aria-expanded`, not from whether a
    filename appears in the page text — a deliverable's name shows up in the
    lane and on the run header too, so text alone cannot tell a collapsed group
    from an expanded one.
    """
    run_id = a_run_with_files(page)
    open_run(page, run_id, "/workspace")
    expect(L.pane(page, L.ARTIFACTS_PANE)).to_be_visible(timeout=20000)

    def groups(page) -> dict[str, str]:
        return {
            row["label"]: row["expanded"]
            for row in page.evaluate(
                """() => [...document.querySelectorAll('[aria-expanded]')]
                     .map(e => ({ label: (e.innerText || '').split('\\n')[0].trim(),
                                  expanded: e.getAttribute('aria-expanded') }))
                     .filter(r => r.label && r.label === r.label.toUpperCase()
                                  || r.label.startsWith('.'))"""
            )
        }

    with shot("artifacts-expanded", "Then the Artifacts pane is expanded"):
        artifacts = groups(page)

    assert artifacts, f"the Artifacts pane rendered no groups: {artifacts}"
    assert any(state == "true" for state in artifacts.values()), (
        f"every Artifacts group is collapsed on open: {artifacts}"
    )

    with shot("all-files-collapsed", 'When I click "All files"'):
        L.pane(page, L.ALL_FILES_PANE).click()
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    all_files = groups(page)
    assert all_files, "the All files pane rendered no groups"
    assert all(state == "false" for state in all_files.values()), (
        f"All files opened with a group already expanded: {all_files}"
    )


@pytest.mark.scenario("S-07-16")
def test_only_all_files_offers_sort_and_bulk_expand(page, shot):
    """Scenario: Only All files offers sort and bulk expand

    Artifacts has no sort BY DESIGN — its groups are in pipeline order, so
    re-sorting would destroy the only information the ordering carries.
    """
    run_id = a_run_with_files(page)
    open_run(page, run_id, "/workspace")
    expect(L.pane(page, L.ARTIFACTS_PANE)).to_be_visible(timeout=20000)

    with shot("artifacts-no-sort", "Then no sort control is shown on Artifacts"):
        artifacts = page.evaluate("() => document.body.innerText")

    assert "Expand all" not in artifacts and "Collapse all" not in artifacts

    with shot("all-files-sort", 'When I click "All files"'):
        L.pane(page, L.ALL_FILES_PANE).click()
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    body = page.evaluate("() => document.body.innerText")
    assert "Expand all" in body and "Collapse all" in body, body[:400]

    sort = page.get_by_role("button", name=re.compile(r"^(Name|Size|Type)$")).first
    seen = []
    for _ in range(4):
        seen.append(sort.inner_text().strip())
        sort.click()
        page.wait_for_timeout(400)
    assert seen[:3] == ["Name", "Size", "Type"], f"the sort cycled {seen}"
    assert seen[0] == "Name"


@pytest.mark.scenario("S-07-17")
@pytest.mark.parametrize("kind", ["text", "image", "pdf", "binary"])
def test_the_viewer_renders_each_file_kind_as_what_it_is(page, shot, kind):
    """Scenario: The viewer renders each file kind as what it is"""
    run_id = a_run_with_files(page)
    listing = api.json_body(page, "GET", f"/api/runs/{run_id}/sandbox")
    target = next((f for f in listing["files"] if f["kind"] == kind), None)
    if not target:
        pytest.skip(f"this workspace holds no {kind} file")

    open_run(page, run_id, "/workspace")
    expect(L.pane(page, L.ALL_FILES_PANE)).to_be_visible(timeout=20000)
    L.pane(page, L.ALL_FILES_PANE).click()
    page.wait_for_timeout(settings.SETTLE_MS // 2)
    if page.get_by_text("Expand all").count():
        page.get_by_text("Expand all").first.click()
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    name = target["path"].split("/")[-1]
    with shot(f"viewer-{kind}", f"When I open a {kind} file"):
        page.get_by_text(name, exact=True).first.click()
        page.wait_for_timeout(settings.SETTLE_MS)

    body = page.evaluate("() => document.body.innerText")
    if kind == "binary":
        assert "binary file" in body.lower(), body[-300:]
    elif kind == "image":
        assert page.locator("img").count() > 0
    elif kind == "pdf":
        assert page.locator("iframe, embed, object").count() > 0
    else:
        assert target["path"] in body or name in body


@pytest.mark.scenario("S-07-18")
def test_markdown_and_html_can_be_toggled_between_source_and_rendered(page, shot):
    """Scenario: Markdown and HTML can be toggled between source and rendered

    The toggle appears for markdown and HTML only — no other kind offers it.
    """
    run_id = a_run_with_files(page)
    listing = api.json_body(page, "GET", f"/api/runs/{run_id}/sandbox")
    target = next(
        (f for f in listing["files"] if f["path"].endswith((".md", ".html"))), None
    )
    if not target:
        pytest.skip("this workspace holds no markdown or HTML file")

    open_run(page, run_id, "/workspace")
    expect(L.pane(page, L.ALL_FILES_PANE)).to_be_visible(timeout=20000)
    L.pane(page, L.ALL_FILES_PANE).click()
    page.wait_for_timeout(settings.SETTLE_MS // 2)
    if page.get_by_text("Expand all").count():
        page.get_by_text("Expand all").first.click()
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    name = target["path"].split("/")[-1]
    with shot("viewer-source", "When I open a markdown or HTML file"):
        page.get_by_text(name, exact=True).first.click()
        page.wait_for_timeout(settings.SETTLE_MS)

    toggle = page.get_by_role("button", name=re.compile(r"^(Preview|Code)$")).first
    expect(toggle).to_be_visible()
    label = toggle.inner_text().strip()

    with shot("viewer-toggled", "When I click the toggle"):
        toggle.click()
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    assert toggle.inner_text().strip() != label, "the toggle did not change state"


@pytest.mark.scenario("S-07-19")
def test_download_all_zips_the_whole_workspace(page, shot):
    """Scenario: Download all zips the whole workspace

    One request, not one download per file: a browser blocks the Files tab's
    fire-a-download-every-150ms approach after a handful, and a ppt_v2 workspace
    is 36 files.
    """
    run_id = a_run_with_files(page)
    open_run(page, run_id, "/workspace")

    with shot("download-all", 'When I click "Download all"'), page.expect_download() as info:
        page.locator(L.DOWNLOAD_WORKSPACE).first.click()

    download = info.value
    assert download.suggested_filename.startswith("workspace-"), download.suggested_filename
    assert download.suggested_filename.endswith(".zip")
    assert run_id[:8] in download.suggested_filename


@pytest.mark.scenario("S-07-20")
@pytest.mark.skip(reason="needs a completed ppt_v2 run whose workspace holds both artifacts")
def test_a_ppt_v2_run_shows_both_artifacts_in_one_view(page, shot):
    """Scenario: A ppt_v2 run shows both artifacts in one view"""


@pytest.mark.scenario("S-07-21")
@pytest.mark.skip(reason="needs runs in four specific workspace states; none is seeded")
def test_each_empty_state_says_which_one_it_is(page, shot):
    """Scenario: Each empty state says which one it is"""


@pytest.mark.scenario("S-07-22")
@pytest.mark.skip(reason="needs a TTL-swept workspace; every seeded run still has one")
def test_an_expired_workspace_says_where_the_deliverable_still_is(page, shot):
    """Scenario: An expired workspace says where the deliverable still is"""


@pytest.mark.scenario("S-07-23")
@pytest.mark.skip(reason="needs a run whose files are all nested; none is seeded")
def test_a_workspace_with_no_top_level_output_offers_a_way_to_its_files(page, shot):
    """Scenario: A workspace with no top-level output offers a way to its files"""


# ── Audit ────────────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-07-24")
def test_audit_filters_by_category(page, shot):
    """Scenario: Audit filters by category"""
    run_id = a_completed_run(page)

    with shot("audit", 'When I cold-load "/runs/{id}/audit"'):
        open_run(page, run_id, "/audit")

    total = L.filter_count(page, "All")
    assert total, "the All filter carries no count"
    named = sum(L.filter_count(page, label) or 0 for label in list(L.AUDIT_FILTERS)[1:])
    assert named == total, (
        f"the category filters account for {named} of {total} records — a record "
        "in no category cannot be found by filtering"
    )

    with shot("audit-governance", 'When I click "Governance"'):
        page.click(L.AUDIT_FILTERS["Governance"])
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    expect(page.locator(L.AUDIT_FILTERS["Governance"])).to_be_visible()


@pytest.mark.scenario("S-07-25")
@pytest.mark.skip(reason="needs a run that passed BOTH a human and a conditional gate; 22_handoff_and_gates makes one")
def test_audit_records_the_human_and_conditional_gates_of_a_gated_run(page, shot):
    """Scenario: Audit records the human and conditional gates of a gated run"""


@pytest.mark.scenario("S-07-26")
def test_blocked_only_narrows_the_audit_to_denials(page, shot):
    """Scenario: Blocked-only narrows the audit to denials"""
    run_id = a_completed_run(page)
    open_run(page, run_id, "/audit")

    toggle = page.get_by_text(re.compile(r"Blocked\s*/\s*denied only", re.I)).first
    if toggle.count() == 0:
        pytest.skip("this audit view offers no blocked-only control")

    with shot("audit-blocked-only", 'When I enable "Blocked / denied only"'):
        toggle.click()
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    body = page.evaluate("() => document.body.innerText")
    assert len(body.strip()) > 40, "the blocked-only view rendered a blank pane"


# ── Preview ──────────────────────────────────────────────────────────────────


@pytest.mark.scenario("S-07-27")
def test_the_preview_renderer_can_be_switched(page, shot):
    """Scenario: The preview renderer can be switched

    The mode set is PER DELIVERABLE TYPE, not global — a `.md` offers
    Auto/HTML/Markdown/Bundle, a prototype offers Auto/Prototype. Never assert a
    fixed list.
    """
    run_id = a_completed_run(page)

    with shot("renderer", 'When I cold-load "/runs/{id}"'):
        open_run(page, run_id)

    switch = page.locator(L.RENDERER_SWITCH)
    # The switch mounts with the preview, which arrives after the run does.
    expect(switch).to_be_visible(timeout=20000)
    modes = [t.strip() for t in switch.locator("button").all_text_contents() if t.strip()]
    assert "Auto" in modes, f"every deliverable offers Auto; this one offers {modes}"

    for mode in modes[1:2]:
        with shot(f"renderer-{mode.lower()}", f'When I select the renderer "{mode}"'):
            switch.get_by_text(mode, exact=True).first.click()
            page.wait_for_timeout(settings.SETTLE_MS // 2)
        # One pill per mode — `.first` because the switch holds several.
        expect(page.locator(L.RENDERER_PILL).first).to_be_visible()


@pytest.mark.scenario("S-07-28")
@pytest.mark.defect
def test_choosing_html_for_a_markdown_deliverable_renders_nothing(page, shot):
    """Scenario: Choosing HTML for a markdown deliverable renders nothing

    Asserts TODAY'S behaviour — D-13. Bundle, on the same file, at least says
    "No files generated yet"; HTML says nothing, and the user cannot tell
    whether the deliverable is missing or the renderer is wrong.
    """
    page.goto("/runs")
    expect(page.locator(RH.ROW).first).to_be_visible()
    for label in RH.rows(page):
        if RH.status_of(label) != "completed":
            continue
        page.locator(f'{RH.ROW}[aria-label="{label}"]').first.click()
        page.wait_for_url(lambda url: "/runs/" in url)
        run_id = page.url.split("/runs/")[1].split("/")[0].split("?")[0]
        open_run(page, run_id)
        if page.locator(L.RENDERER_SWITCH).count() == 0:
            page.goto("/runs")
            expect(page.locator(RH.ROW).first).to_be_visible()
            continue
        modes = [
            t.strip()
            for t in page.locator(L.RENDERER_SWITCH).locator("button").all_text_contents()
            if t.strip()
        ]
        if "HTML" in modes and "Markdown" in modes:
            break
        page.goto("/runs")
        expect(page.locator(RH.ROW).first).to_be_visible()
    else:
        pytest.skip("no completed run has a markdown deliverable offering the HTML renderer")

    with shot("renderer-html", 'When I select the renderer "HTML"'):
        page.locator(L.RENDERER_SWITCH).get_by_text("HTML", exact=True).first.click()
        page.wait_for_timeout(settings.SETTLE_MS)

    body = page.evaluate("() => document.body.innerText")
    assert "No files generated" not in body, (
        "HTML now explains itself the way Bundle does — D-13 is fixed; rewrite "
        "this as the spec's S-07-28"
    )


@pytest.mark.scenario("S-07-29")
def test_a_prototype_run_offers_its_own_renderer_mode(page, shot):
    """Scenario: A prototype run offers its own renderer mode

    A FIFTH mode not in the original manifest list. The mode set is per
    deliverable type, which is why nothing here asserts a fixed list.
    """
    page.goto("/runs")
    expect(page.locator(RH.ROW).first).to_be_visible()
    RH.chip(page, "Prototype").first.click()
    page.wait_for_url("**type=prototype")
    page.wait_for_timeout(settings.SETTLE_MS // 2)
    done = [label for label in RH.rows(page) if RH.status_of(label) == "completed"]
    if not done:
        pytest.skip("no completed prototype run")

    page.locator(f'{RH.ROW}[aria-label="{done[0]}"]').first.click()
    page.wait_for_url(lambda url: "/runs/" in url)
    run_id = page.url.split("/runs/")[1].split("/")[0].split("?")[0]

    with shot("prototype-renderer", 'When I cold-load a prototype run'):
        open_run(page, run_id)

    modes = [
        t.strip()
        for t in page.locator(L.RENDERER_SWITCH).locator("button").all_text_contents()
        if t.strip()
    ]
    assert "Prototype" in modes, f"a prototype run offers {modes}"
    assert "Auto" in modes


@pytest.mark.scenario("S-07-30")
def test_a_prototype_run_previews_its_validated_deliverable(page, shot):
    """Scenario: A prototype run previews its validated deliverable

    **D-18 is FIXED.** The spec records the Preview tab rendering the spec
    agent's markdown as plain text with zero iframes while the Files tab
    reported `prototype.html · validated`. It now renders the prototype in an
    iframe, so this asserts the scenario as written rather than the defect.
    """
    page.goto("/runs")
    expect(page.locator(RH.ROW).first).to_be_visible()
    RH.chip(page, "Prototype").first.click()
    page.wait_for_url("**type=prototype")
    page.wait_for_timeout(settings.SETTLE_MS // 2)
    done = [label for label in RH.rows(page) if RH.status_of(label) == "completed"]
    if not done:
        pytest.skip("no completed prototype run")

    page.locator(f'{RH.ROW}[aria-label="{done[0]}"]').first.click()
    page.wait_for_url(lambda url: "/runs/" in url)
    run_id = page.url.split("/runs/")[1].split("/")[0].split("?")[0]
    open_run(page, run_id)

    with shot("prototype-rendered", 'When I select the "Prototype" renderer'):
        switch = page.locator(L.RENDERER_SWITCH)
        expect(switch).to_be_visible(timeout=20000)
        if switch.get_by_text("Prototype", exact=True).count():
            switch.get_by_text("Prototype", exact=True).first.click()
            page.wait_for_timeout(settings.SETTLE_MS)

    assert page.locator("iframe").count() > 0, (
        "the prototype deliverable is not rendered in an iframe — D-18 has "
        "regressed and the Preview tab is showing a different file again"
    )


@pytest.mark.scenario("S-07-31")
@pytest.mark.skip(reason="needs a completed ppt_v2 deck run")
def test_a_deck_run_offers_slides_and_full_screen(page, shot):
    """Scenario: A deck run offers Slides and Full Screen"""


@pytest.mark.scenario("S-07-32")
def test_full_preview_is_its_own_url(page, shot):
    """Scenario: Full preview is its own URL"""
    run_id = a_completed_run(page)

    with shot("full-preview", 'When I cold-load "/runs/{id}/preview/full"'):
        page.goto(f"/runs/{run_id}/preview/full")
        page.wait_for_load_state("load")
        page.wait_for_timeout(settings.SETTLE_MS)

    assert page.url.endswith("/preview/full")
    expect(page.get_by_text("Page not found.")).to_have_count(0)
    assert len(page.evaluate("() => document.body.innerText").strip()) > 20


@pytest.mark.scenario("S-07-33")
@pytest.mark.destructive
def test_the_run_chat_lane_accepts_a_follow_up(page, shot):
    """Scenario: The run chat lane accepts a follow-up

    Marked destructive: a follow-up on a completed run can start a revision, so
    this asserts the composer accepts and clears the message rather than sending
    one. Actually dispatching belongs to the live tier.
    """
    run_id = a_completed_run(page)

    with shot("composer", 'When I cold-load "/runs/{id}"'):
        open_run(page, run_id)

    expect(page.locator(L.COMPOSER)).to_be_visible()
    expect(page.locator(L.COMPOSER_INPUT)).to_be_visible()
    expect(page.locator(L.ATTACHMENTS)).to_be_attached()

    with shot("composer-typed", "When I type a message"):
        page.fill(L.COMPOSER_INPUT, "E2E S-07-33 follow-up, not sent")
        page.wait_for_timeout(settings.SETTLE_MS // 3)

    expect(page.locator(L.SEND)).to_be_enabled()
    page.fill(L.COMPOSER_INPUT, "")


@pytest.mark.scenario("S-07-34")
def test_back_to_history_returns_to_the_list(page, shot):
    """Scenario: Back to history returns to the list"""
    run_id = a_completed_run(page)
    open_run(page, run_id)

    with shot("back-to-history", 'When I click "Back to history"'):
        page.click(L.BACK)
        page.wait_for_url("**/runs**")
        page.wait_for_timeout(settings.SETTLE_MS // 2)

    assert "/runs" in page.url and run_id not in page.url


@pytest.mark.scenario("S-07-35")
@pytest.mark.skip(reason="no run in this database has more than one version")
def test_a_specific_run_version_is_addressable(page, shot):
    """Scenario: A specific run version is addressable"""


@pytest.mark.scenario("S-07-36")
@pytest.mark.live
@pytest.mark.skip(reason="needs a run that is currently generating; live tier")
def test_a_live_run_streams_into_the_same_surface(page, shot):
    """Scenario: A live run streams into the same surface"""
