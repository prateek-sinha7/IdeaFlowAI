"""Contract: every connector setting reaches the app from every place it is declared.

A connector value that is declared in Settings but missing from the deploy step or the
on-host loader allowlist is dropped silently ("ignoring unknown parameter"), and the
fail-fast startup validation then stops the container. This test pins the names across
Settings, both env templates, ``deploy.yml`` and ``velocityai-load-secrets.sh``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from agents.capabilities.connector_catalog import CONNECTORS
from app.core.config import Settings
from tools.ci.offline_guards import CREDENTIAL_ENV_PATTERNS

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ENV_EXAMPLE = REPO_ROOT / "backend" / ".env.example"
APP_ENV_EXAMPLE = REPO_ROOT / "app.env.example"
DEPLOY_YML = REPO_ROOT / ".github" / "workflows" / "deploy.yml"
LOADER = REPO_ROOT / "infra" / "scripts" / "velocityai-load-secrets.sh"

_SECRET_NAMES = frozenset(
    {"TOKEN_ENCRYPTION_KEY"} | {d.client_secret_env for d in CONNECTORS}
)
_CLIENT_ID_NAMES = frozenset(d.client_id_env for d in CONNECTORS)
#: Values the pipeline pushes to SSM, in the order the design lists them.
_PIPELINE_NAMES = sorted(_SECRET_NAMES | _CLIENT_ID_NAMES | {"APP_BASE_URL"})
#: Everything the app reads for connectors, with or without a pipeline value.
_ALL_NAMES = sorted(set(_PIPELINE_NAMES) | {"OAUTH_REDIRECT_PATH"})

_PUT_PARAM = re.compile(
    r'^\s*put_param\s+"(?P<key>[A-Z_]+)"\s+"\$(?P<var>[A-Z_]+)"\s+'
    r'"(?P<type>String|SecureString)"\s+"(?P<policy>[a-z-]+)"\s*$',
    re.MULTILINE,
)


def _github_actions_name(app_name: str) -> str:
    """GitHub reserves the ``GITHUB_`` prefix, so the workflow uses ``GH_`` instead."""
    if app_name.startswith("GITHUB_"):
        return "GH_" + app_name.removeprefix("GITHUB_")
    return app_name


def _put_params() -> dict[str, re.Match[str]]:
    text = DEPLOY_YML.read_text(encoding="utf-8")
    return {match["key"]: match for match in _PUT_PARAM.finditer(text)}


def _loader_allowlist() -> set[str]:
    text = LOADER.read_text(encoding="utf-8")
    line = next(
        line for line in text.splitlines() if line.strip().startswith("SECRET_KEY|")
    )
    return set(line.strip().rstrip(")").split("|"))


@pytest.mark.parametrize("name", _ALL_NAMES)
def test_env_name_is_a_settings_field_when_connector_setting_declared(name):
    # Assert
    assert name in Settings.model_fields


@pytest.mark.parametrize(
    "template", [BACKEND_ENV_EXAMPLE, APP_ENV_EXAMPLE], ids=lambda p: p.name
)
@pytest.mark.parametrize("name", _ALL_NAMES)
def test_env_name_is_in_template_when_connector_setting_declared(template, name):
    # Arrange
    text = template.read_text(encoding="utf-8")

    # Assert: either an active assignment or a commented example.
    assert re.search(rf"^#?\s*{name}=", text, flags=re.MULTILINE), name


@pytest.mark.parametrize(
    "template", [BACKEND_ENV_EXAMPLE, APP_ENV_EXAMPLE], ids=lambda p: p.name
)
def test_secret_values_are_placeholders_when_template_read(template):
    # Arrange
    text = template.read_text(encoding="utf-8")

    # Assert: no secret has a value in a committed template.
    for name in _SECRET_NAMES:
        assert re.search(rf"^{name}=\s*$", text, flags=re.MULTILINE), name


@pytest.mark.parametrize("name", _PIPELINE_NAMES)
def test_pipeline_pushes_the_name_to_ssm_when_connector_setting_declared(name):
    # Assert
    assert name in _put_params()


@pytest.mark.parametrize("name", sorted(_SECRET_NAMES))
def test_secret_is_a_secure_string_from_actions_secrets_when_pushed(name):
    # Arrange
    match = _put_params()[name]
    source_var = _github_actions_name(name)
    text = DEPLOY_YML.read_text(encoding="utf-8")

    # Assert
    assert match["type"] == "SecureString"
    assert match["policy"] == "required"
    assert match["var"] == source_var
    assert f"{source_var}: ${{{{ secrets.{source_var} }}}}" in text


@pytest.mark.parametrize("name", sorted(_CLIENT_ID_NAMES))
def test_client_id_is_a_string_from_actions_variables_when_pushed(name):
    # Arrange
    match = _put_params()[name]
    source_var = _github_actions_name(name)
    text = DEPLOY_YML.read_text(encoding="utf-8")

    # Assert
    assert match["type"] == "String"
    assert match["policy"] == "required"
    assert match["var"] == source_var
    assert f"{source_var}: ${{{{ vars.{source_var} }}}}" in text


def test_app_base_url_is_deleted_when_empty_in_github():
    # Arrange
    match = _put_params()["APP_BASE_URL"]

    # Assert: clearing it lets the PUBLIC_BASE_URL fallback apply.
    assert match["type"] == "String"
    assert match["policy"] == "delete-if-empty"
    assert match["var"] == "APP_BASE_URL"


def test_workflow_defines_no_github_prefixed_names_when_connectors_mapped():
    # Arrange: GitHub rejects secret and variable names that start with GITHUB_.
    text = DEPLOY_YML.read_text(encoding="utf-8")

    # Assert
    assert not re.search(r"secrets\.GITHUB_OAUTH", text)
    assert not re.search(r"vars\.GITHUB_OAUTH", text)
    assert not re.search(r"^\s+GITHUB_OAUTH_\w+:", text, flags=re.MULTILINE)


@pytest.mark.parametrize("name", _PIPELINE_NAMES)
def test_loader_passes_the_name_through_when_pushed_to_ssm(name):
    # Assert
    assert name in _loader_allowlist()


@pytest.mark.parametrize(
    "name",
    sorted(_SECRET_NAMES | {_github_actions_name(secret) for secret in _SECRET_NAMES}),
)
def test_offline_guard_lists_name_when_connector_secret_declared(name):
    # Assert: the offline CI guard blocks every connector secret and its Actions alias.
    assert name in CREDENTIAL_ENV_PATTERNS
