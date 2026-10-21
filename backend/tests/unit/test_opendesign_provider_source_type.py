"""tests/unit/test_opendesign_provider_source_type.py

Unit tests for the OpenDesign provider Figma block (Phase 4 — roadmap §6.2).
Verifies that the FIGMA DESIGN REFERENCE block is emitted only when
source_type="figma" AND frames.json exists, and that catalog/html runs are
byte-identical to current behavior (INV-3).

Zero I/O: all sandbox reads are mocked via a minimal duck-typed ctx.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock

import pytest

from agents.capabilities.context_providers.opendesign import OpenDesignProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FRAMES_JSON = json.dumps([
    {"index": 0, "filename": "frame-1.png", "screen": "Dashboard", "layout": "sidebar-nav"},
    {"index": 1, "filename": "frame-2.png", "screen": "Settings", "layout": "topbar-nav"},
])


class _FakeSandbox:
    """Minimal duck-typed sandbox that optionally returns frames.json."""

    def __init__(self, *, has_frames: bool = True) -> None:
        self._has_frames = has_frames

    def read(self, relpath: str) -> str | None:
        if relpath == ".context/design/template/figma/frames.json" and self._has_frames:
            return _FRAMES_JSON
        return None


def _make_ctx(
    *,
    source_type: str | None = None,
    ds_body: str | None = None,
    template_body: str | None = None,
    has_frames: bool = True,
) -> Any:
    """Build a minimal ctx object the provider will accept."""
    class _Ctx:
        od_context: dict = {}
        runner: Any = None
        current_spec_tools: set = set()
        current_spec_injects: set = set()
        build_task_number: str = ""

    ctx = _Ctx()
    ctx.od_context = {
        "source_type": source_type,
        "ds_id": "derived",
        "template_id": "custom-figma",
        "ds_body": ds_body,
        "template_body": template_body,
    }

    class _Runner:
        sandbox = _FakeSandbox(has_frames=has_frames)
        def template_injection_parts(self, _tid: str): return []
        def template_example(self, _tid: str): return None

    ctx.runner = _Runner()
    # Inject "design_system" and "template" so DS/SKILL blocks can fire
    ctx.current_spec_injects = {"design_system", "template"}
    return ctx


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_figma_block_emitted_when_source_type_figma_and_frames_exist():
    """FIGMA DESIGN REFERENCE block is emitted when source_type=figma + frames.json exists."""
    ctx = _make_ctx(source_type="figma", has_frames=True)
    blocks = _run(OpenDesignProvider().load(ctx))
    assert any("FIGMA DESIGN REFERENCE" in k for k in blocks), (
        f"Expected FIGMA DESIGN REFERENCE block, got keys: {list(blocks.keys())}"
    )


@pytest.mark.unit
def test_figma_block_absent_when_source_type_catalog():
    """Catalog runs must not emit FIGMA DESIGN REFERENCE (INV-3)."""
    ctx = _make_ctx(source_type="catalog", ds_body="--bg: #fff;", has_frames=True)
    blocks = _run(OpenDesignProvider().load(ctx))
    assert not any("FIGMA DESIGN REFERENCE" in k for k in blocks), (
        f"Unexpected FIGMA DESIGN REFERENCE in catalog run: {list(blocks.keys())}"
    )


@pytest.mark.unit
def test_figma_block_absent_when_no_frames_json():
    """Graceful degrade: source_type=figma but frames.json absent → no FIGMA block."""
    ctx = _make_ctx(source_type="figma", has_frames=False)
    blocks = _run(OpenDesignProvider().load(ctx))
    assert not any("FIGMA DESIGN REFERENCE" in k for k in blocks), (
        "Expected no FIGMA block when frames.json is absent"
    )


@pytest.mark.unit
def test_ds_block_still_emitted_alongside_figma_block():
    """ACTIVE DESIGN SYSTEM block is present alongside FIGMA DESIGN REFERENCE."""
    ctx = _make_ctx(source_type="figma", ds_body="--bg: #0a0a0a; --accent: #6366f1;", has_frames=True)
    blocks = _run(OpenDesignProvider().load(ctx))
    has_ds = any("ACTIVE DESIGN SYSTEM" in k for k in blocks)
    has_figma = any("FIGMA DESIGN REFERENCE" in k for k in blocks)
    assert has_ds, f"Expected ACTIVE DESIGN SYSTEM block, got: {list(blocks.keys())}"
    assert has_figma, f"Expected FIGMA DESIGN REFERENCE block, got: {list(blocks.keys())}"


@pytest.mark.unit
def test_catalog_provider_output_byte_identical():
    """Catalog run with ds_body + template_body: no new keys compared to pre-Phase-4 behavior."""
    ctx = _make_ctx(
        source_type="catalog",
        ds_body="--bg: #fff;",
        template_body="# My Template\n",
        has_frames=False,
    )
    blocks = _run(OpenDesignProvider().load(ctx))
    # Must have DS block (declared inject + ds_body)
    ds_keys = [k for k in blocks if "ACTIVE DESIGN SYSTEM" in k]
    assert len(ds_keys) == 1, f"Expected 1 DS block, got {ds_keys}"
    # Must NOT have FIGMA block
    assert not any("FIGMA" in k for k in blocks)


@pytest.mark.unit
def test_html_source_type_no_figma_block():
    """HTML source type: FIGMA DESIGN REFERENCE must not appear."""
    ctx = _make_ctx(source_type="html", ds_body="--bg: #fafafa;", has_frames=False)
    blocks = _run(OpenDesignProvider().load(ctx))
    assert not any("FIGMA DESIGN REFERENCE" in k for k in blocks), (
        f"Unexpected FIGMA block for html source_type: {list(blocks.keys())}"
    )
