"""``ConnectorAuth``: current token per request, one refresh and retry after a 401."""

from __future__ import annotations

import httpx
import pytest

from app.connectors.errors import ConnectorError, ToolErrorCode
from app.connectors.tokens import AccessToken
from app.connectors.tools.auth import ConnectorAuth


class _Tokens:
    """Scripted token source that records how it was called."""

    def __init__(self, *tokens: AccessToken) -> None:
        self._tokens = list(tokens)
        self.calls: list[dict[str, object]] = []

    async def access_token(
        self,
        user_id: str,
        connector_key: str,
        *,
        force_refresh: bool = False,
        rejected_version: int | None = None,
    ) -> AccessToken:
        self.calls.append(
            {
                "user_id": user_id,
                "connector_key": connector_key,
                "force_refresh": force_refresh,
                "rejected_version": rejected_version,
            }
        )
        return self._tokens.pop(0) if len(self._tokens) > 1 else self._tokens[0]


def _client(
    tokens: _Tokens, statuses: list[int]
) -> tuple[httpx.AsyncClient, list[str]]:
    seen: list[str] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization", ""))
        return httpx.Response(statuses.pop(0) if len(statuses) > 1 else statuses[0])

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(_handler),
        auth=ConnectorAuth("user-a", "jira", tokens),
    )
    return client, seen


class TestConnectorAuth:
    @pytest.mark.asyncio
    async def test_auth_flow_sends_current_token_when_request_succeeds(self) -> None:
        tokens = _Tokens(AccessToken("tok-1", 1))
        client, seen = _client(tokens, [200])

        async with client:
            response = await client.get("https://example.test/x")

        assert response.status_code == 200
        assert seen == ["Bearer tok-1"]
        assert tokens.calls == [
            {
                "user_id": "user-a",
                "connector_key": "jira",
                "force_refresh": False,
                "rejected_version": None,
            }
        ]

    @pytest.mark.asyncio
    async def test_auth_flow_reads_token_again_when_second_request_is_sent(
        self,
    ) -> None:
        tokens = _Tokens(AccessToken("tok-1", 1), AccessToken("tok-2", 2))
        client, seen = _client(tokens, [200])

        async with client:
            await client.get("https://example.test/a")
            await client.get("https://example.test/b")

        assert seen == ["Bearer tok-1", "Bearer tok-2"]

    @pytest.mark.asyncio
    async def test_auth_flow_refreshes_once_and_retries_when_first_answer_is_401(
        self,
    ) -> None:
        tokens = _Tokens(AccessToken("old", 4), AccessToken("new", 5))
        client, seen = _client(tokens, [401, 200])

        async with client:
            response = await client.get("https://example.test/x")

        assert response.status_code == 200
        assert seen == ["Bearer old", "Bearer new"]
        assert tokens.calls[1]["force_refresh"] is True
        assert tokens.calls[1]["rejected_version"] == 4

    @pytest.mark.asyncio
    async def test_auth_flow_does_not_loop_when_retry_is_also_401(self) -> None:
        tokens = _Tokens(AccessToken("old", 1), AccessToken("new", 2))
        client, seen = _client(tokens, [401])

        async with client:
            response = await client.get("https://example.test/x")

        assert response.status_code == 401
        assert seen == ["Bearer old", "Bearer new"]
        assert len(tokens.calls) == 2

    @pytest.mark.asyncio
    async def test_auth_flow_raises_connector_error_when_token_unavailable(
        self,
    ) -> None:
        class _Failing(_Tokens):
            async def access_token(
                self, *args: object, **kwargs: object
            ) -> AccessToken:  # type: ignore[override]
                raise ConnectorError(
                    ToolErrorCode.CONNECTION_EXPIRED, "expired", connector="jira"
                )

        client, seen = _client(_Failing(AccessToken("x", 1)), [200])

        async with client:
            with pytest.raises(ConnectorError) as excinfo:
                await client.get("https://example.test/x")

        assert excinfo.value.code is ToolErrorCode.CONNECTION_EXPIRED
        assert seen == []

    def test_sync_auth_flow_raises_not_implemented_when_called(self) -> None:
        auth = ConnectorAuth("user-a", "jira", _Tokens(AccessToken("t", 1)))

        with pytest.raises(NotImplementedError):
            auth.sync_auth_flow(httpx.Request("GET", "https://example.test/x"))
