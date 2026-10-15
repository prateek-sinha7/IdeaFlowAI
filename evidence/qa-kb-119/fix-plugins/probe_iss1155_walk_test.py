"""Scratch probe (not in the tree): ISS-1155 cursor walk, 422s, scope."""
from tests.integration.api.test_runs_api_events_api import (  # noqa: F401
    _FakeUser, _seed_events, _seed_run, api, db_session,
)


def test_walk_cursor_yields_every_seq_once(api, db_session):
    client, _ = api
    _seed_run(db_session)
    _seed_events(db_session, n=6000)
    seqs, after, calls = [], 0, 0
    while True:
        body = client.get(f"/api/runs/run-1/events?after={after}&limit=5000").json()
        calls += 1
        seqs += [e["seq"] for e in body["events"]]
        if not body["has_more"]:
            break
        after = body["next_after"]
    assert seqs == list(range(1, 6001)) and calls == 2
    # past the end: empty page, cursor echoes after
    tail = client.get("/api/runs/run-1/events?after=6000").json()
    assert tail["events"] == [] and tail["has_more"] is False and tail["next_after"] == 6000
    # exact multiple of limit: has_more must be False on the last full page
    last = client.get("/api/runs/run-1/events?after=5000&limit=1000").json()
    assert len(last["events"]) == 1000 and last["has_more"] is False and last["next_after"] == 6000
    # default page is 1000
    bare = client.get("/api/runs/run-1/events").json()
    assert len(bare["events"]) == 1000 and bare["next_after"] == 1000


def test_bad_params_are_422(api, db_session):
    client, _ = api
    _seed_run(db_session)
    _seed_events(db_session, n=3)
    for q in ("limit=0", "limit=5001", "after=-1", "limit=-1"):
        assert client.get(f"/api/runs/run-1/events?{q}").status_code == 422, q


def test_page_stays_owner_scoped(api, db_session):
    client, state = api
    _seed_run(db_session)
    _seed_events(db_session, n=3)
    _seed_events(db_session, n=3, owner_id="other", workspace_id="ws-1")
    body = client.get("/api/runs/run-1/events").json()
    assert [e["seq"] for e in body["events"]] == [1, 2, 3]
    state["user"] = _FakeUser(id="attacker")
    assert client.get("/api/runs/run-1/events").status_code == 404
