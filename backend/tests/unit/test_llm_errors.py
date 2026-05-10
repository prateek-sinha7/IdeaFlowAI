"""Tests for the Bedrock LLM exception mapper (A7)."""

from __future__ import annotations

import pytest

from app.agents.llm_errors import LLMErrorPayload, map_exception


def _client_error(code: str):
    """Build a minimal botocore.exceptions.ClientError with a given AWS error code."""
    from botocore.exceptions import ClientError

    return ClientError(
        error_response={"Error": {"Code": code, "Message": f"Test {code}"}},
        operation_name="ConverseStream",
    )


# ---------------------------------------------------------------------------
# Bedrock / botocore mappings
# ---------------------------------------------------------------------------


class TestBedrockMapping:
    @pytest.mark.parametrize(
        "aws_code,expected_code,expected_recoverable",
        [
            ("ThrottlingException", "rate_limit", True),
            ("ServiceQuotaExceededException", "rate_limit", True),
            ("TooManyRequestsException", "rate_limit", True),
            ("ServiceUnavailableException", "connection_error", True),
            ("InternalServerException", "internal_error", True),
            ("ModelNotReadyException", "connection_error", True),
            ("ModelStreamErrorException", "connection_error", True),
            ("ModelTimeoutException", "timeout", True),
            ("AccessDeniedException", "auth_error", False),
            ("UnauthorizedException", "auth_error", False),
            ("ResourceNotFoundException", "api_key_missing", False),
            ("ValidationException", "internal_error", False),
        ],
    )
    def test_bedrock_known_codes_map_correctly(
        self, aws_code, expected_code, expected_recoverable
    ):
        result = map_exception(_client_error(aws_code))
        assert isinstance(result, LLMErrorPayload)
        assert result.code == expected_code
        assert result.recoverable == expected_recoverable
        assert result.message  # non-empty

    def test_bedrock_unknown_code_falls_back_to_internal_error_recoverable(self):
        result = map_exception(_client_error("SomeFutureCodeAWSAddedYesterday"))
        assert result.code == "internal_error"
        assert result.recoverable is True

    def test_bedrock_read_timeout_maps_to_timeout(self):
        from botocore.exceptions import ReadTimeoutError

        result = map_exception(ReadTimeoutError(endpoint_url="https://example", error="x"))
        assert result.code == "timeout"
        assert result.recoverable is True

    def test_bedrock_endpoint_connection_error_maps_to_connection(self):
        from botocore.exceptions import EndpointConnectionError

        result = map_exception(EndpointConnectionError(endpoint_url="https://example"))
        assert result.code == "connection_error"
        assert result.recoverable is True


# ---------------------------------------------------------------------------
# Generic fallback
# ---------------------------------------------------------------------------


class TestGenericFallback:
    def test_unrelated_exception_falls_back(self):
        result = map_exception(ValueError("unrelated"))
        assert result.code == "internal_error"
        assert result.recoverable is True
        assert result.message
