"""Verify gate — byte-equivalence of the on-disk deliverable serialiser.

WHAT THIS PROVES
----------------
The engine reads code-gen deliverables from the per-run disk sandbox (written by
the native ``deepagents`` ``write_file`` tool) and serialises them into the
``WorkflowRun.output`` string via
``app.agents.sandbox.serialize_sandbox_deliverable(root)`` —
````` ```filename: <path>\n<content>\n``` ````` blocks, sorted by path, joined by
a blank line, with the ``"(no files written)"`` sentinel when empty — which the
frontend FilesTab / AppBuilderPreview parse.

The acceptance bar (this module): for any realistic set of ``(path, content)``
pairs, writing them into a temp dir and serialising it must return a string
**byte-identical** to the pre-migration in-memory serialiser
(``AgentWorkspace.to_final_output()``), for the non-internal files in sorted
order. That legacy oracle's module (``app/agents/tools/workspace.py``) is dead
pipeline-legacy removed in Phase 7a, so the oracle is now **inlined** below as a
faithful, dependency-free reimplementation of its exact algorithm, and each
fixture test additionally pins the expected output as a string LITERAL captured
from the real oracle pre-deletion (so the golden bytes are independent of both
the inlined oracle and the live serialiser, which stays fully covered).

THE ONE FILESYSTEM CAVEAT (documented, not a deviation)
-------------------------------------------------------
The oracle sorts an in-memory dict whose keys are case-SENSITIVE; a real
filesystem on macOS/Windows is case-INSENSITIVE, so writing both ``A/x`` and
``a/x`` would collapse to one file on disk and the directory casing would be
normalised — diverging the disk walk from the in-memory dict purely as a
filesystem property, not an algorithm bug. Code-gen agents never emit two paths
that differ only by case, so every test set here (incl. the Hypothesis strategy)
is constrained to paths that survive a faithful filesystem round-trip. Within
that (realistic) domain the two serialisations are byte-identical.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.agents.sandbox import (
    count_sandbox_deliverables,
    serialize_sandbox_deliverable,
)

# ---------------------------------------------------------------------------
# Inlined byte-oracle (the formerly-imported AgentWorkspace.to_final_output)
# ---------------------------------------------------------------------------
#
# This module is the byte-equivalence verify gate for the LIVE
# ``serialize_sandbox_deliverable`` / ``count_sandbox_deliverables``. Before the
# Phase-7a legacy excision it imported ``app.agents.tools.workspace.AgentWorkspace``
# and used ``AgentWorkspace.to_final_output()`` (+ ``file_count()``) as the oracle.
# ``workspace.py`` is dead pipeline-legacy (deleted in 7a-4), so the oracle is now
# INLINED here as a faithful, dependency-free reimplementation of the exact
# ``to_final_output`` algorithm it replaced:
#
#     deliverable = {p: c for p, c in files.items() if p not in INTERNAL}
#     if not deliverable: return "(no files written)"
#     "\n\n".join(f"```filename: {path}\n{content}\n```"
#                 for path, content in sorted(deliverable.items()))
#
# (verbatim from ``AgentWorkspace.to_final_output`` /
# ``AgentWorkspace.file_count``; ``_INTERNAL_FILES == {"PLANNER.md"}``). The
# individual fixture tests below ALSO assert the exact expected bytes as inline
# string LITERALS (captured by running the real ``AgentWorkspace`` oracle once,
# pre-deletion), so the golden output is pinned independently of this oracle and
# the live serialiser stays fully covered.

_INTERNAL_FILES = frozenset({"PLANNER.md"})
_EMPTY_SENTINEL = "(no files written)"


def _oracle_output(pairs: dict[str, str], *, internal=_INTERNAL_FILES) -> str:
    """Reference serialisation — the inlined ``AgentWorkspace.to_final_output``.

    Byte-faithful reimplementation of the legacy oracle: filter the internal
    set, sort by path, emit one ``filename:`` block per file joined by ``\\n\\n``,
    with the empty sentinel when nothing remains. ``pairs`` is the in-memory
    ``{relpath: content}`` map the agent "wrote" (the workspace dict analogue).
    """
    deliverable = {p: c for p, c in pairs.items() if p not in internal}
    if not deliverable:
        return _EMPTY_SENTINEL
    parts = [
        f"```filename: {path}\n{content}\n```"
        for path, content in sorted(deliverable.items())
    ]
    return "\n\n".join(parts)


def _oracle_count(pairs: dict[str, str], *, internal=_INTERNAL_FILES) -> int:
    """Reference deliverable count — the inlined ``AgentWorkspace.file_count``."""
    return sum(1 for p in pairs if p not in internal)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_to_disk(root: Path, pairs: dict[str, str]) -> None:
    """Write ``{relpath: content}`` onto ``root`` as the native fs tool would."""
    for relpath, content in pairs.items():
        fp = root / relpath
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")


def _assert_byte_identical(tmp_path: Path, pairs: dict[str, str]) -> str:
    """Core assertion: disk serialiser == the inlined oracle (byte-for-byte)."""
    _write_to_disk(tmp_path, pairs)
    disk = serialize_sandbox_deliverable(tmp_path)
    mem = _oracle_output(pairs)
    assert disk == mem, f"diverged:\n--- disk ---\n{disk!r}\n--- oracle ---\n{mem!r}"
    # Byte-level identity (encode to be unambiguous about "byte-identical").
    assert disk.encode("utf-8") == mem.encode("utf-8")
    return disk


# ---------------------------------------------------------------------------
# 1. Empty case → sentinel
# ---------------------------------------------------------------------------


def test_empty_dir_yields_sentinel(tmp_path: Path) -> None:
    out = _assert_byte_identical(tmp_path, {})
    assert out == "(no files written)"


def test_nonexistent_dir_yields_sentinel(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    assert serialize_sandbox_deliverable(missing) == "(no files written)"
    assert count_sandbox_deliverables(missing) == 0


def test_only_excluded_file_yields_sentinel(tmp_path: Path) -> None:
    # A run that wrote ONLY PLANNER.md has no deliverable → sentinel, matching
    # to_final_output (which filters PLANNER.md then sees an empty dict).
    out = _assert_byte_identical(tmp_path, {"PLANNER.md": "# planning notes\n"})
    assert out == "(no files written)"


# ---------------------------------------------------------------------------
# 2. Single file
# ---------------------------------------------------------------------------


def test_single_file(tmp_path: Path) -> None:
    out = _assert_byte_identical(tmp_path, {"src/app.py": "print('hello')\n"})
    # Content already ends in "\n"; the block format appends another "\n"
    # before the closing fence (exactly as to_final_output's f-string does).
    assert out == "```filename: src/app.py\nprint('hello')\n\n```"


# ---------------------------------------------------------------------------
# 3. Multiple files incl. nested paths → sorted, blank-line-joined
# ---------------------------------------------------------------------------


def test_multiple_nested_files_sorted(tmp_path: Path) -> None:
    pairs = {
        "src/components/Dashboard.tsx": "export const Dashboard = () => null;\n",
        "README.md": "# Project\n",
        "src/app.py": "print('hi')\n",
        "a/b/c.txt": "deeply nested\n",
        "package.json": '{\n  "name": "x"\n}\n',
    }
    out = _assert_byte_identical(tmp_path, pairs)
    # Independently assert the exact bytes (path-sorted, ``\n\n``-joined).
    expected = "\n\n".join(
        f"```filename: {p}\n{pairs[p]}\n```" for p in sorted(pairs)
    )
    assert out == expected
    # And pin the FULL golden string as a literal (captured from the real
    # AgentWorkspace.to_final_output oracle pre-deletion) — independent of the
    # inlined oracle above.
    assert out == (
        "```filename: README.md\n# Project\n\n```\n\n"
        "```filename: a/b/c.txt\ndeeply nested\n\n```\n\n"
        '```filename: package.json\n{\n  "name": "x"\n}\n\n```\n\n'
        "```filename: src/app.py\nprint('hi')\n\n```\n\n"
        "```filename: src/components/Dashboard.tsx\n"
        "export const Dashboard = () => null;\n\n```"
    )
    # Ordering sanity: README.md (uppercase R, 0x52) sorts before lowercase dirs.
    assert out.index("README.md") < out.index("a/b/c.txt")
    assert out.index("a/b/c.txt") < out.index("package.json")
    assert out.index("package.json") < out.index("src/app.py")


# ---------------------------------------------------------------------------
# 4. PLANNER.md at root is excluded; siblings remain
# ---------------------------------------------------------------------------


def test_planner_md_excluded_root(tmp_path: Path) -> None:
    pairs = {
        "PLANNER.md": "# Deep Planner Analysis\n",
        "src/main.py": "x = 1\n",
        "docs/guide.md": "# Guide\n",
    }
    out = _assert_byte_identical(tmp_path, pairs)
    assert "PLANNER.md" not in out
    assert "src/main.py" in out
    assert "docs/guide.md" in out
    # Exactly the two deliverable files appear.
    assert out.count("```filename:") == 2
    # Golden literal (captured from the real AgentWorkspace oracle pre-deletion):
    # PLANNER.md filtered, the two survivors path-sorted (docs/ < src/).
    assert out == (
        "```filename: docs/guide.md\n# Guide\n\n```\n\n"
        "```filename: src/main.py\nx = 1\n\n```"
    )


# ---------------------------------------------------------------------------
# 5. Content edge cases that the block format must preserve verbatim
# ---------------------------------------------------------------------------


def test_content_with_fences_and_blank_lines(tmp_path: Path) -> None:
    # Content containing its own triple-backticks, trailing/leading blank lines,
    # unicode, and no trailing newline — all must round-trip byte-for-byte. (The
    # block format is intentionally lossy-ambiguous re: nested fences, but BOTH
    # serialisers are identically lossy, so byte-equivalence still holds.)
    pairs = {
        "guide.md": "# Title\n\n```python\nprint('x')\n```\n\nDone.",
        "weird.txt": "\n\nleading blank lines and trailing spaces   \n",
        "unicode.txt": "café — naïve — 🚀\n",
        "no_newline.py": "x = 1",  # deliberately no trailing newline
    }
    out = _assert_byte_identical(tmp_path, pairs)
    # Golden literal (captured from the real AgentWorkspace oracle pre-deletion).
    # Note the nested ```python fence inside guide.md round-trips verbatim, and
    # the no-trailing-newline file emits ``x = 1\n``` `` (one \n from the format).
    assert out == (
        "```filename: guide.md\n# Title\n\n```python\nprint('x')\n```\n\nDone.\n```\n\n"
        "```filename: no_newline.py\nx = 1\n```\n\n"
        "```filename: unicode.txt\ncafé — naïve — 🚀\n\n```\n\n"
        "```filename: weird.txt\n\n\nleading blank lines and trailing spaces   \n\n```"
    )


def test_empty_content_file(tmp_path: Path) -> None:
    # A zero-byte file must serialise identically (``...\n\n``` `` `` `).
    out = _assert_byte_identical(tmp_path, {"empty.txt": "", "real.txt": "data\n"})
    # Golden literal: empty.txt → ``...\n\n``` `` (the format's two \n surround the
    # empty content); real.txt follows after the ``\n\n`` block join.
    assert out == (
        "```filename: empty.txt\n\n```\n\n"
        "```filename: real.txt\ndata\n\n```"
    )


# ---------------------------------------------------------------------------
# 6. count_sandbox_deliverables mirrors the inlined file_count() oracle
# ---------------------------------------------------------------------------


def test_count_matches_file_count(tmp_path: Path) -> None:
    pairs = {
        "PLANNER.md": "internal\n",
        "src/a.py": "a\n",
        "src/b.py": "b\n",
        "README.md": "r\n",
    }
    _write_to_disk(tmp_path, pairs)
    # 3 deliverables (PLANNER.md excluded) — matches the inlined file_count oracle
    # AND the literal 3 captured from the real AgentWorkspace.file_count().
    assert count_sandbox_deliverables(tmp_path) == _oracle_count(pairs) == 3


def test_count_empty_and_only_internal(tmp_path: Path) -> None:
    assert count_sandbox_deliverables(tmp_path) == 0
    (tmp_path / "PLANNER.md").write_text("x\n", encoding="utf-8")
    assert count_sandbox_deliverables(tmp_path) == 0


# ---------------------------------------------------------------------------
# 7. Binary / unreadable handling: skipped by the serialiser, still counted
# ---------------------------------------------------------------------------


def test_binary_file_skipped_by_serializer(tmp_path: Path) -> None:
    # A non-UTF-8 file cannot be expressed as a text block; the serialiser skips
    # it (never raises, never emits a corrupt block). The in-memory workspace
    # never holds such content (write_file is str-only), so this is the disk
    # path's defensive guard — asserted directly, not against to_final_output.
    (tmp_path / "good.py").write_text("ok\n", encoding="utf-8")
    (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe\x00\x01")
    out = serialize_sandbox_deliverable(tmp_path)
    # Only the UTF-8 file appears, in the standard block format.
    assert out == "```filename: good.py\nok\n\n```"
    # But it IS a file on disk, so the count (which mirrors file_count's
    # content-agnostic key count) includes it.
    assert count_sandbox_deliverables(tmp_path) == 2


# ---------------------------------------------------------------------------
# 8. Custom exclude set
# ---------------------------------------------------------------------------


def test_custom_exclude_set(tmp_path: Path) -> None:
    pairs = {"keep.py": "k\n", "drop.md": "d\n", "PLANNER.md": "p\n"}
    _write_to_disk(tmp_path, pairs)
    # With a custom exclude, PLANNER.md is NOT excluded (it's not in the set);
    # drop.md is. Mirrors to_final_output called with the matching internal set.
    out = serialize_sandbox_deliverable(tmp_path, exclude={"drop.md"})
    assert "drop.md" not in out
    assert "keep.py" in out
    assert "PLANNER.md" in out
    assert count_sandbox_deliverables(tmp_path, exclude={"drop.md"}) == 2


# ---------------------------------------------------------------------------
# 9. Property-based: byte-identical for any realistic (path, content) set
# ---------------------------------------------------------------------------

# Path segments: lowercase only (so the set can never collide under a
# case-insensitive filesystem), no separators/dots-only, bounded length.
_seg = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-",
    min_size=1,
    max_size=8,
).filter(lambda s: s not in {".", ".."})

_relpath = st.lists(_seg, min_size=1, max_size=4).map("/".join)

# Content: arbitrary text incl. newlines, fences, unicode — but text (the
# workspace only ever stores str). Exclude lone surrogates / NUL which a real
# UTF-8 filesystem write would reject.
_content = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs",), blacklist_characters="\x00"
    ),
    max_size=120,
)

def _no_file_dir_conflict(pairs: dict[str, str]) -> bool:
    """Reject sets a real filesystem can't hold: one path being a directory
    prefix of another (e.g. ``"a"`` AND ``"a/b"`` — ``a`` can't be both a file
    and a directory). The in-memory dict has no such constraint, but a real
    code-gen deliverable on disk does, so this is outside the byte-equivalence
    domain by construction, not a serialiser flaw.
    """
    keys = list(pairs)
    for i, a in enumerate(keys):
        a_parts = a.split("/")
        for b in keys[i + 1 :]:
            b_parts = b.split("/")
            shorter, longer = sorted((a_parts, b_parts), key=len)
            if longer[: len(shorter)] == shorter:
                return False
    return True


_pairs = st.dictionaries(keys=_relpath, values=_content, max_size=6).filter(
    _no_file_dir_conflict
)


@settings(max_examples=200, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(pairs=_pairs)
def test_property_byte_identical_to_workspace(tmp_path: Path, pairs: dict[str, str]) -> None:
    """Property: serialize_sandbox_deliverable == to_final_output, byte-for-byte.

    Spans nested paths, the PLANNER.md exclusion, fence/unicode/blank-line
    content, and the empty case — across 200 random realistic file sets.
    """
    # Hypothesis reuses the function-scoped tmp_path across examples; isolate.
    case_dir = tmp_path / f"case_{abs(hash(frozenset(pairs.items()))) & 0xFFFFFFF}"
    case_dir.mkdir(parents=True, exist_ok=True)
    _assert_byte_identical(case_dir, pairs)
