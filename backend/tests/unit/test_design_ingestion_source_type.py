"""tests/unit/test_design_ingestion_source_type.py — Phase 1 design-ingestor unit tests.

Covers source_type detection in launch_context.py, selections.json
extension in od_context_sandbox.py, and the load_figma_ingest_context()
stub in od_context.py. Zero real I/O — every sandbox is a fake in-memory
object (duck-typed on read/write). Section 6.1 of the roadmap.

Patch discipline (local imports):
  resolve_launch_od_context uses lazy local imports for compile_for_run and
  od_loader. We patch them at their DEFINITION site so the module under test
  sees the mock.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sandbox(files: dict[str, str] | None = None) -> Any:
    """Return a duck-typed in-memory sandbox with read/write/list_files methods."""
    store: dict[str, str] = dict(files or {})

    class _Sandbox:
        def write(self, path: str, content: str) -> None:
            store[path] = content

        def read(self, path: str) -> str | None:
            return store.get(path)

        def list_files(self):
            return [{"path": k} for k in store], {}

    return _Sandbox(), store


def _fake_od_context(source_type: str = "catalog", **kwargs) -> dict:
    """Minimal od_context dict for use with sandbox helpers."""
    base: dict = {
        "template_id": "web-prototype",
        "template_name": "Web Prototype",
        "ds_id": "github",
        "ds_name": "GitHub",
        "no_template": False,
        "is_design_system_required": None,
        "template_body": "## Workflow\nUse .card",
        "ds_body": ":root{--bg:#fff;}",
        "craft_block": "",
        "template_files": {},
        "ds_files": {},
        "source_type": source_type,
        "figma_frame_count": None,
    }
    base.update(kwargs)
    return base


def _resolve_with_mocks(pipeline_type, template_id, design_system_id, **kwargs):
    """Call resolve_launch_od_context with disk I/O mocked out."""
    from app.api.launch_context import resolve_launch_od_context

    fake_tmpl = {
        "id": template_id or "web-prototype",
        "name": "Web Prototype",
        "body": "## Workflow",
        "craft_required": [],
    }
    fake_ds = {"id": design_system_id or "github", "name": "GitHub", "body": ":root{}"}
    with (
        patch(
            "agents.execution_engine.engine.compile_for_run",
            return_value=SimpleNamespace(context_providers=["opendesign"]),
        ),
        patch("app.services.od_loader.get_template", return_value=fake_tmpl),
        patch("app.services.od_loader.get_design_system", return_value=fake_ds),
        patch("app.services.od_loader.get_craft_rules", return_value={}),
        patch("app.services.od_loader.get_template_files", return_value={}),
        patch("app.services.od_loader.get_design_system_files", return_value={}),
    ):
        return resolve_launch_od_context(
            pipeline_type, template_id, design_system_id, fatal=True, **kwargs
        )


# --- source_type detection tests ---


@pytest.mark.unit
def test_source_type_catalog_when_template_id_in_catalog():
    """Catalog template_id with no custom body → source_type='catalog'."""
    _, od = _resolve_with_mocks("prototype", "web-prototype", "github")
    assert od is not None
    assert od["source_type"] == "catalog"
    assert od["figma_frame_count"] is None


@pytest.mark.unit
def test_source_type_html_when_custom_template_body_set():
    """custom_template_body set → source_type='html'."""
    _, od = _resolve_with_mocks(
        "prototype",
        "custom-12345",
        "github",
        custom_template_body="<!DOCTYPE html><html><body>hi</body></html>",
    )
    assert od is not None
    assert od["source_type"] == "html"
    assert od["figma_frame_count"] is None


@pytest.mark.unit
def test_source_type_figma_when_manifest_has_image_entries():
    """figma_frame_count > 0 → source_type='figma', no od_loader call."""
    with patch("app.services.od_loader.get_template") as mock_tmpl:
        with patch(
            "agents.execution_engine.engine.compile_for_run",
            return_value=SimpleNamespace(context_providers=["opendesign"]),
        ):
            from app.api.launch_context import resolve_launch_od_context

            _, od = resolve_launch_od_context(
                "prototype_v2", None, None, fatal=True, figma_frame_count=5
            )
    mock_tmpl.assert_not_called()
    assert od is not None
    assert od["source_type"] == "figma"
    assert od["figma_frame_count"] == 5
    assert od["template_id"] == "custom-figma"


@pytest.mark.unit
def test_source_type_defaults_catalog_no_custom():
    """No custom body, no figma count → source_type='catalog'."""
    _, od = _resolve_with_mocks(
        "prototype", "web-prototype", "github", figma_frame_count=None
    )
    assert od is not None
    assert od["source_type"] == "catalog"


# --- selections.json tests ---


@pytest.mark.unit
def test_selections_json_includes_source_type_field():
    """_write_od_context_to_sandbox writes source_type into selections.json."""
    from app.services.od_context_sandbox import _write_od_context_to_sandbox

    sandbox, store = _make_sandbox()
    _write_od_context_to_sandbox(sandbox, _fake_od_context(source_type="html"))
    data = json.loads(store[".context/selections.json"])
    assert data["source_type"] == "html"


@pytest.mark.unit
def test_selections_json_includes_figma_frame_count():
    """_write_od_context_to_sandbox writes figma_frame_count into selections.json."""
    from app.services.od_context_sandbox import _write_od_context_to_sandbox

    sandbox, store = _make_sandbox()
    _write_od_context_to_sandbox(
        sandbox, _fake_od_context(source_type="figma", figma_frame_count=7)
    )
    data = json.loads(store[".context/selections.json"])
    assert data["source_type"] == "figma"
    assert data["figma_frame_count"] == 7


@pytest.mark.unit
def test_rebuild_reads_source_type_back():
    """rebuild_od_context_from_sandbox returns source_type from selections.json."""
    from app.services.od_context_sandbox import (
        _write_od_context_to_sandbox,
        rebuild_od_context_from_sandbox,
    )

    sandbox, _ = _make_sandbox()
    _write_od_context_to_sandbox(sandbox, _fake_od_context(source_type="html"))
    rebuilt = rebuild_od_context_from_sandbox(sandbox)
    assert rebuilt is not None
    assert rebuilt["source_type"] == "html"
    assert rebuilt["figma_frame_count"] is None


@pytest.mark.unit
def test_rebuild_backward_compat_no_source_type_field():
    """rebuild_od_context_from_sandbox returns None for source_type on old sandboxes."""
    from app.services.od_context_sandbox import rebuild_od_context_from_sandbox

    old_sel = json.dumps(
        {
            "template_id": "web-prototype",
            "ds_id": "github",
            "template_name": "Web Prototype",
            "ds_name": "GitHub",
            "no_template": False,
            "is_design_system_required": None,
        }
    )
    sandbox, _ = _make_sandbox({".context/selections.json": old_sel})
    rebuilt = rebuild_od_context_from_sandbox(sandbox)
    assert rebuilt is not None
    assert rebuilt.get("source_type") is None
    assert rebuilt.get("figma_frame_count") is None


# --- load_figma_ingest_context stub tests ---


@pytest.mark.unit
def test_load_figma_ingest_context_returns_correct_shape():
    """load_figma_ingest_context() returns correct keys/values for Phase 1 stub."""
    from agents.execution_engine.od_context import load_figma_ingest_context

    ctx = load_figma_ingest_context(frame_count=3)
    assert ctx["source_type"] == "figma"
    assert ctx["figma_frame_count"] == 3
    assert ctx["template_id"] == "custom-figma"
    assert ctx["ds_id"] == "derived"
    assert not ctx.get("template_body")
    assert ctx.get("template_files") == {}
    assert ctx.get("ds_files") == {}


@pytest.mark.unit
def test_load_figma_ingest_context_no_od_loader_call():
    """load_figma_ingest_context() must NOT call od_loader (no catalog lookup)."""
    from agents.execution_engine.od_context import load_figma_ingest_context

    with patch("app.services.od_loader.get_template") as mock_tmpl:
        with patch("app.services.od_loader.get_design_system") as mock_ds:
            load_figma_ingest_context(frame_count=2)
    mock_tmpl.assert_not_called()
    mock_ds.assert_not_called()
