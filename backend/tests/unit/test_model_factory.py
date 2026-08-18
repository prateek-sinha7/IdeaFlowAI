"""tests/unit/test_model_factory.py — build_model() provider selection + model_identifier().

Covers the full branch matrix:

  * Anthropic tier (tier 1), Bedrock tier (tier 2), Mistral fallback tier (tier 3).
  * Tier ordering: Bedrock wins over Mistral.
  * The explicit ``provider="mistral"`` opt-in — forces that provider regardless
    of Anthropic/Bedrock config, and fails loudly (no silent fallback) when
    MISTRAL_API_KEY is unset.
  * ``model_identifier()``'s provider-shape fallback chain.

All chat-model constructors are mocked — zero network calls, zero real credentials.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.agents.model_factory import (
    ModelConfigurationError,
    build_model,
    model_identifier,
)
from app.core.config import settings


# ---------------------------------------------------------------------------
# Settings field surface (MISTRAL_API_KEY / MISTRAL_MODEL_ID)
# ---------------------------------------------------------------------------


def test_mistral_settings_fields_have_expected_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings declares MISTRAL_API_KEY / MISTRAL_MODEL_ID with the documented
    defaults, alongside the existing Anthropic/Bedrock fields."""
    from app.core.config import Settings

    # _env_file=None only skips the .env FILE — a real shell env var would still
    # win, so explicitly clear it too (this test asserts the CODE default, not
    # "whatever happens to be exported in the developer's shell").
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    fresh = Settings(_env_file=None)
    assert fresh.MISTRAL_API_KEY == ""
    assert fresh.MISTRAL_MODEL_ID == "mistral-small-latest"


def test_mistral_api_key_resolves_from_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """MISTRAL_API_KEY resolves via pydantic-settings' standard env-var loading —
    no bespoke bridging code (unlike the Bedrock bearer-token special case in
    model_factory.py)."""
    from app.core.config import Settings

    monkeypatch.setenv("MISTRAL_API_KEY", "env-supplied-mistral-key")
    fresh = Settings(_env_file=None)
    assert fresh.MISTRAL_API_KEY == "env-supplied-mistral-key"


@pytest.fixture(autouse=True)
def _clear_provider_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every test from a clean slate: no provider configured.

    Each test opts back in to whichever provider(s) it needs via monkeypatch,
    so tests never leak configuration into one another regardless of order.
    """
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(settings, "BEDROCK_INFERENCE_PROFILE_ID", "")
    monkeypatch.setattr(settings, "BEDROCK_MODEL_ID", "")
    monkeypatch.setattr(settings, "AWS_REGION", "eu-central-1")
    monkeypatch.setattr(settings, "MISTRAL_API_KEY", "")
    monkeypatch.setattr(settings, "MISTRAL_MODEL_ID", "mistral-small-latest")
    monkeypatch.setattr(settings, "AWS_BEARER_TOKEN_BEDROCK", "")


def _mock_chat_anthropic(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock_cls = MagicMock(name="ChatAnthropic")
    monkeypatch.setattr("langchain_anthropic.ChatAnthropic", mock_cls)
    return mock_cls


def _mock_chat_bedrock(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock_cls = MagicMock(name="ChatBedrockConverse")
    monkeypatch.setattr("langchain_aws.ChatBedrockConverse", mock_cls)
    return mock_cls


def _mock_chat_mistral(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock_cls = MagicMock(name="ChatMistralAI")
    monkeypatch.setattr("langchain_mistralai.ChatMistralAI", mock_cls)
    return mock_cls


# ---------------------------------------------------------------------------
# Tier 1 — Anthropic
# ---------------------------------------------------------------------------


def test_anthropic_tier_used_when_key_set(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_cls = _mock_chat_anthropic(monkeypatch)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "fake-anthropic-key")

    result = build_model()

    mock_cls.assert_called_once()
    assert result is mock_cls.return_value
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["api_key"] == "fake-anthropic-key"


# ---------------------------------------------------------------------------
# Tier 2 — Bedrock
# ---------------------------------------------------------------------------


def test_bedrock_tier_used_when_no_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_cls = _mock_chat_bedrock(monkeypatch)
    monkeypatch.setattr(settings, "BEDROCK_MODEL_ID", "anthropic.claude-haiku-4-5-20251001-v1:0")

    result = build_model()

    mock_cls.assert_called_once()
    assert result is mock_cls.return_value


# ---------------------------------------------------------------------------
# Tier 3 — Mistral fallback
# ---------------------------------------------------------------------------


def test_mistral_fallback_used_when_nothing_else_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_cls = _mock_chat_mistral(monkeypatch)
    monkeypatch.setattr(settings, "MISTRAL_API_KEY", "fake-mistral-key")

    result = build_model(model="mistral-medium-latest")  # deliberately != the default, proves override wins

    mock_cls.assert_called_once_with(
        model="mistral-medium-latest",
        api_key="fake-mistral-key",
        timeout=settings.LLM_CALL_TIMEOUT_SECONDS,
    )
    assert result is mock_cls.return_value


def test_mistral_fallback_uses_default_model_id(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_cls = _mock_chat_mistral(monkeypatch)
    monkeypatch.setattr(settings, "MISTRAL_API_KEY", "fake-mistral-key")

    build_model()

    mock_cls.assert_called_once_with(
        model="mistral-small-latest",
        api_key="fake-mistral-key",
        timeout=settings.LLM_CALL_TIMEOUT_SECONDS,
    )


def test_bedrock_wins_over_mistral_fallback_tier(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tier 2 (Bedrock) must win over tier 3 (Mistral) when both are configured."""
    bedrock_cls = _mock_chat_bedrock(monkeypatch)
    mistral_cls = _mock_chat_mistral(monkeypatch)
    monkeypatch.setattr(settings, "BEDROCK_MODEL_ID", "anthropic.claude-haiku-4-5-20251001-v1:0")
    monkeypatch.setattr(settings, "MISTRAL_API_KEY", "fake-mistral-key")

    result = build_model()

    bedrock_cls.assert_called_once()
    mistral_cls.assert_not_called()
    assert result is bedrock_cls.return_value


# ---------------------------------------------------------------------------
# Nothing configured → ModelConfigurationError
# ---------------------------------------------------------------------------


def test_nothing_configured_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ModelConfigurationError, match="MISTRAL_API_KEY") as exc_info:
        build_model()
    assert "ANTHROPIC_API_KEY" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Explicit provider="mistral" opt-in
# ---------------------------------------------------------------------------


def test_explicit_provider_mistral_overrides_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    """provider='mistral' must force Mistral even when ANTHROPIC_API_KEY is set —
    this is the "only use Mistral for evals, keep the rest as-is" guarantee."""
    anthropic_cls = _mock_chat_anthropic(monkeypatch)
    mistral_cls = _mock_chat_mistral(monkeypatch)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "fake-anthropic-key")
    monkeypatch.setattr(settings, "MISTRAL_API_KEY", "fake-mistral-key")

    result = build_model(model="mistral-medium-latest", provider="mistral")

    mistral_cls.assert_called_once_with(
        model="mistral-medium-latest",
        api_key="fake-mistral-key",
        timeout=settings.LLM_CALL_TIMEOUT_SECONDS,
    )
    anthropic_cls.assert_not_called()
    assert result is mistral_cls.return_value


def test_explicit_provider_mistral_overrides_bedrock(monkeypatch: pytest.MonkeyPatch) -> None:
    """The explicit opt-in beats a configured higher tier, not just an unconfigured one."""
    bedrock_cls = _mock_chat_bedrock(monkeypatch)
    mistral_cls = _mock_chat_mistral(monkeypatch)
    monkeypatch.setattr(settings, "BEDROCK_MODEL_ID", "anthropic.claude-haiku-4-5-20251001-v1:0")
    monkeypatch.setattr(settings, "MISTRAL_API_KEY", "fake-mistral-key")

    build_model(provider="mistral")

    mistral_cls.assert_called_once()
    bedrock_cls.assert_not_called()


def test_explicit_provider_mistral_without_key_raises_immediately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No silent fallback to Anthropic/Bedrock even if they ARE configured — an
    explicit provider='mistral' request with no MISTRAL_API_KEY must fail loudly."""
    anthropic_cls = _mock_chat_anthropic(monkeypatch)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "fake-anthropic-key")
    # MISTRAL_API_KEY stays "" (cleared by the autouse fixture)

    with pytest.raises(ModelConfigurationError, match="provider='mistral'"):
        build_model(provider="mistral")

    anthropic_cls.assert_not_called()


def test_provider_none_is_unaffected_by_mistral_key_presence(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression guard: every existing call site omits `provider` — confirm
    that with provider=None (the default), behavior is identical whether or
    not MISTRAL_API_KEY happens to be set, as long as Anthropic resolves."""
    anthropic_cls = _mock_chat_anthropic(monkeypatch)
    _mock_chat_mistral(monkeypatch)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "fake-anthropic-key")
    monkeypatch.setattr(settings, "MISTRAL_API_KEY", "fake-mistral-key")

    result = build_model()

    anthropic_cls.assert_called_once()
    assert result is anthropic_cls.return_value


# ---------------------------------------------------------------------------
# model_identifier()
# ---------------------------------------------------------------------------


def test_model_identifier_bedrock_shape() -> None:
    llm = MagicMock(spec=["model_id"])
    llm.model_id = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
    assert model_identifier(llm) == "eu.anthropic.claude-haiku-4-5-20251001-v1:0"


def test_model_identifier_anthropic_shape() -> None:
    llm = MagicMock(spec=["model"])
    llm.model = "claude-haiku-4-5-20251001"
    assert model_identifier(llm) == "claude-haiku-4-5-20251001"


def test_model_identifier_mistral_shape() -> None:
    """ChatMistralAI exposes `.model`, the same attribute name as ChatAnthropic."""
    llm = MagicMock(spec=["model"])
    llm.model = "mistral-small-latest"
    assert model_identifier(llm) == "mistral-small-latest"


def test_model_identifier_model_name_shape() -> None:
    """The `.model_name` leg of the fallback chain, for any provider that aliases
    the `model=` constructor kwarg to that field instead of `.model`/`.model_id`."""
    llm = MagicMock(spec=["model_name"])
    llm.model_name = "some-provider-model-id"
    assert model_identifier(llm) == "some-provider-model-id"


def test_model_identifier_unknown_shape() -> None:
    llm = MagicMock(spec=[])
    assert model_identifier(llm) == "unknown"
