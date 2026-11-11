"""Override rows are predefined for connected apps (design 5.5 layers 1 and 2, OQ4).

``compile_with_baseline(overrides=...)`` and ``merge_override_steps`` must never
let ``tools.connectors`` through, whatever trust the row compiles at.
"""

from __future__ import annotations

import pytest

from agents.capabilities.registry import CapabilityRegistry, discover
from agents.execution_engine.engine import compile_for_run
from agents.execution_engine.overrides import (
    compile_override_steps,
    compile_with_baseline,
    merge_override_steps,
)
from agents.workflows.compiler import CompilerError, ConnectorGrantsNotAllowed
from agents.workflows.manifest import WorkflowManifest

_JIRA = "jira__get_issue"


@pytest.fixture(autouse=True)
def _discovered() -> None:
    discover()


def _manifest(*steps: dict) -> WorkflowManifest:
    return WorkflowManifest(
        id="override-demo",
        steps=list(steps),
        deliverable={},
        planner="run",
        clarify={"mode": "auto", "defaults": []},
        context_providers=[],
        seed_files={},
        version=1,
    )


def _raw_step(**tools: object) -> dict:
    step: dict = {"agent": "demo-agent", "strategy": "single_shot"}
    if tools:
        step["tools"] = dict(tools)
    return step


class TestCompileWithBaseline:
    @pytest.mark.parametrize("trust", ["user", "db"])
    def test_compile_with_baseline_raises_when_override_step_names_connectors(
        self, trust: str
    ) -> None:
        manifest = _manifest(_raw_step(connectors=[_JIRA]))

        with pytest.raises(ConnectorGrantsNotAllowed) as excinfo:
            compile_with_baseline(
                manifest, CapabilityRegistry(), trust=trust, overrides="custom"
            )

        assert "demo-agent" in str(excinfo.value)
        assert "custom" in str(excinfo.value)

    def test_compile_with_baseline_clears_admit_flag_when_override_has_no_grants(
        self,
    ) -> None:
        plan = compile_with_baseline(
            _manifest(_raw_step()),
            CapabilityRegistry(),
            trust="user",
            overrides="custom",
        )

        assert plan.admits_connector_grants is False

    def test_compile_with_baseline_admits_grants_when_it_is_a_plain_compile(
        self,
    ) -> None:
        plan = compile_with_baseline(
            _manifest(_raw_step(connectors=[_JIRA])),
            CapabilityRegistry(),
            trust="user",
            overrides=None,
        )

        assert plan.admits_connector_grants is True
        assert plan.steps[0].tools.connectors == [_JIRA]

    def test_compile_with_baseline_accepts_empty_connectors_when_override(
        self,
    ) -> None:
        plan = compile_with_baseline(
            _manifest(_raw_step(connectors=[])),
            CapabilityRegistry(),
            trust="user",
            overrides="custom",
        )

        assert plan.steps[0].tools.connectors == []


class TestCompileOverrideSteps:
    def test_compile_override_steps_raises_when_a_step_names_connectors(self) -> None:
        with pytest.raises(ConnectorGrantsNotAllowed):
            compile_override_steps(
                "custom", [_raw_step(connectors=[_JIRA])], CapabilityRegistry()
            )

    def test_connector_grants_not_allowed_is_caught_as_compiler_error_when_raised(
        self,
    ) -> None:
        with pytest.raises(CompilerError):
            compile_override_steps(
                "custom", [_raw_step(connectors=[_JIRA])], CapabilityRegistry()
            )


class TestMergeOverrideSteps:
    def test_merge_override_steps_does_not_admit_when_merge_succeeds(self) -> None:
        base = compile_for_run("custom")

        merged = merge_override_steps(base, [_raw_step()], CapabilityRegistry())

        assert merged is not base
        assert merged.admits_connector_grants is False
        assert [s.agent_id for s in merged.steps] == ["demo-agent"]

    def test_merge_override_steps_falls_back_to_file_plan_when_grants_are_named(
        self,
    ) -> None:
        base = compile_for_run("custom")

        merged = merge_override_steps(
            base, [_raw_step(connectors=[_JIRA])], CapabilityRegistry()
        )

        assert merged is base
        assert merged.admits_connector_grants is False
        assert all(not s.tools.connectors for s in merged.steps)

    def test_merge_override_steps_leaves_cached_plan_untouched_when_merging(
        self,
    ) -> None:
        base = compile_for_run("custom")
        before = (base.admits_connector_grants, len(base.steps))

        merge_override_steps(base, [_raw_step()], CapabilityRegistry())

        assert (base.admits_connector_grants, len(base.steps)) == before
