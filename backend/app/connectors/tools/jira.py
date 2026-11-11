"""Jira provider: typed native tools over Jira Cloud REST v3.

``build_jira_tools`` returns one ``StructuredTool`` per requested tool name. The
tools are always the real tool: nothing touches the network at bind time, so a
missing or expired connection shows up at call time and connecting mid-run makes the
next call work.

Every call resolves the run user's connection and site, signs the request through
``ConnectorAuth`` (current token, one refresh after a 401) and opens its own
short-lived ``httpx.AsyncClient``, so no cookie jar is shared between users.
Path parameters are checked against a pattern and URL-encoded before use.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass
from typing import Annotated, Any, Final
from urllib.parse import quote, urlparse

import httpx
from langchain_core.tools import StructuredTool
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from agents.capabilities.connector_catalog import (
    ConnectorDefinition,
    NativeToolSpec,
)
from app.connectors.errors import ConnectorError, ToolErrorCode
from app.connectors.store import ConnectionRecord
from app.connectors.tools.adf import adf_to_text, text_to_adf
from app.connectors.tools.auth import ConnectorAuth
from app.connectors.tools.base import (
    MAX_ERROR_MESSAGE_CHARS,
    ToolIdentity,
    ToolRuntime,
    clip,
    make_connector_tool,
    status_error,
    validate_arguments,
)
from app.connectors.tools.names import format_tool_name

JIRA_API_BASE: Final = "https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3"
REQUEST_TIMEOUT_SECONDS: Final = 30.0

_ISSUE_KEY_PATTERN: Final = r"^[A-Z][A-Z0-9_]{0,19}-[1-9][0-9]{0,9}$"
_PROJECT_KEY_PATTERN: Final = r"^[A-Z][A-Z0-9_]{1,9}$"
_TRANSITION_ID_PATTERN: Final = r"^[0-9]{1,10}$"
_ISSUE_FIELDS: Final = ["summary", "status", "assignee", "updated"]
_DETAIL_FIELDS: Final = [
    *_ISSUE_FIELDS,
    "description",
    "issuetype",
    "priority",
    "labels",
    "reporter",
    "created",
]

IssueKey = Annotated[str, StringConstraints(pattern=_ISSUE_KEY_PATTERN)]
Label = Annotated[
    str, StringConstraints(min_length=1, max_length=255, pattern=r"^\S+$")
]


# ---- argument models --------------------------------------------------------


class _Args(BaseModel):
    """Common base: unknown arguments are rejected so a typo is reported, not ignored."""

    model_config = ConfigDict(extra="forbid")

    site: str | None = Field(
        default=None,
        max_length=200,
        description="Optional Jira site (id, name or host). Defaults to the first connected site.",
    )


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


class SearchIssuesArgs(_Args):
    """Arguments of ``jira__search_issues``."""

    jql: str = Field(min_length=1, max_length=2000, description="JQL query.")
    max_results: int = Field(default=20, ge=1, le=50)
    next_page_token: str | None = Field(default=None, max_length=512)

    _jql_not_blank = field_validator("jql")(_not_blank)


class GetIssueArgs(_Args):
    """Arguments of ``jira__get_issue``."""

    issue_key: IssueKey = Field(description="Issue key such as ABC-123.")


class ListProjectsArgs(_Args):
    """Arguments of ``jira__list_projects``."""

    query: str | None = Field(default=None, max_length=200)
    max_results: int = Field(default=20, ge=1, le=50)


class GetCommentsArgs(_Args):
    """Arguments of ``jira__get_comments``."""

    issue_key: IssueKey
    max_results: int = Field(default=20, ge=1, le=50)


class ListTransitionsArgs(_Args):
    """Arguments of ``jira__list_transitions``."""

    issue_key: IssueKey


class CreateIssueArgs(_Args):
    """Arguments of ``jira__create_issue``."""

    project_key: str = Field(pattern=_PROJECT_KEY_PATTERN)
    issue_type: str = Field(min_length=1, max_length=60)
    summary: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=32_000)
    labels: list[Label] | None = Field(default=None, max_length=10)

    _not_blank = field_validator("issue_type", "summary")(_not_blank)


class UpdateIssueArgs(_Args):
    """Arguments of ``jira__update_issue``."""

    issue_key: IssueKey
    summary: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=32_000)
    labels: list[Label] | None = Field(default=None, max_length=10)

    @model_validator(mode="after")
    def _needs_a_change(self) -> UpdateIssueArgs:
        if self.summary is None and self.description is None and self.labels is None:
            raise ValueError("give at least one of summary, description, labels")
        if self.summary is not None and not self.summary.strip():
            raise ValueError("summary must not be blank")
        return self


class AddCommentArgs(_Args):
    """Arguments of ``jira__add_comment``."""

    issue_key: IssueKey
    body: str = Field(min_length=1, max_length=32_000)

    _body_not_blank = field_validator("body")(_not_blank)


class TransitionIssueArgs(_Args):
    """Arguments of ``jira__transition_issue``."""

    issue_key: IssueKey
    transition_id: str = Field(pattern=_TRANSITION_ID_PATTERN)


class AssignIssueArgs(_Args):
    """Arguments of ``jira__assign_issue``."""

    issue_key: IssueKey
    account_id: str | None = Field(
        max_length=128, description="Atlassian account id, or null to unassign."
    )


# ---- sites and requests -----------------------------------------------------


@dataclass(frozen=True)
class JiraSite:
    """A Jira site the user granted."""

    id: str
    name: str
    url: str

    @property
    def host(self) -> str:
        """The host of the site URL, lowercase."""
        return (urlparse(self.url).hostname or "").lower()

    @property
    def api_base(self) -> str:
        """The REST v3 base URL for this site."""
        return JIRA_API_BASE.format(cloud_id=quote(self.id, safe=""))

    def issue_url(self, key: str) -> str:
        """The browser URL of an issue."""
        return f"{self.url}/browse/{key}"


def sites_of(record: ConnectionRecord) -> list[JiraSite]:
    """The sites stored on the connection (``provider_metadata.sites``)."""
    raw = (record.provider_metadata or {}).get("sites")
    sites: list[JiraSite] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            site_id, name, url = item.get("id"), item.get("name"), item.get("url")
            if all(isinstance(v, str) and v for v in (site_id, name, url)):
                sites.append(JiraSite(id=site_id, name=name, url=str(url).rstrip("/")))
    return sites


def resolve_site(
    sites: list[JiraSite], requested: str | None, connector: str
) -> JiraSite:
    """Pick the site named by ``requested`` (id, name or host), or the first one.

    Raises:
        ConnectorError: ``connection_expired`` when no site is stored, or
            ``invalid_arguments`` listing the available sites for an unknown value.
    """
    if not sites:
        raise ConnectorError(
            ToolErrorCode.CONNECTION_EXPIRED,
            "No Jira site is available, reconnect in Connectors",
            connector=connector,
        )
    if requested is None:
        return sites[0]
    wanted = requested.strip().casefold()
    for site in sites:
        if wanted in {site.id.casefold(), site.name.casefold(), site.host}:
            return site
    available = ", ".join(f"{site.name} ({site.host})" for site in sites)
    raise ConnectorError(
        ToolErrorCode.INVALID_ARGUMENTS,
        clip(f"Unknown site. Available sites: {available}", MAX_ERROR_MESSAGE_CHARS),
        connector=connector,
    )


def _provider_detail(response: httpx.Response) -> str:
    """The first error message in a Jira error body, cleaned and cut."""
    try:
        body = response.json()
    except ValueError:
        return ""
    if not isinstance(body, dict):
        return ""
    candidates: list[object] = []
    messages = body.get("errorMessages")
    if isinstance(messages, list):
        candidates.extend(messages)
    errors = body.get("errors")
    if isinstance(errors, dict):
        candidates.extend(errors.values())
    candidates.append(body.get("message"))
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return clip(" ".join(candidate.split()), MAX_ERROR_MESSAGE_CHARS)
    return ""


class _JiraCall:
    """One tool call: resolves the connection and site, then sends signed requests."""

    def __init__(
        self, runtime: ToolRuntime, identity: ToolIdentity, spec: NativeToolSpec
    ) -> None:
        self._runtime = runtime
        self._identity = identity
        self._spec = spec

    async def prepare(self, requested_site: str | None) -> JiraSite:
        """Check configuration, user, connection and scopes, then pick the site."""
        identity = self._identity
        key, name = identity.connector_key, identity.display_name
        entry = self._runtime.registry.get(key)
        if entry is None or not entry.configured:
            raise ConnectorError(
                ToolErrorCode.NOT_CONFIGURED,
                f"{name} is not configured on this server",
                connector=key,
            )
        if identity.user_id is None:
            raise ConnectorError(
                ToolErrorCode.SIGN_IN_REQUIRED,
                "Connected apps need a signed-in user",
                connector=key,
            )
        record = await asyncio.to_thread(self._runtime.store.get, identity.user_id, key)
        if record is None:
            raise ConnectorError(
                ToolErrorCode.CONNECTION_MISSING,
                f"{name} connection missing, reconnect in Connectors",
                connector=key,
            )
        if not record.is_active:
            raise ConnectorError(
                ToolErrorCode.CONNECTION_EXPIRED,
                f"{name} connection expired, reconnect in Connectors",
                connector=key,
            )
        missing = [
            scope
            for scope in self._spec.required_scopes
            if record.granted_scopes and scope not in record.granted_scopes
        ]
        if missing:
            raise ConnectorError(
                ToolErrorCode.INSUFFICIENT_SCOPE,
                f"{name} needs more permission (scope: {', '.join(missing)}). "
                "Reconnect in Connectors to grant it.",
                connector=key,
            )
        return resolve_site(sites_of(record), requested_site, key)

    async def request(
        self,
        site: JiraSite,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        not_found: str = "Jira resource",
    ) -> Any:
        """Send one signed request and return the decoded JSON (``None`` for an empty body)."""
        identity = self._identity
        assert identity.user_id is not None  # prepare() rejected anonymous runs
        auth = ConnectorAuth(
            identity.user_id, identity.connector_key, self._runtime.tokens
        )
        client = self._runtime.async_client_factory(
            headers={"Accept": "application/json"},
            timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS),
            auth=auth,
        )
        async with client:
            response = await client.request(
                method, f"{site.api_base}{path}", params=params, json=body
            )
        if response.is_success:
            return _decode(response, identity.connector_key)
        code, message = status_error(response, identity)
        if code is ToolErrorCode.NOT_FOUND:
            message = f"{not_found} was not found"
        elif code is ToolErrorCode.PROVIDER_ERROR:
            detail = _provider_detail(response)
            if detail:
                message = f"{message}: {detail}"
        raise ConnectorError(code, message, connector=identity.connector_key)


def _decode(response: httpx.Response, connector: str) -> Any:
    if response.status_code == 204 or not response.content:
        return None
    try:
        return response.json()
    except ValueError as exc:
        raise ConnectorError(
            ToolErrorCode.PROVIDER_ERROR,
            "Jira returned an unreadable response",
            connector=connector,
        ) from exc


# ---- result shaping ---------------------------------------------------------


def _name_of(value: object) -> str | None:
    if isinstance(value, dict):
        name = value.get("name")
        return name if isinstance(name, str) else None
    return None


def _person(value: object) -> str | None:
    if isinstance(value, dict):
        name = value.get("displayName")
        return name if isinstance(name, str) else None
    return None


def issue_summary(issue: object, site: JiraSite) -> dict[str, Any]:
    """The compact shape of an issue: key, summary, status, assignee, updated, URL."""
    data = issue if isinstance(issue, dict) else {}
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    key = data.get("key") if isinstance(data.get("key"), str) else ""
    return {
        "key": key,
        "summary": fields.get("summary"),
        "status": _name_of(fields.get("status")),
        "assignee": _person(fields.get("assignee")),
        "updated": fields.get("updated"),
        "url": site.issue_url(key) if key else None,
    }


def _issue_detail(issue: object, site: JiraSite) -> dict[str, Any]:
    data = issue if isinstance(issue, dict) else {}
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    detail = issue_summary(issue, site)
    labels = fields.get("labels")
    detail.update(
        {
            "issue_type": _name_of(fields.get("issuetype")),
            "priority": _name_of(fields.get("priority")),
            "reporter": _person(fields.get("reporter")),
            "created": fields.get("created"),
            "labels": [x for x in labels if isinstance(x, str)]
            if isinstance(labels, list)
            else [],
            "description": adf_to_text(fields.get("description")),
        }
    )
    return detail


def _list_of(body: object, key: str) -> list[Any]:
    value = body.get(key) if isinstance(body, dict) else None
    return value if isinstance(value, list) else []


# ---- tool handlers ----------------------------------------------------------

Handler = Callable[[_JiraCall, JiraSite, Any], Awaitable[Any]]


def _issue_path(issue_key: str) -> str:
    return f"/issue/{quote(issue_key, safe='')}"


async def _search_issues(
    call: _JiraCall, site: JiraSite, args: SearchIssuesArgs
) -> Any:
    body: dict[str, Any] = {
        "jql": args.jql,
        "maxResults": args.max_results,
        "fields": _ISSUE_FIELDS,
    }
    if args.next_page_token:
        body["nextPageToken"] = args.next_page_token
    data = await call.request(site, "POST", "/search/jql", body=body)
    token = data.get("nextPageToken") if isinstance(data, dict) else None
    return {
        "issues": [issue_summary(item, site) for item in _list_of(data, "issues")],
        "next_page_token": token if isinstance(token, str) and token else None,
    }


async def _get_issue(call: _JiraCall, site: JiraSite, args: GetIssueArgs) -> Any:
    data = await call.request(
        site,
        "GET",
        _issue_path(args.issue_key),
        params={"fields": ",".join(_DETAIL_FIELDS)},
        not_found=f"Jira issue {args.issue_key}",
    )
    return _issue_detail(data, site)


async def _list_projects(
    call: _JiraCall, site: JiraSite, args: ListProjectsArgs
) -> Any:
    params: dict[str, Any] = {"maxResults": args.max_results}
    if args.query:
        params["query"] = args.query
    data = await call.request(site, "GET", "/project/search", params=params)
    projects = []
    for item in _list_of(data, "values"):
        if isinstance(item, dict):
            projects.append(
                {
                    "key": item.get("key"),
                    "name": item.get("name"),
                    "type": item.get("projectTypeKey"),
                }
            )
    return {"projects": projects}


async def _get_comments(call: _JiraCall, site: JiraSite, args: GetCommentsArgs) -> Any:
    data = await call.request(
        site,
        "GET",
        f"{_issue_path(args.issue_key)}/comment",
        params={"maxResults": args.max_results},
        not_found=f"Jira issue {args.issue_key}",
    )
    comments = []
    for item in _list_of(data, "comments"):
        if isinstance(item, dict):
            comments.append(
                {
                    "id": item.get("id"),
                    "author": _person(item.get("author")),
                    "created": item.get("created"),
                    "body": adf_to_text(item.get("body")),
                }
            )
    return {"issue": args.issue_key, "comments": comments}


async def _list_transitions(
    call: _JiraCall, site: JiraSite, args: ListTransitionsArgs
) -> Any:
    data = await call.request(
        site,
        "GET",
        f"{_issue_path(args.issue_key)}/transitions",
        not_found=f"Jira issue {args.issue_key}",
    )
    transitions = []
    for item in _list_of(data, "transitions"):
        if isinstance(item, dict):
            transitions.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "to": _name_of(item.get("to")),
                }
            )
    return {"issue": args.issue_key, "transitions": transitions}


async def _create_issue(call: _JiraCall, site: JiraSite, args: CreateIssueArgs) -> Any:
    fields: dict[str, Any] = {
        "project": {"key": args.project_key},
        "issuetype": {"name": args.issue_type},
        "summary": args.summary,
    }
    if args.description and args.description.strip():
        fields["description"] = text_to_adf(args.description)
    if args.labels:
        fields["labels"] = args.labels
    data = await call.request(
        site,
        "POST",
        "/issue",
        body={"fields": fields},
        not_found=f"Jira project {args.project_key}",
    )
    key = data.get("key") if isinstance(data, dict) else None
    return {
        "key": key,
        "id": data.get("id") if isinstance(data, dict) else None,
        "url": site.issue_url(key) if isinstance(key, str) else None,
    }


async def _update_issue(call: _JiraCall, site: JiraSite, args: UpdateIssueArgs) -> Any:
    fields: dict[str, Any] = {}
    if args.summary is not None:
        fields["summary"] = args.summary
    if args.description is not None:
        fields["description"] = (
            text_to_adf(args.description) if args.description.strip() else None
        )
    if args.labels is not None:
        fields["labels"] = args.labels
    await call.request(
        site,
        "PUT",
        _issue_path(args.issue_key),
        body={"fields": fields},
        not_found=f"Jira issue {args.issue_key}",
    )
    return {
        "key": args.issue_key,
        "updated": True,
        "url": site.issue_url(args.issue_key),
    }


async def _add_comment(call: _JiraCall, site: JiraSite, args: AddCommentArgs) -> Any:
    data = await call.request(
        site,
        "POST",
        f"{_issue_path(args.issue_key)}/comment",
        body={"body": text_to_adf(args.body)},
        not_found=f"Jira issue {args.issue_key}",
    )
    return {
        "issue": args.issue_key,
        "comment_id": data.get("id") if isinstance(data, dict) else None,
        "url": site.issue_url(args.issue_key),
    }


async def _transition_issue(
    call: _JiraCall, site: JiraSite, args: TransitionIssueArgs
) -> Any:
    await call.request(
        site,
        "POST",
        f"{_issue_path(args.issue_key)}/transitions",
        body={"transition": {"id": args.transition_id}},
        not_found=f"Jira issue {args.issue_key}",
    )
    return {
        "key": args.issue_key,
        "transitioned": True,
        "url": site.issue_url(args.issue_key),
    }


async def _assign_issue(call: _JiraCall, site: JiraSite, args: AssignIssueArgs) -> Any:
    await call.request(
        site,
        "PUT",
        f"{_issue_path(args.issue_key)}/assignee",
        body={"accountId": args.account_id},
        not_found=f"Jira issue {args.issue_key}",
    )
    return {
        "key": args.issue_key,
        "assignee": args.account_id,
        "url": site.issue_url(args.issue_key),
    }


#: Source tool name -> (argument model, handler). Must cover every native tool of the definition.
TOOL_TABLE: Final[dict[str, tuple[type[_Args], Handler]]] = {
    "search_issues": (SearchIssuesArgs, _search_issues),
    "get_issue": (GetIssueArgs, _get_issue),
    "list_projects": (ListProjectsArgs, _list_projects),
    "get_comments": (GetCommentsArgs, _get_comments),
    "list_transitions": (ListTransitionsArgs, _list_transitions),
    "create_issue": (CreateIssueArgs, _create_issue),
    "update_issue": (UpdateIssueArgs, _update_issue),
    "add_comment": (AddCommentArgs, _add_comment),
    "transition_issue": (TransitionIssueArgs, _transition_issue),
    "assign_issue": (AssignIssueArgs, _assign_issue),
}


def build_jira_tools(
    *,
    runtime: ToolRuntime,
    definition: ConnectorDefinition,
    user_id: str | None,
    run_id: str | None,
    requested: Collection[str],
) -> dict[str, StructuredTool]:
    """Return the Jira tools named in ``requested`` (bound names such as ``jira__get_issue``).

    Names that are not Jira tools are ignored. No network is used here.
    """
    identity = ToolIdentity(
        connector_key=definition.key,
        display_name=definition.display_name,
        user_id=user_id,
        run_id=run_id,
    )
    wanted = set(requested)
    tools: dict[str, StructuredTool] = {}
    for spec in definition.tooling.native_tools:
        bound_name = format_tool_name(definition.key, spec.name)
        entry = TOOL_TABLE.get(spec.name)
        if bound_name not in wanted or entry is None:
            continue
        model, handler = entry
        tools[bound_name] = make_connector_tool(
            name=bound_name,
            description=spec.description,
            args_schema=model.model_json_schema(),
            identity=identity,
            body=_body_for(runtime, identity, spec, model, handler),
            audit=runtime.audit,
            write_capable=spec.write_capable,
            source_name=spec.name,
        )
    return tools


def _body_for(
    runtime: ToolRuntime,
    identity: ToolIdentity,
    spec: NativeToolSpec,
    model: type[_Args],
    handler: Handler,
) -> Callable[[dict[str, Any]], Awaitable[str]]:
    async def _body(arguments: dict[str, Any]) -> str:
        args = validate_arguments(model, arguments, identity.connector_key)
        call = _JiraCall(runtime, identity, spec)
        site = await call.prepare(args.site)
        result = await handler(call, site, args)
        return json.dumps(result, ensure_ascii=False)

    return _body
