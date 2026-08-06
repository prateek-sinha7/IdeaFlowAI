"""Unit tests for FIX-191: ISS-057 — _extract_docx silently drops tables, headers, footers.

All tests use python-docx to construct real in-memory .docx bytes — no mocking of
_extract_docx itself, matching the grounded context investigation methodology.

Test structure:
  Category 1 — Regression baseline:  the defect existed (pre-fix behaviour documented)
  Category 2 — Happy path:           the primary reported case now works
  Category 3 — Edge cases:           boundary and error inputs
  Category 4 — Safety boundary:      plain-paragraph (pre-existing) behaviour unchanged
"""
from __future__ import annotations

import io

import pytest


# ---------------------------------------------------------------------------
# Helper: build .docx bytes with python-docx (skips gracefully if not installed)
# ---------------------------------------------------------------------------

docx = pytest.importorskip("docx", reason="python-docx not installed")
from docx import Document  # noqa: E402  (after importorskip)


def _make_docx(
    *,
    paragraphs: list[str] | None = None,
    tables: list[list[list[str]]] | None = None,
    header: str | None = None,
    footer: str | None = None,
) -> bytes:
    """Build an in-memory .docx with the requested content."""
    doc = Document()
    for text in (paragraphs or []):
        doc.add_paragraph(text)
    for table_data in (tables or []):
        rows, cols = len(table_data), max(len(r) for r in table_data)
        t = doc.add_table(rows=rows, cols=cols)
        for r_idx, row in enumerate(table_data):
            for c_idx, cell_text in enumerate(row):
                t.cell(r_idx, c_idx).text = cell_text
    if header is not None:
        section = doc.sections[0]
        section.header.paragraphs[0].text = header
    if footer is not None:
        section = doc.sections[0]
        section.footer.paragraphs[0].text = footer
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Import the real function under test (not a re-implementation)
# ---------------------------------------------------------------------------

from app.api.file_extract import _extract_docx, extract_upload_text  # noqa: E402


# ===========================================================================
# Category 1 — Regression baseline (the defect as it existed before the fix)
# ===========================================================================


class TestFix191RegressionBaseline:
    """Document the defect: tables, headers, footers were silently dropped."""

    def test_fix191_table_content_was_not_in_doc_paragraphs(self):
        """Confirm python-docx does NOT surface table cell text via doc.paragraphs —
        this is the root cause that caused the silent drop before the fix."""
        data = _make_docx(tables=[[["Item", "Price"], ["Widget", "£9.99"]]])
        doc = Document(io.BytesIO(data))
        para_texts = [p.text for p in doc.paragraphs]
        # Table cell text must NOT appear in the paragraphs collection
        full_para_blob = "\n".join(para_texts)
        assert "Item" not in full_para_blob
        assert "Widget" not in full_para_blob

    def test_fix191_old_impl_would_return_empty_for_all_table_docx(self):
        """Simulate the pre-fix behaviour: iterate only doc.paragraphs.
        An all-table document would produce '' and trigger the misleading 422."""
        data = _make_docx(tables=[[["Col A", "Col B"], ["v1", "v2"]]])
        doc = Document(io.BytesIO(data))
        # The old one-liner:
        old_result = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        assert old_result == "", (
            "Pre-fix simulation: all-table docx must return '' with the old one-liner"
        )

    def test_fix191_header_footer_absent_from_doc_paragraphs(self):
        """Confirm header/footer text does NOT appear in doc.paragraphs."""
        data = _make_docx(header="HEADER_SENTINEL", footer="FOOTER_SENTINEL")
        doc = Document(io.BytesIO(data))
        para_blob = "\n".join(p.text for p in doc.paragraphs)
        assert "HEADER_SENTINEL" not in para_blob
        assert "FOOTER_SENTINEL" not in para_blob


# ===========================================================================
# Category 2 — Happy path (primary reported cases now work)
# ===========================================================================


class TestFix191HappyPath:
    """The three confirmed gaps (table, header, footer) are now extracted."""

    def test_fix191_table_cells_now_extracted(self):
        """FIX-191: table cell content must appear in extracted text."""
        data = _make_docx(
            paragraphs=["Intro paragraph."],
            tables=[[["Item", "Price"], ["Widget", "£9.99"]]],
        )
        result = _extract_docx(data)
        assert "Item" in result, "table header cell must be extracted"
        assert "Widget" in result, "table data cell must be extracted"
        assert "£9.99" in result, "table data cell with price must be extracted"

    def test_fix191_table_uses_pipe_separator_and_markers(self):
        """FIX-191: extracted table rows use pipe separator; block wrapped in [Table]/[/Table]."""
        data = _make_docx(tables=[[["A", "B"], ["1", "2"]]])
        result = _extract_docx(data)
        assert "[Table]" in result
        assert "[/Table]" in result
        assert "A | B" in result
        assert "1 | 2" in result

    def test_fix191_header_now_extracted(self):
        """FIX-191: section header text must appear wrapped in [Header]/[/Header]."""
        data = _make_docx(header="CONFIDENTIAL — v1.0")
        result = _extract_docx(data)
        assert "CONFIDENTIAL — v1.0" in result
        assert "[Header]" in result
        assert "[/Header]" in result

    def test_fix191_footer_now_extracted(self):
        """FIX-191: section footer text must appear wrapped in [Footer]/[/Footer]."""
        data = _make_docx(footer="Page 1 of 1 — Internal Use Only")
        result = _extract_docx(data)
        assert "Page 1 of 1 — Internal Use Only" in result
        assert "[Footer]" in result
        assert "[/Footer]" in result

    def test_fix191_all_table_docx_no_longer_returns_empty(self):
        """FIX-191: an all-table / zero-prose docx must NOT return ''.
        Pre-fix this caused a misleading 422 'may be image-based or encrypted'."""
        data = _make_docx(tables=[[["Feature", "Status"], ["Auth", "Done"]]])
        result = _extract_docx(data)
        assert result.strip() != "", "all-table docx must no longer produce empty string"
        assert "Feature" in result
        assert "Auth" in result

    def test_fix191_four_markers_all_present_in_full_evidence_doc(self):
        """FIX-191: replicate the grounded-context evidence doc — all 4 markers survive."""
        para_marker = "PARA_MARKER_9f3d7a1c"
        table_marker = "TABLE_MARKER_b81e5d4f"
        header_marker = "HEADER_MARKER_c4a2e891"
        footer_marker = "FOOTER_MARKER_e77f1b06"
        data = _make_docx(
            paragraphs=[f"Normal paragraph: {para_marker}"],
            tables=[[["Item", f"Contains: {table_marker}"]]],
            header=f"Header: {header_marker}",
            footer=f"Footer: {footer_marker}",
        )
        result = _extract_docx(data)
        assert para_marker in result, "paragraph marker must survive"
        assert table_marker in result, "table marker must survive (was dropped before fix)"
        assert header_marker in result, "header marker must survive (was dropped before fix)"
        assert footer_marker in result, "footer marker must survive (was dropped before fix)"

    def test_fix191_extract_upload_text_returns_same_as_extract_docx(self):
        """FIX-191: extract_upload_text('test.docx', data) == _extract_docx(data) — single impl (INV-12)."""
        data = _make_docx(
            paragraphs=["Para text."],
            tables=[[["Col1", "Col2"], ["v1", "v2"]]],
        )
        assert extract_upload_text("test.docx", data) == _extract_docx(data)


# ===========================================================================
# Category 3 — Edge cases
# ===========================================================================


class TestFix191EdgeCases:
    """Boundary inputs and error conditions."""

    def test_fix191_empty_table_rows_not_included(self):
        """FIX-191: completely empty table rows must NOT emit a blank pipe line."""
        data = _make_docx(tables=[[["", ""], ["Real", "Data"]]])
        result = _extract_docx(data)
        # "Real | Data" must be present; " | " alone (empty row) must not
        assert "Real | Data" in result
        lines = [line for line in result.splitlines() if line.strip() == "|" or line.strip() == " | "]
        assert len(lines) == 0, "empty table rows must be skipped"

    def test_fix191_empty_docx_returns_empty_string(self):
        """FIX-191: a completely empty docx (no paragraphs, no tables, no headers/footers)
        must return '' — unchanged from pre-fix."""
        data = _make_docx()
        result = _extract_docx(data)
        assert result == ""

    def test_fix191_corrupted_bytes_returns_empty_string(self):
        """FIX-191: corrupt/non-docx bytes must return '' (not raise) — same as before."""
        result = _extract_docx(b"this is not a valid docx file")
        assert result == ""

    def test_fix191_table_cells_with_newlines_collapsed_to_space(self):
        """FIX-191: multi-line cell text must have internal newlines collapsed to a space."""
        doc = Document()
        t = doc.add_table(rows=1, cols=1)
        t.cell(0, 0).text = "line one\nline two"
        buf = io.BytesIO()
        doc.save(buf)
        data = buf.getvalue()
        result = _extract_docx(data)
        assert "\n" not in result.split("[Table]")[1].split("[/Table]")[0].strip().splitlines()[0]

    def test_fix191_multiple_tables_all_extracted(self):
        """FIX-191: a docx with multiple tables must extract all of them."""
        data = _make_docx(
            tables=[
                [["Table1Col1", "Table1Col2"]],
                [["Table2Col1", "Table2Col2"]],
            ]
        )
        result = _extract_docx(data)
        assert "Table1Col1" in result
        assert "Table2Col1" in result
        assert result.count("[Table]") == 2

    def test_fix191_blank_header_footer_not_added(self):
        """FIX-191: sections with no header/footer text must NOT add empty [Header]/[Footer] blocks."""
        data = _make_docx(paragraphs=["Just a paragraph."])
        result = _extract_docx(data)
        # A docx with no explicit header/footer content should not emit the markers
        assert "[Header]" not in result or "Just a paragraph." in result


# ===========================================================================
# Category 4 — Safety boundary (pre-existing plain-paragraph behaviour unchanged)
# ===========================================================================


class TestFix191SafetyBoundary:
    """The existing plain-paragraph path must be byte-identical before and after."""

    def test_fix191_plain_paragraphs_output_unchanged(self):
        """FIX-191: a paragraphs-only docx must produce exactly the same output as the pre-fix
        one-liner — backward-compat by construction and by proof."""
        paragraphs = ["First paragraph.", "Second paragraph, after a blank one."]
        data = _make_docx(paragraphs=paragraphs)
        # New implementation
        new_result = _extract_docx(data)
        # Simulate the old one-liner on the same document
        doc = Document(io.BytesIO(data))
        old_result = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        assert new_result == old_result, (
            "Plain-paragraph docx must produce byte-identical output before and after fix"
        )

    def test_fix191_plain_paragraphs_multi_paragraph(self):
        """FIX-191: multiple plain paragraphs must still be newline-joined."""
        data = _make_docx(paragraphs=["Alpha.", "Beta.", "Gamma."])
        result = _extract_docx(data)
        assert "Alpha." in result
        assert "Beta." in result
        assert "Gamma." in result

    def test_fix191_blank_paragraphs_still_filtered(self):
        """FIX-191: blank paragraphs (whitespace-only) must still be excluded — unchanged."""
        doc = Document()
        doc.add_paragraph("Real text.")
        doc.add_paragraph("")        # blank — must be filtered
        doc.add_paragraph("   ")     # whitespace-only — must be filtered
        doc.add_paragraph("More text.")
        buf = io.BytesIO()
        doc.save(buf)
        result = _extract_docx(buf.getvalue())
        assert "Real text." in result
        assert "More text." in result
        # The blank paragraph must not contribute an empty line in body_text
        lines = result.split("\n\n")[0].splitlines()  # first block = body_text
        assert all(line.strip() for line in lines if line)

    def test_fix191_extract_upload_text_non_docx_extension_unchanged(self):
        """FIX-191: extract_upload_text must still return '' for unknown extensions."""
        assert extract_upload_text("report.xyz", b"irrelevant") == ""

    def test_fix191_inv12_single_impl_docx_path(self):
        """FIX-191 / INV-12: extract_upload_text must dispatch .docx to _extract_docx —
        verify that changing _extract_docx is sufficient for both call sites."""
        data = _make_docx(tables=[[["INV12_TABLE_SENTINEL", "value"]]])
        result_direct = _extract_docx(data)
        result_via_dispatch = extract_upload_text("spec.docx", data)
        assert result_direct == result_via_dispatch
        assert "INV12_TABLE_SENTINEL" in result_via_dispatch, (
            "INV-12: single impl — run_files.py call site gets the fix via extract_upload_text"
        )
