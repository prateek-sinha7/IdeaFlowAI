"""Opt-in performance test: builder events reach every connected client within 1 s.

Validates: Requirement 43.3. When the Turn_Runner emits a ``stage``,
``tool_started``, ``tool_finished``, ``check_result`` or ``limit_warning`` event,
the Session_Stream delivers it to every connected client of the Session within
1 s of the moment it was published.

The system under test is ``run_turn`` with the real ``TurnRunner``, the real
``DeepAgentRunner`` loop, the observer middleware, ``run_skill_script`` and
``propose_draft``, publishing through a ``SessionEventBus`` that has several
subscribed clients. The model is ``FakeChatModel``, the Server_Gate is
``FakeGate``, the script process is ``FakeProcessFactory`` and the store is
``InMemoryBuilderStore``. No Docker, database, network, model or subprocess is
used, so this file does not need the throwaway PostgreSQL fixtures.

Each client is an ``asyncio`` task that awaits its own bus queue, the same call the
Session_Stream route makes, and stamps the arrival time. The bus is wrapped so
that every publish is stamped too. Delivery latency is arrival minus publish.

Opt-in: the folder hook in ``tests/conftest.py`` marks everything under
``tests/performance/`` with ``performance``. Run it with ``pytest -m performance``
and leave it out of the PR pipeline with ``-m "not performance"``.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Any, Final
from unittest.mock import patch

import pytest

from app.agents.workflow_builder.skill_package import SKILLS_ROOT
from app.agents.workflow_builder.events import (
    BuilderEvent,
    TurnScoped,
)
from app.agents.workflow_builder.ports import TurnLimits
from app.agents.workflow_builder.sandbox import BuilderSandbox
from app.agents.workflow_builder.script_policy import BUILDER_SKILL_ID
from app.agents.workflow_builder.script_runner import ScriptContext
from app.api.workflow_builder import turns
from app.api.workflow_builder.bus import SessionEventBus, SessionQueue
from app.api.workflow_builder.turns import (
    LiveTurn,
    TurnDeps,
    TurnRequest,
    attach_task,
    build_snapshot,
    register_live_turn,
    run_turn,
    set_event_bus,
)
from app.core.config import settings
from tests.factories.builder_session_factory import BuilderSessionFactory
from tests.fakes.builder_gate import FakeGate
from tests.fakes.builder_store import InMemoryBuilderStore
from tests.fakes.process_factory import FakeProcessFactory, ProcessScript
from tests.fakes.scripted_chat_model import FakeChatModel, ModelTurn, ScriptedToolCall

USER: Final = "user-a"
#: Requirement 43.3: the delivery budget for one event, in seconds.
DELIVERY_BUDGET_SECONDS: Final = 1.0


@pytest.fixture(autouse=True, scope="module")
def _old_builder_path() -> Iterator[None]:
    """The script here drives the builder call alone: run with the intake off."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "BUILDER_INTAKE_V2_ENABLED", False)
        yield


CLIENT_COUNT: Final = 5

_SKILLS_ROOT: Final = SKILLS_ROOT
_SCRIPTS: Final = f"/skills/{BUILDER_SKILL_ID}/scripts"
_MANIFEST_PATH: Final = "/workflows/a.workflow.json"
_MANIFEST: Final[dict[str, Any]] = {
    "id": "wf-one",
    "steps": [{"agent": "custom-agent"}],
}
_VALID_LINE: Final = "VALID: 0 error(s), 0 warning(s)\n"

#: The five event types Requirement 43.3 covers.
_COVERED_TYPES: Final = frozenset(
    {"stage", "tool_started", "tool_finished", "check_result", "limit_warning"}
)

#: Five calls in all; the 80 % warning point is the fourth call, which is the
#: ``propose_draft`` call below, so ``limit_warning`` is sent during the Turn.
_LIMITS: Final = TurnLimits(
    timeout_seconds=900,
    max_tool_calls=5,
    max_gate_rejections=2,
    warning_fraction=0.8,
)

type EventKey = tuple[str, int]


def _key(event: BuilderEvent) -> EventKey:
    """Identify a Turn-scoped event by its type and its ``seq``."""
    assert isinstance(event, TurnScoped)
    return (event.type, event.seq)


@dataclass
class _Clock:
    """Reads one monotonic clock shared by the bus and the clients."""

    now: Callable[[], float]
    published: dict[EventKey, float] = field(default_factory=dict)


class _TimedBus(SessionEventBus):
    """A ``SessionEventBus`` that stamps the time of every Turn-scoped publish."""

    def __init__(self, clock: _Clock) -> None:
        super().__init__(queue_maxsize=10_000)
        self._clock = clock

    def publish(self, session_id: str, event: BuilderEvent) -> None:
        """Record the publish time, then fan the event out unchanged."""
        if isinstance(event, TurnScoped):
            self._clock.published[_key(event)] = self._clock.now()
        super().publish(session_id, event)


async def _read_client(queue: SessionQueue, clock: _Clock) -> dict[EventKey, float]:
    """Read a client queue until the close sentinel; return arrival times by event."""
    arrived: dict[EventKey, float] = {}
    while (event := await queue.get()) is not None:
        if isinstance(event, TurnScoped):
            arrived[_key(event)] = clock.now()
    return arrived


@contextmanager
def _scope(store: Any) -> Iterator[Any]:
    yield store


def _model() -> FakeChatModel:
    """A model that makes four tool calls, one per model call, then answers."""
    validate = f"python {_SCRIPTS}/validate_manifest.py {_MANIFEST_PATH}"
    calls = (
        ScriptedToolCall("get_builder_models", {}),
        ScriptedToolCall(
            "write_file",
            {"file_path": _MANIFEST_PATH, "content": json.dumps(_MANIFEST)},
        ),
        ScriptedToolCall("run_skill_script", {"command": validate}),
        ScriptedToolCall("propose_draft", {"path": _MANIFEST_PATH}),
    )
    scripted = [ModelTurn(tool_calls=(call,)) for call in calls]
    scripted.append(ModelTurn(text=("done",)))
    return FakeChatModel(turns=tuple(scripted))


@pytest.fixture
def _clean_turn_registry() -> Iterator[None]:
    """Empty the process-wide Turn registries and the bus around the test."""
    turns._LIVE_TURNS.clear()
    turns._TURN_TASKS.clear()
    yield
    set_event_bus(None)
    turns._LIVE_TURNS.clear()
    turns._TURN_TASKS.clear()


@pytest.mark.usefixtures("_clean_turn_registry")
async def test_event_delivery_stays_within_budget_when_clients_are_connected(
    tmp_path: Path,
    timer: Callable[[], float],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Req 43.3: every covered event reaches every client within 1 s of publish."""
    # Arrange: a Session with CLIENT_COUNT subscribed clients on a timed bus.
    clock = _Clock(now=timer)
    bus = _TimedBus(clock)
    set_event_bus(bus)
    store = InMemoryBuilderStore()
    session = store.create_session(USER, **BuilderSessionFactory.create_kwargs())
    begun = store.begin_turn(
        USER,
        str(session.id),
        content="hello",
        canvas_state=None,
        client_message_id="client-message-1",
        model_id="model-x",
        effort=None,
        skill_hash="hash",
    )
    live = LiveTurn(
        session_id=str(session.id),
        turn_id=str(begun.assistant_message.id),
        user_message_id=str(begun.user_message.id),
        user_id=USER,
        model_id="model-x",
        effort=None,
    )
    monkeypatch.setattr(turns, "limits_from_settings", lambda: _LIMITS)
    factory = FakeProcessFactory(ProcessScript.with_text(_VALID_LINE, exit_code=0))
    deps = TurnDeps(
        bus=bus,
        store_scope=lambda: _scope(store),
        sandbox_factory=lambda user, sid: BuilderSandbox(
            user, sid, root=tmp_path / "builder"
        ),
        gate=FakeGate(),
        chat_model=_model(),
        skills_root=_SKILLS_ROOT,
    )
    request = TurnRequest(content="make a workflow", canvas_state={"steps": []})
    clients = [
        asyncio.ensure_future(_read_client(queue, clock))
        for queue in (
            bus.subscribe(
                live.session_id,
                lambda: build_snapshot(
                    live.session_id,
                    user_id=USER,
                    store=InMemoryBuilderStore(),
                ),
            )[0]
            for _ in range(CLIENT_COUNT)
        )
    ]
    assert bus.subscriber_count(live.session_id) == CLIENT_COUNT
    spawning = partial(ScriptContext, spawn=factory, semaphore=asyncio.Semaphore(2))
    register_live_turn(live)

    # Act: run the whole Turn, then close every client stream.
    with patch("app.agents.workflow_builder.agent.ScriptContext", spawning):
        task = asyncio.ensure_future(run_turn(live, request, deps))
        attach_task(live, task)
        await task
    bus.close_session(live.session_id, None)
    arrivals = await asyncio.wait_for(asyncio.gather(*clients), timeout=5)

    # Assert: all five covered types were published ...
    covered = {
        key: sent for key, sent in clock.published.items() if key[0] in _COVERED_TYPES
    }
    assert (
        {key[0] for key in covered} == _COVERED_TYPES
    ), "the scripted Turn must publish every event type Requirement 43.3 covers"
    # ... every client got every one of them ...
    for index, arrived in enumerate(arrivals):
        missing = sorted(set(covered) - set(arrived))
        assert not missing, f"client {index} never received {missing}"
    # ... and none took longer than the budget.
    slowest = max(
        arrived[key] - sent for arrived in arrivals for key, sent in covered.items()
    )
    assert (
        slowest < DELIVERY_BUDGET_SECONDS
    ), f"slowest delivery took {slowest:.3f}s (budget {DELIVERY_BUDGET_SECONDS}s)"
