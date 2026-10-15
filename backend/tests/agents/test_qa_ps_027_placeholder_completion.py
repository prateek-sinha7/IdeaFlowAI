"""tests/agents/test_qa_ps_027_placeholder_completion.py — QA-PS-027.

The engine's terminal completion gate (``_execute_impl``, "Step 5: Pipeline
complete", ``engine.py:7376-7457``) only inspects whether an agent RAISED an
exception — never whether its output is meaningful. An agent that streams
conversational/placeholder text (no tool call, no exception) is a clean
completion, so ``published_status`` stays ``"completed"`` even though no real
deliverable was produced.

Four ISS cards, one shared root cause, four distinct consumer/resolver paths:

  * ISS-721 (root) — a ``custom`` pipeline run: ``streamed_text`` deliverable
    strategy takes the LAST agent's placeholder text verbatim.
  * ISS-761 (sibling) — a native (non-composer) pipeline: ``prototype``'s
    ``single_file`` resolver falls back to raw streamed text
    (``single_file.py`` branch 3, ":158-165") when the declared file is
    missing.
  * ISS-762 (sibling) — a ``*_revision`` pipeline: the SAME ``_execute_impl``
    kernel, exercised through the revision dispatch path
    (``ppt_revision`` here) rather than a forward launch.
  * ISS-763 (sibling) — the ``serialized_sandbox`` resolver gates on file
    COUNT alone (``count_sandbox_deliverables(root) > 0``), never content —
    tested directly at the resolver, offline, no engine drive needed.

All four drive the REAL ``_execute_impl`` end to end via the offline
``_drive`` harness (``tests.agents._scripted_model``, zero Bedrock cost) except
ISS-763, which calls the resolver directly (mirrors
``test_serialized_sandbox_payload_v3.py``'s unit-level idiom).
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import agents.execution_engine.engine as engine_mod
import tests.agents._scripted_model as _sm
from agents.capabilities.deliverables._format import coerce_to_declared_format
from agents.execution_engine.finalization import FinalizationRecord
from tests.agents._scripted_model import _ScriptedTurn, _drive

_orig_scripts_for = _sm._scripts_for

PLACEHOLDER_TEXT = (
    "I don't have access to a write_file tool for this task. This suggests "
    "the pipeline may have failed or the files were not properly generated."
)


def _clean_finalizer():
    """Stub ``finalize_terminal_run`` with an unconditionally CLEAN record.

    The offline harness's synthetic run id (``harness-<type>-<hex>``) is not a
    real UUID, so the REAL finalizer's ``create_run_ref`` call fails and one of
    the completion gate's four explicit degrade signals fires for an unrelated
    reason (finalizer-level non-chainable reason, engine.py:7439-7441) — that
    would mask the content-quality gap this file exists to prove. Mirrors
    ``test_pipeline_complete_status_v3.py``'s ``_fake_finalizer`` recipe.
    """

    async def _finalize(run_id, ectx, *, candidate_status="completed"):
        return FinalizationRecord(
            run_id=run_id,
            owner_id="harness-user",
            workspace_id="",
            published_status="completed",
            candidate_status="completed",
        )

    return _finalize


def _pipeline_complete(events: list[dict]) -> dict:
    completes = [e for e in events if e.get("type") == "pipeline_complete"]
    assert len(completes) == 1, f"expected exactly 1 pipeline_complete, got {completes}"
    return completes[0]["data"]


# ---------------------------------------------------------------------------
# ISS-721 — custom pipeline, forward run: last agent's placeholder text IS the
# deliverable (streamed_text strategy), and published_status stays "completed".
# ---------------------------------------------------------------------------


def _custom_placeholder_scripts(agent_id: str) -> list[_ScriptedTurn]:
    if agent_id == "task-list-planner":
        # task-list-planner is the LAST step in custom/workflow.yaml — its
        # streamed text is what streamed_text.py hands back as the deliverable.
        return [_ScriptedTurn(texts=[PLACEHOLDER_TEXT], usage=(15, 8))]
    return _orig_scripts_for(agent_id)


@pytest.mark.asyncio
@pytest.mark.issue("ISS-721")
async def test_custom_pipeline_placeholder_output_not_marked_completed() -> None:
    """A custom-workflow run whose final agent only narrates confusion (no
    exception, no real deliverable) must not publish 'completed'."""
    _sm._scripts_for = _custom_placeholder_scripts
    try:
        with patch.object(engine_mod, "finalize_terminal_run", _clean_finalizer()):
            events = await _drive("custom")
    finally:
        _sm._scripts_for = _orig_scripts_for

    data = _pipeline_complete(events)
    assert data.get("final_output", "") == PLACEHOLDER_TEXT, (
        "sanity check: the placeholder text must be exactly what the "
        "deliverable resolver returned, or this test proves nothing about "
        "content quality"
    )
    assert data.get("published_status") != "completed", (
        "the engine's completion gate checks only for exceptions "
        "(engine.py _unrecovered_agents, :7376-7390) — a clean-exit agent "
        "whose streamed output is pure placeholder narration still "
        "publishes 'completed' (QA-PS-027 / ISS-721)"
    )


# ---------------------------------------------------------------------------
# ISS-761 — native (non-composer) pipeline: prototype-build calls
# report_task_complete (a clean task-loop completion) but never write_file,
# so single_file.py's branch-3 fallback returns the raw placeholder stream.
# ---------------------------------------------------------------------------


def _prototype_placeholder_scripts(agent_id: str) -> list[_ScriptedTurn]:
    if agent_id == "prototype-plan":
        # A single task so prototype-build runs exactly once.
        return [
            _ScriptedTurn(
                texts=["## Task 1: Build the full shell\nOne task only.\n"],
                usage=(40, 30),
            )
        ]
    if agent_id == "prototype-build":
        return [
            _ScriptedTurn(
                texts=[PLACEHOLDER_TEXT],
                tool_calls=[
                    (
                        "report_task_complete",
                        json.dumps(
                            {
                                "task_number": 1,
                                "task_title": "Shell",
                                "summary": "blocked",
                            }
                        ),
                        "c_rtc",
                    ),
                ],
                usage=(15, 8),
            ),
            # ISS-860: text-only wrap-up turn. _next_turn replays turns[-1], so
            # ending on the tool-call turn loops to GraphRecursionError.
            _ScriptedTurn(texts=["Task complete."], usage=(5, 3)),
        ]
    if agent_id == "prototype-validate":
        # single_file's branch-3 fallback reads ctx.last_streamed — whichever
        # agent ran LAST overall (validate, not build) — so validate must also
        # stream nothing real for the raw-fallback text to be the placeholder.
        return [_ScriptedTurn(texts=[PLACEHOLDER_TEXT], usage=(15, 8))]
    return _orig_scripts_for(agent_id)


@pytest.mark.asyncio
@pytest.mark.issue("ISS-761")
async def test_native_prototype_pipeline_placeholder_output_not_marked_completed() -> (
    None
):
    """A native `prototype` run whose build agent never writes prototype.html
    (only streams placeholder text, then reports the task complete) must not
    publish 'completed' — the SAME content-blind gate ISS-721 found in
    _execute_impl, reached through a non-composer pipeline type."""
    _sm._scripts_for = _prototype_placeholder_scripts
    try:
        with patch.object(engine_mod, "finalize_terminal_run", _clean_finalizer()):
            events = await _drive("prototype")
    finally:
        _sm._scripts_for = _orig_scripts_for

    data = _pipeline_complete(events)
    # FIX-623 (QA-SG-014 / ISS-776): branch 3 renders its fallback in the declared .html format.
    assert data.get("final_output", "") == coerce_to_declared_format(
        PLACEHOLDER_TEXT, "prototype.html"
    ), (
        "sanity check: prototype.html must never have been written, so the "
        "single_file resolver's branch-3 raw-stream fallback is what fired"
    )
    assert data.get("published_status") != "completed", (
        "_execute_impl has no pipeline_type branch (SC-001) — a native "
        "prototype build agent that cleanly reports task completion without "
        "writing prototype.html still publishes 'completed' (QA-PS-027 / "
        "ISS-761)"
    )


@pytest.mark.asyncio
@pytest.mark.issue("ISS-860")
async def test_iss761_fixture_models_clean_task_completion(monkeypatch) -> None:
    """ISS-860 — the ISS-761 fixture must model a CLEAN report_task_complete:
    prototype-build must not loop to GraphRecursionError and be marked failed."""
    from app.core.config import settings

    # Cap the runaway loop so the pre-fix run goes red in seconds, not 2500 steps.
    monkeypatch.setattr(settings, "AGENT_RECURSION_LIMIT", 60)
    _sm._scripts_for = _prototype_placeholder_scripts
    try:
        with patch.object(engine_mod, "finalize_terminal_run", _clean_finalizer()):
            events = await _drive("prototype")
    finally:
        _sm._scripts_for = _orig_scripts_for

    data = _pipeline_complete(events)
    assert not data.get(
        "agents_failed"
    ), f"prototype-build was marked failed: {data.get('agents_failed')}"
    assert not [e for e in events if e.get("type") == "agent_error"]


# ---------------------------------------------------------------------------
# ISS-762 — revision pipeline: the SAME _execute_impl kernel, run through the
# ppt_revision manifest instead of a forward custom/native launch.
# ---------------------------------------------------------------------------


def _ppt_revision_placeholder_scripts(agent_id: str) -> list[_ScriptedTurn]:
    if agent_id == "ppt-revision-agent":
        # Streams conversational text and calls no tool at all — no
        # presentation.html edit, no exception.
        return [_ScriptedTurn(texts=[PLACEHOLDER_TEXT], usage=(15, 8))]
    return _orig_scripts_for(agent_id)


@pytest.mark.asyncio
@pytest.mark.issue("ISS-762")
async def test_revision_pipeline_placeholder_output_not_marked_completed() -> None:
    """A ppt_revision run whose editing agent only narrates confusion (no
    presentation.html edit, no exception) must not publish 'completed' — the
    revision dispatch path shares ISS-721's unaware _execute_impl kernel."""
    _sm._scripts_for = _ppt_revision_placeholder_scripts
    try:
        with patch.object(engine_mod, "finalize_terminal_run", _clean_finalizer()):
            events = await _drive("ppt_revision")
    finally:
        _sm._scripts_for = _orig_scripts_for

    data = _pipeline_complete(events)
    # FIX-623 (QA-SG-014 / ISS-776): branch 3 renders its fallback in the declared .html format.
    assert data.get("final_output", "") == coerce_to_declared_format(
        PLACEHOLDER_TEXT, "presentation.html"
    ), (
        "sanity check: presentation.html must never have been edited, so "
        "the single_file resolver's raw-stream fallback is what fired"
    )
    assert data.get("published_status") != "completed", (
        "run_commands.py's _drive_revision_to_queue persists WorkflowRun "
        "status straight off this same content-blind pipeline_complete.status "
        "field — a revision agent that cleanly exits without editing the "
        "deliverable still publishes 'completed' (QA-PS-027 / ISS-762)"
    )


# ---------------------------------------------------------------------------
# ISS-763 — serialized_sandbox resolver: count_sandbox_deliverables(root) > 0
# is a file-COUNT gate, never a content gate. Unit-level, no engine drive.
# ---------------------------------------------------------------------------


@pytest.mark.issue("ISS-763")
def test_serialized_sandbox_resolver_rejects_placeholder_only_sandbox(tmp_path) -> None:
    """A sandbox holding exactly one file — the artifact-fallback write of an
    agent's placeholder narration (engine.py _check_artifact_fallback,
    :8333) — must not be accepted as a real code-gen deliverable just
    because count_sandbox_deliverables(root) > 0."""
    from agents.capabilities.deliverables.serialized_sandbox import (
        SerializedSandboxResolver,
    )
    from app.agents.sandbox import (
        RunSandbox,
        count_sandbox_deliverables,
        serialize_sandbox_deliverable,
    )

    sandbox = RunSandbox("t-qaps027", "run-763", runs_root=str(tmp_path))
    sandbox.ensure()
    # The one file _check_artifact_fallback would have planted: the agent's
    # raw streamed apology, verbatim, no length/content check.
    sandbox.write("output.md", PLACEHOLDER_TEXT)

    runner = SimpleNamespace(
        sandbox=sandbox,
        count_sandbox_deliverables=count_sandbox_deliverables,
        serialize_sandbox_deliverable=serialize_sandbox_deliverable,
    )
    ctx = SimpleNamespace(runner=runner)

    result = SerializedSandboxResolver().resolve(ctx)

    assert result is None, (
        "SerializedSandboxResolver.resolve gates on "
        "count_sandbox_deliverables(root) > 0 alone (serialized_sandbox.py:"
        "45-51) — a sandbox holding a single placeholder-narration file "
        "(planted by _check_artifact_fallback) satisfies that count and is "
        "serialized as a 'completed' code-gen bundle (QA-PS-027 / ISS-763)"
    )
