"""Unit tests for the Session_Stream (task 16.6, design 3.3).

The generator is driven with a real ``SessionEventBus`` and a stubbed revocation
check; the route is mounted on a minimal app with its dependencies overridden. No
database, network or model is used.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents.workflow_builder.events import (
    SessionDeleted,
    Snapshot,
    Text,
    TokenUsage,
    TurnCompleted,
)
from app.api.workflow_builder import stream
from app.api.workflow_builder.admission import BuilderAccess, require_builder_access
from app.api.workflow_builder.bus import SessionEventBus
from app.core.dependencies import bearer_scheme
from app.models.database import get_db

_NOW = datetime(2030, 1, 1, tzinfo=UTC)
_SESSION = "s-1"


def _snapshot() -> Snapshot:
    return Snapshot(
        ts=_NOW,
        state="idle",
        running_turn=None,
        latest_message_id=None,
        latest_revision=None,
        latest_unproposed_revision=None,
    )


def _text(seq: int) -> Text:
    return Text(ts=_NOW, turn_id="t-1", seq=seq, text=f"chunk {seq}")


def _completed() -> TurnCompleted:
    return TurnCompleted(
        ts=_NOW,
        turn_id="t-1",
        seq=9,
        status="completed",
        outcome="reply",
        stop_reason=None,
        message_id="m-1",
        revision=None,
        usage=TokenUsage.zero(),
    )


def _body(frame: dict[str, str]) -> dict[str, Any]:
    return json.loads(frame["data"])


class _Checker:
    """A revocation check that records its calls and answers from a script."""

    def __init__(self, *reasons: str | None) -> None:
        self.calls = 0
        self._reasons = list(reasons)

    async def __call__(self) -> str | None:
        self.calls += 1
        return self._reasons.pop(0) if self._reasons else None


def _gen(bus: SessionEventBus, check: _Checker) -> AsyncIterator[dict[str, str]]:
    return stream.iter_session_frames(
        session_id=_SESSION,
        bus=bus,
        snapshot_fn=_snapshot,
        revocation_check=check,
        now=lambda: _NOW,
        clock=lambda: 0.0,
    )


@pytest.fixture(autouse=True)
def _fast_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stream.settings, "SSE_REVOCATION_CHECK_INTERVAL_SECONDS", 0.05)
    monkeypatch.setattr(stream.settings, "SSE_REVOCATION_CHECK_EVERY_N_EVENTS", 3)


def test_iter_session_frames_sends_snapshot_first_without_id_line() -> None:
    async def scenario() -> dict[str, str]:
        gen = _gen(SessionEventBus(), _Checker())
        try:
            return await anext(gen)
        finally:
            await gen.aclose()

    frame = asyncio.run(scenario())

    assert set(frame) == {"data"}
    body = _body(frame)
    assert body["type"] == "snapshot"
    assert body["data"]["state"] == "idle"
    assert "type" not in body["data"]


def test_iter_session_frames_stays_open_after_turn_completed() -> None:
    async def scenario() -> tuple[list[str], bool, int]:
        bus = SessionEventBus()
        gen = _gen(bus, _Checker())
        types = [_body(await anext(gen))["type"]]
        bus.publish(_SESSION, _completed())
        types.append(_body(await anext(gen))["type"])
        try:
            await asyncio.wait_for(anext(gen), timeout=0.2)
            ended = True
        except TimeoutError:
            ended = False
        return types, ended, bus.subscriber_count(_SESSION)

    types, ended, subscribers = asyncio.run(scenario())

    assert types == ["snapshot", "turn_completed"]
    assert ended is False
    assert subscribers == 0  # the cancelled wait released the subscription


def test_iter_session_frames_closes_after_session_deleted() -> None:
    async def scenario() -> tuple[list[str], int]:
        bus = SessionEventBus()
        gen = _gen(bus, _Checker())
        types = [_body(await anext(gen))["type"]]
        bus.publish(_SESSION, SessionDeleted(ts=_NOW))
        types.append(_body(await anext(gen))["type"])
        with pytest.raises(StopAsyncIteration):
            await anext(gen)
        return types, bus.subscriber_count(_SESSION)

    types, subscribers = asyncio.run(scenario())

    assert types == ["snapshot", "session_deleted"]
    assert subscribers == 0


def test_iter_session_frames_closes_on_none_sentinel() -> None:
    async def scenario() -> int:
        bus = SessionEventBus()
        gen = _gen(bus, _Checker())
        await anext(gen)
        bus.close_session(_SESSION, None)
        with pytest.raises(StopAsyncIteration):
            await anext(gen)
        return bus.subscriber_count(_SESSION)

    assert asyncio.run(scenario()) == 0


def test_iter_session_frames_checks_revocation_after_every_n_events() -> None:
    async def scenario() -> tuple[int, int]:
        bus = SessionEventBus()
        check = _Checker()
        gen = _gen(bus, check)
        await anext(gen)
        for seq in range(1, 8):
            bus.publish(_SESSION, _text(seq))
        for _ in range(7):
            await anext(gen)
        calls = check.calls
        await gen.aclose()
        return calls, bus.subscriber_count(_SESSION)

    calls, subscribers = asyncio.run(scenario())

    assert calls == 2  # after events 3 and 6; the seventh has not reached 3 yet
    assert subscribers == 0


def test_iter_session_frames_sends_session_revoked_and_closes_on_cadence_failure() -> (
    None
):
    async def scenario() -> list[dict[str, Any]]:
        bus = SessionEventBus()
        gen = _gen(bus, _Checker("logged_out"))
        frames = [_body(await anext(gen))]
        for seq in range(1, 4):
            bus.publish(_SESSION, _text(seq))
        frames += [_body(await anext(gen)) for _ in range(4)]
        with pytest.raises(StopAsyncIteration):
            await anext(gen)
        return frames

    frames = asyncio.run(scenario())

    assert [f["type"] for f in frames] == [
        "snapshot",
        "text",
        "text",
        "text",
        "session_revoked",
    ]
    assert frames[-1]["data"] == {
        "ts": _NOW.isoformat().replace("+00:00", "Z"),
        "session_id": _SESSION,
        "reason": "logged_out",
    }


def test_iter_session_frames_checks_revocation_on_idle_timeout() -> None:
    async def scenario() -> tuple[list[str], int]:
        bus = SessionEventBus()
        check = _Checker(None, "credential_expired")
        gen = _gen(bus, check)
        types = [_body(await anext(gen))["type"]]
        types.append(_body(await asyncio.wait_for(anext(gen), timeout=2))["type"])
        with pytest.raises(StopAsyncIteration):
            await anext(gen)
        return types, check.calls

    types, calls = asyncio.run(scenario())

    assert types == ["snapshot", "session_revoked"]
    assert calls == 2  # the first idle check passed, the second failed


def test_iter_session_frames_keeps_idle_cadence_when_wall_clock_jumps() -> None:
    wall = {"ts": _NOW}

    def jumping_now() -> datetime:
        wall["ts"] += timedelta(hours=1)
        return wall["ts"]

    async def scenario() -> int:
        check = _Checker()
        gen = stream.iter_session_frames(
            session_id=_SESSION,
            bus=SessionEventBus(),
            snapshot_fn=_snapshot,
            revocation_check=check,
            now=jumping_now,
        )
        await anext(gen)
        pending = asyncio.ensure_future(anext(gen))
        await asyncio.sleep(0.3)  # six intervals of 0.05 s
        pending.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await pending
        await gen.aclose()
        return check.calls

    calls = asyncio.run(scenario())

    # Wall-clock time is one hour ahead on every read; the cadence must ignore it.
    assert 1 <= calls <= 8


def test_iter_session_frames_releases_subscription_when_snapshot_fails() -> None:
    def broken() -> Snapshot:
        raise RuntimeError("boom")

    async def scenario() -> int:
        bus = SessionEventBus()
        gen = stream.iter_session_frames(
            session_id=_SESSION,
            bus=bus,
            snapshot_fn=broken,
            revocation_check=_Checker(),
        )
        with pytest.raises(RuntimeError):
            await anext(gen)
        return bus.subscriber_count(_SESSION)

    assert asyncio.run(scenario()) == 0


# --- Route ----------------------------------------------------------------------------


def _client(
    monkeypatch: pytest.MonkeyPatch, *, owns: bool
) -> tuple[TestClient, list[dict[str, Any]]]:
    app = FastAPI()
    app.include_router(stream.router)
    access = BuilderAccess(
        user=SimpleNamespace(id="u-1"),  # type: ignore[arg-type]
        principal=SimpleNamespace(),  # type: ignore[arg-type]
        tier="enterprise",
    )
    app.dependency_overrides[require_builder_access] = lambda: access
    app.dependency_overrides[bearer_scheme] = lambda: SimpleNamespace(
        credentials="token"
    )
    app.dependency_overrides[get_db] = lambda: None
    lookups: list[dict[str, Any]] = []

    def owner_lookup(_db: object, user_id: str, session_id: str) -> bool:
        lookups.append({"user_id": user_id, "session_id": session_id})
        return owns

    async def one_frame(**_kwargs: object) -> AsyncIterator[dict[str, str]]:
        yield {"data": json.dumps({"type": "snapshot", "data": {}})}

    monkeypatch.setattr(stream, "_owner_lookup", owner_lookup)
    monkeypatch.setattr(stream, "iter_session_frames", one_frame)
    return TestClient(app), lookups


def test_stream_session_events_returns_404_when_session_not_owned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, lookups = _client(monkeypatch, owns=False)

    response = client.get(f"/api/workflow-builder/sessions/{_SESSION}/events")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "session_not_found"
    assert lookups == [{"user_id": "u-1", "session_id": _SESSION}]


def test_stream_session_events_streams_with_proxy_safe_headers_when_owned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = _client(monkeypatch, owns=True)

    with client.stream(
        "GET", f"/api/workflow-builder/sessions/{_SESSION}/events"
    ) as response:
        text = "".join(response.iter_text())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"
    assert response.headers["cache-control"] == "no-cache"
    assert "data: " in text
    assert "\nid:" not in "\n" + text


def test_stream_session_events_is_registered_under_the_builder_prefix() -> None:
    paths = {route.path for route in stream.router.routes}  # type: ignore[attr-defined]

    assert paths == {"/api/workflow-builder/sessions/{session_id}/events"}
