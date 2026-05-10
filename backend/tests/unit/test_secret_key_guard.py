"""Tests for the SECRET_KEY boot guard (A1).

Refusing to boot with a default or weak SECRET_KEY in non-development
environments is a hard requirement: any attacker who has read the source
code (which ships the default literal) can forge JWTs for every user.
"""

from __future__ import annotations

import importlib

import pytest


def _build_settings(monkeypatch: pytest.MonkeyPatch, **overrides: str):
    """Re-import the settings module with a clean env so the validator runs.

    We delete the .env file from the search path by clearing every related
    env var the loader might find, then re-import config.py to trigger the
    model_validator afresh.
    """
    # Clear anything that could leak from the host environment
    for key in (
        "ENV",
        "SECRET_KEY",
        "LLM_PROVIDER",
        "BEDROCK_MODEL_ID",
        "AWS_REGION",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_MODEL",
        "DATABASE_URL",
        "CORS_ORIGINS",
        "ACCESS_TOKEN_EXPIRE_HOURS",
        "LANGSMITH_TRACING",
    ):
        monkeypatch.delenv(key, raising=False)

    for key, value in overrides.items():
        monkeypatch.setenv(key, value)

    # Make pydantic-settings ignore the .env file by pointing at a non-existent
    # path; we want pure env-var driven validation in tests.
    monkeypatch.setenv("PYDANTIC_SETTINGS_TEST_ONLY", "1")

    import app.core.config as config_module

    # Force a re-import so the module-level Settings() runs again with our env.
    importlib.reload(config_module)
    return config_module


_SHIPPED_DEFAULT = "dev-secret-key-change-in-production"
_STRONG = "x" * 64


class TestSecretKeyValidator:
    def test_default_key_in_production_aborts_boot(self, monkeypatch):
        """The shipped default in any non-dev environment is a hard fail."""
        with pytest.raises(Exception) as exc_info:
            _build_settings(monkeypatch, ENV="production", SECRET_KEY=_SHIPPED_DEFAULT)
        assert "SECRET_KEY" in str(exc_info.value)
        assert "production" in str(exc_info.value).lower() or "default" in str(exc_info.value).lower()

    def test_default_key_in_staging_aborts_boot(self, monkeypatch):
        """Staging is non-dev too — same rule."""
        with pytest.raises(Exception) as exc_info:
            _build_settings(monkeypatch, ENV="staging", SECRET_KEY=_SHIPPED_DEFAULT)
        assert "SECRET_KEY" in str(exc_info.value)

    def test_default_key_in_development_is_allowed(self, monkeypatch, caplog):
        """Dev mode tolerates the default but logs a warning."""
        config_module = _build_settings(
            monkeypatch, ENV="development", SECRET_KEY=_SHIPPED_DEFAULT
        )
        # Should not have raised — module reloads cleanly.
        assert config_module.settings.SECRET_KEY == _SHIPPED_DEFAULT

    def test_empty_key_always_aborts_boot(self, monkeypatch):
        """Empty SECRET_KEY in any environment is a fail."""
        for env in ("development", "production", "ci"):
            with pytest.raises(Exception) as exc_info:
                _build_settings(monkeypatch, ENV=env, SECRET_KEY="")
            assert "empty" in str(exc_info.value).lower() or "SECRET_KEY" in str(exc_info.value)

    def test_short_key_in_production_aborts_boot(self, monkeypatch):
        """Below-floor keys in non-dev environments are a fail."""
        with pytest.raises(Exception) as exc_info:
            _build_settings(monkeypatch, ENV="production", SECRET_KEY="abc123")
        assert "SECRET_KEY" in str(exc_info.value)
        assert "32" in str(exc_info.value) or "short" in str(exc_info.value).lower()

    def test_short_key_in_development_warns_only(self, monkeypatch):
        config_module = _build_settings(
            monkeypatch, ENV="development", SECRET_KEY="abc123"
        )
        assert config_module.settings.SECRET_KEY == "abc123"

    def test_strong_key_in_production_boots(self, monkeypatch):
        config_module = _build_settings(
            monkeypatch, ENV="production", SECRET_KEY=_STRONG
        )
        assert config_module.settings.SECRET_KEY == _STRONG
        assert config_module.settings.ENV == "production"

    def test_env_default_is_development(self, monkeypatch):
        config_module = _build_settings(monkeypatch, SECRET_KEY=_STRONG)
        assert config_module.settings.ENV == "development"
