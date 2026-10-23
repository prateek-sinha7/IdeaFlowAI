"""tests/unit/test_figma_ingestor_opendesign.py

Unit tests for the Phase 7 opendesign.py update: the provider must read
tokens.css and components.html from context/design/ (no-dot) for
source_type in ('figma', 'html') runs.

Zero real I/O: mocks the sandbox reader.
"""
from __future__ import annotations

import asyncio
import json

import pytest


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_ctx(source_type: str, has_tokens: bool = True, has_components: bool = True):
    """Minimal ctx with a mocked sandbox reader."""
    tokens_content = ":root { --bg: #13151f; --accent: #5b5fef; }" if has_tokens else None
    components_content = "<html><body>Components</body></html>" if has_components else None
    ds_body_val = (
        "# Design System\n:root { --bg: #13151f; }"
        if source_type != "catalog"
        else "--bg: #fff;"
    )

    class _MockSandbox:
        def read(self, relpath: str) -> str | None:
            mapping = {
                "context/design/design-system.md": ds_body_val,
                ".context/design/design-system.md": ds_body_val if source_type == "catalog" else None,
                "context/design/template/SKILL.md": "# Template\n",
                ".context/design/template/SKILL.md": None,
                "context/design/tokens.css": tokens_content,
                ".context/design/tokens.css": tokens_content if source_type == "catalog" else None,
                "context/design/components.html": components_content,
                ".context/design/components.html": components_content if source_type == "catalog" else None,
                "context/design/template/figma/frames.json": json.dumps([
                    {"index": 0, "filename": "frame-1.png", "screen": "Dashboard"}
                ]) if source_type == "figma" else None,
                ".context/design/template/figma/frames.json": None,
            }
            return mapping.get(relpath)

    class _MockRunner:
        sandbox = _MockSandbox()

        def template_injection_parts(self, _):
            return []

        def template_example(self, _):
            return None

    class _Ctx:
        od_context = {
            "source_type": source_type,
            "ds_id": "derived",
            "template_id": "custom-figma",
            "ds_body": "",
            "template_body": "# Placeholder",
        }
        runner = _MockRunner()
        current_spec_tools: set = set()
        current_spec_injects: set = {"design_system", "template"}
        build_task_number: str = ""

    return _Ctx()


@pytest.mark.unit
def test_opendesign_provider_reads_tokens_css_for_figma_run() -> None:
    """For source_type=figma, provider must emit a DS block."""
    from agents.capabilities.context_providers.opendesign import OpenDesignProvider

    ctx = _make_ctx("figma", has_tokens=True)
    blocks = _run(OpenDesignProvider().load(ctx))
    ds_keys = [k for k in blocks if "DESIGN SYSTEM" in k.upper() or "ACTIVE DESIGN" in k]
    assert len(ds_keys) >= 1, (
        "Provider must emit a DS block for figma run with design-system.md"
    )


@pytest.mark.unit
def test_opendesign_provider_figma_block_still_present() -> None:
    """FIGMA DESIGN REFERENCE block must still be emitted for figma runs."""
    from agents.capabilities.context_providers.opendesign import OpenDesignProvider

    ctx = _make_ctx("figma")
    blocks = _run(OpenDesignProvider().load(ctx))
    assert any("FIGMA DESIGN REFERENCE" in k for k in blocks), (
        "FIGMA DESIGN REFERENCE block must be present for figma run"
    )


@pytest.mark.unit
def test_opendesign_provider_catalog_run_unaffected() -> None:
    """Catalog run must not emit FIGMA DESIGN REFERENCE block."""
    from agents.capabilities.context_providers.opendesign import OpenDesignProvider

    ctx = _make_ctx("catalog")
    blocks = _run(OpenDesignProvider().load(ctx))
    assert not any("FIGMA DESIGN REFERENCE" in k for k in blocks), (
        "Catalog run must NOT emit FIGMA DESIGN REFERENCE block"
    )
