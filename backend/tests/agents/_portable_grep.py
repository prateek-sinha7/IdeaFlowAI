"""tests/agents/_portable_grep.py — a small cross-platform ``grep``-alike.

Several architecture/SC-001 static-scan tests shell out to a Unix ``grep``
binary (``-rl`` / ``-rn`` / ``-rlE``), which does not exist on stock Windows —
a platform/harness gap (WinError 2: "The system cannot find the file
specified"), not a signal about the code under test. This module reimplements
just the flag combinations these tests use, in pure Python, so the same
assertions run for real on every platform including Windows dev machines.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GrepResult:
    stdout: str
    returncode: int


def _iter_py_files(root: Path):
    yield from root.rglob("*.py")


def grep_files_matching(pattern: str, root: str | Path, *, regex: bool = False) -> GrepResult:
    """Portable equivalent of ``grep -rl[E] <pattern> <root> --include='*.py'``.

    Returns the NEWLINE-joined list of matching file paths in ``stdout``
    (mirroring ``grep -l``'s output shape), empty string when nothing matches.
    """
    compiled = re.compile(pattern) if regex else re.compile(re.escape(pattern))
    root_path = Path(root)
    matches: list[str] = []
    for path in _iter_py_files(root_path):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if compiled.search(text):
            matches.append(str(path))
    stdout = "\n".join(matches)
    return GrepResult(stdout=stdout, returncode=0 if matches else 1)


def grep_lines_matching(pattern: str, root: str | Path) -> GrepResult:
    """Portable equivalent of ``grep -rn <pattern> <root> --include='*.py'``.

    Returns ``path:lineno:line`` entries joined by newlines in ``stdout``
    (mirroring ``grep -n``'s output shape).
    """
    compiled = re.compile(re.escape(pattern))
    root_path = Path(root)
    lines_out: list[str] = []
    for path in _iter_py_files(root_path):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if compiled.search(line):
                lines_out.append(f"{path}:{lineno}:{line}")
    stdout = "\n".join(lines_out) + ("\n" if lines_out else "")
    return GrepResult(stdout=stdout, returncode=0 if lines_out else 1)
