"""Connected-app grants never reach predefined workflows (design 5.5, layers 1-4).

Adversarial view of the isolation: a ``file``/``builtin`` manifest, an override
row, a flat selection map, an unsaved selections overlay and a Path B step each
try to carry ``tools.connectors``. None may end up as a grant on a plan the
engine would hand to the connector binder. The runners that must never see
connector tools (concierge, handoff, builder, chat runner) are checked at the
seam and by an import scan.

Pure data: no database, no network. The one route test stubs the session so a
refused launch cannot write a row.
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

import pytest
import yaml
from fastapi import HTTPException

from agents.capabilities.registry import CapabilityRegistry, discover
from agents.execution_engine.engine import ExecutionEngine, compile_for_run
from agents.execution_engine.overrides import (
    compile_override_steps,
    compile_with_baseline,
    merge_override_steps,
)
from agents.workflows import permission_caps
from agents.workflows.compiler import (
    CompilerError,
    ConnectorGrantsNotAllowed,
    WorkflowCompiler,
)
from agents.workflows.manifest import WorkflowManifest
from agents.workflows.plan import ToolPermissions
from app.api.run_engine import (
    CONNECTOR_GRANTS_NOT_ALLOWED_MESSAGE,
    _reject_connector_selections,
)
from app.api.user_workflows import (
    _compile_check_manifest,
    _compile_check_override_steps,
    _compile_selections_trust_user,
)

_JIRA = "jira__get_issue"
_GITHUB = "github__list_issues"
_CODE = "connector_grants_not_allowed"
_BACKEND = Path(__file__).resolve().parents[2]
_PREDEFINED_PIPELINES = ("custom", "prototype", "prototype_v2", "ppt")


@pytest.fixture(autouse=True)
def _discovered() -> None:
    discover()


def _manifest(*steps: dict) -> WorkflowManifest:
    return WorkflowManifest(
        id="isolation-demo",
        steps=list(steps),
        deliverable={},
        planner="run",
        clarify={"mode": "auto", "defaults": []},
        context_providers=[],
        seed_files={},
        version=1,
    )


def _raw_step(agent: str = "demo-agent", **tools: object) -> dict:
    step: dict = {"agent": agent, "strategy": "single_shot"}
    if tools:
        step["tools"] = dict(tools)
    return step


# ---------------------------------------------------------------------------
# Layer 1: compile time
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("trust", ["file", "builtin", "", "root", "DB", "USER"])
def test_compile_raises_when_predefined_or_unknown_trust_names_connectors(
    trust: str,
) -> None:
    manifest = _manifest(_raw_step(connectors=[_JIRA]))

    with pytest.raises(CompilerError):
        WorkflowCompiler().compile(manifest, CapabilityRegistry(), trust=trust)


@pytest.mark.parametrize("trust", ["file", "builtin"])
def test_compile_names_the_offending_step_when_predefined_manifest_asks(
    trust: str,
) -> None:
    manifest = _manifest(
        _raw_step("ok-agent"), _raw_step("bad-agent", connectors=[_GITHUB])
    )

    with pytest.raises(ConnectorGrantsNotAllowed) as excinfo:
        WorkflowCompiler().compile(manifest, CapabilityRegistry(), trust=trust)

    assert "bad-agent" in str(excinfo.value)
    assert "ok-agent" not in str(excinfo.value)


@pytest.mark.parametrize("trust", ["file", "builtin"])
def test_apply_cap_drops_grant_when_predefined_trust_bypasses_the_compiler(
    trust: str,
) -> None:
    effective = permission_caps.apply_cap(ToolPermissions(connectors=[_JIRA]), trust)

    assert effective.connectors == []


@pytest.mark.parametrize("pipeline", _PREDEFINED_PIPELINES)
def test_compile_for_run_never_admits_grants_when_pipeline_is_file_backed(
    pipeline: str,
) -> None:
    plan = compile_for_run(pipeline)

    assert plan.admits_connector_grants is False
    assert all(step.tools.connectors == [] for step in plan.steps)
    assert permission_caps.connector_tool_grants(plan) == frozenset()


def test_shipped_workflow_yaml_declares_no_connector_grant_when_scanned() -> None:
    manifests = sorted((_BACKEND / "agents" / "workflows").glob("*/workflow.yaml"))
    assert manifests, "fixture assumption: shipped manifests exist"

    offenders: list[str] = []
    for path in manifests:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for step in data.get("steps") or []:
            tools = step.get("tools") if isinstance(step, dict) else None
            if isinstance(tools, dict) and "connectors" in tools:
                offenders.append(f"{path.parent.name}:{step.get('agent')}")

    assert offenders == []


# ---------------------------------------------------------------------------
# Layer 2: override rows and the plan flag
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("trust", ["user", "db", "file", "builtin"])
def test_compile_with_baseline_raises_when_override_row_names_connectors(
    trust: str,
) -> None:
    manifest = _manifest(_raw_step(connectors=[_JIRA]))

    with pytest.raises(CompilerError):
        compile_with_baseline(
            manifest, CapabilityRegistry(), trust=trust, overrides="custom"
        )


def test_compile_override_steps_raises_when_a_row_step_names_connectors() -> None:
    with pytest.raises(ConnectorGrantsNotAllowed):
        compile_override_steps(
            "custom", [_raw_step(connectors=[_JIRA])], CapabilityRegistry()
        )


def test_merge_override_steps_keeps_predefined_plan_when_row_names_connectors() -> None:
    base = compile_for_run("custom")

    merged = merge_override_steps(
        base, [_raw_step(connectors=[_JIRA])], CapabilityRegistry()
    )

    assert merged.admits_connector_grants is False
    assert permission_caps.connector_tool_grants(merged) == frozenset()


def test_merge_override_steps_never_admits_when_override_row_is_clean() -> None:
    merged = merge_override_steps(
        compile_for_run("custom"), [_raw_step()], CapabilityRegistry()
    )

    assert merged.admits_connector_grants is False


@pytest.mark.parametrize("trust", ["user", "db"])
def test_compile_with_baseline_clears_flag_when_override_compiles_at_user_authored_trust(
    trust: str,
) -> None:
    plan = compile_with_baseline(
        _manifest(_raw_step()), CapabilityRegistry(), trust=trust, overrides="custom"
    )

    assert plan.admits_connector_grants is False


def test_connector_tool_grants_is_empty_when_plan_carries_names_but_does_not_admit() -> (
    None
):
    admitting = dataclasses.replace(
        compile_for_run("custom"), admits_connector_grants=True
    )
    step = dataclasses.replace(
        admitting.steps[0], tools=ToolPermissions(connectors=[_JIRA, _GITHUB])
    )
    forged = dataclasses.replace(
        admitting, steps=[step, *admitting.steps[1:]], admits_connector_grants=False
    )

    assert permission_caps.connector_tool_grants(forged) == frozenset()


# ---------------------------------------------------------------------------
# Layer 3: engine selections overlay
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pipeline", _PREDEFINED_PIPELINES)
def test_apply_selections_adds_no_grant_when_base_plan_is_predefined(
    pipeline: str,
) -> None:
    base = compile_for_run(pipeline)
    agent_ids = [step.agent_id for step in base.steps]
    selections = {a: {"tools": {"connectors": [_JIRA, _GITHUB]}} for a in agent_ids}

    plan, user_steps = ExecutionEngine._apply_selections(
        base, selections, run_agent_ids=[*agent_ids, "absent-composed-agent"]
    )

    assert plan.admits_connector_grants is False
    assert all(step.tools.connectors == [] for step in plan.steps)
    assert all(step.tools.connectors == [] for step in user_steps.values())
    assert permission_caps.connector_tool_grants(plan) == frozenset()


def test_apply_selections_adds_no_grant_when_selection_targets_an_absent_agent() -> (
    None
):
    base = compile_for_run("custom")

    plan, user_steps = ExecutionEngine._apply_selections(
        base,
        {"absent-composed-agent": {"tools": {"connectors": [_JIRA]}}},
        run_agent_ids=["absent-composed-agent"],
    )

    assert user_steps, "fixture assumption: Path B synthesises a step"
    assert all(step.tools.connectors == [] for step in user_steps.values())
    assert permission_caps.connector_tool_grants(plan) == frozenset()


def test_overlay_tool_slots_drops_connectors_when_plan_does_not_admit() -> None:
    named = {"connectors": [_JIRA], "write_files": True}

    assert permission_caps.overlay_tool_slots(named, admits=False) == {
        "write_files": True
    }


def test_apply_selections_leaves_cached_plan_untouched_when_overlay_is_refused() -> (
    None
):
    base = compile_for_run("custom")
    agent_id = base.steps[0].agent_id

    ExecutionEngine._apply_selections(
        base, {agent_id: {"tools": {"connectors": [_JIRA]}}}, run_agent_ids=[agent_id]
    )

    assert base.admits_connector_grants is False
    assert all(step.tools.connectors == [] for step in base.steps)


# ---------------------------------------------------------------------------
# Layer 4: ingress and save paths
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "selections",
    [
        {"a": {"tools": {"connectors": [_JIRA]}}},
        {"a": {"tools": {"connectors": [_JIRA]}}, "b": {}},
        {"a": {}, "b": {"tools": {"connectors": [_GITHUB]}}},
        {"_wizard": {"brief": "x"}, "b": {"tools": {"connectors": ["x"]}}},
    ],
)
def test_reject_connector_selections_returns_message_when_any_step_names_connectors(
    selections: dict,
) -> None:
    assert (
        _reject_connector_selections(selections) == CONNECTOR_GRANTS_NOT_ALLOWED_MESSAGE
    )


@pytest.mark.parametrize(
    "selections",
    [None, {}, [], "text", 7, {"a": {"tools": {"connectors": []}}}, {"a": None}],
)
def test_reject_connector_selections_returns_none_when_nothing_is_granted(
    selections: object,
) -> None:
    assert _reject_connector_selections(selections) is None


def _assert_refused(exc: HTTPException) -> None:
    assert exc.status_code == 422
    assert isinstance(exc.detail, dict)
    assert exc.detail["code"] == _CODE
    assert exc.detail["recoverable"] is False


def test_flat_selection_save_returns_422_when_a_step_names_connectors() -> None:
    with pytest.raises(HTTPException) as excinfo:
        _compile_selections_trust_user(
            "custom",
            ["market-research-agent", "swot-analyst"],
            {"swot-analyst": {"tools": {"connectors": [_JIRA]}}},
        )

    _assert_refused(excinfo.value)


@pytest.mark.parametrize("trust", ["file", "builtin"])
def test_manifest_save_returns_422_when_predefined_trust_names_connectors(
    trust: str,
) -> None:
    with pytest.raises(HTTPException) as excinfo:
        _compile_check_manifest(
            {"steps": [_raw_step(connectors=[_JIRA])]}, "workflow:test", trust
        )

    _assert_refused(excinfo.value)


def test_override_row_save_returns_422_when_a_step_names_connectors() -> None:
    with pytest.raises(HTTPException) as excinfo:
        _compile_check_override_steps(
            [_raw_step(connectors=[_JIRA])], "custom", "override:test"
        )

    _assert_refused(excinfo.value)


class _LaunchUser:
    id = "owner"
    tier = "enterprise"


class _WriteRefusingSession:
    """Any write before the grant check is a failure."""

    writes = 0

    def close(self) -> None:
        return None

    def add(self, *_args: object, **_kwargs: object) -> None:
        type(self).writes += 1
        raise AssertionError("a refused connector launch must not write a row")

    commit = flush = add


@pytest.mark.parametrize(
    "selections",
    [
        {"market-research-agent": {"tools": {"connectors": [_JIRA]}}},
        {
            "market-research-agent": {"tools": {"connectors": []}},
            "swot-analyst": {"tools": {"connectors": [_GITHUB]}},
        },
    ],
)
def test_launch_run_returns_422_and_writes_no_row_when_file_pipeline_names_connectors(
    monkeypatch: pytest.MonkeyPatch, selections: dict
) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import run_commands
    from app.core.dependencies import get_current_principal
    from tests.fakes.principal import principal_for

    _WriteRefusingSession.writes = 0
    monkeypatch.setattr(
        run_commands, "_get_db", lambda: _WriteRefusingSession(), raising=False
    )
    monkeypatch.setattr(
        "app.api._workflow_override.resolve_override", lambda *_a, **_k: None
    )
    user = _LaunchUser()
    app = FastAPI()
    app.include_router(run_commands.router)
    app.dependency_overrides[get_current_principal] = lambda: (
        user,
        principal_for(user),
    )

    response = TestClient(app).post(
        "/api/runs",
        json={
            "message": "go",
            "pipeline_type": "custom",
            "agent_ids": ["market-research-agent", "swot-analyst"],
            "selections": selections,
        },
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == _CODE
    assert _WriteRefusingSession.writes == 0


# ---------------------------------------------------------------------------
# Binder seam and runners that never get connector tools
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pool", [None, {}, {_JIRA: object(), _GITHUB: object()}])
def test_bound_connector_tools_returns_nothing_when_no_step_is_bound(
    pool: dict | None,
) -> None:
    # Chat runner, revision agents and direct create_runner calls carry no step.
    assert permission_caps.bound_connector_tools(None, pool) == []


def test_bound_connector_tools_returns_nothing_when_step_granted_none() -> None:
    pool = {_JIRA: object()}

    assert permission_caps.bound_connector_tools(ToolPermissions(), pool) == []


def test_bound_connector_tools_skips_tool_granted_only_to_another_step() -> None:
    pool = {_JIRA: object(), _GITHUB: object()}

    bound = permission_caps.bound_connector_tools(
        ToolPermissions(connectors=[_GITHUB]), pool
    )

    assert bound == [pool[_GITHUB]]


_RUNNER_PATHS = (
    "app/agents/chat/concierge.py",
    "app/agents/chat_runner.py",
    "app/agents/deep_agent_runner.py",
    "app/api/handoff.py",
    "app/api/websocket_handoff.py",
    "app/services/handoff_pipeline.py",
    "app/services/handoff_github.py",
)


def _imported_modules(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


@pytest.mark.parametrize("relative", _RUNNER_PATHS)
def test_runner_module_does_not_import_connectors_when_scanned(relative: str) -> None:
    path = _BACKEND / relative
    assert path.is_file(), f"fixture assumption: {relative} exists"

    leaked = {
        m
        for m in _imported_modules(path)
        if m == "app.connectors" or m.startswith("app.connectors.")
    }

    assert leaked == set()


def test_builder_modules_do_not_import_connectors_when_scanned() -> None:
    root = _BACKEND / "app" / "agents" / "workflow_builder"
    files = sorted(root.rglob("*.py"))
    assert files, "fixture assumption: builder modules exist"

    leaked = {
        f"{path.name}:{module}"
        for path in files
        for module in _imported_modules(path)
        if module == "app.connectors" or module.startswith("app.connectors.")
    }

    assert leaked == set()
