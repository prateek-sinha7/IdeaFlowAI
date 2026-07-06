"""Unit tests for quick-260704-p10 — Bedrock prompt caching + thinking knob.

Two independent, fully-offline concerns:

PART A — ``_BedrockCachePointsMiddleware`` (deep_agent_runner): injects a
``cache_control`` dict into per-call ``model_settings`` on ChatBedrockConverse
requests only, gated by ``settings.BEDROCK_PROMPT_CACHE_ENABLED``. No-op on
non-Bedrock requests (ChatAnthropic keeps deepagents' built-in caching).

PART B — ``build_model`` extended-thinking threading: ``THINKING_BUDGET_TOKENS``
> 0 threads a clamped thinking budget into BOTH provider branches; 0 (default)
adds no thinking field on either branch.

Everything here is offline — no network, no live Bedrock/Anthropic call. The
Bedrock-positive cache case uses an UNINITIALISED ChatBedrockConverse instance
(``object.__new__``) so ``isinstance`` passes without creds; the build_model
tests monkeypatch the provider constructors with capturing stubs.
"""

from __future__ import annotations

import asyncio

import pytest

from app.agents.deep_agent_runner import _BedrockCachePointsMiddleware
from app.core.config import settings


# ---------------------------------------------------------------------------
# A tiny duck-typed fake ModelRequest — the middleware only reads ``.model`` /
# ``.model_settings`` and calls ``.override(**kw)``.
# ---------------------------------------------------------------------------
class _FakeReq:
    def __init__(self, model, model_settings=None):
        self.model = model
        self.model_settings = model_settings if model_settings is not None else {}

    def override(self, **kw):
        new = _FakeReq(self.model, dict(self.model_settings))
        for key, val in kw.items():
            setattr(new, key, val)
        return new


def _recording_handler():
    """Return (handler, box) where box['req'] captures the request seen."""
    box: dict = {}

    def handler(req):
        box["req"] = req
        return "SENTINEL"

    return handler, box


def _bedrock_instance():
    """An uninitialised ChatBedrockConverse — isinstance True, no creds/network."""
    from langchain_aws import ChatBedrockConverse

    return object.__new__(ChatBedrockConverse)


# ===========================================================================
# PART A — cache middleware
# ===========================================================================
def test_cache_middleware_bedrock_enabled_sets_cache_control():
    mw = _BedrockCachePointsMiddleware()
    req = _FakeReq(_bedrock_instance(), {})
    handler, box = _recording_handler()

    result = mw.wrap_model_call(req, handler)

    assert result == "SENTINEL"
    seen = box["req"]
    assert seen.model_settings["cache_control"] == {
        "type": "ephemeral",
        "ttl": settings.BEDROCK_PROMPT_CACHE_TTL,
    }


def test_cache_middleware_non_bedrock_is_passthrough():
    mw = _BedrockCachePointsMiddleware()
    req = _FakeReq(object(), {})  # plain non-Bedrock model
    handler, box = _recording_handler()

    mw.wrap_model_call(req, handler)

    # Original request handed through unchanged — no cache_control anywhere.
    assert box["req"] is req
    assert "cache_control" not in box["req"].model_settings


def test_cache_middleware_disabled_is_passthrough(monkeypatch):
    monkeypatch.setattr(settings, "BEDROCK_PROMPT_CACHE_ENABLED", False)
    mw = _BedrockCachePointsMiddleware()
    req = _FakeReq(_bedrock_instance(), {})
    handler, box = _recording_handler()

    mw.wrap_model_call(req, handler)

    assert box["req"] is req
    assert "cache_control" not in box["req"].model_settings


def test_cache_middleware_async_bedrock_enabled_sets_cache_control():
    mw = _BedrockCachePointsMiddleware()
    req = _FakeReq(_bedrock_instance(), {})
    box: dict = {}

    async def ahandler(r):
        box["req"] = r
        return "SENTINEL"

    result = asyncio.run(mw.awrap_model_call(req, ahandler))

    assert result == "SENTINEL"
    assert box["req"].model_settings["cache_control"] == {
        "type": "ephemeral",
        "ttl": settings.BEDROCK_PROMPT_CACHE_TTL,
    }


# ===========================================================================
# PART B — build_model thinking threading
# ===========================================================================
class _Cap:
    """Capturing constructor stub — records the kwargs build_model passes."""

    last: dict = {}

    def __init__(self, **kw):
        _Cap.last = dict(kw)


@pytest.fixture
def cap(monkeypatch):
    """Patch both provider constructors with the capturing stub + reset capture."""
    _Cap.last = {}
    monkeypatch.setattr("langchain_anthropic.ChatAnthropic", _Cap)
    monkeypatch.setattr("langchain_aws.ChatBedrockConverse", _Cap)
    return _Cap


def test_build_model_anthropic_thinking_enabled(monkeypatch, cap):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(settings, "THINKING_BUDGET_TOKENS", 3000)
    from app.agents.model_factory import build_model

    build_model()

    assert cap.last["thinking"] == {"type": "enabled", "budget_tokens": 3000}
    # thinking requires temperature=1 on Anthropic.
    assert cap.last["temperature"] == 1


def test_build_model_anthropic_thinking_disabled(monkeypatch, cap):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(settings, "THINKING_BUDGET_TOKENS", 0)
    from app.agents.model_factory import build_model

    build_model()

    assert "thinking" not in cap.last
    assert "temperature" not in cap.last  # disabled path byte-identical to today


def test_build_model_bedrock_thinking_enabled(monkeypatch, cap):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(settings, "THINKING_BUDGET_TOKENS", 3000)
    from app.agents.model_factory import build_model

    build_model()

    extra = cap.last["additional_model_request_fields"]
    assert extra["thinking"]["type"] == "enabled"
    assert extra["thinking"]["budget_tokens"] == 3000
    assert extra["thinking"]["budget_tokens"] < settings.MAX_OUTPUT_TOKENS
    assert cap.last["temperature"] == 1


def test_build_model_bedrock_thinking_disabled(monkeypatch, cap):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(settings, "THINKING_BUDGET_TOKENS", 0)
    from app.agents.model_factory import build_model

    build_model()

    assert "additional_model_request_fields" not in cap.last
    assert "temperature" not in cap.last  # disabled path byte-identical to today


def test_build_model_thinking_budget_clamped_to_ceiling(monkeypatch, cap):
    # A budget far above the output ceiling clamps to <resolved max_tokens> - 1
    # (which, with no max_tokens override, is settings.MAX_OUTPUT_TOKENS - 1).
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(settings, "THINKING_BUDGET_TOKENS", 10_000_000)
    from app.agents.model_factory import build_model

    build_model()

    assert cap.last["thinking"]["budget_tokens"] == settings.MAX_OUTPUT_TOKENS - 1


def test_build_model_thinking_budget_clamped_to_floor(monkeypatch, cap):
    # A tiny positive budget clamps UP to the 1024 floor.
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(settings, "THINKING_BUDGET_TOKENS", 500)
    from app.agents.model_factory import build_model

    build_model()

    assert cap.last["thinking"]["budget_tokens"] == 1024
