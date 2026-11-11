"""Unit tests for ``SessionEventBus`` (task 15.11, Req 22.1, 23.18, 30.3)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.agents.workflow_builder.events import (
    BuilderEvent,
    SessionDeleted,
    Snapshot,
    Text,
)
from app.api.workflow_builder.bus import SessionEventBus, SessionQueue

SESSION = "session-1"


def _snapshot() -> Snapshot:
    return Snapshot(
        ts=datetime.now(UTC),
        state="idle",
        running_turn=None,
        latest_message_id=None,
        latest_revision=None,
        latest_unproposed_revision=None,
    )


def _text(seq: int) -> Text:
    return Text(ts=datetime.now(UTC), turn_id="t", seq=seq, text=f"m{seq}")


def _deleted() -> SessionDeleted:
    return SessionDeleted(ts=datetime.now(UTC))


def _drain(queue: SessionQueue) -> list[BuilderEvent | None]:
    items: list[BuilderEvent | None] = []
    while not queue.empty():
        items.append(queue.get_nowait())
    return items


def test_publish_delivers_events_in_order_when_subscriber_registered() -> None:
    bus = SessionEventBus(queue_maxsize=10)
    queue, _ = bus.subscribe(SESSION, _snapshot)

    bus.publish(SESSION, _text(1))
    bus.publish(SESSION, _text(2))

    assert [e.seq for e in _drain(queue) if isinstance(e, Text)] == [1, 2]


def test_subscribe_leaves_queue_unregistered_when_snapshot_fn_raises() -> None:
    bus = SessionEventBus(queue_maxsize=10)

    def boom() -> Snapshot:
        raise RuntimeError("no snapshot")

    with pytest.raises(RuntimeError):
        bus.subscribe(SESSION, boom)

    assert bus.subscriber_count(SESSION) == 0


def test_subscribe_skips_events_published_before_when_client_connects_late() -> None:
    bus = SessionEventBus(queue_maxsize=10)
    bus.publish(SESSION, _text(1))

    queue, _ = bus.subscribe(SESSION, _snapshot)

    assert queue.empty()


def test_publish_evicts_full_queue_and_sends_sentinel_when_queue_overflows() -> None:
    bus = SessionEventBus(queue_maxsize=2)
    slow, _ = bus.subscribe(SESSION, _snapshot)
    fast, _ = bus.subscribe(SESSION, _snapshot)
    bus.publish(SESSION, _text(1))
    _drain(fast)
    bus.publish(SESSION, _text(2))
    _drain(fast)

    bus.publish(SESSION, _text(3))

    assert bus.subscriber_count(SESSION) == 1
    drained = _drain(slow)
    assert drained[-1] is None
    assert [e.seq for e in drained if isinstance(e, Text)] == [2]
    assert [e.seq for e in _drain(fast) if isinstance(e, Text)] == [3]


def test_publish_keeps_other_subscribers_when_one_is_evicted() -> None:
    bus = SessionEventBus(queue_maxsize=1)
    full, _ = bus.subscribe(SESSION, _snapshot)
    bus.publish(SESSION, _text(1))
    healthy, _ = bus.subscribe(SESSION, _snapshot)

    bus.publish(SESSION, _text(2))

    assert bus.subscriber_count(SESSION) == 1
    assert _drain(full)[-1] is None
    assert [e.seq for e in _drain(healthy) if isinstance(e, Text)] == [2]


def test_close_session_sends_final_event_then_sentinel_when_final_given() -> None:
    bus = SessionEventBus(queue_maxsize=10)
    queue, _ = bus.subscribe(SESSION, _snapshot)
    final = _deleted()

    bus.close_session(SESSION, final)

    assert _drain(queue) == [final, None]
    assert bus.subscriber_count(SESSION) == 0


def test_close_session_drops_oldest_events_when_queue_is_full() -> None:
    bus = SessionEventBus(queue_maxsize=2)
    queue, _ = bus.subscribe(SESSION, _snapshot)
    bus.publish(SESSION, _text(1))
    bus.publish(SESSION, _text(2))
    final = _deleted()

    bus.close_session(SESSION, final)

    assert _drain(queue) == [final, None]


def test_close_session_sends_only_sentinel_when_no_final_event() -> None:
    bus = SessionEventBus(queue_maxsize=1)
    queue, _ = bus.subscribe(SESSION, _snapshot)
    bus.publish(SESSION, _text(1))

    bus.close_session(SESSION, None)

    assert _drain(queue) == [None]


def test_close_all_closes_every_session_when_called() -> None:
    bus = SessionEventBus(queue_maxsize=10)
    first, _ = bus.subscribe("a", _snapshot)
    second, _ = bus.subscribe("b", _snapshot)

    bus.close_all()

    assert _drain(first) == [None]
    assert _drain(second) == [None]
    assert bus.subscriber_count("a") == 0
    assert bus.subscriber_count("b") == 0


def test_unsubscribe_ignores_unknown_session_and_queue_when_not_registered() -> None:
    bus = SessionEventBus(queue_maxsize=10)
    queue, _ = bus.subscribe(SESSION, _snapshot)

    bus.unsubscribe("other", queue)
    bus.unsubscribe(SESSION, queue)
    bus.unsubscribe(SESSION, queue)

    assert bus.subscriber_count(SESSION) == 0
