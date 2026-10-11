"""tests/integration/agents/test_v2_event_producers_external.py — V2 event producer, real git.

``finalize_terminal_run`` must emit ``run_finalization_failed`` on a degraded
finalization. Split out of ``tests/unit/agents/test_phase3_cutover_verify.py``: it drives
the real finalizer against a real git sandbox (``git init`` subprocess), which the unit
I/O guard (``tests/unit/conftest.py``) correctly refuses. The documented-vocabulary
constants and the recording-queue spy stay in the unit module (three other suites import
them from there) and are imported here. The test body is byte-identical to its original.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.agents.test_phase3_cutover_verify import (
    _DOCUMENTED_EVENT_TYPES,
    _RecordingQueue,
)


class TestV2EventTypesAreEmittedByTheirProducers:
    """Forward guard for the two Sandbox-Git-Versioning-V2 event types (real-git half)."""

    def test_run_finalization_failed_is_emitted_on_a_degraded_finalization(
        self, tmp_path: Path
    ) -> None:
        """``finalize_terminal_run`` emits it when the run publishes degraded.

        Drives the real finalizer against a real git sandbox with
        ``last_commit_blocked`` set — the metadata-only snapshot degrades the
        attempt (``engine.py:1868``) and the emit site at ``engine.py:2193`` must
        announce it before the terminal event.
        """
        if not shutil.which("git"):
            pytest.skip("git not available")

        # Reuse the finalizer suite's real-git sandbox harness rather than
        # duplicating 120 lines of it here.
        from tests.agents.test_finalizer_v2 import (
            _make_ectx,
            _plant_logs,
            _plant_output,
            _setup_sandbox,
        )
        from agents.execution_engine import engine as eng

        sandbox, run_id = _setup_sandbox(tmp_path)
        _plant_output(sandbox)
        _plant_logs(sandbox, run_id)

        queue = _RecordingQueue()
        ectx = _make_ectx(run_id, sandbox)
        ectx.last_commit_blocked = True
        ectx.event_queue = queue
        eng._finalize_terminal_run_started.discard(run_id)

        with (
            patch("app.models.database.SessionLocal", side_effect=lambda: MagicMock()),
            patch("app.models.workflow.WorkflowRun", MagicMock()),
            patch("app.models.run_finalization.RunFinalization", MagicMock()),
        ):
            record = asyncio.run(
                eng.finalize_terminal_run(run_id, ectx, candidate_status="completed")
            )

        assert record is not None and record.published_status == "degraded", (
            "a blocked payload must publish degraded; got "
            f"{getattr(record, 'published_status', None)!r}"
        )

        emitted = queue.of_type("run_finalization_failed")
        assert len(emitted) == 1, (
            "a degraded finalization must emit exactly one run_finalization_failed; "
            f"queue held {[e.get('type') for e in queue.events]!r}"
        )
        assert "run_finalization_failed" in _DOCUMENTED_EVENT_TYPES

        data = emitted[0].get("data", {})
        assert set(data.keys()) == {"run_id", "reason"}, (
            "payload must stay bounded (Req 20 AC 5) — no paths, diffs, or "
            f"exception text; got {sorted(data.keys())}"
        )
        assert data["run_id"] == run_id
        assert data["reason"] == record.degraded_reason == "payload_blocked", (
            "the event's reason must be the record's bounded degraded_reason; got "
            f"event={data['reason']!r} record={record.degraded_reason!r}"
        )
