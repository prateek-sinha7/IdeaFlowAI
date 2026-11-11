"""Unit tests for the live turn, its registries, the port adapter and the snapshot.

Covers task 15.2: ``LiveTurn`` (one stop reason, first stop wins, task cancel),
``TurnRunner`` (per-turn ``seq`` before publish, stage changes through
``derive_stage``, tool rows and accepted drafts through the store, gate rejection
counting) and ``build_snapshot``. The store is ``InMemoryBuilderStore``; the bus
is a real ``SessionEventBus``. No database, network or model is used.
"""

from __future__ import annotations

import asyncio
import json
import re
import string
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.agents.workflow_builder.skill_package import SKILLS_ROOT
from app.agents.workflow_builder.adherence import ToolCall
from app.agents.workflow_builder.canonical import canonical_hash
from app.agents.workflow_builder.events import (
    BuilderEvent,
    ChangeSummary,
    CheckResult,
    ErrorEvent,
    LaunchNeed,
    LimitWarning,
    SessionDeleted,
    StageChanged,
    StopReason,
    Text,
    ToolActivity,
    ToolFinished,
    ToolStarted,
    TurnCompleted,
    TurnScoped,
    TurnStarted,
    UsageCounts,
)
from app.agents.workflow_builder.ports import (
    AcceptedDraft,
    FinishedToolCall,
    TurnLimits,
)
from app.agents.workflow_builder.stages import Stage, TextDelta, TurnAccepted
from app.agents.workflow_builder.sandbox import CANVAS_FILE, BuilderSandbox
from app.api.workflow_builder import turns
from app.api.workflow_builder.bus import SessionEventBus
from app.api.workflow_builder.turns import (
    LiveTurn,
    TurnDeps,
    TurnRequest,
    TurnRunner,
    TurnRunState,
    attach_task,
    build_snapshot,
    cancel_turn,
    finalize_turn,
    get_event_bus,
    get_live_turn,
    register_live_turn,
    release_live_turn,
    run_turn,
    set_event_bus,
    stop_all,
    stop_session_turn,
    stop_user_turns,
    status_for_stop,
    truncate_result,
)
from app.core.config import settings
from app.models.workflow_builder import (
    DRAFT_KIND_ACCEPTED,
    DRAFT_KIND_UNPROPOSED,
    MESSAGE_ROLE_TOOL,
    MESSAGE_STATUS_RUNNING,
    MESSAGE_STATUS_TOOL_OK,
)
from tests.factories.builder_session_factory import BuilderSessionFactory
from tests.fakes.builder_gate import FakeGate
from tests.fakes.builder_store import InMemoryBuilderStore
from tests.fakes.scripted_chat_model import (
    FakeChatModel,
    ModelTurn,
    ScriptedToolCall,
    ScriptedUsage,
)

USER = "user-a"
OTHER = "user-b"
LIMITS = TurnLimits(
    timeout_seconds=900,
    max_tool_calls=60,
    max_gate_rejections=2,
    warning_fraction=0.8,
)
MANIFEST: dict[str, Any] = {"id": "wf", "steps": []}
SUMMARY = ChangeSummary(
    added=["a"],
    removed=[],
    reordered=False,
    gates_changed=[],
    validators_changed=[],
    models_changed=[],
    prompts_changed=0,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _scope(store: InMemoryBuilderStore) -> Any:
    @contextmanager
    def scope() -> Iterator[InMemoryBuilderStore]:
        yield store

    return scope


@pytest.fixture(autouse=True)
def _clean_registries() -> Iterator[None]:
    turns._LIVE_TURNS.clear()
    turns._TURN_TASKS.clear()
    yield
    turns._LIVE_TURNS.clear()
    turns._TURN_TASKS.clear()
    set_event_bus(None)


@pytest.fixture
def store() -> InMemoryBuilderStore:
    return InMemoryBuilderStore()


@pytest.fixture
def bus() -> SessionEventBus:
    return SessionEventBus(queue_maxsize=100)


def _begin(store: InMemoryBuilderStore) -> LiveTurn:
    """Create a session and a running turn row; return the matching LiveTurn."""
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


def _runner(
    live: LiveTurn, store: InMemoryBuilderStore, bus: SessionEventBus
) -> TurnRunner:
    return TurnRunner(
        live,
        canvas_state={"id": "canvas"},
        limits=LIMITS,
        bus=bus,
        store_scope=_scope(store),
    )


def _text(value: str = "hi") -> Text:
    return Text(ts=_now(), turn_id="placeholder", seq=1, text=value)


def _drain(queue: asyncio.Queue[BuilderEvent | None]) -> list[BuilderEvent]:
    events: list[BuilderEvent] = []
    while not queue.empty():
        item = queue.get_nowait()
        if item is not None:
            events.append(item)
    return events


def _snapshot_fn(live_store: InMemoryBuilderStore, session_id: str, user: str = USER):
    return lambda: build_snapshot(session_id, user_id=user, store=live_store)


# --- truncate_result --------------------------------------------------------------


def test_truncate_result_returns_text_unchanged_when_within_four_thousand_chars() -> (
    None
):
    text = "x" * 4000

    assert truncate_result(text) == text


def test_truncate_result_keeps_head_and_tail_when_longer_than_four_thousand_chars() -> (
    None
):
    text = "H" * 3000 + "m" * 500 + "T" * 1000

    result = truncate_result(text)

    assert result.startswith("H" * 3000)
    assert result.endswith("T" * 900)
    assert "m" not in result
    assert len(result) <= 4000


@pytest.mark.parametrize("length", [4001, 4030, 4031, 5000, 100_000, 1_000_000])
def test_truncate_result_stays_within_four_thousand_chars_when_note_is_added(
    length: int,
) -> None:
    text = (string.ascii_lowercase * (length // 26 + 1))[:length]

    result = truncate_result(text)

    note = re.search(r"\n\[\.\.\. (\d+) characters cut \.\.\.\]\n", result)
    assert note is not None
    tail = result[note.end() :]
    assert len(result) <= 4000
    assert result[:3000] == text[:3000]
    assert tail == text[length - len(tail) :]
    assert int(note.group(1)) == length - 3000 - len(tail)
    assert len(tail) >= 900


# --- LiveTurn ---------------------------------------------------------------------


def test_stop_keeps_first_reason_when_called_twice() -> None:
    live = LiveTurn("s", "t", "u", USER, "m", None)

    live.stop("time")
    live.stop("cancelled")

    assert live.stop_reason == "time"
    assert live.stopping is True


async def test_stop_cancels_task_once_when_first_reason_set() -> None:
    live = LiveTurn("s", "t", "u", USER, "m", None)
    task = asyncio.ensure_future(asyncio.sleep(60))
    attach_task(live, task)

    live.stop("cancelled")

    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.cancelled()


async def test_attach_task_cancels_task_when_turn_already_stopping() -> None:
    live = LiveTurn("s", "t", "u", USER, "m", None)
    live.stop("shutdown")
    task = asyncio.ensure_future(asyncio.sleep(60))

    attach_task(live, task)

    with pytest.raises(asyncio.CancelledError):
        await task


async def test_release_live_turn_removes_both_registry_entries_when_turn_ends() -> None:
    live = LiveTurn("s", "t", "u", USER, "m", None)
    register_live_turn(live)
    task = asyncio.ensure_future(asyncio.sleep(0))
    attach_task(live, task)
    assert get_live_turn("s") is live
    assert task in turns._TURN_TASKS

    release_live_turn(live)

    assert get_live_turn("s") is None
    assert task not in turns._TURN_TASKS
    await task


def test_release_live_turn_keeps_newer_turn_when_ids_differ() -> None:
    old = LiveTurn("s", "t1", "u", USER, "m", None)
    new = LiveTurn("s", "t2", "u", USER, "m", None)
    register_live_turn(new)

    release_live_turn(old)

    assert get_live_turn("s") is new


def test_set_stage_accumulates_seconds_when_stage_changes() -> None:
    live = LiveTurn("s", "t", "u", USER, "m", None)

    live.set_stage(Stage.STARTING)
    live.set_stage(Stage.THINKING)

    assert Stage.STARTING in live.stage_seconds
    assert set(live.stage_durations()) == {Stage.STARTING, Stage.THINKING}


# --- Shared bus -------------------------------------------------------------------


def test_get_event_bus_returns_same_instance_when_called_twice() -> None:
    assert get_event_bus() is get_event_bus()


def test_set_event_bus_replaces_instance_when_given_a_bus(bus: SessionEventBus) -> None:
    set_event_bus(bus)

    assert get_event_bus() is bus


# --- publish and seq --------------------------------------------------------------


async def test_publish_assigns_increasing_seq_and_turn_id_when_turn_events_sent(
    store: InMemoryBuilderStore, bus: SessionEventBus
) -> None:
    live = _begin(store)
    runner = _runner(live, store, bus)
    queue, _ = bus.subscribe(live.session_id, lambda: build_snapshot_stub(live))

    await runner.publish(_text("one"))
    await runner.publish(_text("two"))
    await runner.publish(_text("three"))

    events = _drain(queue)
    assert [e.seq for e in events if isinstance(e, TurnScoped)] == [1, 2, 3]
    assert {e.turn_id for e in events if isinstance(e, TurnScoped)} == {live.turn_id}
    assert live.seq == 3


async def test_publish_leaves_event_unchanged_when_not_turn_scoped(
    store: InMemoryBuilderStore, bus: SessionEventBus
) -> None:
    live = _begin(store)
    runner = _runner(live, store, bus)
    queue, _ = bus.subscribe(live.session_id, lambda: build_snapshot_stub(live))
    event = SessionDeleted(ts=_now())

    await runner.publish(event)

    assert _drain(queue) == [event]
    assert live.seq == 0


async def test_publish_gives_every_subscriber_same_order_when_events_interleave(
    store: InMemoryBuilderStore, bus: SessionEventBus
) -> None:
    live = _begin(store)
    runner = _runner(live, store, bus)
    first, _ = bus.subscribe(live.session_id, lambda: build_snapshot_stub(live))
    await runner.publish(_text("a"))
    second, _ = bus.subscribe(live.session_id, lambda: build_snapshot_stub(live))
    await runner.publish(_text("b"))

    seen_first = [e.seq for e in _drain(first) if isinstance(e, TurnScoped)]
    seen_second = [e.seq for e in _drain(second) if isinstance(e, TurnScoped)]

    assert seen_first == [1, 2]
    assert seen_second == [2]


def build_snapshot_stub(live: LiveTurn) -> Any:
    """A snapshot for bus.subscribe that does not read a store."""
    return build_snapshot(
        live.session_id, user_id=live.user_id, store=InMemoryBuilderStore()
    )


# --- signal_stage -----------------------------------------------------------------


async def test_signal_stage_publishes_stage_event_when_stage_changes(
    store: InMemoryBuilderStore, bus: SessionEventBus
) -> None:
    live = _begin(store)
    runner = _runner(live, store, bus)
    queue, _ = bus.subscribe(live.session_id, lambda: build_snapshot_stub(live))

    await runner.signal_stage(TurnAccepted())
    await runner.signal_stage(TextDelta())

    events = _drain(queue)
    assert [(e.stage, e.seq) for e in events if isinstance(e, StageChanged)] == [
        (Stage.STARTING, 1),
        (Stage.RESPONDING, 2),
    ]
    assert live.stage == Stage.RESPONDING


async def test_signal_stage_publishes_nothing_when_stage_is_unchanged(
    store: InMemoryBuilderStore, bus: SessionEventBus
) -> None:
    live = _begin(store)
    runner = _runner(live, store, bus)
    queue, _ = bus.subscribe(live.session_id, lambda: build_snapshot_stub(live))
    await runner.signal_stage(TurnAccepted())
    _drain(queue)

    await runner.signal_stage(TurnAccepted())
    await runner.signal_stage(TextDelta(tool_running=True))

    assert _drain(queue) == []


# --- counters ---------------------------------------------------------------------


def test_count_tool_call_returns_running_total_when_called_repeatedly(
    store: InMemoryBuilderStore, bus: SessionEventBus
) -> None:
    runner = _runner(_begin(store), store, bus)

    assert [runner.count_tool_call() for _ in range(3)] == [1, 2, 3]


def test_report_gate_rejection_returns_running_total_when_called_repeatedly(
    store: InMemoryBuilderStore, bus: SessionEventBus
) -> None:
    live = _begin(store)
    runner = _runner(live, store, bus)

    assert runner.report_gate_rejection() == 1
    assert runner.report_gate_rejection() == 2
    assert live.gate_rejections == 2


def test_stop_marks_runner_stopping_when_reason_given(
    store: InMemoryBuilderStore, bus: SessionEventBus
) -> None:
    runner = _runner(_begin(store), store, bus)

    runner.stop("gate_rejections")
    runner.stop("cancelled")

    assert runner.stopping is True
    assert runner.live.stop_reason == "gate_rejections"


def test_record_workflow_write_remembers_path_when_write_succeeds(
    store: InMemoryBuilderStore, bus: SessionEventBus
) -> None:
    live = _begin(store)
    runner = _runner(live, store, bus)

    runner.record_workflow_write("/workflows/a.workflow.json")

    assert list(live.changed_workflow_files) == ["/workflows/a.workflow.json"]


# --- record_tool_call -------------------------------------------------------------


def _finished(result: str = "ok") -> FinishedToolCall:
    return FinishedToolCall(
        activity=ToolActivity(
            call_id="c1",
            tool="run_skill_script",
            kind="script",
            label="Checked the workflow",
            status="ok",
            duration_ms=120,
            command="python validate_manifest.py m.json",
            exit_code=0,
            summary="Checked the workflow. Exit code 0.",
        ),
        call=ToolCall(name="run_skill_script", ok=True),
        result=result,
    )


async def test_record_tool_call_stores_truncated_row_when_result_is_long(
    store: InMemoryBuilderStore, bus: SessionEventBus
) -> None:
    live = _begin(store)
    runner = _runner(live, store, bus)
    long_result = "H" * 3000 + "m" * 2000 + "T" * 1000

    await runner.record_tool_call(_finished(long_result))

    rows = store.list_tool_rows(USER, live.turn_id)
    assert len(rows) == 1
    row = rows[0]
    assert row.role == MESSAGE_ROLE_TOOL
    assert row.status == MESSAGE_STATUS_TOOL_OK
    assert row.content == truncate_result(long_result)
    assert row.tool["call_id"] == "c1"
    assert row.tool["exit_code"] == 0
    assert row.tool["command"] == "python validate_manifest.py m.json"
    assert len(live.finished_calls) == 1


async def test_record_tool_call_stores_unknown_status_as_error_when_activity_running(
    store: InMemoryBuilderStore, bus: SessionEventBus
) -> None:
    live = _begin(store)
    runner = _runner(live, store, bus)
    running = _finished()
    running = FinishedToolCall(
        activity=running.activity.model_copy(update={"status": "running"}),
        call=running.call,
        result="",
    )

    await runner.record_tool_call(running)

    assert store.list_tool_rows(USER, live.turn_id)[0].status == "error"


async def test_publish_tracks_activity_when_tool_events_arrive_then_finish_replaces_it(
    store: InMemoryBuilderStore, bus: SessionEventBus
) -> None:
    live = _begin(store)
    runner = _runner(live, store, bus)
    await runner.publish(
        ToolStarted(
            ts=_now(),
            turn_id="x",
            seq=1,
            call_id="c1",
            tool="run_skill_script",
            kind="script",
            label="Checked the workflow",
            command="python validate_manifest.py m.json",
        )
    )
    assert [a.status for a in live.activity] == ["running"]

    await runner.publish(
        ToolFinished(
            ts=_now(),
            turn_id="x",
            seq=1,
            call_id="c1",
            status="ok",
            duration_ms=5,
            summary="done",
        )
    )
    assert [a.status for a in live.activity] == ["ok"]

    await runner.record_tool_call(_finished())
    assert [a.exit_code for a in live.activity] == [0]
    assert len(live.activity) == 1


# --- accept_draft -----------------------------------------------------------------


def _draft() -> AcceptedDraft:
    return AcceptedDraft(
        manifest=MANIFEST,
        trust="user",
        source_file="/workflows/wf.workflow.json",
        change_summary=SUMMARY,
        launch_needs=(LaunchNeed(kind="uploads"),),
    )


async def test_accept_draft_stores_accepted_revision_when_draft_given(
    store: InMemoryBuilderStore, bus: SessionEventBus
) -> None:
    live = _begin(store)
    runner = _runner(live, store, bus)

    revision = await runner.accept_draft(_draft())

    assert revision == 1
    assert runner.accepted_revision == 1
    row = store.get_latest_revision(USER, live.session_id, DRAFT_KIND_ACCEPTED)
    assert row is not None
    assert row.manifest_hash == canonical_hash(MANIFEST)
    assert row.source_turn_id == live.turn_id
    assert row.source_file == "/workflows/wf.workflow.json"
    assert row.target_trust == "user"
    assert row.change_summary["added"] == ["a"]
    assert row.launch_needs == [{"kind": "uploads", "detail": None}]


class _BlockingStore(InMemoryBuilderStore):
    """A store whose ``insert_revision`` waits until the test lets it go."""

    def __init__(self) -> None:
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()

    def insert_revision(self, *args: Any, **kwargs: Any) -> Any:
        self.entered.set()
        self.release.wait(timeout=5)
        return super().insert_revision(*args, **kwargs)


async def test_accept_draft_records_revision_when_cancelled_during_write(
    bus: SessionEventBus,
) -> None:
    blocking = _BlockingStore()
    live = _begin(blocking)
    runner = _runner(live, blocking, bus)
    task = asyncio.ensure_future(runner.accept_draft(_draft()))
    await asyncio.to_thread(blocking.entered.wait, 5)

    task.cancel()
    blocking.release.set()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert runner.accepted_revision == 1
    assert (
        blocking.get_latest_revision(USER, live.session_id, DRAFT_KIND_ACCEPTED)
        is not None
    )


# --- build_snapshot ---------------------------------------------------------------


def test_build_snapshot_is_idle_with_no_ids_when_session_is_empty(
    store: InMemoryBuilderStore,
) -> None:
    session = store.create_session(USER, **BuilderSessionFactory.create_kwargs())

    snapshot = build_snapshot(str(session.id), user_id=USER, store=store)

    assert snapshot.state == "idle"
    assert snapshot.running_turn is None
    assert snapshot.latest_message_id is None
    assert snapshot.latest_revision is None
    assert snapshot.latest_unproposed_revision is None


async def test_build_snapshot_shows_running_turn_state_when_turn_is_live(
    store: InMemoryBuilderStore, bus: SessionEventBus
) -> None:
    live = _begin(store)
    register_live_turn(live)
    runner = _runner(live, store, bus)
    await runner.signal_stage(TurnAccepted())
    await runner.publish(
        ToolStarted(
            ts=_now(),
            turn_id="x",
            seq=1,
            call_id="c1",
            tool="read_file",
            kind="read",
            label="Read SKILL.md",
            command=None,
        )
    )

    snapshot = build_snapshot(live.session_id, user_id=USER, store=store)

    assert snapshot.state == "running"
    running = snapshot.running_turn
    assert running is not None
    assert running.turn_id == live.turn_id
    assert running.message_id == live.user_message_id
    assert running.stage == Stage.STARTING
    assert running.through_seq == 2
    assert [a.call_id for a in running.activity] == ["c1"]
    assert snapshot.latest_message_id == live.turn_id


def test_build_snapshot_is_idle_when_live_turn_belongs_to_another_user(
    store: InMemoryBuilderStore,
) -> None:
    live = _begin(store)
    register_live_turn(live)

    snapshot = build_snapshot(live.session_id, user_id=OTHER, store=store)

    assert snapshot.state == "idle"
    assert snapshot.running_turn is None


def test_build_snapshot_reports_latest_revision_ids_when_revisions_exist(
    store: InMemoryBuilderStore,
) -> None:
    live = _begin(store)
    store.insert_revision(
        USER, live.session_id, kind="accepted", manifest=MANIFEST, manifest_hash="h1"
    )
    store.insert_revision(
        USER, live.session_id, kind="unproposed", manifest=MANIFEST, manifest_hash="h2"
    )

    snapshot = build_snapshot(live.session_id, user_id=USER, store=store)

    assert snapshot.latest_revision == 1
    assert snapshot.latest_unproposed_revision == 2


def test_build_snapshot_skips_tool_rows_when_choosing_latest_message(
    store: InMemoryBuilderStore,
) -> None:
    live = _begin(store)
    store.insert_tool_row(
        USER,
        live.session_id,
        live.turn_id,
        status="ok",
        content="r",
        tool={"call_id": "c"},
    )

    snapshot = build_snapshot(live.session_id, user_id=USER, store=store)

    assert snapshot.latest_message_id == live.turn_id


def test_snapshot_fn_builds_snapshot_inside_bus_subscribe_when_called_synchronously(
    store: InMemoryBuilderStore, bus: SessionEventBus
) -> None:
    live = _begin(store)
    register_live_turn(live)
    live.seq = 4

    _, snapshot = bus.subscribe(live.session_id, _snapshot_fn(store, live.session_id))

    assert snapshot.running_turn is not None
    assert snapshot.running_turn.through_seq == 4


# --- run_turn and finalize_turn (task 15.4) -----------------------------------------

_SKILLS_ROOT = SKILLS_ROOT
_MANIFEST: dict[str, Any] = {"id": "wf-one", "steps": [{"agent": "custom-agent"}]}


def _deps(
    store: InMemoryBuilderStore,
    bus: SessionEventBus,
    tmp_path: Path,
    model: FakeChatModel,
) -> TurnDeps:
    return TurnDeps(
        bus=bus,
        store_scope=_scope(store),
        sandbox_factory=lambda user, session: BuilderSandbox(
            user, session, root=tmp_path / "builder"
        ),
        gate=FakeGate(),
        chat_model=model,
        skills_root=_SKILLS_ROOT,
    )


def _request() -> TurnRequest:
    return TurnRequest(content="make a workflow", canvas_state={"steps": []})


def _watch(bus: SessionEventBus, live: LiveTurn) -> asyncio.Queue[BuilderEvent | None]:
    queue, _ = bus.subscribe(live.session_id, lambda: build_snapshot_stub(live))
    return queue


def _assistant_row(store: InMemoryBuilderStore, live: LiveTurn) -> Any:
    row = store.get_message(USER, live.turn_id)
    assert row is not None
    return row


def _completed(events: list[BuilderEvent]) -> TurnCompleted:
    done = [e for e in events if isinstance(e, TurnCompleted)]
    assert len(done) == 1
    return done[0]


@pytest.mark.parametrize(
    ("reason", "failed", "expected"),
    [
        (None, False, "completed"),
        (None, True, "failed"),
        ("time", False, "timed_out"),
        ("tool_calls", False, "timed_out"),
        ("tokens", False, "timed_out"),
        ("recursion", False, "timed_out"),
        ("gate_rejections", False, "completed"),
        ("cancelled", False, "cancelled"),
        ("deleted", False, "cancelled"),
        ("shutdown", False, "interrupted"),
        ("restart", False, "interrupted"),
        ("error", False, "failed"),
    ],
)
def test_status_for_stop_maps_reason_to_one_status_when_turn_ends(
    reason: StopReason | None, failed: bool, expected: str
) -> None:
    assert status_for_stop(reason, failed=failed) == expected


async def test_run_turn_completes_and_stores_row_when_agent_replies(
    store: InMemoryBuilderStore, bus: SessionEventBus, tmp_path: Path
) -> None:
    live = _begin(store)
    register_live_turn(live)
    queue = _watch(bus, live)
    model = FakeChatModel(
        turns=(
            ModelTurn(
                thinking=("hmm",),
                text=("Hello ", "there"),
                usage=ScriptedUsage(input_tokens=10, output_tokens=5),
            ),
        )
    )

    await run_turn(live, _request(), _deps(store, bus, tmp_path, model))

    events = _drain(queue)
    assert isinstance(events[0], TurnStarted)
    assert events[0].seq == 1
    assert [e.stage for e in events if isinstance(e, StageChanged)][0] == "starting"
    assert [e.seq for e in events if isinstance(e, TurnScoped)] == list(
        range(1, len([e for e in events if isinstance(e, TurnScoped)]) + 1)
    )
    done = _completed(events)
    assert events[-1] is done
    assert (done.status, done.outcome, done.stop_reason) == ("completed", "reply", None)
    row = _assistant_row(store, live)
    assert row.status == "completed"
    assert row.content == "Hello there"
    assert row.thinking == "hmm"
    assert row.usage["input"] == 10
    assert row.usage["output"] == 5
    assert row.prompt_version.startswith("v1:")
    assert row.adherence["manifest_turn"] is False
    assert get_live_turn(live.session_id) is None


async def test_run_turn_writes_canvas_file_and_leaves_workflows_empty_when_started(
    store: InMemoryBuilderStore, bus: SessionEventBus, tmp_path: Path
) -> None:
    live = _begin(store)
    model = FakeChatModel(turns=(ModelTurn(text=("ok",)),))

    await run_turn(live, _request(), _deps(store, bus, tmp_path, model))

    sandbox = BuilderSandbox(USER, live.session_id, root=tmp_path / "builder")
    canvas = json.loads(sandbox.path_for(CANVAS_FILE).read_text(encoding="utf-8"))
    assert canvas == {"steps": []}
    assert list(sandbox.path_for("workflows").iterdir()) == []


async def test_run_turn_rebuilds_missing_sandbox_when_session_has_a_draft(
    store: InMemoryBuilderStore, bus: SessionEventBus, tmp_path: Path
) -> None:
    live = _begin(store)
    store.insert_revision(
        USER,
        live.session_id,
        kind=DRAFT_KIND_ACCEPTED,
        manifest=_MANIFEST,
        manifest_hash=canonical_hash(_MANIFEST),
    )
    model = FakeChatModel(turns=(ModelTurn(text=("ok",)),))

    await run_turn(live, _request(), _deps(store, bus, tmp_path, model))

    sandbox = BuilderSandbox(USER, live.session_id, root=tmp_path / "builder")
    written = json.loads(
        sandbox.path_for("workflows/wf-one.workflow.json").read_text(encoding="utf-8")
    )
    assert written == _MANIFEST


async def test_run_turn_counts_a_clarifying_turn_when_reply_before_first_draft(
    store: InMemoryBuilderStore, bus: SessionEventBus, tmp_path: Path
) -> None:
    live = _begin(store)
    model = FakeChatModel(turns=(ModelTurn(text=("a question?",)),))

    await run_turn(live, _request(), _deps(store, bus, tmp_path, model))

    assert store.get_clarify_count(USER, live.session_id) == 1


async def test_run_turn_ends_timed_out_with_tool_calls_when_cap_is_reached(
    store: InMemoryBuilderStore,
    bus: SessionEventBus,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "BUILDER_MAX_TOOL_CALLS_PER_TURN", 2)
    live = _begin(store)
    queue = _watch(bus, live)
    model = FakeChatModel(
        turns=(ModelTurn(tool_calls=(ScriptedToolCall("get_builder_models", {}),)),),
        repeat_last=True,
    )

    await run_turn(live, _request(), _deps(store, bus, tmp_path, model))

    done = _completed(_drain(queue))
    assert (done.status, done.stop_reason) == ("timed_out", "tool_calls")
    assert _assistant_row(store, live).status == "timed_out"
    assert store.get_clarify_count(USER, live.session_id) == 0


async def test_run_turn_ends_timed_out_with_recursion_when_runner_reports_limit(
    store: InMemoryBuilderStore, bus: SessionEventBus, tmp_path: Path
) -> None:
    live = _begin(store)
    queue = _watch(bus, live)
    model = FakeChatModel(
        turns=(ModelTurn(error=RuntimeError("Recursion limit of 2500 reached")),)
    )

    await run_turn(live, _request(), _deps(store, bus, tmp_path, model))

    events = _drain(queue)
    done = _completed(events)
    assert (done.status, done.stop_reason) == ("timed_out", "recursion")
    assert not [e for e in events if isinstance(e, ErrorEvent)]


async def test_run_turn_ends_failed_with_generic_error_when_model_raises(
    store: InMemoryBuilderStore, bus: SessionEventBus, tmp_path: Path
) -> None:
    live = _begin(store)
    queue = _watch(bus, live)
    model = FakeChatModel(turns=(ModelTurn(error=ValueError("secret detail 123")),))

    await run_turn(live, _request(), _deps(store, bus, tmp_path, model))

    events = _drain(queue)
    errors = [e for e in events if isinstance(e, ErrorEvent)]
    assert len(errors) == 1
    assert "secret detail" not in errors[0].message
    assert errors[0].turn_id == live.turn_id
    done = _completed(events)
    assert (done.status, done.stop_reason) == ("failed", "error")
    row = _assistant_row(store, live)
    assert row.status == "failed"
    assert row.error_code == errors[0].code


async def test_run_turn_stores_unproposed_revision_and_warns_when_time_cap_hits(
    store: InMemoryBuilderStore,
    bus: SessionEventBus,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    short = turns.TurnLimits(
        timeout_seconds=1,
        max_tool_calls=60,
        max_gate_rejections=2,
        warning_fraction=0.3,
    )
    monkeypatch.setattr(turns, "limits_from_settings", lambda: short)
    live = _begin(store)
    queue = _watch(bus, live)
    write = ScriptedToolCall(
        "write_file",
        {"file_path": "/workflows/a.workflow.json", "content": json.dumps(_MANIFEST)},
    )
    model = FakeChatModel(
        turns=(ModelTurn(tool_calls=(write,)), ModelTurn(text=("late",), delay=30.0))
    )

    await run_turn(live, _request(), _deps(store, bus, tmp_path, model))

    events = _drain(queue)
    done = _completed(events)
    assert (done.status, done.stop_reason) == ("timed_out", "time")
    assert [e.kind for e in events if isinstance(e, LimitWarning)] == ["time"]
    unproposed = store.get_latest_revisions(USER, live.session_id).unproposed
    assert unproposed is not None
    assert unproposed.manifest == _MANIFEST
    assert unproposed.source_file == "/workflows/a.workflow.json"
    assert unproposed.source_turn_id == live.turn_id


async def test_run_turn_starts_only_the_cap_and_warning_timers_when_running(
    store: InMemoryBuilderStore, bus: SessionEventBus, tmp_path: Path
) -> None:
    delays: list[float] = []
    loop = asyncio.get_running_loop()
    original = loop.call_later

    def record(delay: float, *args: Any, **kwargs: Any) -> Any:
        delays.append(delay)
        return original(delay, *args, **kwargs)

    loop.call_later = record  # type: ignore[method-assign]
    try:
        live = _begin(store)
        model = FakeChatModel(turns=(ModelTurn(text=("ok",)),))
        await run_turn(live, _request(), _deps(store, bus, tmp_path, model))
    finally:
        del loop.call_later

    timeout = settings.BUILDER_TURN_TIMEOUT_SECONDS
    assert timeout in delays
    assert settings.BUILDER_LIMIT_WARNING_FRACTION * timeout in delays
    assert 180 not in delays


async def test_run_turn_stops_with_tokens_when_budget_is_crossed(
    store: InMemoryBuilderStore,
    bus: SessionEventBus,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "BUILDER_TOKEN_BUDGET_PER_TURN", 100)
    live = _begin(store)
    queue = _watch(bus, live)
    model = FakeChatModel(
        turns=(
            ModelTurn(
                tool_calls=(ScriptedToolCall("get_builder_models", {}),),
                usage=ScriptedUsage(input_tokens=90, output_tokens=5),
            ),
            ModelTurn(
                tool_calls=(ScriptedToolCall("get_builder_models", {}),),
                usage=ScriptedUsage(input_tokens=90, output_tokens=5),
            ),
        ),
        repeat_last=True,
    )

    await run_turn(live, _request(), _deps(store, bus, tmp_path, model))

    events = _drain(queue)
    assert [e.kind for e in events if isinstance(e, LimitWarning)] == ["tokens"]
    assert _completed(events).stop_reason == "tokens"


# --- finalize_turn ------------------------------------------------------------------


async def test_finalize_turn_ends_unfinished_and_keeps_work_when_second_gate_rejection(
    store: InMemoryBuilderStore, bus: SessionEventBus, tmp_path: Path
) -> None:
    live = _begin(store)
    register_live_turn(live)
    queue = _watch(bus, live)
    sandbox = BuilderSandbox(USER, live.session_id, root=tmp_path / "builder")
    sandbox.ensure()
    sandbox.path_for("workflows/w.workflow.json").write_text(
        json.dumps(_MANIFEST), encoding="utf-8"
    )
    live.changed_workflow_files["/workflows/w.workflow.json"] = 1.0
    live.gate_rejections = 2
    live.checks.append(
        CheckResult(source="server_gate", verdict="invalid", errors=2, warnings=0)
    )
    live.stop_reason = "gate_rejections"
    runner = _runner(live, store, bus)
    run = TurnRunState(sandbox=sandbox)
    run.reply.append("I tried.")

    await finalize_turn(runner, run, "completed")

    done = _completed(_drain(queue))
    assert (done.status, done.outcome) == ("completed", "unfinished")
    row = _assistant_row(store, live)
    assert (row.status, row.outcome, row.stop_reason) == (
        "completed",
        "unfinished",
        "gate_rejections",
    )
    assert row.content.startswith("I tried.")
    assert "the platform check" in row.content
    unproposed = store.get_latest_revisions(USER, live.session_id).unproposed
    assert unproposed is not None
    assert unproposed.kind == DRAFT_KIND_UNPROPOSED
    assert store.get_clarify_count(USER, live.session_id) == 0
    assert get_live_turn(live.session_id) is None


async def test_finalize_turn_keeps_accepted_draft_when_cancelled_after_accept(
    store: InMemoryBuilderStore, bus: SessionEventBus, tmp_path: Path
) -> None:
    live = _begin(store)
    register_live_turn(live)
    queue = _watch(bus, live)
    sandbox = BuilderSandbox(USER, live.session_id, root=tmp_path / "builder")
    sandbox.ensure()
    sandbox.path_for("workflows/w.workflow.json").write_text(
        json.dumps(_MANIFEST), encoding="utf-8"
    )
    live.changed_workflow_files["/workflows/w.workflow.json"] = 1.0
    live.accepted_revision = 1
    live.accepted_manifest_hash = canonical_hash(_MANIFEST)
    live.stop_reason = "cancelled"
    runner = _runner(live, store, bus)

    await finalize_turn(runner, TurnRunState(sandbox=sandbox), "cancelled")

    done = _completed(_drain(queue))
    assert (done.status, done.outcome, done.revision) == ("cancelled", "draft", 1)
    assert _assistant_row(store, live).revision == 1
    assert store.get_latest_revisions(USER, live.session_id).unproposed is None


async def test_finalize_turn_stores_unproposed_when_written_file_differs_from_accepted(
    store: InMemoryBuilderStore, bus: SessionEventBus, tmp_path: Path
) -> None:
    live = _begin(store)
    sandbox = BuilderSandbox(USER, live.session_id, root=tmp_path / "builder")
    sandbox.ensure()
    sandbox.path_for("workflows/w.workflow.json").write_text(
        json.dumps({**_MANIFEST, "id": "later"}), encoding="utf-8"
    )
    live.changed_workflow_files["/workflows/w.workflow.json"] = 1.0
    live.accepted_revision = 1
    live.accepted_manifest_hash = canonical_hash(_MANIFEST)
    live.stop_reason = "shutdown"

    await finalize_turn(
        _runner(live, store, SessionEventBus()),
        TurnRunState(sandbox=sandbox),
        "interrupted",
    )

    unproposed = store.get_latest_revisions(USER, live.session_id).unproposed
    assert unproposed is not None
    assert unproposed.manifest["id"] == "later"
    assert _assistant_row(store, live).status == "interrupted"


async def test_finalize_turn_only_cleans_up_when_session_was_deleted(
    store: InMemoryBuilderStore, bus: SessionEventBus
) -> None:
    live = _begin(store)
    register_live_turn(live)
    queue = _watch(bus, live)
    live.stop_reason = "deleted"

    await finalize_turn(_runner(live, store, bus), TurnRunState(), "cancelled")

    assert _drain(queue) == []
    assert _assistant_row(store, live).status == MESSAGE_STATUS_RUNNING
    assert get_live_turn(live.session_id) is None


async def test_finalize_turn_stores_summary_tokens_and_skill_hash_when_turn_ends(
    store: InMemoryBuilderStore, bus: SessionEventBus
) -> None:
    live = _begin(store)
    live.usage = live.usage.model_copy(
        update={"input": 3, "summary": UsageCounts(input=7, output=2)}
    )
    run = TurnRunState(skill_hash="skill-now")

    await finalize_turn(_runner(live, store, bus), run, "completed")

    row = _assistant_row(store, live)
    assert row.usage["summary"]["input"] == 7
    assert row.skill_hash == "skill-now"
    assert row.prompt_version.startswith("v1:")


def test_unproposed_candidate_returns_none_when_no_workflow_was_written(
    tmp_path: Path,
) -> None:
    live = LiveTurn("s", "t", "u", USER, "m", None)
    sandbox = BuilderSandbox(USER, "s", root=tmp_path)
    sandbox.ensure()

    assert turns._unproposed_candidate(live, sandbox) is None


def test_unproposed_candidate_returns_newest_file_when_several_were_written(
    tmp_path: Path,
) -> None:
    live = LiveTurn("s", "t", "u", USER, "m", None)
    sandbox = BuilderSandbox(USER, "s", root=tmp_path)
    sandbox.ensure()
    for name, stamp in (("old", 1.0), ("new", 2.0)):
        sandbox.path_for(f"workflows/{name}.workflow.json").write_text(
            json.dumps({"id": name, "steps": []}), encoding="utf-8"
        )
        live.changed_workflow_files[f"/workflows/{name}.workflow.json"] = stamp

    candidate = turns._unproposed_candidate(live, sandbox)

    assert candidate is not None
    assert candidate[0] == "/workflows/new.workflow.json"
    assert candidate[1]["id"] == "new"


@pytest.mark.parametrize("content", ["not json", "[1, 2]"])
def test_unproposed_candidate_returns_none_when_file_is_not_a_json_object(
    tmp_path: Path, content: str
) -> None:
    live = LiveTurn("s", "t", "u", USER, "m", None)
    sandbox = BuilderSandbox(USER, "s", root=tmp_path)
    sandbox.ensure()
    sandbox.path_for("workflows/a.workflow.json").write_text(content, encoding="utf-8")
    live.changed_workflow_files["/workflows/a.workflow.json"] = 1.0

    assert turns._unproposed_candidate(live, sandbox) is None


# --- Cancel and stop (task 15.5) --------------------------------------------------------


def _live_for(session: str, turn: str, user: str = USER) -> LiveTurn:
    return LiveTurn(session, turn, "user-message", user, "model-x", None)


async def _wait_until(predicate: Callable[[], bool], timeout: float = 10.0) -> None:
    """Poll ``predicate`` until it holds, or fail after ``timeout`` seconds."""

    async def poll() -> None:
        while not predicate():
            await asyncio.sleep(0.01)

    await asyncio.wait_for(poll(), timeout)


async def _start_turn(
    live: LiveTurn,
    model: FakeChatModel,
    store: InMemoryBuilderStore,
    bus: SessionEventBus,
    tmp_path: Path,
) -> asyncio.Task[None]:
    """Register the Turn, run it as a task and wait until the stage is set."""
    register_live_turn(live)
    task = asyncio.ensure_future(
        run_turn(live, _request(), _deps(store, bus, tmp_path, model))
    )
    attach_task(live, task)
    await _wait_until(lambda: live.stage is not None)
    return task


def test_cancel_turn_returns_cancelling_and_sets_reason_when_turn_is_live() -> None:
    live = _live_for("s", "t")
    register_live_turn(live)

    assert cancel_turn("s", "t") == "cancelling"
    assert live.stop_reason == "cancelled"


def test_cancel_turn_returns_not_running_when_no_turn_is_live() -> None:
    assert cancel_turn("s", "t") == "not_running"


def test_cancel_turn_returns_not_running_and_leaves_turn_when_turn_id_differs() -> None:
    live = _live_for("s", "t")
    register_live_turn(live)

    assert cancel_turn("s", "other") == "not_running"
    assert live.stop_reason is None


def test_cancel_turn_returns_not_running_when_turn_is_storing_its_end() -> None:
    live = _live_for("s", "t")
    register_live_turn(live)
    live.finalizing = True

    assert cancel_turn("s", "t") == "not_running"
    assert live.stop_reason is None


def test_cancel_turn_keeps_first_reason_when_turn_already_stopping() -> None:
    live = _live_for("s", "t")
    register_live_turn(live)
    live.stop("time")

    assert cancel_turn("s", "t") == "cancelling"
    assert live.stop_reason == "time"


def test_stop_sets_no_reason_when_turn_already_finalizing() -> None:
    live = _live_for("s", "t")
    live.finalizing = True

    live.stop("cancelled")

    assert live.stop_reason is None


def test_stop_session_turn_stops_with_deleted_when_session_has_live_turn() -> None:
    live = _live_for("s", "t")
    register_live_turn(live)

    assert stop_session_turn("s") is True
    assert live.stop_reason == "deleted"


def test_stop_session_turn_returns_false_when_session_has_no_live_turn() -> None:
    assert stop_session_turn("s") is False


def test_stop_user_turns_stops_only_that_users_turns_when_several_are_live() -> None:
    mine = _live_for("s1", "t1", user=USER)
    other = _live_for("s2", "t2", user="someone-else")
    register_live_turn(mine)
    register_live_turn(other)

    assert stop_user_turns(USER) == 1
    assert mine.stop_reason == "deleted"
    assert other.stop_reason is None


async def test_stop_all_returns_without_waiting_when_no_turn_is_live() -> None:
    await asyncio.wait_for(stop_all(persist_seconds=5.0), 1.0)


async def test_cancel_turn_stores_cancelled_row_when_turn_running_without_draft(
    store: InMemoryBuilderStore, bus: SessionEventBus, tmp_path: Path
) -> None:
    live = _begin(store)
    queue = _watch(bus, live)
    model = FakeChatModel(turns=(ModelTurn(text=("late",), delay=30.0),))
    task = await _start_turn(live, model, store, bus, tmp_path)

    assert cancel_turn(live.session_id, live.turn_id) == "cancelling"
    await asyncio.wait_for(task, 10)

    done = _completed(_drain(queue))
    assert (done.status, done.stop_reason, done.outcome) == (
        "cancelled",
        "cancelled",
        "reply",
    )
    assert _assistant_row(store, live).status == "cancelled"
    assert get_live_turn(live.session_id) is None


async def test_cancel_turn_keeps_accepted_draft_when_draft_accepted_before_cancel(
    store: InMemoryBuilderStore, bus: SessionEventBus, tmp_path: Path
) -> None:
    live = _begin(store)
    queue = _watch(bus, live)
    write = ScriptedToolCall(
        "write_file",
        {"file_path": "/workflows/a.workflow.json", "content": json.dumps(_MANIFEST)},
    )
    propose = ScriptedToolCall("propose_draft", {"path": "/workflows/a.workflow.json"})
    model = FakeChatModel(
        turns=(
            ModelTurn(tool_calls=(write,)),
            ModelTurn(tool_calls=(propose,)),
            ModelTurn(text=("late",), delay=30.0),
        )
    )
    task = await _start_turn(live, model, store, bus, tmp_path)
    await _wait_until(lambda: live.accepted_revision is not None)

    assert cancel_turn(live.session_id, live.turn_id) == "cancelling"
    await asyncio.wait_for(task, 10)

    done = _completed(_drain(queue))
    assert (done.status, done.outcome, done.revision) == ("cancelled", "draft", 1)
    accepted = store.get_latest_revisions(USER, live.session_id).accepted
    assert accepted is not None
    assert accepted.manifest == _MANIFEST


async def test_stop_session_turn_publishes_no_completion_when_session_deleted_mid_turn(
    store: InMemoryBuilderStore, bus: SessionEventBus, tmp_path: Path
) -> None:
    live = _begin(store)
    queue = _watch(bus, live)
    model = FakeChatModel(turns=(ModelTurn(text=("late",), delay=30.0),))
    task = await _start_turn(live, model, store, bus, tmp_path)

    assert stop_session_turn(live.session_id) is True
    await asyncio.wait_for(task, 10)

    events = _drain(queue)
    assert not [e for e in events if isinstance(e, TurnCompleted)]
    assert _assistant_row(store, live).status == MESSAGE_STATUS_RUNNING
    assert get_live_turn(live.session_id) is None


async def test_stop_all_stores_interrupted_row_when_shutdown_arrives_mid_turn(
    store: InMemoryBuilderStore, bus: SessionEventBus, tmp_path: Path
) -> None:
    live = _begin(store)
    queue = _watch(bus, live)
    model = FakeChatModel(turns=(ModelTurn(text=("late",), delay=30.0),))
    task = await _start_turn(live, model, store, bus, tmp_path)

    await stop_all(persist_seconds=5.0)

    assert task.done()
    done = _completed(_drain(queue))
    assert (done.status, done.stop_reason) == ("interrupted", "shutdown")
    assert _assistant_row(store, live).status == "interrupted"
    assert get_live_turn(live.session_id) is None


class _FinalizeBlockingStore(InMemoryBuilderStore):
    """A store whose ``finalize_assistant`` waits until the test lets it go."""

    def __init__(self) -> None:
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()

    def finalize_assistant(self, *args: Any, **kwargs: Any) -> Any:
        self.entered.set()
        self.release.wait(timeout=5)
        return super().finalize_assistant(*args, **kwargs)


async def test_cancel_turn_returns_not_running_when_cancel_arrives_during_finalize(
    bus: SessionEventBus, tmp_path: Path
) -> None:
    blocking = _FinalizeBlockingStore()
    live = _begin(blocking)
    queue = _watch(bus, live)
    model = FakeChatModel(turns=(ModelTurn(text=("ok",)),))
    register_live_turn(live)
    task = asyncio.ensure_future(
        run_turn(live, _request(), _deps(blocking, bus, tmp_path, model))
    )
    attach_task(live, task)
    await asyncio.to_thread(blocking.entered.wait, 10)

    assert cancel_turn(live.session_id, live.turn_id) == "not_running"
    blocking.release.set()
    await asyncio.wait_for(task, 10)

    done = _completed(_drain(queue))
    assert (done.status, done.stop_reason) == ("completed", None)
    assert _assistant_row(blocking, live).status == "completed"


# --- _unproposed_candidate (task 15.11) ---------------------------------------------


def _candidate_turn(sandbox: BuilderSandbox, content: str, **kwargs: Any) -> LiveTurn:
    sandbox.ensure()
    sandbox.path_for("workflows/c.workflow.json").write_text(content, encoding="utf-8")
    live = LiveTurn("s", "t", "u", USER, "m", None)
    live.changed_workflow_files["/workflows/c.workflow.json"] = 1.0
    for key, value in kwargs.items():
        setattr(live, key, value)
    return live


def test_unproposed_candidate_returns_none_when_sandbox_is_missing() -> None:
    live = LiveTurn("s", "t", "u", USER, "m", None)
    live.changed_workflow_files["/workflows/c.workflow.json"] = 1.0

    assert turns._unproposed_candidate(live, None) is None


def test_unproposed_candidate_returns_none_when_no_workflow_file_changed(
    tmp_path: Path,
) -> None:
    sandbox = BuilderSandbox(USER, "s", root=tmp_path / "builder")
    live = LiveTurn("s", "t", "u", USER, "m", None)

    assert turns._unproposed_candidate(live, sandbox) is None


def test_unproposed_candidate_returns_none_when_file_is_not_json_object(
    tmp_path: Path,
) -> None:
    sandbox = BuilderSandbox(USER, "s", root=tmp_path / "builder")

    for content in ("[1, 2]", "not json"):
        live = _candidate_turn(sandbox, content)
        assert turns._unproposed_candidate(live, sandbox) is None


def test_unproposed_candidate_returns_none_when_file_equals_accepted_manifest(
    tmp_path: Path,
) -> None:
    sandbox = BuilderSandbox(USER, "s", root=tmp_path / "builder")
    live = _candidate_turn(
        sandbox,
        json.dumps(_MANIFEST),
        accepted_manifest_hash=canonical_hash(_MANIFEST),
    )

    assert turns._unproposed_candidate(live, sandbox) is None


def test_unproposed_candidate_returns_newest_file_when_several_were_written(
    tmp_path: Path,
) -> None:
    sandbox = BuilderSandbox(USER, "s", root=tmp_path / "builder")
    live = _candidate_turn(sandbox, json.dumps({"id": "old"}))
    sandbox.path_for("workflows/n.workflow.json").write_text(
        json.dumps({"id": "new"}), encoding="utf-8"
    )
    live.changed_workflow_files["/workflows/n.workflow.json"] = 2.0

    assert turns._unproposed_candidate(live, sandbox) == (
        "/workflows/n.workflow.json",
        {"id": "new"},
    )
