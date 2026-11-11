"""OAuth for connectors: provider protocol calls and the authorize/callback/disconnect flows.

``OAuthClient`` is stateless: it builds authorize URLs and talks to the provider's
token, account, site and revoke endpoints. ``OAuthService`` runs the flows on top of
it with the connection store and the token cipher.

Security properties (design sections 1.2 to 1.4 and 5):

* the state is random, stored only as a SHA-256 hash, bound to the initiating
  ``user_id``, expires after 10 minutes and is consumed by one conditional UPDATE;
* PKCE is always S256 and the verifier is stored encrypted;
* RFC 9207 ``iss`` is checked before the code is redeemed;
* the redirect URI sent is the one stored on the state row, byte for byte;
* tokens are encrypted before they reach the store and never appear in a log line,
  a URL, an audit row or an exception message;
* the callback always yields an outcome (never an exception) so the route can answer
  with a redirect.

Everything here is synchronous: it runs in FastAPI's threadpool or a worker thread.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal, Protocol
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy.exc import SQLAlchemyError

from agents.capabilities.connector_catalog import ConnectorDefinition
from app.connectors.adapters import (
    AccountInfo,
    PostConnectResult,
    RevocationOutcome,
    RevokeMaterial,
    get_adapter,
    split_scopes,
)
from app.connectors.crypto import TokenCodec
from app.connectors.errors import (
    CallbackReason,
    ConnectorError,
    ConnectorNotConfigured,
    ConnectorNotFound,
    UndecryptableToken,
)
from app.connectors.http import (
    HttpClientFactory,
    ProviderCallFailed,
    json_object,
    safe_error_code,
    send,
)
from app.connectors.pkce import (
    CODE_CHALLENGE_METHOD,
    code_challenge_s256,
    generate_code_verifier,
    generate_state,
    hash_state,
)
from app.connectors.registry import ClientCredentials, ConnectorRegistry
from app.connectors.store import (
    AuditEntry,
    ConnectionRecord,
    ConnectionStore,
    NewConnection,
    utcnow,
)
from app.models.connector import (
    AUDIT_AUTHORIZE_STARTED,
    AUDIT_CONNECT_FAILED,
    AUDIT_CONNECTED,
    AUDIT_DISCONNECTED,
    AUDIT_OUTCOME_ERROR,
    AUDIT_OUTCOME_OK,
    AUDIT_REVOKE_FAILED,
)

logger = logging.getLogger("app.connectors.oauth")

#: Authorization states live 10 minutes (design section 1.2).
STATE_TTL_SECONDS = 600
#: At most this many unexpired, unconsumed states per user.
MAX_PENDING_STATES = 5
#: States expired for longer than this are swept on callback.
STATE_SWEEP_AFTER = timedelta(hours=24)

_STATE_RE = re.compile(r"^[A-Za-z0-9_-]{20,128}$")
_CODE_RE = re.compile(r"^[\x21-\x7e]{1,2048}$")
_MAX_ISS_LENGTH = 256
_ACCESS_DENIED = "access_denied"
#: Token-endpoint error codes that mean our client credentials were refused.
_CLIENT_ERRORS = frozenset(
    {"invalid_client", "incorrect_client_credentials", "unauthorized_client"}
)


# ---------------------------------------------------------------------------
# Provider protocol
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TokenSet:
    """Tokens from a token-endpoint answer. Token values are hidden from ``repr``."""

    access_token: str = field(repr=False)
    refresh_token: str | None = field(repr=False)
    expires_in: int | None
    refresh_token_expires_in: int | None
    scope: str | None


class _TokenResponse(BaseModel):
    """The fields of a successful token answer that we use; everything else is ignored."""

    model_config = ConfigDict(extra="ignore")

    access_token: str | None = None
    token_type: str | None = None
    refresh_token: str | None = None
    expires_in: int | None = None
    refresh_token_expires_in: int | None = None
    scope: str | None = None


def _parse_token_answer(status_code: int, body: dict[str, object]) -> TokenSet:
    """Validate a token-endpoint body (HTTP 200 may still carry an ``error``)."""
    error = body.get("error")
    if error is not None:
        code = safe_error_code(error)
        kind = "client" if code in _CLIENT_ERRORS else "rejected"
        raise ProviderCallFailed(kind, code or "unknown_error", status_code)
    if status_code >= 400:
        raise ProviderCallFailed("rejected", status=status_code)
    try:
        parsed = _TokenResponse.model_validate(body)
    except ValidationError as exc:
        raise ProviderCallFailed("malformed", status=status_code) from exc
    if not parsed.access_token:
        raise ProviderCallFailed("malformed", status=status_code)
    if parsed.token_type is not None and parsed.token_type.lower() != "bearer":
        raise ProviderCallFailed("malformed", status=status_code)
    return TokenSet(
        access_token=parsed.access_token,
        refresh_token=parsed.refresh_token or None,
        expires_in=parsed.expires_in,
        refresh_token_expires_in=parsed.refresh_token_expires_in,
        scope=parsed.scope,
    )


class OAuthClient:
    """Calls a provider's OAuth endpoints. Holds no state and no secrets."""

    def __init__(self, http_factory: HttpClientFactory) -> None:
        self._http_factory = http_factory

    def build_authorization_url(
        self,
        definition: ConnectorDefinition,
        credentials: ClientCredentials,
        *,
        redirect_uri: str,
        state: str,
        code_challenge: str,
    ) -> str:
        """Return the provider authorize URL for one flow (PKCE S256, exact redirect URI)."""
        spec = definition.oauth
        params: list[tuple[str, str]] = [
            ("response_type", "code"),
            ("client_id", credentials.client_id),
            ("redirect_uri", redirect_uri),
            ("scope", " ".join(spec.scopes)),
            ("state", state),
            ("code_challenge", code_challenge),
            ("code_challenge_method", CODE_CHALLENGE_METHOD),
        ]
        if spec.resource_indicator:
            params.append(("resource", spec.resource_indicator))
        params.extend(spec.extra_authorize_params)
        return f"{spec.authorize_url}?{urlencode(params)}"

    def exchange_code(
        self,
        definition: ConnectorDefinition,
        credentials: ClientCredentials,
        *,
        code: str,
        code_verifier: str,
        redirect_uri: str,
    ) -> TokenSet:
        """Redeem an authorization code.

        Raises:
            ProviderCallFailed: the provider refused or did not answer usably.
        """
        return self._token_request(
            definition,
            credentials,
            {
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": code_verifier,
                "redirect_uri": redirect_uri,
            },
        )

    def refresh(
        self,
        definition: ConnectorDefinition,
        credentials: ClientCredentials,
        refresh_token: str,
    ) -> TokenSet:
        """Exchange a refresh token for new tokens (the provider may rotate it).

        Raises:
            ProviderCallFailed: the provider refused or did not answer usably.
        """
        return self._token_request(
            definition,
            credentials,
            {"grant_type": "refresh_token", "refresh_token": refresh_token},
        )

    def fetch_account(
        self, definition: ConnectorDefinition, access_token: str
    ) -> AccountInfo:
        """Look up the provider account behind ``access_token``.

        Raises:
            ProviderCallFailed: the lookup failed or returned no usable account.
        """
        adapter = get_adapter(definition.key)
        headers = {
            **adapter.account_headers(),
            "Authorization": f"Bearer {access_token}",
        }
        with self._http_factory() as client:
            response = send(client, "GET", definition.account.url, headers=headers)
        return adapter.parse_account(definition, response)

    def fetch_post_connect(
        self, definition: ConnectorDefinition, access_token: str
    ) -> PostConnectResult:
        """Collect provider-specific data (Jira sites). No call when the catalog has none.

        Raises:
            ProviderCallFailed: the provider call failed.
        """
        if definition.post_connect is None:
            return PostConnectResult()
        with self._http_factory() as client:
            return get_adapter(definition.key).post_connect(
                client, definition, access_token
            )

    def revoke(
        self,
        definition: ConnectorDefinition,
        credentials: ClientCredentials,
        material: RevokeMaterial,
    ) -> RevocationOutcome:
        """Revoke the grant at the provider. Returns ``failed`` instead of raising."""
        try:
            with self._http_factory() as client:
                return get_adapter(definition.key).revoke(
                    client, definition, credentials, material
                )
        except Exception as exc:  # a revoke must never raise into a disconnect
            logger.warning(
                "revoke raised connector=%s error=%s",
                definition.key,
                type(exc).__name__,
            )
            return "failed"

    def _token_request(
        self,
        definition: ConnectorDefinition,
        credentials: ClientCredentials,
        fields: dict[str, str],
    ) -> TokenSet:
        spec = definition.oauth
        payload = {
            **fields,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
        }
        if spec.resource_indicator:
            payload["resource"] = spec.resource_indicator
        headers = {"Accept": "application/json"}
        with self._http_factory() as client:
            if spec.token_request_encoding == "json":
                response = send(
                    client, "POST", spec.token_url, json=payload, headers=headers
                )
            else:
                response = send(
                    client, "POST", spec.token_url, data=payload, headers=headers
                )
        try:
            body = json_object(response)
        except ProviderCallFailed:
            # A non-JSON 4xx is a refusal; a non-JSON 2xx is a broken provider.
            if response.status_code >= 400:
                raise ProviderCallFailed("rejected", status=response.status_code)
            raise
        return _parse_token_answer(response.status_code, body)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class FreshAccessTokenSource(Protocol):
    """Gives the OAuth service a current access token (refreshing it when needed)."""

    def fresh_access_token(self, user_id: str, connector_key: str) -> str:
        """Return a usable access token or raise ``ConnectorError``."""
        ...


@dataclass(frozen=True)
class AuthorizationStart:
    """Result of starting an authorization."""

    authorization_url: str
    expires_at: datetime


@dataclass(frozen=True)
class CallbackParams:
    """The raw query parameters of the OAuth callback. Secrets are hidden from ``repr``."""

    state: str | None = field(default=None, repr=False)
    code: str | None = field(default=None, repr=False)
    iss: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class CallbackOutcome:
    """What the callback hands to the route: a connector key and a reason on failure.

    ``reason`` is ``None`` when the connection was stored. ``connector_key`` is
    ``None`` when the state could not be resolved to a connector.
    """

    connector_key: str | None
    reason: CallbackReason | None = None

    @property
    def connected(self) -> bool:
        """Whether the connection was stored."""
        return self.reason is None


@dataclass(frozen=True)
class DisconnectOutcome:
    """Result of a disconnect."""

    provider_revocation: Literal["revoked", "failed", "not_attempted"]
    was_connected: bool


class OAuthService:
    """Authorize, callback and disconnect flows for catalog connectors."""

    def __init__(
        self,
        *,
        registry: ConnectorRegistry,
        store: ConnectionStore,
        cipher: TokenCodec,
        client: OAuthClient,
        token_source: FreshAccessTokenSource,
        clock: Callable[[], datetime] = utcnow,
        on_connection_changed: Callable[[str, str], object] | None = None,
    ) -> None:
        """``on_connection_changed(user_id, connector_key)`` runs after a connect,
        reconnect or disconnect (the tool-list cache hooks in here)."""
        self._registry = registry
        self._store = store
        self._cipher = cipher
        self._client = client
        self._token_source = token_source
        self._clock = clock
        self._on_connection_changed = on_connection_changed

    def _connection_changed(self, user_id: str, connector_key: str) -> None:
        if self._on_connection_changed is None:
            return
        try:
            self._on_connection_changed(user_id, connector_key)
        except Exception as exc:  # a cache problem must not fail a connect
            logger.warning(
                "connection-changed hook failed connector=%s error=%s",
                connector_key,
                type(exc).__name__,
            )

    # ---- authorize ---------------------------------------------------------

    def start_authorization(
        self, user_id: str, connector_key: str
    ) -> AuthorizationStart:
        """Create a state for ``user_id`` and return the provider authorize URL.

        Raises:
            ConnectorNotFound: no such connector.
            ConnectorNotConfigured: the connector's settings are missing or invalid.
            TooManyPendingAuthorizations: the user has too many open authorizations.
        """
        entry = self._registry.get(connector_key)
        if entry is None:
            raise ConnectorNotFound(connector_key)
        redirect_uri = self._registry.redirect_uri
        if not entry.configured or redirect_uri is None:
            raise ConnectorNotConfigured(connector_key)
        credentials = self._registry.client_credentials(connector_key)
        state = generate_state()
        verifier = generate_code_verifier()
        expires_at = self._store.create_state(
            user_id=user_id,
            connector_key=connector_key,
            state_hash=hash_state(state),
            code_verifier_ciphertext=self._cipher.encrypt(verifier),
            redirect_uri=redirect_uri,
            ttl_seconds=STATE_TTL_SECONDS,
            max_pending=MAX_PENDING_STATES,
        )
        url = self._client.build_authorization_url(
            entry.definition,
            credentials,
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=code_challenge_s256(verifier),
        )
        self._audit(user_id, connector_key, AUDIT_AUTHORIZE_STARTED, AUDIT_OUTCOME_OK)
        return AuthorizationStart(authorization_url=url, expires_at=expires_at)

    # ---- callback ----------------------------------------------------------

    def complete_callback(self, params: CallbackParams) -> CallbackOutcome:
        """Finish an authorization from the provider's redirect. Never raises."""
        if params.state is None or not _STATE_RE.match(params.state):
            return CallbackOutcome(None, CallbackReason.INVALID_STATE)
        known_key: list[str] = []
        try:
            return self._complete(params, params.state, known_key)
        except Exception as exc:  # the callback must always produce a redirect
            logger.error(
                "oauth callback failed unexpectedly connector=%s error=%s",
                known_key[0] if known_key else "-",
                type(exc).__name__,
            )
            return CallbackOutcome(
                known_key[0] if known_key else None, CallbackReason.SERVER_ERROR
            )

    def _complete(
        self, params: CallbackParams, state: str, known_key: list[str]
    ) -> CallbackOutcome:
        self._sweep()
        state_hash = hash_state(state)
        consumed = self._store.consume_state(state_hash)
        if consumed is None:
            logger.warning("oauth callback with unknown state hash=%s", state_hash[:8])
            return CallbackOutcome(None, CallbackReason.INVALID_STATE)
        key = consumed.connector_key
        known_key.append(key)
        user_id = consumed.user_id

        entry = self._registry.get(key)
        if entry is None or not entry.configured:
            return self._fail(user_id, key, CallbackReason.NOT_CONFIGURED)
        definition = entry.definition

        if params.error is not None:
            code = safe_error_code(params.error)
            logger.info(
                "oauth provider returned an error connector=%s code=%s", key, code
            )
            reason = (
                CallbackReason.ACCESS_DENIED
                if code == _ACCESS_DENIED
                else CallbackReason.PROVIDER_ERROR
            )
            return self._fail(user_id, key, reason, code)

        issuer_reason = self._check_issuer(definition, params.iss)
        if issuer_reason is not None:
            logger.warning(
                "oauth issuer check failed connector=%s reason=%s",
                key,
                issuer_reason.value,
            )
            return self._fail(user_id, key, issuer_reason)

        if params.code is None or not _CODE_RE.match(params.code):
            return self._fail(user_id, key, CallbackReason.MISSING_CODE)

        try:
            verifier = self._cipher.decrypt(consumed.code_verifier_ciphertext)
        except UndecryptableToken:
            logger.error("oauth verifier could not be decrypted connector=%s", key)
            return self._fail(
                user_id, key, CallbackReason.SERVER_ERROR, "undecryptable"
            )

        credentials = self._registry.client_credentials(key)
        try:
            tokens = self._client.exchange_code(
                definition,
                credentials,
                code=params.code,
                code_verifier=verifier,
                redirect_uri=consumed.redirect_uri,
            )
        except ProviderCallFailed as exc:
            return self._fail_exchange(user_id, definition, exc)

        try:
            account = self._client.fetch_account(definition, tokens.access_token)
            post_connect = self._client.fetch_post_connect(
                definition, tokens.access_token
            )
        except ProviderCallFailed as exc:
            logger.warning(
                "oauth account lookup failed connector=%s kind=%s status=%s",
                key,
                exc.kind,
                exc.status,
            )
            return self._fail(
                user_id, key, CallbackReason.ACCOUNT_LOOKUP_FAILED, exc.kind
            )
        if not post_connect.usable:
            logger.info("oauth grant has no usable site connector=%s", key)
            return self._fail(user_id, key, CallbackReason.NO_ACCESSIBLE_SITES)

        now = self._clock()
        scopes = (
            account.scopes if account.scopes is not None else split_scopes(tokens.scope)
        )
        try:
            self._store.upsert(
                NewConnection(
                    user_id=user_id,
                    connector_key=key,
                    provider_account_id=account.account_id,
                    provider_account_login=account.login,
                    provider_account_name=account.display_name,
                    granted_scopes=scopes,
                    provider_metadata=post_connect.metadata,
                    access_token_expires_at=_expiry(now, tokens.expires_in),
                    refresh_token_expires_at=_expiry(
                        now, tokens.refresh_token_expires_in
                    ),
                    access_token_ciphertext=self._cipher.encrypt(tokens.access_token),
                    refresh_token_ciphertext=(
                        self._cipher.encrypt(tokens.refresh_token)
                        if tokens.refresh_token
                        else None
                    ),
                )
            )
        except SQLAlchemyError as exc:
            logger.error(
                "oauth connection could not be stored connector=%s error=%s",
                key,
                type(exc).__name__,
            )
            return self._fail(user_id, key, CallbackReason.SERVER_ERROR, "store_failed")
        self._connection_changed(user_id, key)
        self._audit(user_id, key, AUDIT_CONNECTED, AUDIT_OUTCOME_OK)
        return CallbackOutcome(key)

    @staticmethod
    def _check_issuer(
        definition: ConnectorDefinition, iss: str | None
    ) -> CallbackReason | None:
        """RFC 9207: compare ``iss`` with the issuer as plain strings."""
        if iss is None:
            if definition.oauth.iss_param == "required":
                return CallbackReason.ISSUER_MISSING
            return None
        if len(iss) > _MAX_ISS_LENGTH or iss != definition.oauth.issuer:
            return CallbackReason.ISSUER_MISMATCH
        return None

    def _fail_exchange(
        self, user_id: str, definition: ConnectorDefinition, exc: ProviderCallFailed
    ) -> CallbackOutcome:
        key = definition.key
        if exc.kind == "unavailable":
            logger.warning(
                "oauth token exchange unavailable connector=%s status=%s",
                key,
                exc.status,
            )
            return self._fail(
                user_id, key, CallbackReason.PROVIDER_ERROR, "unavailable"
            )
        if exc.kind == "client":
            logger.error(
                "oauth client credentials were refused connector=%s; check %s and %s",
                key,
                definition.client_id_env,
                definition.client_secret_env,
            )
        else:
            logger.warning(
                "oauth token exchange failed connector=%s kind=%s code=%s",
                key,
                exc.kind,
                exc.error_code,
            )
        return self._fail(
            user_id,
            key,
            CallbackReason.TOKEN_EXCHANGE_FAILED,
            exc.error_code or exc.kind,
        )

    def _fail(
        self,
        user_id: str,
        key: str,
        reason: CallbackReason,
        error_code: str | None = None,
    ) -> CallbackOutcome:
        self._audit(
            user_id,
            key,
            AUDIT_CONNECT_FAILED,
            AUDIT_OUTCOME_ERROR,
            error_code or reason.value,
        )
        return CallbackOutcome(key, reason)

    def _sweep(self) -> None:
        try:
            self._store.sweep_expired_states(STATE_SWEEP_AFTER)
        except SQLAlchemyError as exc:
            logger.warning("oauth state sweep failed error=%s", type(exc).__name__)

    # ---- disconnect --------------------------------------------------------

    def disconnect(self, user_id: str, connector_key: str) -> DisconnectOutcome:
        """Revoke the grant at the provider (best effort) and delete the local row.

        A revoke failure never keeps tokens: the row is always deleted. Calling it
        with nothing connected is a no-op.

        Raises:
            ConnectorNotFound: no such connector.
        """
        entry = self._registry.get(connector_key)
        if entry is None:
            raise ConnectorNotFound(connector_key)
        record = self._store.get(user_id, connector_key)
        if record is None:
            return DisconnectOutcome("not_attempted", was_connected=False)
        revocation = self._revoke_remote(record)
        self._store.delete(user_id, connector_key)
        self._connection_changed(user_id, connector_key)
        self._audit(user_id, connector_key, AUDIT_DISCONNECTED, AUDIT_OUTCOME_OK)
        if revocation == "failed":
            self._audit(
                user_id,
                connector_key,
                AUDIT_REVOKE_FAILED,
                AUDIT_OUTCOME_ERROR,
                "revoke_failed",
            )
        return DisconnectOutcome(revocation, was_connected=True)

    def _revoke_remote(
        self, record: ConnectionRecord
    ) -> Literal["revoked", "failed", "not_attempted"]:
        """Revoke ``record`` at its provider. Never raises."""
        key = record.connector_key
        entry = self._registry.get(key)
        if entry is None or not entry.configured:
            logger.warning("revoke skipped, connector not configured connector=%s", key)
            return "not_attempted"
        definition = entry.definition
        adapter = get_adapter(key)
        try:
            if adapter.revoke_needs_access_token:
                # A GitHub token lives hours; one that is (nearly) expired is
                # refreshed first so the grant deletion can authenticate.
                # Probe first: the token source reports an undecryptable token as
                # an expired connection, which would read as a failed revoke.
                self._cipher.decrypt(record.access_token_ciphertext)
                try:
                    access_token = self._token_source.fresh_access_token(
                        record.user_id, key
                    )
                except ConnectorError as exc:
                    logger.warning(
                        "revoke failed, no current token connector=%s code=%s",
                        key,
                        exc.code.value,
                    )
                    return "failed"
                material = RevokeMaterial(access_token=access_token)
            else:
                material = RevokeMaterial(
                    access_token=self._cipher.decrypt(record.access_token_ciphertext),
                    refresh_token=(
                        self._cipher.decrypt(record.refresh_token_ciphertext)
                        if record.refresh_token_ciphertext
                        else None
                    ),
                )
            outcome = self._client.revoke(
                definition, self._registry.client_credentials(key), material
            )
        except UndecryptableToken:
            logger.warning("revoke skipped, token undecryptable connector=%s", key)
            return "not_attempted"
        except Exception as exc:
            logger.warning(
                "revoke failed unexpectedly connector=%s error=%s",
                key,
                type(exc).__name__,
            )
            return "failed"
        if outcome == "failed":
            logger.warning("provider revoke failed connector=%s", key)
        return outcome

    # ---- audit -------------------------------------------------------------

    def _audit(
        self,
        user_id: str,
        connector_key: str,
        action: str,
        outcome: str,
        error_code: str | None = None,
    ) -> None:
        self._store.record_audit(
            AuditEntry(
                user_id=user_id,
                connector_key=connector_key,
                action=action,
                outcome=outcome,
                error_code=error_code,
            )
        )


def _expiry(now: datetime, seconds: int | None) -> datetime | None:
    """Return ``now + seconds`` for a positive lifetime, else ``None`` (no expiry given)."""
    if seconds is None or seconds <= 0:
        return None
    return now + timedelta(seconds=seconds)
