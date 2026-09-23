"""BUGS.md#qa-ps-047 — Live run stream page fires 49+ requests (10+ MB) with
runs?limit=50 called 8-9x in real time as live SSE events arrive, and the
same unconditional refetch fires on every screen with a backgrounded run,
not only the stream page.

Cards:
- ISS-842 — `handleWebSocketMessage` (`frontend/src/app/[...view]/page.tsx`)
  calls `getWorkflows(token, { limit: 50 })` directly inside live-reachable
  SSE branches (`review_gate_ready`, `review_gate_approved`,
  `questionnaire_ready`, `questionnaire_complete`, `pipeline_complete`,
  etc.) with no debounce/coalescing — every matching live event refetches
  the run list, on top of the one expected at mount.
- ISS-846 — those same branches carry no `mainView`/route guard (unlike the
  mount-time fetch, which is explicitly skipped in wizard mode). The
  refetch fires no matter what screen the tab is showing, as long as a run
  is attached to the SSE fan-out (`RunConnectionProvider`, mounted above
  the router, survives navigation).

Both tests intercept the run's own SSE endpoint
(`GET /api/runs/{id}/events/stream`) and feed it a synthetic
`review_gate_ready` frame — no live pipeline/model run is started; the run
itself is a pre-existing `waiting_for_user` fixture already in the DB and
its `pipeline_run_id`-less frame just exercises the `sourceRunId` fallback
review_gate_ready path.

Not part of a screens/*.feature.md — no `scenario` marker.
"""

from __future__ import annotations

import json

import pytest

from framework import api
from framework.locators import shell as SHELL


def _sse_body(run_id: str) -> str:
    """One `stream_attached{live:true}` block followed by one
    `review_gate_ready` block — the minimum a live-attached stream needs to
    reach the `case "review_gate_ready"` branch in `handleWebSocketMessage`
    (data={} is enough; `gateRunId` falls back to the frame's source run)."""
    attached = json.dumps({"type": "stream_attached", "data": {"live": True}})
    gate = json.dumps({"type": "review_gate_ready", "data": {}})
    return f"id: 1\ndata: {attached}\n\nid: 2\ndata: {gate}\n\n"


def _first_waiting_run_id(page) -> str:
    """Navigates to `/dashboard` first (page.evaluate needs a real
    origin, not `about:blank`) then reads the run list via the browser's
    own fetch. A `waiting_for_user` run already sitting in the DB — no run is
    launched here. `waiting_for_user` is a BACKGROUND/parked status
    (`RunConnectionProvider`'s `AUTO_STREAM_STATUSES` excludes it), so its
    SSE stream is attached only via the sticky focus a stream-page visit
    sets, matching the real repro path (opened from the running badge)."""
    page.goto("/dashboard")
    resp = api.full(page, "GET", "/api/runs?limit=50")
    data = json.loads(resp["body"])
    runs = data.get("runs", data) if isinstance(data, dict) else data
    for r in runs:
        if r.get("status") == "waiting_for_user":
            return r["id"]
    raise AssertionError("no waiting_for_user run in the DB to attach a stream to")


@pytest.mark.issue("ISS-842")
def test_live_gate_event_causes_no_extra_runs_list_refetch(page):
    """ISS-842 — per QA-PS-047's own "Expected": once mounted, the SSE
    stream carries all live updates with NO additional `runs?limit=50`
    fetches as events arrive. A single live `review_gate_ready` frame must
    not trigger another `runs?limit=50` call."""
    run_id = _first_waiting_run_id(page)

    page.route(
        f"**/api/runs/{run_id}/events/stream*",
        lambda route: route.fulfill(
            status=200,
            headers={"Content-Type": "text/event-stream"},
            body=_sse_body(run_id),
        ),
    )

    requests: list[str] = []
    page.on("request", lambda req: requests.append(req.url))

    page.goto(f"/runs/{run_id}/stream")
    page.wait_for_timeout(4000)

    runs_list_calls = [u for u in requests if "/api/runs?" in u and "limit=50" in u]

    assert len(runs_list_calls) <= 1, (
        "a single live SSE event must not trigger an extra runs?limit=50 "
        f"fetch beyond the one at mount, saw {len(runs_list_calls)}: {runs_list_calls}"
    )


@pytest.mark.issue("ISS-846")
def test_live_gate_event_on_unrelated_screen_causes_no_refetch(page):
    """ISS-846 — the live-event refetch carries no route guard. Attach the
    stream from `/runs/{id}/stream` (the sticky focus), navigate away to
    `/library` (a screen with no visible use for `recentRuns`), THEN
    deliver the live event: no `runs?limit=50` fetch should fire while the
    tab is showing an unrelated screen."""
    run_id = _first_waiting_run_id(page)

    pending_routes: list = []
    page.route(
        f"**/api/runs/{run_id}/events/stream*",
        lambda route: pending_routes.append(route),
    )

    page.goto(f"/runs/{run_id}/stream")
    page.wait_for_timeout(3000)
    assert pending_routes, "the SSE request to the run's stream never arrived"

    # Client-side nav (never page.goto): RunConnectionProvider's SSE fetch is
    # mounted at the root layout and survives an in-app route change, not a
    # hard browser navigation, which would tear it down and invalidate the
    # premise ISS-846 makes (the connection is app-level, not per-page).
    SHELL.nav(page, "Library").click()
    page.wait_for_timeout(2000)

    requests: list[str] = []
    page.on("request", lambda req: requests.append(req.url))

    # Deliver the live event now, while the tab is on /library. Use the LAST
    # captured request (React strict-mode / a token-refresh effect can cause
    # useRunStream to reconnect once between mount and now, replacing the
    # in-flight fetch the first captured route belongs to).
    pending_routes[-1].fulfill(
        status=200,
        headers={"Content-Type": "text/event-stream"},
        body=_sse_body(run_id),
    )
    page.wait_for_timeout(5000)

    runs_list_calls = [u for u in requests if "/api/runs?" in u and "limit=50" in u]

    assert not runs_list_calls, (
        "a live SSE event delivered while on an unrelated screen (/library) "
        f"must not refetch runs?limit=50, saw {runs_list_calls}"
    )
