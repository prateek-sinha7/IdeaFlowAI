"""A10 (STABILIZATION.md) — the ``mechanical: publish`` no-model step kind.

Two halves:
  * compile-time — ``WorkflowCompiler`` accepts a declared ``mechanical: "publish"``
    step, materializes it onto the compiled ``Step``, and rejects a malformed
    declaration (an unknown kind, or ``mechanical`` paired with a ``tools:`` grant).
  * run-time — ``agents.capabilities.publish_step.publish_draft`` copies the
    highest-numbered ``draft.v*.html`` (numeric ``vN`` comparison, never lexical)
    onto the deliverable name byte-for-byte, returns its content, and raises a
    ``PublishStepError`` naming the glob when there is nothing to copy.
"""

from __future__ import annotations

import pytest

from agents.capabilities.publish_step import (
    MechanicalPublishStrategy,
    PublishStepError,
    publish_draft,
)
from agents.capabilities.registry import CapabilityRegistry
from agents.workflows.compiler import CompilerError, WorkflowCompiler
from agents.workflows.manifest import WorkflowManifest
from app.agents.sandbox import RunSandbox


# ===========================================================================
# Compile-time: mechanical: publish
# ===========================================================================


def _manifest_one_step(step: dict) -> WorkflowManifest:
    return WorkflowManifest(
        id="pub-test",
        steps=[step],
        deliverable={
            "strategy": "single_file",
            "name": "prototype.html",
            "publish_from_glob": "draft.v*.html",
        },
        planner="run",
        clarify={"mode": "auto", "defaults": []},
        context_providers=[],
        seed_files={},
        version=1,
    )


def test_mechanical_publish_compiles_and_is_materialized_on_the_step():
    manifest = _manifest_one_step(
        {"agent": "custom-agent", "instance_id": "publish", "mechanical": "publish"}
    )
    compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry())
    assert compiled.steps[0].mechanical == "publish"


def test_mechanical_absent_defaults_to_none():
    manifest = _manifest_one_step({"agent": "step-x"})
    compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry())
    assert compiled.steps[0].mechanical is None


def test_unknown_mechanical_kind_raises():
    manifest = _manifest_one_step({"agent": "step-x", "mechanical": "teleport"})
    with pytest.raises(CompilerError) as exc:
        WorkflowCompiler().compile(manifest, CapabilityRegistry())
    assert "teleport" in str(exc.value)


def test_mechanical_with_tools_grant_raises():
    """A mechanical step runs no agent — a tools: grant has nothing to bind to."""
    manifest = _manifest_one_step(
        {
            "agent": "step-x",
            "mechanical": "publish",
            "tools": {"read_files": True},
        }
    )
    with pytest.raises(CompilerError) as exc:
        WorkflowCompiler().compile(manifest, CapabilityRegistry())
    assert "tools" in str(exc.value)


def test_mechanical_with_validators_is_allowed():
    """validators: is explicitly meaningful on a publish step (the shipped file
    is render-checked) — must NOT be rejected."""
    manifest = _manifest_one_step(
        {
            "agent": "step-x",
            "mechanical": "publish",
            "validators": ["html_static"],
        }
    )
    compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry())
    assert compiled.steps[0].mechanical == "publish"
    assert compiled.steps[0].validators == ["html_static"]


def test_mechanical_with_human_gate_is_allowed():
    """gates: is explicitly meaningful on a publish step (review before publish)
    — must NOT be rejected."""
    manifest = _manifest_one_step(
        {
            "agent": "step-x",
            "mechanical": "publish",
            "gates": ["human"],
        }
    )
    compiled = WorkflowCompiler().compile(manifest, CapabilityRegistry())
    assert compiled.steps[0].gates == ["human"]


# ===========================================================================
# Run-time: publish_draft
# ===========================================================================


class _Deliverable:
    def __init__(self, name=None, publish_from_glob=None) -> None:
        self.name = name
        self.publish_from_glob = publish_from_glob


class _FakeRunner:
    def __init__(self, sandbox) -> None:
        self.sandbox = sandbox


class _Ctx:
    def __init__(self, runner, deliverable) -> None:
        self.runner = runner
        self.deliverable = deliverable


@pytest.fixture
def sandbox(tmp_path):
    return RunSandbox("tester", "run-publish", runs_root=str(tmp_path))


def test_publish_draft_copies_highest_version_numerically(sandbox):
    """v10 > v9 > v2 numerically, never lexically ('draft.v2' > 'draft.v10')."""
    sandbox.write("draft.v2.html", "<html>v2</html>")
    sandbox.write("draft.v9.html", "<html>v9</html>")
    sandbox.write("draft.v10.html", "<html>v10 — the real highest</html>")
    ctx = _Ctx(
        _FakeRunner(sandbox),
        _Deliverable(name="prototype.html", publish_from_glob="draft.v*.html"),
    )

    out = publish_draft(ctx)

    assert out == "<html>v10 — the real highest</html>"
    assert sandbox.read("prototype.html") == out


def test_publish_draft_defaults_deliverable_name_to_prototype_html(sandbox):
    sandbox.write("draft.v1.html", "<html>only draft</html>")
    ctx = _Ctx(
        _FakeRunner(sandbox), _Deliverable(publish_from_glob="draft.v*.html")
    )  # name omitted

    publish_draft(ctx)

    assert sandbox.read("prototype.html") == "<html>only draft</html>"


def test_publish_draft_raises_when_no_draft_exists(sandbox):
    with pytest.raises(PublishStepError) as exc:
        publish_draft(
            _Ctx(
                _FakeRunner(sandbox),
                _Deliverable(name="prototype.html", publish_from_glob="draft.v*.html"),
            )
        )
    assert "draft.v*.html" in str(exc.value)


def test_publish_draft_raises_when_glob_undeclared(sandbox):
    sandbox.write("draft.v1.html", "<html>irrelevant</html>")
    with pytest.raises(PublishStepError):
        publish_draft(_Ctx(_FakeRunner(sandbox), _Deliverable(name="prototype.html")))


def test_publish_draft_never_invents_content_on_failure(sandbox):
    """A failed publish must not leave a fabricated prototype.html behind."""
    with pytest.raises(PublishStepError):
        publish_draft(
            _Ctx(
                _FakeRunner(sandbox),
                _Deliverable(name="prototype.html", publish_from_glob="draft.v*.html"),
            )
        )
    assert sandbox.read("prototype.html") is None


# ===========================================================================
# Run-time: MechanicalPublishStrategy — the strategy-shaped engine-hook adapter
# ===========================================================================


class _Spec:
    id = "custom-agent:publish"
    name = "Publish"
    role = "Publish the finished draft"
    icon = "Upload"


async def _drain(agen):
    return [event async for event in agen]


@pytest.mark.asyncio
async def test_strategy_emits_start_chunk_complete_with_zero_tokens(sandbox):
    sandbox.write("draft.v1.html", "<html>final</html>")
    ctx = _Ctx(
        _FakeRunner(sandbox),
        _Deliverable(name="prototype.html", publish_from_glob="draft.v*.html"),
    )
    results: list = []
    strategy = MechanicalPublishStrategy(
        spec=_Spec(), index=7, total=9, results=results
    )

    events = await _drain(strategy.run(step=None, ctx=ctx))

    types = [e["type"] for e in events]
    assert types == ["agent_start", "agent_chunk", "agent_complete"]
    assert events[0]["data"]["index"] == 7 and events[0]["data"]["total"] == 9
    assert events[1]["data"]["chunk"] == "<html>final</html>"
    complete = events[2]["data"]
    assert complete["output_length"] == len("<html>final</html>")
    assert complete["input_tokens"] == 0 and complete["total_tokens"] == 0
    # The step's output lands in the shared `results` list (the SAME contract
    # `_run_agent` appends to), so `ectx.last_streamed` refreshes downstream.
    assert results == [
        {
            "agent_id": "custom-agent:publish",
            "name": "Publish",
            "role": _Spec.role,
            "icon": _Spec.icon,
            "output": "<html>final</html>",
            "duration": results[0]["duration"],
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
        }
    ]


@pytest.mark.asyncio
async def test_strategy_emits_agent_error_and_appends_nothing_when_no_draft(sandbox):
    ctx = _Ctx(
        _FakeRunner(sandbox),
        _Deliverable(name="prototype.html", publish_from_glob="draft.v*.html"),
    )
    results: list = []
    strategy = MechanicalPublishStrategy(
        spec=_Spec(), index=0, total=1, results=results
    )

    events = await _drain(strategy.run(step=None, ctx=ctx))

    assert [e["type"] for e in events] == ["agent_start", "agent_error"]
    assert events[1]["data"]["recoverable"] is False
    assert "draft.v*.html" in events[1]["data"]["error"]
    assert results == []


# ===========================================================================
# Engine-level: a compiled plan with a mechanical: publish step, end-to-end
# ===========================================================================
#
# Offline — no live LLM. Driven via the scripted-model harness
# (tests/agents/_scripted_model._drive) against agents/workflows/ex_publish_step/
# workflow.yaml (draft -> publish), proving the A10 engine hook: the outer
# per-step dispatch loop short-circuits strategy resolution for a mechanical
# step and drives MechanicalPublishStrategy through the SAME generic
# gates/hooks/cursor machinery every other strategy uses.


def _publish_fixture_scripts_for(agent_id: str) -> list:
    """draft writes draft.v1.html via write_file; publish never reaches the
    model (mechanical — no create_runner call for it)."""
    from tests.agents._scripted_model import _ScriptedTurn
    import json as _json

    if agent_id == "custom-agent:draft":
        html = "<html><body>the finished draft</body></html>"
        return [
            _ScriptedTurn(
                texts=["Writing the draft. "],
                tool_calls=[
                    (
                        "write_file",
                        _json.dumps({"file_path": "draft.v1.html", "content": html}),
                        "c_draft",
                    ),
                ],
                usage=(20, 10),
            ),
            _ScriptedTurn(texts=["Done."], usage=(5, 2)),
        ]
    return [_ScriptedTurn(texts=[f"{agent_id} default output."], usage=(5, 3))]


@pytest.mark.asyncio
async def test_engine_runs_mechanical_publish_step_end_to_end():
    from tests.agents import _scripted_model as _sm
    from tests.agents._scripted_model import _drive

    orig_scripts_for = _sm._scripts_for
    _sm._scripts_for = _publish_fixture_scripts_for
    try:
        # ``offline_db=False``: this test asserts a CLEAN completion, and the
        # finalizer degrades a completed run whenever its tag->WorkflowRun mapping
        # write raises (Requirement 5 AC 22). The default no-database seam raises
        # on every session, so it would publish ``degraded`` for reasons unrelated
        # to the publish step. The hermetic per-worker SQLite (tests/conftest.py)
        # lets that write run — a missing row is tolerated, not a failure.
        events = await _drive("ex_publish_step", offline_db=False)
    finally:
        _sm._scripts_for = orig_scripts_for

    types = [e.get("type") for e in events]
    starts = [
        e["data"].get("agent_id") for e in events if e.get("type") == "agent_start"
    ]
    assert starts == ["custom-agent:draft", "custom-agent:publish"], (starts, types)

    publish_complete = next(
        e
        for e in events
        if e.get("type") == "agent_complete"
        and e["data"].get("agent_id") == "custom-agent:publish"
    )
    expected_html = "<html><body>the finished draft</body></html>"
    assert publish_complete["data"]["output_length"] == len(expected_html)
    assert publish_complete["data"]["input_tokens"] == 0
    assert publish_complete["data"]["output_tokens"] == 0
    assert publish_complete["data"]["total_tokens"] == 0

    publish_chunk = next(
        e
        for e in events
        if e.get("type") == "agent_chunk"
        and e["data"].get("agent_id") == "custom-agent:publish"
    )
    assert publish_chunk["data"]["chunk"] == expected_html

    completes = [e for e in events if e.get("type") == "pipeline_complete"]
    assert len(completes) == 1, types
    assert completes[0]["data"].get("status") != "degraded"
