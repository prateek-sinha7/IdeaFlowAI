"""Each model runs at its own output ceiling, not the global 32,768 (run 7ef4faf8)."""

from __future__ import annotations

import pytest

from agents.capabilities.model_catalog import max_output_tokens
from app.core.config import settings


@pytest.mark.parametrize(
    "model_id, cap",
    [
        ("eu.anthropic.claude-haiku-4-5-20251001-v1:0", 64000),
        ("claude-haiku-4-5", 64000),
        ("eu.anthropic.claude-sonnet-4-6", 128000),
        ("global.anthropic.claude-sonnet-4-6", 128000),
        ("us.anthropic.claude-sonnet-5", 128000),
        ("eu.anthropic.claude-opus-4-6-v1", 128000),
        ("claude-opus-4-7", 128000),
        ("claude-opus-5-5", 128000),
        ("claude-fable-5-1", 128000),
    ],
)
def test_listed_models_resolve_to_their_own_cap(model_id, cap):
    assert max_output_tokens(model_id) == cap


@pytest.mark.parametrize(
    "model_id",
    [
        "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
        "global.openai.gpt-5.6-luna",
        "",
        None,
    ],
)
def test_unlisted_models_keep_the_global_cap(model_id):
    assert max_output_tokens(model_id) is None


class _Cap:
    last: dict = {}

    def __init__(self, **kw):
        _Cap.last = dict(kw)


def test_bedrock_calls_carry_the_model_cap_and_a_budget_below_it(monkeypatch):
    monkeypatch.setattr("langchain_aws.ChatBedrockConverse", _Cap)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(settings, "THINKING_BUDGET_TOKENS", 32767)
    from app.agents.model_factory import build_model

    build_model("eu.anthropic.claude-sonnet-4-6")
    assert _Cap.last["max_tokens"] == 128000
    assert (
        _Cap.last["additional_model_request_fields"]["thinking"]["budget_tokens"]
        == 127999
    )
    assert _Cap.last["config"].read_timeout == 1800

    build_model("global.openai.gpt-5.6-luna")  # not listed: unchanged global cap
    assert _Cap.last["max_tokens"] == settings.MAX_OUTPUT_TOKENS == 32768

    build_model("eu.anthropic.claude-sonnet-4-6", max_tokens=4096)  # explicit cap wins
    assert _Cap.last["max_tokens"] == 4096
