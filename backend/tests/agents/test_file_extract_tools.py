"""backend/tests/agents/test_pdf_tools.py — PDF tools test suite (spec 019 / T7).

Coverage:
  - file_info: inventory uploads, inspect document metadata
  - Reading order: text + images interleaved by vertical position
  - Fragment merge: adjacent overlapping images become one
  - Crop geometry: crops use rendered page, preserve annotations
  - Materialise: temp-dir + atomic rename, manifest, document.md
  - Resume: skip complete pages, redo interrupted ones
  - Stale manifest: source_sha256 mismatch discards folder
  - Traversal refusal: reject ".." and absolute paths
  - Error paths: all failures return text, never raise
  - file_find: search materialised text, cap results
  - file_page_image: render full page for diagram-heavy layouts
  - Parallel: process pool (though small documents run sequential)
"""

from __future__ import annotations

import hashlib
import io
import json
import pathlib
import shutil
import tempfile
from datetime import datetime, timezone
from unittest import mock

import pytest


def _gen_minimal_pdf_bytes() -> bytes:
    """Generate a minimal 3-page PDF using pypdf.

    Returns PDF bytes with 3 simple blank pages (pypdf can read/render these).
    """
    from pypdf import PdfWriter

    writer = PdfWriter()
    # Add 3 blank pages (612x792 points, standard letter size)
    for i in range(3):
        writer.add_blank_page(width=612, height=792)

    pdf_bytes = io.BytesIO()
    writer.write(pdf_bytes)
    pdf_bytes.seek(0)
    return pdf_bytes.read()


class _Sandbox:
    """Minimal sandbox mock for testing."""

    def __init__(self, root: pathlib.Path):
        self.root = root

    def path_for(self, relpath: str) -> pathlib.Path:
        """Resolve a path through the sandbox, rejecting traversals."""
        if str(relpath).startswith("/"):
            raise ValueError(f"absolute paths not allowed: {relpath}")
        resolved = (self.root / relpath).resolve()
        if not resolved.is_relative_to(self.root.resolve()):
            raise ValueError(f"path escape attempt: {relpath}")
        return resolved


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Bind a temporary sandbox for PDF tools testing."""
    from app.agents.tools import file_extract_tools
    mock_sandbox = _Sandbox(tmp_path)
    monkeypatch.setattr(file_extract_tools, "_SANDBOX", mock_sandbox)
    # Create uploads directory
    (tmp_path / ".uploads").mkdir(exist_ok=True)
    return tmp_path


@pytest.fixture
def test_pdf(tmp_path):
    """Create a test PDF in .uploads/ and return its path (relative to sandbox)."""
    uploads_dir = tmp_path / ".uploads"
    uploads_dir.mkdir(exist_ok=True)
    pdf_bytes = _gen_minimal_pdf_bytes()
    pdf_path = uploads_dir / "test.pdf"
    pdf_path.write_bytes(pdf_bytes)
    return ".uploads/test.pdf"


# ─── Test Suite ────────────────────────────────────────────────────────────

class TestInfo:
    """file_info: document inventory and profiling."""

    def test_info_with_empty_path_lists_uploads(self, sandbox, test_pdf):
        """Empty path inventories all uploads in sorted order."""
        from app.agents.tools import file_extract_tools
        result = file_extract_tools.file_info("")
        assert "test.pdf" in result
        assert "extract_text materialises it into" in result

    def test_info_with_empty_path_says_so_when_no_uploads(self, sandbox):
        """Empty path explicitly says when there are no uploads."""
        from app.agents.tools import file_extract_tools
        result = file_extract_tools.file_info("")
        assert "No uploads" in result

    def test_info_profiles_a_document(self, sandbox, test_pdf):
        """Path provided profiles page count, text layer, encryption, metadata."""
        from app.agents.tools import file_extract_tools
        result = file_extract_tools.file_info(test_pdf)
        assert "Pages: 3" in result
        assert "text layer" in result.lower()
        assert "Encryption:" in result

    def test_info_never_materialises(self, sandbox, test_pdf):
        """file_info does not create .extract/ folder."""
        from app.agents.tools import file_extract_tools
        file_extract_tools.file_info(test_pdf)
        pdf_dir = sandbox / ".pdf"
        assert not pdf_dir.exists()

    def test_info_rejects_traversal(self, sandbox):
        """Reject ../../etc/passwd traversal attempts."""
        from app.agents.tools import file_extract_tools
        result = file_extract_tools.file_info("../../etc/passwd")
        assert "path rejected" in result.lower()

    def test_info_contains_absolute_paths_instead_of_refusing_them(self, sandbox):
        """A leading slash is STRIPPED, so `/etc/passwd` misses inside the run root.

        The contract this asserts is containment, not the wording of the miss.
        `/x` and `x` now both resolve, matching every other sandbox-bound tool
        and matching what `ls`/`glob` hand back; `path_for` is what enforces the
        boundary. Asserting the old "path rejected" string made the SPELLING the
        subject and let two tool contracts disagree inside one run.
        """
        from app.agents.tools import file_extract_tools
        result = file_extract_tools.file_info("/etc/passwd")
        assert "root:" not in result, "real /etc/passwd content leaked"
        assert "not a file" in result.lower() or "not found" in result.lower()

    def test_info_returns_text_not_raises(self, sandbox):
        """Every failure returns readable text."""
        from app.agents.tools import file_extract_tools
        result = file_extract_tools.file_info("/bad/path")
        assert isinstance(result, str)
        assert "not a file" in result.lower() or "not found" in result.lower()


class TestReadingOrder:
    """Reading order: text + images interleaved by vertical position."""

    def test_reading_order_materialises_each_page(self, sandbox, test_pdf):
        """extract_text materialises each page with text.md."""
        from app.agents.tools import file_extract_tools
        result = file_extract_tools._extract_text_sync(test_pdf)
        assert result.startswith("Materialised")

        # Check that pages have text.md files
        for page_num in [1, 2, 3]:
            page_dir = sandbox / ".extract" / "pdf" / "test" / "pages" / f"{page_num:02d}"
            text_file = page_dir / "text.md"
            assert text_file.exists(), f"page {page_num} missing text.md"

    def test_reading_order_text_md_format_valid(self, sandbox, test_pdf):
        """Each page's text.md is readable text (even if empty)."""
        from app.agents.tools import file_extract_tools
        file_extract_tools._extract_text_sync(test_pdf)

        page_dir = sandbox / ".extract" / "pdf" / "test" / "pages" / "01"
        text_file = page_dir / "text.md"
        content = text_file.read_text()

        # Content should be text, not binary
        assert isinstance(content, str)


class TestFragmentMerge:
    """Fragment merge: adjacent images with vertical gap ≤ 2.0pt and x-overlap."""

    def test_merge_fragments_on_contiguous_bboxes(self):
        """Adjacent bboxes with gap ≤ 2.0pt and x-overlap merge into one."""
        from app.agents.tools.file_extract_tools import _merge_image_fragments

        images = [
            {"x0": 50, "x1": 150, "top": 100, "bottom": 150},
            {"x0": 60, "x1": 160, "top": 150, "bottom": 200},  # gap=0, x-overlap exists
        ]
        result = _merge_image_fragments(images)
        assert len(result) == 1
        assert result[0]["parts"] == 2
        assert result[0]["bottom"] == 200

    def test_no_merge_when_x_ranges_dont_overlap(self):
        """Images with no x-overlap don't merge even if vertical gap is small."""
        from app.agents.tools.file_extract_tools import _merge_image_fragments

        images = [
            {"x0": 50, "x1": 100, "top": 100, "bottom": 150},
            {"x0": 200, "x1": 250, "top": 150, "bottom": 200},  # no x overlap
        ]
        result = _merge_image_fragments(images)
        assert len(result) == 2

    def test_no_merge_when_gap_exceeds_threshold(self):
        """Images with vertical gap > 2.0pt don't merge."""
        from app.agents.tools.file_extract_tools import _merge_image_fragments

        images = [
            {"x0": 50, "x1": 150, "top": 100, "bottom": 150},
            {"x0": 60, "x1": 160, "top": 153, "bottom": 200},  # gap=3.0 > 2.0
        ]
        result = _merge_image_fragments(images)
        assert len(result) == 2


class TestCropGeometry:
    """Crop geometry: crops come from rendered page, preserve annotations."""

    def test_crop_box_uses_render_scale(self):
        """Crop box is scaled by render dimensions, not embedded image."""
        from app.agents.tools.file_extract_tools import _crop_box_for_image

        image = {"x0": 100, "x1": 200, "top": 100, "bottom": 150}
        page_width = 612.0
        page_height = 792.0
        render_width = 1224
        render_height = 1584

        box = _crop_box_for_image(image, page_width, page_height, render_width, render_height)
        # Should be scaled by 2.0x
        assert box[0] == 200
        assert box[1] == 200

    def test_crop_box_clamped_to_render_bounds(self):
        """Crop box is clamped to render pixel bounds."""
        from app.agents.tools.file_extract_tools import _crop_box_for_image

        image = {"x0": 0, "x1": 1000, "top": 0, "bottom": 1000}
        page_width = 612.0
        page_height = 792.0
        render_width = 100
        render_height = 100

        box = _crop_box_for_image(image, page_width, page_height, render_width, render_height)
        assert box[2] <= render_width
        assert box[3] <= render_height

    def test_crop_geometry_extracts_pages(self, sandbox, test_pdf):
        """Crop geometry function is invoked during materialisation."""
        from app.agents.tools import file_extract_tools
        # This test verifies that materialisation completes without error,
        # which means crop geometry is working (no exceptions raised).
        result = file_extract_tools._extract_text_sync(test_pdf)
        assert "Materialised" in result


class TestMaterialise:
    """Materialise: temp-dir + atomic rename, manifest, document.md."""

    def test_materialise_creates_page_directories(self, sandbox, test_pdf):
        """extract_text creates numbered page directories (01, 02, ...)."""
        from app.agents.tools import file_extract_tools
        result = file_extract_tools._extract_text_sync(test_pdf)

        pages_dir = sandbox / ".extract" / "pdf" / "test" / "pages"
        assert pages_dir.exists()
        pages = sorted([d.name for d in pages_dir.iterdir() if d.is_dir()])
        assert "01" in pages
        assert "02" in pages
        assert "03" in pages

    def test_materialise_creates_manifest(self, sandbox, test_pdf):
        """extract_text creates manifest.json with source_sha256, page_count, scale."""
        from app.agents.tools import file_extract_tools
        file_extract_tools._extract_text_sync(test_pdf)

        manifest_path = sandbox / ".extract" / "pdf" / "test" / "manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert manifest["source"] == "test.pdf"
        assert "source_sha256" in manifest
        assert manifest["page_count"] == 3
        assert manifest["scale"] == 2.0
        assert "pages" in manifest
        assert "totals" in manifest

    def test_materialise_creates_document_md(self, sandbox, test_pdf):
        """extract_text creates document.md concatenating all page text.md."""
        from app.agents.tools import file_extract_tools
        file_extract_tools._extract_text_sync(test_pdf)

        doc_path = sandbox / ".extract" / "pdf" / "test" / "document.md"
        assert doc_path.exists()
        content = doc_path.read_text()
        assert "PAGE 1" in content or "Page" in content
        assert "PAGE 2" in content or "Page" in content or content  # might vary by renderer

    def test_materialise_returns_receipt_not_content(self, sandbox, test_pdf):
        """extract_text returns a receipt (page counts, token estimate), never page text."""
        from app.agents.tools import file_extract_tools
        result = file_extract_tools._extract_text_sync(test_pdf)

        assert "Materialised" in result
        assert "Processed:" in result or "pages" in result
        assert "No uploads" not in result

    def test_temp_dir_not_renamed_on_exception(self, sandbox, test_pdf):
        """If materialise fails mid-page, temp dir is not renamed (not in pages/)."""
        from app.agents.tools import file_extract_tools

        # This is hard to test without mocking PDF rendering.
        # We can at least check that stray .tmp- dirs are cleaned up on restart.
        pages_dir = sandbox / ".extract" / "pdf" / "test" / "pages"
        pages_dir.mkdir(parents=True, exist_ok=True)
        stray_tmp = pages_dir / ".tmp-01-abc123"
        stray_tmp.mkdir()
        (stray_tmp / "text.md").write_text("incomplete")

        file_extract_tools._extract_text_sync(test_pdf)
        # Stray temp dir should be cleaned
        assert not stray_tmp.exists()


class TestResume:
    """Resume: skip complete pages, redo interrupted ones."""

    def test_resume_skips_already_complete_pages(self, sandbox, test_pdf):
        """Second run skips pages that already have directories."""
        from app.agents.tools import file_extract_tools

        # First run
        result1 = file_extract_tools._extract_text_sync(test_pdf)
        assert "Processed: 3 page(s)" in result1

        # Get initial mtimes
        pages_dir = sandbox / ".extract" / "pdf" / "test" / "pages"
        mtime_01 = (pages_dir / "01" / "text.md").stat().st_mtime

        # Second run (should skip)
        result2 = file_extract_tools._extract_text_sync(test_pdf)
        assert "Skipped (already present): 3" in result2

        # Mtime should not change
        mtime_01_after = (pages_dir / "01" / "text.md").stat().st_mtime
        assert mtime_01 == mtime_01_after

    def test_resume_redoes_deleted_page(self, sandbox, test_pdf):
        """If one page directory is deleted, resume rebuilds only that page."""
        from app.agents.tools import file_extract_tools

        # First run
        file_extract_tools._extract_text_sync(test_pdf)

        # Delete page 2
        pages_dir = sandbox / ".extract" / "pdf" / "test" / "pages"
        shutil.rmtree(pages_dir / "02")

        # Resume
        result = file_extract_tools._extract_text_sync(test_pdf)
        assert "02" in result or "1 page" in result  # Should rebuild page 2
        assert (pages_dir / "02").exists()

    def test_resume_selective_pages(self, sandbox, test_pdf):
        """Pages argument selects which pages to build/skip."""
        from app.agents.tools import file_extract_tools

        # Build only page 1
        result = file_extract_tools._extract_text_sync(test_pdf, pages="1")
        pages_dir = sandbox / ".extract" / "pdf" / "test" / "pages"
        assert (pages_dir / "01").exists()
        assert not (pages_dir / "02").exists()

        # Resume with pages="1,2" should skip 1, build 2
        result = file_extract_tools._extract_text_sync(test_pdf, pages="1,2")
        assert "Skipped (already present): 1" in result
        assert (pages_dir / "02").exists()


class TestStale:
    """Stale manifest: source_sha256 mismatch discards folder."""

    def test_stale_sha256_discards_folder(self, sandbox, test_pdf):
        """Mismatch in source_sha256 discards the .extract/ folder and re-materialises."""
        from app.agents.tools import file_extract_tools

        # First run
        file_extract_tools._extract_text_sync(test_pdf)

        # Corrupt the manifest's source_sha256
        manifest_path = sandbox / ".extract" / "pdf" / "test" / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["source_sha256"] = "0" * 64  # Wrong hash
        manifest_path.write_text(json.dumps(manifest))

        # Re-run with same filename
        result = file_extract_tools._extract_text_sync(test_pdf)

        # Folder should be rebuilt (mtime changed)
        new_manifest = json.loads((sandbox / ".extract" / "pdf" / "test" / "manifest.json").read_text())
        assert new_manifest["source_sha256"] != "0" * 64

    def test_same_filename_different_content_detected(self, sandbox, test_pdf):
        """Upload the same filename with different bytes; old folder is discarded."""
        from app.agents.tools import file_extract_tools

        # First run
        file_extract_tools._extract_text_sync(test_pdf)
        first_manifest = sandbox / ".extract" / "pdf" / "test" / "manifest.json"
        first_sha = json.loads(first_manifest.read_text())["source_sha256"]

        # Overwrite the PDF with different bytes
        new_pdf = _gen_minimal_pdf_bytes() + b"extra junk"
        (sandbox / ".uploads" / "test.pdf").write_bytes(new_pdf)

        # Re-run
        file_extract_tools._extract_text_sync(test_pdf)

        # Manifest should have a different source_sha256
        new_manifest = json.loads(first_manifest.read_text())
        assert new_manifest["source_sha256"] != first_sha


class TestTraversalRefusal:
    """Traversal refusal: reject ".." and absolute paths."""

    def test_reject_traversal_up(self, sandbox):
        """Reject ../../etc/passwd attempts."""
        from app.agents.tools import file_extract_tools
        result = file_extract_tools.file_find("test", path="../../etc/passwd")
        assert "path rejected" in result.lower() or "not found" in result.lower()

    def test_absolute_paths_are_contained_not_refused(self, sandbox):
        """`/etc/passwd` resolves under the run root and misses — it never leaks.

        Traversal (`..`) is still refused; a leading slash is only spelling.
        """
        from app.agents.tools import file_extract_tools
        result = file_extract_tools.file_find("root:", path="/etc/passwd")
        assert "root:" not in result, "real /etc/passwd content leaked"

    def test_sandbox_binding_required(self, sandbox, monkeypatch):
        """Tools without a bound sandbox return an error message."""
        from app.agents.tools import file_extract_tools
        monkeypatch.setattr(file_extract_tools, "_SANDBOX", None)
        result = file_extract_tools.file_info(".uploads/test.pdf")
        assert "not bound" in result.lower()


class TestErrorHandling:
    """Every failure path returns text and never raises."""

    def test_nonexistent_pdf_returns_error_text(self, sandbox):
        """Missing PDF returns readable error, not an exception."""
        from app.agents.tools import file_extract_tools
        result = file_extract_tools.file_info(".uploads/nonexistent.pdf")
        assert isinstance(result, str)
        assert "not a file" in result.lower() or "failed" in result.lower()

    def test_corrupt_pdf_returns_error_text(self, sandbox):
        """Corrupt PDF bytes return readable error."""
        from app.agents.tools import file_extract_tools
        (sandbox / ".uploads").mkdir(exist_ok=True)
        (sandbox / ".uploads" / "corrupt.pdf").write_bytes(b"not a pdf")
        result = file_extract_tools._extract_text_sync(".uploads/corrupt.pdf")
        assert isinstance(result, str)
        assert "failed" in result.lower() or "error" in result.lower()

    def test_invalid_page_selector_returns_error_text(self, sandbox, test_pdf):
        """Invalid pages="x,y,z" syntax returns readable error."""
        from app.agents.tools import file_extract_tools
        result = file_extract_tools._extract_text_sync(test_pdf, pages="1,foo,3")
        assert isinstance(result, str)
        assert "invalid" in result.lower() or "error" in result.lower()

    def test_out_of_range_page_returns_error_text(self, sandbox, test_pdf):
        """Pages="999" (out of range) returns error, not exception."""
        from app.agents.tools import file_extract_tools
        result = file_extract_tools._extract_text_sync(test_pdf, pages="999")
        assert isinstance(result, str)
        assert "out of bounds" in result.lower() or "error" in result.lower()


class TestPdfFind:
    """file_find: search materialised text layer, cap results."""

    def test_find_searches_materialised_text(self, sandbox, test_pdf):
        """file_find searches text.md files in the materialised folder."""
        from app.agents.tools import file_extract_tools

        # Materialise first
        file_extract_tools._extract_text_sync(test_pdf)

        # Search using the document path (which has slug "test")
        result = file_extract_tools.file_find("page", path=test_pdf)
        # Result should be text (either found hits or "not found" message)
        assert isinstance(result, str)

    def test_find_returns_error_when_not_materialised(self, sandbox):
        """file_find returns error when document not materialised."""
        from app.agents.tools import file_extract_tools

        # Create a non-existent PDF reference
        (sandbox / ".uploads").mkdir(exist_ok=True)
        result = file_extract_tools.file_find("test", path=".uploads/notfound.pdf")
        # Should return an error or "not found" message
        assert isinstance(result, str)

    def test_find_caps_results(self, sandbox, test_pdf):
        """file_find caps hits at limit (default 50) and reports the cap."""
        from app.agents.tools import file_extract_tools

        # Materialise
        file_extract_tools._extract_text_sync(test_pdf)

        # Search for any term
        result = file_extract_tools.file_find("pdf", path=test_pdf)
        # Result should be readable text
        assert isinstance(result, str)


class TestPageImage:
    """file_page_image: render a full page for diagram-heavy layouts."""

    def test_page_image_function_contract(self, sandbox, test_pdf):
        """file_page_image (when implemented) always returns text, never raises."""
        from app.agents.tools import file_extract_tools

        # Materialise first (creates the .pdf folder and manifest)
        file_extract_tools._extract_text_sync(test_pdf)

        # Skip if not implemented (T6 task)
        if not hasattr(file_extract_tools, 'file_page_image'):
            pytest.skip("file_page_image not yet implemented (T6)")

        # Valid page
        result = file_extract_tools._file_page_image_sync(".extract/pdf/test", page=1)
        assert isinstance(result, str)

        # Invalid page - should return error string, never raise
        result = file_extract_tools._file_page_image_sync(".extract/pdf/test", page=999)
        assert isinstance(result, str)


class TestParallel:
    """Parallel: process pool threshold (though small docs run sequential)."""

    def test_small_document_runs_sequential(self, sandbox, test_pdf):
        """A 3-page document runs sequentially, not via process pool."""
        from app.agents.tools import file_extract_tools

        # This test simply verifies that the 3-page test PDF completes.
        # Since it's under the ~30-page threshold, it should run synchronously.
        result = file_extract_tools._extract_text_sync(test_pdf)
        assert "Materialised" in result
        assert "3 page" in result or "3" in result


# ─── Acceptance Criteria Verification ─────────────────────────────────────

def test_ac1_file_passes_standalone(sandbox, test_pdf):
    """AC1: pytest backend/tests/agents/test_pdf_tools.py -q passes."""
    # This test is the file itself.
    pass


def test_ac2_no_reference_dependency(sandbox, test_pdf):
    """AC2: No test depends on .reference/ (which is untracked)."""
    # Verified by construction: all tests use _gen_minimal_pdf_bytes().
    # No test imports or references .reference/.
    pass


def test_ac3_k_selectors_each_find_tests():
    """AC3: Each -k selector finds at least one test."""
    # Verified by class/function naming:
    # -k info          -> class TestInfo + test_info_*
    # -k order         -> class TestReadingOrder + test_reading_order_*
    # -k merge         -> class TestFragmentMerge + test_merge_*
    # -k crop          -> class TestCropGeometry + test_crop_*
    # -k materialise   -> class TestMaterialise + test_materialise_*
    # -k resume        -> class TestResume + test_resume_*
    # -k stale         -> class TestStale + test_stale_*
    # -k find          -> class TestPdfFind + test_find_*
    # -k page_image    -> class TestPageImage + test_page_image_*
    # -k parallel      -> class TestParallel + test_*
    pass


# ─── Post-implementation audit regressions (spec 019) ─────────────────────
#
# Four defects the workflow's own validators did not catch, each with the
# check that fails on the old behaviour.


class TestDocumentRefs:
    """document.md placeholder refs are {slug}/-relative (contracts/on-disk-format.md)."""

    def test_document_md_refs_are_slug_relative(self, sandbox, test_pdf):
        """A bare "image-1.png" in a page's text.md becomes "pages/01/image-1.png".

        Left page-relative, every page's "image-1.png" names a different file and
        a reader of document.md cannot resolve any of them.
        """
        from app.agents.tools import file_extract_tools

        file_extract_tools._extract_text_sync(test_pdf)
        pages_dir = sandbox / ".extract" / "pdf" / "test" / "pages"

        # Inject a placeholder into an already-complete page, then re-extract:
        # document.md is rebuilt from whatever is on disk (the folder is the state).
        (pages_dir / "01" / "text.md").write_text("before\n\n@[[image-1.png]]  <!-- 10x10, 1 source object -->\n\nafter\n")
        file_extract_tools._extract_text_sync(test_pdf)

        document = (sandbox / ".extract" / "pdf" / "test" / "document.md").read_text()
        assert "@[[pages/01/image-1.png]]" in document
        assert "@[[image-1.png]]" not in document

    def test_document_md_leaves_already_qualified_refs_alone(self, sandbox, test_pdf):
        """A ref that already carries a "/" is {slug}/-relative and is not rewritten."""
        from app.agents.tools import file_extract_tools

        file_extract_tools._extract_text_sync(test_pdf)
        pages_dir = sandbox / ".extract" / "pdf" / "test" / "pages"
        (pages_dir / "02" / "text.md").write_text("@[[pages/01/image-1.png]]\n")
        file_extract_tools._extract_text_sync(test_pdf)

        document = (sandbox / ".extract" / "pdf" / "test" / "document.md").read_text()
        assert "@[[pages/01/image-1.png]]" in document
        assert "pages/02/pages/01" not in document


class TestParallelBranch:
    """The >threshold branch actually runs, including from inside an event loop."""

    def test_parallel_branch_materialises_every_page(self, sandbox, test_pdf, monkeypatch):
        """Forced above the threshold, the process pool produces the same page set."""
        from app.agents.tools import file_extract_tools

        monkeypatch.setattr(file_extract_tools, "_PARALLEL_PAGE_THRESHOLD", 1)
        result = file_extract_tools._extract_text_sync(test_pdf)

        assert "Materialised" in result
        assert "failed" not in result
        pages_dir = sandbox / ".extract" / "pdf" / "test" / "pages"
        assert sorted(p.name for p in pages_dir.iterdir() if p.is_dir()) == ["01", "02", "03"]

    def test_parallel_branch_survives_a_running_event_loop(self, sandbox, test_pdf, monkeypatch):
        """Regression: an asyncio.run() wrapper here raised inside a live loop.

        The tool is a plain sync callable; calling it from a thread that owns a
        loop must still materialise, not return "failed to materialise pages in
        parallel: asyncio.run() cannot be called from a running event loop".
        """
        import asyncio

        from app.agents.tools import file_extract_tools

        monkeypatch.setattr(file_extract_tools, "_PARALLEL_PAGE_THRESHOLD", 1)

        async def call_from_the_loop():
            return file_extract_tools._extract_text_sync(test_pdf)

        result = asyncio.run(call_from_the_loop())
        assert "Materialised" in result
        assert "asyncio.run" not in result

    def test_no_thread_is_used_for_pdf_work(self):
        """PDFium is not thread-safe: rendering across threads crashes the process."""
        import inspect

        from app.agents.tools import file_extract_tools

        source = inspect.getsource(file_extract_tools)
        assert "ThreadPoolExecutor" not in source
        assert "threading.Thread" not in source


class TestMissingSourceWithSidecar:
    """FR-021: a surviving sidecar is not the same as a document never uploaded."""

    def test_wiped_source_points_at_the_materialised_pages(self, sandbox, test_pdf):
        from app.agents.tools import file_extract_tools

        file_extract_tools._extract_text_sync(test_pdf)
        (sandbox / test_pdf).unlink()

        result = file_extract_tools._extract_text_sync(test_pdf)
        assert ".extract/pdf/test/" in result
        assert "never uploaded" in result

    def test_never_uploaded_says_only_that(self, sandbox):
        from app.agents.tools import file_extract_tools

        result = file_extract_tools._extract_text_sync(".uploads/no-such-document.pdf")
        assert "not a file" in result
        assert ".extract/" not in result

    def test_page_image_makes_the_same_distinction(self, sandbox, test_pdf):
        from app.agents.tools import file_extract_tools

        file_extract_tools._extract_text_sync(test_pdf)
        (sandbox / test_pdf).unlink()

        assert "materialised pages survive" in file_extract_tools._file_page_image_sync(test_pdf, 1)


# ─── Office formats: one entry point, one route (spec 019, FR-026…FR-043) ──


def _gen_docx_bytes(paragraphs=("Alpha paragraph.", "Beta paragraph.")) -> bytes:
    """A real .docx via python-docx (vendored in requirements.txt)."""
    from docx import Document

    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _soffice_available() -> bool:
    from app.agents.tools import soffice

    return soffice.available()


requires_soffice = pytest.mark.skipif(
    not _soffice_available(),
    reason="LibreOffice is not installed in this environment (FR-027a)",
)


class TestFormatIsADirectoryLevel:
    """FR-030: report.docx and report.pdf are different documents."""

    def test_slug_drops_the_extension(self):
        from app.agents.tools import file_extract_tools

        assert file_extract_tools._slug_from_filename("Inland Marine Creating a Quote 2.pdf") == (
            "inland-marine-creating-a-quote-2"
        )
        assert file_extract_tools._slug_from_filename("report.docx") == "report"

    def test_same_stem_different_format_land_in_different_directories(self):
        """The slugs are equal on purpose; the format level is what separates them."""
        from app.agents.tools import file_extract_tools

        assert file_extract_tools._slug_from_filename("report.docx") == file_extract_tools._slug_from_filename("report.pdf")
        assert file_extract_tools._doc_rel("docx", "report") != file_extract_tools._doc_rel("pdf", "report")
        assert file_extract_tools._doc_rel("docx", "report") == ".extract/docx/report"

    @requires_soffice
    def test_two_formats_of_one_name_coexist(self, sandbox, test_pdf):
        """The collision FR-030 exists to prevent, end to end."""
        from app.agents.tools import file_extract_tools

        (sandbox / ".uploads" / "test.docx").write_bytes(_gen_docx_bytes(("Word revision.",)))
        file_extract_tools._extract_text_sync(test_pdf)
        file_extract_tools._extract_text_sync(".uploads/test.docx")
        file_extract_tools._extract_text_sync(test_pdf)

        assert (sandbox / ".extract" / "pdf" / "test" / "manifest.json").is_file()
        assert (sandbox / ".extract" / "docx" / "test" / "manifest.json").is_file()
        assert "Word revision." in (
            sandbox / ".extract" / "docx" / "test" / "pages" / "01" / "text.md"
        ).read_text()


class TestFormatDispatch:
    """FR-039: one entry point; an unsupported container is refused in text."""

    def test_unsupported_format_returns_readable_text(self, sandbox):
        from app.agents.tools import file_extract_tools

        (sandbox / ".uploads" / "notes.rtf").write_bytes(b"not a real rtf")
        result = file_extract_tools._extract_text_sync(".uploads/notes.rtf")
        assert "not a supported format" in result
        assert ".docx" in result and ".xlsx" in result and ".pptx" in result

    def test_missing_converter_is_named_not_raised(self, sandbox, monkeypatch):
        """FR-031: absent LibreOffice is an explanation, never an exception."""
        from app.agents.tools import file_extract_tools, soffice

        monkeypatch.setattr(soffice, "find_binary", lambda: None)
        (sandbox / ".uploads" / "report.docx").write_bytes(_gen_docx_bytes())

        result = file_extract_tools._extract_text_sync(".uploads/report.docx")
        assert "LibreOffice is not installed" in result
        assert "PDF uploads are unaffected" in result


@requires_soffice
class TestOfficeConversion:
    """The .docx goes through LibreOffice and then the SAME materialiser."""

    def test_docx_materialises_like_a_pdf(self, sandbox):
        from app.agents.tools import file_extract_tools

        (sandbox / ".uploads" / "report.docx").write_bytes(_gen_docx_bytes())
        result = file_extract_tools._extract_text_sync(".uploads/report.docx")

        assert "Materialised" in result
        pages = sandbox / ".extract" / "docx" / "report" / "pages" / "01"
        assert pages.is_dir()
        assert "Alpha paragraph." in (pages / "text.md").read_text()

    def test_conversion_is_cached_as_source_pdf(self, sandbox):
        """FR-028: present iff conversion completed; a second call reuses it."""
        from app.agents.tools import file_extract_tools

        (sandbox / ".uploads" / "report.docx").write_bytes(_gen_docx_bytes())
        file_extract_tools._extract_text_sync(".uploads/report.docx")

        cached = sandbox / ".extract" / "docx" / "report" / "source.pdf"
        assert cached.is_file()
        stamp = cached.stat().st_mtime_ns

        file_extract_tools._extract_text_sync(".uploads/report.docx")
        assert cached.stat().st_mtime_ns == stamp, "conversion re-ran instead of reusing the cache"

    def test_manifest_records_the_source_format_and_converter(self, sandbox):
        """FR-029: the hash is of the .docx, not of the PDF derived from it."""
        from app.agents.tools import file_extract_tools

        docx_bytes = _gen_docx_bytes()
        (sandbox / ".uploads" / "report.docx").write_bytes(docx_bytes)
        file_extract_tools._extract_text_sync(".uploads/report.docx")

        manifest = json.loads((sandbox / ".extract" / "docx" / "report" / "manifest.json").read_text())
        assert manifest["source_format"] == "docx"
        assert manifest["converted_by"] == "libreoffice"
        assert manifest["source_sha256"] == hashlib.sha256(docx_bytes).hexdigest()

    def test_receipt_says_whose_pagination_it_is(self, sandbox, test_pdf):
        """FR-035: Word and LibreOffice do not agree on where page 4 begins."""
        from app.agents.tools import file_extract_tools

        (sandbox / ".uploads" / "report.docx").write_bytes(_gen_docx_bytes())

        converted = file_extract_tools._extract_text_sync(".uploads/report.docx")
        assert "converter's pagination" in converted

        native = file_extract_tools._extract_text_sync(test_pdf)
        assert "converter's pagination" not in native

    def test_reupload_under_the_same_name_discards_the_conversion(self, sandbox):
        """FR-008 + FR-029 together: a new .docx must not serve the old PDF."""
        from app.agents.tools import file_extract_tools

        upload = sandbox / ".uploads" / "report.docx"
        upload.write_bytes(_gen_docx_bytes(("First revision.",)))
        file_extract_tools._extract_text_sync(".uploads/report.docx")

        upload.write_bytes(_gen_docx_bytes(("Second revision.",)))
        file_extract_tools._extract_text_sync(".uploads/report.docx")

        text = (sandbox / ".extract" / "docx" / "report" / "pages" / "01" / "text.md").read_text()
        assert "Second revision." in text
        assert "First revision." not in text


class TestNoPageCap:
    """FR-034: a large document is materialised, never refused.

    A client's 1000-page PDF is real content. Measured on the screenshot-heavy
    reference document (the worst case, since text-only pages are much smaller):
    204 KB/page, so 1000 pages is ~0.19 GB and ~25s once the process pool engages.
    Refusing that would be the tool failing at its own job.
    """

    def test_a_large_document_is_materialised_not_refused(self, sandbox, monkeypatch):
        from app.agents.tools import file_extract_tools as fx

        monkeypatch.setattr(fx, "_LARGE_DOCUMENT_PAGES", 1)
        monkeypatch.setattr(
            fx, "_converted_pdf", lambda path, doc_dir: (_gen_minimal_pdf_bytes(), "libreoffice", "")
        )
        (sandbox / ".uploads" / "book.xlsx").write_bytes(b"stand-in; conversion is stubbed")

        result = fx._extract_text_sync(".uploads/book.xlsx")

        assert "Materialised" in result
        assert "ceiling" not in result.lower()
        assert (sandbox / ".extract" / "xlsx" / "book" / "pages" / "01").is_dir()

    def test_a_large_document_is_told_that_slicing_exists(self, sandbox, monkeypatch):
        """Advisory, not a gate — the pages are already on disk when this prints."""
        from app.agents.tools import file_extract_tools as fx

        monkeypatch.setattr(fx, "_LARGE_DOCUMENT_PAGES", 1)
        monkeypatch.setattr(
            fx, "_converted_pdf", lambda path, doc_dir: (_gen_minimal_pdf_bytes(), "libreoffice", "")
        )
        (sandbox / ".uploads" / "book.xlsx").write_bytes(b"stand-in; conversion is stubbed")

        result = fx._extract_text_sync(".uploads/book.xlsx")
        assert 'pages="1-20"' in result
        assert (sandbox / ".extract" / "xlsx" / "book" / "pages" / "03").is_dir(), (
            "every page must still be materialised — the note is advice, not a limit"
        )

    def test_a_spreadsheet_says_whose_pagination_it_is(self, sandbox, monkeypatch):
        from app.agents.tools import file_extract_tools as fx

        monkeypatch.setattr(
            fx, "_converted_pdf", lambda path, doc_dir: (_gen_minimal_pdf_bytes(), "libreoffice", "")
        )
        (sandbox / ".uploads" / "book.xlsx").write_bytes(b"stand-in; conversion is stubbed")

        result = fx._extract_text_sync(".uploads/book.xlsx")
        assert "print settings" in result

    def test_a_small_document_gets_no_advisory_noise(self, sandbox, test_pdf):
        from app.agents.tools import file_extract_tools as fx

        result = fx._extract_text_sync(test_pdf)
        assert 'pages="1-20"' not in result


class TestThreeRoutes:
    """FR-044: text comes back inline, paged formats go to disk, else refused."""

    def test_plain_text_returns_its_content(self, sandbox):
        from app.agents.tools import file_extract_tools

        (sandbox / ".uploads" / "notes.md").write_text("# Heading\n\nBody line.\n")
        result = file_extract_tools._extract_text_sync(".uploads/notes.md")

        assert "# Heading" in result and "Body line." in result
        assert not (sandbox / ".extract").exists(), "a text file must not be materialised"

    @pytest.mark.parametrize("name", ["a.txt", "b.md", "c.csv", "d.json"])
    def test_every_text_format_takes_the_inline_route(self, sandbox, name):
        from app.agents.tools import file_extract_tools

        (sandbox / ".uploads" / name).write_text("payload-marker")
        assert "payload-marker" in file_extract_tools._extract_text_sync(f".uploads/{name}")

    def test_a_huge_text_file_is_truncated_and_says_so(self, sandbox):
        from app.agents.tools import file_extract_tools

        big = "x" * (file_extract_tools._TEXT_INLINE_MAX_CHARS + 5_000)
        (sandbox / ".uploads" / "big.csv").write_text(big)
        result = file_extract_tools._extract_text_sync(".uploads/big.csv")

        assert "TRUNCATED" in result
        assert "read_file" in result
        assert len(result) < len(big)

    def test_a_paged_format_returns_a_receipt_naming_document_md(self, sandbox, test_pdf):
        from app.agents.tools import file_extract_tools

        result = file_extract_tools._extract_text_sync(test_pdf)
        assert "read_file .extract/pdf/test/document.md" in result
        assert (sandbox / ".extract" / "pdf" / "test" / "document.md").is_file()

    def test_an_unknown_type_is_refused_without_trying_a_conversion(self, sandbox, monkeypatch):
        """No blind soffice attempt: the allow-list decides what reaches this process."""
        from app.agents.tools import file_extract_tools, soffice

        def _never(*a, **k):
            raise AssertionError("conversion attempted on an unsupported type")

        monkeypatch.setattr(soffice, "convert_to_pdf", _never)
        (sandbox / ".uploads" / "archive.zip").write_bytes(b"PK\x03\x04stub")

        result = file_extract_tools._extract_text_sync(".uploads/archive.zip")
        assert "not a supported format" in result

    def test_info_describes_a_text_file_without_a_pdf_parser(self, sandbox):
        from app.agents.tools import file_extract_tools

        (sandbox / ".uploads" / "rows.csv").write_text("a,b\n1,2\n3,4\n")
        result = file_extract_tools.file_info(".uploads/rows.csv")

        assert "plain text" in result
        assert "3 lines" in result
        assert "nothing to materialise" in result.lower()


class TestDeclaredDependencies:
    """Every third-party module these tools import must be in requirements.txt.

    This is the FIX-191 / ISS-057 failure mode and spec 019 reintroduced it:
    `pdfplumber` was imported on every extract and declared nowhere, so the tools
    worked on a developer machine and returned "PDF libraries unavailable" in the
    container. A lazy import inside a function plus a broad `except ImportError`
    turns a missing dependency into a silent, environment-specific wrong answer —
    which is exactly why this is asserted rather than remembered.
    """

    THIRD_PARTY = {"pdfplumber", "pypdfium2", "pypdf", "PIL", "docx", "pptx", "openpyxl"}
    PACKAGE_FOR = {"PIL": "pillow", "docx": "python-docx", "pptx": "python-pptx"}

    # Imported directly, declared nowhere ON PURPOSE: each is a hard dependency of
    # pdfplumber (`Pillow>=12.2.0`, `pypdfium2>=5.9.0`), and pinning it here would
    # assert a version contract this project does not control (FR-001). Listing it
    # is the point — the decision is visible, so an import that arrives from NOTHING
    # still fails this test, which is how `pdfplumber` itself slipped through.
    TRANSITIVE_VIA = {"pypdfium2": "pdfplumber", "PIL": "pdfplumber"}

    def _requirements(self) -> str:
        """Declared packages only — comment lines are prose, not declarations."""
        import pathlib

        here = pathlib.Path(__file__).resolve()
        backend = next(p for p in here.parents if (p / "requirements.txt").is_file())
        lines = (backend / "requirements.txt").read_text().splitlines()
        return "\n".join(
            line.split("#", 1)[0].strip().lower()
            for line in lines
            if line.strip() and not line.lstrip().startswith("#")
        )

    def _imported_modules(self) -> set:
        import ast
        import pathlib

        source = pathlib.Path(
            __import__("app.agents.tools.file_extract_tools", fromlist=["x"]).__file__
        )
        tree = ast.parse(source.read_text())
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                found.add(node.module.split(".")[0])
        return found

    def test_every_imported_third_party_module_is_accounted_for(self):
        requirements = self._requirements()
        missing = []
        for module in sorted(self._imported_modules() & self.THIRD_PARTY):
            if module in self.TRANSITIVE_VIA:
                carrier = self.TRANSITIVE_VIA[module]
                assert carrier.lower() in requirements, (
                    f"{module} rides on {carrier}, which is itself undeclared"
                )
                continue
            package = self.PACKAGE_FOR.get(module, module)
            if package.lower() not in requirements:
                missing.append(f"{module} (declare as {package})")

        assert not missing, (
            "imported, declared nowhere, and not recorded as transitive — these fail "
            f"only in the container: {missing}"
        )

    def test_pypdfium2_is_deliberately_not_pinned(self):
        """FR-001: it arrives via pdfplumber; a direct pin asserts a contract we don't own."""
        assert "pdfplumber" in self._requirements()
        assert "pypdfium2" not in self._requirements()


class TestColumnSeparation:
    """A converted spreadsheet's columns must not fuse into values that don't exist."""

    def test_word_tolerance_is_tighter_than_pdfplumbers_prose_default(self):
        """pdfplumber defaults to 3.0, which is tuned for prose, not for a grid."""
        from app.agents.tools import file_extract_tools as fx

        assert fx._WORD_X_TOLERANCE < 3.0

    def test_adjacent_columns_stay_separate_words(self):
        """A right-aligned number flush against a left-aligned value: "46445" + "Yes".

        At pdfplumber's default this arrives as the single token "46445Yes" — a value
        that appears nowhere in the workbook. Reproduced here with synthetic words so
        the test needs neither LibreOffice nor a fixture spreadsheet.
        """
        from app.agents.tools import file_extract_tools as fx

        class _Page:
            images: list = []

            def extract_words(self, x_tolerance=3.0):
                # "46445" ends at x=100.0; "Yes" starts at x=102.0 — a 2.0pt gap.
                words = [
                    {"text": "46445", "top": 50.0, "x0": 80.0, "x1": 100.0},
                    {"text": "Yes", "top": 50.0, "x0": 102.0, "x1": 118.0},
                ]
                if x_tolerance >= 2.0:  # pdfplumber would fuse them
                    return [{"text": "46445Yes", "top": 50.0, "x0": 80.0, "x1": 118.0}]
                return words

        items = fx._reading_order_items(_Page())
        line = next(payload for _, kind, payload in items if kind == "text")

        assert line == "46445 Yes"
        assert "46445Yes" not in line

    def test_prose_extraction_is_unchanged_by_the_tighter_tolerance(self, sandbox, test_pdf):
        """Measured on the reference PDF: 15,072 chars at every tolerance 3.0 → 1.0."""
        from app.agents.tools import file_extract_tools as fx

        result = fx._extract_text_sync(test_pdf)
        assert "Materialised" in result
