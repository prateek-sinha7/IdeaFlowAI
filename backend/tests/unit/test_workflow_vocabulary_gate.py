"""ADR-0002 — `workflow` is the only vocabulary; `pipeline` is removed, not deprecated.

ADR-0002 decided that the legacy `pipeline` vocabulary is removed from the
files it governs rather than kept as an alias, "to achieve one name per
concept enforced by a grep gate". No such gate exists yet, and the governed
files still use `pipeline` pervasively (identifiers, comments, docs).

This test IS that grep gate. It fails today because the rename has not
happened; it will pass once ADR-0002 is implemented.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[2]

# Files ADR-0002 (applies_to.globs) governs.
_GOVERNED_FILES = [
    _BACKEND_DIR / "agents" / "loader.py",
    _BACKEND_DIR / "agents" / "registry.py",
    _BACKEND_DIR / "agents" / "execution_engine" / "engine.py",
    _BACKEND_DIR / "CLAUDE.md",
]

_PIPELINE = re.compile(r"pipeline", re.IGNORECASE)


@pytest.mark.issue("ADR-0002")
@pytest.mark.xfail(reason="ADR-0002 unfixed", strict=True)
@pytest.mark.parametrize("path", _GOVERNED_FILES, ids=lambda p: p.name)
def test_no_pipeline_vocabulary_in_governed_files(path: Path):
    """`pipeline` must not appear anywhere in a file ADR-0002 governs."""
    text = path.read_text(encoding="utf-8")
    hits = [
        (lineno, line.strip())
        for lineno, line in enumerate(text.splitlines(), start=1)
        if _PIPELINE.search(line)
    ]
    assert not hits, (
        f"{path.relative_to(_BACKEND_DIR)} still uses `pipeline` vocabulary "
        f"({len(hits)} lines), violating ADR-0002: {hits[:5]}"
    )
