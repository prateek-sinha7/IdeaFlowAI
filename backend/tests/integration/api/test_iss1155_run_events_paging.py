"""ISS-1155 (QA-KB-119) — GET /api/runs/{id}/events must page, not replay the whole log."""

from __future__ import annotations

import pytest

from tests.integration.api.test_runs_api_events_api import (  # noqa: F401
    _seed_events,
    _seed_run,
    api,
    db_session,
)

N = 6000  # above the 5000 hard cap the fix is specified to enforce


@pytest.mark.issue("ISS-1155")
def test_bare_events_call_is_a_bounded_page(api, db_session):
    """ISS-1155 — no params returns a bounded page with has_more and a next cursor."""
    client, _ = api
    _seed_run(db_session)
    _seed_events(db_session, n=N)

    body = client.get("/api/runs/run-1/events").json()

    assert len(body["events"]) < N, f"whole log returned ({len(body['events'])} rows)"
    assert body["has_more"] is True
    assert body["next_after"] == body["events"][-1]["seq"]


@pytest.mark.issue("ISS-1155")
def test_limit_param_is_honoured(api, db_session):
    """ISS-1155 — an explicit ?limit=10 returns 10 rows."""
    client, _ = api
    _seed_run(db_session)
    _seed_events(db_session, n=50)

    body = client.get("/api/runs/run-1/events?limit=10").json()

    assert len(body["events"]) == 10
