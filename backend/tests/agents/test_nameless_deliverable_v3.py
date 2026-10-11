"""
Tests for the finalizer's no-declared-deliverable-name branch.

GAPS closure — Phase R row **R6** (FR-016 / Req 4 AC 4 / FR-060; exposed by U2).

Why this file exists
---------------------
``sample_wave``, ``sample_fanout`` and ``ex_playwright_smoke_test`` declare
``deliverable: {strategy: serialized_sandbox}`` with NO ``name:`` key —
Requirement 4 AC 4 makes such a workflow non-chainable BY DESIGN (no single
named output another run could chain from). ``build_flat_payload`` finds no
output basename and returns a non-chainable ``Payload``; before this fix,
``finalize_terminal_run`` treated ANY non-chainable payload as a failure and
called ``attempt.degrade(...)`` unconditionally, so a run that completed
perfectly published ``degraded``, was left untagged, and read as failed in
history. U2's fix (persisting ``published_status`` onto the run row) is what
made this newly visible.

This file proves the two branches are now distinguished:

* no name declared → the run's true candidate status is published, it is
  tagged under the normal completed rule, and the payload is marked
  non-chainable with the honest reason ``no_declared_output`` — not a
  degrade.
* a name IS declared but the bytes could not be produced → the existing
  ``output_unmaterializable`` degrade is unchanged — still degrades, still
  untagged. The genuine-defect path must not be weakened.

The sandbox/git helpers are imported from ``test_finalizer_v2.py`` rather than
duplicated — that file owns the real-git ``FakeSandbox`` fixture.

Requirements: 4 (AC 4, 8, 16), 5 (AC 15-18); FR-016 / FR-060
"""

from __future__ import annotations

import asyncio
import shutil
import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

BACKEND_ROOT = Path(__file__).parent.parent.parent  # …/backend/
sys.path.insert(0, str(BACKEND_ROOT))

from tests.agents.test_finalizer_v2 import (  # noqa: E402
    FakeSandbox,
    _make_ectx,
    _plant_logs,
    _run_git,
    _setup_sandbox,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_nameless_ectx(
    run_id: str,
    sandbox: FakeSandbox,
    *,
    revision_ordinal: int = 1,
) -> types.SimpleNamespace:
    """An ectx whose deliverable declares NO name — mirrors ``sample_wave`` /
    ``sample_fanout`` / ``ex_playwright_smoke_test``: ``strategy:
    serialized_sandbox`` with no ``name:`` key, so the compiled
    ``DeliverableSpec.name`` is ``None`` (``compiler.py``'s ``raw_name =
    raw.get("name")``).
    """
    ectx = _make_ectx(
        run_id, sandbox, deliverable_name=None, revision_ordinal=revision_ordinal
    )
    ectx.deliverable = types.SimpleNamespace(name=None, strategy="serialized_sandbox")
    return ectx


def _finalize(run_id: str, ectx: types.SimpleNamespace) -> Any:
    """Drive ``finalize_terminal_run`` with the DB stubbed out."""
    from agents.execution_engine import engine as eng  # noqa: PLC0415

    eng._finalize_terminal_run_started.discard(run_id)

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    with (
        patch("app.models.database.SessionLocal", return_value=db),
        patch("app.models.workflow.WorkflowRun", MagicMock()),
        patch("app.models.run_finalization.RunFinalization", MagicMock()),
    ):
        return asyncio.run(
            eng.finalize_terminal_run(run_id, ectx, candidate_status="completed")
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestNamelessDeliverableIsNotADegrade:
    """No declared name → non-chainable by design, never a degrade (GAPS R6)."""

    def test_nameless_run_completes_tagged_and_non_chainable(
        self, tmp_path: Path
    ) -> None:
        """A completed run with no declared deliverable name publishes
        'completed', mints its tag, and is marked non-chainable with the
        honest 'no_declared_output' reason — not degraded."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, run_id = _setup_sandbox(tmp_path)
        (sandbox.root / "hello.html").write_text("<h1>hi</h1>", encoding="utf-8")
        _plant_logs(sandbox, run_id)

        ectx = _make_nameless_ectx(run_id, sandbox)
        record = _finalize(run_id, ectx)

        assert record is not None
        assert record.published_status == "completed", (
            f"expected completed, got {record.published_status!r} "
            f"(degraded_reason={getattr(record, 'degraded_reason', None)!r})"
        )
        assert record.payload_chainable is False
        assert record.non_chainable_reason == "no_declared_output"
        assert "v1" in sandbox.list_tags(), (
            f"no v1 tag minted for a non-chainable-by-design run; "
            f"tags={sandbox.list_tags()}"
        )
        assert record.git_tag == "v1"

    def test_nameless_run_still_commits_logs_and_summary(self, tmp_path: Path) -> None:
        """.chain/logs.jsonl and .chain/summary.md are still written and
        force-staged even though there is no output file to chain from — the
        run log and summary are useful regardless of chainability (Req 4)."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, run_id = _setup_sandbox(tmp_path)
        _plant_logs(sandbox, run_id)

        ectx = _make_nameless_ectx(run_id, sandbox)
        _finalize(run_id, ectx)

        tracked = _run_git("ls-files", ".chain/", cwd=sandbox.root)
        assert ".chain/logs.jsonl" in tracked
        assert ".chain/summary.md" in tracked
        chain_status = _run_git(
            "status", "--porcelain", "--", ".chain/", cwd=sandbox.root
        )
        assert chain_status == "", f".chain/ not fully committed: {chain_status!r}"


class TestDeclaredNameStillDegradesWhenUnmaterializable:
    """A declared name whose bytes are unavailable is UNCHANGED — still
    degrades, still untagged. The genuine defect path must not weaken."""

    def test_declared_name_no_bytes_still_degrades_untagged(
        self, tmp_path: Path
    ) -> None:
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, run_id = _setup_sandbox(tmp_path)
        _plant_logs(sandbox, run_id)
        # Do NOT write output.html — it cannot be materialized.

        ectx = _make_ectx(run_id, sandbox, deliverable_name="output.html")
        record = _finalize(run_id, ectx)

        assert record is not None
        assert (
            record.published_status == "degraded"
        ), f"expected degraded, got {record.published_status!r}"
        assert record.non_chainable_reason == "output_unmaterializable"
        assert sandbox.list_tags() == [], (
            f"unexpected tag for an unmaterializable declared output: "
            f"{sandbox.list_tags()}"
        )
