"""
Tests for ``build_flat_payload``'s ``streamed_text`` materialization.

GAPS closure — Phase L row **L5** (``C-tag(v1)``), pre-documented as task **S8**
in GIT_VERSIONING_TASKS.md section 0.

Why this file exists
--------------------
``chat`` (``chat.md``), ``custom`` (``output.md``), ``user_stories``
(``user_stories.md``) and ``reverse_engineer`` (``analysis.md``) declare a
nominal deliverable filename whose bytes live in ``ectx.last_streamed`` (the
final agent's streamed output), never on disk. ``build_flat_payload`` tested
for a literal file under that name, which can never exist for a
``streamed_text`` strategy, so every such run took the
``output_unmaterializable`` fallback, degraded, and minted no ``vN`` tag —
exactly the ``L5`` live failure (``user_stories``, run
``adb7a90c-4828-4208-93bc-2492198c33e6``: ``published=degraded
reason='output_unmaterializable' tag=``).

Mirrors ``test_serialized_sandbox_payload_v3.py`` (the analogous fix for the
``serialized_sandbox`` strategy) — same helpers, same shape.

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


def _make_streamed_ectx(
    run_id: str,
    sandbox: FakeSandbox,
    *,
    deliverable_name: str = "user_stories.md",
    last_streamed: str = "# Backlog\n\n- story one\n",
    revision_ordinal: int = 1,
) -> types.SimpleNamespace:
    """An ectx whose deliverable is ``streamed_text`` under a nominal name.

    Mirrors production: the compiled deliverable declares a literal-looking
    filename that is never written to disk; the real bytes are
    ``ectx.last_streamed``, set by the engine right after the final agent's
    step completes (``engine.py`` around ``ectx.last_streamed = results[-1]…``).
    """
    ectx = _make_ectx(
        run_id,
        sandbox,
        deliverable_name=deliverable_name,
        revision_ordinal=revision_ordinal,
    )
    ectx.deliverable.strategy = "streamed_text"
    ectx.last_streamed = last_streamed
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


class TestStreamedTextPayload:
    """``streamed_text`` materializes ``ectx.last_streamed`` under the nominal name."""

    def test_last_streamed_materializes_under_the_nominal_name(
        self, tmp_path: Path
    ) -> None:
        """The declared output is ``ectx.last_streamed``, not a file literally on disk."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        from agents.execution_engine.engine import build_flat_payload  # noqa: PLC0415

        sandbox, run_id = _setup_sandbox(tmp_path)
        _plant_logs(sandbox, run_id)

        ectx = _make_streamed_ectx(run_id, sandbox)
        payload = build_flat_payload(run_id, ectx)

        assert payload.built is True
        assert payload.materialized is True, (
            "streamed_text must materialize from ectx.last_streamed — "
            "a literal file named 'user_stories.md' never exists"
        )
        assert payload.chainable is True
        assert payload.non_chainable_reason == ""
        assert ".chain/user_stories.md" in payload.allowlist

        written = (sandbox.root / ".chain" / "user_stories.md").read_text(
            encoding="utf-8"
        )
        assert written == "# Backlog\n\n- story one\n"
        # The bundle is the agent's streamed text verbatim — it must never pick
        # up this run's own staging artefacts (mirrors the serialized_sandbox
        # ordering guarantee: resolved before .chain.staging-{run_id}/ exists).
        assert "logs.jsonl" not in written
        assert "summary.md" not in written

    def test_empty_last_streamed_still_degrades_untagged(self, tmp_path: Path) -> None:
        """An empty ``ectx.last_streamed`` is not a claim — degrade, no tag.

        Mirrors ``serialized_sandbox``'s ``count > 0`` claim rule: a bundle is
        only real when it has content. Without this check an empty stream
        would silently materialize as a zero-byte file and still mint a tag.
        """
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, run_id = _setup_sandbox(tmp_path)
        _plant_logs(sandbox, run_id)

        ectx = _make_streamed_ectx(run_id, sandbox, last_streamed="")
        record = _finalize(run_id, ectx)

        assert record is not None
        assert (
            record.published_status == "degraded"
        ), f"expected degraded, got {record.published_status!r}"
        assert (
            sandbox.list_tags() == []
        ), f"unexpected tag for an empty last_streamed: {sandbox.list_tags()}"

    def test_completed_run_mints_its_tag(self, tmp_path: Path) -> None:
        """L5's C-tag(v1): a completed streamed_text run publishes + tags."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, run_id = _setup_sandbox(tmp_path)
        _plant_logs(sandbox, run_id)

        ectx = _make_streamed_ectx(run_id, sandbox)
        record = _finalize(run_id, ectx)

        assert record is not None
        assert record.published_status == "completed", (
            f"expected completed, got {record.published_status!r} "
            f"(degraded_reason={getattr(record, 'degraded_reason', None)!r})"
        )
        assert (
            "v1" in sandbox.list_tags()
        ), f"no v1 tag minted; tags={sandbox.list_tags()}"

    def test_literal_file_on_disk_wins_over_last_streamed(self, tmp_path: Path) -> None:
        """If the declared name already exists as a real file, copy it — do not
        overwrite it with ``ectx.last_streamed`` (the streamed-text fallback
        only fires when no literal file is present, same as ``serialized_sandbox``)."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        from agents.execution_engine.engine import build_flat_payload  # noqa: PLC0415

        sandbox, run_id = _setup_sandbox(tmp_path)
        (sandbox.root / "user_stories.md").write_text(
            "real file on disk", encoding="utf-8"
        )
        _plant_logs(sandbox, run_id)

        ectx = _make_streamed_ectx(run_id, sandbox, last_streamed="stale stream text")
        payload = build_flat_payload(run_id, ectx)

        assert payload.materialized is True
        written = (sandbox.root / ".chain" / "user_stories.md").read_text(
            encoding="utf-8"
        )
        assert written == "real file on disk"


# ---------------------------------------------------------------------------
# ppt strategy — B4 fix
# ---------------------------------------------------------------------------


def _make_ppt_ectx(
    run_id: str,
    sandbox: FakeSandbox,
    *,
    deliverable_name: str = "presentation.pptx",
    last_streamed: str = "<html><body><section class='slide'><h1>Slide 1</h1></section></body></html>",
    revision_ordinal: int = 1,
) -> types.SimpleNamespace:
    """An ectx whose deliverable is ``ppt`` strategy under a nominal name.

    Mirrors production: the ppt manifest declares ``strategy: ppt`` and
    ``name: presentation.pptx``.  The actual deck is ``ectx.last_streamed``
    (sanitized HTML), never on disk as a literal .pptx.
    """
    ectx = _make_ectx(
        run_id,
        sandbox,
        deliverable_name=deliverable_name,
        revision_ordinal=revision_ordinal,
    )
    ectx.deliverable.strategy = "ppt"
    ectx.last_streamed = last_streamed
    return ectx


class TestPptPayload:
    """``ppt`` strategy materializes the sanitized deck from ``ectx.last_streamed`` (B4 fix).

    Before this fix every completed ``ppt`` run degraded with
    ``output_unmaterializable`` and minted no ``vN`` tag because
    ``build_flat_payload`` only checked for a literal file on disk,
    which the ppt workflow never writes (GAPS B4 / ppt/workflow.yaml comment).
    """

    def test_ppt_materializes_from_last_streamed(self, tmp_path: Path) -> None:
        """B4 fix: ``strategy: ppt`` must materialize from ``ectx.last_streamed``
        when no literal file exists on disk, applying the carousel-sanitize
        transforms before writing."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        from agents.execution_engine.engine import build_flat_payload  # noqa: PLC0415

        sandbox, run_id = _setup_sandbox(tmp_path)
        _plant_logs(sandbox, run_id)

        deck = (
            "<html><body><section class='slide'><h1>Hello</h1></section></body></html>"
        )
        ectx = _make_ppt_ectx(run_id, sandbox, last_streamed=deck)
        payload = build_flat_payload(run_id, ectx)

        assert payload.built is True
        assert payload.materialized is True, (
            "ppt strategy must materialize from ectx.last_streamed (B4 fix) — "
            "a literal file named 'presentation.pptx' is never written to disk"
        )
        assert payload.chainable is True
        assert ".chain/presentation.pptx" in payload.allowlist

        written = (sandbox.root / ".chain" / "presentation.pptx").read_text(
            encoding="utf-8"
        )
        assert written  # sanitized deck is non-empty
        assert "logs.jsonl" not in written
        assert "summary.md" not in written

    def test_empty_ppt_stream_degrades_untagged(self, tmp_path: Path) -> None:
        """An empty ``ectx.last_streamed`` for a ppt run must not materialize —
        same empty-stream guard as ``streamed_text``."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, run_id = _setup_sandbox(tmp_path)
        _plant_logs(sandbox, run_id)

        ectx = _make_ppt_ectx(run_id, sandbox, last_streamed="")
        record = _finalize(run_id, ectx)

        assert record is not None
        assert (
            record.published_status == "degraded"
        ), f"empty ppt stream must not mint a tag; got {record.published_status!r}"
        assert sandbox.list_tags() == []

    def test_ppt_completed_run_mints_tag(self, tmp_path: Path) -> None:
        """B4 fix: a completed ppt run must publish ``completed`` and mint ``v1``."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        sandbox, run_id = _setup_sandbox(tmp_path)
        _plant_logs(sandbox, run_id)

        deck = "<html><body><section class='slide'><h1>Slide 1</h1></section></body></html>"
        ectx = _make_ppt_ectx(run_id, sandbox, last_streamed=deck)
        record = _finalize(run_id, ectx)

        assert record is not None
        assert record.published_status == "completed", (
            f"ppt run must publish completed (not {record.published_status!r}); "
            f"degraded_reason={getattr(record, 'degraded_reason', None)!r} — "
            "B4: ppt strategy must materialize from last_streamed in build_flat_payload"
        )
        assert (
            "v1" in sandbox.list_tags()
        ), f"ppt run must mint v1; tags={sandbox.list_tags()}"

    def test_literal_ppt_file_on_disk_wins_over_last_streamed(
        self, tmp_path: Path
    ) -> None:
        """If the ppt output file already exists on disk (unusual but valid),
        use it rather than last_streamed — same precedence as streamed_text."""
        if not shutil.which("git"):
            pytest.skip("git not available")

        from agents.execution_engine.engine import build_flat_payload  # noqa: PLC0415

        sandbox, run_id = _setup_sandbox(tmp_path)
        (sandbox.root / "presentation.pptx").write_text(
            "real file on disk", encoding="utf-8"
        )
        _plant_logs(sandbox, run_id)

        stale_deck = (
            "<html><body><section class='slide'><h1>Stale</h1></section></body></html>"
        )
        ectx = _make_ppt_ectx(run_id, sandbox, last_streamed=stale_deck)
        payload = build_flat_payload(run_id, ectx)

        assert payload.materialized is True
        written = (sandbox.root / ".chain" / "presentation.pptx").read_text(
            encoding="utf-8"
        )
        assert (
            written == "real file on disk"
        ), "disk file must take precedence over last_streamed for ppt strategy"
