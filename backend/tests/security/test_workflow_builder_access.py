"""Security: who may call the AI Workflow Builder API at all.

Validates: Requirements 2.4, 2.5, 49.7.

Every builder route is called by an unauthenticated caller, a caller with an invalid
token, and callers whose tier lacks the ``custom`` pipeline. Each call must be refused, and the refusal must leave
everything alone: the Session_Store, the sandbox folders, the live Turn registry, the
event bus (no publish, no subscription, no close), the turn starter, the capacity gate
and the stream generator. The caller owns a Session with a running Turn in every case,
so the access check is the only thing standing between the request and a change.

One control keeps the refusals from being vacuous: an entitled caller gets through on every route, and the route table here is checked against the routes the
app really mounts, so a new route cannot be added without a case.

Everything runs in memory: ``InMemoryBuilderStore``, a recording database mock and the
real dependency chain (``require_builder_access``, and the real ``get_current_principal``
for the unauthenticated cases). No Docker and no database server are needed.
"""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import patch

import pytest
from httpx import Response

from app.core.identity import CredentialInvalid
from tests.security.builder_world import (
    BuilderWorld,
    Caller,
    RouteCase,
    Seeded,
    route_cases,
    route_signatures,
)

#: Tiers whose pipeline set lacks ``custom`` (``TIER_PIPELINES``).
UNENTITLED_TIERS = ("basic", "pro", "hexaware")

#: Codes the access dependency answers with. A request that got through never carries one.
ACCESS_CODES = {"custom_entitlement_required", "builder_unavailable"}

type WorldFactory = Callable[..., BuilderWorld]


def _case_id(case: RouteCase) -> str:
    return case.signature.replace("/api/workflow-builder", "")


def _detail_code(response: Response) -> str | None:
    """The ``detail.code`` of a JSON error body, or ``None`` for any other body."""
    if "json" not in response.headers.get("content-type", ""):
        return None
    body = response.json()
    detail = body.get("detail") if isinstance(body, dict) else None
    return detail.get("code") if isinstance(detail, dict) else None


def _owned_world(
    make_builder_world: WorldFactory,
    *,
    tier: str,
    real_auth: bool = False,
) -> tuple[BuilderWorld, Caller, Seeded]:
    """A world whose caller owns a Session with a running Turn."""
    world = make_builder_world(real_auth=real_auth)
    caller = world.add_caller("owner", tier)
    seeded = world.seed_session(caller, running_turn=True)
    return world, caller, seeded


def _assert_refused_without_effect(
    world: BuilderWorld,
    seeded: Seeded,
    case: RouteCase,
    caller: Caller | None,
    *,
    status_code: int,
    code: str | None,
) -> None:
    before = world.state()

    response = world.send(
        case,
        caller=caller,
        session_id=seeded.session_id,
        turn_id=seeded.turn_id or "turn-1",
    )

    assert response.status_code == status_code, response.text
    assert _detail_code(response) == code
    assert world.state() == before, "a refused request changed something"
    assert seeded.live is not None
    assert seeded.live.stop_reason is None, "a refused request stopped the live Turn"
    assert (seeded.sandbox / "workflows" / "keep.workflow.json").exists()
    assert seeded.session_id not in response.text


# --- The route table covers the real routes ---------------------------------------------


def test_route_cases_cover_every_builder_route_when_the_app_is_mounted(
    make_builder_world: WorldFactory,
) -> None:
    world = make_builder_world()

    mounted = route_signatures(world.app)

    assert mounted == {case.signature for case in route_cases}


# --- Unauthenticated --------------------------------------------------------------------


@pytest.mark.parametrize("case", route_cases, ids=_case_id)
def test_builder_route_answers_401_and_changes_nothing_when_no_credential_is_sent(
    make_builder_world: WorldFactory, case: RouteCase
) -> None:
    world, _owner, seeded = _owned_world(
        make_builder_world, tier="enterprise", real_auth=True
    )

    _assert_refused_without_effect(
        world, seeded, case, None, status_code=401, code=None
    )


@pytest.mark.parametrize("case", route_cases, ids=_case_id)
def test_builder_route_answers_401_and_changes_nothing_when_the_token_is_invalid(
    make_builder_world: WorldFactory, case: RouteCase
) -> None:
    world, _owner, seeded = _owned_world(
        make_builder_world, tier="enterprise", real_auth=True
    )
    stranger = Caller(name="stranger", user=world.callers["owner"].user, token="forged")

    with patch(
        "app.core.dependencies.verify_credential",
        side_effect=CredentialInvalid("bad signature"),
    ):
        _assert_refused_without_effect(
            world, seeded, case, stranger, status_code=401, code=None
        )


# --- No custom entitlement --------------------------------------------------------------


@pytest.mark.parametrize("tier", UNENTITLED_TIERS)
@pytest.mark.parametrize("case", route_cases, ids=_case_id)
def test_builder_route_answers_403_and_changes_nothing_when_tier_lacks_custom(
    make_builder_world: WorldFactory, case: RouteCase, tier: str
) -> None:
    world, owner, seeded = _owned_world(make_builder_world, tier=tier)

    _assert_refused_without_effect(
        world,
        seeded,
        case,
        owner,
        status_code=403,
        code="custom_entitlement_required",
    )


# --- Control: the same requests get through for an entitled caller ----------------------


def test_builder_routes_reach_their_handlers_when_caller_is_entitled(
    make_builder_world: WorldFactory,
) -> None:
    world, owner, seeded = _owned_world(make_builder_world, tier="enterprise")
    reached: dict[str, int] = {}

    for case in route_cases:
        response = world.send(
            case,
            caller=owner,
            session_id=seeded.session_id,
            turn_id=seeded.turn_id or "turn-1",
        )
        reached[case.signature] = response.status_code
        assert response.status_code not in {401, 403, 503}, (case, response.text)
        assert _detail_code(response) not in ACCESS_CODES, (case, response.text)

    assert reached["GET /api/workflow-builder/models"] == 200
    assert reached["POST /api/workflow-builder/sessions"] == 201
    assert reached["GET /api/workflow-builder/sessions/{session_id}/events"] == 200
    assert reached["DELETE /api/workflow-builder/sessions/{session_id}"] == 204
