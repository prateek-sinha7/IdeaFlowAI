"""P27 ``write_paths``: an opt-in per-step write allow-list, enforced by the runner's path guard.

Run a46ce12b/8012aa52: the Ingest step read the brief ("Build the simulator") as its own job and
wrote a whole app (app/oms-channel-simulator.html); later builders kept working in it instead of
prototype.html. Steps that must not build now declare where they may write.
"""

from types import SimpleNamespace

import pytest

from agents.capabilities.registry import CapabilityRegistry
from agents.workflows.compiler import CompilerError, WorkflowCompiler
from agents.workflows.manifest import WorkflowManifest
from app.agents.deep_agent_runner import _ReservedPathGuardMiddleware


def _compile(**step_keys):
    step = {"agent": "step-x", **step_keys}
    m = WorkflowManifest(
        id="t",
        steps=[step],
        deliverable={"strategy": "single_file", "name": "o.html"},
        planner="run",
        clarify={"mode": "auto", "defaults": []},
        context_providers=[],
        seed_files={},
        version=1,
    )
    return WorkflowCompiler().compile(m, CapabilityRegistry()).steps[0]


def _write(path, tool="write_file"):
    return SimpleNamespace(
        tool_call={"name": tool, "args": {"file_path": path}, "id": "c1"}
    )


def test_compile_carries_write_paths():
    assert _compile(write_paths=[".goal/*", "ingest-*.md"]).write_paths == [
        ".goal/*",
        "ingest-*.md",
    ]


def test_compile_absent_means_unrestricted():
    assert _compile().write_paths is None


@pytest.mark.parametrize("value", [[], "x", [""], [1]])
def test_compile_rejects_bad_write_paths(value):
    with pytest.raises(CompilerError, match="write_paths"):
        _compile(write_paths=value)


GUARD = _ReservedPathGuardMiddleware(write_paths=[".goal/*", "ingest-*.md"])


@pytest.mark.parametrize(
    "path", ["/.goal/inventory.json", ".goal/acceptance/G1.json", "./ingest-oms.md"]
)
def test_allowed_writes_pass(path):
    assert GUARD._refusal(_write(path)) is None


@pytest.mark.parametrize(
    "path",
    [
        "/app/oms-channel-simulator.html",
        "index.html",
        "prototype.html",
        "/.goal/../index.html",
    ],
)
def test_other_writes_are_refused(path):
    refusal = GUARD._refusal(_write(path))
    assert refusal is not None and refusal.status == "error"
    assert "may only write" in refusal.content


def test_edit_file_is_guarded_too():
    assert GUARD._refusal(_write("/app/x.html", tool="edit_file")) is not None


def test_reads_are_not_limited():
    req = SimpleNamespace(
        tool_call={
            "name": "read_file",
            "args": {"file_path": "/prototype.html"},
            "id": "c1",
        }
    )
    assert GUARD._refusal(req) is None


def test_no_write_paths_keeps_todays_behaviour():
    assert _ReservedPathGuardMiddleware()._refusal(_write("/app/anything.html")) is None


# --- brief_role: reference -------------------------------------------------------------

from agents.execution_engine.context import ExecutionContext  # noqa: E402
from agents.execution_engine.engine import ExecutionEngine  # noqa: E402


def test_compile_carries_brief_role():
    assert _compile(brief_role="reference").brief_role == "reference"
    assert _compile().brief_role is None
    with pytest.raises(CompilerError, match="brief_role"):
        _compile(brief_role="other")


async def _first_message(step) -> str:
    spec = SimpleNamespace(
        id="custom-agent:ingest",
        name="ingest",
        role="t",
        injects=[],
        tools=[],
        consumes=[],
    )
    ectx = ExecutionContext(run_id="r-brief", owner_id="o-brief")
    ectx.current_step = step
    return await ExecutionEngine()._compose_context_message(
        spec=spec,
        index=0,
        ordered_agents=[spec],
        user_message="Build the simulator",
        planning_context={},
        ectx=ectx,
    )


@pytest.mark.asyncio
async def test_reference_brief_is_framed_as_background():
    msg = await _first_message(SimpleNamespace(brief_role="reference"))
    assert "NOT your task" in msg and "Build the simulator" in msg
    assert "=== ORIGINAL USER REQUEST ===" not in msg


@pytest.mark.asyncio
async def test_default_brief_is_unchanged():
    msg = await _first_message(SimpleNamespace(brief_role=None))
    assert msg.startswith("=== ORIGINAL USER REQUEST ===\nBuild the simulator")
