"""Unit tests for builder admission (task 16.2): the access dependency and
``admit_message`` against ``InMemoryBuilderStore``. The capacity gate and the
turn starter are stubs; no database, network or model is used.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from app.api.workflow_builder import turns
from app.api.workflow_builder.admission import (
    admit_retry,
    BuilderAccess,
    BuilderReadiness,
    admit_message,
    require_builder_access,
    validate_canvas_state,
)
from app.api.workflow_builder.schemas import SendMessageRequest
from app.api.workflow_builder.turns import get_live_turn, release_live_turn
from app.core.config import settings
from app.core.entitlements import group_for_tier
from app.models.workflow_builder import MESSAGE_STATUS_FAILED
from tests.factories.builder_session_factory import BuilderSessionFactory
from tests.fakes.builder_store import InMemoryBuilderStore
from tests.fakes.principal import principal_for

MODEL = "eu.anthropic.claude-sonnet-5-5"
USER_ID = "user-1"
NOW = datetime(2030, 1, 1, tzinfo=UTC)


def _access(user_id: str = USER_ID, tier: str = "enterprise") -> BuilderAccess:
    user = SimpleNamespace(id=user_id, tier=tier, is_admin=False)
    return BuilderAccess(user=user, principal=principal_for(user), tier=tier)  # type: ignore[arg-type]


def _body(**overrides: Any) -> SendMessageRequest:
    values: dict[str, Any] = {
        "content": "Make a workflow",
        "model_id": MODEL,
        "effort": "medium",
        "canvas_state": {"steps": []},
        "client_message_id": "client-msg-0001",
    }
    values.update(overrides)
    return SendMessageRequest(**values)


class _Starter:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, turn: Any, content: str, canvas_state: dict[str, Any]) -> None:
        self.calls.append(turn.turn_id)


def _no_capacity_limit(user: Any) -> None:
    return None


def _code(exc: pytest.ExceptionInfo[HTTPException]) -> str:
    return exc.value.detail["code"]  # type: ignore[index]


@pytest.fixture
def store() -> InMemoryBuilderStore:
    return InMemoryBuilderStore()


@pytest.fixture
def session_id(store: InMemoryBuilderStore) -> str:
    return str(
        store.create_session(USER_ID, **BuilderSessionFactory.create_kwargs()).id
    )


@pytest.fixture
def starter() -> _Starter:
    return _Starter()


@pytest.fixture(autouse=True)
def _release_turns() -> Any:
    yield
    turns._LIVE_TURNS.clear()


async def _admit(
    store: InMemoryBuilderStore,
    session_id: str,
    body: SendMessageRequest,
    starter: _Starter,
    *,
    access: BuilderAccess | None = None,
    capacity_gate: Any = _no_capacity_limit,
):
    return await admit_message(
        store=store,
        access=access or _access(),
        session_id=session_id,
        body=body,
        start_turn=starter,
        capacity_gate=capacity_gate,
        clock=lambda: datetime.now(UTC),
    )


# --- require_builder_access -----------------------------------------------------------


def _auth(tier: str = "enterprise") -> tuple[Any, Any]:
    user = SimpleNamespace(id=USER_ID, tier=tier, is_admin=False)
    return user, principal_for(user)  # type: ignore[arg-type]


def _ready() -> BuilderReadiness:
    readiness = BuilderReadiness()
    readiness.mark_ready()
    return readiness


def test_require_builder_access_returns_403_when_tier_lacks_custom() -> None:
    assert group_for_tier("basic")
    with pytest.raises(HTTPException) as exc:
        require_builder_access(_auth("basic"), _ready())
    assert exc.value.status_code == 403
    assert _code(exc) == "custom_entitlement_required"


def test_require_builder_access_returns_503_when_not_ready() -> None:
    with pytest.raises(HTTPException) as exc:
        require_builder_access(_auth(), BuilderReadiness())
    assert exc.value.status_code == 503
    assert _code(exc) == "builder_unavailable"
    assert exc.value.detail["recoverable"] is False  # type: ignore[index]


def test_require_builder_access_returns_access_when_all_pass() -> None:
    access = require_builder_access(_auth(), _ready())
    assert access.tier == "enterprise"
    assert access.user.id == USER_ID


# --- validate_canvas_state ------------------------------------------------------------


@pytest.mark.parametrize(
    "canvas",
    [
        [],
        {},
        {"steps": {}},
        {"steps": ["x"]},
        {"steps": [{"a": "x" * 200_001}]},
    ],
)
def test_validate_canvas_state_raises_422_when_structure_invalid(canvas: Any) -> None:
    with pytest.raises(HTTPException) as exc:
        validate_canvas_state(canvas)
    assert exc.value.status_code == 422
    assert _code(exc) == "canvas_state_invalid"


def test_validate_canvas_state_raises_422_when_nesting_too_deep() -> None:
    node: dict[str, Any] = {}
    for _ in range(40):
        node = {"n": node}
    with pytest.raises(HTTPException) as exc:
        validate_canvas_state({"steps": [node]})
    assert _code(exc) == "canvas_state_invalid"


def test_validate_canvas_state_raises_413_when_over_byte_cap(monkeypatch) -> None:
    monkeypatch.setattr(settings, "BUILDER_MAX_CANVAS_STATE_BYTES", 40)
    with pytest.raises(HTTPException) as exc:
        validate_canvas_state({"steps": [{"name": "é" * 30}]})
    assert exc.value.status_code == 413
    assert _code(exc) == "canvas_state_too_large"


def test_validate_canvas_state_counts_utf8_bytes_when_not_ascii(monkeypatch) -> None:
    # {"steps":[{"n":"ééé"}]} is 23 characters and 26 UTF-8 bytes.
    canvas = {"steps": [{"n": "ééé"}]}
    monkeypatch.setattr(settings, "BUILDER_MAX_CANVAS_STATE_BYTES", 26)
    validate_canvas_state(canvas)
    monkeypatch.setattr(settings, "BUILDER_MAX_CANVAS_STATE_BYTES", 25)
    with pytest.raises(HTTPException):
        validate_canvas_state(canvas)


# --- admit_message --------------------------------------------------------------------


async def test_admit_message_stores_rows_and_starts_turn_when_all_checks_pass(
    store, session_id, starter
) -> None:
    accepted = await _admit(store, session_id, _body(), starter)

    assert accepted.replayed is False
    assert starter.calls == [accepted.turn_id]
    rows = store.list_messages(USER_ID, session_id)
    assert [r.role for r in rows] == ["user", "assistant"]
    session = store.get_session(USER_ID, session_id)
    assert session.model_id == MODEL
    assert session.effort == "medium"
    assert session.title == "Make a workflow"
    live = get_live_turn(session_id)
    assert live is not None
    release_live_turn(live)


async def test_admit_message_returns_original_ids_when_client_message_id_repeats(
    store, session_id, starter
) -> None:
    first = await _admit(store, session_id, _body(), starter)

    again = await _admit(store, session_id, _body(), starter)

    assert again.replayed is True
    assert (again.turn_id, again.message_id) == (first.turn_id, first.message_id)
    assert len(starter.calls) == 1
    assert len(store.list_messages(USER_ID, session_id)) == 2
    live = get_live_turn(session_id)
    assert live is not None
    release_live_turn(live)


async def test_admit_message_returns_404_when_session_belongs_to_other_user(
    store, session_id, starter
) -> None:
    with pytest.raises(HTTPException) as exc:
        await _admit(store, session_id, _body(), starter, access=_access("user-2"))
    assert exc.value.status_code == 404
    assert _code(exc) == "session_not_found"


async def test_admit_message_returns_409_when_turn_is_running(
    store, session_id, starter
) -> None:
    await _admit(store, session_id, _body(), starter)

    with pytest.raises(HTTPException) as exc:
        await _admit(
            store, session_id, _body(client_message_id="client-msg-0002"), starter
        )

    assert exc.value.status_code == 409
    assert _code(exc) == "turn_running"
    assert len(store.list_messages(USER_ID, session_id)) == 2
    live = get_live_turn(session_id)
    assert live is not None
    release_live_turn(live)


@pytest.mark.parametrize(
    ("overrides", "status_code", "code"),
    [
        ({"model_id": "no-such-model"}, 422, "model_not_allowed"),
        ({"effort": "bogus"}, 422, "effort_not_allowed"),
        ({"canvas_state": {"nope": 1}}, 422, "canvas_state_invalid"),
    ],
)
async def test_admit_message_refuses_and_stores_nothing_when_choice_or_canvas_invalid(
    store, session_id, starter, overrides, status_code, code
) -> None:
    with pytest.raises(HTTPException) as exc:
        await _admit(store, session_id, _body(**overrides), starter)

    assert exc.value.status_code == status_code
    assert _code(exc) == code
    assert store.list_messages(USER_ID, session_id) == []
    assert starter.calls == []


async def test_admit_message_returns_409_when_session_turn_limit_reached(
    store, session_id, starter, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "BUILDER_MAX_TURNS_PER_SESSION", 1)
    first = await _admit(store, session_id, _body(), starter)
    store.finalize_assistant(USER_ID, first.turn_id, status="completed")

    with pytest.raises(HTTPException) as exc:
        await _admit(
            store, session_id, _body(client_message_id="client-msg-0002"), starter
        )

    assert exc.value.status_code == 409
    assert _code(exc) == "session_turn_limit"
    live = get_live_turn(session_id)
    assert live is not None
    release_live_turn(live)


async def test_admit_message_returns_429_with_retry_after_when_rate_exceeded(
    store, session_id, starter, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "BUILDER_MESSAGES_PER_MINUTE", 1)
    first = await _admit(store, session_id, _body(), starter)
    store.finalize_assistant(USER_ID, first.turn_id, status="completed")

    with pytest.raises(HTTPException) as exc:
        await _admit(
            store, session_id, _body(client_message_id="client-msg-0002"), starter
        )

    assert exc.value.status_code == 429
    assert _code(exc) == "rate_limited"
    retry_after = int((exc.value.headers or {})["Retry-After"])
    assert 1 <= retry_after <= 60
    assert len(store.list_messages(USER_ID, session_id)) == 2
    live = get_live_turn(session_id)
    assert live is not None
    release_live_turn(live)


async def test_admit_message_admits_when_oldest_message_left_rate_window(
    store, session_id, starter, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "BUILDER_MESSAGES_PER_MINUTE", 1)
    first = await _admit(store, session_id, _body(), starter)
    store.finalize_assistant(USER_ID, first.turn_id, status="completed")

    later = await admit_message(
        store=store,
        access=_access(),
        session_id=session_id,
        body=_body(client_message_id="client-msg-0002"),
        start_turn=starter,
        capacity_gate=_no_capacity_limit,
        clock=lambda: datetime.now(UTC) + timedelta(seconds=61),
    )

    assert later.replayed is False
    live = get_live_turn(session_id)
    assert live is not None
    release_live_turn(live)


async def test_admit_message_returns_429_when_user_has_too_many_running_turns(
    store, starter, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "BUILDER_MAX_RUNNING_TURNS_PER_USER", 1)
    first_id = str(
        store.create_session(USER_ID, **BuilderSessionFactory.create_kwargs()).id
    )
    second_id = str(
        store.create_session(USER_ID, **BuilderSessionFactory.create_kwargs()).id
    )
    await _admit(store, first_id, _body(), starter)

    with pytest.raises(HTTPException) as exc:
        await _admit(
            store, second_id, _body(client_message_id="client-msg-0002"), starter
        )

    assert exc.value.status_code == 429
    assert _code(exc) == "too_many_running_turns"
    assert (exc.value.headers or {})["Retry-After"] == "15"
    live = get_live_turn(first_id)
    assert live is not None
    release_live_turn(live)


async def test_admit_message_checks_capacity_last_and_stores_nothing_when_busy(
    store, session_id, starter
) -> None:
    def busy(user: Any) -> None:
        raise HTTPException(status_code=503, detail={"code": "host_capacity_exhausted"})

    with pytest.raises(HTTPException) as exc:
        await _admit(store, session_id, _body(), starter, capacity_gate=busy)
    assert exc.value.status_code == 503
    assert store.list_messages(USER_ID, session_id) == []

    # A message refused earlier in the order never reaches the capacity gate.
    with pytest.raises(HTTPException) as exc2:
        await _admit(
            store,
            session_id,
            _body(model_id="no-such-model"),
            starter,
            capacity_gate=busy,
        )
    assert _code(exc2) == "model_not_allowed"


async def test_admit_message_fails_row_and_returns_503_when_starter_raises(
    store, session_id
) -> None:
    def broken(turn: Any, content: str, canvas_state: dict[str, Any]) -> None:
        raise RuntimeError("boom")

    with pytest.raises(HTTPException) as exc:
        await admit_message(
            store=store,
            access=_access(),
            session_id=session_id,
            body=_body(),
            start_turn=broken,
            capacity_gate=_no_capacity_limit,
        )

    assert exc.value.status_code == 503
    assert _code(exc) == "turn_start_failed"
    assert store.get_running_turn(USER_ID, session_id) is None
    assert get_live_turn(session_id) is None


async def test_admit_message_starts_live_turn_with_callers_tier_when_enterprise(
    store, session_id, starter
) -> None:
    await _admit(store, session_id, _body(), starter, access=_access(tier="enterprise"))

    live = get_live_turn(session_id)
    assert live is not None
    assert live.tier == "enterprise"


async def test_admit_retry_starts_live_turn_with_callers_tier_when_enterprise(
    store, session_id, starter
) -> None:
    first = await _admit(store, session_id, _body(), starter)
    live = get_live_turn(session_id)
    assert live is not None
    release_live_turn(live)
    store.finalize_assistant(USER_ID, first.turn_id, status=MESSAGE_STATUS_FAILED)

    retried = await admit_retry(
        store=store,
        access=_access(tier="enterprise"),
        session_id=session_id,
        turn_id=first.turn_id,
        start_turn=starter,
        capacity_gate=_no_capacity_limit,
        clock=lambda: datetime.now(UTC),
    )

    assert retried.turn_id != first.turn_id
    retry_live = get_live_turn(session_id)
    assert retry_live is not None
    assert retry_live.turn_id == retried.turn_id
    assert retry_live.tier == "enterprise"


# --- Check order (design 3.1.2, checks 6 to 16) -----------------------------------------


class _SpyStore:
    """Delegates to ``InMemoryBuilderStore`` and records the order of store calls."""

    def __init__(self, inner: InMemoryBuilderStore, log: list[str]) -> None:
        self._inner = inner
        self._log = log

    def __getattr__(self, name: str) -> Any:
        target = getattr(self._inner, name)
        if not callable(target):
            return target

        def call(*args: Any, **kwargs: Any) -> Any:
            self._log.append(name)
            return target(*args, **kwargs)

        return call


async def test_admit_message_calls_dependencies_in_design_order_when_admitted(
    store, session_id, starter
) -> None:
    log: list[str] = []

    def capacity(user: Any) -> None:
        log.append("capacity_gate")

    await _admit(
        _SpyStore(store, log),  # type: ignore[arg-type]
        session_id,
        _body(),
        starter,
        capacity_gate=capacity,
    )

    assert log == [
        "get_session",  # 6
        "find_user_message_by_client_id",  # 7
        "get_running_turn",  # 8
        "count_user_messages_since",  # 13
        "count_running_turns",  # 14
        "capacity_gate",  # 15
        "begin_turn",  # 16
    ]


async def test_admit_message_stops_at_first_failing_check_when_session_is_missing(
    store, starter
) -> None:
    log: list[str] = []

    with pytest.raises(HTTPException) as exc:
        await _admit(
            _SpyStore(store, log),  # type: ignore[arg-type]
            "no-such-session",
            _body(),
            starter,
        )

    assert _code(exc) == "session_not_found"
    assert log == ["get_session"]


# The refusal codes of checks 8 to 15, in design order.
_ORDERED_VIOLATIONS = [
    "turn_running",
    "model_not_allowed",
    "canvas_state_invalid",
    "session_turn_limit",
    "rate_limited",
    "too_many_running_turns",
    "host_capacity_exhausted",
]


@pytest.mark.parametrize("index", range(len(_ORDERED_VIOLATIONS)))
async def test_admit_message_reports_earliest_violation_when_later_checks_also_fail(
    index: int, store, session_id, starter, monkeypatch
) -> None:
    active = set(_ORDERED_VIOLATIONS[index:])
    first = await _admit(store, session_id, _body(), starter)
    if "turn_running" not in active:
        store.finalize_assistant(USER_ID, first.turn_id, status="completed")
    if "session_turn_limit" in active:
        monkeypatch.setattr(settings, "BUILDER_MAX_TURNS_PER_SESSION", 0)
    if "rate_limited" in active:
        monkeypatch.setattr(settings, "BUILDER_MESSAGES_PER_MINUTE", 0)
    if "too_many_running_turns" in active:
        monkeypatch.setattr(settings, "BUILDER_MAX_RUNNING_TURNS_PER_USER", 0)

    def capacity(user: Any) -> None:
        if "host_capacity_exhausted" in active:
            raise HTTPException(
                status_code=503, detail={"code": "host_capacity_exhausted"}
            )

    body = _body(
        client_message_id="client-msg-0002",
        model_id="no-such-model" if "model_not_allowed" in active else MODEL,
        canvas_state={"bad": 1} if "canvas_state_invalid" in active else {"steps": []},
    )

    with pytest.raises(HTTPException) as exc:
        await _admit(store, session_id, body, starter, capacity_gate=capacity)

    assert _code(exc) == _ORDERED_VIOLATIONS[index]
    assert len(store.list_messages(USER_ID, session_id)) == 2  # nothing new stored
    assert len(starter.calls) == 1


async def test_admit_message_replays_before_any_later_check_when_id_was_stored(
    store, session_id, starter, monkeypatch
) -> None:
    await _admit(store, session_id, _body(), starter)
    monkeypatch.setattr(settings, "BUILDER_MAX_TURNS_PER_SESSION", 0)
    monkeypatch.setattr(settings, "BUILDER_MESSAGES_PER_MINUTE", 0)
    log: list[str] = []

    again = await _admit(
        _SpyStore(store, log),  # type: ignore[arg-type]
        session_id,
        _body(model_id="no-such-model", canvas_state={"bad": 1}),
        starter,
    )

    assert again.replayed is True
    assert log == ["get_session", "find_user_message_by_client_id"]
