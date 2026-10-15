"""ISS-1133 (QA-KB-107) - preflight_check_provider must honour USE_LOCAL_OLLAMA.

Siblings from the same analysis: ISS-1135 (the preflight's Mistral-fallback rung) and
ISS-1134 (SmartPlanner's own copy of the provider chain).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.agents.model_factory import preflight_check_provider
from app.core.config import settings

from .test_model_factory import _make_bearer_token


@pytest.mark.issue("ISS-1133")
@pytest.mark.parametrize("flag", ["1", "true"])
def test_expired_bedrock_token_does_not_block_launch_when_ollama_on(
    monkeypatch: pytest.MonkeyPatch, flag: str
) -> None:
    """ISS-1133 - with USE_LOCAL_OLLAMA on, build_model never touches Bedrock,
    so an expired bearer token must not fail the launch preflight."""
    expired = datetime.now(timezone.utc) - timedelta(hours=2)
    monkeypatch.setattr(
        settings, "AWS_BEARER_TOKEN_BEDROCK", _make_bearer_token(expired, 60)
    )
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("USE_LOCAL_OLLAMA", flag)

    ok, message = preflight_check_provider()

    assert ok is True, message
    assert message is None


@pytest.mark.issue("ISS-1133")
def test_flag_set_only_in_the_env_file_is_honoured(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """ISS-1133 - on the reporting machine the flag lives only in backend/.env, never
    in os.environ, so a check that reads os.environ alone misses it."""
    env_file = tmp_path / ".env"
    env_file.write_text("USE_LOCAL_OLLAMA=1\n")
    monkeypatch.setattr("app.core.config.ENV_FILE", env_file)
    monkeypatch.delenv("USE_LOCAL_OLLAMA", raising=False)
    expired = datetime.now(timezone.utc) - timedelta(hours=2)
    monkeypatch.setattr(
        settings, "AWS_BEARER_TOKEN_BEDROCK", _make_bearer_token(expired, 60)
    )
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(settings, "MISTRAL_API_KEY", "")

    assert preflight_check_provider() == (True, None)


@pytest.mark.issue("ISS-1135")
def test_expired_bedrock_token_does_not_block_the_mistral_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ISS-1135 - with Bedrock unconfigured and MISTRAL_API_KEY set, build_model falls
    back to ChatMistralAI and never touches Bedrock. The same config without the key
    must still refuse: test_model_factory.py::TestPreflightCheckProvider covers that."""
    expired = datetime.now(timezone.utc) - timedelta(hours=2)
    monkeypatch.setattr(
        settings, "AWS_BEARER_TOKEN_BEDROCK", _make_bearer_token(expired, 60)
    )
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(settings, "BEDROCK_INFERENCE_PROFILE_ID", "")
    monkeypatch.setattr(settings, "BEDROCK_MODEL_ID", "")
    monkeypatch.setattr(settings, "MISTRAL_API_KEY", "m")
    monkeypatch.setenv("USE_LOCAL_OLLAMA", "0")

    assert preflight_check_provider() == (True, None)


@pytest.mark.issue("ISS-1134")
def test_smart_planner_builds_the_local_model_when_ollama_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ISS-1134 - with USE_LOCAL_OLLAMA on, the planner's model is the local one every
    other call gets, not its own Bedrock client."""
    from agents.planner.smart_planner import SmartPlanner

    ollama = MagicMock(name="ChatOllama")
    bedrock = MagicMock(name="ChatBedrockConverse")
    monkeypatch.setattr("langchain_ollama.ChatOllama", ollama)
    monkeypatch.setattr("langchain_aws.ChatBedrockConverse", bedrock)
    monkeypatch.setattr(
        "app.agents.model_factory._restore_ollama_string_tool_args", lambda: None
    )
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(settings, "AWS_BEARER_TOKEN_BEDROCK", "")
    monkeypatch.setenv("USE_LOCAL_OLLAMA", "1")

    SmartPlanner()

    ollama.assert_called_once()
    bedrock.assert_not_called()


@pytest.mark.issue("ISS-1134")
def test_smart_planner_keeps_its_own_client_when_ollama_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ISS-1134 control - with the override off the planner's own Bedrock exit runs
    as before (INV-3): build_model is not consulted and ChatOllama is never built."""
    from agents.planner.smart_planner import SmartPlanner

    ollama = MagicMock(name="ChatOllama")
    bedrock = MagicMock(name="ChatBedrockConverse")
    build_model = MagicMock(name="build_model")
    monkeypatch.setattr("langchain_ollama.ChatOllama", ollama)
    monkeypatch.setattr("langchain_aws.ChatBedrockConverse", bedrock)
    monkeypatch.setattr("app.agents.model_factory.build_model", build_model)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(settings, "AWS_BEARER_TOKEN_BEDROCK", "")
    monkeypatch.setenv("USE_LOCAL_OLLAMA", "0")

    SmartPlanner()

    build_model.assert_not_called()
    ollama.assert_not_called()
    bedrock.assert_called_once()
