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

import base64 as _b64
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.agents.model_factory import (
    BedrockTokenDecodeError,
    ModelConfigurationError,
    build_model,
    decode_bedrock_bearer_token_expiry,
    model_identifier,
    preflight_check_provider,
)
from app.core.config import settings


# ---------------------------------------------------------------------------
# Settings field surface (MISTRAL_API_KEY / MISTRAL_MODEL_ID)
# ---------------------------------------------------------------------------


def test_mistral_settings_fields_have_expected_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    monkeypatch.setattr(
        settings, "BEDROCK_MODEL_ID", "anthropic.claude-haiku-4-5-20251001-v1:0"
    )

    result = build_model()

    mock_cls.assert_called_once()
    assert result is mock_cls.return_value


# ---------------------------------------------------------------------------
# Tier 3 — Mistral fallback
# ---------------------------------------------------------------------------


def test_mistral_fallback_used_when_nothing_else_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_cls = _mock_chat_mistral(monkeypatch)
    monkeypatch.setattr(settings, "MISTRAL_API_KEY", "fake-mistral-key")

    result = build_model(
        model="mistral-medium-latest"
    )  # deliberately != the default, proves override wins

    mock_cls.assert_called_once_with(
        model="mistral-medium-latest",
        api_key="fake-mistral-key",
        timeout=settings.LLM_CALL_TIMEOUT_SECONDS,
    )
    assert result is mock_cls.return_value


def test_mistral_fallback_uses_default_model_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_cls = _mock_chat_mistral(monkeypatch)
    monkeypatch.setattr(settings, "MISTRAL_API_KEY", "fake-mistral-key")

    build_model()

    mock_cls.assert_called_once_with(
        model="mistral-small-latest",
        api_key="fake-mistral-key",
        timeout=settings.LLM_CALL_TIMEOUT_SECONDS,
    )


def test_bedrock_wins_over_mistral_fallback_tier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tier 2 (Bedrock) must win over tier 3 (Mistral) when both are configured."""
    bedrock_cls = _mock_chat_bedrock(monkeypatch)
    mistral_cls = _mock_chat_mistral(monkeypatch)
    monkeypatch.setattr(
        settings, "BEDROCK_MODEL_ID", "anthropic.claude-haiku-4-5-20251001-v1:0"
    )
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


def test_explicit_provider_mistral_overrides_anthropic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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


def test_explicit_provider_mistral_overrides_bedrock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The explicit opt-in beats a configured higher tier, not just an unconfigured one."""
    bedrock_cls = _mock_chat_bedrock(monkeypatch)
    mistral_cls = _mock_chat_mistral(monkeypatch)
    monkeypatch.setattr(
        settings, "BEDROCK_MODEL_ID", "anthropic.claude-haiku-4-5-20251001-v1:0"
    )
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


def test_provider_none_is_unaffected_by_mistral_key_presence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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


# ---------------------------------------------------------------------------
# A4 (STABILIZATION.md) — Bedrock bearer-token expiry decode + launch preflight
# ---------------------------------------------------------------------------


def _make_bearer_token(issued_at: "datetime", expires_seconds: int) -> str:
    """Build a syntactically-real ``bedrock-api-key-`` token around a KNOWN,
    fabricated date — never a real credential."""
    payload = (
        "X-Amz-Algorithm=AWS4-HMAC-SHA256"
        "&X-Amz-Credential=AKIAFAKE%2F20260101%2Feu-central-1%2Fbedrock%2Faws4_request"
        f"&X-Amz-Date={issued_at.strftime('%Y%m%dT%H%M%SZ')}"
        f"&X-Amz-Expires={expires_seconds}"
        "&X-Amz-SignedHeaders=host"
        "&X-Amz-Signature=deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
    )
    return "bedrock-api-key-" + _b64.b64encode(payload.encode()).decode()


class TestDecodeBedrockBearerTokenExpiry:
    def test_decodes_known_date_and_ttl(self) -> None:
        issued = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        token = _make_bearer_token(issued, 3600)

        expiry = decode_bedrock_bearer_token_expiry(token)

        assert expiry == datetime(2026, 1, 1, 1, 0, 0, tzinfo=timezone.utc)

    def test_rejects_wrong_prefix(self) -> None:
        with pytest.raises(BedrockTokenDecodeError):
            decode_bedrock_bearer_token_expiry("sk-not-a-bedrock-token")

    def test_rejects_empty_token(self) -> None:
        with pytest.raises(BedrockTokenDecodeError):
            decode_bedrock_bearer_token_expiry("")

    def test_rejects_unparseable_base64(self) -> None:
        with pytest.raises(BedrockTokenDecodeError):
            decode_bedrock_bearer_token_expiry("bedrock-api-key-!!!not-base64!!!")

    def test_rejects_payload_missing_expiry_fields(self) -> None:
        payload = "X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-SignedHeaders=host"
        token = "bedrock-api-key-" + _b64.b64encode(payload.encode()).decode()
        with pytest.raises(BedrockTokenDecodeError):
            decode_bedrock_bearer_token_expiry(token)


class TestPreflightCheckProvider:
    def test_no_bearer_token_configured_passes(self) -> None:
        ok, message = preflight_check_provider()
        assert ok is True
        assert message is None

    def test_anthropic_key_set_skips_bedrock_token_check(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """build_model() always prefers ANTHROPIC_API_KEY over Bedrock — a stale/
        expired bearer token sitting in the env is irrelevant to this run."""
        expired = datetime.now(timezone.utc) - timedelta(hours=2)
        monkeypatch.setattr(
            settings, "AWS_BEARER_TOKEN_BEDROCK", _make_bearer_token(expired, 60)
        )
        monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "fake-anthropic-key")

        ok, message = preflight_check_provider()

        assert ok is True
        assert message is None

    def test_valid_unexpired_token_passes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        issued = datetime.now(timezone.utc) - timedelta(minutes=5)
        monkeypatch.setattr(
            settings, "AWS_BEARER_TOKEN_BEDROCK", _make_bearer_token(issued, 3600)
        )

        ok, message = preflight_check_provider()

        assert ok is True
        assert message is None

    def test_expired_token_rejects_with_actionable_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        issued = datetime.now(timezone.utc) - timedelta(hours=2)
        monkeypatch.setattr(
            settings, "AWS_BEARER_TOKEN_BEDROCK", _make_bearer_token(issued, 60)
        )

        ok, message = preflight_check_provider()

        assert ok is False
        assert "expired at" in message
        assert "AWS_BEARER_TOKEN_BEDROCK" in message
        assert "restart the backend" in message

    def test_token_within_skew_window_rejects(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A token with 10s of nominal life left is treated as already-expired
        (60s skew) — a run that takes even a few seconds to actually start
        would otherwise launch on a token that's dead before the first call."""
        issued = datetime.now(timezone.utc) - timedelta(seconds=50)
        monkeypatch.setattr(
            settings, "AWS_BEARER_TOKEN_BEDROCK", _make_bearer_token(issued, 60)
        )

        ok, _message = preflight_check_provider()

        assert ok is False

    def test_undecodable_token_does_not_block_launch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unrecognized token shape degrades to "don't block" rather than
        failing every launch on a decode gap this function didn't anticipate."""
        monkeypatch.setattr(
            settings,
            "AWS_BEARER_TOKEN_BEDROCK",
            "bedrock-api-key-not-a-real-payload-shape",
        )

        ok, message = preflight_check_provider()

        assert ok is True
        assert message is None


# ---------------------------------------------------------------------------
# T12 — spec 020 reasoning payload guards (SC-02…SC-05, SC-08)
#
# Every assertion below reads the kwargs ChatBedrockConverse was CONSTRUCTED
# with — the actual request payload. Asserting on the effort string that went in
# would pass on a feature whose mapping layer is entirely broken.
# ---------------------------------------------------------------------------

LUNA = "global.openai.gpt-5.6-luna"
SOL = "global.openai.gpt-5.6-sol"
HAIKU_45 = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
SONNET_5 = "us.anthropic.claude-sonnet-5"


def _bedrock_fields(
    monkeypatch: pytest.MonkeyPatch, model: str, **kwargs
) -> dict | None:
    """Build on the Bedrock tier and return additional_model_request_fields."""
    mock_cls = _mock_chat_bedrock(monkeypatch)
    monkeypatch.setattr(settings, "BEDROCK_MODEL_ID", model)
    build_model(model, max_tokens=32768, **kwargs)
    return mock_cls.call_args.kwargs.get("additional_model_request_fields")


def test_sc02_gpt_effort_becomes_nested_reasoning_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SC-02 — Sol + High produces exactly {"reasoning": {"effort": "high"}}.

    The nesting is not cosmetic: verified live against bedrock-runtime in
    eu-north-1 (spec §12), a FLAT ``reasoning_effort`` is rejected with
    ValidationException: unknown_parameter.
    """
    assert _bedrock_fields(monkeypatch, SOL, effort="high") == {
        "reasoning": {"effort": "high"}
    }


@pytest.mark.parametrize("level", ["none", "low", "medium", "high", "xhigh", "max"])
def test_sc02_every_gpt_level_round_trips(
    monkeypatch: pytest.MonkeyPatch, level: str
) -> None:
    """All six levels the catalog advertises for GPT reach the payload verbatim.

    Bedrock accepts exactly this set and rejects anything else (spec §12), so a
    level silently dropped here is a 400 at run time, not a degraded request.
    """
    assert _bedrock_fields(monkeypatch, LUNA, effort=level) == {
        "reasoning": {"effort": level}
    }


def test_sc03_claude_never_sends_reasoning(monkeypatch: pytest.MonkeyPatch) -> None:
    """SC-03 — the same step switched to Haiku 4.5 sends `thinking`, never `reasoning`."""
    fields = _bedrock_fields(monkeypatch, HAIKU_45, effort="on")
    assert "reasoning" not in fields
    assert fields == {"thinking": {"type": "enabled", "budget_tokens": 32767}}


def test_sc03_claude_effort_none_disables_thinking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Effort=None on a Claude model is the UI's "off" — it must actively
    disable thinking, not merely omit the field (adaptive models default ON)."""
    assert _bedrock_fields(monkeypatch, SONNET_5, effort="none") == {
        "thinking": {"type": "disabled"}
    }


def test_sc03_gpt_level_on_claude_is_dropped_not_forwarded(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A stale `xhigh` left on a step whose model was switched to Claude must be
    dropped with a warning — forwarding it would send Bedrock a level Claude has
    no concept of."""
    with caplog.at_level("WARNING", logger="app.agents.model_factory"):
        fields = _bedrock_fields(monkeypatch, HAIKU_45, effort="xhigh")
    assert fields == {"thinking": {"type": "enabled", "budget_tokens": 32767}}
    assert "is not offered by" in caplog.text and "xhigh" in caplog.text


def test_sc04_reasoning_mode_none_sends_no_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SC-04 — a model with reasoning mode "none" sends no field at ANY effort.

    Haiku 3.5 was the only catalog model in this mode and was removed on
    2026-09-22 (AWS serves it in no form in eu-north-1). The MODE is still live
    in ``reasoning_fields``, so it is pinned here with a synthetic entry rather
    than deleted along with the model — otherwise the next model that needs it
    ships on an untested branch.
    """
    import dataclasses

    from agents.capabilities import model_catalog as mc

    real = mc.ModelCatalog().get(HAIKU_45)
    assert real is not None
    silent = dataclasses.replace(
        real, reasoning=mc.Reasoning(mode="none", levels=(), default_effort=None)
    )
    monkeypatch.setattr(mc.ModelCatalog, "resolve", lambda self, mid: silent)

    assert _bedrock_fields(monkeypatch, HAIKU_45) is None
    assert _bedrock_fields(monkeypatch, HAIKU_45, effort="high") is None
    assert _bedrock_fields(monkeypatch, HAIKU_45, effort="none") is None


# SC-05 — INV-3 parity. Recorded by replaying build_model() over every catalog id
# against the PRE-CHANGE tree (main @ 049a8c3a4) — this is measured output, not a
# restatement of the new code's intent. 21 of the 24 (model × disable_thinking)
# combinations are byte-identical; the 3 that are not are listed in
# _PARITY_EXCEPTIONS with the criterion that authorises each.
_PRE_CHANGE_FIELDS: dict[str, dict | None] = {
    HAIKU_45: {"thinking": {"type": "enabled", "budget_tokens": 32767}},
    "us.anthropic.claude-haiku-4-5-20251001-v1:0": {
        "thinking": {"type": "enabled", "budget_tokens": 32767}
    },
    "eu.anthropic.claude-sonnet-4-5-20250929-v1:0": {
        "thinking": {"type": "enabled", "budget_tokens": 32767}
    },
    "eu.anthropic.claude-sonnet-4-6": {
        "thinking": {"type": "enabled", "budget_tokens": 32767}
    },
    "eu.anthropic.claude-sonnet-4-20250514-v1:0": {
        "thinking": {"type": "enabled", "budget_tokens": 32767}
    },
    "eu.anthropic.claude-opus-4-5-20251101-v1:0": {
        "thinking": {"type": "enabled", "budget_tokens": 32767}
    },
    "eu.anthropic.claude-opus-4-6-v1": {
        "thinking": {"type": "enabled", "budget_tokens": 32767}
    },
    SONNET_5: {"thinking": {"type": "adaptive"}},
    "eu.anthropic.claude-sonnet-5": {"thinking": {"type": "adaptive"}},
}

HAIKU_55 = "eu.anthropic.claude-haiku-5-5"
SONNET_55 = "eu.anthropic.claude-sonnet-5-5"

# id → (the request an unset effort produces, the decision that authorises it).
# Every model here either did not exist pre-change or deliberately sends its
# catalog ``default_effort`` explicitly, so it has no pre-change payload to match.
_PARITY_EXCEPTIONS: dict[str, tuple[dict, str]] = {
    LUNA: (
        {"reasoning": {"effort": "medium"}},
        "default_effort=medium — the provider's own default, now sent explicitly",
    ),
    SOL: (
        {"reasoning": {"effort": "medium"}},
        "default_effort=medium — the provider's own default, now sent explicitly",
    ),
    HAIKU_55: (
        {
            "thinking": {"type": "adaptive", "display": "summarized"},
            "output_config": {"effort": "xhigh"},
        },
        "new model; default_effort=xhigh, summarized thinking so the tab has text",
    ),
    SONNET_55: (
        {
            "thinking": {"type": "adaptive", "display": "summarized"},
            "output_config": {"effort": "high"},
        },
        "new model; default_effort=high (provider default), summarized thinking",
    ),
}


def test_sc05_every_catalog_model_is_byte_identical_without_an_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SC-05 / INV-3 — a step that sets no effort must produce the request it
    produced before spec 020, for EVERY model in the catalog — except the models
    listed in ``_PARITY_EXCEPTIONS``, each pinned to its own decided request.

    A regression here means existing runs changed behaviour silently.
    """
    from agents.capabilities.model_catalog import ModelCatalog

    checked = 0
    for entry in ModelCatalog().list():
        actual = _bedrock_fields(monkeypatch, entry.id)  # no effort — today's path
        if entry.id in _PARITY_EXCEPTIONS:
            expected, reason = _PARITY_EXCEPTIONS[entry.id]
            assert actual == expected, f"{entry.id} ({reason}): got {actual}"
        else:
            assert entry.id in _PRE_CHANGE_FIELDS, (
                f"{entry.id} is new to the catalog but has no recorded pre-change payload and no "
                f"entry in _PARITY_EXCEPTIONS. Record one or the other — an unlisted model is an "
                f"unverified parity claim."
            )
            assert (
                actual == _PRE_CHANGE_FIELDS[entry.id]
            ), f"parity broken for {entry.id}"
        checked += 1
    assert (
        checked == 13
    ), f"catalog changed size ({checked}); re-record the parity fixture"


def test_sc05_disable_thinking_parity_holds_for_adaptive_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The adaptive quirk that FIX-era code encoded by substring: an adaptive
    model under disable_thinking must send an explicit {"type": "disabled"},
    because omitting the field leaves adaptive thinking ON."""
    assert _bedrock_fields(monkeypatch, SONNET_5, disable_thinking=True) == {
        "thinking": {"type": "disabled"}
    }
    # Budget-mode models omit the field entirely — also unchanged.
    assert _bedrock_fields(monkeypatch, HAIKU_45, disable_thinking=True) is None


def test_sc08_gpt_fallback_rebuilt_on_claude_sends_thinking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SC-08 — when a GPT step is throttled into its fallback chain and rebuilds
    on a Claude model, the payload follows the model it ACTUALLY ran on.

    The effort travels with the step, so the same `high` that was a
    `reasoning.effort` on Sol must become a `thinking` block on Haiku — the
    mapping is keyed on the model, not on what the step asked for.
    """
    assert _bedrock_fields(monkeypatch, SOL, effort="high") == {
        "reasoning": {"effort": "high"}
    }
    assert _bedrock_fields(monkeypatch, HAIKU_45, effort="high") == {
        "thinking": {"type": "enabled", "budget_tokens": 32767}
    }


def test_temperature_pinned_only_when_thinking_is_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bedrock requires temperature=1 when extended thinking is on, and GPT's
    reasoning.effort is NOT extended thinking — pinning temperature there would
    silently change sampling for every GPT run."""
    mock_cls = _mock_chat_bedrock(monkeypatch)
    monkeypatch.setattr(settings, "BEDROCK_MODEL_ID", HAIKU_45)
    build_model(HAIKU_45, max_tokens=32768)
    assert mock_cls.call_args.kwargs.get("temperature") == 1

    mock_cls = _mock_chat_bedrock(monkeypatch)
    build_model(SOL, max_tokens=32768, effort="high")
    assert "temperature" not in mock_cls.call_args.kwargs


# ---------------------------------------------------------------------------
# Claude 5.5 family — real effort levels, catalog default effort, display
#
# The AWS adaptive-thinking guide is the contract: the level rides in a SEPARATE
# ``output_config`` object (inside ``thinking`` is a ValidationException), and
# with thinking disabled Bedrock caps effort at "high" (xhigh/max → 400).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("level", ["low", "medium", "high", "xhigh", "max"])
def test_build_model_sends_output_config_effort_when_5_5_level_set(
    monkeypatch: pytest.MonkeyPatch, level: str
) -> None:
    # Arrange + Act
    fields = _bedrock_fields(monkeypatch, SONNET_55, effort=level)
    # Assert: the level is outside ``thinking``, verbatim.
    assert fields == {
        "thinking": {"type": "adaptive", "display": "summarized"},
        "output_config": {"effort": level},
    }


def test_build_model_uses_catalog_default_when_legacy_on_effort_on_5_5(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # Arrange: "on" was the only Claude level before the 5.5 family offered levels.
    with caplog.at_level("WARNING", logger="app.agents.model_factory"):
        # Act
        fields = _bedrock_fields(monkeypatch, HAIKU_55, effort="on")
    # Assert: treated as "the model's default" (xhigh), silently — not dropped.
    assert fields == {
        "thinking": {"type": "adaptive", "display": "summarized"},
        "output_config": {"effort": "xhigh"},
    }
    assert "is not offered by" not in caplog.text


def test_build_model_disables_thinking_when_5_5_effort_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _bedrock_fields(monkeypatch, HAIKU_55, effort="none") == {
        "thinking": {"type": "disabled"}
    }


def test_build_model_sends_no_default_effort_when_thinking_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A one-shot classifier call must stay as small as it was: no default level.
    assert _bedrock_fields(monkeypatch, HAIKU_55, disable_thinking=True) == {
        "thinking": {"type": "disabled"}
    }
    assert _bedrock_fields(monkeypatch, LUNA, disable_thinking=True) is None


@pytest.mark.parametrize("level", ["low", "medium", "high"])
def test_build_model_keeps_explicit_effort_when_thinking_disabled(
    monkeypatch: pytest.MonkeyPatch, level: str
) -> None:
    assert _bedrock_fields(
        monkeypatch, HAIKU_55, effort=level, disable_thinking=True
    ) == {"thinking": {"type": "disabled"}, "output_config": {"effort": level}}


@pytest.mark.parametrize("level", ["xhigh", "max"])
def test_build_model_caps_effort_at_high_when_thinking_disabled(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, level: str
) -> None:
    with caplog.at_level("WARNING", logger="app.agents.model_factory"):
        fields = _bedrock_fields(
            monkeypatch, HAIKU_55, effort=level, disable_thinking=True
        )
    assert fields == {
        "thinking": {"type": "disabled"},
        "output_config": {"effort": "high"},
    }
    assert "capping at 'high'" in caplog.text


def test_build_model_sends_no_default_effort_when_global_thinking_switch_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # THINKING_BUDGET_TOKENS <= 0 is the operator's "send nothing extra" switch.
    monkeypatch.setattr(settings, "THINKING_BUDGET_TOKENS", 0)
    assert _bedrock_fields(monkeypatch, HAIKU_55) is None
    assert _bedrock_fields(monkeypatch, LUNA) is None


def test_build_model_passes_effort_to_chat_anthropic_when_5_5_level_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange: the local-dev Anthropic-direct path.
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-test")
    mock_cls = _mock_chat_anthropic(monkeypatch)
    # Act
    build_model("claude-haiku-5-5", max_tokens=32768, effort="low")
    # Assert: ChatAnthropic takes effort as its own field; display stays on thinking.
    kwargs = mock_cls.call_args.kwargs
    assert kwargs["effort"] == "low"
    assert kwargs["thinking"]["display"] == "summarized"
    assert kwargs["temperature"] == 1


def test_build_model_sends_no_effort_to_chat_anthropic_when_model_has_no_levels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-test")
    mock_cls = _mock_chat_anthropic(monkeypatch)
    build_model("claude-haiku-4-5-20251001", max_tokens=32768)
    assert "effort" not in mock_cls.call_args.kwargs


# ---------------------------------------------------------------------------
# force_streaming — stream Claude on Bedrock even when langchain-aws does not
# know the model (1.4.6 lists Claude families only up to 4 and turns streaming
# off for Claude 5). The workflow builder sets it.
# ---------------------------------------------------------------------------


class TestBuildModelForceStreaming:
    # Plan #1 | B1, B2
    @pytest.mark.parametrize(
        "model_id",
        [
            "eu.anthropic.claude-sonnet-5-5",
            "eu.anthropic.claude-haiku-5-5",
            "anthropic.claude-haiku-5-5",
            "anthropic.claude-haiku-4-5-20251001-v1:0",
        ],
        ids=[
            "geo-sonnet-5-5",
            "geo-haiku-5-5",
            "bare-haiku-5-5",
            "versioned-haiku-4-5",
        ],
    )
    def test_build_model_enables_streaming_when_force_streaming_on_bedrock_claude(
        self, monkeypatch: pytest.MonkeyPatch, model_id: str
    ) -> None:
        # Arrange
        mock_cls = _mock_chat_bedrock(monkeypatch)
        monkeypatch.setattr(settings, "BEDROCK_MODEL_ID", model_id)

        # Act
        build_model(model_id, force_streaming=True)

        # Assert
        assert mock_cls.call_args.kwargs["disable_streaming"] is False

    # Plan #2 | B1
    def test_build_model_leaves_streaming_to_library_when_force_streaming_is_omitted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange
        mock_cls = _mock_chat_bedrock(monkeypatch)
        monkeypatch.setattr(settings, "BEDROCK_MODEL_ID", SONNET_55)

        # Act
        build_model(SONNET_55, effort="high")

        # Assert: every other caller keeps the request it had before the option existed.
        assert "disable_streaming" not in mock_cls.call_args.kwargs

    # Plan #3 | B2
    @pytest.mark.parametrize(
        "model_id",
        ["global.openai.gpt-5.6-luna", "amazon.nova-pro-v1:0", "claude-sonnet-5-5"],
        ids=["openai", "amazon-nova", "no-provider-segment"],
    )
    def test_build_model_leaves_streaming_to_library_when_force_streaming_on_non_claude_bedrock_model(
        self, monkeypatch: pytest.MonkeyPatch, model_id: str
    ) -> None:
        # Arrange
        mock_cls = _mock_chat_bedrock(monkeypatch)
        monkeypatch.setattr(settings, "BEDROCK_MODEL_ID", model_id)

        # Act
        build_model(model_id, force_streaming=True)

        # Assert
        assert "disable_streaming" not in mock_cls.call_args.kwargs

    # Plan #4 | B3
    def test_build_model_ignores_force_streaming_when_provider_is_anthropic_direct(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange: ChatAnthropic already streams, so the option has nothing to do.
        monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-test")
        mock_cls = _mock_chat_anthropic(monkeypatch)

        # Act
        build_model("claude-haiku-5-5", force_streaming=True)

        # Assert
        assert "disable_streaming" not in mock_cls.call_args.kwargs

    # Plan #5 | B1
    def test_build_model_kwargs_keep_streaming_on_through_langchain_aws_when_force_streaming_on_claude_5(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Arrange: capture the constructor kwargs (a real client is refused offline,
        # ISS-102), then run them through langchain-aws's own streaming validator.
        # This proves the explicit value beats the library's model table, which
        # on its own turns streaming off for Claude 5.
        from langchain_aws import ChatBedrockConverse

        mock_cls = _mock_chat_bedrock(monkeypatch)
        monkeypatch.setattr(settings, "BEDROCK_MODEL_ID", SONNET_55)
        build_model(SONNET_55, effort="high", force_streaming=True)
        kwargs = dict(mock_cls.call_args.kwargs)

        # Act
        validated = ChatBedrockConverse.set_disable_streaming(kwargs)

        # Assert
        assert validated["disable_streaming"] is False
