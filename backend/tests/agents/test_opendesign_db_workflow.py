"""Tests for DB-authored workflows with opendesign context provider and step injects.

Tests that:
1. A DB-authored manifest with context_providers: ["opendesign"] compiles with values intact
2. Step injects: ["design_system", "template", "template_example"] are preserved
3. OpenDesignProvider emits the correct blocks for a step that declares injects
4. OpenDesignProvider emits nothing without injects
5. OpenDesignProvider skips design_system for build_task_number >= "2"
"""

from __future__ import annotations

import pytest

from agents.capabilities import registry as registry_mod
from agents.capabilities.context_providers.opendesign import OpenDesignProvider
from agents.capabilities.registry import CapabilityRegistry
from agents.workflows.compiler import WorkflowCompiler
from agents.workflows.manifest import build_manifest_from_dict


def test_db_manifest_keeps_context_providers_and_step_injects() -> None:
    """A DB-authored manifest with context_providers and step injects compiles intact."""
    registry_mod.discover()  # ensure built-ins are bound

    raw = {
        "id": "workflow:test-opendesign-db",
        "name": "Test OpenDesign DB Workflow",
        "steps": [
            {
                "agent": "custom-agent",
                "instance_id": "step-1",
                "strategy": "single_shot",
                "gates": [],
                "tools": {"read_files": True, "write_files": True, "exec": False, "tool_sets": []},
            },
            {
                "agent": "custom-agent",
                "instance_id": "step-2",
                "strategy": "single_shot",
                "gates": [],
                "tools": {"read_files": True, "write_files": True, "exec": False, "tool_sets": []},
                "injects": ["design_system", "template", "template_example"],
                "depends_on": ["custom-agent:step-1"],
            },
        ],
        "deliverable": {"strategy": "single_file", "name": "prototype.html"},
        "planner": "skip",
        "clarify": {"mode": "skip", "defaults": []},
        "context_providers": ["opendesign"],
        "design_mode": "web",
    }

    # Compile as a DB-trusted manifest
    manifest = build_manifest_from_dict(raw, "workflow:test-opendesign-db")
    registry = CapabilityRegistry()
    compiled = WorkflowCompiler().compile(manifest, registry, trust="db")

    # Assert context_providers are preserved
    assert compiled.context_providers == ["opendesign"]

    # Assert step injects are preserved (second step)
    assert compiled.steps[1].injects == ["design_system", "template", "template_example"]


@pytest.mark.asyncio
async def test_opendesign_provider_emits_blocks_for_a_step_that_declares_injects() -> None:
    """OpenDesignProvider emits blocks when a step declares injects."""

    class FakeRunner:
        def template_example(self, template_id):
            return "EXAMPLE HTML"

        def template_injection_parts(self, template_id):
            return []

    class FakeCtx:
        def __init__(self):
            self.od_context = {
                "ds_id": "airbnb",
                "ds_body": "DS BODY",
                "template_id": "dashboard",
                "template_body": "TEMPLATE BODY",
            }
            self.current_spec_injects = {"design_system", "template", "template_example"}
            self.current_spec_tools = set()
            self.build_task_number = ""
            self.runner = FakeRunner()

    ctx = FakeCtx()
    provider = OpenDesignProvider()
    result = await provider.load(ctx)

    # Assert the blocks are present with expected content
    assert any(k.startswith("ACTIVE DESIGN SYSTEM") for k in result)
    assert any(k.startswith("ACTIVE TEMPLATE") for k in result)
    assert any(k.startswith("TEMPLATE EXAMPLE") for k in result)

    # Find and verify the design system block ends with DS BODY
    ds_key = next(k for k in result if k.startswith("ACTIVE DESIGN SYSTEM"))
    assert result[ds_key].endswith("DS BODY")

    # Find and verify the template block
    tpl_key = next(k for k in result if k.startswith("ACTIVE TEMPLATE"))
    assert result[tpl_key] == "TEMPLATE BODY"

    # Find and verify the example block
    ex_key = next(k for k in result if k.startswith("TEMPLATE EXAMPLE"))
    assert result[ex_key] == "EXAMPLE HTML"


@pytest.mark.asyncio
async def test_opendesign_provider_emits_nothing_without_injects() -> None:
    """OpenDesignProvider emits empty dict when injects is empty."""

    class FakeRunner:
        def template_example(self, template_id):
            return "EXAMPLE HTML"

        def template_injection_parts(self, template_id):
            return []

    class FakeCtx:
        def __init__(self):
            self.od_context = {
                "ds_id": "airbnb",
                "ds_body": "DS BODY",
                "template_id": "dashboard",
                "template_body": "TEMPLATE BODY",
            }
            self.current_spec_injects = set()  # Empty injects
            self.current_spec_tools = set()
            self.build_task_number = ""
            self.runner = FakeRunner()

    ctx = FakeCtx()
    provider = OpenDesignProvider()
    result = await provider.load(ctx)

    # Assert result is empty
    assert result == {}


@pytest.mark.asyncio
async def test_opendesign_provider_skips_design_system_for_build_task_two_plus() -> None:
    """OpenDesignProvider skips design_system and template for build_task_number >= '2'."""

    class FakeRunner:
        def template_example(self, template_id):
            return "EXAMPLE HTML"

        def template_injection_parts(self, template_id):
            return ["=== TEMPLATE SEED ===\nseed\n=== END TEMPLATE SEED ==="]

    class FakeCtx:
        def __init__(self, build_task_number):
            self.od_context = {
                "ds_id": "airbnb",
                "ds_body": "DS BODY",
                "template_id": "dashboard",
                "template_body": "TEMPLATE BODY",
            }
            self.current_spec_injects = {"design_system", "template", "template_example"}
            self.current_spec_tools = {"prototype_emit_only"}
            self.build_task_number = build_task_number
            self.runner = FakeRunner()

    provider = OpenDesignProvider()

    # Build task 2 - should skip design_system and template blocks
    # but seed injection parts should still be present
    ctx2 = FakeCtx("2")
    result2 = await provider.load(ctx2)
    assert not any(k.startswith("ACTIVE DESIGN SYSTEM") for k in result2)
    assert not any(k.startswith("ACTIVE TEMPLATE") for k in result2)
    assert not any(k.startswith("TEMPLATE EXAMPLE") for k in result2)
    # Seed parts should be present
    assert any("TEMPLATE SEED" in v for v in result2.values())

    # Build task 1 - should include design_system and template
    ctx1 = FakeCtx("1")
    result1 = await provider.load(ctx1)
    assert any(k.startswith("ACTIVE DESIGN SYSTEM") for k in result1)
    assert any(k.startswith("ACTIVE TEMPLATE") for k in result1)
    assert any(k.startswith("TEMPLATE EXAMPLE") for k in result1)
