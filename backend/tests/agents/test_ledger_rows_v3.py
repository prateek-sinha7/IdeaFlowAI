"""tests/agents/test_ledger_rows_v3.py — verification of ledger rows 10, 13.

Covers gaps in the FR-030 30-row ledger (GAPS §1 P2):
  * Row 10: PLANNER.md written after clarify merge (a run that answers a clarify
    gate, read back).
  * Row 13: PRIOR OUTPUT → `-p{visit}` (agents reading prior pass outputs with
    the visit suffix on the filename).

Rows 16/26 (uploads land in `.uploads/` with sidecar) are NOT re-tested here:
`tests/unit/test_run_files_upload.py::test_extractable_doc_lands_raw_plus_sidecar_plus_manifest`
and `::test_txt_upload_lands_raw_has_text_false` already drive the real
`app/api/run_files.py` upload endpoint end to end for exactly this behaviour —
checked first, per the row's own instruction, before deciding not to add a
duplicate here.

Row 10 drives the real engine end to end via
``tests.agents.live_harness.drive_engine_pipeline`` (``ExecutionEngine.execute()``);
row 13 drives ``app.agents.sandbox.write_agent_output`` directly against a real
``RunSandbox``.
"""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Importing the harness forces InMemory checkpointer + temp RUNS_ROOT before
# app.core.config loads.  Keep this import first.
from tests.agents._scripted_model import (  # noqa: E402
    ScriptedFakeChatModel,
    _ScriptedTurn,
    _scripts_for,
)
import tests.agents.live_harness as live_harness  # noqa: E402
from tests.agents.live_harness import drive_engine_pipeline  # noqa: E402


# ===========================================================================
# Row 10 — PLANNER.md written after clarify merge and read back
# ===========================================================================


@pytest.mark.asyncio
async def test_planner_md_written_after_clarify_merge(monkeypatch) -> None:
    """[Row 10 / FR-030] PLANNER.md is written AFTER a clarify-gate round
    answers, reflecting the MERGED planning_context, not the pre-clarify draft.

    Drives the REAL engine end to end — ``drive_engine_pipeline`` ->
    ``ExecutionEngine.execute()`` — with a forced ``CLARIFY_REQUIRED`` planner
    verdict and the questionnaire auto-answered (same offline recipe as
    ``TestClarifyAutoAnswerOffline`` in ``test_live_harness.py``: the LLM
    question-generation call is forced to fail so ``ClarifyEngine`` falls back
    to its static question library, zero Bedrock cost). This actually reaches
    the clarify-then-merge flow the row requires ("a run that answers a
    clarify gate, read back") and the real PLANNER.md writer at
    ``engine.py``'s post-clarify block (~4859-4886) — not a copy of it.

    The assertion targets the ``"<question> → <answer>"`` signature that only
    ``ClarifyEngine._merge_answers`` produces in ``explicit_constraints`` —
    proof the file reflects the MERGED context, not the context that existed
    before the clarify round ran.
    """
    from agents.execution_engine.engine import ExecutionEngine
    from app.agents.sandbox import RunSandbox

    async def _no_llm(*args, **kwargs):
        raise RuntimeError("offline test: no LLM clarify generation")

    monkeypatch.setattr("app.agents.cached_invoke.cached_invoke", _no_llm)

    ctx = ExecutionEngine()._default_planning_context(
        "Build user stories for a task-management web app."
    )
    ctx["pipeline_type"] = "user_stories"
    ctx["execution_gate"] = "CLARIFY_REQUIRED"
    ctx["missing_information"] = ["topic", "target_audience"]

    run_id = f"planner-md-clarify-{uuid.uuid4().hex[:8]}"
    result = await drive_engine_pipeline(
        "user_stories",
        model=lambda aid: ScriptedFakeChatModel(_scripts_for(aid)),
        planner_result=(ctx, "CLARIFY_REQUIRED"),
        auto_answer_clarify=True,
        run_id=run_id,
    )

    types = result.event_types()
    assert "questionnaire_ready" in types, "clarify did not trigger"
    assert "questionnaire_complete" in types, "clarify was not auto-answered"
    assert result.completed is True, f"run did not complete (error={result.error})"

    sandbox = RunSandbox("harness-user", run_id, runs_root=live_harness._RUNS_ROOT)
    planner_md = sandbox.read("PLANNER.md")
    assert planner_md is not None, "PLANNER.md was not written by the engine"
    assert "# PLANNER.md" in planner_md, "PLANNER.md missing header"
    assert " → " in planner_md, (
        "PLANNER.md should contain the clarify merge's 'question → answer' "
        "constraint line(s) that ONLY ClarifyEngine._merge_answers produces — "
        "its absence means the file reflects the PRE-clarify context"
    )


# ===========================================================================
# Row 13 — Two-pass agent output with -p{visit} suffix
# ===========================================================================


@pytest.mark.asyncio
async def test_agent_output_written_with_visit_suffix_on_multiple_passes() -> None:
    """[Row 13 / FR-030] Agent outputs with visit_count > 1 are written with
    the `-p{visit}` suffix in the filename, allowing agents to read prior pass
    outputs.

    This test verifies the code path at sandbox.py:1370 that writes agent
    outputs with the visit suffix when a step runs multiple times.
    """
    from app.agents.sandbox import write_agent_output

    # Create a temporary sandbox directory
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        from app.agents.sandbox import RunSandbox

        sandbox = RunSandbox("test-user", "multi-pass-run", runs_root=str(tmp_path))
        sandbox.ensure()

        # Write a first pass output (visit_count=0, no suffix)
        output_path_1 = write_agent_output(
            sandbox,
            index=0,
            agent_id="domain-analyst",
            name="domain-analyst-output",
            output="First analysis of the requirements.",
            task_number="",
            visit_count=0,
        )

        assert output_path_1 is not None, "First agent output write failed"
        assert (
            ".agents/01-domain-analyst.md" in output_path_1
        ), f"First output path should not have visit suffix: {output_path_1}"

        # Verify the first pass file exists and contains the output
        # (write_agent_output adds a markdown header)
        content_1 = sandbox.read(output_path_1)
        assert content_1 is not None, "First agent output was not written"
        assert (
            "First analysis of the requirements." in content_1
        ), "First agent output content mismatch"
        assert (
            "# domain-analyst-output" in content_1
        ), "First agent output missing header"

        # Write a second pass output (visit_count=1, with `-p1` suffix)
        output_path_2 = write_agent_output(
            sandbox,
            index=0,
            agent_id="domain-analyst",
            name="domain-analyst-output",
            output="Second analysis - refined understanding.",
            task_number="",
            visit_count=1,
        )

        assert output_path_2 is not None, "Second agent output write failed"
        assert (
            ".agents/01-domain-analyst-p1.md" in output_path_2
        ), f"Second output path should have -p1 suffix: {output_path_2}"

        # Verify the second pass file exists with correct content
        content_2 = sandbox.read(output_path_2)
        assert (
            "Second analysis - refined understanding." in content_2
        ), "Second agent output content mismatch"

        # Verify both files are independently readable
        content_1_reread = sandbox.read(output_path_1)
        assert (
            "First analysis of the requirements." in content_1_reread
        ), "First pass output not readable after second pass write"

        # Write a third pass with visit_count=2 (suffix `-p2`)
        output_path_3 = write_agent_output(
            sandbox,
            index=0,
            agent_id="domain-analyst",
            name="domain-analyst-output",
            output="Third analysis - final refinement.",
            task_number="",
            visit_count=2,
        )

        assert output_path_3 is not None, "Third agent output write failed"
        assert (
            ".agents/01-domain-analyst-p2.md" in output_path_3
        ), f"Third output path should have -p2 suffix: {output_path_3}"

        content_3 = sandbox.read(output_path_3)
        assert (
            "Third analysis - final refinement." in content_3
        ), "Third agent output content mismatch"

        # Verify all three passes can be read back independently
        content_1_final = sandbox.read(".agents/01-domain-analyst.md")
        content_2_final = sandbox.read(".agents/01-domain-analyst-p1.md")
        content_3_final = sandbox.read(".agents/01-domain-analyst-p2.md")

        assert content_1_final is not None, "First pass file not readable"
        assert content_2_final is not None, "Second pass file not readable"
        assert content_3_final is not None, "Third pass file not readable"


@pytest.mark.asyncio
async def test_task_loop_visit_count_distinguishes_passes() -> None:
    """[Row 13 / FR-030] When a step is part of a task loop, both task_number
    and visit_count create distinct output filenames: `-t{task}-p{visit}`.

    Verifies the naming pattern at sandbox.py:1370-1374.
    """
    from app.agents.sandbox import write_agent_output

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        from app.agents.sandbox import RunSandbox

        sandbox = RunSandbox("test-user", "task-loop-run", runs_root=str(tmp_path))
        sandbox.ensure()

        # Simulate a build loop with 2 tasks × 2 passes per task
        # Task 1, pass 1: -t1
        path_t1_p0 = write_agent_output(
            sandbox,
            index=2,  # third agent (build)
            agent_id="prototype-build",
            name="build-output",
            output="Building task 1 first pass",
            task_number="1",
            visit_count=0,
        )
        assert path_t1_p0 is not None
        assert ".agents/03-prototype-build-t1.md" in path_t1_p0

        # Task 1, pass 2: -t1-p1
        path_t1_p1 = write_agent_output(
            sandbox,
            index=2,
            agent_id="prototype-build",
            name="build-output",
            output="Building task 1 second pass",
            task_number="1",
            visit_count=1,
        )
        assert path_t1_p1 is not None
        assert ".agents/03-prototype-build-t1-p1.md" in path_t1_p1

        # Task 2, pass 1: -t2
        path_t2_p0 = write_agent_output(
            sandbox,
            index=2,
            agent_id="prototype-build",
            name="build-output",
            output="Building task 2 first pass",
            task_number="2",
            visit_count=0,
        )
        assert path_t2_p0 is not None
        assert ".agents/03-prototype-build-t2.md" in path_t2_p0

        # Task 2, pass 2: -t2-p1
        path_t2_p1 = write_agent_output(
            sandbox,
            index=2,
            agent_id="prototype-build",
            name="build-output",
            output="Building task 2 second pass",
            task_number="2",
            visit_count=1,
        )
        assert path_t2_p1 is not None
        assert ".agents/03-prototype-build-t2-p1.md" in path_t2_p1

        # Verify all four files can be read back independently
        content_t1_p0 = sandbox.read(".agents/03-prototype-build-t1.md")
        content_t1_p1 = sandbox.read(".agents/03-prototype-build-t1-p1.md")
        content_t2_p0 = sandbox.read(".agents/03-prototype-build-t2.md")
        content_t2_p1 = sandbox.read(".agents/03-prototype-build-t2-p1.md")

        assert content_t1_p0 is not None, "Task 1 pass 1 file not readable"
        assert content_t1_p1 is not None, "Task 1 pass 2 file not readable"
        assert content_t2_p0 is not None, "Task 2 pass 1 file not readable"
        assert content_t2_p1 is not None, "Task 2 pass 2 file not readable"
