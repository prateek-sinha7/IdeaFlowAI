"""Security: one user cannot reach another user's builder Session (IDOR).

Validates: Requirements 2.6, 2.7, 2.8, 49.7.

Bob is a fully entitled caller. Alice owns a Session with a running Turn, an open
stream client and a sandbox folder. Bob names Alice's Session on every route that takes
a Session id, the stream included. Each call must answer 404 ``session_not_found``,
never 403, with the same body as a Session id that does not exist at all (so the
answer is no oracle for which ids are real). Alice's rows, running Turn, stream
client and sandbox must be unchanged, and Bob's list must not show her Session.

The matrix runs twice: against ``InMemoryBuilderStore`` (always) and against the real
``BuilderStore`` on a throwaway PostgreSQL database, where the ``user_id`` filter is
SQL. The PostgreSQL variant needs ``PYTEST_POSTGRES_ADMIN_URL`` or Docker, so it
skips on a Docker-less machine and runs on the CI runner.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest

from tests.security.builder_world import (
    API,
    BuilderWorld,
    RouteCase,
    WorldKind,
    route_cases,
)

SESSION_SCOPED = tuple(case for case in route_cases if case.session_scoped)
WORLD_KINDS: tuple[WorldKind, ...] = ("in_memory", "postgres")

type WorldFactory = Callable[..., BuilderWorld]


def _case_id(case: RouteCase) -> str:
    return case.signature.replace(API, "")


@pytest.fixture(params=WORLD_KINDS)
def world(
    request: pytest.FixtureRequest, make_builder_world: WorldFactory
) -> BuilderWorld:
    """The builder app over each store kind."""
    kind: WorldKind = request.param
    return make_builder_world(kind=kind)


def test_session_scoped_cases_include_the_stream_when_routes_are_listed() -> None:
    templates = {case.template for case in SESSION_SCOPED}

    assert f"{API}/sessions/{{session_id}}/events" in templates
    assert len(SESSION_SCOPED) == 8


@pytest.mark.parametrize("case", SESSION_SCOPED, ids=_case_id)
def test_builder_route_answers_404_and_changes_nothing_when_session_belongs_to_another_user(
    world: BuilderWorld, case: RouteCase
) -> None:
    alice = world.add_caller("alice")
    bob = world.add_caller("bob")
    owned = world.seed_session(alice, running_turn=True)
    client_queue = world.subscribe(owned.session_id)
    world.bus.subscribes.clear()
    before = world.state()

    foreign = world.send(
        case, caller=bob, session_id=owned.session_id, turn_id=owned.turn_id or "t"
    )
    missing = world.send(
        case,
        caller=bob,
        session_id=str(uuid.uuid4()),
        turn_id=owned.turn_id or "t",
    )

    assert foreign.status_code == 404, foreign.text
    assert foreign.json()["detail"]["code"] == "session_not_found"
    assert (missing.status_code, missing.json()) == (
        foreign.status_code,
        foreign.json(),
    ), "a foreign Session must look exactly like a missing one"
    assert world.state() == before, "a foreign request changed something"
    assert owned.live is not None
    assert owned.live.stop_reason is None, "a foreign request stopped Alice's Turn"
    assert client_queue.empty(), "a foreign request reached Alice's stream client"
    assert (owned.sandbox / "workflows" / "keep.workflow.json").exists()
    assert owned.session_id not in foreign.text


def test_session_list_holds_only_the_callers_sessions_when_two_users_have_sessions(
    world: BuilderWorld,
) -> None:
    alice = world.add_caller("alice")
    bob = world.add_caller("bob")
    alices = world.seed_session(alice)
    bobs = world.seed_session(bob)

    alice_ids = {
        item["id"]
        for item in world.client.get(f"{API}/sessions", headers=alice.headers).json()[
            "items"
        ]
    }
    bob_ids = {
        item["id"]
        for item in world.client.get(f"{API}/sessions", headers=bob.headers).json()[
            "items"
        ]
    }

    assert alice_ids == {alices.session_id}
    assert bob_ids == {bobs.session_id}


def test_owner_still_reaches_session_and_running_turn_when_another_user_attacked_first(
    world: BuilderWorld,
) -> None:
    alice = world.add_caller("alice")
    bob = world.add_caller("bob")
    owned = world.seed_session(alice, running_turn=True)
    turn_id = owned.turn_id or "t"
    for case in SESSION_SCOPED:
        world.send(case, caller=bob, session_id=owned.session_id, turn_id=turn_id)

    detail = world.client.get(
        f"{API}/sessions/{owned.session_id}", headers=alice.headers
    )

    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["id"] == owned.session_id
    assert body["running"] is True
    assert body["running_turn"] is not None
    assert body["running_turn"]["turn_id"] == turn_id
