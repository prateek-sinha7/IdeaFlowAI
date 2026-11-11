"""Security: a revoked login ends the builder Session_Stream with ``session_revoked``.

Validates: Requirements 40.7, 40.8, 49.7.

An open stream outlives the request that opened it, so the credential is checked again
while the stream runs: after every ``SSE_REVOCATION_CHECK_EVERY_N_EVENTS`` (5) events
and at least every ``SSE_REVOCATION_CHECK_INTERVAL_SECONDS`` (30 s). When the check
fails the stream sends ``session_revoked`` and closes, and sends nothing after it.

The checks here use the real ``_run_revocation_check`` (worker thread, time limit, fail
closed) and the real ``recheck_stream_credential`` where the credential is the subject:

* through the real route, a token the verifier no longer accepts closes the stream with
  ``session_revoked`` on the first interval check;
* through the generator the route wraps, five events trigger the check, the stream
  closes on failure, an event published afterwards reaches nobody and the revoked
  user's running Turn is left alone (G-15);
* a check that raises or runs past its time limit counts as a failure (fail closed);
* a token that still verifies keeps the stream open across several intervals.

No Docker and no database: ``InMemoryBuilderStore`` and a short interval set through
settings. Timing-dependent tests carry a ``timeout`` mark so a stream that fails to close
fails the test instead of hanging the run.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

import pytest

from app.agents.workflow_builder.events import Snapshot, Text
from app.api import run_stream
from app.api.run_stream import _run_revocation_check  # noqa: PLC2701 - the check the route uses
from app.api.workflow_builder import stream
from app.api.workflow_builder.bus import SessionEventBus
from app.api.workflow_builder.turns import (
    LiveTurn,
    get_live_turn,
    register_live_turn,
    release_live_turn,
)
from app.core.config import settings
from app.core.identity import CredentialInvalid
from tests.security.builder_world import API, BuilderWorld

SESSION = "session-revocation"
NOW = datetime(2030, 1, 1, tzinfo=UTC)

type WorldFactory = Callable[..., BuilderWorld]


def _snapshot() -> Snapshot:
    return Snapshot(
        ts=NOW,
        state="idle",
        running_turn=None,
        latest_message_id=None,
        latest_revision=None,
        latest_unproposed_revision=None,
    )


def _text(seq: int) -> Text:
    return Text(ts=NOW, turn_id="t-1", seq=seq, text=f"chunk {seq}")


def _body(frame: dict[str, str]) -> dict[str, Any]:
    return json.loads(frame["data"])


def _frames_of(lines: list[str]) -> list[dict[str, Any]]:
    """Decode the ``data:`` lines of a finished SSE body."""
    return [
        json.loads(line.removeprefix("data:").strip())
        for line in lines
        if line.startswith("data:")
    ]


def _generator(bus: SessionEventBus) -> Any:
    """The frame generator the route wraps, with the real revocation check."""

    async def revocation_check() -> str | None:
        return await _run_revocation_check(
            token="token", user_id="user-1", run_id=SESSION
        )

    return stream.iter_session_frames(
        session_id=SESSION,
        bus=bus,
        snapshot_fn=_snapshot,
        revocation_check=revocation_check,
    )


class _Recheck:
    """Stands in for ``recheck_stream_credential``: records calls, answers from a script."""

    def __init__(self, *reasons: str | None, delay: float = 0.0) -> None:
        self.calls = 0
        self._reasons = list(reasons)
        self._delay = delay

    def __call__(self, token: str) -> str | None:
        del token
        self.calls += 1
        if self._delay:
            time.sleep(self._delay)
        return self._reasons.pop(0) if self._reasons else None


@pytest.fixture
def _quick_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "SSE_REVOCATION_CHECK_INTERVAL_SECONDS", 0.05)
    monkeypatch.setattr(settings, "SSE_REVOCATION_CHECK_EVERY_N_EVENTS", 5)


@pytest.fixture
def _production_cadence(monkeypatch: pytest.MonkeyPatch) -> None:
    """The cadence Requirement 40.7 names: every 5 events, at least every 30 s."""
    monkeypatch.setattr(settings, "SSE_REVOCATION_CHECK_INTERVAL_SECONDS", 30)
    monkeypatch.setattr(settings, "SSE_REVOCATION_CHECK_EVERY_N_EVENTS", 5)


# --- Through the real route -------------------------------------------------------------


@pytest.mark.timeout(30)
@pytest.mark.usefixtures("_quick_interval")
def test_stream_route_closes_with_session_revoked_when_the_token_no_longer_verifies(
    make_builder_world: WorldFactory,
) -> None:
    world = make_builder_world(real_stream=True)
    alice = world.add_caller("alice")
    owned = world.seed_session(alice)

    # The route lets the caller in (the request-time check is overridden by the world);
    # the periodic check runs the real verifier, which now rejects the token.
    with patch(
        "app.core.identity.verify_credential",
        side_effect=CredentialInvalid("key rotated"),
    ):
        with world.client.stream(
            "GET",
            f"{API}/sessions/{owned.session_id}/events",
            headers=alice.headers,
        ) as response:
            assert response.status_code == 200
            lines = list(response.iter_lines())

    frames = _frames_of(lines)
    assert [f["type"] for f in frames] == ["snapshot", "session_revoked"]
    assert frames[-1]["data"]["session_id"] == owned.session_id
    assert frames[-1]["data"]["reason"] == "credential_expired"
    assert world.bus.subscriber_count(owned.session_id) == 0


# --- Through the generator the route wraps ------------------------------------------------


@pytest.mark.timeout(30)
@pytest.mark.usefixtures("_production_cadence")
async def test_iter_session_frames_closes_after_fifth_event_when_the_check_fails() -> (
    None
):
    bus = SessionEventBus()
    live = LiveTurn(
        session_id=SESSION,
        turn_id="t-1",
        user_message_id="m-1",
        user_id="user-1",
        model_id="model-x",
        effort=None,
    )
    recheck = _Recheck("logged_out")
    gen = _generator(bus)
    register_live_turn(live)

    try:
        with patch.object(run_stream, "recheck_stream_credential", recheck):
            frames = [_body(await anext(gen))]
            for seq in range(1, 5):
                bus.publish(SESSION, _text(seq))
            frames += [_body(await anext(gen)) for _ in range(4)]
            assert recheck.calls == 0, "the check ran before the fifth event"
            bus.publish(SESSION, _text(5))
            frames += [_body(await anext(gen)) for _ in range(2)]
            with pytest.raises(StopAsyncIteration):
                await anext(gen)
        still_registered = get_live_turn(SESSION) is live
    finally:
        release_live_turn(live)

    assert [f["type"] for f in frames] == ["snapshot"] + ["text"] * 5 + [
        "session_revoked"
    ]
    assert frames[-1]["data"]["reason"] == "logged_out"
    assert recheck.calls == 1
    # Nothing is sent after the close, and the client is gone from the bus ...
    assert bus.subscriber_count(SESSION) == 0
    bus.publish(SESSION, _text(6))
    # ... and the revoked user's running Turn is not stopped (G-15).
    assert still_registered
    assert live.stop_reason is None


@pytest.mark.timeout(30)
@pytest.mark.usefixtures("_quick_interval")
async def test_iter_session_frames_closes_with_session_revoked_when_idle_and_check_fails() -> (
    None
):
    bus = SessionEventBus()
    recheck = _Recheck(None, "account_removed")
    gen = _generator(bus)

    with patch.object(run_stream, "recheck_stream_credential", recheck):
        first = _body(await anext(gen))
        second = _body(await asyncio.wait_for(anext(gen), timeout=5))
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(anext(gen), timeout=5)

    assert first["type"] == "snapshot"
    assert second["type"] == "session_revoked"
    assert second["data"]["reason"] == "account_removed"
    assert recheck.calls == 2  # the first idle check passed, the second failed
    assert bus.subscriber_count(SESSION) == 0


@pytest.mark.timeout(30)
@pytest.mark.usefixtures("_quick_interval")
async def test_iter_session_frames_closes_with_session_revoked_when_the_check_raises() -> (
    None
):
    bus = SessionEventBus()

    def broken(token: str) -> str | None:
        del token
        raise RuntimeError("identity provider unreachable")

    gen = _generator(bus)

    with patch.object(run_stream, "recheck_stream_credential", broken):
        await anext(gen)
        revoked = _body(await asyncio.wait_for(anext(gen), timeout=5))
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(anext(gen), timeout=5)

    assert revoked["type"] == "session_revoked"
    assert revoked["data"]["reason"] == "revocation_check_failed"


@pytest.mark.timeout(30)
@pytest.mark.usefixtures("_quick_interval")
async def test_iter_session_frames_closes_with_session_revoked_when_the_check_is_too_slow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(run_stream, "_REVOCATION_CHECK_TIMEOUT_SECONDS", 0.05)
    bus = SessionEventBus()
    gen = _generator(bus)

    with patch.object(run_stream, "recheck_stream_credential", _Recheck(delay=0.5)):
        await anext(gen)
        revoked = _body(await asyncio.wait_for(anext(gen), timeout=5))

    assert revoked["type"] == "session_revoked"
    assert revoked["data"]["reason"] == "revocation_check_failed"


# --- Control: a valid credential keeps the stream open ----------------------------------


@pytest.mark.timeout(30)
@pytest.mark.usefixtures("_quick_interval")
async def test_iter_session_frames_stays_open_when_the_credential_still_verifies() -> (
    None
):
    bus = SessionEventBus()
    recheck = _Recheck()  # always None: still valid
    frames: list[dict[str, Any]] = []

    async def read_all() -> None:
        async for frame in _generator(bus):
            frames.append(_body(frame))

    with patch.object(run_stream, "recheck_stream_credential", recheck):
        reader = asyncio.ensure_future(read_all())
        await asyncio.sleep(0.5)  # about ten intervals
        still_open = not reader.done()
        calls_while_idle = recheck.calls
        bus.publish(SESSION, _text(1))
        await asyncio.sleep(0.1)
        reader.cancel()
        await asyncio.gather(reader, return_exceptions=True)

    assert still_open
    assert calls_while_idle >= 2, "the periodic check did not run while idle"
    assert [f["type"] for f in frames] == ["snapshot", "text"]
    assert bus.subscriber_count(SESSION) == 0
