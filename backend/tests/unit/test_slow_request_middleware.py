"""tests/unit/test_slow_request_middleware.py — the slow-request logging
middleware in app/main.py (STABILIZATION.md diagnosability).

Drives ``app.main._slow_request_middleware`` directly against a fake
``Request`` and a ``call_next`` that sleeps past the threshold, so the test
doesn't need to spin up a full app / real HTTP round-trip.
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from app import main


class _FakeURL:
    def __init__(self, path: str) -> None:
        self.path = path


class _FakeRequest:
    def __init__(self, method: str, path: str) -> None:
        self.method = method
        self.url = _FakeURL(path)


@pytest.mark.asyncio
async def test_slow_request_is_logged(caplog, monkeypatch):
    monkeypatch.setattr(main, "_SLOW_REQUEST_THRESHOLD_SECONDS", 0.05)

    async def slow_call_next(request):
        await asyncio.sleep(0.1)
        return "the-response"

    request = _FakeRequest("GET", "/api/slow")
    with caplog.at_level(logging.WARNING, logger="app.main"):
        response = await main._slow_request_middleware(request, slow_call_next)

    assert response == "the-response"
    slow_logs = [r for r in caplog.records if "slow request" in r.message]
    assert slow_logs, f"expected a slow-request log, got: {[r.message for r in caplog.records]}"
    assert "method=GET" in slow_logs[0].message
    assert "path=/api/slow" in slow_logs[0].message


@pytest.mark.asyncio
async def test_fast_request_is_not_logged(caplog, monkeypatch):
    monkeypatch.setattr(main, "_SLOW_REQUEST_THRESHOLD_SECONDS", 5.0)

    async def fast_call_next(request):
        return "the-response"

    request = _FakeRequest("GET", "/health")
    with caplog.at_level(logging.WARNING, logger="app.main"):
        await main._slow_request_middleware(request, fast_call_next)

    slow_logs = [r for r in caplog.records if "slow request" in r.message]
    assert not slow_logs


@pytest.mark.asyncio
async def test_slow_request_is_logged_even_on_failure(caplog, monkeypatch):
    monkeypatch.setattr(main, "_SLOW_REQUEST_THRESHOLD_SECONDS", 0.05)

    async def failing_call_next(request):
        await asyncio.sleep(0.1)
        raise RuntimeError("boom")

    request = _FakeRequest("POST", "/api/whatever")
    with caplog.at_level(logging.WARNING, logger="app.main"):
        with pytest.raises(RuntimeError):
            await main._slow_request_middleware(request, failing_call_next)

    slow_logs = [r for r in caplog.records if "slow request" in r.message]
    assert slow_logs, f"expected a slow-request log even on failure, got: {[r.message for r in caplog.records]}"
