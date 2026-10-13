"""tests/agents/test_pipeline_complete_status_v3.py — U2 (FR-060 / GAPS §5 AC-29,
GAPS §1 P0 #11).

Live finding (2026-09-11), run ``02b262f0``: the finalizer published
``degraded`` (``output_unmaterializable``) but ``workflow_runs.status`` and the
UI both said ``completed`` — "Done", a version pill, no tag. The frontend
(``Badge.tsx`` / ``LaneRunHeader.tsx`` / ``Sidebar.tsx``) already renders
``degraded`` correctly; it was faithfully showing a wrong backend value.

Root cause: ``_execute_impl``'s "Step 5: Pipeline complete" block already
embeds the finalizer's authoritative outcome as the ADDITIVE
``published_status`` key (Task 5.9), but the pre-existing ``status`` key —
the ONE key every downstream consumer decides ``WorkflowRun.status`` from
(``_drive_launch_to_queue`` / ``_drive_revision_to_queue`` /
``_reconcile_terminal_status`` in ``app/api/run_commands.py``, all reading
``data.get("status") == "degraded"`` off this exact event) — was set only for
two narrower cases (an unrecovered agent failure, or
``ectx.last_commit_blocked``). A finalizer degrade for any OTHER reason
(``output_unmaterializable``, a tag/ref failure, …) left ``status`` absent, so
every one of those downstream consumers took their "clean pipeline_complete"
branch and persisted "completed".

Fix (``engine.py``, the same "Step 5" block, ~6 lines): when
``_fin_record.published_status == "degraded"``, also set
``_pipeline_complete_data["status"] = "degraded"`` — never "completed" (that
key stays implicit/absent on a clean run, matching the pre-existing INV-3
byte-parity contract the characterization goldens pin).

This file drives the REAL ``_execute_impl`` end to end (the offline
``_drive`` harness — zero Bedrock cost) and stubs only ``finalize_terminal_run``
itself, so the test exercises the exact "Step 5" code under test without
depending on which finalizer-internal reason produced the degrade (the row
is explicit: "Do not change what *causes* a degrade, only that the decision
is persisted and surfaced" — the test mirrors that split). The finalizer's own
degrade-causes-no-tag behavior (``output_unmaterializable`` via
``streamed_text`` with an empty ``ectx.last_streamed``) is independently
proven end-to-end against a real git sandbox in
``test_streamed_text_payload_v3.py::test_empty_last_streamed_still_degrades_untagged``
(S8) — not re-duplicated here.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

# Importing the harness forces InMemory checkpointer + temp RUNS_ROOT before
# app.core.config loads. Keep this import first (mirrors test_cancel_paths_v3.py).
from tests.agents._scripted_model import _drive

import agents.execution_engine.engine as engine_mod
from agents.execution_engine.finalization import FinalizationRecord


def _fake_finalizer(published_status: str, candidate_status: str = "completed"):
    """A drop-in replacement for ``engine.finalize_terminal_run`` that returns a
    controlled record — isolating "what the finalizer decided" from "does that
    decision reach the terminal event", exactly the seam U2 fixes.
    """

    async def _finalize(run_id, ectx, *, candidate_status=candidate_status):
        return FinalizationRecord(
            run_id=run_id,
            owner_id="harness-user",
            workspace_id="",
            published_status=published_status,
            candidate_status=candidate_status,
        )

    return _finalize


def _pipeline_complete_events(events: list[dict]) -> list[dict]:
    return [e for e in events if e.get("type") == "pipeline_complete"]


class TestFinalizerDegradeSurfacesOnPipelineComplete:
    """U2: the finalizer's ``published_status`` must flip the SAME ``status``
    key every DB-persisting consumer already reads off ``pipeline_complete``.
    """

    @pytest.mark.asyncio
    async def test_finalizer_degrade_flips_status_key(self) -> None:
        with patch.object(
            engine_mod, "finalize_terminal_run", _fake_finalizer("degraded")
        ):
            events = await _drive("custom")

        completes = _pipeline_complete_events(events)
        assert (
            len(completes) == 1
        ), f"expected exactly 1 pipeline_complete, got {completes}"
        data = completes[0]["data"]

        assert data.get("published_status") == "degraded"
        # The load-bearing assertion: run_commands.py's _drive_launch_to_queue /
        # _drive_revision_to_queue / _reconcile_terminal_status all key off
        # data["status"], never published_status alone.
        assert data.get("status") == "degraded", (
            "a finalizer-level degrade must be visible on the SAME 'status' key "
            "_drive_launch_to_queue reads to decide WorkflowRun.status — otherwise "
            "the DB row, history badge and version pill still read 'completed' "
            "(the live defect on run 02b262f0)"
        )

    @pytest.mark.asyncio
    async def test_clean_finalize_keeps_status_key_absent_and_completed(self) -> None:
        """Control: a clean finalization must NOT regress — 'status' stays
        implicit/absent (INV-3 byte parity), and published_status is 'completed'.
        """
        with patch.object(
            engine_mod, "finalize_terminal_run", _fake_finalizer("completed")
        ):
            events = await _drive("custom")

        completes = _pipeline_complete_events(events)
        assert (
            len(completes) == 1
        ), f"expected exactly 1 pipeline_complete, got {completes}"
        data = completes[0]["data"]

        assert data.get("published_status") == "completed"
        assert "status" not in data, (
            "a clean run must never carry an explicit status key — it stays "
            "absent (the pre-existing INV-3 contract the characterization "
            "goldens pin); this proves the fix only ever SETS 'degraded', "
            "never 'completed'"
        )


def _finalizer_that_marks(**marks):
    """A fake finalizer that first sets commit-outcome flags on the ectx, as the
    real step commits would have during the run, then publishes degraded."""
    inner = _fake_finalizer("degraded")

    async def _finalize(run_id, ectx, *, candidate_status="completed"):
        for key, value in marks.items():
            setattr(ectx, key, value)
        return await inner(run_id, ectx, candidate_status=candidate_status)

    return _finalize


class TestACommitDegradeNamesItsCause:
    """Live (run 53d022e9): a degrade caused by the commit path was persisted as
    "degraded: agent(s) failed: " with an EMPTY agent list — no reason at all."""

    @pytest.mark.asyncio
    async def test_files_left_out_of_the_history_are_named(self) -> None:
        marks = {
            "commit_excluded_files": {
                "build/ui/components/button.png": "unknown binary"
            }
        }
        with patch.object(
            engine_mod, "finalize_terminal_run", _finalizer_that_marks(**marks)
        ):
            events = await _drive("custom")

        data = _pipeline_complete_events(events)[0]["data"]
        assert data.get("status") == "degraded"
        assert "build/ui/components/button.png" in (data.get("degraded_reason") or "")

    @pytest.mark.asyncio
    async def test_a_refused_commit_says_why(self) -> None:
        marks = {
            "last_commit_blocked": True,
            "last_commit_block_reason": "secret_detected",
        }
        with patch.object(
            engine_mod, "finalize_terminal_run", _finalizer_that_marks(**marks)
        ):
            events = await _drive("custom")

        data = _pipeline_complete_events(events)[0]["data"]
        assert data.get("status") == "degraded"
        assert "secret" in (data.get("degraded_reason") or "")
