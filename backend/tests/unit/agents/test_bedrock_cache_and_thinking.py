"""Unit tests for quick-260704-p10 — Bedrock prompt caching + thinking knob.

Two independent, fully-offline concerns:

PART A — ``_BedrockCachePointsMiddleware`` (deep_agent_runner): injects a
``cache_control`` dict into per-call ``model_settings`` on ChatBedrockConverse
requests only, gated by ``settings.BEDROCK_PROMPT_CACHE_ENABLED``. No-op on
non-Bedrock requests (ChatAnthropic keeps deepagents' built-in caching).

PART B — ``build_model`` extended-thinking threading: ``THINKING_BUDGET_TOKENS``
> 0 threads a clamped thinking budget into BOTH provider branches; 0 (default)
adds no thinking field on either branch.

PART C — ``_extract_thinking`` (deep_agent_runner): pulls streamed extended-
thinking text out of a message content-block list, recognizing both the native
Anthropic shape (``{"type": "thinking", "thinking": ...}``) and the Bedrock
Converse shape (``{"type": "reasoning_content", "reasoning_content": {"text": ...}}``).

Everything here is offline — no network, no live Bedrock/Anthropic call. The
Bedrock-positive cache case uses an UNINITIALISED ChatBedrockConverse instance
(``object.__new__``) so ``isinstance`` passes without creds; the build_model
tests monkeypatch the provider constructors with capturing stubs.
"""

from __future__ import annotations

import asyncio

import pytest

from app.agents.deep_agent_runner import (
    _BedrockCachePointsMiddleware,
    _extract_thinking,
)
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
    """A budget-mode Claude model gets a `thinking` block at the configured budget.

    The model is PINNED rather than taken from BEDROCK_INFERENCE_PROFILE_ID. This
    test used to call `build_model()` bare, so it silently asserted that the
    deployment default happens to be a Claude model — it went red the moment the
    default was pointed at GPT-5.6 Luna to validate spec 020's FR-13, for no
    reason connected to what it is testing.
    """
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(settings, "THINKING_BUDGET_TOKENS", 3000)
    from app.agents.model_factory import build_model

    build_model("eu.anthropic.claude-haiku-4-5-20251001-v1:0")

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


# ===========================================================================
# PART C — _extract_thinking: streamed content-block extraction, by provider
#
# Extended thinking arrives as a content BLOCK (never additional_kwargs), in a
# provider-specific shape. Pure function, no runner/graph scaffolding needed.
# ===========================================================================
def test_extract_thinking_anthropic_block():
    content = [{"type": "thinking", "thinking": "Let me consider the options"}]
    assert _extract_thinking(content) == "Let me consider the options"


def test_extract_thinking_bedrock_block():
    content = [
        {
            "type": "reasoning_content",
            "reasoning_content": {
                "type": "text",
                "text": "I need to calculate",
                "signature": "abc",
            },
        }
    ]
    assert _extract_thinking(content) == "I need to calculate"


def test_extract_thinking_ignores_text_blocks():
    content = [{"type": "text", "text": "visible output"}]
    assert _extract_thinking(content) == ""


def test_extract_thinking_mixed_blocks_extracts_only_thinking():
    content = [
        {
            "type": "reasoning_content",
            "reasoning_content": {"type": "text", "text": "reasoning "},
        },
        {"type": "text", "text": "answer"},
    ]
    assert _extract_thinking(content) == "reasoning "


def test_extract_thinking_plain_string_content_yields_nothing():
    # A plain str ``content`` (no blocks) never carries thinking.
    assert _extract_thinking("just text") == ""


def test_extract_thinking_empty_list_yields_nothing():
    assert _extract_thinking([]) == ""


# ---------------------------------------------------------------------------
# PART A2 — capability gating of the cache middleware (spec 020 / FR-21, SC-12)
#
# The middleware used to decide on TRANSPORT alone (isinstance
# ChatBedrockConverse). OpenAI's models ride that same client and support prompt
# caching on the Responses API only: a cachePoint on Converse comes back
# AccessDeniedException, measured against global.openai.gpt-5.6-luna while Claude
# Haiku 4.5 accepted the identical call. With the flag defaulting ON that failed
# 100% of GPT requests, so the gate now asks the catalog.
# ---------------------------------------------------------------------------
def _bedrock_instance_with_id(model_id: str):
    """A ChatBedrockConverse test double carrying a model id.

    ``object.__new__`` skips pydantic validation (no creds, no network) and the
    id goes straight into ``__dict__``, which is where ``model_identifier``
    reads ``.model_id`` from.
    """
    inst = _bedrock_instance()
    inst.__dict__["model_id"] = model_id
    return inst


def _cache_control_for(model_id: str):
    """Return the cache_control the middleware would send for ``model_id``."""
    mw = _BedrockCachePointsMiddleware()
    req = _FakeReq(_bedrock_instance_with_id(model_id), {})
    handler, box = _recording_handler()
    mw.wrap_model_call(req, handler)
    return box["req"].model_settings.get("cache_control")


def test_cache_middleware_skips_a_model_that_cannot_cache(monkeypatch):
    """A catalog entry with supports_prompt_caching=False gets NO cachePoint."""
    import dataclasses

    from agents.capabilities import model_catalog as mc

    claude_id = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
    real = mc.ModelCatalog().get(claude_id)
    assert real is not None and real.supports_prompt_caching is True

    # Flip ONLY the capability, leaving every other field alone, so this pins the
    # GATE rather than anything about a particular model.
    no_cache = dataclasses.replace(real, supports_prompt_caching=False)
    monkeypatch.setattr(
        mc.ModelCatalog, "get", lambda self, mid: no_cache if mid == claude_id else None
    )

    assert _cache_control_for(claude_id) is None


def test_cache_middleware_still_caches_a_model_that_can():
    assert _cache_control_for("eu.anthropic.claude-haiku-4-5-20251001-v1:0") == {
        "type": "ephemeral",
        "ttl": settings.BEDROCK_PROMPT_CACHE_TTL,
    }


def test_cache_middleware_fails_open_for_an_uncatalogued_model():
    """An id the catalog does not know keeps caching ON — today's behaviour.

    Fail-closed would silently disable caching for any model missing from the
    catalog, which is a parity break dressed up as a safety measure.
    """
    assert _cache_control_for("some.model.nobody.registered") == {
        "type": "ephemeral",
        "ttl": settings.BEDROCK_PROMPT_CACHE_TTL,
    }


# ── SC-12 — the one confirmed hard blocker ───────────────────────────────────
# Sending a cachePoint to a GPT-5.6 model returns AccessDeniedException from
# bedrock-runtime (verified live in eu-north-1, spec §12 — Claude passed as the
# control in the same session). BEDROCK_PROMPT_CACHE_ENABLED defaults to true, so
# without this gate every GPT run fails on its first call.


@pytest.mark.parametrize(
    "gpt_id", ["global.openai.gpt-5.6-luna", "global.openai.gpt-5.6-sol"]
)
def test_sc12_gpt_models_get_no_cache_control_with_caching_enabled(monkeypatch, gpt_id):
    monkeypatch.setattr(settings, "BEDROCK_PROMPT_CACHE_ENABLED", True)
    assert _cache_control_for(gpt_id) is None


def test_sc12_claude_still_cached_in_the_same_configuration():
    """The control for the test above: the gate must be keyed on the model's
    capability, not on prompt caching having been switched off wholesale."""
    assert settings.BEDROCK_PROMPT_CACHE_ENABLED is True
    assert _cache_control_for("eu.anthropic.claude-haiku-4-5-20251001-v1:0") is not None
