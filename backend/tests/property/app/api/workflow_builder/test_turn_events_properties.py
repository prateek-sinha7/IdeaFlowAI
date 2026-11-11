"""Property tests for the event stream of a scripted builder Turn.

# Feature: ai-workflow-builder, Property 14: Turn event streams are well formed

For any scripted Turn (any mix of tool calls, refusals, validator runs, dry runs,
``propose_draft`` accepts and rejects, and a stop signal at any gate call), the
published events have strictly increasing ``seq`` starting at 1. Every
``tool_started`` has exactly one ``tool_finished`` with the same ``call_id``. Each
validator run, dry run and gate check yields exactly one ``check_result``. There is
at most one ``draft_applied``, only after an accepted check and never after a stop
was requested. Dry runs never count as rejections, the second rejection ends the
Turn, and ``turn_completed`` is the last event.

**Validates: Requirements 7.1, 23.10, 23.11, 23.12, 30.4, 36.2, 36.10, 38.2, 38.9,
38.10, 38.14, 42.1, 47.3**

The system under test is ``run_turn`` with the real ``TurnRunner``, the real
``DeepAgentRunner`` loop, the observer middleware, ``run_skill_script`` and
``propose_draft``. The model is ``FakeChatModel``, the Server_Gate is a ``FakeGate``
subclass, the script process is ``FakeProcessFactory`` and the store is
``InMemoryBuilderStore``. No database, network, model or subprocess is used.

The oracle never reads ``LiveTurn`` events. Expected counts come from what the
fakes recorded (process starts, gate calls and their verdicts) and from the
scripted stop.

The tests are synchronous and drive the event loop with ``asyncio.run``, because
Hypothesis does not await coroutine tests.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Literal
from unittest.mock import patch

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.agents.workflow_builder.skill_package import SKILLS_ROOT
from app.agents.workflow_builder.events import (
    BuilderEvent,
    CheckResultEvent,
    DraftApplied,
    ErrorEvent,
    ToolFinished,
    ToolStarted,
    TurnCompleted,
    TurnScoped,
)
from app.agents.workflow_builder.ports import GateResult
from app.agents.workflow_builder.sandbox import BuilderSandbox
from app.agents.workflow_builder.script_policy import BUILDER_SKILL_ID
from app.agents.workflow_builder.script_runner import ScriptContext
from app.api.workflow_builder import turns
from app.api.workflow_builder.bus import SessionEventBus
from app.api.workflow_builder.turns import (
    LiveTurn,
    TurnDeps,
    TurnRequest,
    attach_task,
    cancel_turn,
    register_live_turn,
    run_turn,
    set_event_bus,
)
from tests.factories.builder_session_factory import BuilderSessionFactory
from tests.fakes.builder_gate import FakeGate, accepted_result, rejected_result
from tests.fakes.process_factory import FakeProcessFactory, ProcessScript
from tests.fakes.scripted_chat_model import FakeChatModel, ModelTurn, ScriptedToolCall

USER = "user-a"
_SKILLS_ROOT = SKILLS_ROOT
_SCRIPTS = f"/skills/{BUILDER_SKILL_ID}/scripts"
_MANIFEST_PATH = "/workflows/a.workflow.json"
_MANIFEST: dict[str, Any] = {"id": "wf-one", "steps": [{"agent": "custom-agent"}]}
_VALID_LINE = "VALID: 0 error(s), 0 warning(s)\n"
_INVALID_LINE = "INVALID: 2 error(s), 1 warning(s)\n"

Op = Literal[
    "list",
    "write",
    "validate_ok",
    "validate_bad",
    "dry_run",
    "refused",
    "propose",
    "propose_bad_path",
]
StopKind = Literal["check", "dry_run"]

_OPS: tuple[Op, ...] = (
    "list",
    "write",
    "validate_ok",
    "validate_bad",
    "dry_run",
    "refused",
    "propose",
    "propose_bad_path",
)


@dataclass(frozen=True)
class Scenario:
    """One scripted Turn: the model's tool calls, gate verdicts and a stop."""

    ops: tuple[Op, ...]
    check_accepts: tuple[bool, ...]
    dry_run_accepts: tuple[bool, ...]
    stop_at: tuple[StopKind, int] | None


@st.composite
def scenarios(draw: st.DrawFn) -> Scenario:
    """Draw up to eight tool calls, gate verdicts and an optional stop point."""
    ops = tuple(draw(st.lists(st.sampled_from(_OPS), min_size=0, max_size=8)))
    verdicts = st.lists(st.booleans(), min_size=0, max_size=4)
    stop_at = draw(
        st.none() | st.tuples(st.sampled_from(("check", "dry_run")), st.integers(0, 2))
    )
    return Scenario(
        ops=ops,
        check_accepts=tuple(draw(verdicts)),
        dry_run_accepts=tuple(draw(verdicts)),
        stop_at=stop_at,
    )


class _StopInfo:
    """Where a scripted stop fired: the Turn's ``seq`` and the gate kind."""

    def __init__(self) -> None:
        self.seq: int | None = None
        self.kind: StopKind | None = None
        self.accepted: bool | None = None


class RecordingGate(FakeGate):
    """A ``FakeGate`` that records verdicts and can stop the Turn on a call."""

    def __init__(self, scenario: Scenario) -> None:
        super().__init__()
        self._scenario = scenario
        self.live: LiveTurn | None = None
        self.stop = _StopInfo()
        self.check_verdicts: list[bool] = []

    def _result(self, accepted: bool, trust: Any) -> GateResult:
        return accepted_result(trust) if accepted else rejected_result("scripted")

    def _maybe_stop(self, kind: StopKind, index: int, accepted: bool) -> None:
        wanted = self._scenario.stop_at
        if wanted is None or wanted != (kind, index) or self.live is None:
            return
        self.stop.seq = self.live.seq
        self.stop.kind = kind
        self.stop.accepted = accepted
        cancel_turn(self.live.session_id, self.live.turn_id)

    async def check(self, manifest: dict[str, Any], *, requested_trust: Any) -> Any:
        """Return the next scripted verdict; stop the Turn when scripted."""
        index = len(self.check_calls)
        self.check_calls.append(_check_call(manifest, requested_trust))
        verdicts = self._scenario.check_accepts
        accepted = verdicts[index] if index < len(verdicts) else True
        self.check_verdicts.append(accepted)
        self._maybe_stop("check", index, accepted)
        return self._result(accepted, requested_trust)

    async def dry_run(self, manifest_path: Path, *, requested_trust: Any) -> Any:
        """Return the next scripted verdict; stop the Turn when scripted."""
        index = len(self.dry_run_calls)
        self.dry_run_calls.append(_dry_run_call(manifest_path, requested_trust))
        verdicts = self._scenario.dry_run_accepts
        accepted = verdicts[index] if index < len(verdicts) else True
        self._maybe_stop("dry_run", index, accepted)
        return self._result(accepted, requested_trust)


def _check_call(manifest: dict[str, Any], trust: Any) -> Any:
    from tests.fakes.builder_gate import CheckCall

    return CheckCall(manifest, trust)


def _dry_run_call(path: Path, trust: Any) -> Any:
    from tests.fakes.builder_gate import DryRunCall

    return DryRunCall(path, trust)


def _tool_call(op: Op) -> ScriptedToolCall:
    """Map one scripted op to the tool call the model makes."""
    validate = f"python {_SCRIPTS}/validate_manifest.py {_MANIFEST_PATH}"
    match op:
        case "list":
            return ScriptedToolCall("get_builder_models", {})
        case "write":
            return ScriptedToolCall(
                "write_file",
                {"file_path": _MANIFEST_PATH, "content": json.dumps(_MANIFEST)},
            )
        case "validate_ok" | "validate_bad":
            return ScriptedToolCall("run_skill_script", {"command": validate})
        case "dry_run":
            return ScriptedToolCall(
                "run_skill_script", {"command": f"{validate} --compiler out"}
            )
        case "refused":
            return ScriptedToolCall(
                "run_skill_script",
                {"command": f"python {_SCRIPTS}/validate_manifest.py ../../etc/passwd"},
            )
        case "propose":
            return ScriptedToolCall("propose_draft", {"path": _MANIFEST_PATH})
        case "propose_bad_path":
            return ScriptedToolCall("propose_draft", {"path": "/notes/a.txt"})


def _process_scripts(ops: tuple[Op, ...]) -> list[ProcessScript]:
    """One process script per op that starts a validator process, in order."""
    scripts: list[ProcessScript] = []
    for op in ops:
        if op == "validate_bad":
            scripts.append(ProcessScript.with_text(_INVALID_LINE, exit_code=1))
        elif op in ("validate_ok", "dry_run"):
            scripts.append(ProcessScript.with_text(_VALID_LINE, exit_code=0))
    return scripts


def _model(scenario: Scenario) -> FakeChatModel:
    """A model that makes one scripted tool call per call, then answers."""
    scripted = [ModelTurn(tool_calls=(_tool_call(op),)) for op in scenario.ops]
    scripted.append(ModelTurn(text=("done",)))
    return FakeChatModel(turns=tuple(scripted))


@contextmanager
def _scope(store: Any) -> Iterator[Any]:
    yield store


@dataclass(frozen=True)
class Outcome:
    """What a scripted Turn produced."""

    events: list[BuilderEvent]
    gate: RecordingGate
    factory: FakeProcessFactory
    live: LiveTurn


async def _play(scenario: Scenario, root: Path) -> Outcome:
    """Run the scenario through ``run_turn`` and return what was published."""
    from tests.fakes.builder_store import InMemoryBuilderStore

    turns._LIVE_TURNS.clear()
    turns._TURN_TASKS.clear()
    store = InMemoryBuilderStore()
    bus = SessionEventBus(queue_maxsize=10_000)
    set_event_bus(bus)
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
    gate = RecordingGate(scenario)
    gate.live = live
    factory = FakeProcessFactory(*_process_scripts(scenario.ops))
    queue, _ = bus.subscribe(live.session_id, lambda: _empty_snapshot(live))
    deps = TurnDeps(
        bus=bus,
        store_scope=lambda: _scope(store),
        sandbox_factory=lambda user, sid: BuilderSandbox(user, sid, root=root),
        gate=gate,
        chat_model=_model(scenario),
        skills_root=_SKILLS_ROOT,
    )
    request = TurnRequest(content="make a workflow", canvas_state={"steps": []})
    spawning = partial(ScriptContext, spawn=factory, semaphore=asyncio.Semaphore(2))
    register_live_turn(live)
    with patch("app.agents.workflow_builder.agent.ScriptContext", spawning):
        task = asyncio.ensure_future(run_turn(live, request, deps))
        attach_task(live, task)
        await task
    events: list[BuilderEvent] = []
    while not queue.empty():
        item = queue.get_nowait()
        if item is not None:
            events.append(item)
    set_event_bus(None)
    return Outcome(events, gate, factory, live)


def _empty_snapshot(live: LiveTurn) -> Any:
    from app.api.workflow_builder.turns import build_snapshot
    from tests.fakes.builder_store import InMemoryBuilderStore

    return build_snapshot(
        live.session_id, user_id=live.user_id, store=InMemoryBuilderStore()
    )


def _turn_events(events: list[BuilderEvent]) -> list[BuilderEvent]:
    """Events that carry the Turn's ``seq``."""
    return [
        e
        for e in events
        if isinstance(e, TurnScoped)
        or (isinstance(e, ErrorEvent) and e.turn_id is not None)
    ]


def _check_well_formed(scenario: Scenario, out: Outcome) -> None:
    events = _turn_events(out.events)
    # seq starts at 1 and rises by one.
    seqs = [e.seq for e in events]  # type: ignore[union-attr]
    assert seqs == list(range(1, len(events) + 1))

    # turn_completed is the one and only last event.
    completed = [e for e in events if isinstance(e, TurnCompleted)]
    assert len(completed) == 1
    assert events[-1] is completed[0]

    # Every tool_started has exactly one tool_finished, after it.
    started = [e for e in events if isinstance(e, ToolStarted)]
    finished = [e for e in events if isinstance(e, ToolFinished)]
    assert len({e.call_id for e in started}) == len(started)
    assert sorted(e.call_id for e in finished) == sorted(e.call_id for e in started)
    start_seq = {e.call_id: e.seq for e in started}
    assert all(start_seq[e.call_id] < e.seq for e in finished)

    # One check_result per validator run, dry run and gate check.
    checks = [e for e in events if isinstance(e, CheckResultEvent)]
    by_source = {
        source: [c for c in checks if c.source == source]
        for source in ("skill_validator", "platform_dry_run", "server_gate")
    }
    validator_runs = [
        s
        for s in out.factory.starts
        if any("validate_manifest.py" in a for a in s.argv)
    ]
    assert len(by_source["skill_validator"]) == len(validator_runs)
    assert len(by_source["platform_dry_run"]) == len(out.gate.dry_run_calls)
    # A check that accepted a draft the Turn was already stopping applies
    # nothing and reports nothing (Req 30.4).
    unreported = 1 if out.gate.stop.kind == "check" and out.gate.stop.accepted else 0
    assert len(by_source["server_gate"]) == len(out.gate.check_calls) - unreported

    # At most one draft_applied, only after an accepted check, never after a stop.
    applied = [e for e in events if isinstance(e, DraftApplied)]
    assert len(applied) <= 1
    for draft in applied:
        earlier = [c for c in by_source["server_gate"] if c.seq < draft.seq]
        assert earlier
        assert earlier[-1].verdict == "valid"
        if out.gate.stop.seq is not None:
            assert draft.seq <= out.gate.stop.seq
    if out.gate.stop.kind == "check" and out.gate.stop.accepted:
        assert not applied

    # Dry runs never count as rejections; only rejected gate checks do.
    invalid = [c for c in by_source["server_gate"] if c.verdict == "invalid"]
    assert out.live.gate_rejections == len(invalid)

    # The second rejection ends the Turn: nothing starts after it.
    if len(invalid) >= 2:
        second = invalid[1]
        assert not [e for e in started if e.seq > second.seq]
        if out.gate.stop.seq is None:
            assert completed[0].stop_reason == "gate_rejections"
    assert len(invalid) <= 2


@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(scenario=scenarios())
def test_turn_events_are_well_formed_for_any_scripted_turn(
    scenario: Scenario,
) -> None:
    """Property 14: the event stream of any scripted Turn is well formed."""
    with tempfile.TemporaryDirectory() as folder:
        out = asyncio.run(_play(scenario, Path(folder) / "builder"))
    _check_well_formed(scenario, out)
