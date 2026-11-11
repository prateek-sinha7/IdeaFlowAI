"""Property tests for the terminal status of a builder Turn.

# Feature: ai-workflow-builder, Property 15: A turn ends with exactly one status

For any sequence of stop signals arriving at any point, together with normal
completion or failure, the Turn stores exactly one terminal status and publishes
exactly one ``turn_completed`` (none when the Session was deleted, because its
rows are going away). The first stop signal decides the status. An unproposed
revision is stored if and only if the ending is not a plain completion, no draft
was accepted and a ``/workflows/*.workflow.json`` file changed.

**Validates: Requirements 21.9, 22.1, 22.3, 23.18, 30.3, 30.5, 48.16**

The system under test is ``run_turn`` with ``finalize_turn``, ``cancel_turn`` and
``stop_session_turn``. The model is ``FakeChatModel``, the gate is ``FakeGate``
and the store is ``InMemoryBuilderStore``; nothing touches a database or the
network. The expected status comes from the table ``_FIRST_REASON_STATUS`` below,
not from ``status_for_stop``.

The tests are synchronous and drive the event loop with ``asyncio.run``, because
Hypothesis does not await coroutine tests.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.agents.workflow_builder.skill_package import SKILLS_ROOT
from app.agents.workflow_builder.events import (
    BuilderEvent,
    TurnCompleted,
)
from app.agents.workflow_builder.sandbox import BuilderSandbox
from app.api.workflow_builder import turns
from app.api.workflow_builder.bus import SessionEventBus
from app.api.workflow_builder.turns import (
    LiveTurn,
    TurnDeps,
    TurnRequest,
    attach_task,
    build_snapshot,
    cancel_turn,
    register_live_turn,
    run_turn,
    stop_session_turn,
)
from app.core.config import settings as app_settings
from tests.factories.builder_session_factory import BuilderSessionFactory
from tests.fakes.builder_gate import FakeGate
from tests.fakes.builder_store import InMemoryBuilderStore
from tests.fakes.scripted_chat_model import FakeChatModel, ModelTurn, ScriptedToolCall
from tests.property.budget import examples

USER = "user-a"
_SKILLS_ROOT = SKILLS_ROOT
_MANIFEST: dict[str, Any] = {"id": "wf-one", "steps": [{"agent": "custom-agent"}]}
_PATH = "/workflows/a.workflow.json"
_WRITE = ScriptedToolCall(
    "write_file", {"file_path": _PATH, "content": json.dumps(_MANIFEST)}
)
_PROPOSE = ScriptedToolCall("propose_draft", {"path": _PATH})
_SLOW = ModelTurn(text=("late",), delay=30.0)

# The oracle: the status each stop reason must end the Turn with.
_FIRST_REASON_STATUS: dict[str, str] = {
    "time": "timed_out",
    "tool_calls": "timed_out",
    "tokens": "timed_out",
    "recursion": "timed_out",
    "gate_rejections": "completed",
    "cancelled": "cancelled",
    "deleted": "cancelled",
    "shutdown": "interrupted",
    "restart": "interrupted",
}
_STOP_REASONS = sorted(_FIRST_REASON_STATUS)
_TERMINAL = {"completed", "failed", "timed_out", "cancelled", "interrupted"}

_stop_sequences = st.lists(st.sampled_from(_STOP_REASONS), min_size=1, max_size=4)
_stopped_scripts = st.sampled_from(["plain", "wrote", "accepted"])
_natural_endings = st.sampled_from(["reply", "error", "recursion", "tool_cap"])


def _scope(store: InMemoryBuilderStore) -> Callable[[], Any]:
    @contextmanager
    def scope() -> Iterator[InMemoryBuilderStore]:
        yield store

    return scope


def _begin(store: InMemoryBuilderStore) -> LiveTurn:
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
    return LiveTurn(
        session_id=str(session.id),
        turn_id=str(begun.assistant_message.id),
        user_message_id=str(begun.user_message.id),
        user_id=USER,
        model_id="model-x",
        effort=None,
    )


def _deps(
    store: InMemoryBuilderStore, bus: SessionEventBus, root: Path, model: FakeChatModel
) -> TurnDeps:
    return TurnDeps(
        bus=bus,
        store_scope=_scope(store),
        sandbox_factory=lambda user, session: BuilderSandbox(
            user, session, root=root / "builder"
        ),
        gate=FakeGate(),
        chat_model=model,
        skills_root=_SKILLS_ROOT,
    )


def _drain(queue: asyncio.Queue[BuilderEvent | None]) -> list[BuilderEvent]:
    events: list[BuilderEvent] = []
    while not queue.empty():
        item = queue.get_nowait()
        if item is not None:
            events.append(item)
    return events


async def _wait_until(predicate: Callable[[], bool]) -> None:
    async def poll() -> None:
        while not predicate():
            await asyncio.sleep(0.005)

    await asyncio.wait_for(poll(), 10.0)


def _model_for(script: str) -> FakeChatModel:
    if script == "wrote":
        return FakeChatModel(turns=(ModelTurn(tool_calls=(_WRITE,)), _SLOW))
    if script == "accepted":
        return FakeChatModel(
            turns=(
                ModelTurn(tool_calls=(_WRITE,)),
                ModelTurn(tool_calls=(_PROPOSE,)),
                _SLOW,
            )
        )
    return FakeChatModel(turns=(_SLOW,))


def _fire(live: LiveTurn, reasons: list[str]) -> None:
    """Send the first signal through its public entry point, then the rest."""
    first = reasons[0]
    if first == "cancelled":
        assert cancel_turn(live.session_id, live.turn_id) == "cancelling"
    elif first == "deleted":
        assert stop_session_turn(live.session_id) is True
    else:
        live.stop(first)  # type: ignore[arg-type]
    for reason in reasons[1:]:
        live.stop(reason)  # type: ignore[arg-type]


def _check_one_status(
    store: InMemoryBuilderStore,
    live: LiveTurn,
    events: list[BuilderEvent],
    expected: str,
) -> TurnCompleted:
    completed = [e for e in events if isinstance(e, TurnCompleted)]
    assert len(completed) == 1
    assert events[-1] is completed[0]
    assert completed[0].status == expected
    assert completed[0].status in _TERMINAL
    row = store.get_message(USER, live.turn_id)
    assert row is not None
    assert row.status == expected
    assert turns.get_live_turn(live.session_id) is None
    return completed[0]


async def _stopped_turn(script: str, reasons: list[str], root: Path) -> None:
    store = InMemoryBuilderStore()
    bus = SessionEventBus(queue_maxsize=1000)
    live = _begin(store)
    queue, _ = bus.subscribe(
        live.session_id,
        lambda: build_snapshot(live.session_id, user_id=USER, store=store),
    )
    register_live_turn(live)
    task = asyncio.ensure_future(
        run_turn(
            live,
            TurnRequest(content="make a workflow", canvas_state={"steps": []}),
            _deps(store, bus, root, _model_for(script)),
        )
    )
    attach_task(live, task)
    if script == "wrote":
        await _wait_until(lambda: bool(live.changed_workflow_files))
    elif script == "accepted":
        await _wait_until(lambda: live.accepted_revision is not None)
    else:
        await _wait_until(lambda: live.stage is not None)

    _fire(live, reasons)
    await asyncio.wait_for(task, 10.0)

    events = _drain(queue)
    first = reasons[0]
    if first == "deleted":
        assert not [e for e in events if isinstance(e, TurnCompleted)]
        assert turns.get_live_turn(live.session_id) is None
        return
    expected = _FIRST_REASON_STATUS[first]
    done = _check_one_status(store, live, events, expected)
    assert done.stop_reason == first
    unproposed = store.get_latest_revisions(USER, live.session_id).unproposed
    ends_unfinished = expected != "completed" or first == "gate_rejections"
    if script == "wrote" and ends_unfinished:
        assert unproposed is not None
        assert unproposed.manifest == _MANIFEST
        assert unproposed.source_file == _PATH
    else:
        assert unproposed is None
    if script == "accepted":
        assert done.outcome == "draft"
        assert done.revision == 1


async def _natural_turn(ending: str, root: Path) -> None:
    store = InMemoryBuilderStore()
    bus = SessionEventBus(queue_maxsize=1000)
    live = _begin(store)
    queue, _ = bus.subscribe(
        live.session_id,
        lambda: build_snapshot(live.session_id, user_id=USER, store=store),
    )
    scripts: dict[str, FakeChatModel] = {
        "reply": FakeChatModel(turns=(ModelTurn(text=("ok",)),)),
        "error": FakeChatModel(turns=(ModelTurn(error=ValueError("boom")),)),
        "recursion": FakeChatModel(
            turns=(ModelTurn(error=RuntimeError("Recursion limit of 2500 reached")),)
        ),
        "tool_cap": FakeChatModel(
            turns=(
                ModelTurn(tool_calls=(ScriptedToolCall("get_builder_models", {}),)),
            ),
            repeat_last=True,
        ),
    }
    expected = {
        "reply": ("completed", None),
        "error": ("failed", "error"),
        "recursion": ("timed_out", "recursion"),
        "tool_cap": ("timed_out", "tool_calls"),
    }[ending]
    register_live_turn(live)
    with patch.object(app_settings, "BUILDER_MAX_TOOL_CALLS_PER_TURN", 2):
        await run_turn(
            live,
            TurnRequest(content="make a workflow", canvas_state={"steps": []}),
            _deps(store, bus, root, scripts[ending]),
        )

    done = _check_one_status(store, live, _drain(queue), expected[0])
    assert done.stop_reason == expected[1]
    assert store.get_latest_revisions(USER, live.session_id).unproposed is None


def _fresh_state() -> None:
    turns._LIVE_TURNS.clear()
    turns._TURN_TASKS.clear()


@settings(
    max_examples=examples(100, quick=25),
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(script=_stopped_scripts, reasons=_stop_sequences)
def test_run_turn_stores_status_of_first_stop_when_signals_arrive_in_any_order(
    script: str, reasons: list[str]
) -> None:
    # Feature: ai-workflow-builder, Property 15: A turn ends with exactly one status
    _fresh_state()
    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(_stopped_turn(script, list(reasons), Path(tmp)))


@settings(
    max_examples=examples(100, quick=25),
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(ending=_natural_endings)
def test_run_turn_stores_one_status_when_turn_ends_without_a_stop_signal(
    ending: str,
) -> None:
    # Feature: ai-workflow-builder, Property 15: A turn ends with exactly one status
    _fresh_state()
    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(_natural_turn(ending, Path(tmp)))
