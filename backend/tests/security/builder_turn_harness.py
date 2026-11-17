"""Run one whole builder Turn offline, for the security tests that need the real agent loop.

``run_scripted_turn`` runs ``turns.run_turn`` with the real ``TurnRunner``, the real
``DeepAgentRunner`` loop, the observer middleware, the file backend and the tools. The
model is the scripted ``FakeChatModel``, the Server_Gate is ``FakeGate`` and the store is
``InMemoryBuilderStore``. No Docker, database, network, model or subprocess is involved.

It is a helper, not a test module, and it asserts nothing. It leaves the process-wide
Turn registries and event bus as it found them.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final
from unittest.mock import patch

from app.agents.workflow_builder.skill_package import SKILLS_ROOT
from app.agents.workflow_builder.sandbox import BuilderSandbox
from app.api.workflow_builder import turns
from app.api.workflow_builder.bus import SessionEventBus
from app.api.workflow_builder.turns import (
    LiveTurn,
    TurnDeps,
    TurnRequest,
    attach_task,
    register_live_turn,
    run_turn,
    set_event_bus,
)
from app.core.config import settings
from tests.factories.builder_session_factory import BuilderSessionFactory
from tests.fakes.builder_gate import FakeGate
from tests.fakes.builder_store import InMemoryBuilderStore
from tests.fakes.scripted_chat_model import FakeChatModel, ModelTurn

__all__ = ["BACKEND_SKILLS_ROOT", "TURN_USER", "TurnRun", "run_scripted_turn"]

#: The folder that holds the builder skill folder.
BACKEND_SKILLS_ROOT: Final = SKILLS_ROOT
TURN_USER: Final = "user-turn-harness"
_MODEL_ID: Final = "model-x"


@dataclass(frozen=True)
class TurnRun:
    """What a finished scripted Turn left behind.

    Attributes:
        model: The scripted model; ``model.calls`` holds every message list it saw.
        store: The Session_Store the Turn wrote to.
        sandbox: The Session sandbox the Turn used.
        session_id: The Session id.
        turn_id: The Turn (assistant message) id.
        bus: The event bus the Turn published on.
    """

    model: FakeChatModel
    store: InMemoryBuilderStore
    sandbox: BuilderSandbox
    session_id: str
    turn_id: str
    bus: SessionEventBus


@contextmanager
def _scope(store: InMemoryBuilderStore) -> Iterator[InMemoryBuilderStore]:
    yield store


async def run_scripted_turn(  # noqa: PLR0913 - every input is a named test knob
    *,
    tmp_path: Path,
    model_turns: tuple[ModelTurn, ...],
    canvas_state: dict[str, Any],
    content: str = "Add a review step",
    skills_root: Path = BACKEND_SKILLS_ROOT,
    prepare: Callable[[BuilderSandbox], None] | None = None,
    intake: bool = False,
) -> TurnRun:
    """Run one Turn to its end and return what it left behind.

    ``model_turns`` script the builder call alone, so the intake is off unless
    ``intake`` is True.

    Args:
        tmp_path: Folder for the Session sandbox.
        model_turns: What the scripted model does on each call.
        canvas_state: The canvas sent with the message.
        content: The user's text.
        skills_root: The skill package the Turn serves under ``/skills/``.
        prepare: Called with the sandbox before the Turn starts, to plant files.
        intake: Run the intake call first (``BUILDER_INTAKE_V2_ENABLED``).
    """
    turns._LIVE_TURNS.clear()
    turns._TURN_TASKS.clear()
    store = InMemoryBuilderStore()
    session = store.create_session(TURN_USER, **BuilderSessionFactory.create_kwargs())
    session_id = str(session.id)
    begun = store.begin_turn(
        TURN_USER,
        session_id,
        content=content,
        canvas_state=canvas_state,
        client_message_id="client-message-1",
        model_id=_MODEL_ID,
        effort=None,
        skill_hash="hash",
    )
    sandbox_root = tmp_path / "builder"
    sandbox = BuilderSandbox(TURN_USER, session_id, root=sandbox_root)
    sandbox.ensure()
    if prepare is not None:
        prepare(sandbox)
    bus = SessionEventBus()
    set_event_bus(bus)
    model = FakeChatModel(turns=model_turns)
    deps = TurnDeps(
        bus=bus,
        store_scope=lambda: _scope(store),
        sandbox_factory=lambda user, sid: BuilderSandbox(user, sid, root=sandbox_root),
        gate=FakeGate(),
        chat_model=model,
        skills_root=skills_root,
    )
    live = LiveTurn(
        session_id=session_id,
        turn_id=str(begun.assistant_message.id),
        user_message_id=str(begun.user_message.id),
        user_id=TURN_USER,
        model_id=_MODEL_ID,
        effort=None,
    )
    register_live_turn(live)
    try:
        with patch.object(settings, "BUILDER_INTAKE_V2_ENABLED", intake):
            task = asyncio.ensure_future(
                run_turn(
                    live, TurnRequest(content=content, canvas_state=canvas_state), deps
                )
            )
            attach_task(live, task)
            await task
    finally:
        set_event_bus(None)
        turns._LIVE_TURNS.clear()
        turns._TURN_TASKS.clear()
    return TurnRun(model, store, sandbox, session_id, live.turn_id, bus)
