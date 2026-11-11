"""Connector tools never reach the runners that must not have them.

Concierge, handoff, the workflow builder and the chat runner are kept free of connector
tools. This file checks three things:

* the four surface modules never import ``app.connectors`` (AST scan, nested imports
  included);
* a step with no connector grant binds nothing, and a step binds only the tools its own
  grant names;
* a launch hands the binder the run's own verified user id, for two users in turn.

Pure data and a stubbed engine: no database, no network.
"""

from __future__ import annotations

import ast
import asyncio
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import app.api.run_commands as run_commands
from agents.execution_engine.run_tools import RunToolRequest
from agents.workflows import permission_caps
from agents.workflows.plan import ToolPermissions

_BACKEND = Path(__file__).resolve().parents[2]
_SURFACE_PATHS = (
    "app/agents/chat/concierge.py",
    "app/agents/handoff/coder.py",
    "app/agents/workflow_builder/agent.py",
    "app/agents/chat_runner.py",
)
_JIRA = "jira__get_issue"
_GITHUB = "github__list_issues"


def _imported_modules(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


@pytest.mark.parametrize("relative", _SURFACE_PATHS)
def test_surface_module_does_not_import_connectors_when_scanned(relative: str) -> None:
    path = _BACKEND / relative
    assert path.is_file(), f"fixture assumption: {relative} exists"

    leaked = {
        module
        for module in _imported_modules(path)
        if module == "app.connectors" or module.startswith("app.connectors.")
    }

    assert leaked == set()


def test_bound_connector_tools_returns_empty_when_no_step_tools() -> None:
    pool = {_GITHUB: object()}

    assert permission_caps.bound_connector_tools(None, pool) == []


def test_bound_connector_tools_returns_only_granted_tool_when_steps_differ() -> None:
    jira_tool = object()
    github_tool = object()
    pool = {_JIRA: jira_tool, _GITHUB: github_tool}

    bound = permission_caps.bound_connector_tools(
        ToolPermissions(connectors=[_JIRA]), pool
    )

    assert bound == [jira_tool]


class _LaunchUser:
    """The verified caller of a launch: only the fields the launch driver reads."""

    def __init__(self, user_id: str) -> None:
        self.id = user_id
        self.tier = "enterprise"


class _RecordingBinder:
    """Stands in for the app's binder: keeps every request it is handed."""

    def __init__(self) -> None:
        self.requests: list[RunToolRequest] = []

    async def __call__(self, request: RunToolRequest) -> Mapping[str, Any]:
        self.requests.append(request)
        return {}


class _DriverEngine:
    """Stands in for ``ExecutionEngine.execute``.

    It asks the binder for one connector tool with the ``user_id`` it was given, the way
    the engine does for a run. The engine's own request construction is covered by the
    engine seam tests; this file covers what the launch driver passes in.
    """

    def __init__(self, binder: _RecordingBinder) -> None:
        self._binder = binder
        self.kwargs: dict[str, Any] = {}

    async def execute(self, **kwargs: Any):
        self.kwargs = kwargs
        await self._binder(
            RunToolRequest(
                run_id=kwargs["pipeline_run_id"],
                user_id=kwargs["user_id"],
                tool_names=frozenset({_GITHUB}),
            )
        )
        yield {"type": "pipeline_complete", "data": {"status": "completed"}}


async def _drive_launch(user: _LaunchUser, run_id: str) -> None:
    """Run the launch driver with no workflow row, so it writes nothing to a database."""
    await run_commands._drive_launch_to_queue(
        workflow_run_id=None,
        pipeline_run_id=run_id,
        agents=[],
        content="go",
        pipeline_type="custom",
        cancel_event=asyncio.Event(),
        user=user,
        attached_skills=[],
        attached_hooks=[],
        od_context=None,
        validated_images=[],
        gate_agent_ids=None,
        parent_run_id=None,
        model_overrides={},
        selections=None,
        event_queue=asyncio.Queue(),
    )


@pytest.mark.asyncio
async def test_binder_request_carries_only_run_owner_user_id_when_two_users_launch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binder = _RecordingBinder()
    engine = _DriverEngine(binder)
    monkeypatch.setattr(
        "agents.execution_engine.engine.get_execution_engine", lambda: engine
    )
    monkeypatch.setattr(
        "app.connectors.services.get_connector_services",
        lambda: SimpleNamespace(binder=binder),
    )

    await _drive_launch(_LaunchUser("user-a"), "run-a")
    assert engine.kwargs["user_id"] == "user-a"
    await _drive_launch(_LaunchUser("user-b"), "run-b")
    assert engine.kwargs["user_id"] == "user-b"

    assert [(r.run_id, r.user_id) for r in binder.requests] == [
        ("run-a", "user-a"),
        ("run-b", "user-b"),
    ]
