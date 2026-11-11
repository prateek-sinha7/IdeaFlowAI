"""Unit tests for app/core/config.py — GLOBAL_SKILLS_ROOT normalisation."""

from __future__ import annotations

import logging

import pytest
from cryptography.fernet import Fernet

from app.core.config import ConnectorsMisconfigured, Settings

# The validator is called directly. Constructing Settings (even via
# model_validate) reads the process env and backend/.env in this
# pydantic-settings version, and a unit test must not depend on either.


def test_normalize_global_skills_root_strips_whitespace_when_value_padded():
    # Act
    normalized = Settings._normalize_global_skills_root(
        "  /app/builtin-skills/global\n"
    )

    # Assert
    assert normalized == "/app/builtin-skills/global"


def test_normalize_global_skills_root_returns_empty_when_value_none():
    # Act
    normalized = Settings._normalize_global_skills_root(None)

    # Assert
    assert normalized == ""


def test_global_skills_root_defaults_to_empty_when_field_declared():
    # Act
    default = Settings.model_fields["GLOBAL_SKILLS_ROOT"].default

    # Assert
    assert default == ""


def test_settings_has_no_workflow_builder_flag_when_loaded():
    # Arrange: the AI Workflow Builder is always on, so no env switch may exist.
    removed_flag = "WORKFLOW_BUILDER_ENABLED"

    # Act
    declared = set(Settings.model_fields)

    # Assert
    assert removed_flag not in declared


# ════════════════════════════════════════════════════════════════════════════
# Connector settings (Settings._validate_connector_config)
# ════════════════════════════════════════════════════════════════════════════
_SENTINEL = "SENTINEL-value-that-must-never-be-echoed"


def _connector_settings(**overrides: str) -> Settings:
    """Build a Settings with valid non-development values, ignoring env files.

    Every connector field is passed explicitly, so the process environment cannot
    leak a value into the test. Fernet keys are generated here; none is a real secret.
    """
    values: dict[str, str] = {
        "ENV": "production",
        "SECRET_KEY": "p" * 64,
        "COGNITO_USER_POOL_ID": "eu-central-1_testpool",
        "COGNITO_CLIENT_ID": "test-client-id",
        "COGNITO_CLIENT_SECRET": "test-client-secret",
        "PUBLIC_BASE_URL": "https://public.example.test",
        "APP_BASE_URL": "https://app.example.test",
        "OAUTH_REDIRECT_PATH": "/api/connectors/oauth/callback",
        "TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "JIRA_OAUTH_CLIENT_ID": "test-jira-client-id",
        "JIRA_OAUTH_CLIENT_SECRET": "test-jira-client-secret",
        "GITHUB_OAUTH_CLIENT_ID": "test-github-client-id",
        "GITHUB_OAUTH_CLIENT_SECRET": "test-github-client-secret",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _unconfigured_dev_settings(**overrides: str) -> Settings:
    cleared = {
        "ENV": "development",
        "APP_BASE_URL": "",
        "PUBLIC_BASE_URL": "http://localhost:3000",
        "TOKEN_ENCRYPTION_KEY": "",
        "JIRA_OAUTH_CLIENT_ID": "",
        "JIRA_OAUTH_CLIENT_SECRET": "",
        "GITHUB_OAUTH_CLIENT_ID": "",
        "GITHUB_OAUTH_CLIENT_SECRET": "",
    }
    cleared.update(overrides)
    return Settings(_env_file=None, **cleared)


class TestConnectorSettings:
    def test_connector_config_issues_is_empty_when_everything_valid(self):
        # Act
        issues = _connector_settings().connector_config_issues()

        # Assert
        assert issues.all() == ()
        assert issues.for_connector("jira") == ()

    def test_validator_warns_and_boots_when_development_has_nothing_configured(
        self, caplog
    ):
        # Act
        with caplog.at_level(logging.WARNING, logger="app.core.config"):
            built = _unconfigured_dev_settings()

        # Assert
        text = " ".join(record.getMessage() for record in caplog.records)
        for name in (
            "TOKEN_ENCRYPTION_KEY",
            "JIRA_OAUTH_CLIENT_ID",
            "JIRA_OAUTH_CLIENT_SECRET",
            "GITHUB_OAUTH_CLIENT_ID",
            "GITHUB_OAUTH_CLIENT_SECRET",
        ):
            assert name in text
        assert built.connector_config_issues().for_connector("jira")
        assert built.connector_config_issues().for_connector("github")

    def test_issues_are_scoped_to_the_connector_when_only_jira_secret_missing(self):
        # Act
        issues = _connector_settings(
            ENV="development", JIRA_OAUTH_CLIENT_SECRET=""
        ).connector_config_issues()

        # Assert
        assert issues.for_connector("jira") == ("JIRA_OAUTH_CLIENT_SECRET is not set",)
        assert issues.for_connector("github") == ()

    def test_issues_apply_to_every_connector_when_encryption_key_missing(self):
        # Act
        issues = _unconfigured_dev_settings(
            JIRA_OAUTH_CLIENT_ID="a",
            JIRA_OAUTH_CLIENT_SECRET="b",
            GITHUB_OAUTH_CLIENT_ID="c",
            GITHUB_OAUTH_CLIENT_SECRET="d",
            APP_BASE_URL="http://localhost:3000",
        ).connector_config_issues()

        # Assert
        assert issues.shared == ("TOKEN_ENCRYPTION_KEY is not set",)
        assert issues.for_connector("jira") == issues.shared
        assert issues.for_connector("github") == issues.shared

    def test_validator_raises_naming_every_variable_when_production_unconfigured(self):
        # Act
        with pytest.raises(ConnectorsMisconfigured) as exc_info:
            _connector_settings(
                TOKEN_ENCRYPTION_KEY="",
                JIRA_OAUTH_CLIENT_ID="",
                GITHUB_OAUTH_CLIENT_SECRET="",
            )

        # Assert
        message = str(exc_info.value)
        assert "TOKEN_ENCRYPTION_KEY" in message
        assert "JIRA_OAUTH_CLIENT_ID" in message
        assert "GITHUB_OAUTH_CLIENT_SECRET" in message

    def test_validator_never_echoes_values_when_production_values_invalid(self):
        # Act
        with pytest.raises(ConnectorsMisconfigured) as exc_info:
            _connector_settings(
                TOKEN_ENCRYPTION_KEY=_SENTINEL,
                JIRA_OAUTH_CLIENT_ID=f"{_SENTINEL} with spaces",
                APP_BASE_URL=f"http://{_SENTINEL}.example.test",
            )

        # Assert
        assert _SENTINEL not in str(exc_info.value)

    def test_validator_does_not_log_values_when_development_values_invalid(
        self, caplog
    ):
        # Act
        with caplog.at_level(logging.WARNING, logger="app.core.config"):
            _unconfigured_dev_settings(
                TOKEN_ENCRYPTION_KEY=_SENTINEL,
                JIRA_OAUTH_CLIENT_ID=f"{_SENTINEL} with spaces",
            )

        # Assert
        assert _SENTINEL not in caplog.text

    def test_issues_flag_key_when_token_encryption_key_not_fernet(self):
        # Act
        issues = _unconfigured_dev_settings(
            TOKEN_ENCRYPTION_KEY="not-a-fernet-key"
        ).connector_config_issues()

        # Assert
        assert any("TOKEN_ENCRYPTION_KEY entry 1" in issue for issue in issues.shared)

    def test_issues_flag_duplicate_when_token_encryption_key_repeats(self):
        # Arrange
        key = Fernet.generate_key().decode()

        # Act
        issues = _unconfigured_dev_settings(
            TOKEN_ENCRYPTION_KEY=f"{key},{key}"
        ).connector_config_issues()

        # Assert
        assert any("duplicate" in issue for issue in issues.shared)

    def test_issues_flag_count_when_more_than_five_keys(self):
        # Arrange
        keys = ",".join(Fernet.generate_key().decode() for _ in range(6))

        # Act
        issues = _unconfigured_dev_settings(
            TOKEN_ENCRYPTION_KEY=keys
        ).connector_config_issues()

        # Assert
        assert any("more than 5" in issue for issue in issues.shared)

    def test_issues_are_empty_when_five_distinct_keys_given(self):
        # Arrange
        keys = ",".join(Fernet.generate_key().decode() for _ in range(5))

        # Act
        issues = _connector_settings(
            TOKEN_ENCRYPTION_KEY=keys
        ).connector_config_issues()

        # Assert
        assert issues.shared == ()

    def test_issues_flag_trailing_comma_when_key_list_has_empty_entry(self):
        # Arrange
        key = Fernet.generate_key().decode()

        # Act
        issues = _unconfigured_dev_settings(
            TOKEN_ENCRYPTION_KEY=f"{key},"
        ).connector_config_issues()

        # Assert
        assert any("entry 2" in issue for issue in issues.shared)

    def test_validator_raises_when_production_base_url_is_http(self):
        # Act / Assert
        with pytest.raises(ConnectorsMisconfigured, match="https"):
            _connector_settings(APP_BASE_URL="http://app.example.test")

    def test_validator_accepts_http_when_development(self):
        # Act
        issues = _unconfigured_dev_settings(
            APP_BASE_URL="http://localhost:3000"
        ).connector_config_issues()

        # Assert
        assert not any("https" in issue for issue in issues.shared)

    @pytest.mark.parametrize(
        "base_url",
        [
            "https://app.example.test/app",
            "https://app.example.test?x=1",
            "https://app.example.test#frag",
            "https://user:pw@app.example.test",
            "ftp://app.example.test",
            "https://",
            "https://app.example.test:notaport",
            "https://app .example.test",
        ],
    )
    def test_issues_flag_base_url_when_not_a_plain_origin(self, base_url):
        # Act
        issues = _unconfigured_dev_settings(
            APP_BASE_URL=base_url
        ).connector_config_issues()

        # Assert
        assert any("APP_BASE_URL" in issue for issue in issues.shared)

    def test_effective_base_url_uses_public_base_url_when_app_base_url_empty(self):
        # Act
        built = _connector_settings(APP_BASE_URL="")

        # Assert
        assert built.effective_app_base_url == "https://public.example.test"
        assert (
            built.connector_redirect_uri
            == "https://public.example.test/api/connectors/oauth/callback"
        )

    def test_effective_base_url_prefers_app_base_url_when_both_set(self):
        # Act
        built = _connector_settings()

        # Assert
        assert built.effective_app_base_url == "https://app.example.test"

    def test_effective_base_url_drops_trailing_slash_when_present(self):
        # Act
        built = _connector_settings(APP_BASE_URL="https://app.example.test/")

        # Assert
        assert built.effective_app_base_url == "https://app.example.test"
        assert built.connector_redirect_uri.startswith("https://app.example.test/api/")

    def test_issues_name_public_base_url_when_fallback_is_invalid(self):
        # Act
        issues = _unconfigured_dev_settings(
            APP_BASE_URL="", PUBLIC_BASE_URL="https://x.example.test/path"
        ).connector_config_issues()

        # Assert
        assert any(issue.startswith("PUBLIC_BASE_URL") for issue in issues.shared)

    def test_issues_flag_base_url_when_both_urls_empty(self):
        # Act
        issues = _unconfigured_dev_settings(
            APP_BASE_URL="", PUBLIC_BASE_URL=""
        ).connector_config_issues()

        # Assert
        assert any("APP_BASE_URL is not set" in issue for issue in issues.shared)

    @pytest.mark.parametrize(
        "path",
        [
            "api/connectors/oauth/callback",
            "/api/connectors/oauth/callback?x=1",
            "/api/connectors/oauth/callback#x",
            "/api/../callback",
            "/api//callback",
            "/api/call back",
            "/" + "a" * 200,
        ],
    )
    def test_issues_flag_redirect_path_when_invalid(self, path):
        # Act
        issues = _unconfigured_dev_settings(
            OAUTH_REDIRECT_PATH=path
        ).connector_config_issues()

        # Assert
        assert any("OAUTH_REDIRECT_PATH" in issue for issue in issues.shared)

    def test_issues_accept_redirect_path_when_exactly_200_characters(self):
        # Act
        issues = _unconfigured_dev_settings(
            OAUTH_REDIRECT_PATH="/" + "a" * 199
        ).connector_config_issues()

        # Assert
        assert not any("OAUTH_REDIRECT_PATH" in issue for issue in issues.shared)

    @pytest.mark.parametrize(
        "value,expected",
        [("has space", "contains whitespace"), ("x" * 513, "longer than 512")],
    )
    def test_issues_flag_client_credential_when_malformed(self, value, expected):
        # Act
        issues = _unconfigured_dev_settings(
            JIRA_OAUTH_CLIENT_ID=value,
            JIRA_OAUTH_CLIENT_SECRET="ok",
            GITHUB_OAUTH_CLIENT_ID="ok",
            GITHUB_OAUTH_CLIENT_SECRET="ok",
        ).connector_config_issues()

        # Assert
        assert any(expected in issue for issue in issues.for_connector("jira"))
        assert issues.for_connector("github") == issues.shared

    def test_secrets_are_hidden_when_settings_repr_taken(self):
        # Arrange
        built = _connector_settings(
            JIRA_OAUTH_CLIENT_SECRET=_SENTINEL,
            GITHUB_OAUTH_CLIENT_SECRET=_SENTINEL,
        )

        # Act
        text = repr(built)

        # Assert
        assert _SENTINEL not in text
        assert built.TOKEN_ENCRYPTION_KEY not in text

    def test_tuning_defaults_match_design_when_unset(self):
        # Act
        built = _connector_settings()

        # Assert
        assert built.CONNECTOR_TOOL_SCHEMA_TTL_SECONDS == 600
        assert built.CONNECTOR_REFRESH_SKEW_SECONDS == 300
        assert built.CONNECTOR_HTTP_TIMEOUT_SECONDS == 10
        assert built.OAUTH_REDIRECT_PATH == "/api/connectors/oauth/callback"
