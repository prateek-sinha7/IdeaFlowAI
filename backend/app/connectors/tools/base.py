"""The wrapper every connector tool goes through.

``make_connector_tool`` builds a LangChain ``StructuredTool`` that

* carries the namespaced name and a ``write_capable`` flag in its metadata,
* never raises: every failure becomes the error envelope of design section 5.6,
* writes one audit row per call (connector, tool, outcome, code, duration, run id,
  agent), never arguments, results or tokens,
* caps the result at ``MAX_RESULT_CHARS`` characters.

LangGraph's default tool node re-raises tool exceptions and fails the agent step, so
catching everything here is what keeps a Jira outage from ending a run.

Logs carry the exception type and the error code only.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final

import httpx
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import StructuredTool, ToolException
from langchain_mcp_adapters.sessions import McpHttpClientFactory
from pydantic import BaseModel, ValidationError

from app.connectors.audit import ConnectorAudit, agent_ref_from_config
from app.connectors.errors import ConnectorError, ToolErrorCode, error_envelope
from app.connectors.http import mcp_client_factory
from app.connectors.registry import ConnectorRegistry
from app.connectors.store import ConnectionStore
from app.connectors.tools.auth import AccessTokenSource

logger = logging.getLogger("app.connectors.tools.base")

#: Longest tool result handed to the model, in characters.
MAX_RESULT_CHARS: Final = 100_000
TRUNCATION_NOTICE: Final = "\n[result truncated]"
#: Longest provider message or validation message copied into an error envelope.
MAX_ERROR_MESSAGE_CHARS: Final = 300
#: Retry-After values outside this range are clamped (seconds).
_MAX_RETRY_AFTER: Final = 300

#: What a connector tool runs: raw arguments in, result text out; failures raise.
ToolBody = Callable[[dict[str, Any]], Awaitable[str]]

#: A permissive schema for stubs and for tools whose schema is unknown.
PERMISSIVE_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "additionalProperties": True,
}


@dataclass(frozen=True)
class ToolRuntime:
    """What the tool providers share: configuration, storage, tokens, audit, HTTP."""

    registry: ConnectorRegistry
    store: ConnectionStore
    tokens: AccessTokenSource
    audit: ConnectorAudit
    async_client_factory: McpHttpClientFactory = mcp_client_factory


@dataclass(frozen=True)
class ToolIdentity:
    """Who a tool instance acts for. ``user_id`` is ``None`` only for anonymous runs."""

    connector_key: str
    display_name: str
    user_id: str | None
    run_id: str | None


def tool_metadata(
    identity: ToolIdentity, *, write_capable: bool, source_name: str
) -> dict[str, Any]:
    """Metadata hooks or HITL can read to treat write tools differently."""
    return {
        "connector": identity.connector_key,
        "write_capable": write_capable,
        "source_name": source_name,
    }


def clip(value: str, limit: int) -> str:
    """Return ``value`` cut to ``limit`` characters."""
    return value if len(value) <= limit else value[:limit]


def shape_result(text: str) -> str:
    """Cap a tool result at ``MAX_RESULT_CHARS`` characters."""
    if len(text) <= MAX_RESULT_CHARS:
        return text
    return text[: MAX_RESULT_CHARS - len(TRUNCATION_NOTICE)] + TRUNCATION_NOTICE


def parse_retry_after(value: str | None) -> int | None:
    """Return ``Retry-After`` as whole seconds (1 to 300), or ``None`` when absent or not a number."""
    if value is None:
        return None
    try:
        seconds = int(value.strip())
    except ValueError:
        return None
    return max(1, min(seconds, _MAX_RETRY_AFTER))


def validation_message(exc: ValidationError) -> str:
    """Summarize a Pydantic error as ``field: message`` pairs, without the input values."""
    parts = []
    for error in exc.errors(include_input=False, include_url=False)[:5]:
        location = ".".join(str(part) for part in error.get("loc", ())) or "arguments"
        parts.append(f"{location}: {error.get('msg', 'invalid')}")
    return clip("Invalid arguments: " + "; ".join(parts), MAX_ERROR_MESSAGE_CHARS)


def validate_arguments(
    model: type[BaseModel], arguments: Mapping[str, Any], connector: str
) -> Any:
    """Validate ``arguments`` against ``model``.

    Raises:
        ConnectorError: ``invalid_arguments`` with a short message.
    """
    try:
        return model.model_validate(dict(arguments))
    except ValidationError as exc:
        raise ConnectorError(
            ToolErrorCode.INVALID_ARGUMENTS,
            validation_message(exc),
            connector=connector,
        ) from exc


def _flatten(exc: BaseException) -> list[BaseException]:
    if isinstance(exc, BaseExceptionGroup):
        leaves: list[BaseException] = []
        for inner in exc.exceptions:
            leaves.extend(_flatten(inner))
        return leaves
    return [exc]


def status_error(
    response: httpx.Response, identity: ToolIdentity
) -> tuple[ToolErrorCode, str]:
    """Map an HTTP error response to a code and message (no response body text)."""
    status = response.status_code
    name = identity.display_name
    if status == 401:
        return (
            ToolErrorCode.CONNECTION_EXPIRED,
            f"{name} connection expired, reconnect in Connectors",
        )
    if status == 403:
        challenge = response.headers.get("www-authenticate", "")
        if "insufficient_scope" in challenge:
            return (
                ToolErrorCode.INSUFFICIENT_SCOPE,
                f"{name} needs more permission. Reconnect in Connectors to grant it.",
            )
        return (
            ToolErrorCode.PERMISSION_DENIED,
            f"{name} refused the request: you do not have permission for this resource",
        )
    if status == 404:
        return ToolErrorCode.NOT_FOUND, f"{name} resource was not found"
    if status == 429:
        wait = parse_retry_after(response.headers.get("retry-after"))
        hint = f" in {wait} seconds" if wait else " shortly"
        return (
            ToolErrorCode.RATE_LIMITED,
            f"{name} rate limit reached; try again{hint}",
        )
    if status >= 500:
        return (
            ToolErrorCode.PROVIDER_UNAVAILABLE,
            f"{name} is temporarily unavailable; try again",
        )
    return (
        ToolErrorCode.PROVIDER_ERROR,
        f"{name} rejected the request (HTTP {status})",
    )


def to_tool_error(
    exc: BaseException, identity: ToolIdentity, tool_name: str
) -> tuple[ToolErrorCode, str]:
    """Return the code and message a failure is reported with.

    ``ConnectorError`` keeps its own code and message; HTTP, timeout and MCP failures
    map per design section 5.6; anything else is ``internal_error``.
    """
    leaves = _flatten(exc)
    for leaf in leaves:
        if isinstance(leaf, ConnectorError):
            return leaf.code, clip(str(leaf), MAX_ERROR_MESSAGE_CHARS)
    for leaf in leaves:
        if isinstance(leaf, httpx.HTTPStatusError):
            return status_error(leaf.response, identity)
    for leaf in leaves:
        if isinstance(leaf, httpx.TimeoutException | httpx.TransportError):
            return (
                ToolErrorCode.PROVIDER_UNAVAILABLE,
                f"{identity.display_name} is temporarily unavailable; try again",
            )
    for leaf in leaves:
        if isinstance(leaf, ToolException):
            text = " ".join(str(leaf).split())
            return (
                ToolErrorCode.PROVIDER_ERROR,
                f"{identity.display_name} reported an error: "
                + (clip(text, MAX_ERROR_MESSAGE_CHARS) or "no details"),
            )
    return ToolErrorCode.INTERNAL_ERROR, f"Unexpected error in {tool_name}"


def make_connector_tool(
    *,
    name: str,
    description: str,
    args_schema: dict[str, Any],
    identity: ToolIdentity,
    body: ToolBody,
    audit: ConnectorAudit,
    write_capable: bool,
    source_name: str,
) -> StructuredTool:
    """Wrap ``body`` as a never-raising, audited LangChain tool.

    ``args_schema`` is the JSON schema the model sees; ``body`` receives the raw
    arguments and validates them itself, so a bad call is audited like any other.
    """

    async def _run(run_config: RunnableConfig, **arguments: Any) -> str:
        started = time.monotonic()
        outcome = "ok"
        error_code: str | None = None
        try:
            text = shape_result(await body(arguments))
        except Exception as exc:  # noqa: BLE001 - a tool never raises; cancellation is a BaseException and passes through
            code, message = to_tool_error(exc, identity, name)
            outcome, error_code = "error", code.value
            logger.info(
                "connector tool failed connector=%s tool=%s code=%s error=%s",
                identity.connector_key,
                name,
                code.value,
                type(exc).__name__,
            )
            text = json.dumps(error_envelope(code, message, identity.connector_key))
        await _record(
            audit,
            identity,
            name,
            outcome,
            error_code,
            int((time.monotonic() - started) * 1000),
            agent_ref_from_config(run_config),
        )
        return text

    return StructuredTool(
        name=name,
        description=description,
        args_schema=args_schema,
        coroutine=_run,
        handle_tool_error=True,
        handle_validation_error=True,
        metadata=tool_metadata(
            identity, write_capable=write_capable, source_name=source_name
        ),
    )


def make_stub_tool(
    *,
    name: str,
    description: str,
    identity: ToolIdentity,
    audit: ConnectorAudit,
    code: ToolErrorCode,
    message: str,
    write_capable: bool = True,
    source_name: str | None = None,
) -> StructuredTool:
    """A tool that answers every call with one fixed error (connection missing, expired, ...).

    The schema is permissive because the real one is unknown or needs a token. A
    stub whose write flag is unknown counts as a write (``write_capable=True``).
    """

    async def _body(_arguments: dict[str, Any]) -> str:
        raise ConnectorError(code, message, connector=identity.connector_key)

    return make_connector_tool(
        name=name,
        description=description,
        args_schema=dict(PERMISSIVE_SCHEMA),
        identity=identity,
        body=_body,
        audit=audit,
        write_capable=write_capable,
        source_name=source_name or name,
    )


async def _record(
    audit: ConnectorAudit,
    identity: ToolIdentity,
    tool_name: str,
    outcome: str,
    error_code: str | None,
    duration_ms: int,
    agent_ref: str | None,
) -> None:
    if identity.user_id is None:
        return
    try:
        await audit.record_tool_call(
            user_id=identity.user_id,
            connector_key=identity.connector_key,
            tool_name=tool_name,
            outcome=outcome,
            error_code=error_code,
            duration_ms=duration_ms,
            run_id=identity.run_id,
            agent_ref=agent_ref,
        )
    except Exception as exc:  # noqa: BLE001 - auditing never fails a tool
        logger.warning(
            "connector audit call failed connector=%s error=%s",
            identity.connector_key,
            type(exc).__name__,
        )
