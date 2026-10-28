"""Unit coverage for saved-workflow state carried through the trigger port."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import agents.execution_engine.kernel_services as kernel_services
from agents.execution_engine.trigger_port import (
    ResolvedTriggeredWorkflow,
    TriggerLaunchPort,
)


def _services() -> kernel_services.KernelServices:
    services = object.__new__(kernel_services.KernelServices)
    services._pipeline_type = "source-workflow"
    services._ordered_agents = []
    return services


@pytest.mark.asyncio
async def test_run_trigger_workflow_forwards_saved_settings_when_target_is_flat(
    monkeypatch,
) -> None:
    resolved = ResolvedTriggeredWorkflow(
        pipeline_type="custom",
        agents=[SimpleNamespace(id="custom-agent")],
        model_overrides={"custom-agent": "model-1"},
        attached_skills=[{"name": "brand", "content": "Use the brand voice."}],
        attached_hooks=[{"name": "audit", "event": "after_agent"}],
    )
    captured: dict[str, object] = {}

    async def _launch_run(**kwargs):
        captured.update(kwargs)
        return {"run_id": "child-flat"}

    port = TriggerLaunchPort(
        resolve_saved_workflow=lambda *_: resolved,
        launch_run=_launch_run,
    )
    monkeypatch.setattr(kernel_services, "get_trigger_launch_port", lambda: port)
    ectx = SimpleNamespace(
        run_id="parent",
        owner_id="owner-1",
        workspace_id="workspace-1",
        trigger_depth=2,
    )

    result = await _services().run_trigger_workflow(
        None, ectx, workflow_ref="saved-flat", content="continue"
    )

    assert result == ("child-flat", "custom")
    assert captured["agents"] == resolved.agents
    assert captured["model_overrides"] == resolved.model_overrides
    assert captured["attached_skills"] == resolved.attached_skills
    assert captured["attached_hooks"] == resolved.attached_hooks
    assert captured["manifest_json"] is None
    assert captured["parent_run_id_override"] == "parent"
    assert captured["owner_id_override"] == "owner-1"
    assert captured["workspace_id_override"] == "workspace-1"
    assert captured["trigger_depth"] == 3


@pytest.mark.asyncio
async def test_run_trigger_workflow_forwards_persisted_manifest_when_target_is_composed(
    monkeypatch,
) -> None:
    manifest = {
        "id": "user-workflow-saved-manifest",
        "steps": [{"agent": "custom-agent"}],
        "_trust": "db",
    }
    compiled = SimpleNamespace(steps=[SimpleNamespace(agent_id="custom-agent")])
    resolved = ResolvedTriggeredWorkflow(
        pipeline_type="custom",
        compiled=compiled,
        manifest_json=manifest,
    )
    captured: dict[str, object] = {}

    async def _launch_run(**kwargs):
        captured.update(kwargs)
        return {"run_id": "child-manifest"}

    port = TriggerLaunchPort(
        resolve_saved_workflow=lambda *_: resolved,
        launch_run=_launch_run,
    )
    monkeypatch.setattr(kernel_services, "get_trigger_launch_port", lambda: port)
    ectx = SimpleNamespace(
        run_id="parent",
        owner_id="owner-1",
        workspace_id="workspace-1",
        trigger_depth=0,
    )

    result = await _services().run_trigger_workflow(
        None, ectx, workflow_ref="saved-manifest"
    )

    assert result == ("child-manifest", "custom")
    assert captured["compiled"] is compiled
    assert captured["manifest_json"] == manifest
    assert captured["agents"] is None
