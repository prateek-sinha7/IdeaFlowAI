"""The connector tool wrapper: envelope, audit, truncation, metadata and error mapping."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from langchain_core.tools import ToolException
from pydantic import BaseModel, Field

from app.connectors.errors import ConnectorError, ToolErrorCode
from app.connectors.tools.base import (
    MAX_RESULT_CHARS,
    ToolIdentity,
    make_connector_tool,
    make_stub_tool,
    parse_retry_after,
    shape_result,
    to_tool_error,
    validate_arguments,
)
from tests.fakes.connector_services import ConnectorWorld, build_world

USER = "user-a"
CONFIG = {"configurable": {"thread_id": "run-1:agent-a"}}


def _identity(user_id: str | None = USER, run_id: str | None = "run-1") -> ToolIdentity:
    return ToolIdentity(
        connector_key="jira", display_name="Jira", user_id=user_id, run_id=run_id
    )


def _tool(world: ConnectorWorld, body: Any, *, user_id: str | None = USER) -> Any:
    return make_connector_tool(
        name="jira__probe",
        description="probe",
        args_schema={"type": "object", "additionalProperties": True},
        identity=_identity(user_id),
        body=body,
        audit=world.services.audit,
        write_capable=False,
        source_name="probe",
    )


def _status_error(
    status: int, headers: dict[str, str] | None = None
) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.test/x")
    response = httpx.Response(status, request=request, headers=headers)
    return httpx.HTTPStatusError("boom", request=request, response=response)


class TestMakeConnectorTool:
    @pytest.mark.asyncio
    async def test_ainvoke_returns_body_text_and_audits_ok_when_body_succeeds(
        self,
    ) -> None:
        world = build_world()

        async def body(arguments: dict[str, Any]) -> str:
            return f"got {arguments['q']}"

        result = await _tool(world, body).ainvoke({"q": "x"}, config=CONFIG)

        assert result == "got x"
        (entry,) = world.store.audit
        assert (entry.action, entry.outcome, entry.error_code) == (
            "tool_call",
            "ok",
            None,
        )
        assert entry.tool_name == "jira__probe"
        assert entry.run_id == "run-1"
        assert entry.agent_ref == "agent-a"
        assert entry.duration_ms is not None

    @pytest.mark.asyncio
    async def test_ainvoke_returns_envelope_and_does_not_raise_when_body_raises_unexpected_error(
        self,
    ) -> None:
        world = build_world()

        async def body(_arguments: dict[str, Any]) -> str:
            raise RuntimeError("secret detail that must not leak")

        result = await _tool(world, body).ainvoke({}, config=CONFIG)

        error = json.loads(result)["error"]
        assert error == {
            "code": "internal_error",
            "message": "Unexpected error in jira__probe",
            "connector": "jira",
            "recoverable": False,
        }
        assert "secret detail" not in result
        assert world.store.audit[0].error_code == "internal_error"
        assert world.store.audit[0].outcome == "error"

    @pytest.mark.asyncio
    async def test_ainvoke_keeps_connector_error_code_when_body_raises_connector_error(
        self,
    ) -> None:
        world = build_world()

        async def body(_arguments: dict[str, Any]) -> str:
            raise ConnectorError(
                ToolErrorCode.CONNECTION_MISSING,
                "Jira connection missing, reconnect in Connectors",
                connector="jira",
            )

        result = await _tool(world, body).ainvoke({}, config=CONFIG)

        error = json.loads(result)["error"]
        assert error["code"] == "connection_missing"
        assert error["message"] == "Jira connection missing, reconnect in Connectors"
        assert error["recoverable"] is False

    @pytest.mark.asyncio
    async def test_ainvoke_marks_recoverable_when_code_is_provider_unavailable(
        self,
    ) -> None:
        world = build_world()

        async def body(_arguments: dict[str, Any]) -> str:
            raise httpx.ConnectTimeout("slow")

        result = await _tool(world, body).ainvoke({}, config=CONFIG)

        error = json.loads(result)["error"]
        assert error["code"] == "provider_unavailable"
        assert error["recoverable"] is True

    @pytest.mark.asyncio
    async def test_ainvoke_truncates_result_when_body_returns_too_much(self) -> None:
        world = build_world()

        async def body(_arguments: dict[str, Any]) -> str:
            return "x" * (MAX_RESULT_CHARS + 500)

        result = await _tool(world, body).ainvoke({}, config=CONFIG)

        assert len(result) == MAX_RESULT_CHARS
        assert result.endswith("[result truncated]")

    @pytest.mark.asyncio
    async def test_ainvoke_writes_no_audit_row_when_run_is_anonymous(self) -> None:
        world = build_world()

        async def body(_arguments: dict[str, Any]) -> str:
            return "ok"

        result = await _tool(world, body, user_id=None).ainvoke({}, config=CONFIG)

        assert result == "ok"
        assert world.store.audit == []

    @pytest.mark.asyncio
    async def test_ainvoke_still_returns_result_when_audit_insert_fails(self) -> None:
        world = build_world()

        def broken(_entry: Any) -> None:
            raise RuntimeError("db down")

        world.store.record_audit = broken  # type: ignore[method-assign]

        async def body(_arguments: dict[str, Any]) -> str:
            return "fine"

        assert await _tool(world, body).ainvoke({}, config=CONFIG) == "fine"

    @pytest.mark.asyncio
    async def test_ainvoke_leaves_agent_ref_empty_when_thread_id_is_missing(
        self,
    ) -> None:
        world = build_world()

        async def body(_arguments: dict[str, Any]) -> str:
            return "ok"

        await _tool(world, body).ainvoke({}, config={})

        assert world.store.audit[0].agent_ref is None

    def test_make_connector_tool_carries_write_flag_and_names_when_built(self) -> None:
        world = build_world()

        async def body(_arguments: dict[str, Any]) -> str:
            return ""

        tool = make_connector_tool(
            name="jira__create_issue",
            description="d",
            args_schema={"type": "object"},
            identity=_identity(),
            body=body,
            audit=world.services.audit,
            write_capable=True,
            source_name="create_issue",
        )

        assert tool.name == "jira__create_issue"
        assert tool.metadata == {
            "connector": "jira",
            "write_capable": True,
            "source_name": "create_issue",
        }
        assert tool.handle_tool_error is True

    @pytest.mark.asyncio
    async def test_ainvoke_never_logs_arguments_when_audit_logs(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        world = build_world()

        async def body(_arguments: dict[str, Any]) -> str:
            return "the secret result"

        with caplog.at_level("DEBUG"):
            await _tool(world, body).ainvoke(
                {"q": "the secret argument"}, config=CONFIG
            )

        assert "the secret argument" not in caplog.text
        assert "the secret result" not in caplog.text


class TestMakeStubTool:
    @pytest.mark.asyncio
    async def test_ainvoke_returns_fixed_envelope_and_audits_error_when_stub_called(
        self,
    ) -> None:
        world = build_world()
        stub = make_stub_tool(
            name="github__list_issues",
            description="stub",
            identity=ToolIdentity("github", "GitHub", USER, "run-1"),
            audit=world.services.audit,
            code=ToolErrorCode.CONNECTION_MISSING,
            message="GitHub connection missing, reconnect in Connectors",
        )

        result = await stub.ainvoke({"anything": 1}, config=CONFIG)

        error = json.loads(result)["error"]
        assert error["code"] == "connection_missing"
        assert error["message"] == "GitHub connection missing, reconnect in Connectors"
        assert world.store.audit[0].outcome == "error"
        assert stub.metadata is not None and stub.metadata["write_capable"] is True


class TestToToolError:
    def test_to_tool_error_maps_status_codes_when_http_status_error(self) -> None:
        identity = _identity()
        cases = {
            401: ToolErrorCode.CONNECTION_EXPIRED,
            403: ToolErrorCode.PERMISSION_DENIED,
            404: ToolErrorCode.NOT_FOUND,
            429: ToolErrorCode.RATE_LIMITED,
            500: ToolErrorCode.PROVIDER_UNAVAILABLE,
            503: ToolErrorCode.PROVIDER_UNAVAILABLE,
            400: ToolErrorCode.PROVIDER_ERROR,
            422: ToolErrorCode.PROVIDER_ERROR,
        }

        for status, expected in cases.items():
            code, _message = to_tool_error(_status_error(status), identity, "jira__x")
            assert code is expected, status

    def test_to_tool_error_reports_scope_when_403_has_insufficient_scope_challenge(
        self,
    ) -> None:
        exc = _status_error(
            403, {"www-authenticate": 'Bearer error="insufficient_scope"'}
        )

        code, message = to_tool_error(exc, _identity(), "jira__x")

        assert code is ToolErrorCode.INSUFFICIENT_SCOPE
        assert "Reconnect in Connectors" in message

    def test_to_tool_error_includes_wait_when_429_has_retry_after(self) -> None:
        _code, message = to_tool_error(
            _status_error(429, {"retry-after": "30"}), _identity(), "jira__x"
        )

        assert message == "Jira rate limit reached; try again in 30 seconds"

    def test_to_tool_error_maps_to_provider_unavailable_when_transport_error(
        self,
    ) -> None:
        for exc in (httpx.ReadTimeout("t"), httpx.ConnectError("c")):
            code, _ = to_tool_error(exc, _identity(), "jira__x")
            assert code is ToolErrorCode.PROVIDER_UNAVAILABLE

    def test_to_tool_error_maps_to_provider_error_when_mcp_tool_exception(self) -> None:
        code, message = to_tool_error(
            ToolException("repo   not\nfound"), _identity(), "jira__x"
        )

        assert code is ToolErrorCode.PROVIDER_ERROR
        assert message == "Jira reported an error: repo not found"

    def test_to_tool_error_unwraps_connector_error_when_inside_exception_group(
        self,
    ) -> None:
        inner = ConnectorError(
            ToolErrorCode.CONNECTION_EXPIRED, "expired", connector="github"
        )
        group = BaseExceptionGroup("tg", [RuntimeError("noise"), inner])

        code, message = to_tool_error(group, _identity(), "github__x")

        assert code is ToolErrorCode.CONNECTION_EXPIRED
        assert message == "expired"

    def test_to_tool_error_cuts_message_when_provider_text_is_long(self) -> None:
        _code, message = to_tool_error(
            ToolException("z" * 5000), _identity(), "jira__x"
        )

        assert len(message) < 400


class TestHelpers:
    def test_parse_retry_after_clamps_and_rejects_when_value_odd(self) -> None:
        assert parse_retry_after(None) is None
        assert parse_retry_after("abc") is None
        assert parse_retry_after("0") == 1
        assert parse_retry_after("5000") == 300
        assert parse_retry_after(" 12 ") == 12

    def test_shape_result_keeps_text_when_within_limit(self) -> None:
        assert shape_result("short") == "short"
        assert len(shape_result("y" * MAX_RESULT_CHARS)) == MAX_RESULT_CHARS

    def test_validate_arguments_raises_invalid_arguments_without_input_when_invalid(
        self,
    ) -> None:
        class Model(BaseModel):
            issue_key: str = Field(pattern=r"^[A-Z]+-1$")

        with pytest.raises(ConnectorError) as raised:
            validate_arguments(Model, {"issue_key": "hunter2-token"}, "jira")

        assert raised.value.code is ToolErrorCode.INVALID_ARGUMENTS
        assert "issue_key" in str(raised.value)
        assert "hunter2-token" not in str(raised.value)
