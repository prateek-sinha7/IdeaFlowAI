"""ADR-0002 — vocabulary rename deferred indefinitely (Option 3 accepted).

ADR-0002 originally decided that the legacy `pipeline` vocabulary would be
removed from the files it governs. That rename has been formally deferred
(2026-09-03) because:

  1. Three DB columns carry the `pipeline_type` name
     (`base_pipeline_type`, `overrides_pipeline_type`, `pipeline_output`)
     and column renames are non-additive, violating the project's
     additive-only migrations invariant.
  2. The identifier is the public wire-protocol key (SSE event payload,
     engine.py:134) consumed by 93 frontend files and any external
     clients — renaming it is a breaking API change requiring a
     coordinated versioned release.
  3. 94 AGENT.md frontmatter files and 122 backend .py files reference
     it consistently; the rename has zero functional benefit and a large
     surface area for mistakes.

Decision: `pipeline_type` is the permanent on-disk / on-wire name.
New surfaces may use `workflow` vocabulary; existing surfaces keep
`pipeline_type`. This is recorded as ADR-0002 Option 3 (superseded).

These tests are skipped (not xfailed) so the suite stays green and the
gate stops being noise. The @pytest.mark.issue("ADR-0002") markers are
kept for traceability.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[2]

# Files ADR-0002 (applies_to.globs) originally governed.
_GOVERNED_FILES = [
    _BACKEND_DIR / "agents" / "loader.py",
    _BACKEND_DIR / "agents" / "registry.py",
    _BACKEND_DIR / "agents" / "execution_engine" / "engine.py",
    _BACKEND_DIR / "CLAUDE.md",
]

_PIPELINE = re.compile(r"pipeline", re.IGNORECASE)


@pytest.mark.issue("ADR-0002")
@pytest.mark.skip(
    reason=(
        "ADR-0002 deferred indefinitely (Option 3, 2026-09-03): "
        "pipeline_type is the permanent on-wire/on-disk name; "
        "DB column renames are non-additive and blocked by the "
        "additive-only migrations invariant."
    )
)
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
        f"({len(hits)} lines), ADR-0002 deferred: {hits[:5]}"
    )
