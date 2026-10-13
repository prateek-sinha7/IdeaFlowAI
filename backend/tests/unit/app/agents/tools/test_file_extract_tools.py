"""Unit tests for app.agents.tools.file_extract_tools (self-sufficient: 100% branch coverage alone).

Real parsing logic runs against tiny hand-built PDFs / text files in ``tmp_path``.
Only the process pool, the LibreOffice converter and failure-injection points of
third-party libraries are replaced. Plan: unit-test-prompt/test-files/
app__agents__tools__file_extract_tools/02-test-plan.md.
"""

from __future__ import annotations

import builtins
import concurrent.futures
import hashlib
import io
import json
import os
import re
import sys
import threading
from pathlib import Path
from typing import Any
from unittest import mock

import pdfplumber
import pypdf
import pypdfium2
import pytest
from PIL import Image

from app.agents.tools import file_extract_tools as fet
from app.agents.tools import soffice

NOT_BOUND = "document tools not bound to a run sandbox (internal error)"
SUPPORTED = ".csv, .docx, .htm, .html, .json, .md, .pdf, .pptx, .txt, .xlsx"
PNOTE = (
    "\nNOTE: this document was converted by libreoffice; page numbers are "
    "the converter's pagination, which the authoring application may not share."
)


# --------------------------------------------------------------------------- helpers
class _Sandbox:
    """Duck-typed RunSandbox: resolves under root, rejects escapes and denied substrings."""

    def __init__(self, root: Path, deny: tuple[str, ...] = ()) -> None:
        self.root = root
        self.deny = deny
        self.calls: list[str] = []

    def path_for(self, relpath: str) -> Path:
        self.calls.append(relpath)
        if any(d in relpath for d in self.deny):
            raise ValueError(f"denied: {relpath}")
        resolved = (self.root / relpath).resolve()
        if not resolved.is_relative_to(self.root.resolve()):
            raise ValueError(f"escapes root: {relpath}")
        return resolved


def _make_pdf(texts: list[str]) -> bytes:
    """Build a valid tiny PDF (one Helvetica line per page) with a correct xref."""
    n = len(texts)
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(n))
    objs: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for i, text in enumerate(texts):
        objs.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * i} 0 R >>"
            ).encode()
        )
        stream = f"BT /F1 12 Tf 20 150 Td ({text}) Tj ET".encode()
        objs.append(
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
        )
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    ).encode()
    return bytes(out)


def _upload(root: Path, name: str, data: bytes | str) -> str:
    """Write .uploads/<name> and return its sandbox-relative path."""
    d = root / ".uploads"
    d.mkdir(exist_ok=True)
    p = d / name
    p.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
    return f".uploads/{name}"


def _manifest(root: Path, fmt: str, slug: str, body: dict | None = None) -> Path:
    d = root / ".extract" / fmt / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(json.dumps(body or {"k": 1}))
    return d


def _page(doc_dir: Path, num: str, text: str | None) -> None:
    d = doc_dir / "pages" / num
    d.mkdir(parents=True, exist_ok=True)
    if text is not None:
        (d / "text.md").write_text(text)


class _InlineExecutor:
    """In-process stand-in for ProcessPoolExecutor (the unit I/O guard forbids spawning)."""

    def __init__(self, max_workers: int | None = None) -> None:
        self.max_workers = max_workers
        self.submitted: list[tuple[Any, ...]] = []

    def __enter__(self) -> _InlineExecutor:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def submit(self, fn, *args):
        self.submitted.append(args)
        fut: concurrent.futures.Future = concurrent.futures.Future()
        fut.set_result(fn(*args))
        return fut


class _CloseSpy:
    """Delegating wrapper that counts close() calls on a real document."""

    def __init__(self, real: Any, closed: list[int]) -> None:
        self._real = real
        self._closed = closed

    @property
    def pages(self):
        return self._real.pages

    def close(self) -> None:
        self._closed.append(1)
        self._real.close()


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Bind a sandbox rooted at tmp_path; monkeypatch restores the global afterwards."""
    monkeypatch.setattr(fet, "_SANDBOX", None)
    fet.bind_sandbox(_Sandbox(tmp_path))
    return tmp_path


@pytest.fixture
def unbound(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fet, "_SANDBOX", None)


@pytest.fixture
def inline_pool(monkeypatch: pytest.MonkeyPatch) -> list[_InlineExecutor]:
    made: list[_InlineExecutor] = []

    def factory(max_workers=None):
        ex = _InlineExecutor(max_workers)
        made.append(ex)
        return ex

    monkeypatch.setattr(fet, "ProcessPoolExecutor", factory)
    return made


def _stub_materialize(text: str | None, images: dict[str, tuple[int, int]], chars: int):
    """Replacement for _materialize_page that writes text.md and PNGs deterministically."""

    def fake(page, render, out_dir: Path) -> dict:
        if text is not None:
            (out_dir / "text.md").write_text(text)
        for name, size in images.items():
            target = out_dir / name if "/" not in name else out_dir.parent.parent / name
            target.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", size).save(target, format="PNG")
        return {
            "text_md": text or "",
            "images": list(images),
            "chars": chars,
            "raw_images": len(images),
            "merged_images": len(images),
        }

    return fake


# --------------------------------------------------------------------------- pure helpers
class TestPaginationNote:
    # Plan #1 | B1
    @pytest.mark.parametrize("value", [None, ""], ids=["none", "empty"])
    def test_pagination_note_returns_empty_when_not_converted(self, value):
        # Arrange / Act
        result = fet._pagination_note(value)
        # Assert
        assert result == ""

    # Plan #2 | B1
    def test_pagination_note_names_converter_when_converted(self):
        # Arrange / Act
        result = fet._pagination_note("libreoffice")
        # Assert
        assert result == PNOTE


class TestFormatOfAndDocRel:
    # Plan #3 | B2
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("a.PDF", "pdf"),
            ("a.tar.gz", "gz"),
            ("README", ""),
            ("a.", ""),
            (".hidden", ""),
        ],
        ids=["upper", "double-ext", "no-ext", "trailing-dot", "dotfile"],
    )
    def test_format_of_returns_lowercase_extension(self, name, expected):
        # Arrange / Act
        result = fet._format_of(name)
        # Assert
        assert result == expected

    # Plan #4 | B2
    def test_doc_rel_joins_format_and_slug_when_called(self):
        # Arrange / Act
        result = fet._doc_rel("pdf", "r")
        # Assert
        assert result == ".extract/pdf/r"


class TestBindSandbox:
    # Plan #5 | B3
    def test_bind_sandbox_replaces_global_when_rebound(self, monkeypatch, tmp_path):
        # Arrange
        monkeypatch.setattr(fet, "_SANDBOX", None)
        sb = _Sandbox(tmp_path)
        # Act
        fet.bind_sandbox(sb)
        bound = fet._SANDBOX
        fet.bind_sandbox(None)
        # Assert
        assert bound is sb
        assert fet._SANDBOX is None


class TestResolvePath:
    # Plan #6 | B4
    def test_resolve_path_reports_unbound_when_no_sandbox(self, unbound):
        # Arrange / Act
        result = fet._resolve_path("x")
        # Assert
        assert result == (None, NOT_BOUND)

    # Plan #7 | B5
    @pytest.mark.parametrize("prefix", ["", "/", "//"], ids=["none", "one", "two"])
    def test_resolve_path_strips_leading_slashes_when_present(self, root, prefix):
        # Arrange
        sb = fet._SANDBOX
        # Act
        result = fet._resolve_path(f"{prefix}.uploads/a.pdf")
        # Assert
        assert sb.calls == [".uploads/a.pdf"]
        assert result == ((root / ".uploads" / "a.pdf").resolve(), "")

    # Plan #8 | B6
    def test_resolve_path_rejects_traversal_when_path_escapes_root(self, root):
        # Arrange / Act
        result = fet._resolve_path("../../etc/passwd")
        # Assert
        assert result == (None, "path rejected: escapes root: ../../etc/passwd")

    # Plan #8b | B5
    def test_resolve_path_contains_absolute_path_when_leading_slash(self, root):
        # Arrange / Act
        path, err = fet._resolve_path("/etc/passwd")
        # Assert
        assert err == ""
        assert path == (root / "etc" / "passwd").resolve()

    # Plan #8c | B6
    def test_resolve_path_rejects_symlink_escape_when_link_points_outside(
        self, root, tmp_path_factory
    ):
        # Arrange
        outside = tmp_path_factory.mktemp("outside")
        link = root / "link"
        try:
            os.symlink(outside, link, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("symlink creation not permitted on this platform")
        # Act
        path, err = fet._resolve_path("link/secret.txt")
        # Assert
        assert path is None
        assert err == "path rejected: escapes root: link/secret.txt"


class TestMissingSourceMessage:
    # Plan #9 | B7
    def test_missing_source_message_returns_base_error_when_no_manifest(self, root):
        # Arrange / Act
        result = fet._missing_source_message(".uploads/a.pdf", "base")
        # Assert
        assert result == "base"

    # Plan #10 | B7
    def test_missing_source_message_returns_base_error_when_doc_dir_unresolvable(
        self, root
    ):
        # Arrange
        fet.bind_sandbox(_Sandbox(root, deny=(".extract",)))
        # Act
        result = fet._missing_source_message(".uploads/a.pdf", "base")
        # Assert
        assert result == "base"

    # Plan #11 | B7
    def test_missing_source_message_explains_survival_when_manifest_exists(self, root):
        # Arrange
        _manifest(root, "pdf", "report")
        # Act
        result = fet._missing_source_message(".uploads/Report.pdf", "err")
        # Assert
        assert result.startswith(
            "err — but its materialised pages survive at .extract/pdf/report/. "
        )
        assert "a resumed run" in result
        assert result.endswith("re-materialising is impossible without the source.")


class TestReadBytes:
    # Plan #12 | B8
    def test_read_bytes_returns_content_when_file_exists(self, root):
        # Arrange
        rel = _upload(root, "a.bin", b"abc")
        # Act
        result = fet._read_bytes(rel)
        # Assert
        assert result == (b"abc", "")

    # Plan #13 | B8
    def test_read_bytes_returns_empty_bytes_when_file_empty(self, root):
        # Arrange
        rel = _upload(root, "e.bin", b"")
        # Act
        result = fet._read_bytes(rel)
        # Assert
        assert result == (b"", "")

    # Plan #14 | B8
    @pytest.mark.parametrize("kind", ["missing", "directory"])
    def test_read_bytes_reports_not_a_file_when_path_missing_or_directory(
        self, root, kind
    ):
        # Arrange
        if kind == "directory":
            (root / ".uploads" / "p").mkdir(parents=True)
        # Act
        result = fet._read_bytes(".uploads/p")
        # Assert
        assert result == (None, "path is not a file: .uploads/p")

    # Plan #15 | B6,B8
    def test_read_bytes_reports_resolve_error_when_traversal(self, root):
        # Arrange / Act
        result = fet._read_bytes("../x")
        # Assert
        assert result == (None, "path rejected: escapes root: ../x")

    # Plan #16 | B8
    def test_read_bytes_reports_failed_to_read_when_open_raises_oserror(
        self, root, monkeypatch
    ):
        # Arrange
        rel = _upload(root, "p.bin", b"abc")
        target = str((root / ".uploads" / "p.bin").resolve())
        real_open = builtins.open

        def fake_open(file, *args, **kwargs):
            if str(file) == target:
                raise OSError("denied")
            return real_open(file, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", fake_open)
        # Act
        result = fet._read_bytes(rel)
        # Assert
        assert result == (None, f"failed to read {rel}: denied")


class TestListUploads:
    # Plan #17 | B9
    def test_list_uploads_returns_error_when_unbound(self, unbound):
        # Arrange / Act
        result = fet._list_uploads()
        # Assert
        assert result == ([], NOT_BOUND)

    # Plan #17 | B9
    def test_list_uploads_returns_error_when_path_for_rejects(self, root):
        # Arrange
        fet.bind_sandbox(_Sandbox(root, deny=(".uploads",)))
        # Act
        result = fet._list_uploads()
        # Assert
        assert result == ([], "uploads directory not accessible")

    # Plan #17 | B9
    def test_list_uploads_returns_empty_when_no_directory(self, root):
        # Arrange / Act
        result = fet._list_uploads()
        # Assert
        assert result == ([], "")

    # Plan #18 | B9
    def test_list_uploads_returns_sorted_supported_files_when_mixed(self, root):
        # Arrange
        _upload(root, "b.pdf", b"x")
        _upload(root, "a.txt", b"x")
        _upload(root, "c.png", b"x")
        (root / ".uploads" / "d.pdf").mkdir()
        # Act
        result = fet._list_uploads()
        # Assert
        assert result == (["a.txt", "b.pdf"], "")

    # Plan #19 | B9
    def test_list_uploads_returns_error_when_listdir_raises(self, root, monkeypatch):
        # Arrange
        (root / ".uploads").mkdir()
        monkeypatch.setattr(fet.os, "listdir", mock.Mock(side_effect=OSError("x")))
        # Act
        result = fet._list_uploads()
        # Assert
        assert result == ([], "failed to list uploads: x")


class TestListAllUploads:
    # Plan #20 | B11
    def test_list_all_uploads_returns_error_when_unbound(self, unbound):
        # Arrange / Act
        result = fet._list_all_uploads()
        # Assert
        assert result == ([], NOT_BOUND)

    # Plan #20 | B11
    def test_list_all_uploads_returns_error_when_path_for_rejects(self, root):
        # Arrange
        fet.bind_sandbox(_Sandbox(root, deny=(".uploads",)))
        # Act
        result = fet._list_all_uploads()
        # Assert
        assert result == ([], "uploads directory not accessible")

    # Plan #20 | B11
    def test_list_all_uploads_returns_empty_when_no_directory(self, root):
        # Arrange / Act
        result = fet._list_all_uploads()
        # Assert
        assert result == ([], "")

    # Plan #20 | B11
    def test_list_all_uploads_flags_support_and_sorts_when_mixed(self, root):
        # Arrange
        _upload(root, "c.png", b"x")
        _upload(root, "b.pdf", b"x")
        _upload(root, "a.txt", b"x")
        (root / ".uploads" / "d.pdf").mkdir()
        # Act
        result = fet._list_all_uploads()
        # Assert
        assert result == ([("a.txt", True), ("b.pdf", True), ("c.png", False)], "")

    # Plan #20 | B11
    def test_list_all_uploads_returns_error_when_listdir_raises(
        self, root, monkeypatch
    ):
        # Arrange
        (root / ".uploads").mkdir()
        monkeypatch.setattr(fet.os, "listdir", mock.Mock(side_effect=OSError("x")))
        # Act
        result = fet._list_all_uploads()
        # Assert
        assert result == ([], "failed to list uploads: x")


class TestSlugFromFilename:
    # Plan #21 | B10
    @pytest.mark.parametrize(
        ("name", "slug"),
        [
            (
                "Inland Marine Creating a Quote 2.pdf",
                "inland-marine-creating-a-quote-2",
            ),
            ("UPPER.PDF", "upper"),
            ("a--b.pdf", "a-b"),
            ("--a--.pdf", "a"),
            ("Résumé.pdf", "r-sum"),
            (".pdf", "pdf"),
            ("A_B.c.pdf", "a-b-c"),
            ("noext", "noext"),
            ("", ""),
        ],
        ids=[
            "spaces",
            "upper",
            "collapse",
            "trim",
            "unicode",
            "dotfile",
            "multi-dot",
            "no-ext",
            "empty",
        ],
    )
    def test_slug_from_filename_derives_slug(self, name, slug):
        # Arrange / Act
        result = fet._slug_from_filename(name)
        # Assert
        assert result == slug


# --------------------------------------------------------------------------- file_info
def _patch_info(monkeypatch, reader, pl_pages):
    class _PlDoc:
        pages = pl_pages

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return None

    monkeypatch.setattr(pypdf, "PdfReader", lambda stream: reader)
    monkeypatch.setattr(pdfplumber, "open", lambda stream: _PlDoc())


class _FakeReader:
    def __init__(
        self, *, encrypted=False, decrypt=True, metadata=None, outline=None, raises=()
    ):
        self.pages = [object()]
        self.is_encrypted = encrypted
        self._decrypt = decrypt
        self._metadata = metadata
        self._outline = outline
        self._raises = set(raises)

    def decrypt(self, password):
        if "decrypt" in self._raises:
            raise RuntimeError("bad")
        return self._decrypt

    @property
    def metadata(self):
        if "metadata" in self._raises:
            raise RuntimeError("bad")
        return self._metadata

    @property
    def outline(self):
        if "outline" in self._raises:
            raise RuntimeError("bad")
        return self._outline


class _FakePlPage:
    def __init__(self, text, images):
        self._text = text
        self.images = images

    def extract_text(self):
        return self._text


class TestFileInfo:
    # Plan #22 | B12
    @pytest.mark.parametrize("arg", ["", "   "], ids=["empty", "blank"])
    def test_file_info_reports_no_uploads_when_directory_empty(self, root, arg):
        # Arrange
        (root / ".uploads").mkdir()
        # Act
        result = fet.file_info(arg)
        # Assert
        assert result == "No uploads in this run."

    # Plan #23 | B12
    def test_file_info_returns_error_when_unbound(self, unbound):
        # Arrange / Act
        result = fet.file_info()
        # Assert
        assert result == NOT_BOUND

    # Plan #24 | B12
    def test_file_info_lists_statuses_when_uploads_present(self, root):
        # Arrange
        _upload(root, "a.txt", b"x")
        _upload(root, "b.pdf", b"x")
        _upload(root, "c.png", b"x")
        # Act
        result = fet.file_info()
        # Assert
        assert result == (
            "Uploads in this run:\n\n"
            "  • a.txt — ✓ plain text — extract_text returns its content directly\n"
            "  • b.pdf — ✓ extract_text materialises it into .extract/\n"
            f"  • c.png — ✗ unsupported — these tools read {SUPPORTED}"
        )

    # Plan #25 | B13
    def test_file_info_profiles_text_file_when_text_format(self, root):
        # Arrange
        rel = _upload(root, "n.txt", "héllo\nwörld\n")
        # Act
        result = fet.file_info(rel)
        # Assert
        assert result == (
            "n.txt — plain text (.txt)\n"
            "  12 characters, 2 lines\n"
            "  No pages, no images, nothing to materialise. extract_text returns "
            "its content directly."
        )

    # Plan #26 | B13,B7
    def test_file_info_returns_missing_message_when_text_file_absent(self, root):
        # Arrange / Act
        result = fet.file_info(".uploads/n.txt")
        # Assert
        assert result == "path is not a file: .uploads/n.txt"

    # Plan #26 | B13,B7
    def test_file_info_mentions_surviving_pages_when_text_source_gone(self, root):
        # Arrange
        _manifest(root, "txt", "n")
        # Act
        result = fet.file_info(".uploads/n.txt")
        # Assert
        assert result.startswith(
            "path is not a file: .uploads/n.txt — but its materialised pages survive at .extract/txt/n/."
        )

    # Plan #27 | B14
    def test_file_info_returns_read_error_when_pdf_path_missing(self, root):
        # Arrange / Act
        result = fet.file_info(".uploads/x.pdf")
        # Assert
        assert result == "path is not a file: .uploads/x.pdf"

    # Plan #28 | B14
    def test_file_info_reports_libraries_unavailable_when_import_fails(
        self, root, monkeypatch
    ):
        # Arrange
        rel = _upload(root, "x.pdf", b"%PDF")
        monkeypatch.setitem(sys.modules, "pypdf", None)
        # Act
        result = fet.file_info(rel)
        # Assert
        assert result.startswith("PDF libraries unavailable:")

    # Plan #29 | B14
    def test_file_info_reports_failed_to_read_when_pypdf_rejects_bytes(self, root):
        # Arrange
        rel = _upload(root, "x.pdf", b"this is not a pdf")
        # Act
        result = fet.file_info(rel)
        # Assert
        assert result.startswith("Failed to read PDF:")

    # Plan #30 | B15
    @pytest.mark.parametrize(
        ("reader_kwargs", "expected"),
        [
            ({}, "Encryption: not encrypted"),
            (
                {"encrypted": True, "decrypt": True},
                "Encryption: encrypted (openable with empty password)",
            ),
            ({"encrypted": True, "decrypt": False}, "Encryption: encrypted (locked)"),
            (
                {"encrypted": True, "raises": ["decrypt"]},
                "Encryption: encrypted (unparseable)",
            ),
        ],
        ids=["plain", "empty-password", "locked", "unparseable"],
    )
    def test_file_info_reports_encryption_state(
        self, root, monkeypatch, reader_kwargs, expected
    ):
        # Arrange
        rel = _upload(root, "x.pdf", b"%PDF")
        _patch_info(monkeypatch, _FakeReader(**reader_kwargs), [_FakePlPage("", [])])
        # Act
        result = fet.file_info(rel)
        # Assert
        assert expected in result.splitlines()

    # Plan #31 | B16
    def test_file_info_reports_metadata_sorted_when_present(self, root, monkeypatch):
        # Arrange
        rel = _upload(root, "x.pdf", b"%PDF")
        meta = {"/Author": "A", "/Producer": "P", "/CreationDate": "C", "/ModDate": "M"}
        _patch_info(monkeypatch, _FakeReader(metadata=meta), [_FakePlPage("", [])])
        # Act
        result = fet.file_info(rel)
        # Assert
        assert (
            "Metadata:\n  author: A\n  created: C\n  modified: M\n  producer: P\n"
            in result
        )

    # Plan #31 | B16
    @pytest.mark.parametrize(
        "meta",
        [None, {}, {"/Title": "only-title"}],
        ids=["none", "empty", "no-known-keys"],
    )
    def test_file_info_omits_metadata_block_when_no_known_keys(
        self, root, monkeypatch, meta
    ):
        # Arrange
        rel = _upload(root, "x.pdf", b"%PDF")
        _patch_info(monkeypatch, _FakeReader(metadata=meta), [_FakePlPage("", [])])
        # Act
        result = fet.file_info(rel)
        # Assert
        assert "Metadata:" not in result

    # Plan #31 | B19
    def test_file_info_omits_metadata_block_when_metadata_access_raises(
        self, root, monkeypatch
    ):
        # Arrange
        rel = _upload(root, "x.pdf", b"%PDF")
        _patch_info(
            monkeypatch, _FakeReader(raises=["metadata"]), [_FakePlPage("", [])]
        )
        # Act
        result = fet.file_info(rel)
        # Assert
        assert "Metadata:" not in result
        assert "Pages: 1" in result

    # Plan #32 | B17
    @pytest.mark.parametrize(
        ("kwargs", "expected"),
        [
            ({"outline": [1, 2, 3]}, "Outline: 3 entries"),
            ({"outline": []}, "Outline: 0 entries"),
            ({"raises": ["outline"]}, "Outline: 0 entries"),
        ],
        ids=["three", "empty", "raises"],
    )
    def test_file_info_counts_outline_entries(
        self, root, monkeypatch, kwargs, expected
    ):
        # Arrange
        rel = _upload(root, "x.pdf", b"%PDF")
        _patch_info(monkeypatch, _FakeReader(**kwargs), [_FakePlPage("", [])])
        # Act
        result = fet.file_info(rel)
        # Assert
        assert expected in result.splitlines()

    # Plan #33 | B18
    @pytest.mark.parametrize(
        ("text", "verdict"),
        [
            ("x" * 99, "minimal/no text layer"),
            ("x" * 100, "text layer present"),
            ("x" * 101, "text layer present"),
            (None, "minimal/no text layer"),
        ],
        ids=["99", "100", "101", "none"],
    )
    def test_file_info_reports_text_layer_verdict_at_threshold(
        self, root, monkeypatch, text, verdict
    ):
        # Arrange
        rel = _upload(root, "x.pdf", b"%PDF")
        _patch_info(monkeypatch, _FakeReader(), [_FakePlPage(text, [])])
        # Act
        result = fet.file_info(rel)
        # Assert
        assert f"] {verdict}, 0 image(s)" in result

    # Plan #33 | B18
    def test_file_info_estimates_tokens_as_quarter_of_characters(
        self, root, monkeypatch
    ):
        # Arrange
        rel = _upload(root, "x.pdf", b"%PDF")
        _patch_info(monkeypatch, _FakeReader(), [_FakePlPage("x" * 100, [])])
        # Act
        result = fet.file_info(rel)
        # Assert
        assert "  Total characters: 100\n" in result
        assert result.endswith("  Estimated tokens to read: ~25")

    # Plan #34 | B18
    @pytest.mark.parametrize(
        ("images", "count"),
        [([], 0), (None, 0), ([{}, {}], 2)],
        ids=["empty", "none", "two"],
    )
    def test_file_info_counts_images_per_page(self, root, monkeypatch, images, count):
        # Arrange
        rel = _upload(root, "x.pdf", b"%PDF")
        _patch_info(monkeypatch, _FakeReader(), [_FakePlPage("", images)])
        # Act
        result = fet.file_info(rel)
        # Assert
        assert f", {count} image(s)" in result
        assert f"  Total images: {count}" in result

    # Plan #35 | B19
    def test_file_info_returns_error_when_analysis_raises(self, root, monkeypatch):
        # Arrange
        rel = _upload(root, "x.pdf", b"%PDF")
        monkeypatch.setattr(pypdf, "PdfReader", lambda stream: _FakeReader())
        monkeypatch.setattr(
            pdfplumber, "open", mock.Mock(side_effect=RuntimeError("boom"))
        )
        # Act
        result = fet.file_info(rel)
        # Assert
        assert result == "Error analyzing PDF: boom"

    # Plan #36 | B15,B17,B18,B19
    def test_file_info_reports_real_pdf_summary_when_valid_pdf(self, root):
        # Arrange
        rel = _upload(root, "doc.pdf", _make_pdf(["Hello", "Worlds"]))
        # Act
        result = fet.file_info(rel)
        # Assert
        assert result == (
            "Document: doc.pdf\n\n"
            "Pages: 2\n"
            "Encryption: not encrypted\n"
            "Outline: 0 entries\n\n"
            "Per-page text analysis:\n\n"
            "  Page  1:    5 chars [threshold: 100] minimal/no text layer, 0 image(s)\n"
            "  Page  2:    6 chars [threshold: 100] minimal/no text layer, 0 image(s)\n\n"
            "Totals:\n"
            "  Total characters: 11\n"
            "  Total images: 0\n"
            "  Estimated tokens to read: ~2"
        )


# --------------------------------------------------------------------------- geometry
class TestMergeImageFragments:
    @staticmethod
    def _box(x0, x1, top, bottom):
        return {"x0": x0, "x1": x1, "top": top, "bottom": bottom}

    # Plan #37 | B20
    def test_merge_image_fragments_returns_empty_when_no_images(self):
        # Arrange / Act
        result = fet._merge_image_fragments([])
        # Assert
        assert result == []

    # Plan #38 | B20
    def test_merge_image_fragments_sets_parts_one_when_single_image(self):
        # Arrange / Act
        result = fet._merge_image_fragments([self._box(0, 10, 0, 10)])
        # Assert
        assert result == [{"x0": 0, "x1": 10, "top": 0, "bottom": 10, "parts": 1}]

    # Plan #39 | B20
    @pytest.mark.parametrize(
        ("second", "merged"),
        [
            ((0, 10, 20, 30), True),
            ((0, 10, 22, 30), True),
            ((0, 10, 22.01, 30), False),
            ((0, 10, 5, 30), True),
        ],
        ids=["gap-0", "gap-2.0", "gap-2.01", "vertical-overlap"],
    )
    def test_merge_image_fragments_merges_only_when_gap_within_limit(
        self, second, merged
    ):
        # Arrange
        first = {"x0": 0, "x1": 10, "top": 0, "bottom": 20}
        other = self._box(*second)
        # Act
        result = fet._merge_image_fragments([first, other])
        # Assert
        if merged:
            assert result == [
                {"x0": 0, "x1": 10, "top": 0, "bottom": max(20, second[3]), "parts": 2}
            ]
        else:
            assert [r["parts"] for r in result] == [1, 1]
            assert len(result) == 2

    # Plan #40 | B20
    def test_merge_image_fragments_keeps_separate_when_x_ranges_only_touch(self):
        # Arrange
        a = self._box(0, 10, 0, 20)
        b = self._box(10, 20, 20, 40)
        # Act
        result = fet._merge_image_fragments([a, b])
        # Assert
        assert result == [dict(a, parts=1), dict(b, parts=1)]

    # Plan #41 | B20
    def test_merge_image_fragments_sorts_before_merging_and_chains_three(self):
        # Arrange
        boxes = [
            self._box(5, 15, 40, 60),
            self._box(0, 10, 0, 20),
            self._box(2, 12, 20, 40),
        ]
        # Act
        result = fet._merge_image_fragments(boxes)
        # Assert
        assert result == [{"x0": 0, "x1": 15, "top": 0, "bottom": 60, "parts": 3}]


class _FakePage:
    def __init__(self, words=(), images=None, width=100.0, height=200.0):
        self._words = list(words)
        self.images = images
        self.width = width
        self.height = height
        self.kwargs: dict[str, Any] = {}

    def extract_words(self, **kwargs):
        self.kwargs = kwargs
        return self._words


class TestReadingOrderItems:
    # Plan #42 | B21
    def test_reading_order_items_interleaves_text_and_images_by_top(self):
        # Arrange
        page = _FakePage(
            words=[
                {"text": "a", "top": 10.2},
                {"text": "b", "top": 10.4},
                {"text": "c", "top": 30.0},
            ],
            images=[{"x0": 0, "x1": 50, "top": 20, "bottom": 40, "extra": 1}],
        )
        # Act
        result = fet._reading_order_items(page)
        # Assert
        assert result == [
            (10.0, "text", "a b"),
            (20, "image", {"x0": 0, "x1": 50, "top": 20, "bottom": 40, "parts": 1}),
            (30.0, "text", "c"),
        ]
        assert page.kwargs == {"x_tolerance": 1.5}

    # Plan #43 | B21
    def test_reading_order_items_puts_text_first_when_tie(self):
        # Arrange
        page = _FakePage(
            words=[{"text": "t", "top": 20.0}],
            images=[{"x0": 0, "x1": 5, "top": 20, "bottom": 30}],
        )
        # Act
        result = fet._reading_order_items(page)
        # Assert
        assert [kind for _, kind, _ in result] == ["text", "image"]

    # Plan #44 | B21
    @pytest.mark.parametrize("images", [None, []], ids=["none", "empty"])
    def test_reading_order_items_returns_empty_when_no_words_or_images(self, images):
        # Arrange / Act
        result = fet._reading_order_items(_FakePage(images=images))
        # Assert
        assert result == []


class TestCropBox:
    # Plan #45 | B22
    def test_crop_box_for_image_scales_to_pixels_when_inside_bounds(self):
        # Arrange
        image = {"x0": 10, "x1": 30, "top": 20, "bottom": 40}
        # Act
        result = fet._crop_box_for_image(image, 100, 200, 200, 400)
        # Assert
        assert result == (20, 40, 60, 80)

    # Plan #46 | B22
    @pytest.mark.parametrize(
        "image",
        [
            {"x0": -5, "x1": 100, "top": -5, "bottom": 200},
            {"x0": 0, "x1": 150, "top": 0, "bottom": 300},
        ],
        ids=["negative", "overflow"],
    )
    def test_crop_box_for_image_clamps_when_outside_bounds(self, image):
        # Arrange / Act
        result = fet._crop_box_for_image(image, 100, 200, 200, 400)
        # Assert
        assert result == (0, 0, 200, 400)


class _FakeCrop:
    def __init__(self, box):
        self.width = box[2] - box[0]
        self.height = box[3] - box[1]

    def save(self, path):
        Path(path).write_bytes(b"png")


class _FakeRender:
    width = 200
    height = 400

    def __init__(self):
        self.boxes: list[tuple[int, int, int, int]] = []

    def crop(self, box):
        self.boxes.append(box)
        return _FakeCrop(box)


class TestMaterializePage:
    # Plan #47 | B23
    def test_materialize_page_writes_text_only_when_no_images(self, tmp_path):
        # Arrange
        page = _FakePage(
            words=[{"text": "hello", "top": 1.0}, {"text": "world", "top": 1.2}]
        )
        # Act
        receipt = fet._materialize_page(page, _FakeRender(), tmp_path)
        # Assert
        assert receipt == {
            "text_md": "hello world",
            "images": [],
            "chars": 11,
            "raw_images": 0,
            "merged_images": 0,
        }
        assert (tmp_path / "text.md").read_text() == "hello world"

    # Plan #48 | B23
    def test_materialize_page_crops_images_when_images_present(self, tmp_path):
        # Arrange
        page = _FakePage(
            words=[{"text": "Intro", "top": 5.0}],
            images=[
                {"x0": 10, "x1": 30, "top": 20, "bottom": 40},
                {"x0": 10, "x1": 30, "top": 100, "bottom": 120},
                {"x0": 10, "x1": 30, "top": 121, "bottom": 140},
            ],
        )
        render = _FakeRender()
        # Act
        receipt = fet._materialize_page(page, render, tmp_path)
        # Assert
        assert render.boxes == [(20, 40, 60, 80), (20, 200, 60, 280)]
        assert receipt["text_md"] == (
            "Intro\n"
            "\n@[[image-1.png]]  <!-- 40x40, 1 source object -->\n"
            "\n"
            "\n@[[image-2.png]]  <!-- 40x80, 2 source objects -->\n"
        )
        assert receipt["images"] == ["image-1.png", "image-2.png"]
        assert (receipt["chars"], receipt["raw_images"], receipt["merged_images"]) == (
            5,
            3,
            2,
        )
        assert (tmp_path / "image-1.png").read_bytes() == b"png"
        assert (tmp_path / "image-2.png").read_bytes() == b"png"


# --------------------------------------------------------------------------- sharding
class TestBuildShards:
    # Plan #49 | B24
    def test_build_shards_returns_empty_when_no_pages(self):
        # Arrange / Act
        result = fet._build_shards("doc", "pdf", [], {})
        # Assert
        assert result == []

    # Plan #50 | B24
    def test_build_shards_packs_contiguous_pages_within_budget(self):
        # Arrange
        tokens = {1: 50_000, 2: 50_000, 3: 50_000}
        # Act
        result = fet._build_shards("doc", "pdf", [1, 2, 3], tokens)
        # Assert
        assert result == [
            {
                "id": "doc-s01",
                "slug": "doc",
                "format": "pdf",
                "pages": [1, 2],
                "page_range": "1-2",
                "est_tokens": 100_000,
                "source": ".extract/pdf/doc/pages/",
                "out": "shards/doc-s01/",
                "over_budget": False,
            },
            {
                "id": "doc-s02",
                "slug": "doc",
                "format": "pdf",
                "pages": [3],
                "page_range": "3",
                "est_tokens": 50_000,
                "source": ".extract/pdf/doc/pages/",
                "out": "shards/doc-s02/",
                "over_budget": False,
            },
        ]

    # Plan #51 | B24
    @pytest.mark.parametrize(
        ("second", "count"),
        [(55_000, 1), (55_001, 2)],
        ids=["at-usable", "over-by-one"],
    )
    def test_build_shards_splits_only_above_usable_boundary(self, second, count):
        # Arrange
        tokens = {1: 50_000, 2: second}
        # Act
        result = fet._build_shards("d", "pdf", [1, 2], tokens)
        # Assert
        assert len(result) == count

    # Plan #52 | B24
    def test_build_shards_splits_when_page_cap_reached(self):
        # Arrange / Act
        result = fet._build_shards("d", "pdf", [1, 2, 3], {}, page_cap=2)
        # Assert
        assert [s["pages"] for s in result] == [[1, 2], [3]]

    # Plan #53 | B24
    def test_build_shards_flags_over_budget_when_single_page_exceeds(self):
        # Arrange / Act
        result = fet._build_shards("d", "pdf", [1], {1: 200_000})
        # Assert
        assert [(s["pages"], s["over_budget"]) for s in result] == [([1], True)]

    # Plan #54 | B24
    @pytest.mark.parametrize(
        ("model", "count"),
        [("nope", 2), ("haiku-4.5", 2), ("sonnet-5", 1)],
        ids=["unknown", "haiku", "sonnet5"],
    )
    def test_build_shards_selects_budget_by_model_when_model_given(self, model, count):
        # Arrange
        tokens = {1: 60_000, 2: 60_000}
        # Act
        result = fet._build_shards("d", "pdf", [1, 2], tokens, model=model)
        # Assert
        assert len(result) == count

    # Plan #55 | B24
    def test_build_shards_treats_missing_page_tokens_as_zero(self):
        # Arrange / Act
        result = fet._build_shards("d", "pdf", [1, 2], {})
        # Assert
        assert [(s["page_range"], s["est_tokens"]) for s in result] == [("1-2", 0)]


class TestSplitIntoRanges:
    # Plan #56 | B25
    @pytest.mark.parametrize(
        ("pages", "expected"),
        [
            ([], []),
            ([1], [[1]]),
            ([1, 2, 3, 4, 5], [[1, 2], [3, 4], [5]]),
            ([1, 2, 3, 4, 5, 6, 7, 8], [[1, 2], [3, 4], [5, 6], [7, 8]]),
        ],
        ids=["zero", "one", "five", "eight"],
    )
    def test_split_into_ranges_chunks_contiguously(self, pages, expected):
        # Arrange / Act
        result = fet._split_into_ranges(pages, 4)
        # Assert
        assert result == expected


# --------------------------------------------------------------------------- workers
class TestMaterializePageRange:
    # Plan #57 | B26
    def test_materialize_page_range_materialises_each_page_when_pdf_valid(
        self, tmp_path
    ):
        # Arrange
        pdf = _make_pdf(["Alpha", "Beta"])
        # Act
        receipts = fet._materialize_page_range(pdf, [1, 2], str(tmp_path))
        # Assert
        assert sorted(receipts) == [1, 2]
        assert receipts[1]["text_md"] == "Alpha"
        assert receipts[2]["chars"] == 4
        assert sorted(p.name for p in tmp_path.iterdir()) == ["01", "02"]
        assert (tmp_path / "02" / "text.md").read_text() == "Beta"

    # Plan #58 | B26
    def test_materialize_page_range_closes_documents_when_page_fails(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        closed: list[int] = []
        real_pl_open = pdfplumber.open
        real_doc = pypdfium2.PdfDocument

        class _SpyFium:
            def __init__(self, data):
                self._d = real_doc(data)

            def __getitem__(self, i):
                return self._d[i]

            def close(self):
                closed.append(2)
                self._d.close()

        monkeypatch.setattr(
            pdfplumber, "open", lambda s: _CloseSpy(real_pl_open(s), closed)
        )
        monkeypatch.setattr(pypdfium2, "PdfDocument", _SpyFium)
        monkeypatch.setattr(
            fet, "_materialize_page", mock.Mock(side_effect=RuntimeError("bad"))
        )
        # Act / Assert
        with pytest.raises(RuntimeError, match="bad"):
            fet._materialize_page_range(_make_pdf(["A"]), [1], str(tmp_path))
        assert sorted(closed) == [1, 2]


class TestMaterializeParallelSync:
    # Plan #59 | B27,B25
    def test_materialize_parallel_sync_merges_receipts_from_all_ranges(
        self, tmp_path, monkeypatch, inline_pool
    ):
        # Arrange
        worker = mock.Mock(side_effect=lambda pdf, rng, d: {n: {"r": n} for n in rng})
        monkeypatch.setattr(fet, "_materialize_page_range", worker)
        # Act
        result = fet._materialize_parallel_sync(b"PDF", list(range(1, 10)), tmp_path)
        # Assert
        assert result == {n: {"r": n} for n in range(1, 10)}
        assert inline_pool[0].max_workers == 4
        assert [args[1] for args in inline_pool[0].submitted] == [
            [1, 2, 3],
            [4, 5, 6],
            [7, 8, 9],
        ]
        assert all(args[2] == str(tmp_path) for args in inline_pool[0].submitted)


# --------------------------------------------------------------------------- conversion
def _fake_convert(content: bytes = b"PDF2"):
    def convert(src, out_dir, *args, **kwargs):
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / "x.pdf"
        out.write_bytes(content)
        return out, ""

    return mock.create_autospec(soffice.convert_to_pdf, side_effect=convert)


class TestConvertedPdf:
    # Plan #60 | B28
    def test_converted_pdf_returns_cached_bytes_when_source_pdf_exists(
        self, root, monkeypatch
    ):
        # Arrange
        doc_dir = root / "d"
        doc_dir.mkdir()
        (doc_dir / "source.pdf").write_bytes(b"PDF")
        conv = mock.create_autospec(soffice.convert_to_pdf)
        monkeypatch.setattr(fet.soffice, "convert_to_pdf", conv)
        # Act
        result = fet._converted_pdf(".uploads/a.docx", doc_dir)
        # Assert
        assert result == (b"PDF", "libreoffice", "")
        conv.assert_not_called()

    # Plan #61 | B28
    def test_converted_pdf_reports_cache_read_error_when_read_fails(
        self, root, monkeypatch
    ):
        # Arrange
        doc_dir = root / "d"
        doc_dir.mkdir()
        (doc_dir / "source.pdf").write_bytes(b"PDF")
        monkeypatch.setattr(Path, "read_bytes", mock.Mock(side_effect=OSError("x")))
        # Act
        result = fet._converted_pdf(".uploads/a.docx", doc_dir)
        # Assert
        assert result == (None, None, "failed to read the cached conversion: x")

    # Plan #62 | B28
    def test_converted_pdf_returns_resolve_error_when_sandbox_rejects(self, root):
        # Arrange / Act
        result = fet._converted_pdf("../a.docx", root / "d")
        # Assert
        assert result == (None, None, "path rejected: escapes root: ../a.docx")

    # Plan #63 | B28
    def test_converted_pdf_reports_mkdir_failure_when_doc_dir_uncreatable(self, root):
        # Arrange
        blocker = root / "afile"
        blocker.write_text("x")
        # Act
        result = fet._converted_pdf(".uploads/a.docx", blocker / "doc")
        # Assert
        assert result[:2] == (None, None)
        assert result[2].startswith("cannot create doc: ")

    # Plan #64 | B28
    @pytest.mark.parametrize(
        ("returned", "message"),
        [((None, "boom"), "boom"), ((None, ""), "conversion produced no output")],
        ids=["error", "no-output"],
    )
    def test_converted_pdf_returns_conversion_error_when_soffice_fails(
        self, root, monkeypatch, returned, message
    ):
        # Arrange
        conv = mock.create_autospec(soffice.convert_to_pdf, return_value=returned)
        monkeypatch.setattr(fet.soffice, "convert_to_pdf", conv)
        doc_dir = root / "d"
        # Act
        result = fet._converted_pdf(".uploads/a.docx", doc_dir)
        # Assert
        assert result == (None, None, message)
        assert [p.name for p in doc_dir.iterdir()] == []

    # Plan #65 | B28
    def test_converted_pdf_moves_output_into_cache_when_conversion_succeeds(
        self, root, monkeypatch
    ):
        # Arrange
        conv = _fake_convert(b"PDF2")
        monkeypatch.setattr(fet.soffice, "convert_to_pdf", conv)
        doc_dir = root / "d"
        # Act
        result = fet._converted_pdf(".uploads/a.docx", doc_dir)
        # Assert
        assert result == (b"PDF2", "libreoffice", "")
        assert (doc_dir / "source.pdf").read_bytes() == b"PDF2"
        assert [p.name for p in doc_dir.iterdir()] == ["source.pdf"]
        conv.assert_called_once()
        assert conv.call_args.args[0] == (root / ".uploads" / "a.docx").resolve()
        assert conv.call_args.args[1].parent == doc_dir

    # Plan #66 | B28
    def test_converted_pdf_reports_conversion_failed_when_replace_raises(
        self, root, monkeypatch
    ):
        # Arrange
        monkeypatch.setattr(fet.soffice, "convert_to_pdf", _fake_convert())
        monkeypatch.setattr(fet.os, "replace", mock.Mock(side_effect=OSError("r")))
        # Act
        result = fet._converted_pdf(".uploads/a.docx", root / "d")
        # Assert
        assert result == (None, None, "conversion failed: r")

    # Plan #67 | B28
    def test_converted_pdf_reports_read_error_when_final_read_fails(
        self, root, monkeypatch
    ):
        # Arrange
        monkeypatch.setattr(fet.soffice, "convert_to_pdf", _fake_convert())
        monkeypatch.setattr(Path, "read_bytes", mock.Mock(side_effect=OSError("x")))
        # Act
        result = fet._converted_pdf(".uploads/a.docx", root / "d")
        # Assert
        assert result == (None, None, "failed to read the conversion: x")


# --------------------------------------------------------------------------- manifest helpers
class TestIterDocumentDirs:
    # Plan #68 | B29
    def test_iter_document_dirs_lists_sorted_documents_with_manifest(self, tmp_path):
        # Arrange
        ext = tmp_path / ".extract"
        for fmt, slug in [
            ("pdf", "b"),
            ("pdf", "a"),
            ("docx", "c"),
            (".hid", "z"),
            ("pdf", ".hidden"),
        ]:
            d = ext / fmt / slug
            d.mkdir(parents=True)
            (d / "manifest.json").write_text("{}")
        (ext / "pdf" / "nomanifest").mkdir()
        (ext / "stray.txt").write_text("x")
        # Act
        result = fet._iter_document_dirs(ext)
        # Assert
        assert result == [
            ("docx", "c", ext / "docx" / "c"),
            ("pdf", "a", ext / "pdf" / "a"),
            ("pdf", "b", ext / "pdf" / "b"),
        ]

    # Plan #69 | B29
    def test_iter_document_dirs_returns_empty_when_root_missing(self, tmp_path):
        # Arrange / Act
        result = fet._iter_document_dirs(tmp_path / "nope")
        # Assert
        assert result == []


class TestLoadManifest:
    # Plan #70 | B30
    def test_load_manifest_returns_none_when_absent(self, tmp_path):
        # Arrange / Act
        result = fet._load_manifest(tmp_path / "manifest.json")
        # Assert
        assert result is None

    # Plan #70 | B30
    def test_load_manifest_returns_dict_when_valid(self, tmp_path):
        # Arrange
        (tmp_path / "manifest.json").write_text('{"a": 1}')
        # Act
        result = fet._load_manifest(tmp_path / "manifest.json")
        # Assert
        assert result == {"a": 1}

    # Plan #70 | B30
    def test_load_manifest_returns_none_when_json_invalid(self, tmp_path):
        # Arrange
        (tmp_path / "manifest.json").write_text("{not json")
        # Act
        result = fet._load_manifest(tmp_path / "manifest.json")
        # Assert
        assert result is None

    # Plan #70 | B30
    def test_load_manifest_returns_none_when_read_raises_oserror(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        (tmp_path / "manifest.json").write_text("{}")
        monkeypatch.setattr(Path, "read_text", mock.Mock(side_effect=OSError("x")))
        # Act
        result = fet._load_manifest(tmp_path / "manifest.json")
        # Assert
        assert result is None


class TestParsePagesSelector:
    # Plan #71 | B31
    @pytest.mark.parametrize("value", ["", "  "], ids=["empty", "blank"])
    def test_parse_pages_selector_returns_all_pages_when_empty(self, value):
        # Arrange / Act
        result = fet._parse_pages_selector(value, 3)
        # Assert
        assert result == ([1, 2, 3], "")

    # Plan #72 | B31
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("2", [2]),
            ("1-3", [1, 2, 3]),
            ("1,3,4-5", [1, 3, 4, 5]),
            (" 1 , ,3 ", [1, 3]),
            ("3,1,3", [1, 3]),
            ("1", [1]),
            ("5", [5]),
            ("1-5", [1, 2, 3, 4, 5]),
        ],
        ids=["single", "range", "mixed", "blanks", "dupes", "min", "max", "full-range"],
    )
    def test_parse_pages_selector_parses_valid_selector(self, value, expected):
        # Arrange / Act
        result = fet._parse_pages_selector(value, 5)
        # Assert
        assert result == (expected, "")

    # Plan #73 | B31
    @pytest.mark.parametrize(
        ("value", "error"),
        [
            ("a-b", "invalid page range: 'a-b'"),
            ("-1", "invalid page range: '-1'"),
            ("0-2", "page range out of bounds (1-5): '0-2'"),
            ("1-6", "page range out of bounds (1-5): '1-6'"),
            ("3-1", "page range out of bounds (1-5): '3-1'"),
            ("x", "invalid page number: 'x'"),
            ("0", "page 0 out of bounds (1-5)"),
            ("6", "page 6 out of bounds (1-5)"),
        ],
        ids=[
            "alpha-range",
            "neg",
            "lo-zero",
            "hi-over",
            "reversed",
            "alpha",
            "zero",
            "over",
        ],
    )
    def test_parse_pages_selector_rejects_invalid_selector(self, value, error):
        # Arrange / Act
        result = fet._parse_pages_selector(value, 5)
        # Assert
        assert result == ([], error)


class TestWriteIfChanged:
    # Plan #74 | B32
    def test_write_if_changed_creates_file_when_absent(self, tmp_path):
        # Arrange
        p = tmp_path / "f.txt"
        # Act
        fet._write_if_changed(p, "new")
        # Assert
        assert p.read_text() == "new"

    # Plan #74 | B32
    def test_write_if_changed_keeps_mtime_when_content_identical(self, tmp_path):
        # Arrange
        p = tmp_path / "f.txt"
        p.write_text("same")
        os.utime(p, ns=(1_000_000_000, 1_000_000_000))
        # Act
        fet._write_if_changed(p, "same")
        # Assert
        assert p.stat().st_mtime_ns == 1_000_000_000

    # Plan #74 | B32
    def test_write_if_changed_overwrites_when_content_differs(self, tmp_path):
        # Arrange
        p = tmp_path / "f.txt"
        p.write_text("old")
        # Act
        fet._write_if_changed(p, "new")
        # Assert
        assert p.read_text() == "new"

    # Plan #74 | B32
    def test_write_if_changed_writes_when_existing_read_raises(
        self, tmp_path, monkeypatch
    ):
        # Arrange
        p = tmp_path / "f.txt"
        p.write_text("old")
        real_write = Path.write_text
        monkeypatch.setattr(Path, "read_text", mock.Mock(side_effect=OSError("x")))
        # Act
        fet._write_if_changed(p, "new")
        monkeypatch.undo()
        # Assert
        assert real_write is Path.write_text
        assert p.read_text() == "new"


class TestInlineText:
    # Plan #75 | B33
    @pytest.mark.parametrize("n", [99_999, 100_000], ids=["limit-1", "limit"])
    def test_inline_text_returns_full_text_when_within_limit(self, root, n):
        # Arrange
        rel = _upload(root, "n.txt", "a" * n)
        # Act
        result = fet._inline_text(rel, "n.txt", "txt")
        # Assert
        assert (
            result
            == f"n.txt (.txt, {n:,} characters) — full text follows.\n\n" + "a" * n
        )

    # Plan #76 | B33
    def test_inline_text_truncates_when_over_limit(self, root):
        # Arrange
        rel = _upload(root, "n.txt", "a" * 100_001)
        # Act
        result = fet._inline_text(rel, "n.txt", "txt")
        # Assert
        assert result == (
            "n.txt (.txt, 100,001 characters) — TRUNCATED to the first 100,000. "
            "Use read_file on .uploads/n.txt to page through the rest.\n\n"
            + "a"
            * 100_000
        )

    # Plan #77 | B33
    def test_inline_text_replaces_invalid_utf8_and_counts_characters(self, root):
        # Arrange
        rel = _upload(root, "n.txt", b"a\xffb")
        # Act
        result = fet._inline_text(rel, "n.txt", "txt")
        # Assert
        assert result == "n.txt (.txt, 3 characters) — full text follows.\n\na\ufffdb"

    # Plan #77b | B33
    def test_inline_text_returns_empty_body_when_file_empty(self, root):
        # Arrange
        rel = _upload(root, "n.txt", b"")
        # Act
        result = fet._inline_text(rel, "n.txt", "txt")
        # Assert
        assert result == "n.txt (.txt, 0 characters) — full text follows.\n\n"

    # Plan #77c | B33
    def test_inline_text_preserves_unicode_when_multibyte(self, root):
        # Arrange
        rel = _upload(root, "n.md", "日本語✓")
        # Act
        result = fet._inline_text(rel, "n.md", "md")
        # Assert
        assert result == "n.md (.md, 4 characters) — full text follows.\n\n日本語✓"

    # Plan #78 | B33,B7
    def test_inline_text_returns_missing_message_when_absent(self, root):
        # Arrange / Act
        result = fet._inline_text(".uploads/n.txt", "n.txt", "txt")
        # Assert
        assert result == "path is not a file: .uploads/n.txt"


# --------------------------------------------------------------------------- async wrappers / lock
class TestExtractTextAsync:
    # Plan #79 | B34,B35
    async def test_extract_text_returns_sync_result_when_unbound(self, unbound):
        # Arrange / Act
        result = await fet.extract_text("a.pdf")
        # Assert
        assert result == NOT_BOUND

    # Plan #79 | B34,B35
    async def test_extract_text_returns_inline_text_when_awaited_with_bound_sandbox(
        self, root
    ):
        # Arrange
        rel = _upload(root, "n.txt", "hi")
        # Act
        result = await fet.extract_text(rel)
        # Assert
        assert result == "n.txt (.txt, 2 characters) — full text follows.\n\nhi"

    # Plan #80 | B34
    def test_locked_call_returns_function_result_and_releases_lock(self):
        # Arrange / Act
        result = fet._locked_call(lambda a, b: a + b, 2, 3)
        acquired = fet._PDFIUM_LOCK.acquire(blocking=False)
        if acquired:
            fet._PDFIUM_LOCK.release()
        # Assert
        assert result == 5
        assert acquired is True

    # Plan #80b | B34
    def test_locked_call_releases_lock_when_function_raises(self):
        # Arrange / Act / Assert
        with pytest.raises(ValueError, match="boom"):
            fet._locked_call(mock.Mock(side_effect=ValueError("boom")))
        acquired = fet._PDFIUM_LOCK.acquire(blocking=False)
        if acquired:
            fet._PDFIUM_LOCK.release()
        assert acquired is True
        assert isinstance(fet._PDFIUM_LOCK, type(threading.Lock()))


# --------------------------------------------------------------------------- _extract_text_sync
class TestExtractTextSyncRouting:
    # Plan #81 | B36
    def test_extract_text_sync_rejects_unsupported_file_type_when_override_invalid(
        self, root
    ):
        # Arrange / Act
        result = fet._extract_text_sync("a.pdf", "", "exe")
        # Assert
        assert result == (
            "cannot extract a.pdf: file_type='exe' is not a supported format. "
            f"Supported: {SUPPORTED}."
        )

    # Plan #82 | B36
    @pytest.mark.parametrize(
        ("name", "shown"),
        [("a.png", ".png"), ("noext", ".(no extension)")],
        ids=["png", "no-ext"],
    )
    def test_extract_text_sync_rejects_unsupported_extension(self, root, name, shown):
        # Arrange / Act
        result = fet._extract_text_sync(f".uploads/{name}")
        # Assert
        assert result == (
            f"cannot extract {name}: {shown} is not a supported format. Supported: {SUPPORTED}. "
            "If the extension is missing or wrong, pass file_type explicitly."
        )

    # Plan #83 | B37
    @pytest.mark.parametrize("ext", ["txt", "md", "csv", "json"])
    def test_extract_text_sync_returns_inline_text_when_text_format(self, root, ext):
        # Arrange
        rel = _upload(root, f"d.{ext}", "a,b")
        # Act
        result = fet._extract_text_sync(rel)
        # Assert
        assert result == f"d.{ext} (.{ext}, 3 characters) — full text follows.\n\na,b"
        assert not (root / ".extract").exists()

    # Plan #84 | B36,B37
    @pytest.mark.parametrize(
        ("override", "ext"),
        [(" .TXT ", "txt"), ("MD", "md")],
        ids=["dot-upper", "upper"],
    )
    def test_extract_text_sync_normalises_file_type_override(self, root, override, ext):
        # Arrange
        rel = _upload(root, "a.dat", "xyz")
        # Act
        result = fet._extract_text_sync(rel, "", override)
        # Assert
        assert result == f"a.dat (.{ext}, 3 characters) — full text follows.\n\nxyz"

    # Plan #85 | B38
    def test_extract_text_sync_returns_missing_message_when_source_absent(self, root):
        # Arrange / Act
        result = fet._extract_text_sync(".uploads/a.pdf")
        # Assert
        assert result == "path is not a file: .uploads/a.pdf"

    # Plan #85b | B38
    def test_extract_text_sync_returns_error_when_unbound(self, unbound):
        # Arrange / Act
        result = fet._extract_text_sync("a.pdf")
        # Assert
        assert result == NOT_BOUND

    # Plan #86 | B39
    def test_extract_text_sync_returns_error_when_doc_dir_unresolvable(self, root):
        # Arrange
        rel = _upload(root, "a.pdf", _make_pdf(["A"]))
        fet.bind_sandbox(_Sandbox(root, deny=(".extract",)))
        # Act
        result = fet._extract_text_sync(rel)
        # Assert
        assert result == "path rejected: denied: .extract/pdf/a"

    # Plan #86b | B6
    def test_extract_text_sync_rejects_traversal_when_path_escapes(self, root):
        # Arrange / Act
        result = fet._extract_text_sync("../../a.pdf")
        # Assert
        assert result == "path rejected: escapes root: ../../a.pdf"


EXPECTED_SHA_INPUT = _make_pdf(["Alpha", "Beta"])


class TestExtractTextSyncMaterialise:
    # Plan #87 | B35,B41,B46,B48,B50,B51
    def test_extract_text_sync_materialises_pdf_and_returns_receipt_when_valid_pdf(
        self, root
    ):
        # Arrange
        rel = _upload(root, "a.pdf", EXPECTED_SHA_INPUT)
        # Act
        result = fet._extract_text_sync(rel)
        # Assert
        assert result == (
            "Materialised a.pdf -> .extract/pdf/a/ (2 page(s) total)\n\n"
            "Processed: 2 page(s) — 1, 2\n"
            "  images this run: 0 raw -> 0 after merge\n"
            "Skipped (already present): 0 page(s)\n\n"
            "Document totals: 2/2 page(s) complete, 9 characters, 0 raw images -> 0 after merge\n"
            "Estimated tokens to read document.md + all images: ~2\n"
            "Shards: 1 — a-s01 pages 1-2 (~2 tok)\n\n"
            "Read it with: read_file .extract/pdf/a/document.md"
        )

    # Plan #87 | B35,B46,B48,B50
    def test_extract_text_sync_writes_manifest_and_document_when_valid_pdf(self, root):
        # Arrange
        rel = _upload(root, "a.pdf", EXPECTED_SHA_INPUT)
        # Act
        fet._extract_text_sync(rel)
        # Assert
        doc_dir = root / ".extract" / "pdf" / "a"
        manifest = json.loads((doc_dir / "manifest.json").read_text())
        assert manifest["source"] == "a.pdf"
        assert (
            manifest["source_sha256"] == hashlib.sha256(EXPECTED_SHA_INPUT).hexdigest()
        )
        assert manifest["source_format"] == "pdf"
        assert manifest["converted_by"] is None
        assert manifest["slug"] == "a"
        assert manifest["page_count"] == 2
        assert manifest["scale"] == 2.0
        assert manifest["pages"] == {
            "1": {"images": [], "chars": 5, "raw_images": 0, "merged_images": 0},
            "2": {"images": [], "chars": 4, "raw_images": 0, "merged_images": 0},
        }
        assert manifest["shard_basis"] == {
            "safe_budget": 120000,
            "agent_reserve": 15000,
            "usable": 105000,
            "model": "haiku-4.5",
            "page_cap": 100,
        }
        assert manifest["totals"] == {"raw_images": 0, "after_merge": 0, "unique": 0}
        assert (doc_dir / "document.md").read_text() == (
            "\n\n<!-- ================= PAGE 1 ================= -->\n\nAlpha"
            "\n\n<!-- ================= PAGE 2 ================= -->\n\nBeta"
        )

    # Plan #88 | B40,B46,B50,B51,B48
    def test_extract_text_sync_skips_existing_pages_and_keeps_created_at_when_resumed(
        self, root
    ):
        # Arrange
        rel = _upload(root, "a.pdf", EXPECTED_SHA_INPUT)
        fet._extract_text_sync(rel)
        manifest_path = root / ".extract" / "pdf" / "a" / "manifest.json"
        first_created = json.loads(manifest_path.read_text())["created_at"]
        os.utime(manifest_path, ns=(5_000_000_000, 5_000_000_000))
        # Act
        result = fet._extract_text_sync(rel)
        # Assert
        assert "Processed: 0 pages (nothing new to materialise)\n" in result
        assert "Skipped (already present): 2 page(s)\n" in result
        assert json.loads(manifest_path.read_text())["created_at"] == first_created
        assert manifest_path.stat().st_mtime_ns == 5_000_000_000

    # Plan #88b | B48
    def test_extract_text_sync_skips_rendering_when_nothing_to_build(
        self, root, monkeypatch
    ):
        # Arrange
        rel = _upload(root, "a.pdf", EXPECTED_SHA_INPUT)
        fet._extract_text_sync(rel)
        boom = mock.Mock(side_effect=RuntimeError("must not open"))
        monkeypatch.setattr(pypdfium2, "PdfDocument", boom)
        # Act
        result = fet._extract_text_sync(rel)
        # Assert
        assert result.startswith(
            "Materialised a.pdf -> .extract/pdf/a/ (2 page(s) total)"
        )
        boom.assert_not_called()

    # Plan #89 | B40
    def test_extract_text_sync_rebuilds_from_scratch_when_source_bytes_changed(
        self, root
    ):
        # Arrange
        rel = _upload(root, "a.pdf", _make_pdf(["Alpha", "Beta"]))
        fet._extract_text_sync(rel)
        doc_dir = root / ".extract" / "pdf" / "a"
        (doc_dir / "stale.marker").write_text("x")
        new_bytes = _make_pdf(["Gamma", "Delta"])
        _upload(root, "a.pdf", new_bytes)
        # Act
        result = fet._extract_text_sync(rel)
        # Assert
        assert "Processed: 2 page(s) — 1, 2\n" in result
        assert not (doc_dir / "stale.marker").exists()
        assert json.loads((doc_dir / "manifest.json").read_text())["source_sha256"] == (
            hashlib.sha256(new_bytes).hexdigest()
        )
        assert (doc_dir / "pages" / "01" / "text.md").read_text() == "Gamma"

    # Plan #90 | B46
    def test_extract_text_sync_redoes_deleted_page_when_resumed(self, root):
        # Arrange
        rel = _upload(root, "a.pdf", EXPECTED_SHA_INPUT)
        fet._extract_text_sync(rel)
        import shutil

        shutil.rmtree(root / ".extract" / "pdf" / "a" / "pages" / "01")
        # Act
        result = fet._extract_text_sync(rel)
        # Assert
        assert "Processed: 1 page(s) — 1\n" in result
        assert "Skipped (already present): 1 page(s)\n" in result

    # Plan #91 | B45,B46
    def test_extract_text_sync_removes_stray_tmp_dirs_when_present(self, root):
        # Arrange
        rel = _upload(root, "a.pdf", _make_pdf(["A"]))
        pages = root / ".extract" / "pdf" / "a" / "pages"
        (pages / ".tmp-01-x").mkdir(parents=True)
        (pages / "notes").write_text("keep")
        (pages / "07").write_text("file not dir")
        # Act
        result = fet._extract_text_sync(rel)
        # Assert
        assert not (pages / ".tmp-01-x").exists()
        assert (pages / "notes").read_text() == "keep"
        assert "Processed: 1 page(s) — 1\n" in result

    # Plan #92 | B31,B46
    def test_extract_text_sync_honors_pages_selector(self, root):
        # Arrange
        rel = _upload(root, "a.pdf", _make_pdf(["A", "B", "C"]))
        # Act
        result = fet._extract_text_sync(rel, "2")
        # Assert
        assert "Processed: 1 page(s) — 2\n" in result
        assert (
            "Document totals: 1/3 page(s) complete, 1 characters, 0 raw images -> 0 after merge\n"
            in result
        )

    # Plan #93 | B44
    def test_extract_text_sync_returns_selector_error_and_closes_document(
        self, root, monkeypatch
    ):
        # Arrange
        rel = _upload(root, "a.pdf", _make_pdf(["A", "B"]))
        closed: list[int] = []
        real_open = pdfplumber.open
        monkeypatch.setattr(
            pdfplumber, "open", lambda s: _CloseSpy(real_open(s), closed)
        )
        # Act
        result = fet._extract_text_sync(rel, "9")
        # Assert
        assert result == "page 9 out of bounds (1-2)"
        assert closed == [1]

    # Plan #94 | B42
    def test_extract_text_sync_reports_libraries_unavailable_when_import_fails(
        self, root, monkeypatch
    ):
        # Arrange
        rel = _upload(root, "a.pdf", _make_pdf(["A"]))
        monkeypatch.setitem(sys.modules, "pdfplumber", None)
        # Act
        result = fet._extract_text_sync(rel)
        # Assert
        assert result.startswith("PDF libraries unavailable:")

    # Plan #95 | B43
    def test_extract_text_sync_reports_failed_to_read_when_pdf_invalid(self, root):
        # Arrange
        rel = _upload(root, "a.pdf", b"this is not a pdf")
        # Act
        result = fet._extract_text_sync(rel)
        # Assert
        assert result.startswith("failed to read PDF:")

    # Plan #95 | B43
    def test_extract_text_sync_reports_failed_to_read_when_open_raises(
        self, root, monkeypatch
    ):
        # Arrange
        rel = _upload(root, "a.pdf", _make_pdf(["A"]))
        monkeypatch.setattr(
            pdfplumber, "open", mock.Mock(side_effect=RuntimeError("nope"))
        )
        # Act
        result = fet._extract_text_sync(rel)
        # Assert
        assert result == "failed to read PDF: nope"

    # Plan #95 | B43
    def test_extract_text_sync_closes_document_when_pages_access_raises(
        self, root, monkeypatch
    ):
        # Arrange
        rel = _upload(root, "a.pdf", _make_pdf(["A"]))
        closed: list[int] = []

        class _BadPages:
            @property
            def pages(self):
                raise RuntimeError("pages broke")

            def close(self):
                closed.append(1)

        monkeypatch.setattr(pdfplumber, "open", lambda s: _BadPages())
        # Act
        result = fet._extract_text_sync(rel)
        # Assert
        assert result == "failed to read PDF: pages broke"
        assert closed == [1]

    # Plan #96 | B48
    def test_extract_text_sync_reports_render_failure_when_pdfium_raises(
        self, root, monkeypatch
    ):
        # Arrange
        rel = _upload(root, "a.pdf", _make_pdf(["A"]))
        monkeypatch.setattr(
            pypdfium2, "PdfDocument", mock.Mock(side_effect=RuntimeError("boom"))
        )
        # Act
        result = fet._extract_text_sync(rel)
        # Assert
        assert result == "failed to render PDF: boom"

    # Plan #97 | B48
    def test_extract_text_sync_reports_page_failure_and_cleans_tmp_when_materialize_raises(
        self, root, monkeypatch
    ):
        # Arrange
        rel = _upload(root, "a.pdf", _make_pdf(["A"]))
        monkeypatch.setattr(
            fet, "_materialize_page", mock.Mock(side_effect=ValueError("bad"))
        )
        # Act
        result = fet._extract_text_sync(rel)
        # Assert
        assert result == "failed to materialise page 1: bad"
        pages = root / ".extract" / "pdf" / "a" / "pages"
        assert list(pages.iterdir()) == []


class TestExtractTextSyncParallel:
    # Plan #98 | B47
    def test_extract_text_sync_uses_parallel_branch_when_pages_exceed_threshold(
        self, root, monkeypatch, inline_pool
    ):
        # Arrange
        rel = _upload(root, "a.pdf", EXPECTED_SHA_INPUT)
        monkeypatch.setattr(fet, "_PARALLEL_PAGE_THRESHOLD", 1)
        # Act
        result = fet._extract_text_sync(rel)
        # Assert
        assert len(inline_pool) == 1
        assert "Processed: 2 page(s) — 1, 2\n" in result
        assert (
            root / ".extract" / "pdf" / "a" / "pages" / "02" / "text.md"
        ).read_text() == "Beta"

    # Plan #98 | B47
    def test_extract_text_sync_uses_sequential_branch_when_pages_equal_threshold(
        self, root, monkeypatch
    ):
        # Arrange
        rel = _upload(root, "a.pdf", _make_pdf(["A"]))
        monkeypatch.setattr(fet, "_PARALLEL_PAGE_THRESHOLD", 1)
        spy = mock.Mock(side_effect=AssertionError("parallel must not run"))
        monkeypatch.setattr(fet, "_materialize_parallel_sync", spy)
        # Act
        result = fet._extract_text_sync(rel)
        # Assert
        spy.assert_not_called()
        assert "Processed: 1 page(s) — 1\n" in result

    # Plan #99 | B47
    def test_extract_text_sync_reports_parallel_failure_when_workers_raise(
        self, root, monkeypatch
    ):
        # Arrange
        rel = _upload(root, "a.pdf", EXPECTED_SHA_INPUT)
        monkeypatch.setattr(fet, "_PARALLEL_PAGE_THRESHOLD", 1)
        monkeypatch.setattr(
            fet,
            "_materialize_parallel_sync",
            mock.Mock(side_effect=RuntimeError("pool")),
        )
        # Act
        result = fet._extract_text_sync(rel)
        # Assert
        assert result == "failed to materialise pages in parallel: pool"

    # Plan #100 | B47
    def test_extract_text_sync_records_only_pages_with_receipts_when_worker_incomplete(
        self, root, monkeypatch
    ):
        # Arrange
        rel = _upload(root, "a.pdf", EXPECTED_SHA_INPUT)
        monkeypatch.setattr(fet, "_PARALLEL_PAGE_THRESHOLD", 1)
        receipt = {"images": [], "chars": 7, "raw_images": 0, "merged_images": 0}
        monkeypatch.setattr(
            fet, "_materialize_parallel_sync", mock.Mock(return_value={1: receipt})
        )
        # Act
        result = fet._extract_text_sync(rel)
        # Assert
        assert (
            "Processed: 2 page(s) — 1, 2\n  images this run: 0 raw -> 0 after merge\n"
            in result
        )
        assert "Document totals: 0/2 page(s) complete, 0 characters" in result
        assert "Shards:" not in result
        manifest = json.loads(
            (root / ".extract" / "pdf" / "a" / "manifest.json").read_text()
        )
        assert manifest["pages"] == {}
        assert manifest["shards"] == []


class TestExtractTextSyncDetails:
    # Plan #101 | B49
    def test_extract_text_sync_counts_image_tokens_and_skips_unreadable_image(
        self, root, monkeypatch
    ):
        # Arrange
        rel = _upload(root, "a.pdf", _make_pdf(["A"]))
        stub = _stub_materialize(
            "t", {"image-1.png": (100, 75), "sub/x.png": (50, 15)}, 400
        )

        # an unreadable image name is recorded in the receipt but never written to disk
        def with_missing(page, render, out_dir):
            r = stub(page, render, out_dir)
            r["images"].append("missing.png")
            return r

        monkeypatch.setattr(fet, "_materialize_page", with_missing)
        # Act
        result = fet._extract_text_sync(rel)
        # Assert
        assert "Estimated tokens to read document.md + all images: ~111\n" in result
        assert "Shards: 1 — a-s01 pages 1 (~111 tok)\n" in result

    # Plan #102 | B50
    def test_extract_text_sync_rewrites_image_refs_in_document_md(
        self, root, monkeypatch
    ):
        # Arrange
        rel = _upload(root, "a.pdf", _make_pdf(["A"]))
        monkeypatch.setattr(
            fet,
            "_materialize_page",
            _stub_materialize("x @[[image-1.png]] @[[a/b.png]]", {}, 1),
        )
        # Act
        fet._extract_text_sync(rel)
        # Assert
        doc = (root / ".extract" / "pdf" / "a" / "document.md").read_text()
        assert doc == (
            "\n\n<!-- ================= PAGE 1 ================= -->\n\n"
            "x @[[pages/01/image-1.png]] @[[a/b.png]]"
        )

    # Plan #103 | B50
    def test_extract_text_sync_uses_empty_text_when_text_md_missing(
        self, root, monkeypatch
    ):
        # Arrange
        rel = _upload(root, "a.pdf", _make_pdf(["A"]))
        monkeypatch.setattr(fet, "_materialize_page", _stub_materialize(None, {}, 0))
        # Act
        fet._extract_text_sync(rel)
        # Assert
        doc = (root / ".extract" / "pdf" / "a" / "document.md").read_text()
        assert doc == "\n\n<!-- ================= PAGE 1 ================= -->\n\n"

    # Plan #104 | B51
    @pytest.mark.parametrize(
        ("pages", "advisory"), [(1, False), (2, True)], ids=["at-limit", "over-limit"]
    )
    def test_extract_text_sync_adds_large_document_advisory_only_over_threshold(
        self, root, monkeypatch, pages, advisory
    ):
        # Arrange
        rel = _upload(root, "a.pdf", _make_pdf(["A"] * pages))
        monkeypatch.setattr(fet, "_LARGE_DOCUMENT_PAGES", 1)
        # Act
        result = fet._extract_text_sync(rel)
        # Assert
        assert (
            'extract_text(path, pages="1-20") materialises a slice instead' in result
        ) is advisory
        if advisory:
            assert "This document is 2 pages (~0 tokens to read whole). " in result


class TestExtractTextSyncOffice:
    @staticmethod
    def _converter(monkeypatch) -> mock.Mock:
        conv = _fake_convert(_make_pdf(["Doc"]))
        monkeypatch.setattr(fet.soffice, "convert_to_pdf", conv)
        return conv

    # Plan #105 | B41,B51,B1
    @pytest.mark.parametrize("ext", ["docx", "pptx"])
    def test_extract_text_sync_converts_office_and_appends_pagination_note(
        self, root, monkeypatch, ext
    ):
        # Arrange
        conv = self._converter(monkeypatch)
        rel = _upload(root, f"a.{ext}", b"office-bytes")
        # Act
        result = fet._extract_text_sync(rel)
        # Assert
        assert result.startswith(
            f"Materialised a.{ext} -> .extract/{ext}/a/ (1 page(s) total)\n"
        )
        assert result.endswith(PNOTE)
        manifest = json.loads(
            (root / ".extract" / ext / "a" / "manifest.json").read_text()
        )
        assert (manifest["converted_by"], manifest["source_format"]) == (
            "libreoffice",
            ext,
        )
        conv.assert_called_once()

    # Plan #105 | B51
    def test_extract_text_sync_adds_spreadsheet_line_when_xlsx(self, root, monkeypatch):
        # Arrange
        self._converter(monkeypatch)
        rel = _upload(root, "a.xlsx", b"office-bytes")
        # Act
        result = fet._extract_text_sync(rel)
        # Assert
        assert result.endswith(
            "These 1 page(s) are LibreOffice's pagination of a spreadsheet, driven by its "
            "print settings — not a structure the workbook itself has." + PNOTE
        )

    # Plan #105b | B41
    def test_extract_text_sync_reuses_cached_conversion_when_resumed(
        self, root, monkeypatch
    ):
        # Arrange
        conv = self._converter(monkeypatch)
        rel = _upload(root, "a.docx", b"office-bytes")
        fet._extract_text_sync(rel)
        # Act
        result = fet._extract_text_sync(rel)
        # Assert
        conv.assert_called_once()
        assert "Processed: 0 pages (nothing new to materialise)\n" in result

    # Plan #106 | B41
    def test_extract_text_sync_returns_conversion_error_when_converter_fails(
        self, root, monkeypatch
    ):
        # Arrange
        monkeypatch.setattr(
            fet.soffice,
            "convert_to_pdf",
            mock.create_autospec(
                soffice.convert_to_pdf, return_value=(None, "no soffice")
            ),
        )
        rel = _upload(root, "a.docx", b"office-bytes")
        # Act
        result = fet._extract_text_sync(rel)
        # Assert
        assert result == "no soffice"

    # Plan #106 | B41
    def test_extract_text_sync_reports_no_output_when_converter_returns_nothing(
        self, root, monkeypatch
    ):
        # Arrange
        monkeypatch.setattr(
            fet.soffice,
            "convert_to_pdf",
            mock.create_autospec(soffice.convert_to_pdf, return_value=(None, "")),
        )
        rel = _upload(root, "a.docx", b"office-bytes")
        # Act
        result = fet._extract_text_sync(rel)
        # Assert
        assert result == "conversion produced no output"


# --------------------------------------------------------------------------- file_find
class TestFileFind:
    # Plan #108 | B52
    def test_file_find_returns_error_when_unbound(self, unbound):
        # Arrange / Act
        result = fet.file_find("x")
        # Assert
        assert result == NOT_BOUND

    # Plan #108 | B52
    @pytest.mark.parametrize("query", ["", "  "], ids=["empty", "blank"])
    def test_file_find_rejects_empty_query(self, root, query):
        # Arrange / Act
        result = fet.file_find(query)
        # Assert
        assert result == "search query is empty"

    # Plan #109 | B52
    def test_file_find_returns_resolve_error_when_extract_root_rejected(self, root):
        # Arrange
        fet.bind_sandbox(_Sandbox(root, deny=(".extract",)))
        # Act
        result = fet.file_find("x")
        # Assert
        assert result == "path rejected: denied: .extract"

    # Plan #109 | B52
    def test_file_find_returns_resolve_error_when_path_rejected(self, root):
        # Arrange / Act
        result = fet.file_find("x", "../x.pdf")
        # Assert
        assert result == "path rejected: escapes root: ../x.pdf"

    # Plan #110 | B52
    def test_file_find_reports_none_materialised_when_root_missing(self, root):
        # Arrange / Act
        result = fet.file_find("x")
        # Assert
        assert result == "No materialised documents found."

    # Plan #110 | B52
    def test_file_find_reports_target_not_materialised_when_root_missing_and_path_given(
        self, root
    ):
        # Arrange / Act
        result = fet.file_find("x", ".uploads/a.pdf")
        # Assert
        assert result == "document not materialised: a"

    # Plan #111 | B52
    def test_file_find_reports_none_materialised_when_no_documents(self, root):
        # Arrange
        (root / ".extract").mkdir()
        # Act
        result = fet.file_find("x")
        # Assert
        assert result == "No materialised documents found."

    # Plan #112 | B52
    @pytest.mark.parametrize(
        ("target", "message"),
        [(".uploads/a.pdf", "pdf/a"), (".uploads/a.docx", "docx/a")],
        ids=["slug-mismatch", "format-mismatch"],
    )
    def test_file_find_reports_target_not_materialised_when_other_docs_only(
        self, root, target, message
    ):
        # Arrange
        _manifest(root, "pdf", "b")
        if target.endswith("docx"):
            _manifest(root, "pdf", "a")
        # Act
        result = fet.file_find("x", target)
        # Assert
        assert result == f"document not materialised: {message}"

    # Plan #113 | B54,B55
    def test_file_find_returns_hit_with_context_when_query_matches(self, root):
        # Arrange
        _page(_manifest(root, "pdf", "a"), "02", "Hello World")
        # Act
        result = fet.file_find("world")
        # Assert
        assert result == (
            "Found 1 match(es) for 'world':\n\n"
            "1. Document: pdf/a, Page: 2\n   Context: ...Hello World...\n"
        )

    # Plan #114 | B53
    def test_file_find_skips_document_without_pages_directory(self, root):
        # Arrange
        _manifest(root, "pdf", "a")
        # Act
        result = fet.file_find("x")
        # Assert
        assert result == "No matches for 'x' in any materialised document."

    # Plan #114 | B53
    def test_file_find_skips_non_digit_dirs_files_and_pages_without_text(self, root):
        # Arrange
        doc = _manifest(root, "pdf", "a")
        _page(doc, "notes", "x needle")
        (doc / "pages" / "05").mkdir()
        (doc / "pages" / "06").write_text("x needle")
        # Act
        result = fet.file_find("needle")
        # Assert
        assert result == "No matches for 'needle' in any materialised document."

    # Plan #114 | B53
    def test_file_find_skips_page_when_read_text_raises(self, root, monkeypatch):
        # Arrange
        _page(_manifest(root, "pdf", "a"), "01", "needle")
        monkeypatch.setattr(Path, "read_text", mock.Mock(side_effect=OSError("x")))
        # Act
        result = fet.file_find("needle")
        # Assert
        assert result == "No matches for 'needle' in any materialised document."

    # Plan #114 | B53
    def test_file_find_skips_document_when_listdir_raises(self, root, monkeypatch):
        # Arrange
        doc = _manifest(root, "pdf", "a")
        _page(doc, "01", "needle")
        real = os.listdir

        def fake(p):
            if Path(p) == doc / "pages":
                raise OSError("x")
            return real(p)

        monkeypatch.setattr(fet.os, "listdir", fake)
        # Act
        result = fet.file_find("needle")
        # Assert
        assert result == "No matches for 'needle' in any materialised document."

    # Plan #115 | B54
    def test_file_find_clamps_context_to_150_chars_each_side_and_collapses_whitespace(
        self, root
    ):
        # Arrange
        _page(_manifest(root, "pdf", "a"), "01", "A" * 200 + "\n needle \n" + "B" * 200)
        # Act
        result = fet.file_find("needle")
        # Assert
        assert result == (
            "Found 1 match(es) for 'needle':\n\n"
            "1. Document: pdf/a, Page: 1\n   Context: ..."
            + "A" * 148
            + " needle "
            + "B" * 148
            + "...\n"
        )

    # Plan #116 | B54
    def test_file_find_finds_overlapping_occurrences(self, root):
        # Arrange
        _page(_manifest(root, "pdf", "a"), "01", "aaa")
        # Act
        result = fet.file_find("aa")
        # Assert
        assert result.startswith("Found 2 match(es) for 'aa':")

    # Plan #116 | B54
    def test_file_find_orders_pages_numerically_when_many_pages(self, root):
        # Arrange
        doc = _manifest(root, "pdf", "a")
        _page(doc, "10", "needle ten")
        _page(doc, "02", "needle two")
        # Act
        result = fet.file_find("needle")
        # Assert
        assert result.index("Page: 2") < result.index("Page: 10")

    # Plan #117 | B54,B55
    def test_file_find_caps_hits_within_one_page(self, root):
        # Arrange
        _page(_manifest(root, "pdf", "a"), "01", "x x x x x")
        # Act
        result = fet.file_find("x", limit=2)
        # Assert
        assert result.startswith("Found 2 match(es) for 'x':")
        assert result.endswith(
            "\nResults capped at 2 hits. To narrow the search, try a more specific query."
        )

    # Plan #117 | B54,B55
    def test_file_find_caps_hits_across_pages_and_documents(self, root):
        # Arrange
        a = _manifest(root, "pdf", "a")
        _page(a, "01", "x")
        _page(a, "02", "x")
        _page(_manifest(root, "pdf", "b"), "01", "x")
        # Act
        result = fet.file_find("x", limit=2)
        # Assert
        assert result.count("Document: pdf/a") == 2
        assert "pdf/b" not in result

    # Plan #117 | B54,B55
    def test_file_find_omits_cap_message_when_hits_below_limit(self, root):
        # Arrange
        _page(_manifest(root, "pdf", "a"), "01", "x x")
        # Act
        result = fet.file_find("x", limit=3)
        # Assert
        assert result.startswith("Found 2 match(es)")
        assert "capped" not in result

    # Plan #117 | B54,B55
    def test_file_find_stops_at_first_document_when_limit_is_one(self, root):
        # Arrange
        _page(_manifest(root, "pdf", "a"), "01", "x")
        _page(_manifest(root, "pdf", "b"), "01", "x")
        # Act
        result = fet.file_find("x", limit=1)
        # Assert
        assert "pdf/b" not in result
        assert "Results capped at 1 hits." in result

    # Plan #118 | B52,B55
    def test_file_find_filters_by_path_when_target_given(self, root):
        # Arrange
        _page(_manifest(root, "pdf", "a"), "01", "needle")
        _page(_manifest(root, "pdf", "b"), "01", "needle")
        # Act
        result = fet.file_find("needle", ".uploads/a.pdf")
        # Assert
        assert "Document: pdf/a," in result
        assert "pdf/b" not in result

    # Plan #119 | B55
    def test_file_find_reports_no_matches_for_target_document(self, root):
        # Arrange
        _page(_manifest(root, "pdf", "a"), "01", "other")
        # Act
        result = fet.file_find("zzz", ".uploads/a.pdf")
        # Assert
        assert result == "No matches for 'zzz' in document 'a'."

    # Plan #119b | B55
    def test_file_find_reports_no_matches_when_query_absent_without_target(self, root):
        # Arrange
        _page(_manifest(root, "pdf", "a"), "01", "other")
        # Act
        result = fet.file_find("zzz")
        # Assert
        assert result == "No matches for 'zzz' in any materialised document."

    # Plan #119c | B54
    def test_file_find_matches_case_insensitively(self, root):
        # Arrange
        _page(_manifest(root, "pdf", "a"), "01", "HELLO")
        # Act
        result = fet.file_find("hello")
        # Assert
        assert "Context: ...HELLO..." in result


# --------------------------------------------------------------------------- file_page_image
class _FakeImage:
    width = 10
    height = 20

    def __init__(self, nbytes: int) -> None:
        self._n = nbytes

    def save(self, fp, format=None):
        fp.write(b"x" * self._n)


class _FakeFiumDoc:
    def __init__(self, nbytes_per_scale: float = 1000.0, fail: bool = False) -> None:
        self.scales: list[float] = []
        self.closed = 0
        self._k = nbytes_per_scale
        self._fail = fail

    def __getitem__(self, idx):
        doc = self

        class _P:
            def render(self, scale):
                doc.scales.append(scale)
                if doc._fail:
                    raise RuntimeError("r")

                class _R:
                    def to_pil(_s):
                        return _FakeImage(int(doc._k * scale))

                return _R()

        return _P()

    def close(self):
        self.closed += 1


class TestFilePageImageSync:
    # Plan #120 | B56
    async def test_file_page_image_returns_sync_result_when_awaited(self, unbound):
        # Arrange / Act
        result = await fet.file_page_image("a.pdf", 1)
        # Assert
        assert result == NOT_BOUND

    # Plan #120 | B56
    async def test_file_page_image_renders_page_when_awaited_with_bound_sandbox(
        self, root
    ):
        # Arrange
        rel = _upload(root, "a.pdf", _make_pdf(["A"]))
        # Act
        result = await fet.file_page_image(rel, 1)
        # Assert
        assert re.fullmatch(
            r"\.extract/pdf/a/pages[\\/]01[\\/]page-full\.png \(400x400, \d+ KB, ~213 tokens\)",
            result,
        )

    # Plan #121 | B56
    @pytest.mark.parametrize(
        "page", [0, -1, "1", 1.5, None], ids=["zero", "neg", "str", "float", "none"]
    )
    def test_file_page_image_sync_rejects_invalid_page(self, root, page):
        # Arrange / Act
        result = fet._file_page_image_sync(".uploads/a.pdf", page)
        # Assert
        assert result == f"page must be a positive integer (got {page!r})"

    # Plan #122 | B57
    def test_file_page_image_sync_returns_missing_message_when_absent(self, root):
        # Arrange / Act
        result = fet._file_page_image_sync(".uploads/a.pdf", 1)
        # Assert
        assert result == "path is not a file: .uploads/a.pdf"

    # Plan #122 | B57
    def test_file_page_image_sync_returns_error_when_doc_dir_unresolvable(self, root):
        # Arrange
        rel = _upload(root, "a.pdf", _make_pdf(["A"]))
        fet.bind_sandbox(_Sandbox(root, deny=(".extract",)))
        # Act
        result = fet._file_page_image_sync(rel, 1)
        # Assert
        assert result == "path rejected: denied: .extract/pdf/a"

    # Plan #123 | B57
    def test_file_page_image_sync_reports_libraries_unavailable(
        self, root, monkeypatch
    ):
        # Arrange
        rel = _upload(root, "a.pdf", _make_pdf(["A"]))
        monkeypatch.setitem(sys.modules, "pdfplumber", None)
        # Act
        result = fet._file_page_image_sync(rel, 1)
        # Assert
        assert result.startswith("PDF libraries unavailable:")

    # Plan #124 | B57
    def test_file_page_image_sync_reports_failed_to_read_when_pdf_invalid(self, root):
        # Arrange
        rel = _upload(root, "a.pdf", b"this is not a pdf")
        # Act
        result = fet._file_page_image_sync(rel, 1)
        # Assert
        assert result.startswith("failed to read PDF:")

    # Plan #125 | B57
    def test_file_page_image_sync_reports_out_of_range_and_closes_document(
        self, root, monkeypatch
    ):
        # Arrange
        rel = _upload(root, "a.pdf", _make_pdf(["A", "B"]))
        closed: list[int] = []
        real_open = pdfplumber.open
        monkeypatch.setattr(
            pdfplumber, "open", lambda s: _CloseSpy(real_open(s), closed)
        )
        # Act
        result = fet._file_page_image_sync(rel, 3)
        # Assert
        assert result == "page 3 out of range (1-2)"
        assert closed == [1]

    # Plan #125 | B57
    def test_file_page_image_sync_accepts_last_page_when_page_equals_count(self, root):
        # Arrange
        rel = _upload(root, "a.pdf", _make_pdf(["A", "B"]))
        # Act
        result = fet._file_page_image_sync(rel, 2)
        # Assert
        assert result.startswith(".extract/pdf/a/pages")
        assert (
            root / ".extract" / "pdf" / "a" / "pages" / "02" / "page-full.png"
        ).is_file()

    # Plan #126 | B57
    def test_file_page_image_sync_reports_render_failure_when_pdfium_document_fails(
        self, root, monkeypatch
    ):
        # Arrange
        rel = _upload(root, "a.pdf", _make_pdf(["A"]))
        monkeypatch.setattr(
            pypdfium2, "PdfDocument", mock.Mock(side_effect=RuntimeError("boom"))
        )
        # Act
        result = fet._file_page_image_sync(rel, 1)
        # Assert
        assert result == "failed to render PDF: boom"

    # Plan #127 | B58
    def test_file_page_image_sync_writes_page_full_png_when_within_limit(self, root):
        # Arrange
        rel = _upload(root, "a.pdf", _make_pdf(["A"]))
        # Act
        result = fet._file_page_image_sync(rel, 1)
        # Assert
        out = root / ".extract" / "pdf" / "a" / "pages" / "01" / "page-full.png"
        match = re.fullmatch(
            r"\.extract/pdf/a/pages[\\/]01[\\/]page-full\.png \((\d+)x(\d+), (\d+) KB, ~(\d+) tokens\)",
            result,
        )
        assert match is not None
        with Image.open(out) as im:
            assert im.size == (400, 400)
        assert (match.group(1), match.group(2)) == ("400", "400")
        assert int(match.group(3)) == out.stat().st_size // 1024
        assert match.group(4) == "213"

    # Plan #128 | B58
    def test_file_page_image_sync_downscales_when_png_over_limit(
        self, root, monkeypatch
    ):
        # Arrange
        rel = _upload(root, "a.pdf", _make_pdf(["A"]))
        fium = _FakeFiumDoc(1000.0)
        monkeypatch.setattr(pypdfium2, "PdfDocument", lambda data: fium)
        monkeypatch.setattr(fet, "_IMAGE_MAX_BYTES", 1750)
        # Act
        result = fet._file_page_image_sync(rel, 1)
        # Assert
        assert fium.scales == pytest.approx([2.0, 1.7])
        assert result.endswith("(10x20, 1 KB, ~0 tokens)")
        assert (
            root / ".extract" / "pdf" / "a" / "pages" / "01" / "page-full.png"
        ).stat().st_size == 1700

    # Plan #129 | B58
    def test_file_page_image_sync_reports_size_limit_when_downscaling_exhausted(
        self, root, monkeypatch
    ):
        # Arrange
        rel = _upload(root, "a.pdf", _make_pdf(["A"]))
        fium = _FakeFiumDoc(1000.0)
        monkeypatch.setattr(pypdfium2, "PdfDocument", lambda data: fium)
        monkeypatch.setattr(fet, "_IMAGE_MAX_BYTES", 1)
        # Act
        result = fet._file_page_image_sync(rel, 1)
        # Assert
        assert result == (
            "page 1 exceeds size limits even after downscaling "
            "(try file_find to locate relevant content)"
        )
        assert len(fium.scales) == 5

    # Plan #130 | B58
    def test_file_page_image_sync_reports_render_error_for_page(
        self, root, monkeypatch
    ):
        # Arrange
        rel = _upload(root, "a.pdf", _make_pdf(["A"]))
        monkeypatch.setattr(
            pypdfium2, "PdfDocument", lambda data: _FakeFiumDoc(fail=True)
        )
        # Act
        result = fet._file_page_image_sync(rel, 1)
        # Assert
        assert result == "failed to render page 1: r"

    # Plan #131 | B58
    def test_file_page_image_sync_reports_write_failure(self, root, monkeypatch):
        # Arrange
        rel = _upload(root, "a.pdf", _make_pdf(["A"]))
        monkeypatch.setattr(Path, "write_bytes", mock.Mock(side_effect=OSError("ro")))
        # Act
        result = fet._file_page_image_sync(rel, 1)
        # Assert
        assert result == "failed to write page 1 image: ro"

    # Plan #132 | B58
    @pytest.mark.parametrize("fail", [False, True], ids=["success", "render-error"])
    def test_file_page_image_sync_closes_both_documents_in_every_outcome(
        self, root, monkeypatch, fail
    ):
        # Arrange
        rel = _upload(root, "a.pdf", _make_pdf(["A"]))
        fium = _FakeFiumDoc(fail=fail)
        closed: list[int] = []
        real_open = pdfplumber.open
        monkeypatch.setattr(pypdfium2, "PdfDocument", lambda data: fium)
        monkeypatch.setattr(
            pdfplumber, "open", lambda s: _CloseSpy(real_open(s), closed)
        )
        # Act
        fet._file_page_image_sync(rel, 1)
        # Assert
        assert fium.closed == 1
        assert closed == [1]


class TestModuleConstants:
    # Plan #133 | B59
    def test_module_constants_expose_expected_tool_keys_and_formats(self):
        # Arrange / Act / Assert
        assert (
            fet.EXTRACT_TEXT,
            fet.FILE_INFO,
            fet.FILE_FIND,
            fet.FILE_PAGE_IMAGE,
        ) == (
            "extract_text",
            "file_info",
            "file_find",
            "file_page_image",
        )
        assert fet._SUPPORTED_FORMATS == {
            "txt",
            "md",
            "csv",
            "htm",
            "html",
            "json",
            "pdf",
            "docx",
            "xlsx",
            "pptx",
        }
        assert fet._CONVERTED_FORMATS == {"docx", "xlsx", "pptx"}
