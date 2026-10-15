"""QA-KB-056: build_flat_payload's streamed_text payload must equal the resolver output.

Cards: ISS-791 (wrapper/preamble), ISS-979 (declared .html format), ISS-980 (wrapper-only stream).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from agents.capabilities.deliverables.streamed_text import StreamedTextResolver
from agents.execution_engine.engine import build_flat_payload
from tests.agents.test_finalizer_v2 import _plant_logs, _setup_sandbox
from tests.agents.test_streamed_text_payload_v3 import (
    _finalize,
    _make_streamed_ectx,
)


def _materialize(tmp_path: Path, name: str, streamed: str):
    sandbox, run_id = _setup_sandbox(tmp_path)
    _plant_logs(sandbox, run_id)
    ectx = _make_streamed_ectx(
        run_id, sandbox, deliverable_name=name, last_streamed=streamed
    )
    build_flat_payload(run_id, ectx)
    f = sandbox.root / ".chain" / name
    written = f.read_text(encoding="utf-8") if f.is_file() else None
    return written, StreamedTextResolver().resolve(ectx), sandbox, run_id, ectx


@pytest.mark.issue("ISS-791")
def test_payload_strips_artifact_wrapper_and_preamble(tmp_path: Path) -> None:
    """ISS-791: .chain/<name> equals the resolver output, not the raw stream."""
    written, resolved, *_ = _materialize(
        tmp_path,
        "output.md",
        "Thinking...\n<artifact><!DOCTYPE html><html></html></artifact>",
    )
    assert resolved == "<!DOCTYPE html><html></html>"
    assert written == resolved


@pytest.mark.issue("ISS-979")
def test_payload_honours_declared_html_format(tmp_path: Path) -> None:
    """ISS-979: an .html-declared deliverable's payload is the rendered HTML."""
    written, resolved, *_ = _materialize(
        tmp_path, "output.html", "# Title\n\nbody text\n"
    )
    assert resolved.lstrip().lower().startswith("<!doctype html")
    assert written == resolved


@pytest.mark.issue("ISS-980")
def test_wrapper_only_stream_publishes_degraded(tmp_path: Path) -> None:
    """ISS-980: a stream that resolves to empty must not publish completed / mint v1."""
    if not shutil.which("git"):
        pytest.skip("git not available")
    sandbox, run_id = _setup_sandbox(tmp_path)
    _plant_logs(sandbox, run_id)
    ectx = _make_streamed_ectx(
        run_id,
        sandbox,
        deliverable_name="output.md",
        last_streamed="<artifact>\n</artifact>",
    )
    assert StreamedTextResolver().resolve(ectx) == ""
    record = _finalize(run_id, ectx)
    assert record.published_status == "degraded"
    assert sandbox.list_tags() == []
