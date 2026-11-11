"""Unit tests for ``app.connectors.http``."""

from __future__ import annotations

import httpx
import pytest

from app.connectors.http import (
    USER_AGENT,
    ProviderCallFailed,
    default_http_client_factory,
    json_object,
    safe_error_code,
    send,
)


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize("value", ["invalid_grant", "bad_refresh_token", "a"])
def test_safe_error_code_returns_value_when_plain_oauth_code(value):
    # Act / Assert
    assert safe_error_code(value) == value


@pytest.mark.parametrize(
    "value", ["Invalid Grant", "x" * 65, "", "a-b", "<script>", 5, None, ["x"]]
)
def test_safe_error_code_returns_none_when_value_is_not_a_plain_code(value):
    # Act / Assert
    assert safe_error_code(value) is None


def test_send_returns_response_when_status_is_4xx():
    # Arrange
    client = _client(lambda request: httpx.Response(400, json={"error": "x"}))

    # Act
    response = send(client, "POST", "https://example.test/token")

    # Assert
    assert response.status_code == 400


@pytest.mark.parametrize("status", [429, 500, 502, 503])
def test_send_raises_unavailable_when_status_is_429_or_5xx(status):
    # Arrange
    client = _client(lambda request: httpx.Response(status))

    # Act
    with pytest.raises(ProviderCallFailed) as raised:
        send(client, "GET", "https://example.test/x")

    # Assert
    assert raised.value.kind == "unavailable"
    assert raised.value.status == status


def test_send_raises_unavailable_with_exception_type_when_transport_times_out():
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow", request=request)

    # Act
    with pytest.raises(ProviderCallFailed) as raised:
        send(_client(handler), "GET", "https://example.test/x")

    # Assert
    assert raised.value.kind == "unavailable"
    assert raised.value.error_code == "ConnectTimeout"


def test_json_object_returns_dict_when_body_is_a_json_object():
    # Act
    body = json_object(httpx.Response(200, json={"a": 1}))

    # Assert
    assert body == {"a": 1}


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not json"),
        httpx.Response(200, json=[1, 2]),
        httpx.Response(200, json="text"),
    ],
)
def test_json_object_raises_malformed_when_body_is_not_a_json_object(response):
    # Act / Assert
    with pytest.raises(ProviderCallFailed) as raised:
        json_object(response)
    assert raised.value.kind == "malformed"


def test_default_http_client_factory_sets_agent_timeout_and_no_redirects_when_built():
    # Act
    with default_http_client_factory(7)() as client:
        # Assert
        assert client.headers["user-agent"] == USER_AGENT
        assert client.follow_redirects is False
        assert client.timeout.read == 7


def test_provider_call_failed_message_has_no_response_body_when_raised():
    # Act
    error = ProviderCallFailed("rejected", "invalid_grant", 400)

    # Assert
    assert (
        str(error) == "provider call failed kind=rejected code=invalid_grant status=400"
    )
