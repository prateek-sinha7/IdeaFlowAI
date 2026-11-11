"""Property tests for the builder fan-out and the connect-time snapshot.

# Feature: ai-workflow-builder, Property 24: Every client sees the same turn

For any Turn event stream and any set of connect times, every client sees the
same Turn. A client that connects after ``k`` events gets a ``Snapshot`` whose
``through_seq`` is ``k`` and which already holds the stage, the tool activity and
the checks of those ``k`` events. The events it then receives are exactly
``seq`` ``k + 1`` to the end, in order, with no gap and no overlap. Applying them
to the snapshot gives the same final state as a client that was connected from
the start, and the same state as the one a reader derives from the scripted
events alone. A client that applies the ``seq`` dedupe rule (drop an event of the
same Turn whose ``seq`` is not above the last one applied) reaches that state even
when the stream replays events the snapshot already holds.

**Validates: Requirements 13.3, 17.9, 17.10, 40.4, 40.5, 40.6**

The system under test is ``TurnRunner`` (``seq`` stamping and live tracking),
``build_snapshot`` and ``SessionEventBus.subscribe``. The store is
``InMemoryBuilderStore``; nothing touches a database, the network or a model.

The oracle does not read ``LiveTurn``. It is computed from the scripted event
specs: the expected snapshot after ``k`` specs and the expected final state are
folded straight from ``specs[:k]``, and a spec at index ``i`` must come out as
the event with ``seq == i + 1``.

The tests are synchronous and drive the event loop with ``asyncio.run``, because
Hypothesis does not await coroutine tests. ``TurnRunner.publish`` never suspends,
so every step runs in one synchronous block, as it does in production.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, get_args

from hypothesis import given, settings
from hypothesis import strategies as st

from app.agents.workflow_builder.events import (
    BuilderEvent,
    CheckResultEvent,
    CheckSource,
    CheckVerdict,
    Snapshot,
    StageChanged,
    Text,
    Thinking,
    ToolFinished,
    ToolFinishStatus,
    ToolKind,
    ToolStarted,
    TurnScoped,
)
from app.agents.workflow_builder.ports import TurnLimits
from app.agents.workflow_builder.stages import Stage
from app.api.workflow_builder.bus import SessionEventBus, SessionQueue
from app.api.workflow_builder.turns import (
    LiveTurn,
    TurnRunner,
    build_snapshot,
    register_live_turn,
    release_live_turn,
)
from tests.factories.builder_session_factory import BuilderSessionFactory
from tests.fakes.builder_store import InMemoryBuilderStore

USER = "user-a"
LIMITS = TurnLimits(
    timeout_seconds=900,
    max_tool_calls=60,
    max_gate_rejections=2,
    warning_fraction=0.8,
)

_TOOL_KINDS: tuple[str, ...] = get_args(ToolKind)
_FINISH_STATUSES: tuple[str, ...] = get_args(ToolFinishStatus)
_CHECK_SOURCES: tuple[str, ...] = get_args(CheckSource)
_CHECK_VERDICTS: tuple[str, ...] = get_args(CheckVerdict)

# --- Scripted events: the independent description of what is published -----------

# ("stage", Stage) | ("start", call_id, kind) | ("finish", call_id, status)
# | ("check", source, verdict, errors) | ("text", s) | ("thinking", s)
Spec = tuple[Any, ...]

# Raw operation drawn by Hypothesis. A ``finish`` names a running call by index;
# ``_resolve`` turns it into a concrete spec or, with nothing running, into text.
_OPS = st.one_of(
    st.tuples(st.just("stage"), st.sampled_from(list(Stage))),
    st.tuples(st.just("start"), st.sampled_from(_TOOL_KINDS)),
    st.tuples(
        st.just("finish"),
        st.integers(min_value=0, max_value=9),
        st.sampled_from(_FINISH_STATUSES),
    ),
    st.tuples(
        st.just("check"),
        st.sampled_from(_CHECK_SOURCES),
        st.sampled_from(_CHECK_VERDICTS),
        st.integers(min_value=0, max_value=5),
    ),
    st.tuples(st.just("text"), st.text(max_size=8)),
    st.tuples(st.just("thinking"), st.text(max_size=8)),
)
_SCRIPTS = st.lists(_OPS, max_size=25)


def _resolve(ops: list[tuple[Any, ...]]) -> list[Spec]:
    """Turn raw operations into specs where every finish names a running call."""
    specs: list[Spec] = []
    running: list[str] = []
    started = 0
    for op in ops:
        match op:
            case ("start", kind):
                started += 1
                call_id = f"call-{started}"
                running.append(call_id)
                specs.append(("start", call_id, kind))
            case ("finish", index, status):
                if running:
                    specs.append(("finish", running.pop(index % len(running)), status))
                else:
                    specs.append(("text", ""))
            case _:
                specs.append(op)
    return specs


def _now() -> datetime:
    return datetime.now(UTC)


def _event_for(spec: Spec) -> BuilderEvent:
    """Build the event of ``spec`` with placeholder ``turn_id`` and ``seq``."""
    base: dict[str, Any] = {"ts": _now(), "turn_id": "placeholder", "seq": 1}
    match spec:
        case ("stage", stage):
            return StageChanged(**base, stage=stage, label=f"label {stage.value}")
        case ("start", call_id, kind):
            return ToolStarted(
                **base,
                call_id=call_id,
                tool="tool",
                kind=kind,
                label="doing it",
                command=None,
            )
        case ("finish", call_id, status):
            return ToolFinished(
                **base, call_id=call_id, status=status, duration_ms=1, summary="done"
            )
        case ("check", source, verdict, errors):
            return CheckResultEvent(
                **base,
                source=source,
                verdict=verdict,
                errors=errors,
                warnings=0,
                attempt=None,
                attempts_left=None,
            )
        case ("text", text):
            return Text(**base, text=text)
        case ("thinking", text):
            return Thinking(**base, text=text)
    raise AssertionError(f"unknown spec {spec!r}")


# --- Reader-side state: what a client shows -------------------------------------


@dataclass
class _View:
    """What a client shows of a running Turn."""

    stage: str = Stage.STARTING.value
    activity: dict[str, str] = field(default_factory=dict)
    checks: list[tuple[str, str, int]] = field(default_factory=list)

    def key(self) -> tuple[str, list[tuple[str, str]], list[tuple[str, str, int]]]:
        return self.stage, list(self.activity.items()), list(self.checks)


def _fold(specs: list[Spec]) -> _View:
    """The oracle: the view that ``specs`` produce, computed without the server."""
    view = _View()
    for spec in specs:
        match spec:
            case ("stage", stage):
                view.stage = stage.value
            case ("start", call_id, _kind):
                view.activity[call_id] = "running"
            case ("finish", call_id, status):
                view.activity[call_id] = status
            case ("check", source, verdict, errors):
                view.checks.append((source, verdict, errors))
    return view


def _view_of_snapshot(snapshot: Snapshot) -> _View:
    running = snapshot.running_turn
    assert running is not None
    return _View(
        stage=running.stage.value,
        activity={entry.call_id: entry.status for entry in running.activity},
        checks=[(c.source, c.verdict, c.errors) for c in running.checks],
    )


def _apply(view: _View, event: BuilderEvent) -> None:
    """Apply one live event to a view (the client reducer, reduced to this state)."""
    match event:
        case StageChanged():
            view.stage = event.stage.value
        case ToolStarted():
            view.activity.setdefault(event.call_id, "running")
        case ToolFinished():
            view.activity[event.call_id] = event.status
        case CheckResultEvent():
            view.checks.append((event.source, event.verdict, event.errors))
        case _:
            pass


@dataclass
class _Client:
    """A connected client: its snapshot and everything its queue received."""

    connected_after: int
    snapshot: Snapshot
    queue: SessionQueue
    received: list[BuilderEvent] = field(default_factory=list)


def _drain(queue: SessionQueue) -> list[BuilderEvent]:
    events: list[BuilderEvent] = []
    while not queue.empty():
        item = queue.get_nowait()
        if item is not None:
            events.append(item)
    return events


def _matches(spec: Spec, event: BuilderEvent) -> bool:
    """True when ``event`` is the event ``spec`` describes."""
    match spec, event:
        case ("stage", stage), StageChanged():
            return event.stage == stage
        case ("start", call_id, kind), ToolStarted():
            return event.call_id == call_id and event.kind == kind
        case ("finish", call_id, status), ToolFinished():
            return event.call_id == call_id and event.status == status
        case ("check", source, verdict, errors), CheckResultEvent():
            return (event.source, event.verdict, event.errors) == (
                source,
                verdict,
                errors,
            )
        case ("text", text), Text():
            return event.text == text
        case ("thinking", text), Thinking():
            return event.text == text
    return False


# --- Harness --------------------------------------------------------------------


def _scope(store: InMemoryBuilderStore) -> Any:
    @contextmanager
    def scope() -> Iterator[InMemoryBuilderStore]:
        yield store

    return scope


def _live_turn(store: InMemoryBuilderStore) -> LiveTurn:
    """Create a session with a running turn row; return the matching LiveTurn."""
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


@dataclass
class _Played:
    """The outcome of playing a script against a set of connecting clients."""

    turn_id: str
    clients: list[_Client]
    latest_message_ids: set[str | None]


def _play(specs: list[Spec], connect_points: list[int], *, with_noise: bool) -> _Played:
    """Publish ``specs`` through a ``TurnRunner`` and connect clients between them.

    A client with connect point ``k`` subscribes after ``k`` specs were published.
    With ``with_noise`` a second Session publishes an event after every step.
    """

    async def main() -> _Played:
        store = InMemoryBuilderStore()
        bus = SessionEventBus(queue_maxsize=0)
        live = _live_turn(store)
        noise_live = _live_turn(store)
        register_live_turn(live)
        register_live_turn(noise_live)
        try:
            runner = TurnRunner(
                live,
                canvas_state=None,
                limits=LIMITS,
                bus=bus,
                store_scope=_scope(store),
            )
            noise = TurnRunner(
                noise_live,
                canvas_state=None,
                limits=LIMITS,
                bus=bus,
                store_scope=_scope(store),
            )
            noise_client = bus.subscribe(
                noise_live.session_id,
                lambda: build_snapshot(
                    noise_live.session_id, user_id=USER, store=store
                ),
            )[0]
            clients: list[_Client] = []
            for step in range(len(specs) + 1):
                for point in connect_points:
                    if point == step:
                        queue, snapshot = bus.subscribe(
                            live.session_id,
                            lambda: build_snapshot(
                                live.session_id, user_id=USER, store=store
                            ),
                        )
                        clients.append(_Client(point, snapshot, queue))
                if step < len(specs):
                    await runner.publish(_event_for(specs[step]))
                    if with_noise:
                        await noise.publish(_event_for(("text", "noise")))
            for client in clients:
                client.received = _drain(client.queue)
            # The other Session's clients saw only their own Session's events.
            assert all(e.turn_id == noise_live.turn_id for e in _drain(noise_client))  # type: ignore[union-attr]
            return _Played(
                turn_id=live.turn_id,
                clients=clients,
                latest_message_ids={c.snapshot.latest_message_id for c in clients},
            )
        finally:
            release_live_turn(live)
            release_live_turn(noise_live)

    return asyncio.run(main())


_CONNECT_POINTS = st.lists(st.integers(min_value=0, max_value=25), max_size=6)


def _clamp(points: list[int], count: int) -> list[int]:
    """Connect points are steps 0..count; the first client always connects at 0."""
    return [0, *(min(p, count) for p in points)]


# --- Property 24 ----------------------------------------------------------------


@settings(max_examples=100, deadline=None)
@given(ops=_SCRIPTS, points=_CONNECT_POINTS, with_noise=st.booleans())
def test_fanout_gives_every_client_the_same_turn_when_connect_times_interleave(
    ops: list[tuple[Any, ...]], points: list[int], with_noise: bool
) -> None:
    specs = _resolve(ops)
    count = len(specs)
    played = _play(specs, _clamp(points, count), with_noise=with_noise)

    reference = played.clients[0]
    assert reference.connected_after == 0
    # The reference client saw every scripted event once, in order, with seq 1..n.
    assert [e.seq for e in reference.received if isinstance(e, TurnScoped)] == list(
        range(1, count + 1)
    )
    assert len(reference.received) == count
    assert all(_matches(s, e) for s, e in zip(specs, reference.received, strict=True))
    assert all(
        isinstance(e, TurnScoped) and e.turn_id == played.turn_id
        for e in reference.received
    )
    assert len(played.latest_message_ids) == 1

    expected_final = _fold(specs).key()
    for client in played.clients:
        k = client.connected_after
        running = client.snapshot.running_turn
        # The snapshot reflects exactly the first k events.
        assert client.snapshot.state == "running"
        assert running is not None
        assert running.turn_id == played.turn_id
        assert running.through_seq == k
        view = _view_of_snapshot(client.snapshot)
        assert view.key() == _fold(specs[:k]).key()
        # The live events continue at k + 1: no gap and no overlap.
        seqs = [e.seq for e in client.received if isinstance(e, TurnScoped)]
        assert seqs == list(range(k + 1, count + 1))
        # They are the same events every other client received.
        assert client.received == reference.received[k:]
        for event in client.received:
            _apply(view, event)
        assert view.key() == expected_final


# --- The client dedupe rule -----------------------------------------------------


def _apply_with_dedupe(
    snapshot: Snapshot, stream: list[BuilderEvent]
) -> tuple[_View, list[int]]:
    """Client reducer: seed from the snapshot, then apply the dedupe rule (3.3.4)."""
    running = snapshot.running_turn
    assert running is not None
    view = _view_of_snapshot(snapshot)
    turn_id, last_seq = running.turn_id, running.through_seq
    applied: list[int] = []
    for event in stream:
        if not isinstance(event, TurnScoped):
            _apply(view, event)
            continue
        if event.turn_id == turn_id and event.seq <= last_seq:
            continue
        _apply(view, event)
        applied.append(event.seq)
        turn_id, last_seq = event.turn_id, event.seq
    return view, applied


@settings(max_examples=100, deadline=None)
@given(
    ops=_SCRIPTS,
    connect=st.integers(min_value=0, max_value=25),
    replay_from=st.integers(min_value=0, max_value=25),
    doubled=st.booleans(),
)
def test_dedupe_rule_reaches_final_state_when_stream_replays_events_the_snapshot_holds(
    ops: list[tuple[Any, ...]], connect: int, replay_from: int, doubled: bool
) -> None:
    specs = _resolve(ops)
    count = len(specs)
    k = min(connect, count)
    played = _play(specs, [0, k], with_noise=False)
    full_log = played.clients[0].received
    late = played.clients[1]

    # A stream that starts before the snapshot's ``through_seq`` and may repeat
    # every event. Per the design this cannot happen, but the rule must cope.
    stream = full_log[min(replay_from, k) :]
    if doubled:
        stream = [e for event in stream for e in (event, event)]
    view, applied = _apply_with_dedupe(late.snapshot, stream)

    assert applied == list(range(k + 1, count + 1))
    assert view.key() == _fold(specs).key()
