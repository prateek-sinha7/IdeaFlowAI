"""Connector tools bound by the engine for one run, against the in-process GitHub MCP stub.

The engine, the factory and ``ConnectorRunToolBinder`` run unmodified. The model is a
``FakeChatModel`` (``tests/fakes/scripted_chat_model.py``) that asks for
``github__list_issues`` on its first call and answers on its second. The GitHub server
is ``FakeGitHubMcpServer`` (no sockets). Connections and audit rows live in SQLite.

The run uses the offline seam from ``tests/agents/_scripted_model.py``, so the engine's
own persistence never reaches a real database.
"""

from __future__ import annotations

import dataclasses
from collections.abc import AsyncIterator
from typing import Any

import pytest
from langchain_core.messages import ToolMessage

import agents.execution_engine.engine as engine_mod
import agents.factory as factory_mod
from agents.execution_engine.engine import ExecutionEngine, compile_for_run
from agents.registry import get_pipeline_agents
from app.connectors.binder import ConnectorRunToolBinder
from app.connectors.tools.remote_mcp import RemoteMcpBinder, RemoteMcpLister
from app.core.config import settings as live_settings
from app.models.connector import AUDIT_TOOL_CALL, AUDIT_TOOLS_BOUND
from tests.agents._scripted_model import _RUNS_ROOT, offline_db_seam
from tests.fakes.connector_sqlite import SqliteConnectors, sqlite_connectors
from tests.fakes.scripted_chat_model import (
    FakeChatModel,
    ModelTurn,
    ScriptedToolCall,
    ScriptedUsage,
)
from tests.fakes.streamable_http_mcp import FakeGitHubMcpServer

_PIPELINE = "user_stories"
_FIRST_AGENT = "domain-analyst"
_SECOND_AGENT = "epic-architect"
_GITHUB_TOOL = "github__list_issues"
_USER = "user-binder-external"
_QUERY = "open"
_USAGE = ScriptedUsage(input_tokens=10, output_tokens=5)


def _granted_plan() -> Any:
    """The user_stories plan where only the first step grants ``github__list_issues``.

    Built with ``dataclasses.replace`` so the cached file plan is never mutated. The
    clarifier is off because the harness has no user to answer questions.
    """
    base = compile_for_run(_PIPELINE)
    assert base.steps[0].agent_id == _FIRST_AGENT, "fixture assumption"
    first = base.steps[0]
    granted = dataclasses.replace(
        first, tools=dataclasses.replace(first.tools, connectors=[_GITHUB_TOOL])
    )
    return dataclasses.replace(
        base,
        steps=[granted, *base.steps[1:]],
        clarify=dataclasses.replace(base.clarify, mode="off"),
        admits_connector_grants=True,
    )


def _default_model() -> FakeChatModel:
    """Answers once and then repeats, so an agent the test does not script never calls out."""
    return FakeChatModel(turns=(ModelTurn(text=("done",)),), repeat_last=True)


def _first_agent_model() -> FakeChatModel:
    return FakeChatModel(
        turns=(
            ModelTurn(
                tool_calls=(
                    ScriptedToolCall(name=_GITHUB_TOOL, args={"query": _QUERY}),
                ),
                usage=_USAGE,
            ),
            ModelTurn(text=("done",), usage=_USAGE),
        )
    )


async def _no_review_gate(*_args: Any, **_kwargs: Any) -> AsyncIterator[dict]:
    for _ in ():
        yield {}


def _binder(
    env: SqliteConnectors, server: FakeGitHubMcpServer
) -> ConnectorRunToolBinder:
    """The app's binder, wired to the SQLite services and the stub server's client."""
    services = env.services
    runtime = env.tool_runtime(server.client_factory)
    remote = RemoteMcpBinder(
        runtime=runtime,
        lister=RemoteMcpLister(
            registry=services.registry,
            tokens=services.tokens,
            cache=services.tool_cache,
            httpx_client_factory=server.client_factory,
        ),
        httpx_client_factory=server.client_factory,
    )
    return ConnectorRunToolBinder(runtime=runtime, remote=remote)


async def _run_user_stories(
    binder: ConnectorRunToolBinder, run_id: str
) -> dict[str, FakeChatModel]:
    """Run the first agent through ``execute()`` offline; return each agent's model.

    The engine's state machine is process-wide and keyed by run id, so each test passes
    its own id.

    ``create_runner`` is wrapped so every agent gets a ``FakeChatModel``. The real factory
    still builds the runner, so the connector tools reach the model through the
    production path.
    """
    spec = next(s for s in get_pipeline_agents(_PIPELINE) if s.id == _FIRST_AGENT)
    live_settings.RUNS_ROOT = _RUNS_ROOT
    models: dict[str, FakeChatModel] = {}
    original = factory_mod.create_runner

    def _with_scripted_model(agent_id: str, ctx: Any, **kwargs: Any) -> Any:
        if agent_id not in models:
            models[agent_id] = (
                _first_agent_model() if agent_id == _FIRST_AGENT else _default_model()
            )
        ctx.model = models[agent_id]
        return original(agent_id, ctx, **kwargs)

    factory_mod.create_runner = _with_scripted_model
    engine_mod.create_runner = _with_scripted_model
    engine = ExecutionEngine()

    async def _planner(user_message: str, *_args: Any, **_kwargs: Any) -> Any:
        return engine._default_planning_context(user_message), "PROCEED"

    async def _store(*_args: Any, **_kwargs: Any) -> str:
        return "artifact-id"

    engine._run_planner = _planner  # type: ignore[assignment]
    engine._store.store = _store  # type: ignore[assignment]
    engine._run_review_gate = _no_review_gate  # type: ignore[assignment]
    try:
        with offline_db_seam():
            async for _event in engine.execute(
                agents=[spec],
                user_message="Build me a thing for managing tasks.",
                pipeline_run_id=run_id,
                pipeline_type=_PIPELINE,
                user_id=_USER,
                od_context=None,
                gate_agent_ids=[],
                compiled_override=_granted_plan(),
                run_tool_binder=binder,
            ):
                pass
    finally:
        factory_mod.create_runner = original
        engine_mod.create_runner = original
    return models


async def _scenario(
    run_id: str,
) -> tuple[dict[str, FakeChatModel], list[Any], FakeGitHubMcpServer]:
    """Run once against a connected GitHub account; return the models, audit rows and server."""
    async with FakeGitHubMcpServer() as server:
        server.add_read_tool("list_issues", "List issues")
        with sqlite_connectors(
            [_USER], mcp_http_client_factory=server.client_factory
        ) as env:
            env.connect(_USER, "github")
            models = await _run_user_stories(_binder(env, server), run_id)
            rows = env.audit_rows()
    return models, rows, server


class TestAgentBindsConnectorTools:
    @pytest.mark.asyncio
    async def test_execute_returns_tool_result_to_model_when_step_grants_github_list_issues(
        self,
    ) -> None:
        models, _rows, server = await _scenario("run-binder-reply")

        first = models[_FIRST_AGENT]
        assert _GITHUB_TOOL in first.bound_tool_names
        assert ("list_issues", {"query": _QUERY}) in server.calls
        assert first.call_count == 2
        results = [
            message.content
            for message in first.calls[1]
            if isinstance(message, ToolMessage)
        ]
        assert any("list_issues:open" in str(content) for content in results)

    @pytest.mark.asyncio
    async def test_execute_writes_tools_bound_and_tool_call_audit_rows_when_step_grants_tool(
        self,
    ) -> None:
        run_id = "run-binder-audit"
        _models, rows, _server = await _scenario(run_id)

        bound = [r for r in rows if r.action == AUDIT_TOOLS_BOUND]
        calls = [r for r in rows if r.action == AUDIT_TOOL_CALL]
        assert [(r.connector_key, r.outcome, r.run_id) for r in bound] == [
            ("github", "ok", run_id)
        ]
        (call,) = calls
        assert (call.user_id, call.connector_key, call.tool_name) == (
            _USER,
            "github",
            _GITHUB_TOOL,
        )
        assert (call.outcome, call.run_id, call.agent_ref) == (
            "ok",
            run_id,
            _FIRST_AGENT,
        )

    @pytest.mark.asyncio
    async def test_execute_binds_no_github_tool_for_second_step_when_its_grant_is_empty(
        self,
    ) -> None:
        models, _rows, server = await _scenario("run-binder-second")

        second = models[_SECOND_AGENT]
        assert _GITHUB_TOOL not in second.bound_tool_names
        assert server.calls == [
            ("list_issues", {"query": _QUERY})
        ], "only the granting step may reach the GitHub server"
