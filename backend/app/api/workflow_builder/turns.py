"""Live Turn state, the live-turn registries and the Turn_Runner's port adapter.

This module holds what the Turn_Runner keeps in memory for a running Turn
(design 3.1.4) and the :class:`TurnRunner` that exposes it to the agent layer
as a :class:`~app.agents.workflow_builder.ports.TurnPort`:

* :class:`LiveTurn` is the in-process state of one Turn. It has a single
  ``stop_reason``. The first stop wins and cancels the Turn's task.
* ``_LIVE_TURNS`` (session id to live Turn) and ``_TURN_TASKS`` (the set of Turn
  tasks) are the registries. A Turn is removed from both when it ends
  (``release_live_turn``). One process runs all Turns (Req 48.16); everything that
  must survive a restart is stored.
* :class:`TurnRunner` assigns the Turn's ``seq`` to every Turn-scoped event
  *before* it hands the event to the bus, in one synchronous block, so every
  subscriber sees one order (Req 38.2, 40.5). It keeps the live activity and
  check lists the snapshot reads (Req 40.6), moves the stage through
  ``derive_stage``, stores tool rows and accepted drafts through the
  Session_Store in ``asyncio.to_thread``, and counts tool calls and gate
  rejections.
* :func:`build_snapshot` builds the first frame of a Session_Stream from the
  live Turn and the latest stored ids (Req 38.3).

* :func:`run_turn` runs one Turn (task 15.4, design 3.1.4). :func:`finalize_turn`
  stores its one terminal status, the unproposed revision, the clarify count, the
  adherence record and the usage, publishes ``turn_completed`` and removes the Turn
  from both registries. Nothing stops a Turn at 180 s; the only time cap is
  ``BUILDER_TURN_TIMEOUT_SECONDS``.

* :func:`cancel_turn` answers the Stop control (task 15.5). :func:`stop_session_turn`
  and :func:`stop_user_turns` stop the Turns of a deleted Session or account, and
  :func:`stop_all` stops every Turn for a shutdown and waits for their rows.

Authorisation: ``user_id`` is the key. The store is always called with the live
Turn's ``user_id``, and :func:`build_snapshot` shows a live Turn only to its
owner.

The shared :class:`~app.api.workflow_builder.bus.SessionEventBus` lives here:
:func:`get_event_bus` creates it on first use, and :func:`set_event_bus` replaces
it (tests, or an app that wants its own). A :class:`TurnRunner` can also be given
a bus directly.

Logs carry ids and counts only, never message text, tool output or
``canvas_state`` (Req 42.4, 44.2).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager, aclosing, contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal, Protocol

from app.agents.llm_errors import map_exception
from app.agents.workflow_builder import adherence as adherence_module
from app.agents.workflow_builder.adherence import AdherenceRecord
from app.agents.workflow_builder.adherence import ToolCall as AdherenceToolCall
from app.agents.workflow_builder.agent import (
    PROMPT_VERSION,
    BuilderPorts,
    BuilderTurnInputs,
    build_builder_runner,
)
from app.agents.workflow_builder.canonical import canonical_hash
from app.agents.workflow_builder.events import (
    BuilderEvent,
    CheckResult,
    CheckResultEvent,
    CheckStep,
    ErrorEvent,
    LimitWarning,
    Outcome,
    RunningTurnSnapshot,
    Snapshot,
    StageChanged,
    StopReason,
    Text,
    Thinking,
    ThinkingStep,
    TokenUsage,
    ToolActivity,
    ToolFinished,
    ToolsStep,
    TurnCompleted,
    TurnScoped,
    TurnStarted,
    TurnStatus,
    TurnStep,
)
from app.agents.workflow_builder.events import ToolStarted as ToolStartedEvent
from app.agents.workflow_builder.model_catalog_view import builder_models
from app.agents.workflow_builder.ports import (
    AcceptedDraft,
    FinishedToolCall,
    GatePort,
    TurnLimits,
)
from app.agents.workflow_builder.read_tools import (
    BuilderReadPort,
    PlaceholderReadPort,
)
from app.agents.workflow_builder.sandbox import (
    CANVAS_FILE,
    BuilderSandbox,
    SandboxPathError,
)
from app.agents.workflow_builder.script_policy import BUILDER_SKILL_ID
from app.agents.workflow_builder.skill_package import SKILL_DIR, read_skill_facts
from app.agents.workflow_builder.stages import (
    Signal,
    Stage,
    TextDelta,
    ThinkingDelta,
    TurnAccepted,
    derive_stage,
    label_for,
)
from app.agents.workflow_builder.transcript import counts_toward_clarify
from app.api.run_engine import _saved_row_trust
from app.api.workflow_builder.agent_input import (
    InputRequest,
    InputStore,
    Summarizer,
    add_usage,
    build_agent_input,
    default_summarizer,
)
from app.api.workflow_builder.bus import SessionEventBus
from app.api.workflow_builder.gate import ServerGate
from app.api.workflow_builder.store import (
    BuilderStore,
    LatestRevisions,
)
from app.api.workflow_builder.telemetry import (
    emit_gate_rejection,
    emit_script_call,
    emit_turn_metrics,
    turn_logger,
)
from app.core.config import settings
from app.models.database import SessionLocal
from app.models.workflow_builder import (
    DRAFT_KIND_ACCEPTED,
    DRAFT_KIND_UNPROPOSED,
    MESSAGE_STATUS_TIMED_OUT,
    MESSAGE_STATUS_TOOL_ERROR,
    MESSAGE_STATUS_TOOL_OK,
    MESSAGE_STATUS_TOOL_REFUSED,
    MESSAGE_STATUS_TOOL_STOPPED,
    WorkflowBuilderDraft,
    WorkflowBuilderMessage,
)

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

__all__ = [
    "STORED_RESULT_HEAD_CHARS",
    "STORED_RESULT_TAIL_CHARS",
    "LiveTurn",
    "SnapshotStore",
    "StoreScope",
    "TurnDeps",
    "TurnRequest",
    "TurnRunState",
    "TurnRunner",
    "TurnStore",
    "add_thinking_step",
    "add_tool_step",
    "attach_task",
    "build_snapshot",
    "cancel_turn",
    "finalize_turn",
    "get_event_bus",
    "get_live_turn",
    "limits_from_settings",
    "open_store",
    "register_live_turn",
    "release_live_turn",
    "run_turn",
    "set_event_bus",
    "stop_all",
    "stop_session_turn",
    "stop_user_turns",
    "status_for_stop",
    "stored_steps",
    "truncate_result",
]

_logger_name: Final = __name__

# A stored tool result keeps at most head + tail characters, the cut note included
# [pending G-19]: the head is kept whole and the tail is shortened by the note.
STORED_RESULT_HEAD_CHARS: Final = 3000
STORED_RESULT_TAIL_CHARS: Final = 1000

_TOOL_ROW_STATUSES: Final = frozenset(
    {
        MESSAGE_STATUS_TOOL_OK,
        MESSAGE_STATUS_TOOL_ERROR,
        MESSAGE_STATUS_TOOL_REFUSED,
        MESSAGE_STATUS_TOOL_STOPPED,
        MESSAGE_STATUS_TIMED_OUT,
    }
)


# --- Pure helpers ---------------------------------------------------------------------


def add_thinking_step(steps: list[TurnStep], text: str) -> None:
    """Add reasoning ``text`` to ``steps``: join the last step when it is thinking.

    An empty ``text`` changes nothing.
    """
    if not text:
        return
    last = steps[-1] if steps else None
    if isinstance(last, ThinkingStep):
        steps[-1] = last.model_copy(update={"text": last.text + text})
    else:
        steps.append(ThinkingStep(text=text))


def add_tool_step(steps: list[TurnStep], call_id: str) -> None:
    """Add a started call to ``steps``: join the last step when it is a tool group.

    A call id already in the last group is not added twice.
    """
    last = steps[-1] if steps else None
    if isinstance(last, ToolsStep):
        if call_id not in last.call_ids:
            steps[-1] = last.model_copy(update={"call_ids": [*last.call_ids, call_id]})
    else:
        steps.append(ToolsStep(call_ids=[call_id]))


def stored_steps(steps: list[TurnStep]) -> list[dict[str, Any]] | None:
    """The JSON form of ``steps`` for the assistant row, or ``None`` when there are none."""
    return [step.model_dump(mode="json") for step in steps] or None


def truncate_result(text: str) -> str:
    """Cut a tool result to at most 4,000 characters, note included (G-19).

    A result that fits in 4,000 characters is returned unchanged. Otherwise the
    first 3,000 characters and the end of the text are joined by a note that
    gives the number of characters cut. The tail is the last 1,000 characters
    shortened by the length of the note, so the whole result stays within 4,000.
    """
    limit = STORED_RESULT_HEAD_CHARS + STORED_RESULT_TAIL_CHARS
    if len(text) <= limit:
        return text
    # The note holds the cut count, and the cut count depends on the tail that is
    # kept, so settle the tail size. It only shrinks, so the loop ends.
    tail_keep = STORED_RESULT_TAIL_CHARS
    while True:
        cut = len(text) - STORED_RESULT_HEAD_CHARS - tail_keep
        note = f"\n[... {cut} characters cut ...]\n"
        settled = max(STORED_RESULT_TAIL_CHARS - len(note), 0)
        if settled == tail_keep:
            break
        tail_keep = settled
    return f"{text[:STORED_RESULT_HEAD_CHARS]}{note}{text[len(text) - tail_keep :]}"


# --- Live turn ------------------------------------------------------------------------


@dataclass(eq=False)
class LiveTurn:
    """In-process state of one running Turn (design 3.1.4).

    Attributes:
        session_id: The Session the Turn belongs to.
        turn_id: The Turn id, equal to the assistant message id.
        user_message_id: The user message the Turn answers.
        user_id: The owner. It is the authorisation key for every store call.
        model_id: The chat model of the Turn.
        effort: The reasoning effort, or ``None``.
        tier: The caller's effective tier. An unknown tier is treated as
            ``basic`` by every tier lookup (fail closed).
        started_at: Monotonic start time. Set after admission (Req 28.5).
        started_at_wall: The same moment as a UTC time, for the snapshot.
        seq: The ``seq`` of the last event published for this Turn.
        stage: The current stage, or ``None`` before the first one.
        stage_seconds: Seconds spent in each finished stage.
        activity: Tool calls so far, running and finished.
        checks: Check results so far.
        steps: Thinking, tool-call groups and checks in the order they were
            published. Stored on the assistant row when the Turn ends.
        finished_calls: Finished tool calls, for the adherence record.
        tool_calls: Tool calls counted so far.
        gate_rejections: Server_Gate rejections so far.
        accepted_revision: The revision this Turn accepted, or ``None``.
        accepted_manifest_hash: Canonical hash of the accepted manifest, or
            ``None``. The unproposed-revision rule compares written files to it.
        changed_workflow_files: Virtual path to the monotonic time of the last
            successful write, for ``/workflows/*.workflow.json`` files.
        usage: Token usage so far.
        stop_reason: Why the Turn is being stopped. Set once.
        finalizing: The Turn's status is fixed and its rows are being stored. From
            then on :meth:`stop` changes nothing, so the stored status always
            agrees with the stop reason.
        task: The asyncio task that runs the Turn.
    """

    session_id: str
    turn_id: str
    user_message_id: str
    user_id: str
    model_id: str
    effort: str | None
    tier: str = "basic"
    started_at: float = field(default_factory=time.monotonic)
    started_at_wall: datetime = field(default_factory=lambda: datetime.now(UTC))
    seq: int = 0
    stage: Stage | None = None
    stage_entered_at: float = field(default_factory=time.monotonic)
    stage_seconds: dict[Stage, float] = field(default_factory=dict)
    activity: list[ToolActivity] = field(default_factory=list)
    checks: list[CheckResult] = field(default_factory=list)
    steps: list[TurnStep] = field(default_factory=list)
    finished_calls: list[AdherenceToolCall] = field(default_factory=list)
    tool_calls: int = 0
    gate_rejections: int = 0
    accepted_revision: int | None = None
    accepted_manifest_hash: str | None = None
    changed_workflow_files: dict[str, float] = field(default_factory=dict)
    usage: TokenUsage = field(default_factory=TokenUsage.zero)
    stop_reason: StopReason | None = None
    finalizing: bool = False
    task: asyncio.Task[None] | None = None

    @property
    def stopping(self) -> bool:
        """True once the Turn has a stop reason."""
        return self.stop_reason is not None

    def stop(self, reason: StopReason) -> None:
        """Stop the Turn. The first reason wins; later calls change nothing.

        Sets the reason and cancels the Turn's task. A task attached later is
        cancelled by :func:`attach_task`. Once the Turn is finalizing, the status
        is already fixed, so the call changes nothing (Req 30.2).
        """
        if self.stop_reason is not None or self.finalizing:
            return
        self.stop_reason = reason
        if self.task is not None and not self.task.done():
            self.task.cancel()

    def set_stage(self, stage: Stage) -> None:
        """Move to ``stage`` and add the time spent in the stage left."""
        now = time.monotonic()
        if self.stage is not None:
            self.stage_seconds[self.stage] = self.stage_seconds.get(
                self.stage, 0.0
            ) + max(0.0, now - self.stage_entered_at)
        self.stage = stage
        self.stage_entered_at = now

    def stage_durations(self) -> dict[Stage, float]:
        """Return seconds per stage, counting the open stage up to now."""
        durations = dict(self.stage_seconds)
        if self.stage is not None:
            open_seconds = max(0.0, time.monotonic() - self.stage_entered_at)
            durations[self.stage] = durations.get(self.stage, 0.0) + open_seconds
        return durations


# --- Registries -----------------------------------------------------------------------

# session id -> the live Turn. One Turn per Session; the stored partial unique
# index is the restart-safe guard (Req 21.8).
_LIVE_TURNS: dict[str, LiveTurn] = {}
# Turn tasks, held so they are not garbage collected while they run.
_TURN_TASKS: set[asyncio.Task[None]] = set()


def get_live_turn(session_id: str) -> LiveTurn | None:
    """Return the live Turn of ``session_id``, or ``None`` when it has none."""
    return _LIVE_TURNS.get(session_id)


def register_live_turn(turn: LiveTurn) -> None:
    """Make ``turn`` the live Turn of its Session."""
    _LIVE_TURNS[turn.session_id] = turn


def attach_task(turn: LiveTurn, task: asyncio.Task[None]) -> None:
    """Record ``task`` as the Turn's task and keep it in ``_TURN_TASKS``.

    A Turn stopped before its task was attached cancels the task here.
    """
    turn.task = task
    _TURN_TASKS.add(task)
    task.add_done_callback(_TURN_TASKS.discard)
    if turn.stopping:
        task.cancel()


def release_live_turn(turn: LiveTurn) -> None:
    """Remove ``turn`` from both registries (called when the Turn ends).

    A newer Turn registered for the same Session is left alone.
    """
    if _LIVE_TURNS.get(turn.session_id) is turn:
        del _LIVE_TURNS[turn.session_id]
    if turn.task is not None:
        _TURN_TASKS.discard(turn.task)


# --- Shared bus -----------------------------------------------------------------------

_bus: SessionEventBus | None = None


def get_event_bus() -> SessionEventBus:
    """Return the process-wide Session event bus, creating it on first use."""
    global _bus  # noqa: PLW0603 - one lazily created instance per process
    if _bus is None:
        _bus = SessionEventBus()
    return _bus


def set_event_bus(bus: SessionEventBus | None) -> None:
    """Replace the process-wide bus. ``None`` makes the next use create a new one."""
    global _bus  # noqa: PLW0603 - one instance per process, replaceable for tests
    _bus = bus


# --- Store access ---------------------------------------------------------------------


class SnapshotStore(Protocol):
    """The Session_Store reads :func:`build_snapshot` needs."""

    def get_latest_message(
        self, user_id: str, session_id: str
    ) -> WorkflowBuilderMessage | None:
        """Return the newest user or assistant row."""
        ...

    def get_latest_revisions(self, user_id: str, session_id: str) -> LatestRevisions:
        """Return the newest revision of each kind."""
        ...


class TurnStore(InputStore, Protocol):
    """The Session_Store calls the Turn_Runner makes while a Turn runs.

    It includes the reads and the summary write of :class:`InputStore`.
    """

    def finalize_assistant(  # noqa: PLR0913 - mirrors BuilderStore.finalize_assistant
        self,
        user_id: str,
        turn_id: str,
        *,
        status: str,
        outcome: str | None = None,
        stop_reason: str | None = None,
        error_code: str | None = None,
        content: str = "",
        thinking: str | None = None,
        steps: list[dict[str, Any]] | None = None,
        usage: dict[str, Any] | None = None,
        adherence: dict[str, Any] | None = None,
        revision: int | None = None,
        skill_hash: str | None = None,
        prompt_version: str | None = None,
        ended_at: datetime | None = None,
    ) -> WorkflowBuilderMessage | None:
        """Write the final state of the running assistant row."""
        ...

    def set_clarify_count(self, user_id: str, session_id: str, count: int) -> None:
        """Store ``clarify_turns_without_draft``."""
        ...

    def insert_tool_row(  # noqa: PLR0913 - mirrors BuilderStore.insert_tool_row
        self,
        user_id: str,
        session_id: str,
        turn_id: str,
        *,
        status: str,
        content: str,
        tool: dict[str, Any],
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
    ) -> WorkflowBuilderMessage:
        """Store one finished tool call."""
        ...

    def insert_revision(  # noqa: PLR0913 - mirrors BuilderStore.insert_revision
        self,
        user_id: str,
        session_id: str,
        *,
        kind: str,
        manifest: dict[str, Any],
        manifest_hash: str,
        target_trust: str | None = None,
        change_summary: dict[str, Any] | None = None,
        launch_needs: list[dict[str, Any]] | None = None,
        source_turn_id: str | None = None,
        source_file: str | None = None,
    ) -> WorkflowBuilderDraft:
        """Store a revision."""
        ...


#: Opens a store for one blocking call. A worker thread must not share a
#: SQLAlchemy session with the event loop, so each call opens its own.
type StoreScope = Callable[[], AbstractContextManager[TurnStore]]


@contextmanager
def open_store() -> Iterator[TurnStore]:
    """Open a Session_Store on its own database session and close it afterwards."""
    db = SessionLocal()
    try:
        yield BuilderStore(db)
    finally:
        db.close()


# --- Turn port adapter ----------------------------------------------------------------


class TurnRunner:
    """The live Turn as the agent layer's middleware and tools see it.

    Implements :class:`~app.agents.workflow_builder.ports.TurnPort`. Methods that
    only change in-memory state are synchronous. Publishing is asynchronous in
    the port but does not suspend: assigning ``seq`` and handing the event to the
    bus happen in one synchronous block.

    Args:
        turn: The live Turn this runner serves.
        canvas_state: The Canvas state the user's message was sent with.
        limits: The Turn's limits, read from settings when the Turn started.
        bus: The Session event bus. Defaults to :func:`get_event_bus`.
        store_scope: Opens a store for one blocking call. Defaults to
            :func:`open_store`.
    """

    def __init__(
        self,
        turn: LiveTurn,
        *,
        canvas_state: dict[str, Any] | None,
        limits: TurnLimits,
        bus: SessionEventBus | None = None,
        store_scope: StoreScope | None = None,
    ) -> None:
        self._turn = turn
        self._canvas_state = canvas_state
        self._limits = limits
        self._bus = bus if bus is not None else get_event_bus()
        self._store_scope: StoreScope = (
            store_scope if store_scope is not None else open_store
        )
        self._log = turn_logger(turn.session_id, turn.turn_id, name=_logger_name)

    # --- Read properties (TurnPort) -------------------------------------------------

    @property
    def live(self) -> LiveTurn:
        """The in-process state of the Turn."""
        return self._turn

    @property
    def turn_id(self) -> str:
        """The id of the Turn, equal to its assistant message id."""
        return self._turn.turn_id

    @property
    def stopping(self) -> bool:
        """True once the Turn has a stop reason."""
        return self._turn.stopping

    @property
    def canvas_state(self) -> dict[str, Any] | None:
        """The Canvas state the user's message was sent with, if any."""
        return self._canvas_state

    @property
    def limits(self) -> TurnLimits:
        """The limits that apply to this Turn."""
        return self._limits

    @property
    def accepted_revision(self) -> int | None:
        """The revision number this Turn already accepted, or ``None``."""
        return self._turn.accepted_revision

    # --- Events ---------------------------------------------------------------------

    @property
    def store_scope(self) -> StoreScope:
        """Opens a store for one blocking call."""
        return self._store_scope

    async def publish(self, event: BuilderEvent) -> None:
        """Stamp ``event`` with the Turn's next ``seq`` and publish it.

        ``turn_id`` and ``seq`` of a Turn-scoped event (and of an ``error`` event
        that has a ``turn_id``) are replaced; the caller passes any valid
        placeholder. Other events go out unchanged.
        """
        self._emit(event)

    def emit(self, event: BuilderEvent) -> None:
        """Synchronous :meth:`publish`, for timer callbacks that cannot await."""
        self._emit(event)

    def _emit(self, event: BuilderEvent) -> None:
        """Stamp, track and publish ``event`` in one synchronous block."""
        stamped = self._stamp(event)
        self._track(stamped)
        self._bus.publish(self._turn.session_id, stamped)

    def _stamp(self, event: BuilderEvent) -> BuilderEvent:
        """Return ``event`` with this Turn's id and the next ``seq`` set."""
        if isinstance(event, TurnScoped):
            self._turn.seq += 1
            return event.model_copy(
                update={"turn_id": self._turn.turn_id, "seq": self._turn.seq}
            )
        if isinstance(event, ErrorEvent) and event.turn_id is not None:
            self._turn.seq += 1
            return event.model_copy(
                update={"turn_id": self._turn.turn_id, "seq": self._turn.seq}
            )
        return event

    def _track(self, event: BuilderEvent) -> None:
        """Keep the live stage, activity and checks the snapshot reads (Req 40.6)."""
        turn = self._turn
        match event:
            case StageChanged():
                turn.set_stage(event.stage)
            case Thinking():
                add_thinking_step(turn.steps, event.text)
            case ToolStartedEvent():
                add_tool_step(turn.steps, event.call_id)
                turn.activity.append(
                    ToolActivity(
                        call_id=event.call_id,
                        tool=event.tool,
                        kind=event.kind,
                        label=event.label,
                        status="running",
                        command=event.command,
                    )
                )
            case ToolFinished():
                self._finish_activity(event)
            case CheckResultEvent():
                check = CheckResult(
                    source=event.source,
                    verdict=event.verdict,
                    errors=event.errors,
                    warnings=event.warnings,
                    attempt=event.attempt,
                    attempts_left=event.attempts_left,
                )
                turn.checks.append(check)
                turn.steps.append(CheckStep(check=check))
            case _:
                pass

    def _finish_activity(self, event: ToolFinished) -> None:
        """Mark the activity entry of ``event.call_id`` as finished."""
        activity = self._turn.activity
        for index, entry in enumerate(activity):
            if entry.call_id == event.call_id:
                activity[index] = entry.model_copy(
                    update={
                        "status": event.status,
                        "duration_ms": event.duration_ms,
                        "summary": event.summary,
                    }
                )
                return

    async def signal_stage(self, signal: Signal) -> None:
        """Feed ``signal`` to ``derive_stage`` and publish ``stage`` on a change."""
        new_stage = derive_stage(signal, self._turn.stage)
        if new_stage is None:
            return
        self._emit(
            StageChanged(
                ts=_now(),
                turn_id=self._turn.turn_id,
                seq=1,
                stage=new_stage,
                label=label_for(new_stage),
            )
        )

    # --- Stop and counters ----------------------------------------------------------

    def stop(self, reason: StopReason) -> None:
        """Stop the Turn. The first reason wins; later calls change nothing."""
        self._turn.stop(reason)

    def count_tool_call(self) -> int:
        """Count one tool call and return how many the Turn has made so far."""
        self._turn.tool_calls += 1
        return self._turn.tool_calls

    def record_workflow_write(self, path: str) -> None:
        """Remember a successful write of a ``/workflows/*.workflow.json`` file."""
        self._turn.changed_workflow_files[path] = time.monotonic()

    def report_gate_rejection(self) -> int:
        """Count one gate rejection and return how many the Turn has had so far."""
        turn = self._turn
        turn.gate_rejections += 1
        emit_gate_rejection(
            session_id=turn.session_id,
            turn_id=turn.turn_id,
            rejection_count=turn.gate_rejections,
        )
        return turn.gate_rejections

    # --- Stored rows ----------------------------------------------------------------

    async def record_tool_call(self, finished: FinishedToolCall) -> None:
        """Keep a finished tool call and store it as a tool row (Req 24.5, 36.13).

        The in-memory activity and the adherence input are updated first, so the
        snapshot and the adherence record are right even if the write fails. The
        row is written in ``asyncio.to_thread``, with the result cut by
        :func:`truncate_result` to at most 4,000 characters.
        """
        self._replace_activity(finished.activity)
        self._turn.finished_calls.append(finished.call)
        await asyncio.to_thread(self._store_tool_row, finished)

    def _replace_activity(self, activity: ToolActivity) -> None:
        """Put the finished ``activity`` in place of its running entry."""
        entries = self._turn.activity
        for index, entry in enumerate(entries):
            if entry.call_id == activity.call_id:
                entries[index] = activity
                return
        entries.append(activity)

    def _store_tool_row(self, finished: FinishedToolCall) -> None:
        """Insert the tool row. Blocking; runs in a worker thread."""
        turn = self._turn
        activity = finished.activity
        status = activity.status if activity.status in _TOOL_ROW_STATUSES else "error"
        ended_at = datetime.now(UTC)
        started_at = ended_at - timedelta(milliseconds=activity.duration_ms or 0)
        tool: dict[str, Any] = {
            "call_id": activity.call_id,
            "tool": activity.tool,
            "kind": activity.kind,
            "label": activity.label,
            "command": activity.command,
            "exit_code": activity.exit_code,
            "duration_ms": activity.duration_ms,
            "summary": activity.summary,
        }
        with self._store_scope() as store:
            store.insert_tool_row(
                turn.user_id,
                turn.session_id,
                turn.turn_id,
                status=status,
                content=truncate_result(finished.result),
                tool=tool,
                started_at=started_at,
                ended_at=ended_at,
            )

    async def accept_draft(self, draft: AcceptedDraft) -> int:
        """Store ``draft`` as an accepted revision and return its number.

        A cancel that arrives during the write does not lose the result: the
        write is waited for, the Turn records the revision, and the cancel then
        goes on. A draft accepted before a cancel stays (Req 30.4).
        """
        write = asyncio.ensure_future(asyncio.to_thread(self._store_revision, draft))
        try:
            row = await asyncio.shield(write)
        except asyncio.CancelledError:
            await self._settle_revision(write)
            raise
        revision = int(row.revision)  # type: ignore[arg-type]
        self._turn.accepted_revision = revision
        self._turn.accepted_manifest_hash = str(row.manifest_hash)
        return revision

    async def _settle_revision(
        self, write: asyncio.Future[WorkflowBuilderDraft]
    ) -> None:
        """Wait for a revision write whose caller was cancelled and record it."""
        try:
            row = await write
        except Exception:  # noqa: BLE001 - nothing was stored; the cancel goes on
            self._log.warning("accepted revision could not be stored", exc_info=True)
            return
        self._turn.accepted_revision = int(row.revision)  # type: ignore[arg-type]
        self._turn.accepted_manifest_hash = str(row.manifest_hash)

    def _store_revision(self, draft: AcceptedDraft) -> WorkflowBuilderDraft:
        """Insert the accepted revision. Blocking; runs in a worker thread."""
        turn = self._turn
        with self._store_scope() as store:
            return store.insert_revision(
                turn.user_id,
                turn.session_id,
                kind=DRAFT_KIND_ACCEPTED,
                manifest=draft.manifest,
                manifest_hash=canonical_hash(draft.manifest),
                target_trust=draft.trust,
                change_summary=draft.change_summary.model_dump(mode="json"),
                launch_needs=[
                    need.model_dump(mode="json") for need in draft.launch_needs
                ],
                source_turn_id=turn.turn_id,
                source_file=draft.source_file,
            )


# --- Snapshot -------------------------------------------------------------------------


def build_snapshot(session_id: str, *, user_id: str, store: SnapshotStore) -> Snapshot:
    """Build the first frame of a Session_Stream (Req 38.3, 40.6).

    The running Turn comes from the in-process :class:`LiveTurn`: stage, the
    activity and checks so far, and ``through_seq``, the ``seq`` of the last event
    the snapshot reflects. The latest message and revision ids come from the
    store. Pass this function (with its arguments bound) to
    :meth:`SessionEventBus.subscribe`. It does not await, so no event can be
    published between building the snapshot and registering the queue (G-14).

    A live Turn of another user is not shown: the state is ``idle``.

    Args:
        session_id: The Session the client watches.
        user_id: The caller. The route has already checked that the caller owns
            the Session.
        store: Reads the latest stored ids.
    """
    live = _LIVE_TURNS.get(session_id)
    running: RunningTurnSnapshot | None = None
    if live is not None and live.user_id == user_id:
        stage = live.stage or Stage.STARTING
        running = RunningTurnSnapshot(
            turn_id=live.turn_id,
            message_id=live.user_message_id,
            stage=stage,
            label=label_for(stage),
            started_at=live.started_at_wall,
            through_seq=live.seq,
            activity=list(live.activity),
            checks=list(live.checks),
        )
    latest_message = store.get_latest_message(user_id, session_id)
    revisions = store.get_latest_revisions(user_id, session_id)
    numbered = [
        int(row.revision)  # type: ignore[arg-type]
        for row in (revisions.seed, revisions.accepted, revisions.undo)
        if row is not None
    ]
    return Snapshot(
        ts=_now(),
        state="running" if running is not None else "idle",
        running_turn=running,
        latest_message_id=str(latest_message.id)
        if latest_message is not None
        else None,
        latest_revision=max(numbered) if numbered else None,
        latest_unproposed_revision=(
            int(revisions.unproposed.revision)  # type: ignore[arg-type]
            if revisions.unproposed is not None
            else None
        ),
    )


def _now() -> datetime:
    """Return the current time in UTC."""
    return datetime.now(UTC)


# --- Run and finalize a Turn (task 15.4, design 3.1.4) ---------------------------------

_SAVE_CHECK_LABEL: Final = "workflow builder draft"
_UNKNOWN_SKILL_HASH: Final = "unknown"
_RECURSION_MARKER: Final = "recursion limit"
_WORKFLOWS_PREFIX: Final = "/workflows/"
_CAP_STOPS: Final = frozenset({"time", "tool_calls"})
_CHECK_LABELS: Final = {
    "skill_validator": "the builder validator",
    "platform_dry_run": "the platform dry run",
    "server_gate": "the platform check",
}


@dataclass(frozen=True, slots=True)
class TurnRequest:
    """What the user sent with the message that started the Turn.

    Attributes:
        content: The user's text.
        canvas_state: The Canvas state sent with it, or ``None``.
    """

    content: str
    canvas_state: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class TurnDeps:
    """Collaborators of :func:`run_turn`. Every field has a production default.

    Attributes:
        bus: The Session event bus. ``None`` uses :func:`get_event_bus`.
        store_scope: Opens a store for one blocking call. ``None`` uses
            :func:`open_store`.
        sandbox_factory: ``(user_id, session_id) -> BuilderSandbox``.
        gate: The Server_Gate. ``None`` builds a ``ServerGate`` for the tier.
        reads: The read-tool data source. ``None`` uses ``PlaceholderReadPort``
            (Q-18).
        summarizer: Writes the Transcript_Summary.
        chat_model: A ready chat model used instead of ``build_model`` (test seam).
        skills_root: The folder that holds the skill folder (test seam). ``None``
            uses ``app/agents/workflow_builder/skills``.
    """

    bus: SessionEventBus | None = None
    store_scope: StoreScope | None = None
    sandbox_factory: Callable[[str, str], BuilderSandbox] = BuilderSandbox
    gate: GatePort | None = None
    reads: BuilderReadPort | None = None
    summarizer: Summarizer = default_summarizer
    chat_model: BaseChatModel | None = None
    skills_root: Path | None = None


@dataclass(frozen=True, slots=True)
class _FatalError:
    """The error that failed a Turn: the generic triple the user sees."""

    code: str
    message: str
    retryable: bool


@dataclass(eq=False)
class TurnRunState:
    """What :func:`run_turn` collects for :func:`finalize_turn`.

    Attributes:
        reply: Text pieces streamed so far.
        thinking: Reasoning pieces streamed so far.
        final_output: The runner's final (sanitised) output, when it sent one.
        fatal: The error that failed the Turn, if any.
        sandbox: The session sandbox, once it is ready.
        skill_hash: The skill hash at the start of the Turn, if it could be read.
        skill_line_counts: Line counts of the skill files, for adherence.
        token_warned: The 80 % token warning was sent.
    """

    reply: list[str] = field(default_factory=list)
    thinking: list[str] = field(default_factory=list)
    final_output: str | None = None
    fatal: _FatalError | None = None
    sandbox: BuilderSandbox | None = None
    skill_hash: str | None = None
    skill_line_counts: Mapping[str, int] = field(default_factory=dict)
    token_warned: bool = False


def limits_from_settings() -> TurnLimits:
    """Read the Turn's limits from settings."""
    return TurnLimits(
        timeout_seconds=settings.BUILDER_TURN_TIMEOUT_SECONDS,
        max_tool_calls=settings.BUILDER_MAX_TOOL_CALLS_PER_TURN,
        max_gate_rejections=settings.BUILDER_MAX_GATE_REJECTIONS_PER_TURN,
        warning_fraction=settings.BUILDER_LIMIT_WARNING_FRACTION,
        token_budget=settings.BUILDER_TOKEN_BUDGET_PER_TURN,
    )


def status_for_stop(reason: StopReason | None, *, failed: bool = False) -> TurnStatus:
    """Map a stop reason to the one stored status (design 3.1.3, G-04, G-12).

    The tool-call cap, a token budget and the recursion limit end as
    ``timed_out`` [pending G-04]. The second gate rejection ends ``completed``
    with outcome ``unfinished`` [pending G-12].

    Args:
        reason: The Turn's stop reason, or ``None`` when the graph ended.
        failed: The graph ended with an error. Used only when ``reason`` is
            ``None``.
    """
    match reason:
        case None:
            return "failed" if failed else "completed"
        case "time" | "tool_calls" | "tokens" | "recursion":
            return "timed_out"
        case "gate_rejections":
            return "completed"
        case "cancelled" | "deleted":
            return "cancelled"
        case "shutdown" | "restart":
            return "interrupted"
        case "error":
            return "failed"


def _set_reason(turn: LiveTurn, reason: StopReason) -> None:
    """Record ``reason`` when the Turn has none. Does not cancel the task."""
    if turn.stop_reason is None:
        turn.stop_reason = reason


def _outcome_for(turn: LiveTurn, reason: StopReason | None) -> Outcome:
    """Return the outcome: the Turn's draft, an unfinished draft, or a reply."""
    if turn.accepted_revision is not None:
        return "draft"
    if reason == "gate_rejections":
        return "unfinished"
    return "reply"


def _skill_facts(skills_root: Path | None) -> tuple[str, Mapping[str, int]]:
    """Return the skill hash and the skill files' line counts, from disk. Blocking."""
    skill_dir = SKILL_DIR if skills_root is None else skills_root / BUILDER_SKILL_ID
    facts = read_skill_facts(skill_dir)
    return facts.skill_hash, facts.line_counts


def _prepare_sandbox(  # noqa: PLR0913 - one call per Turn, all inputs are named
    factory: Callable[[str, str], BuilderSandbox],
    scope: StoreScope,
    turn: LiveTurn,
    canvas_state: dict[str, Any] | None,
) -> BuilderSandbox:
    """Make the sandbox ready and write the Canvas_File. Blocking.

    A missing folder is rebuilt from the stored revisions (Req 20.12). The
    Canvas_File is written without touching ``/workflows/``.
    """
    sandbox = factory(turn.user_id, turn.session_id)
    log = turn_logger(turn.session_id, turn.turn_id, name=_logger_name)
    if sandbox.exists():
        sandbox.ensure()
    else:
        with scope() as store:
            revisions = store.get_latest_revisions(turn.user_id, turn.session_id)
            drafts = [
                row
                for row in (revisions.seed, revisions.accepted, revisions.undo)
                if row is not None
            ]
            latest = max(drafts, key=lambda row: int(row.revision)) if drafts else None  # type: ignore[arg-type]
            unproposed = revisions.unproposed
            if (
                unproposed is not None
                and latest is not None
                and int(unproposed.revision) <= int(latest.revision)  # type: ignore[arg-type]
            ):
                unproposed = None
            try:
                sandbox.rebuild(latest, unproposed)
            except SandboxPathError:
                log.warning("unproposed revision could not be restored", exc_info=True)
                sandbox.rebuild(latest, None)
    canvas = canvas_state if canvas_state is not None else {"steps": []}
    sandbox.path_for(CANVAS_FILE).write_text(
        json.dumps(canvas, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return sandbox


def _tool_running(turn: LiveTurn) -> bool:
    return any(entry.status == "running" for entry in turn.activity)


def _count(event: Mapping[str, Any], key: str) -> int:
    value = event.get(key, 0)
    return int(value) if isinstance(value, (int, float)) else 0


def _on_usage(runner: TurnRunner, run: TurnRunState, event: Mapping[str, Any]) -> None:
    """Add a ``usage`` event to the Turn's total and apply the token budget."""
    turn = runner.live
    before = turn.usage
    turn.usage = before.model_copy(
        update={
            "input": before.input + _count(event, "input_tokens"),
            "output": before.output + _count(event, "output_tokens"),
            "cache_read": before.cache_read + _count(event, "cache_read_tokens"),
            "cache_write": before.cache_write + _count(event, "cache_write_tokens"),
        }
    )
    budget = runner.limits.token_budget
    if budget is None:
        return
    used = turn.usage.input + turn.usage.output
    if used >= budget:
        turn.stop("tokens")
    elif not run.token_warned and used >= runner.limits.warning_fraction * budget:
        run.token_warned = True
        runner.emit(
            LimitWarning(
                ts=_now(),
                turn_id=turn.turn_id,
                seq=1,
                kind="tokens",
                used=used,
                limit=budget,
            )
        )


async def _on_error(
    runner: TurnRunner, run: TurnRunState, event: Mapping[str, Any]
) -> None:
    """Handle an ``error`` event: recursion text stops the Turn, else it fails."""
    turn = runner.live
    text = str(event.get("error", ""))
    if _RECURSION_MARKER in text.lower():
        turn.stop("recursion")
        return
    payload = map_exception(RuntimeError(text))
    run.fatal = _FatalError(payload.code, payload.message, payload.recoverable)
    await runner.publish(
        ErrorEvent(
            ts=_now(),
            turn_id=turn.turn_id,
            seq=1,
            code=payload.code,
            message=payload.message,
            retryable=payload.recoverable,
        )
    )


async def _on_runner_event(
    runner: TurnRunner, run: TurnRunState, event: Mapping[str, Any]
) -> None:
    """Translate one runner event (design 3.1.4).

    The runner's own ``tool_call`` and ``tool_result`` events are ignored: tool
    activity comes from the observer middleware (D-05).
    """
    turn = runner.live
    match event.get("type"):
        case "chunk":
            text = str(event.get("chunk", ""))
            if text:
                run.reply.append(text)
                await runner.signal_stage(TextDelta(tool_running=_tool_running(turn)))
                await runner.publish(
                    Text(ts=_now(), turn_id=turn.turn_id, seq=1, text=text)
                )
        case "thinking":
            text = str(event.get("thinking", ""))
            if text:
                run.thinking.append(text)
                await runner.signal_stage(
                    ThinkingDelta(tool_running=_tool_running(turn))
                )
                await runner.publish(
                    Thinking(ts=_now(), turn_id=turn.turn_id, seq=1, text=text)
                )
        case "usage":
            _on_usage(runner, run, event)
        case "error":
            await _on_error(runner, run, event)
        case "done":
            output = event.get("output")
            if isinstance(output, str) and output.strip():
                run.final_output = output
        case _:
            pass


def _warn_time(runner: TurnRunner) -> None:
    """Timer callback: send ``limit_warning`` for the time cap at 80 %."""
    turn = runner.live
    if turn.stopping:
        return
    runner.emit(
        LimitWarning(
            ts=_now(),
            turn_id=turn.turn_id,
            seq=1,
            kind="time",
            used=round(time.monotonic() - turn.started_at),
            limit=runner.limits.timeout_seconds,
        )
    )


def _build_gate(turn: LiveTurn, deps: TurnDeps) -> GatePort:
    if deps.gate is not None:
        return deps.gate
    return ServerGate(
        tier=turn.tier,
        max_trust=_saved_row_trust(turn.tier),  # type: ignore[arg-type]
        step_models=builder_models(turn.tier).step,
        label=_SAVE_CHECK_LABEL,
    )


def _script_metric_sink(
    turn: LiveTurn,
) -> Callable[[str, float, int | None, bool], None]:
    def sink(
        script: str, duration_seconds: float, exit_code: int | None, refused: bool
    ) -> None:
        emit_script_call(
            session_id=turn.session_id,
            turn_id=turn.turn_id,
            script=script,
            duration_seconds=duration_seconds,
            exit_code=exit_code,
            refused=refused,
        )

    return sink


async def _execute(
    runner: TurnRunner, run: TurnRunState, request: TurnRequest, deps: TurnDeps
) -> None:
    """Start the Turn, build its input and stream the agent (design 3.1.4)."""
    turn = runner.live
    log = turn_logger(turn.session_id, turn.turn_id, name=_logger_name)
    try:
        run.skill_hash, run.skill_line_counts = await asyncio.to_thread(
            _skill_facts, deps.skills_root
        )
    except OSError:
        log.warning("skill facts could not be read", exc_info=True)
    await runner.publish(
        TurnStarted(
            ts=_now(),
            turn_id=turn.turn_id,
            seq=1,
            message_id=turn.user_message_id,
            model_id=turn.model_id,
            effort=turn.effort,
            skill_hash=run.skill_hash or _UNKNOWN_SKILL_HASH,
        )
    )
    await runner.signal_stage(TurnAccepted())
    run.sandbox = await asyncio.to_thread(
        _prepare_sandbox,
        deps.sandbox_factory,
        runner.store_scope,
        turn,
        request.canvas_state,
    )
    agent_input = await build_agent_input(
        InputRequest(
            user_id=turn.user_id,
            session_id=turn.session_id,
            turn_id=turn.turn_id,
            user_message_id=turn.user_message_id,
            model_id=turn.model_id,
            tier=turn.tier,
            content=request.content,
            canvas_state=request.canvas_state,
        ),
        store_scope=runner.store_scope,
        summarizer=deps.summarizer,
    )
    if agent_input.summary_usage is not None:
        turn.usage = turn.usage.model_copy(
            update={"summary": add_usage(turn.usage.summary, agent_input.summary_usage)}
        )
    agent_runner = build_builder_runner(
        BuilderTurnInputs(
            session_id=turn.session_id,
            turn_id=turn.turn_id,
            user_id=turn.user_id,
            tier=turn.tier,
            model_id=turn.model_id,
            effort=turn.effort,
            message=agent_input.message,
            chat_model=deps.chat_model,
        ),
        run.sandbox,
        BuilderPorts(
            turn=runner,
            gate=_build_gate(turn, deps),
            reads=deps.reads if deps.reads is not None else PlaceholderReadPort(),
            elapsed_seconds=lambda: time.monotonic() - turn.started_at,
            on_script_metric=_script_metric_sink(turn),
            stopped_by_turn_cap=lambda: turn.stop_reason in _CAP_STOPS,
        ),
        skills_root=deps.skills_root,
    )
    async with aclosing(
        agent_runner.astream_events(agent_input.message, history=agent_input.history)
    ) as events:
        async for event in events:
            await _on_runner_event(runner, run, event)


async def _finalize_shielded(
    runner: TurnRunner, run: TurnRunState, status: TurnStatus
) -> None:
    """Run :func:`finalize_turn` under ``asyncio.shield`` and wait for it to end.

    A stop that a tool or the event handler made from inside the Turn's own task
    leaves a cancel pending, and a shutdown can cancel the task again. Either would
    otherwise end this wait early. The Turn's rows must be stored first, so the
    cancel is cleared (``uncancel``) and the wait goes on.
    """
    finalizing = asyncio.ensure_future(finalize_turn(runner, run, status))
    current = asyncio.current_task()
    while not finalizing.done():
        try:
            await asyncio.shield(finalizing)
        except asyncio.CancelledError:
            if current is not None:
                current.uncancel()
    if not finalizing.cancelled():
        finalizing.exception()  # finalize_turn handles its own errors; mark retrieved


async def run_turn(
    turn: LiveTurn, request: TurnRequest, deps: TurnDeps | None = None
) -> None:
    """Run one Turn from ``turn_started`` to ``turn_completed`` (design 3.1.4).

    Starts the time cap and the 80 % warning from settings (the cap counts from
    here, after admission, Req 28.5), publishes ``turn_started`` and the
    ``starting`` stage, readies the sandbox, builds the agent input, and streams
    the agent. Whatever happens, :func:`finalize_turn` runs under
    ``asyncio.shield`` and stores one terminal status. Nothing stops a Turn at
    180 s.

    Args:
        turn: The live Turn, already registered by admission.
        request: The user's text and Canvas state.
        deps: Collaborators; the defaults are the production ones.
    """
    resolved = deps if deps is not None else TurnDeps()
    limits = limits_from_settings()
    runner = TurnRunner(
        turn,
        canvas_state=request.canvas_state,
        limits=limits,
        bus=resolved.bus,
        store_scope=resolved.store_scope,
    )
    run = TurnRunState()
    log = turn_logger(turn.session_id, turn.turn_id, name=_logger_name)
    loop = asyncio.get_running_loop()
    if turn.task is None:
        # Called outside a task that admission attached: a stop must still end us.
        turn.task = asyncio.current_task()
    turn.started_at = time.monotonic()
    cap = loop.call_later(limits.timeout_seconds, turn.stop, "time")
    warning = loop.call_later(
        limits.warning_fraction * limits.timeout_seconds, _warn_time, runner
    )
    status: TurnStatus = "failed"
    try:
        await _execute(runner, run, request, resolved)
        status = status_for_stop(turn.stop_reason, failed=run.fatal is not None)
    except asyncio.CancelledError:
        _set_reason(turn, "cancelled")
        status = status_for_stop(turn.stop_reason)
    except Exception as exc:  # noqa: BLE001 - any failure ends the Turn as failed
        log.error("builder turn failed (%s)", type(exc).__name__, exc_info=True)
        payload = map_exception(exc)
        run.fatal = _FatalError(payload.code, payload.message, payload.recoverable)
        runner.emit(
            ErrorEvent(
                ts=_now(),
                turn_id=turn.turn_id,
                seq=1,
                code=payload.code,
                message=payload.message,
                retryable=payload.recoverable,
            )
        )
        status = status_for_stop(turn.stop_reason, failed=True)
    finally:
        cap.cancel()
        warning.cancel()
        # No await since the status was computed, so a stop that arrives later
        # cannot change the stored status (see LiveTurn.stop).
        turn.finalizing = True
        await _finalize_shielded(runner, run, status)


# --- Finalize -------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Final:
    """The values :func:`finalize_turn` stores for a Turn."""

    status: TurnStatus
    outcome: Outcome
    stop_reason: StopReason | None
    content: str
    thinking: str | None
    steps: list[dict[str, Any]] | None
    usage: dict[str, Any]
    adherence: dict[str, Any] | None
    error_code: str | None
    skill_hash: str | None


def _gate_notice(turn: LiveTurn) -> str:
    """Explain a Turn that ended on its last gate rejection [pending G-12]."""
    failed = []
    for check in turn.checks:
        label = _CHECK_LABELS.get(check.source, check.source)
        if check.verdict == "invalid" and label not in failed:
            failed.append(label)
    where = f" It failed {', '.join(failed)}." if failed else ""
    return (
        "I could not get this draft through the platform checks after "
        f"{turn.gate_rejections} tries.{where} The work so far is kept. "
        "Say continue and I will pick it up from the saved draft."
    )


def _reply_content(turn: LiveTurn, run: TurnRunState, reason: StopReason | None) -> str:
    text = run.final_output if run.final_output is not None else "".join(run.reply)
    if reason == "gate_rejections":
        text = f"{text.rstrip()}\n\n{_gate_notice(turn)}".strip()
    return text


def _adherence_record(turn: LiveTurn, run: TurnRunState) -> AdherenceRecord:
    return adherence_module.record(
        turn.finished_calls,
        run.skill_line_counts,
        skill_id=adherence_module.DEFAULT_SKILL_ID,
    )


def _unproposed_candidate(
    turn: LiveTurn, sandbox: BuilderSandbox | None
) -> tuple[str, dict[str, Any]] | None:
    """Return the last manifest the agent wrote that no accepted draft holds.

    The newest ``/workflows/*.workflow.json`` written in the Turn is read back
    from the sandbox. It is skipped when it is not a JSON object or when it is
    the manifest the Turn already accepted.
    """
    if sandbox is None or not turn.changed_workflow_files:
        return None
    changed = turn.changed_workflow_files
    path = "/" + max(changed, key=lambda key: changed[key]).lstrip("/")
    if not path.startswith(_WORKFLOWS_PREFIX):
        return None
    try:
        manifest = json.loads(sandbox.path_for(path).read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            return None
        if (
            turn.accepted_manifest_hash is not None
            and canonical_hash(manifest) == turn.accepted_manifest_hash
        ):
            return None
    except (OSError, ValueError, TypeError):
        return None
    return path, manifest


def _persist_turn(
    scope: StoreScope, turn: LiveTurn, run: TurnRunState, final: _Final
) -> None:
    """Write the Turn's final rows. Blocking; runs in a worker thread.

    Each step has its own error handling, so a failed unproposed-revision write
    does not stop the assistant row from being finalised.
    """
    log = turn_logger(turn.session_id, turn.turn_id, name=_logger_name)
    with scope() as store:
        if final.status != "completed" or final.outcome == "unfinished":
            candidate = _unproposed_candidate(turn, run.sandbox)
            if candidate is not None:
                path, manifest = candidate
                try:
                    store.insert_revision(
                        turn.user_id,
                        turn.session_id,
                        kind=DRAFT_KIND_UNPROPOSED,
                        manifest=manifest,
                        manifest_hash=canonical_hash(manifest),
                        source_turn_id=turn.turn_id,
                        source_file=path,
                    )
                except Exception:  # noqa: BLE001 - the row must still be finalised
                    log.warning("unproposed revision not stored", exc_info=True)
        try:
            store.finalize_assistant(
                turn.user_id,
                turn.turn_id,
                status=final.status,
                outcome=final.outcome,
                stop_reason=final.stop_reason,
                error_code=final.error_code,
                content=final.content,
                thinking=final.thinking,
                steps=final.steps,
                usage=final.usage,
                adherence=final.adherence,
                revision=turn.accepted_revision,
                skill_hash=final.skill_hash,
                prompt_version=PROMPT_VERSION,
            )
        except Exception:  # noqa: BLE001 - the startup sweep catches the leftover row
            log.error("assistant row not finalised", exc_info=True)
            return
        try:
            _update_clarify_count(store, turn, final)
        except Exception:  # noqa: BLE001 - the count is advisory
            log.warning("clarify count not updated", exc_info=True)


def _update_clarify_count(store: TurnStore, turn: LiveTurn, final: _Final) -> None:
    """Add one to the clarify count for a reply turn before the first draft."""
    session = store.get_session(turn.user_id, turn.session_id)
    if session is None:
        return
    before_first_accepted = (
        session.first_accepted_revision is None and turn.accepted_revision is None
    )
    if counts_toward_clarify(final.status, final.outcome, before_first_accepted):
        store.set_clarify_count(
            turn.user_id,
            turn.session_id,
            int(session.clarify_turns_without_draft) + 1,  # type: ignore[arg-type]
        )


async def finalize_turn(
    runner: TurnRunner, run: TurnRunState, status: TurnStatus
) -> None:
    """Store the Turn's end state, publish ``turn_completed`` and clean up.

    Stores one terminal status from the stop reason (tool-call, token and
    recursion stops as ``timed_out`` [pending G-04]), the unproposed revision
    when the Turn wrote a manifest that no accepted draft holds (also after the
    second gate rejection, outcome ``unfinished`` [pending G-12]), the clarify
    count, the adherence record, the usage with the summary tokens, the skill
    hash and ``prompt_version``. Writes run in ``asyncio.to_thread``. The
    registries are cleaned up last, even when a write fails.

    A deleted session has no rows left, so a Turn stopped with ``deleted`` only
    cleans up.

    Args:
        runner: The Turn's runner.
        run: What the run collected.
        status: The status ``run_turn`` derived from the stop reason.
    """
    turn = runner.live
    log = turn_logger(turn.session_id, turn.turn_id, name=_logger_name)
    try:
        if run.fatal is not None:
            _set_reason(turn, "error")
        reason = turn.stop_reason
        if reason == "deleted":
            return
        outcome = _outcome_for(turn, reason)
        adherence_record = _adherence_record(turn, run)
        final = _Final(
            status=status,
            outcome=outcome,
            stop_reason=reason,
            content=_reply_content(turn, run, reason),
            thinking="".join(run.thinking) or None,
            steps=stored_steps(turn.steps),
            usage=turn.usage.model_dump(mode="json"),
            adherence=adherence_record.as_dict(),
            error_code=run.fatal.code if run.fatal is not None else None,
            skill_hash=run.skill_hash,
        )
        try:
            await asyncio.to_thread(_persist_turn, runner.store_scope, turn, run, final)
        except Exception:  # noqa: BLE001 - still tell the client the Turn ended
            log.error("turn rows not stored", exc_info=True)
        emit_turn_metrics(
            session_id=turn.session_id,
            turn_id=turn.turn_id,
            status=status,
            latency_seconds=time.monotonic() - turn.started_at,
            stage_seconds={str(k): v for k, v in turn.stage_durations().items()},
            usage=turn.usage,
            adherence=adherence_record,
            skill_hash=run.skill_hash,
            stop_reason=reason,
            model_id=turn.model_id,
            prompt_version=PROMPT_VERSION,
        )
        runner.emit(
            TurnCompleted(
                ts=_now(),
                turn_id=turn.turn_id,
                seq=1,
                status=status,  # type: ignore[arg-type]
                outcome=outcome,
                stop_reason=reason,
                message_id=turn.turn_id,
                revision=turn.accepted_revision,
                usage=turn.usage,
            )
        )
    finally:
        release_live_turn(turn)


# --- Cancel and stop (task 15.5, design 3.1.5 and 3.1.6) --------------------------------

CancelState = Literal["cancelling", "not_running"]


def cancel_turn(session_id: str, turn_id: str) -> CancelState:
    """Stop the running Turn ``turn_id`` of ``session_id`` at the user's request.

    The caller has already checked that the user owns the Session (Req 2.7). The
    Turn stops with reason ``cancelled``. The agent stops at its next await, the
    script runner kills a running subprocess, and a stopping Turn applies no
    draft (Req 30.2, 30.4). A draft accepted before this call stays, and
    :func:`finalize_turn` stores ``cancelled`` with outcome ``draft`` (Req 30.5).

    Args:
        session_id: The Session the Turn belongs to.
        turn_id: The Turn to stop. It is also the assistant message id.

    Returns:
        ``cancelling`` when that Turn is live and not yet storing its end. Returns
        ``not_running`` otherwise, so a double click or a late cancel from another
        tab is harmless [pending G-35].
    """
    live = _LIVE_TURNS.get(session_id)
    if live is None or live.turn_id != turn_id or live.finalizing:
        return "not_running"
    live.stop("cancelled")
    return "cancelling"


def stop_session_turn(session_id: str, reason: StopReason = "deleted") -> bool:
    """Stop the live Turn of ``session_id`` for ``reason``, if it has one.

    The route calls this when the user deletes the Session, before the Session's
    rows are removed (Req 31.3). With ``deleted`` the Turn stores nothing and
    publishes no ``turn_completed``, because its rows are going away.

    Returns:
        True when the Session had a live Turn. A Turn already storing its end is
        left to finish, so a True result does not always mean it stopped.
    """
    live = _LIVE_TURNS.get(session_id)
    if live is None:
        return False
    live.stop(reason)
    return True


def stop_user_turns(user_id: str) -> int:
    """Stop every live Turn of ``user_id`` with reason ``deleted``.

    The admin route calls this before it deletes the user's account (Req 31.7).
    The rows are removed with the account, so nothing is stored for these Turns.

    Returns:
        The number of live Turns the user had.
    """
    found = [live for live in _LIVE_TURNS.values() if live.user_id == user_id]
    for live in found:
        live.stop("deleted")
    return len(found)


async def stop_all(reason: StopReason = "shutdown", *, persist_seconds: float) -> None:
    """Stop every live Turn for a server shutdown and wait for their rows.

    Each live Turn stops with ``reason`` (Req 22.1). Its task is cancelled, and
    :func:`finalize_turn` stores the end state (``interrupted`` for a shutdown).
    This waits up to ``persist_seconds`` for those writes. A Turn still storing
    after the window is left to the startup sweep (Req 22.2). A Turn whose task
    never started never reaches :func:`finalize_turn`, so its row is also left to
    the sweep.

    This does not close the Session streams. The caller does that after this
    returns (design 3.1.6).

    Args:
        reason: The stop reason. A shutdown uses ``shutdown``.
        persist_seconds: How long to wait for the Turns to store their end.
    """
    for live in list(_LIVE_TURNS.values()):
        live.stop(reason)
    pending = {task for task in _TURN_TASKS if not task.done()}
    if not pending:
        return
    _, still_running = await asyncio.wait(pending, timeout=persist_seconds)
    if still_running:
        logging.getLogger(_logger_name).warning(
            "%d builder turn(s) had not stored their end within %.1f s",
            len(still_running),
            persist_seconds,
        )
