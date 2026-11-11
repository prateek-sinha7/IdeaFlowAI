"""Property tests for the skill hash and the required-files check.

# Feature: ai-workflow-builder, Property 6: Skill integrity

For any set of skill files the skill hash read from disk is the same whatever
order the files were written in and whether text files use CRLF or LF. It
changes when a file's content changes or a file is added, removed or renamed.
``missing_files`` names exactly the required files that are absent.

**Validates: Requirements 20.1, 32.9**

Every example builds its file tree in its own ``tempfile.TemporaryDirectory``
because hypothesis does not reset a function-scoped ``tmp_path`` between
examples.
"""

from __future__ import annotations

import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from app.agents.workflow_builder import skill_package

_NAME_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789"
_NAME = st.text(alphabet=_NAME_CHARS, min_size=1, max_size=4)

# Folder names start with "d" and file names with a fixed letter, so a file
# path can never collide with a folder path or differ only by letter case.
_DIR = _NAME.map(lambda name: f"d{name}")


def _paths(prefix: str) -> st.SearchStrategy[str]:
    """Relative POSIX paths with 0-2 folders whose file name starts with ``prefix``."""
    file_name = st.tuples(_NAME, st.sampled_from([".md", ".txt", ".json"])).map(
        lambda parts: f"{prefix}{parts[0]}{parts[1]}"
    )
    return st.tuples(st.lists(_DIR, max_size=2), file_name).map(
        lambda parts: "/".join([*parts[0], parts[1]])
    )


_LINES = st.lists(
    st.text(
        alphabet=st.characters(
            blacklist_characters="\r\n", blacklist_categories=("Cs",)
        ),
        max_size=12,
    ),
    max_size=5,
)

# path -> (text lines, whether the checkout used CRLF)
_TEXT_TREES = st.dictionaries(
    _paths("f"),
    st.tuples(_LINES, st.booleans()),
    min_size=1,
    max_size=6,
)


def _encode(lines: list[str], *, crlf: bool) -> bytes:
    return ("\r\n" if crlf else "\n").join(lines).encode("utf-8")


def _lf_files(tree: Mapping[str, tuple[list[str], bool]]) -> dict[str, bytes]:
    return {path: _encode(lines, crlf=False) for path, (lines, _) in tree.items()}


def _write_tree(
    root: Path, files: Mapping[str, bytes], order: Sequence[str] | None = None
) -> None:
    for relative in order if order is not None else files:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(files[relative])


def _hash_of(files: Mapping[str, bytes]) -> str:
    """Write ``files`` to a fresh temp folder and return the skill hash."""
    with tempfile.TemporaryDirectory() as tmp:
        skill_dir = Path(tmp)
        _write_tree(skill_dir, files)
        return skill_package.read_skill_facts(skill_dir).skill_hash


@settings(max_examples=100, deadline=None)
@given(tree=_TEXT_TREES)
def test_read_skill_facts_returns_same_facts_when_line_endings_differ(
    tree: dict[str, tuple[list[str], bool]],
) -> None:
    # Feature: ai-workflow-builder, Property 6: Skill integrity
    lf_files = _lf_files(tree)
    mixed_files = {
        path: _encode(lines, crlf=crlf) for path, (lines, crlf) in tree.items()
    }
    with tempfile.TemporaryDirectory() as tmp:
        lf_dir = Path(tmp) / "lf"
        mixed_dir = Path(tmp) / "mixed"
        _write_tree(lf_dir, lf_files)
        _write_tree(mixed_dir, mixed_files)
        lf_facts = skill_package.read_skill_facts(lf_dir)
        mixed_facts = skill_package.read_skill_facts(mixed_dir)

    assert mixed_facts.skill_hash == lf_facts.skill_hash
    assert dict(mixed_facts.line_counts) == dict(lf_facts.line_counts)


@settings(max_examples=100, deadline=None)
@given(
    entries=st.dictionaries(
        _paths("f"),
        st.text(alphabet="0123456789abcdef", min_size=40, max_size=40),
        min_size=1,
        max_size=8,
    ),
    data=st.data(),
)
def test_compute_skill_hash_returns_same_hash_when_entry_order_differs(
    entries: dict[str, str], data: st.DataObject
) -> None:
    # Feature: ai-workflow-builder, Property 6: Skill integrity
    pairs = list(entries.items())
    shuffled = data.draw(st.permutations(pairs))

    assert skill_package.compute_skill_hash(
        shuffled
    ) == skill_package.compute_skill_hash(pairs)


@settings(max_examples=100, deadline=None)
@given(tree=_TEXT_TREES, data=st.data())
def test_read_skill_facts_returns_same_hash_when_files_written_in_any_order(
    tree: dict[str, tuple[list[str], bool]], data: st.DataObject
) -> None:
    # Feature: ai-workflow-builder, Property 6: Skill integrity
    files = _lf_files(tree)
    shuffled = data.draw(st.permutations(sorted(files)))
    with tempfile.TemporaryDirectory() as tmp:
        sorted_dir = Path(tmp) / "sorted"
        shuffled_dir = Path(tmp) / "shuffled"
        _write_tree(sorted_dir, files, order=sorted(files))
        _write_tree(shuffled_dir, files, order=shuffled)
        sorted_hash = skill_package.read_skill_facts(sorted_dir).skill_hash
        shuffled_hash = skill_package.read_skill_facts(shuffled_dir).skill_hash

    assert shuffled_hash == sorted_hash


@settings(max_examples=100, deadline=None)
@given(tree=_TEXT_TREES, data=st.data())
def test_read_skill_facts_changes_hash_when_file_content_changes(
    tree: dict[str, tuple[list[str], bool]], data: st.DataObject
) -> None:
    # Feature: ai-workflow-builder, Property 6: Skill integrity
    files = _lf_files(tree)
    changed_path = data.draw(st.sampled_from(sorted(files)))
    changed = {**files, changed_path: files[changed_path] + b"x"}

    assert _hash_of(changed) != _hash_of(files)


@settings(max_examples=100, deadline=None)
@given(tree=_TEXT_TREES, new_path=_paths("n"), new_lines=_LINES)
def test_read_skill_facts_changes_hash_when_file_is_added(
    tree: dict[str, tuple[list[str], bool]], new_path: str, new_lines: list[str]
) -> None:
    # Feature: ai-workflow-builder, Property 6: Skill integrity
    files = _lf_files(tree)
    added = {**files, new_path: _encode(new_lines, crlf=False)}

    assert _hash_of(added) != _hash_of(files)


@settings(max_examples=100, deadline=None)
@given(tree=_TEXT_TREES, data=st.data())
def test_read_skill_facts_changes_hash_when_file_is_removed(
    tree: dict[str, tuple[list[str], bool]], data: st.DataObject
) -> None:
    # Feature: ai-workflow-builder, Property 6: Skill integrity
    files = _lf_files(tree)
    removed_path = data.draw(st.sampled_from(sorted(files)))
    remaining = {p: d for p, d in files.items() if p != removed_path}
    if not remaining:
        remaining = {"keep.md": b""}
        files = {**files, "keep.md": b""}

    assert _hash_of(remaining) != _hash_of(files)


@settings(max_examples=100, deadline=None)
@given(tree=_TEXT_TREES, new_path=_paths("n"), data=st.data())
def test_read_skill_facts_changes_hash_when_file_is_renamed(
    tree: dict[str, tuple[list[str], bool]], new_path: str, data: st.DataObject
) -> None:
    # Feature: ai-workflow-builder, Property 6: Skill integrity
    files = _lf_files(tree)
    old_path = data.draw(st.sampled_from(sorted(files)))
    renamed = {p: d for p, d in files.items() if p != old_path}
    renamed[new_path] = files[old_path]

    assert _hash_of(renamed) != _hash_of(files)


@settings(max_examples=100, deadline=None)
@given(data=st.data())
def test_missing_files_names_exactly_the_absent_required_files_when_some_are_deleted(
    data: st.DataObject,
) -> None:
    # Feature: ai-workflow-builder, Property 6: Skill integrity
    required = skill_package.required_files()
    deleted = data.draw(st.sets(st.sampled_from(required)))

    with tempfile.TemporaryDirectory() as tmp:
        skill_dir = Path(tmp)
        _write_tree(skill_dir, dict.fromkeys(required, b"x\n"))
        for path in deleted:
            (skill_dir / path).unlink()
        # A file outside the required list never counts.
        (skill_dir / "zz-extra.txt").write_bytes(b"extra")
        missing = skill_package.missing_files(skill_dir)

    assert missing == [p for p in required if p in deleted]
