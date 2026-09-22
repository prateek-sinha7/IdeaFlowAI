"""Wave-0 acceptance for the optional tree-sitter symbol index (Phase 09 / REPO-02).

Drives the ``repo_index`` capability fully OFFLINE:

  * the OFFLINE-INSTALL PROOF (RESEARCH R-C Open Risk): ``Language(...)`` from the
    per-language prebuilt grammar wheels parses a fixture with the network DISABLED
    and yields a non-empty tree — proving the grammars are wheel-bundled, NOT
    lazy-downloaded. (The originally-planned ``tree-sitter-language-pack==1.8.1``
    lazy-downloads grammars and FAILS this gate; the documented R-C fallback —
    per-language wheels — is taken.)
  * index OFF → grep/glob (``search``) is the default and always available;
  * index ON → ``symbol_query`` returns the file + line of a known function/class.

The heavy ``tree_sitter`` import lives ONLY behind ``app.agents.repo_index`` — the
REPO-02 acceptance gate (``grep -rn "import tree_sitter"`` finds only that module)
is asserted by the verify step, not here.
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from agents.capabilities.registry import CapabilityRegistry, discover


# ── A minimal handle: a duck-typed workspace over a real on-disk tree ─────────
class _FakeWorkspace:
    """Stand-in for the LocalWorkspace surface the index reaches via the handle."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def read_file(self, relpath: str) -> str:
        return (self.root / relpath).read_text(encoding="utf-8")

    def list_files(self) -> list[str]:
        return [
            p.relative_to(self.root).as_posix()
            for p in sorted(self.root.rglob("*"))
            if p.is_file() and ".git" not in p.parts
        ]

    def search(self, query: str) -> list[str]:
        hits: list[str] = []
        for rel in self.list_files():
            text = (self.root / rel).read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), start=1):
                if query in line:
                    hits.append(f"{rel}:{lineno}:{line}")
        return hits


class _FakeRunner:
    def __init__(self, workspace: _FakeWorkspace) -> None:
        self.workspace = workspace


@pytest.fixture()
def repo_tree(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text(
        '"""mod."""\n\n\ndef greet(name):\n    return f"hi {name}"\n\n\nclass Service:\n    def run(self):\n        return greet("x")\n',
        encoding="utf-8",
    )
    (src / "util.js").write_text(
        "function helper(a){ return a + 1; }\nclass Box {}\n",
        encoding="utf-8",
    )
    return tmp_path


def _index():
    discover()
    idx = CapabilityRegistry().resolve("repo_index", "tree_sitter")
    return idx


# ── OFFLINE-INSTALL PROOF ─────────────────────────────────────────────────────
def test_grammars_parse_offline_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """The per-language grammars parse with ZERO network (wheel-bundled, not lazy)."""

    def _blocked(*_a, **_k):  # noqa: ANN002, ANN003
        raise OSError("network disabled for the offline-grammar proof")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)

    import tree_sitter_javascript
    import tree_sitter_python
    import tree_sitter_typescript
    from tree_sitter import Language, Parser

    cases = [
        (Language(tree_sitter_python.language()), b"def f(x):\n    return x\n"),
        (Language(tree_sitter_javascript.language()), b"function f(x){ return x; }\n"),
        (
            Language(tree_sitter_typescript.language_typescript()),
            b"function f(x: number): number { return x; }\n",
        ),
    ]
    for lang, src in cases:
        tree = Parser(lang).parse(src)
        assert tree.root_node.child_count > 0, "expected a non-empty parse tree offline"


# ── index OFF → grep/glob is the default ──────────────────────────────────────
def test_search_is_the_default_without_an_index(repo_tree: Path) -> None:
    runner = _FakeRunner(_FakeWorkspace(repo_tree))
    idx = _index()

    # No build() call: grep still works (the always-available default seam).
    matches = idx.search(runner, "def greet")
    assert any(m.file == "src/app.py" and m.line == 4 for m in matches), matches

    # symbol_query is empty with no index built.
    assert idx.symbol_query("greet") == []


def test_search_glob_filter(repo_tree: Path) -> None:
    runner = _FakeRunner(_FakeWorkspace(repo_tree))
    idx = _index()
    py_only = idx.search(runner, "class", glob="*.py")
    assert py_only and all(m.file.endswith(".py") for m in py_only)


# ── index ON → symbol_query returns file+line of a known symbol ───────────────
def test_symbol_query_returns_file_and_line_when_built(repo_tree: Path) -> None:
    from app.agents.repo_index.index import RepoIndex

    runner = _FakeRunner(_FakeWorkspace(repo_tree))
    # A fresh per-run index; declared=True forces the build (manifest opt-in path).
    idx = RepoIndex().build(runner, declared=True)

    greet_hits = idx.symbol_query("greet")
    assert any(
        h.file == "src/app.py" and h.line == 4 and h.kind == "function"
        for h in greet_hits
    ), greet_hits

    service_hits = idx.symbol_query("Service")
    assert any(
        h.file == "src/app.py" and h.line == 8 and h.kind == "class"
        for h in service_hits
    ), service_hits

    # The JS grammar is also indexed (cross-language coverage).
    helper_hits = idx.symbol_query("helper")
    assert any(h.file == "src/util.js" and h.kind == "function" for h in helper_hits)


def test_n6_threshold_decision() -> None:
    """The build decision is ``declared OR file_count > N6`` (INV-5, capability-side)."""
    from app.agents.repo_index.index import (
        REPO_INDEX_FILE_THRESHOLD,
        should_build_index,
    )

    # Opt-in forces a build regardless of size.
    assert should_build_index(declared=True, file_count=1) is True
    # Below threshold + no opt-in → grep-only.
    assert should_build_index(declared=False, file_count=10) is False
    # Above threshold → auto-build even without opt-in.
    assert (
        should_build_index(declared=False, file_count=REPO_INDEX_FILE_THRESHOLD + 1)
        is True
    )


def test_repo_index_registered() -> None:
    discover()
    assert CapabilityRegistry().is_registered("repo_index", "tree_sitter")
