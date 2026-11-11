"""Connectors API: connect external accounts (GitHub, Jira) for the signed-in user.

Five endpoints under ``/api/connectors``. Every response sets ``Cache-Control:
no-store`` and none carries a token, ciphertext, authorization code, state or
verifier. The OAuth callback is the only public route: a provider's browser redirect
cannot carry the bearer token, so the single-use, hashed, 10-minute state row bound
to the initiating ``user_id`` is its credential. It always answers with a 303 to the
landing page, never JSON.

The callback route is declared before the ``{key}`` routes, and ``oauth`` is a
reserved word no connector key can use.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from agents.capabilities.connector_catalog import CONNECTOR_KEY_PATTERN
from app.connectors.errors import (
    CallbackReason,
    ConnectorError,
    ConnectorNotConfigured,
    ConnectorNotFound,
    TooManyPendingAuthorizations,
)
from app.connectors.oauth import CallbackParams
from app.connectors.registry import RegisteredConnector
from app.connectors.services import ConnectorServices, get_connector_services
from app.connectors.store import ConnectionRecord
from app.connectors.tool_listing import ConnectorExpired, ConnectorNotConnected
from app.core.dependencies import get_current_user
from app.models.user import User

logger = logging.getLogger("app.api.connectors")

_NO_STORE = {"Cache-Control": "no-store"}
#: Where the callback sends the browser (a static page, relative so the host stays).
_LANDING_PATH = "/connectors/oauth-complete"


def _no_store(response: Response) -> None:
    """Router dependency: every response is uncacheable."""
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(
    prefix="/api/connectors", tags=["connectors"], dependencies=[Depends(_no_store)]
)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ConnectorAccount(BaseModel):
    """The provider account behind a connection."""

    id: str
    display_name: str | None
    login: str | None


class ConnectorSite(BaseModel):
    """A Jira site the connection can reach."""

    id: str
    name: str
    url: str


class ConnectorSummary(BaseModel):
    """One connector card."""

    key: str
    display_name: str
    description: str
    icon: str
    docs_url: str
    mode: Literal["remote_mcp", "native_api"]
    status: Literal["connected", "not_connected", "expired", "not_configured"]
    account: ConnectorAccount | None
    requested_scopes: list[str]
    granted_scopes: list[str]
    sites: list[ConnectorSite]
    connected_at: datetime | None
    last_refreshed_at: datetime | None


class ConnectorListResponse(BaseModel):
    """All connectors, in catalog order."""

    connectors: list[ConnectorSummary]


class AuthorizeResponse(BaseModel):
    """Where to send the user to approve the connection."""

    authorization_url: str
    expires_at: datetime


class DisconnectResponse(BaseModel):
    """Result of a disconnect."""

    status: Literal["disconnected"]
    provider_revocation: Literal["revoked", "failed", "not_attempted"]


class ConnectorTool(BaseModel):
    """One tool a workflow step can switch on."""

    name: str
    source_name: str
    title: str
    description: str
    write_capable: bool


class ConnectorToolsResponse(BaseModel):
    """The tools of one connector."""

    connector: str
    status: Literal["connected", "not_connected", "expired"]
    tools: list[ConnectorTool]
    listed_at: datetime | None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reject(
    status_code: int, error: str, code: str, *, recoverable: bool = False
) -> HTTPException:
    """Typed error with the project's envelope (as ``run_commands._reject``)."""
    return HTTPException(
        status_code=status_code,
        detail={"error": error, "code": code, "recoverable": recoverable},
        headers=_NO_STORE,
    )


def _not_found() -> HTTPException:
    return _reject(
        status.HTTP_404_NOT_FOUND, "Connector not found", "connector_not_found"
    )


def _known_key(key: str, services: ConnectorServices) -> str:
    """Return ``key`` when it is a catalog connector, else raise 404."""
    if not CONNECTOR_KEY_PATTERN.match(key) or services.registry.get(key) is None:
        raise _not_found()
    return key


def _summary(
    entry: RegisteredConnector, record: ConnectionRecord | None
) -> ConnectorSummary:
    definition = entry.definition
    connector_status: Literal["connected", "not_connected", "expired", "not_configured"]
    if not entry.configured:
        connector_status = "not_configured"
    elif record is None:
        connector_status = "not_connected"
    elif record.is_active:
        connector_status = "connected"
    else:
        connector_status = "expired"
    account = None
    sites: list[ConnectorSite] = []
    if record is not None:
        account = ConnectorAccount(
            id=record.provider_account_id,
            display_name=record.provider_account_name,
            login=record.provider_account_login,
        )
        sites = _sites(record)
    return ConnectorSummary(
        key=definition.key,
        display_name=definition.display_name,
        description=definition.description,
        icon=definition.icon,
        docs_url=definition.docs_url,
        mode=definition.tooling.mode,
        status=connector_status,
        account=account,
        requested_scopes=list(definition.oauth.scopes),
        granted_scopes=list(record.granted_scopes) if record else [],
        sites=sites,
        connected_at=record.created_at if record else None,
        last_refreshed_at=record.last_refreshed_at if record else None,
    )


def _sites(record: ConnectionRecord) -> list[ConnectorSite]:
    raw = (record.provider_metadata or {}).get("sites")
    if not isinstance(raw, list):
        return []
    sites: list[ConnectorSite] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        site_id, name, url = item.get("id"), item.get("name"), item.get("url")
        if all(isinstance(value, str) for value in (site_id, name, url)):
            sites.append(ConnectorSite(id=site_id, name=name, url=url))
    return sites


def _callback_redirect(
    connector: str | None, reason: CallbackReason | None
) -> Response:
    """Build the 303 to the landing page. The query holds only allow-listed values."""
    params: list[tuple[str, str]] = []
    if connector is not None:
        params.append(("connector", connector))
    if reason is None:
        params.append(("result", "connected"))
    else:
        params.append(("result", "error"))
        params.append(("reason", reason.value))
    return RedirectResponse(
        url=f"{_LANDING_PATH}?{urlencode(params)}",
        status_code=status.HTTP_303_SEE_OTHER,
        headers={
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
            "Referrer-Policy": "no-referrer",
        },
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=ConnectorListResponse)
def list_connectors(
    user: User = Depends(get_current_user),
    services: ConnectorServices = Depends(get_connector_services),
) -> ConnectorListResponse:
    """List every connector with the caller's connection status."""
    records = {r.connector_key: r for r in services.store.list_for_user(user.id)}
    return ConnectorListResponse(
        connectors=[
            _summary(entry, records.get(entry.definition.key))
            for entry in services.registry.all()
        ]
    )


@router.get("/oauth/callback")
def oauth_callback(
    state: str | None = Query(default=None),
    code: str | None = Query(default=None),
    iss: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    services: ConnectorServices = Depends(get_connector_services),
) -> Response:
    """Finish an authorization from the provider's redirect (public route).

    Always answers 303 to the landing page, never JSON, so no length limit is
    declared here (a limit would answer 422); the service validates every value and
    maps a bad one to a reason code. ``error_description`` is ignored: it is never
    stored, logged or echoed.
    """
    del error_description
    outcome = services.oauth.complete_callback(
        CallbackParams(state=state, code=code, iss=iss, error=error)
    )
    return _callback_redirect(outcome.connector_key, outcome.reason)


@router.post("/{key}/authorize", response_model=AuthorizeResponse)
def authorize_connector(
    key: str,
    user: User = Depends(get_current_user),
    services: ConnectorServices = Depends(get_connector_services),
) -> AuthorizeResponse:
    """Start an authorization and return the provider URL for the popup."""
    _known_key(key, services)
    try:
        started = services.oauth.start_authorization(user.id, key)
    except ConnectorNotFound as exc:
        raise _not_found() from exc
    except ConnectorNotConfigured as exc:
        logger.info("authorize refused, connector not configured connector=%s", key)
        raise _reject(
            status.HTTP_409_CONFLICT,
            "Connector is not configured on this server",
            "connector_not_configured",
        ) from exc
    except TooManyPendingAuthorizations as exc:
        logger.info("authorize refused, too many pending connector=%s", key)
        raise _reject(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many pending authorizations; finish or wait for the open ones",
            "too_many_pending_authorizations",
            recoverable=True,
        ) from exc
    return AuthorizeResponse(
        authorization_url=started.authorization_url, expires_at=started.expires_at
    )


@router.delete("/{key}", response_model=DisconnectResponse)
def disconnect_connector(
    key: str,
    user: User = Depends(get_current_user),
    services: ConnectorServices = Depends(get_connector_services),
) -> DisconnectResponse:
    """Revoke the grant at the provider (best effort) and delete the local connection."""
    _known_key(key, services)
    try:
        outcome = services.oauth.disconnect(user.id, key)
    except ConnectorNotFound as exc:
        raise _not_found() from exc
    return DisconnectResponse(
        status="disconnected", provider_revocation=outcome.provider_revocation
    )


@router.get("/{key}/tools", response_model=ConnectorToolsResponse)
async def list_connector_tools(
    key: str,
    user: User = Depends(get_current_user),
    services: ConnectorServices = Depends(get_connector_services),
) -> ConnectorToolsResponse:
    """List the tools of a connector the caller can switch on in a workflow step."""
    _known_key(key, services)
    try:
        view = await services.tool_listing.list_tools(user.id, key)
    except ConnectorNotFound as exc:
        raise _not_found() from exc
    except ConnectorNotConfigured as exc:
        raise _reject(
            status.HTTP_409_CONFLICT,
            "Connector is not configured on this server",
            "connector_not_configured",
        ) from exc
    except ConnectorNotConnected as exc:
        raise _reject(
            status.HTTP_409_CONFLICT,
            "Connector is not connected",
            "connector_not_connected",
        ) from exc
    except ConnectorExpired as exc:
        raise _reject(
            status.HTTP_409_CONFLICT,
            "Connector connection expired; reconnect it",
            "connector_expired",
        ) from exc
    except ConnectorError as exc:
        logger.warning("tool listing failed connector=%s code=%s", key, exc.code.value)
        raise _reject(
            status.HTTP_502_BAD_GATEWAY,
            "The provider is temporarily unavailable",
            "provider_unavailable",
            recoverable=True,
        ) from exc
    return ConnectorToolsResponse(
        connector=view.connector_key,
        status=view.status,
        tools=[
            ConnectorTool(
                name=tool.name,
                source_name=tool.source_name,
                title=tool.title,
                description=tool.description,
                write_capable=tool.write_capable,
            )
            for tool in view.tools
        ],
        listed_at=view.listed_at,
    )
