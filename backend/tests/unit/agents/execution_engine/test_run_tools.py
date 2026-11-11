"""Unit tests for the per-run connector tool port (connectors phase 3, step 8a).

``agents/execution_engine/run_tools.py`` holds stdlib-only data (``RunToolRequest``), the
bind timeout constant and the ``RunToolBinder`` protocol. These tests pin the request shape,
the timeout value and the binder call contract. Offline and unmarked: no DB, network, or
filesystem access.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from typing import Any

import pytest

from agents.execution_engine import run_tools
from agents.execution_engine.run_tools import (
    RUN_TOOL_BIND_TIMEOUT_SECONDS,
    RunToolBinder,
    RunToolRequest,
)


def test_run_tool_request_holds_identity_and_grant_when_constructed() -> None:
    request = RunToolRequest(
        run_id="run-1",
        user_id="user-1",
        tool_names=frozenset({"jira__get_issue"}),
    )

    assert request.run_id == "run-1"
    assert request.user_id == "user-1"
    assert request.tool_names == frozenset({"jira__get_issue"})


def test_run_tool_request_accepts_none_user_id_when_run_is_anonymous() -> None:
    request = RunToolRequest(run_id="run-2", user_id=None, tool_names=frozenset())

    assert request.user_id is None
    assert request.tool_names == frozenset()


def test_run_tool_request_rejects_reassignment_when_frozen() -> None:
    request = RunToolRequest(run_id="run-1", user_id="user-1", tool_names=frozenset())

    with pytest.raises(dataclasses.FrozenInstanceError):
        request.run_id = "other-run"  # type: ignore[misc]


def test_run_tool_request_compares_and_hashes_equal_when_fields_match() -> None:
    first = RunToolRequest(
        run_id="run-1", user_id="user-1", tool_names=frozenset({"x__y"})
    )
    second = RunToolRequest(
        run_id="run-1", user_id="user-1", tool_names=frozenset({"x__y"})
    )

    assert first == second
    assert hash(first) == hash(second)


def test_run_tool_bind_timeout_is_thirty_seconds_when_read() -> None:
    assert RUN_TOOL_BIND_TIMEOUT_SECONDS == 30.0


async def test_run_tool_binder_returns_mapping_keyed_by_name_when_called() -> None:
    received: list[RunToolRequest] = []

    async def binder(request: RunToolRequest) -> Mapping[str, Any]:
        received.append(request)
        return {name: object() for name in request.tool_names}

    bind: RunToolBinder = binder
    request = RunToolRequest(
        run_id="run-1",
        user_id="user-1",
        tool_names=frozenset({"github__list_issues"}),
    )

    result = await bind(request)

    assert received == [request]
    assert set(result) == {"github__list_issues"}


async def test_run_tool_binder_returns_empty_mapping_when_no_names_requested() -> None:
    async def binder(request: RunToolRequest) -> Mapping[str, Any]:
        return {name: object() for name in request.tool_names}

    bind: RunToolBinder = binder
    result = await bind(
        RunToolRequest(run_id="run-1", user_id=None, tool_names=frozenset())
    )

    assert dict(result) == {}


def test_run_tools_module_references_no_app_module_when_inspected() -> None:
    referenced_modules = {
        getattr(value, "__module__", "") for value in vars(run_tools).values()
    }

    assert not any(str(module).startswith("app") for module in referenced_modules)
