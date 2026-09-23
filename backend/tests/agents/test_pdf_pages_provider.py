"""backend/tests/agents/test_pdf_pages_provider.py — pdf_pages input provider tests (spec 019 / T16).

Coverage:
  - A step declaring injects: [pdf_pages] receives image content blocks from .extract/
  - A step not declaring injects: [pdf_pages] receives no blocks (dormancy)
  - An absent .extract/ tree is dormant and returns []
  - The provider is registered and resolvable
  - The provider never raises; failures degrade to []
"""

from __future__ import annotations

import asyncio
import base64
import json
import pathlib
import tempfile
from types import SimpleNamespace
from unittest import mock

import pytest

from agents.capabilities import registry as registry_mod
from agents.capabilities.registry import CapabilityRegistry, _KNOWN


# ─── Fixtures ──────────────────────────────────────────────────────────────


class _MockRunner:
    """Mock runner with a sandbox."""

    def __init__(self, sandbox):
        self.sandbox = sandbox


def _create_test_image(width: int = 100, height: int = 100) -> bytes:
    """Create a minimal PNG image using PIL.

    Returns PNG bytes of the specified dimensions.
    """
    try:
        from io import BytesIO

        from PIL import Image
    except ImportError:
        # Fallback: return minimal PNG (8x8 blank)
        return base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAYAAADED76LAAAAFUlEQVQoU2NkYGD4z8DAwMBQiwEtVQEKqJz+5QAAAABJRU5ErkJggg=="
        )

    img = Image.new("RGB", (width, height), color="white")
    output = BytesIO()
    img.save(output, format="PNG")
    output.seek(0)
    return output.getvalue()


@pytest.fixture
def temp_sandbox(tmp_path):
    """Create a temporary sandbox directory."""

    class _Sandbox:
        def __init__(self, root: pathlib.Path):
            self.root = root

        def path_for(self, relpath: str) -> pathlib.Path:
            if str(relpath).startswith("/"):
                raise ValueError(f"absolute paths not allowed: {relpath}")
            resolved = (self.root / relpath).resolve()
            if not resolved.is_relative_to(self.root.resolve()):
                raise ValueError(f"path escape attempt: {relpath}")
            return resolved

    return _Sandbox(tmp_path)


@pytest.fixture
def pdf_pages_directory(temp_sandbox):
    """Create an .extract/ directory with test pages and images."""
    pdf_dir = temp_sandbox.path_for(".extract")
    slug_dir = pdf_dir / "pdf" / "test-document"
    pages_dir = slug_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    # Create manifest.json
    manifest = {
        "source": "test.pdf",
        "source_sha256": "abc123",
        "slug": "test-document",
        "page_count": 2,
        "scale": 2.0,
        "created_at": "2026-08-28T13:00:00Z",
        "pages": {
            "1": {"images": ["image-1.png", "image-2.png"], "chars": 1000},
            "2": {"images": ["image-1.png"], "chars": 500},
        },
        "totals": {"raw_images": 3, "after_merge": 3, "unique": 2},
    }
    (slug_dir / "manifest.json").write_text(json.dumps(manifest))

    # Create page 1 with two images
    page1_dir = pages_dir / "01"
    page1_dir.mkdir(exist_ok=True)
    (page1_dir / "text.md").write_text("# Page 1\n\nSome text here.")
    (page1_dir / "image-1.png").write_bytes(_create_test_image(100, 100))
    (page1_dir / "image-2.png").write_bytes(_create_test_image(200, 150))

    # Create page 2 with one image (a reference to page 1's image-1)
    page2_dir = pages_dir / "02"
    page2_dir.mkdir(exist_ok=True)
    (page2_dir / "text.md").write_text("# Page 2\n\nMore text.")
    (page2_dir / "image-1.png").write_bytes(_create_test_image(150, 120))

    return pdf_dir


# ─── Test: Provider with .pdf/ directory ──────────────────────────────────


def test_pdf_pages_provider_returns_blocks_when_pdf_directory_exists(
    pdf_pages_directory, temp_sandbox
):
    """A step declaring injects: [pdf_pages] receives image blocks."""
    from agents.capabilities.input_providers.pdf_pages import PdfPagesProvider

    runner = _MockRunner(temp_sandbox)
    ctx = SimpleNamespace(runner=runner)

    provider = PdfPagesProvider()
    assert provider.name == "pdf_pages"

    blocks = asyncio.run(provider.load(ctx))

    # Should have 3 blocks total (page 1: 2 images, page 2: 1 image)
    assert len(blocks) == 3
    assert all(b["type"] == "image" for b in blocks)
    assert all(b["source_type"] == "base64" for b in blocks)
    assert all(b["mime_type"] == "image/png" for b in blocks)
    assert all("data" in b and isinstance(b["data"], str) for b in blocks)

    # All base64 data should be decodable
    for block in blocks:
        try:
            base64.b64decode(block["data"])
        except Exception as exc:
            pytest.fail(f"Invalid base64 data: {exc}")


def test_pdf_pages_provider_preserves_page_order(pdf_pages_directory, temp_sandbox):
    """Images are returned in reading order: page 1, then page 2."""
    from agents.capabilities.input_providers.pdf_pages import PdfPagesProvider

    runner = _MockRunner(temp_sandbox)
    ctx = SimpleNamespace(runner=runner)

    provider = PdfPagesProvider()
    blocks = asyncio.run(provider.load(ctx))

    # First two blocks should be from page 1, third from page 2
    assert len(blocks) == 3
    # All should be present (order is determined by manifest/page iteration)
    assert all(b["type"] == "image" for b in blocks)


# ─── Test: Dormancy — absent .extract/ ────────────────────────────────────────


def test_pdf_pages_provider_dormant_when_pdf_directory_absent(temp_sandbox):
    """An absent .extract/ tree is dormant and returns []."""
    from agents.capabilities.input_providers.pdf_pages import PdfPagesProvider

    # temp_sandbox exists but has no .extract/ directory
    runner = _MockRunner(temp_sandbox)
    ctx = SimpleNamespace(runner=runner)

    provider = PdfPagesProvider()
    blocks = asyncio.run(provider.load(ctx))

    assert blocks == []


def test_pdf_pages_provider_dormant_when_sandbox_absent():
    """An absent sandbox/runner is dormant and returns []."""
    from agents.capabilities.input_providers.pdf_pages import PdfPagesProvider

    # ctx with no runner
    ctx = SimpleNamespace()

    provider = PdfPagesProvider()
    blocks = asyncio.run(provider.load(ctx))

    assert blocks == []


def test_pdf_pages_provider_dormant_when_manifest_missing(temp_sandbox):
    """An empty .extract/ tree with no manifest is dormant and returns []."""
    from agents.capabilities.input_providers.pdf_pages import PdfPagesProvider

    pdf_dir = temp_sandbox.path_for(".extract")
    slug_dir = pdf_dir / "pdf" / "test-document"
    slug_dir.mkdir(parents=True, exist_ok=True)
    # No manifest.json created

    runner = _MockRunner(temp_sandbox)
    ctx = SimpleNamespace(runner=runner)

    provider = PdfPagesProvider()
    blocks = asyncio.run(provider.load(ctx))

    assert blocks == []


def test_pdf_pages_provider_dormant_when_no_pages(temp_sandbox):
    """A manifest with no pages is dormant and returns []."""
    from agents.capabilities.input_providers.pdf_pages import PdfPagesProvider

    pdf_dir = temp_sandbox.path_for(".extract")
    slug_dir = pdf_dir / "pdf" / "test-document"
    slug_dir.mkdir(parents=True, exist_ok=True)

    # Create manifest with empty pages
    manifest = {
        "source": "test.pdf",
        "source_sha256": "abc123",
        "slug": "test-document",
        "page_count": 0,
        "pages": {},
        "totals": {"raw_images": 0, "after_merge": 0, "unique": 0},
    }
    (slug_dir / "manifest.json").write_text(json.dumps(manifest))

    runner = _MockRunner(temp_sandbox)
    ctx = SimpleNamespace(runner=runner)

    provider = PdfPagesProvider()
    blocks = asyncio.run(provider.load(ctx))

    assert blocks == []


# ─── Test: Registry integration ────────────────────────────────────────────


def test_pdf_pages_provider_is_registered():
    """The pdf_pages provider is registered in the capability registry."""
    registry_mod.discover()
    reg = CapabilityRegistry()
    assert reg.is_registered("input_provider", "pdf_pages") is True


def test_pdf_pages_provider_resolves():
    """The pdf_pages provider resolves and has the correct name."""
    registry_mod.discover()
    reg = CapabilityRegistry()
    impl = reg.resolve("input_provider", "pdf_pages")
    assert getattr(impl, "name", None) == "pdf_pages"


def test_pdf_pages_known_registry_contains_entry():
    """The _KNOWN registry contains the pdf_pages entry (spec 019 T9)."""
    registry_mod.discover()
    # Should contain ("input_provider", "pdf_pages")
    known_names = set(_KNOWN)
    assert ("input_provider", "pdf_pages") in known_names


# ─── Test: Error handling (never raises) ───────────────────────────────────


def test_pdf_pages_provider_handles_corrupted_manifest(temp_sandbox):
    """A corrupted manifest.json is handled gracefully; returns []."""
    from agents.capabilities.input_providers.pdf_pages import PdfPagesProvider

    pdf_dir = temp_sandbox.path_for(".extract")
    slug_dir = pdf_dir / "pdf" / "test-document"
    slug_dir.mkdir(parents=True, exist_ok=True)

    # Write invalid JSON
    (slug_dir / "manifest.json").write_text("{invalid json")

    runner = _MockRunner(temp_sandbox)
    ctx = SimpleNamespace(runner=runner)

    provider = PdfPagesProvider()
    # Should not raise; should return []
    blocks = asyncio.run(provider.load(ctx))

    assert blocks == []


def test_pdf_pages_provider_handles_missing_image_files(temp_sandbox):
    """Missing image files are skipped; returns blocks for existing files only."""
    from agents.capabilities.input_providers.pdf_pages import PdfPagesProvider

    pdf_dir = temp_sandbox.path_for(".extract")
    slug_dir = pdf_dir / "pdf" / "test-document"
    pages_dir = slug_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    # Create manifest referencing images that don't exist
    manifest = {
        "source": "test.pdf",
        "source_sha256": "abc123",
        "slug": "test-document",
        "page_count": 1,
        "pages": {
            "1": {"images": ["image-1.png", "image-2.png"], "chars": 1000},
        },
        "totals": {"raw_images": 2, "after_merge": 2, "unique": 2},
    }
    (slug_dir / "manifest.json").write_text(json.dumps(manifest))

    # Create page directory but only one image
    page1_dir = pages_dir / "01"
    page1_dir.mkdir(exist_ok=True)
    (page1_dir / "image-1.png").write_bytes(_create_test_image(100, 100))
    # image-2.png is NOT created

    runner = _MockRunner(temp_sandbox)
    ctx = SimpleNamespace(runner=runner)

    provider = PdfPagesProvider()
    # Should not raise; should return block for existing image only
    blocks = asyncio.run(provider.load(ctx))

    # Should have 1 block (only the existing image)
    assert len(blocks) == 1
    assert blocks[0]["type"] == "image"


# ─── Post-implementation audit regression (spec 019) ──────────────────────


def _add_second_document(pdf_dir, slug: str, colour_size: int, fmt: str = "pdf") -> None:
    """Materialise a second document beside the first, at .extract/{fmt}/{slug}/."""
    pages_dir = pdf_dir / fmt / slug / "pages" / "01"
    pages_dir.mkdir(parents=True, exist_ok=True)
    (pdf_dir / fmt / slug).mkdir(parents=True, exist_ok=True)
    (pdf_dir / fmt / slug / "manifest.json").write_text(
        json.dumps(
            {
                "source": f"{slug}.pdf",
                "source_sha256": "def456",
                "slug": slug,
                "page_count": 1,
                "scale": 2.0,
                "created_at": "2026-08-28T13:00:00Z",
                "pages": {"1": {"images": ["image-1.png"], "chars": 10}},
                "totals": {"raw_images": 1, "after_merge": 1, "unique": 1},
            }
        )
    )
    (pages_dir / "image-1.png").write_bytes(_create_test_image(colour_size, colour_size))


def test_pdf_pages_provider_is_deterministic_across_calls(
    pdf_pages_directory, temp_sandbox
):
    """Two materialised documents must not make the order depend on inode layout."""
    from agents.capabilities.input_providers.pdf_pages import PdfPagesProvider

    _add_second_document(pdf_pages_directory, "aaa-first-alphabetically", 64)

    ctx = SimpleNamespace(runner=_MockRunner(temp_sandbox))
    provider = PdfPagesProvider()

    first = asyncio.run(provider.load(ctx))
    second = asyncio.run(provider.load(ctx))

    assert first == second, "provider is not deterministic across calls"


def test_pdf_pages_provider_attaches_every_document(pdf_pages_directory, temp_sandbox):
    """A document the user uploaded must not be silently dropped.

    Scope is not derivable from ctx (FR-012a: providers take no per-step
    arguments). Attaching more than was needed is visible in the prompt;
    omitting a document is not.
    """
    from agents.capabilities.input_providers.pdf_pages import PdfPagesProvider

    ctx = SimpleNamespace(runner=_MockRunner(temp_sandbox))
    baseline = len(asyncio.run(PdfPagesProvider().load(ctx)))

    _add_second_document(pdf_pages_directory, "report", 64, fmt="docx")

    assert len(asyncio.run(PdfPagesProvider().load(ctx))) == baseline + 1


def test_pdf_pages_provider_crosses_format_directories(pdf_pages_directory, temp_sandbox):
    """.extract/ is two levels deep; a one-level walk finds format dirs, no manifests."""
    from agents.capabilities.input_providers.pdf_pages import PdfPagesProvider

    _add_second_document(pdf_pages_directory, "sheet", 64, fmt="xlsx")
    ctx = SimpleNamespace(runner=_MockRunner(temp_sandbox))

    assert asyncio.run(PdfPagesProvider().load(ctx)), "nothing found under .extract/{format}/"


def test_one_unreadable_document_does_not_blank_the_others(
    pdf_pages_directory, temp_sandbox
):
    """A corrupt manifest contributes nothing and never stops the rest."""
    from agents.capabilities.input_providers.pdf_pages import PdfPagesProvider

    ctx = SimpleNamespace(runner=_MockRunner(temp_sandbox))
    baseline = len(asyncio.run(PdfPagesProvider().load(ctx)))
    assert baseline > 0

    broken = pdf_pages_directory / "docx" / "broken"
    broken.mkdir(parents=True, exist_ok=True)
    (broken / "manifest.json").write_text("{ not json")

    assert len(asyncio.run(PdfPagesProvider().load(ctx))) == baseline
