"""
Tests for ``build_flat_payload``'s ``serialized_sandbox`` materialization.

GAPS closure — Phase L row **L2** (``C-tag(v1,v2)``).

Why this file exists
--------------------
``deliverable.name`` is a literal on-disk basename only for the file-backed
strategies (``single_file`` / ``ppt``).  A ``serialized_sandbox`` manifest
declares a NOMINAL label for an unknown-shape output — ``custom_revision`` →
``output``, ``app_builder`` → ``app``, ``dotnet_to_azure`` → ``azure-app`` —
and its resolved bytes are the whole-sandbox ``filename:``-block bundle.

``build_flat_payload`` tested for a literal file under that label, which can
never exist, so EVERY completed ``serialized_sandbox`` run took the
``output_unmaterializable`` fallback, degraded, and minted no ``vN`` tag.  That
is the single root cause behind L2's ``C-tag(v1,v2)`` FAIL (backend.log:
``build_flat_payload: output file not found run=02b262f0-… basename='output'``
→ ``published=degraded … tag=None … reason='output_unmaterializable'``).

The sandbox/git helpers are imported from ``test_finalizer_v2.py`` rather than
duplicated — that file owns the real-git ``FakeSandbox`` fixture.

Requirements: 4 (AC 3, 4, 8, 16), 5 (AC 15-18)
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
    _setup_sandbox,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bundle_ectx(
    run_id: str,
    sandbox: FakeSandbox,
    *,
    deliverable_name: str = "output",
    revision_ordinal: int = 1,
) -> types.SimpleNamespace:
    """An ectx whose deliverable is ``serialized_sandbox`` under a nominal name.

    Mirrors production: ``ectx.deliverable`` carries the compiled strategy, and
    ``ectx.runner`` exposes the two sandbox-deliverable helpers the declared
    resolver reaches through (``kernel_services.py`` — never a direct ``app.*``
    import from the engine).
    """
    from app.agents.sandbox import (  # noqa: PLC0415
        count_sandbox_deliverables,
        serialize_sandbox_deliverable,
    )

    ectx = _make_ectx(
        run_id,
        sandbox,
        deliverable_name=deliverable_name,
        revision_ordinal=revision_ordinal,
    )
    ectx.deliverable.strategy = "serialized_sandbox"
    ectx.runner.count_sandbox_deliverables = count_sandbox_deliverables
    ectx.runner.serialize_sandbox_deliverable = serialize_sandbox_deliverable
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


class TestSerializedSandboxPayload:
    """``serialized_sandbox`` materializes its bundle under the nominal name."""

    def test_bundle_materializes_under_the_nominal_name(self, tmp_path: Path) -> None:
        """The declared output is the bundle, not a file literally named 'output'."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        from agents.execution_engine.engine import build_flat_payload  # noqa: PLC0415

        sandbox, run_id = _setup_sandbox(tmp_path)
        (sandbox.root / "hello.html").write_text("<h1>hi</h1>", encoding="utf-8")
        _plant_logs(sandbox, run_id)

        ectx = _make_bundle_ectx(run_id, sandbox)
        payload = build_flat_payload(run_id, ectx)

        assert payload.built is True
        assert payload.materialized is True, (
            "serialized_sandbox with >=1 deliverable file must materialize — "
            "a literal file named 'output' never exists"
        )
        assert payload.chainable is True
        assert payload.non_chainable_reason == ""
        assert ".chain/output" in payload.allowlist

        written = (sandbox.root / ".chain" / "output").read_text(encoding="utf-8")
        assert "```filename: hello.html" in written
        assert "<h1>hi</h1>" in written
        # The staging dir is NOT a RESERVED_PATHS prefix — the bundle must be
        # serialized before it exists, or the run's own payload recurses into it.
        assert ".chain.staging-" not in written
        assert "logs.jsonl" not in written

    def test_completed_revision_mints_its_tag(self, tmp_path: Path) -> None:
        """L2's C-tag: a completed serialized_sandbox revision publishes + tags."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, run_id = _setup_sandbox(tmp_path)
        (sandbox.root / "hello.html").write_text("<h1>hi</h1>", encoding="utf-8")
        _plant_logs(sandbox, run_id)

        ectx = _make_bundle_ectx(run_id, sandbox, revision_ordinal=2)
        record = _finalize(run_id, ectx)

        assert record is not None
        assert record.published_status == "completed", (
            f"expected completed, got {record.published_status!r} "
            f"(degraded_reason={getattr(record, 'degraded_reason', None)!r})"
        )
        assert (
            "v2" in sandbox.list_tags()
        ), f"no v2 tag minted; tags={sandbox.list_tags()}"

    def test_empty_sandbox_still_degrades_untagged(self, tmp_path: Path) -> None:
        """Zero deliverable files → the resolver does not claim → no tag (Req 4 AC 4)."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, run_id = _setup_sandbox(tmp_path)
        _plant_logs(sandbox, run_id)  # .logs/ is excluded from the deliverable walk

        ectx = _make_bundle_ectx(run_id, sandbox, revision_ordinal=2)
        record = _finalize(run_id, ectx)

        assert record is not None
        assert record.published_status == "degraded"
        assert (
            sandbox.list_tags() == []
        ), f"unexpected tag for an empty sandbox: {sandbox.list_tags()}"
