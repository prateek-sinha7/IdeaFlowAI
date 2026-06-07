"""Unit tests for agents/workflows/compiler.py — WorkflowCompiler.compile.

Covers MAN-02 / MAN-03 / INV-1 / INV-4 / INV-5:
  - test_compiles_clean:  a well-formed manifest compiles to a CompiledWorkflow
    whose steps (agent_id/strategy), deliverable, clarify, planner match input.
  - test_unknown_capability:  an unregistered strategy/validator/gate/
    context_provider/deliverable/task_parser reference raises CompilerError whose
    message NAMES the bad reference (INV-4 / MAN-03).
  - test_rejects_dsl:  a manifest carrying a control-flow construct
    (when:/if:/for:/${...}/{{...}}) is rejected (INV-5 / D-08) — either at load
    (strict-key) or by the compiler refusing the expression value.
  - test_no_name_branch:  compiler.py source contains NO workflow-name /
    pipeline_type literal branch (INV-1) and NO eval/exec.
  - test_empty_plan:  a steps:[] manifest compiles to an empty-step plan (D-05).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.capabilities.registry import CapabilityRegistry
from agents.workflows.compiler import CompilerError, WorkflowCompiler
from agents.workflows.manifest import (
    ManifestValidationError,
    WorkflowManifest,
    load_manifest,
)
from agents.workflows.plan import CompiledWorkflow, Step

_COMPILER_SRC = (
    Path(__file__).resolve().parents[2]
    / "agents"
    / "workflows"
    / "compiler.py"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _manifest(**overrides) -> WorkflowManifest:
    """Build a well-formed WorkflowManifest, overriding any field."""
    base = dict(
        id="demo",
        steps=[
            {"agent": "demo-specify", "strategy": "single_shot", "gates": ["human"]},
            {
                "agent": "demo-build",
                "strategy": "task_loop",
                "task_source": {"kind": "parsed", "parser": "heading_tasks"},
                "validators": ["html_static", "html_render"],
                "compaction": "html_skeleton",
            },
        ],
        deliverable={"strategy": "single_file", "name": "out.html"},
        planner="run",
        clarify={"mode": "auto", "defaults": ["target_audience", "scope"]},
        context_providers=["previous_run"],
        seed_files={},
        version=1,
    )
    base.update(overrides)
    return WorkflowManifest(**base)


def _write_manifest(base_dir: Path, workflow_id: str, text: str) -> Path:
    wf_dir = base_dir / workflow_id
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / "workflow.yaml").write_text(text, encoding="utf-8")
    return base_dir


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_compiles_clean() -> None:
    compiled = WorkflowCompiler().compile(_manifest(), CapabilityRegistry())

    assert isinstance(compiled, CompiledWorkflow)
    assert compiled.id == "demo"
    assert compiled.planner == "run"
    assert compiled.clarify.defaults == ["target_audience", "scope"]
    assert compiled.deliverable.strategy == "single_file"
    assert compiled.deliverable.name == "out.html"
    assert compiled.context_providers == ["previous_run"]

    assert [s.agent_id for s in compiled.steps] == ["demo-specify", "demo-build"]
    assert all(isinstance(s, Step) for s in compiled.steps)
    assert compiled.steps[0].strategy == "single_shot"
    assert compiled.steps[0].gates == ["human"]
    assert compiled.steps[1].strategy == "task_loop"
    assert compiled.steps[1].validators == ["html_static", "html_render"]
    assert compiled.steps[1].compaction == "html_skeleton"
    assert compiled.steps[1].task_source is not None
    assert compiled.steps[1].task_source.parser == "heading_tasks"


def test_empty_plan() -> None:
    compiled = WorkflowCompiler().compile(_manifest(steps=[]), CapabilityRegistry())
    assert compiled.steps == []


# ---------------------------------------------------------------------------
# Unknown capability reference → CompilerError naming the bad ref (INV-4)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides, bad_name",
    [
        ({"steps": [{"agent": "a", "strategy": "nonexistent"}]}, "nonexistent"),
        (
            {"steps": [{"agent": "a", "validators": ["bogus_validator"]}]},
            "bogus_validator",
        ),
        ({"steps": [{"agent": "a", "gates": ["bogus_gate"]}]}, "bogus_gate"),
        (
            {
                "steps": [
                    {
                        "agent": "a",
                        "task_source": {"kind": "parsed", "parser": "bogus_parser"},
                    }
                ]
            },
            "bogus_parser",
        ),
        ({"steps": [{"agent": "a", "compaction": "bogus_compaction"}]}, "bogus_compaction"),
        ({"context_providers": ["bogus_provider"]}, "bogus_provider"),
        ({"deliverable": {"strategy": "bogus_deliverable"}}, "bogus_deliverable"),
    ],
)
def test_unknown_capability(overrides: dict, bad_name: str) -> None:
    with pytest.raises(CompilerError) as exc:
        WorkflowCompiler().compile(_manifest(**overrides), CapabilityRegistry())
    assert bad_name in str(exc.value)


# ---------------------------------------------------------------------------
# DSL rejection (INV-5 / D-08)
# ---------------------------------------------------------------------------


def test_rejects_dsl(tmp_path: Path) -> None:
    # A control-flow top-level key has nowhere to live: load-time strict-key
    # rejection (D-08) is the first guard. Assert the load path rejects it.
    dsl_yaml = """\
id: dsl_demo
planner: run
clarify: {mode: auto, defaults: []}
deliverable: {strategy: streamed_text}
when: some_condition
steps:
  - agent: a
    strategy: single_shot
"""
    base = _write_manifest(tmp_path, "dsl_demo", dsl_yaml)
    with pytest.raises(ManifestValidationError):
        load_manifest("dsl_demo", base)

    # And an expression value smuggled into a capability name must not resolve
    # against the registry — the compiler refuses it (names the bad reference).
    with pytest.raises(CompilerError):
        WorkflowCompiler().compile(
            _manifest(steps=[{"agent": "a", "strategy": "${evil}"}]),
            CapabilityRegistry(),
        )


# ---------------------------------------------------------------------------
# Structure test — no workflow-name branch, no eval (INV-1)
# ---------------------------------------------------------------------------


def test_no_name_branch() -> None:
    src_lines = _COMPILER_SRC.read_text(encoding="utf-8").splitlines()
    # Strip comment-only lines so a docstring/comment mention is not a false hit.
    code = "\n".join(
        line for line in src_lines if not line.lstrip().startswith("#")
    )
    assert "if pipeline_type" not in code
    for literal in ('== "prototype"', '== "ppt"', '== "user_stories"', '== "chat"'):
        assert literal not in code
    assert "eval(" not in code
    assert "exec(" not in code
