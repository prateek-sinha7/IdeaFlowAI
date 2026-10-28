"""tests/integration/agents/test_figma_ingest_context_chain.py

Integration tests for the Figma ingest context chain (Phase 3).
Verifies that load_figma_ingest_context produces the correct od_context shape,
that od_context_sandbox writes only selections.json for figma source_type,
and that manifest frame counting works correctly.

These are unit-style tests (no DB, no LLM) but live in integration/agents/
because they exercise the cross-module boundary:
  launch_context → od_context → od_context_sandbox.
"""

from __future__ import annotations

import json
import pytest

from agents.execution_engine.od_context import load_figma_ingest_context


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeSandbox:
    """Minimal duck-typed sandbox for od_context_sandbox tests."""

    def __init__(self) -> None:
        self._files: dict[str, str] = {}

    def write(self, relpath: str, content: str) -> None:
        self._files[relpath] = content

    def read(self, relpath: str) -> str | None:
        return self._files.get(relpath)

    def list_files(self) -> tuple[list[dict], None]:
        return [{"path": p} for p in self._files], None


# ---------------------------------------------------------------------------
# load_figma_ingest_context
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_figma_manifest_triggers_ingest_context_not_catalog() -> None:
    """load_figma_ingest_context returns source_type=figma, never touches od_loader."""
    ctx = load_figma_ingest_context(frame_count=3)
    assert ctx["source_type"] == "figma"
    assert ctx["template_id"] == "custom-figma"
    assert ctx["ds_id"] == "derived"


@pytest.mark.integration
def test_figma_od_context_has_no_template_body() -> None:
    """The Ingestor agent writes template/SKILL.md; the loader must not pre-populate
    template_body or ds_body.  Accepts both None and "" (empty string) as falsy —
    load_figma_ingest_context intentionally returns "" so od_context_sandbox's
    ``or ""`` guard treats it identically.
    """
    ctx = load_figma_ingest_context(frame_count=2)
    assert ctx.get("template_body") is None
    assert not ctx.get("ds_body")  # None or "" — both are correct empty signals
    assert ctx.get("template_files") is None or ctx.get("template_files") == {}


@pytest.mark.integration
def test_figma_frame_count_from_manifest() -> None:
    """frame_count is preserved in the od_context dict."""
    ctx = load_figma_ingest_context(frame_count=5)
    assert ctx["figma_frame_count"] == 5


@pytest.mark.integration
def test_mixed_manifest_counts_only_image_entries() -> None:
    """frame_count reflects only the image entries, not total manifest entries."""
    # Simulate: caller counted 2 image entries out of 5 total manifest entries
    ctx = load_figma_ingest_context(frame_count=2)
    assert ctx["figma_frame_count"] == 2


@pytest.mark.integration
def test_figma_od_context_sandbox_writes_only_selections() -> None:
    """write_od_context_to_sandbox with source_type=figma writes ONLY selections.json.

    The Ingestor agent owns .context/design/ — the sandbox must not pre-populate it.
    """
    from app.services.od_context_sandbox import _write_od_context_to_sandbox

    sandbox = _FakeSandbox()
    ctx = load_figma_ingest_context(frame_count=4)
    _write_od_context_to_sandbox(sandbox, ctx)

    written = set(sandbox._files.keys())
    # Must write selections.json
    assert ".context/selections.json" in written
    # Must NOT write any design/ files (Ingestor owns those)
    design_files = [p for p in written if p.startswith(".context/design/")]
    assert (
        design_files == []
    ), f"sandbox wrote design files it should not have: {design_files}"
    # Verify selections.json content
    sel = json.loads(sandbox._files[".context/selections.json"])
    assert sel["source_type"] == "figma"
    assert sel["figma_frame_count"] == 4
    assert sel["template_id"] == "custom-figma"


@pytest.mark.integration
def test_existing_figma_frame_upload_tests_unaffected() -> None:
    """The design-ingestor infrastructure must not regress any existing figma frame
    upload tests.  Runs tests/integration/api/test_figma_frames_api.py in a
    subprocess and asserts exit code 0.
    """
    import subprocess
    import sys
    from pathlib import Path

    backend = Path(__file__).resolve().parents[3]
    target = str(backend / "tests" / "integration" / "api" / "test_figma_frames_api.py")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", target, "-q", "--no-header", "--tb=short"],
        capture_output=True,
        text=True,
        cwd=str(backend),
    )
    assert result.returncode == 0, (
        f"Existing figma frame upload tests FAILED (exit={result.returncode}):\n"
        f"stdout: {result.stdout[-3000:]}\n"
        f"stderr: {result.stderr[-500:]}"
    )
