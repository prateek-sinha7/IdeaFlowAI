"""tests/integration/api/test_design_ingestor_sandbox.py — Phase 1 sandbox integration tests.

Tests the selections.json extension for catalog/html/figma source types, the
context_already_present() guard for the inheritance rule, and the
rebuild_od_context_from_sandbox() round-trip for figma sandboxes.
Section 6.3 of the roadmap.

Uses tmp_path for real file I/O via the duck-typed sandbox; no DB, no Bedrock.
"""

from __future__ import annotations

import json
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_disk_sandbox(tmp_path) -> Any:
    """Return a duck-typed sandbox backed by real files in tmp_path."""

    class _DiskSandbox:
        def write(self, relpath: str, content: str) -> None:
            full = tmp_path / relpath
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding="utf-8")

        def read(self, relpath: str) -> str | None:
            full = tmp_path / relpath
            if full.is_file():
                return full.read_text(encoding="utf-8")
            return None

        def list_files(self):
            entries = []
            for p in tmp_path.rglob("*"):
                if p.is_file():
                    rel = str(p.relative_to(tmp_path)).replace("\\", "/")
                    entries.append({"path": f"./{rel}"})
            return entries, {}

    return _DiskSandbox()


def _catalog_od_context() -> dict:
    return {
        "template_id": "web-prototype",
        "template_name": "Web Prototype",
        "ds_id": "github",
        "ds_name": "GitHub",
        "no_template": False,
        "is_design_system_required": None,
        "template_body": "## Workflow\nUse .card and .grid classes.",
        "ds_body": ":root{--bg:#fff;--fg:#111;}",
        "craft_block": "",
        "template_files": {"example.html": "<html></html>"},
        "ds_files": {},
        "source_type": "catalog",
        "figma_frame_count": None,
    }


def _html_od_context() -> dict:
    return {
        "template_id": "custom-12345",
        "template_name": "Custom HTML Upload",
        "ds_id": "github",
        "ds_name": "GitHub",
        "no_template": False,
        "is_design_system_required": None,
        "template_body": "# Custom Template\n<html>...",
        "ds_body": ":root{--bg:#fff;}",
        "craft_block": "",
        "template_files": {},
        "ds_files": {},
        "source_type": "html",
        "figma_frame_count": None,
    }


def _figma_od_context(frame_count: int = 3) -> dict:
    return {
        "template_id": "custom-figma",
        "template_name": f"Figma Upload ({frame_count} screens)",
        "ds_id": "derived",
        "ds_name": "Derived from Figma",
        "no_template": False,
        "is_design_system_required": None,
        "template_body": None,
        "ds_body": "",
        "craft_block": "",
        "template_files": {},
        "ds_files": {},
        "source_type": "figma",
        "figma_frame_count": frame_count,
    }


# ---------------------------------------------------------------------------
# Catalog sandbox write is unchanged
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_catalog_sandbox_write_unchanged(tmp_path):
    """Catalog od_context writes the full .context/ layout (unchanged behavior)."""
    from app.services.od_context_sandbox import _write_od_context_to_sandbox

    sandbox = _make_disk_sandbox(tmp_path)
    _write_od_context_to_sandbox(sandbox, _catalog_od_context())

    selections_path = tmp_path / ".context" / "selections.json"
    assert selections_path.exists()
    data = json.loads(selections_path.read_text())
    assert data["template_id"] == "web-prototype"
    assert data["source_type"] == "catalog"
    assert data["figma_frame_count"] is None
    # Existing files still written
    assert (tmp_path / ".context" / "design" / "design-system.md").exists()
    assert (tmp_path / ".context" / "design" / "template" / "example.html").exists()


# ---------------------------------------------------------------------------
# HTML source_type written to selections.json
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_html_source_type_written_to_selections_json(tmp_path):
    """HTML source type is written to selections.json."""
    from app.services.od_context_sandbox import _write_od_context_to_sandbox

    sandbox = _make_disk_sandbox(tmp_path)
    _write_od_context_to_sandbox(sandbox, _html_od_context())

    data = json.loads((tmp_path / ".context" / "selections.json").read_text())
    assert data["source_type"] == "html"
    assert data["figma_frame_count"] is None


# ---------------------------------------------------------------------------
# Figma source_type written to selections.json
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_figma_source_type_written_to_selections_json(tmp_path):
    """Figma source type and frame count written to selections.json."""
    from app.services.od_context_sandbox import _write_od_context_to_sandbox

    sandbox = _make_disk_sandbox(tmp_path)
    _write_od_context_to_sandbox(sandbox, _figma_od_context(frame_count=5))

    data = json.loads((tmp_path / ".context" / "selections.json").read_text())
    assert data["source_type"] == "figma"
    assert data["figma_frame_count"] == 5


# ---------------------------------------------------------------------------
# context_already_present before and after write
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_context_already_present_false_before_ingestor(tmp_path):
    """context_already_present() returns False when selections.json is absent."""
    from app.services.od_context_sandbox import context_already_present

    sandbox = _make_disk_sandbox(tmp_path)
    # Nothing written yet
    assert context_already_present(sandbox) is False


@pytest.mark.integration
def test_context_already_present_true_after_selections_written(tmp_path):
    """context_already_present() returns True after write_od_context_to_sandbox."""
    from app.services.od_context_sandbox import (
        _write_od_context_to_sandbox,
        context_already_present,
    )

    sandbox = _make_disk_sandbox(tmp_path)
    _write_od_context_to_sandbox(sandbox, _figma_od_context())
    assert context_already_present(sandbox) is True


# ---------------------------------------------------------------------------
# Revision run does not overwrite figma context
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_revision_run_does_not_overwrite_figma_context(tmp_path):
    """write_od_context_to_sandbox skips when context already present (revision guard)."""
    from app.services.od_context_sandbox import write_od_context_to_sandbox

    sandbox = _make_disk_sandbox(tmp_path)
    # First write — figma run
    write_od_context_to_sandbox(sandbox, _figma_od_context(frame_count=3))

    # Second write — simulate revision with different od_context, no explicit selection
    revision_ctx = _catalog_od_context()
    write_od_context_to_sandbox(sandbox, revision_ctx, explicit_selection=False)

    # The original figma selections.json must be preserved
    data = json.loads((tmp_path / ".context" / "selections.json").read_text())
    assert data["source_type"] == "figma"
    assert data["template_id"] == "custom-figma"


# ---------------------------------------------------------------------------
# rebuild_od_context_from_sandbox round-trip for figma
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_rebuild_od_context_from_figma_sandbox(tmp_path):
    """rebuild_od_context_from_sandbox correctly reads source_type='figma' back."""
    from app.services.od_context_sandbox import (
        _write_od_context_to_sandbox,
        rebuild_od_context_from_sandbox,
    )

    sandbox = _make_disk_sandbox(tmp_path)
    _write_od_context_to_sandbox(sandbox, _figma_od_context(frame_count=4))

    rebuilt = rebuild_od_context_from_sandbox(sandbox)
    assert rebuilt is not None
    assert rebuilt["source_type"] == "figma"
    assert rebuilt["figma_frame_count"] == 4
    assert rebuilt["template_id"] == "custom-figma"


# ---------------------------------------------------------------------------
# Figma sandbox writes only selections.json (minimal write for Phase 1)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_figma_od_context_sandbox_writes_only_selections(tmp_path):
    """Figma od_context with empty body fields writes only selections.json.

    Phase 1: the minimal figma od_context has empty template_body/ds_body/
    template_files/ds_files — the existing write guards skip those, so only
    selections.json is written. The Ingestor agent (Phase 3) owns the design
    files.
    """
    from app.services.od_context_sandbox import _write_od_context_to_sandbox

    sandbox = _make_disk_sandbox(tmp_path)
    _write_od_context_to_sandbox(sandbox, _figma_od_context())

    # Only selections.json should exist
    context_dir = tmp_path / ".context"
    written_files = [
        str(p.relative_to(tmp_path)).replace("\\", "/")
        for p in context_dir.rglob("*")
        if p.is_file()
    ]
    assert written_files == [".context/selections.json"]
