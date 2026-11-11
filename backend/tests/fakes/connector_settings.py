"""Settings for connector tests: every connector configured, nothing real.

The encryption key is generated per call and the client ids and secrets are
placeholders (the secret values are sentinels the secret-exposure tests search for).
"""

from __future__ import annotations

from cryptography.fernet import Fernet

from app.core.config import Settings

REDIRECT_URI = "http://localhost:3000/api/connectors/oauth/callback"
CLIENT_SECRETS = {
    "JIRA_OAUTH_CLIENT_SECRET": "jira-secret-sentinel",
    "GITHUB_OAUTH_CLIENT_SECRET": "github-secret-sentinel",
}


def make_settings(**overrides: str) -> Settings:
    """Development settings with every connector configured (generated key, placeholders)."""
    values: dict[str, str] = {
        "ENV": "development",
        "APP_BASE_URL": "http://localhost:3000",
        "PUBLIC_BASE_URL": "http://localhost:3000",
        "OAUTH_REDIRECT_PATH": "/api/connectors/oauth/callback",
        "TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "JIRA_OAUTH_CLIENT_ID": "jira-client-id",
        "GITHUB_OAUTH_CLIENT_ID": "github-client-id",
        **CLIENT_SECRETS,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)
