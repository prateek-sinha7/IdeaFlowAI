"""Property test for the Session_Stream revocation cadence (task 16.7).

# Feature: ai-workflow-builder, Property 25: Revocation is checked on cadence

For any timeline of events and idle periods on an open stream, a revocation check
runs after every fifth event and no more than 30 seconds after the previous check,
and a failed check is followed by ``session_revoked`` and the end of the stream.

**Validates: Requirements 40.7, 40.8**

The system under test is ``stream.iter_session_frames``. Time is simulated.
``asyncio.wait_for`` is replaced, for one drive, by a fake with the same signature.
The fake decides between the next scheduled delivery and the timeout, then advances
a fake clock instead of waiting, so an idle hour takes no real time. The revocation
check is a stub that records the fake time and the number of events delivered when
it runs. Nothing touches a database, the network or a model.

The oracle is the requirement text. It does not read the generator's counter or
its timeout branch:

* the checks that follow an event must fall exactly after events 5, 10, 15 and so
  on, with no check after any other event;
* the gaps between the stream opening, each check and the stream closing must not
  exceed 30 seconds;
* a failed check must be the last frame, after which the stream closes and the
  subscription is released.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Coroutine, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st

from app.agents.workflow_builder.events import BuilderEvent, Snapshot, Text
from app.api.workflow_builder import stream
from app.api.workflow_builder.bus import SessionEventBus, SessionQueue

_START = datetime(2030, 1, 1, tzinfo=UTC)
_SESSION = "s-1"
_TURN = "t-1"
_REASON = "credential_revoked"

#: Requirement 40.7: a check after every fifth event.
_EVERY_N_EVENTS = 5
#: Requirement 40.7: a check at least every 30 seconds.
_MAX_GAP_SECONDS = 30

Trigger = Literal["event", "timeout"]

# Idle gaps between events, in seconds. The mix covers dense bursts, gaps that sit
# on the 30 s boundary and long silences.
_GAP_SECONDS = st.one_of(
    st.integers(min_value=0, max_value=5),
    st.integers(min_value=20, max_value=40),
    st.integers(min_value=0, max_value=120),
)
_GAPS = st.lists(_GAP_SECONDS, max_size=30)
_FAIL_ON_CALL = st.one_of(st.none(), st.integers(min_value=0, max_value=40))


@dataclass
class _Clock:
    """Simulated seconds since the stream opened."""

    seconds: float = 0.0

    def now(self) -> datetime:
        """Return the simulated wall-clock time (event and revocation timestamps)."""
        return _START + timedelta(seconds=self.seconds)

    def monotonic(self) -> float:
        """Return the simulated monotonic seconds (the revocation cadence)."""
        return self.seconds


@dataclass(frozen=True)
class _Check:
    """One revocation check: when it ran, what woke the stream, and the event count."""

    at: float
    trigger: Trigger
    delivered: int


@dataclass(frozen=True)
class _Run:
    """What one drive of the generator produced."""

    frames: list[dict[str, Any]]
    checks: list[_Check]
    delivered: int
    ended_at: float
    unsubscribed: int


class _TimedQueue(asyncio.Queue[BuilderEvent | None]):
    """A client queue that releases its scripted deliveries in order.

    ``schedule`` holds ``(due_seconds, event)`` pairs in order and ends with a
    ``None`` close sentinel. The queue never waits by itself. ``_fake_wait_for``
    reads the next due time and decides whether that delivery beats the timeout the
    stream passed in. Its own ``get`` is never awaited.
    """

    def __init__(self, schedule: list[tuple[float, BuilderEvent | None]]) -> None:
        super().__init__()
        self._schedule = schedule
        self._position = 0
        self.delivered = 0
        self.last_trigger: Trigger = "event"

    def next_due(self) -> float:
        """Return the due time of the next scheduled item."""
        return self._schedule[self._position][0]

    def take_next(self) -> BuilderEvent | None:
        """Consume the next scheduled item and count it when it is an event."""
        _, event = self._schedule[self._position]
        self._position += 1
        if event is not None:
            self.delivered += 1
        return event


def _fake_wait_for(
    clock: _Clock, queue: _TimedQueue
) -> Callable[
    [Coroutine[Any, Any, BuilderEvent | None], float],
    Coroutine[Any, Any, BuilderEvent | None],
]:
    """Build a stand-in for ``asyncio.wait_for`` that runs on the fake clock.

    The next scheduled item is delivered only when it is due strictly before the
    timeout. A deadline tie goes to the timeout, so the revocation check runs first
    at exactly the interval. Otherwise the clock moves forward by the timeout and
    ``TimeoutError`` is raised. The awaitable from ``queue.get()`` is closed unused
    in both cases, because the fake never runs it.
    """

    async def wait_for(
        awaitable: Coroutine[Any, Any, BuilderEvent | None], timeout: float
    ) -> BuilderEvent | None:
        awaitable.close()
        if queue.next_due() - clock.seconds < timeout:
            clock.seconds = max(clock.seconds, queue.next_due())
            queue.last_trigger = "event"
            return queue.take_next()
        clock.seconds += timeout
        queue.last_trigger = "timeout"
        raise TimeoutError

    return wait_for


class _TimedBus(SessionEventBus):
    """A bus that hands the generator one scripted queue and counts unsubscribes."""

    def __init__(self, queue: _TimedQueue) -> None:
        super().__init__(queue_maxsize=0)
        self._queue = queue
        self.unsubscribed = 0

    def subscribe(
        self, session_id: str, snapshot_fn: Callable[[], Snapshot]
    ) -> tuple[SessionQueue, Snapshot]:
        """Return the scripted queue and the snapshot, with no real registration."""
        return self._queue, snapshot_fn()

    def unsubscribe(self, session_id: str, q: SessionQueue) -> None:
        """Count the release of the subscription."""
        self.unsubscribed += 1


class _StubCheck:
    """A revocation check that records each call and fails on one chosen call."""

    def __init__(
        self, clock: _Clock, queue: _TimedQueue, fail_on_call: int | None
    ) -> None:
        self._clock = clock
        self._queue = queue
        self._fail_on_call = fail_on_call
        self.checks: list[_Check] = []

    async def __call__(self) -> str | None:
        """Record the call; return a reason only for the chosen failing call."""
        index = len(self.checks)
        self.checks.append(
            _Check(
                at=self._clock.seconds,
                trigger=self._queue.last_trigger,
                delivered=self._queue.delivered,
            )
        )
        return _REASON if index == self._fail_on_call else None


def _snapshot() -> Snapshot:
    """Return an idle snapshot. The stream opens with it before any delivery."""
    return Snapshot(
        ts=_START,
        state="idle",
        running_turn=None,
        latest_message_id=None,
        latest_revision=None,
        latest_unproposed_revision=None,
    )


def _schedule(
    gaps: list[int], interval: float
) -> list[tuple[float, BuilderEvent | None]]:
    """Turn idle gaps into absolute delivery times, ending with a close after 3 intervals."""
    schedule: list[tuple[float, BuilderEvent | None]] = []
    due = 0.0
    for seq, gap in enumerate(gaps, start=1):
        due += gap
        event = Text(
            ts=_START + timedelta(seconds=due),
            turn_id=_TURN,
            seq=seq,
            text=f"chunk {seq}",
        )
        schedule.append((due, event))
    schedule.append((due + 3 * interval, None))
    return schedule


async def _drive(gaps: list[int], fail_on_call: int | None) -> _Run:
    """Run ``iter_session_frames`` over the simulated timeline and collect what it did."""
    interval = float(stream.settings.SSE_REVOCATION_CHECK_INTERVAL_SECONDS)
    clock = _Clock()
    queue = _TimedQueue(_schedule(gaps, interval))
    check = _StubCheck(clock, queue, fail_on_call)
    bus = _TimedBus(queue)
    # Only the stream's wait_for call is faked. Nothing else in this drive awaits it.
    with patch(
        "app.api.workflow_builder.stream.asyncio.wait_for",
        _fake_wait_for(clock, queue),
    ):
        frames = [
            json.loads(frame["data"])
            async for frame in stream.iter_session_frames(
                session_id=_SESSION,
                bus=bus,
                snapshot_fn=_snapshot,
                revocation_check=check,
                now=clock.now,
                clock=clock.monotonic,
            )
        ]
    return _Run(
        frames=frames,
        checks=check.checks,
        delivered=queue.delivered,
        ended_at=clock.seconds,
        unsubscribed=bus.unsubscribed,
    )


@contextmanager
def _requirement_cadence() -> Iterator[None]:
    """Pin the cadence settings to the values Requirement 40.7 names."""
    with patch.multiple(
        stream.settings,
        SSE_REVOCATION_CHECK_EVERY_N_EVENTS=_EVERY_N_EVENTS,
        SSE_REVOCATION_CHECK_INTERVAL_SECONDS=_MAX_GAP_SECONDS,
    ):
        yield


@settings(max_examples=100, deadline=None)
@given(gaps=_GAPS, fail_on_call=_FAIL_ON_CALL)
def test_iter_session_frames_checks_revocation_on_cadence_when_events_and_idle_vary(
    gaps: list[int], fail_on_call: int | None
) -> None:
    """Checks follow the every-five-events and 30-second rules; a failed check ends the stream."""
    with _requirement_cadence():
        run = asyncio.run(_drive(gaps, fail_on_call))

    revoked = fail_on_call is not None and len(run.checks) > fail_on_call

    # Requirement 40.8: a failed check is followed by session_revoked, then the end.
    if revoked:
        assert len(run.checks) == fail_on_call + 1
        assert run.frames[-1]["type"] == "session_revoked"
        assert run.frames[-1]["data"]["reason"] == _REASON
        assert run.ended_at == run.checks[-1].at
    else:
        assert all(frame["type"] != "session_revoked" for frame in run.frames)

    # Every delivered event is sent before the next check, so text frames equal deliveries.
    assert sum(frame["type"] == "text" for frame in run.frames) == run.delivered
    assert run.unsubscribed == 1

    # Requirement 40.7, event rule: checks after events 5, 10, 15 and so on, only.
    event_marks = [c.delivered for c in run.checks if c.trigger == "event"]
    assert event_marks == list(
        range(_EVERY_N_EVENTS, run.delivered + 1, _EVERY_N_EVENTS)
    )

    # Requirement 40.7, time rule: no gap of more than 30 s from the stream opening,
    # between checks, or from the last check to the close.
    times = [0.0, *(c.at for c in run.checks), run.ended_at]
    gaps_seconds = [
        later - earlier for earlier, later in zip(times, times[1:], strict=False)
    ]
    assert all(gap <= _MAX_GAP_SECONDS for gap in gaps_seconds), (
        f"gaps between checks {gaps_seconds} exceed {_MAX_GAP_SECONDS} s; "
        f"event gaps {gaps}"
    )
