"""``ConnectorAudit``: rows and log lines without secrets, never raising."""

from __future__ import annotations

import asyncio
import json
import logging
import time

import pytest

from app.connectors.audit import ConnectorAudit, agent_ref_from_config
from app.connectors.store import AuditEntry
from app.models.connector import AUDIT_TOOL_CALL, AUDIT_TOOLS_BOUND
from tests.fakes.connector_store import FakeConnectionStore


class TestAgentRefFromConfig:
    @pytest.mark.parametrize(
        ("thread_id", "expected"),
        [
            ("run-1:design-ingestor", "design-ingestor"),
            ("run-1:coder:retry2", "coder"),
            ("run-1:step:d1:3", "step"),
            ("run-1", None),
            ("run-1:bad agent!", None),
            ("run-1:" + "a" * 129, None),
        ],
    )
    def test_agent_ref_from_config_reads_second_segment_when_thread_id_has_one(
        self, thread_id: str, expected: str | None
    ) -> None:
        config = {"configurable": {"thread_id": thread_id}}

        assert agent_ref_from_config(config) == expected

    @pytest.mark.parametrize(
        "config",
        [None, {}, {"configurable": None}, {"configurable": {"thread_id": 7}}],
    )
    def test_agent_ref_from_config_returns_none_when_config_has_no_thread_id(
        self, config: dict | None
    ) -> None:
        assert agent_ref_from_config(config) is None


class TestRecordToolCall:
    @pytest.mark.asyncio
    async def test_record_tool_call_writes_row_without_payload_when_called(
        self,
    ) -> None:
        store = FakeConnectionStore()
        audit = ConnectorAudit(store)  # type: ignore[arg-type]

        await audit.record_tool_call(
            user_id="user-a",
            connector_key="jira",
            tool_name="jira__search_issues",
            outcome="ok",
            duration_ms=412,
            run_id="run-1",
            agent_ref="coder",
        )

        assert store.audit == [
            AuditEntry(
                user_id="user-a",
                connector_key="jira",
                action=AUDIT_TOOL_CALL,
                outcome="ok",
                error_code=None,
                tool_name="jira__search_issues",
                run_id="run-1",
                agent_ref="coder",
                duration_ms=412,
            )
        ]

    @pytest.mark.asyncio
    async def test_record_tool_call_logs_json_line_without_arguments_when_called(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        audit = ConnectorAudit(FakeConnectionStore())  # type: ignore[arg-type]

        with caplog.at_level(logging.INFO, logger="app.connectors.audit"):
            await audit.record_tool_call(
                user_id="user-a",
                connector_key="jira",
                tool_name="jira__search_issues",
                outcome="error",
                error_code="not_found",
                duration_ms=5,
                run_id="run-1",
            )

        payload = json.loads(caplog.records[-1].getMessage())
        assert payload == {
            "event": "connector.tool_call",
            "connector": "jira",
            "tool": "jira__search_issues",
            "outcome": "error",
            "error_code": "not_found",
            "duration_ms": 5,
            "run_id": "run-1",
        }

    @pytest.mark.asyncio
    async def test_record_tool_call_does_not_raise_when_insert_fails(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        class _Broken(FakeConnectionStore):
            def record_audit(self, entry: AuditEntry) -> None:
                raise RuntimeError("database is down")

        audit = ConnectorAudit(_Broken())  # type: ignore[arg-type]

        with caplog.at_level(logging.WARNING, logger="app.connectors.audit"):
            await audit.record_tool_call(
                user_id="u", connector_key="jira", tool_name="jira__x", outcome="ok"
            )

        assert any("insert failed" in r.getMessage() for r in caplog.records)
        assert "database is down" not in caplog.text

    @pytest.mark.asyncio
    async def test_record_tool_call_returns_within_bound_when_insert_is_slow(
        self,
    ) -> None:
        class _Slow(FakeConnectionStore):
            def record_audit(self, entry: AuditEntry) -> None:
                time.sleep(0.5)

        audit = ConnectorAudit(_Slow(), insert_timeout_seconds=0.05)  # type: ignore[arg-type]

        started = asyncio.get_running_loop().time()
        await audit.record_tool_call(
            user_id="u", connector_key="jira", tool_name="jira__x", outcome="ok"
        )

        assert asyncio.get_running_loop().time() - started < 0.4

    @pytest.mark.asyncio
    async def test_record_tool_call_clips_long_values_when_oversized(self) -> None:
        store = FakeConnectionStore()
        audit = ConnectorAudit(store)  # type: ignore[arg-type]

        await audit.record_tool_call(
            user_id="u",
            connector_key="jira",
            tool_name="t" * 500,
            outcome="error",
            error_code="e" * 500,
        )

        assert len(store.audit[0].tool_name or "") == 128
        assert len(store.audit[0].error_code or "") == 64


class TestRecordToolsBound:
    @pytest.mark.asyncio
    async def test_record_tools_bound_writes_row_when_called(self) -> None:
        store = FakeConnectionStore()
        audit = ConnectorAudit(store)  # type: ignore[arg-type]

        await audit.record_tools_bound(
            user_id="u",
            connector_key="github",
            outcome="error",
            error_code="connection_missing",
            run_id="run-1",
        )

        assert store.audit_actions() == [
            (AUDIT_TOOLS_BOUND, "error", "connection_missing")
        ]
        assert store.audit[0].run_id == "run-1"
