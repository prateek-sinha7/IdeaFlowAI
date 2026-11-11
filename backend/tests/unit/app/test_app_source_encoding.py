"""Source-encoding guard for ``backend/app`` (open decision 22.2).

A UTF-8 byte-order mark (``EF BB BF``) at the start of a Python file is invisible in
most editors. Python imports such a file without complaint, but ``ast.parse`` on the
text fails, so source-scanning tests break with an error that points nowhere. Two
files under ``app/agents/workflow_builder`` once carried one. This test keeps it out.
Reads the first three bytes of each file only; it never imports ``app``.
"""

from __future__ import annotations

from pathlib import Path

_APP_DIR = Path(__file__).resolve().parents[3] / "app"
_UTF8_BOM = b"\xef\xbb\xbf"


def _files_with_bom(root: Path) -> list[str]:
    """Return the ``.py`` files under ``root`` that start with a UTF-8 BOM."""
    found: list[str] = []
    for path in sorted(root.rglob("*.py")):
        with path.open("rb") as handle:
            if handle.read(len(_UTF8_BOM)) == _UTF8_BOM:
                found.append(path.relative_to(root).as_posix())
    return found


def test_app_sources_start_without_bom_when_scanned() -> None:
    assert _APP_DIR.is_dir(), f"app package not found at {_APP_DIR}"

    assert (
        _files_with_bom(_APP_DIR) == []
    ), "these files start with a UTF-8 byte-order mark; remove the first three bytes"


def test_files_with_bom_lists_file_when_it_starts_with_bom(tmp_path: Path) -> None:
    (tmp_path / "clean.py").write_bytes(b"x = 1\n")
    (tmp_path / "marked.py").write_bytes(_UTF8_BOM + b"x = 1\n")
    nested = tmp_path / "pkg"
    nested.mkdir()
    (nested / "inner.py").write_bytes(_UTF8_BOM + b"y = 2\n")

    assert _files_with_bom(tmp_path) == ["marked.py", "pkg/inner.py"]
