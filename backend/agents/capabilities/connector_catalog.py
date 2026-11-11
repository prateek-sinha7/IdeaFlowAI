"""agents/capabilities/connector_catalog.py — the single source of connector metadata.

Pure-data module (stdlib only), beside ``model_catalog.py`` and under the same
single-source rule: one ``ConnectorDefinition`` per OAuth-backed connector.
Adding a connector means one definition here, two Settings fields and the env
entries; the kernel, the API and the frontend do not change.

Scope guards:
  - DATA only. No behavior, no registration with ``registry.py`` (connectors are
    not capabilities), no Settings access: ``client_id_env`` / ``client_secret_env``
    only NAME the Settings fields that hold the credentials.
  - MUST NOT import ``app.*`` or ``agents.execution_engine`` (import-linter contract
    "agents.capabilities must not import the execution kernel or the web layer").
  - Stdlib only, so the compiler (``agents.workflows``) can read it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Literal

#: A connector key: the catalog key, the ``<key>__<tool>`` prefix and the URL path segment.
CONNECTOR_KEY_PATTERN: Final = re.compile(r"^[a-z][a-z0-9]{1,31}$")

#: Words that name a route under ``/api/connectors`` and so can never be a key.
RESERVED_CONNECTOR_KEYS: Final = frozenset({"oauth"})


@dataclass(frozen=True)
class OAuthSpec:
    """Authorization-server endpoints and request shape for one connector."""

    authorize_url: str
    token_url: str
    issuer: str
    iss_param: Literal["required", "if_present"]  # RFC 9207 handling
    scopes: tuple[str, ...]
    extra_authorize_params: tuple[tuple[str, str], ...] = ()
    token_request_encoding: Literal["form", "json"] = "form"
    pkce: bool = True  # always S256 when True
    resource_indicator: str | None = None  # RFC 8707, authorize + token requests


@dataclass(frozen=True)
class RevokeSpec:
    """How a grant is revoked at the provider. ``{client_id}`` is substituted in ``url``."""

    strategy: Literal["github_grant", "rfc7009"]
    url: str


@dataclass(frozen=True)
class AccountSpec:
    """The provider endpoint that identifies the connected account."""

    url: str
    id_field: str
    name_field: str
    login_field: str | None = None
    scopes_header: str | None = None  # GitHub: X-OAuth-Scopes


@dataclass(frozen=True)
class NativeToolSpec:
    """One typed tool of a ``native_api`` connector, bound as ``f"{key}__{name}"``."""

    name: str
    title: str
    description: str
    write_capable: bool
    required_scopes: tuple[str, ...]


@dataclass(frozen=True)
class ToolingSpec:
    """How a connector's tools are produced for an agent step."""

    mode: Literal["remote_mcp", "native_api"]
    mcp_url: str | None = None
    mcp_headers: tuple[tuple[str, str], ...] = ()
    selected_tools_header: str | None = None  # GitHub: X-MCP-Tools at bind time
    tool_allow: tuple[str, ...] = ("*",)  # fnmatch on source tool names (remote_mcp)
    tool_deny: tuple[str, ...] = ()
    write_tools: tuple[str, ...] = ()  # extra write flags beyond readOnlyHint
    native_tools: tuple[NativeToolSpec, ...] = ()


@dataclass(frozen=True)
class ConnectorDefinition:
    """Everything the runtime needs to know about one connector, as data."""

    key: str  # ^[a-z][a-z0-9]{1,31}$
    display_name: str
    description: str
    icon: str
    docs_url: str
    client_id_env: str  # name of a Settings field
    client_secret_env: str  # name of a Settings field
    oauth: OAuthSpec
    revoke: RevokeSpec
    account: AccountSpec
    tooling: ToolingSpec
    post_connect: Literal["atlassian_accessible_resources"] | None = None


_JIRA_READ = ("read:jira-work",)
_JIRA_WRITE = ("write:jira-work",)

GITHUB: Final = ConnectorDefinition(
    key="github",
    display_name="GitHub",
    description=(
        "Work with your repositories, issues and pull requests from custom workflows."
    ),
    icon="github",
    docs_url="https://docs.github.com/en/apps/oauth-apps",
    client_id_env="GITHUB_OAUTH_CLIENT_ID",
    client_secret_env="GITHUB_OAUTH_CLIENT_SECRET",
    oauth=OAuthSpec(
        authorize_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",
        issuer="https://github.com/login/oauth",
        iss_param="required",
        scopes=("repo", "offline_access"),
        token_request_encoding="form",
        resource_indicator="https://api.githubcopilot.com/mcp/",
    ),
    revoke=RevokeSpec(
        strategy="github_grant",
        url="https://api.github.com/applications/{client_id}/grant",
    ),
    account=AccountSpec(
        url="https://api.github.com/user",
        id_field="id",
        name_field="name",
        login_field="login",
        scopes_header="X-OAuth-Scopes",
    ),
    tooling=ToolingSpec(
        mode="remote_mcp",
        mcp_url="https://api.githubcopilot.com/mcp/",
        selected_tools_header="X-MCP-Tools",
    ),
)

JIRA: Final = ConnectorDefinition(
    key="jira",
    display_name="Jira",
    description="Search, read and update Jira issues from custom workflows.",
    icon="jira",
    docs_url="https://developer.atlassian.com/cloud/jira/platform/oauth-2-3lo-apps/",
    client_id_env="JIRA_OAUTH_CLIENT_ID",
    client_secret_env="JIRA_OAUTH_CLIENT_SECRET",
    oauth=OAuthSpec(
        authorize_url="https://auth.atlassian.com/authorize",
        token_url="https://auth.atlassian.com/oauth/token",
        issuer="https://auth.atlassian.com",
        iss_param="if_present",
        scopes=("read:jira-work", "write:jira-work", "read:me", "offline_access"),
        extra_authorize_params=(
            ("audience", "api.atlassian.com"),
            ("prompt", "consent"),
        ),
        token_request_encoding="json",
    ),
    revoke=RevokeSpec(
        strategy="rfc7009", url="https://auth.atlassian.com/oauth/revoke"
    ),
    account=AccountSpec(
        url="https://api.atlassian.com/me",
        id_field="account_id",
        name_field="name",
    ),
    tooling=ToolingSpec(
        mode="native_api",
        native_tools=(
            NativeToolSpec(
                name="search_issues",
                title="Search issues",
                description="Search Jira issues with a JQL query.",
                write_capable=False,
                required_scopes=_JIRA_READ,
            ),
            NativeToolSpec(
                name="get_issue",
                title="Get issue",
                description="Read one Jira issue by its key.",
                write_capable=False,
                required_scopes=_JIRA_READ,
            ),
            NativeToolSpec(
                name="list_projects",
                title="List projects",
                description="List the Jira projects the account can see.",
                write_capable=False,
                required_scopes=_JIRA_READ,
            ),
            NativeToolSpec(
                name="get_comments",
                title="Get comments",
                description="Read the comments of a Jira issue.",
                write_capable=False,
                required_scopes=_JIRA_READ,
            ),
            NativeToolSpec(
                name="list_transitions",
                title="List transitions",
                description="List the workflow transitions available for a Jira issue.",
                write_capable=False,
                required_scopes=_JIRA_READ,
            ),
            NativeToolSpec(
                name="create_issue",
                title="Create issue",
                description="Create a Jira issue in a project.",
                write_capable=True,
                required_scopes=_JIRA_WRITE,
            ),
            NativeToolSpec(
                name="update_issue",
                title="Update issue",
                description="Change the summary, description or labels of a Jira issue.",
                write_capable=True,
                required_scopes=_JIRA_WRITE,
            ),
            NativeToolSpec(
                name="add_comment",
                title="Add comment",
                description="Add a comment to a Jira issue.",
                write_capable=True,
                required_scopes=_JIRA_WRITE,
            ),
            NativeToolSpec(
                name="transition_issue",
                title="Transition issue",
                description="Move a Jira issue through one of its workflow transitions.",
                write_capable=True,
                required_scopes=_JIRA_WRITE,
            ),
            NativeToolSpec(
                name="assign_issue",
                title="Assign issue",
                description="Assign a Jira issue to a user, or unassign it.",
                write_capable=True,
                required_scopes=_JIRA_WRITE,
            ),
        ),
    ),
    post_connect="atlassian_accessible_resources",
)

#: Every connector, in display order (the order ``GET /api/connectors`` returns).
CONNECTORS: Final[tuple[ConnectorDefinition, ...]] = (GITHUB, JIRA)


def get_connector(key: str) -> ConnectorDefinition | None:
    """Return the definition for ``key``, or ``None`` when no such connector exists."""
    for definition in CONNECTORS:
        if definition.key == key:
            return definition
    return None


def connector_keys() -> tuple[str, ...]:
    """Return every connector key, in catalog order."""
    return tuple(definition.key for definition in CONNECTORS)
