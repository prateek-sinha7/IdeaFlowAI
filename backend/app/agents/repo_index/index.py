"""app/agents/repo_index/index.py — the optional tree-sitter symbol index (REPO-02 / D-03/D-04).

The brownfield search seam: ONE registered capability exposing TWO methods so the
default grep/glob and the optional symbol index resolve through a single seam:

  * ``search(pattern, *, glob=None) -> list[Match]`` — the DEFAULT. Backs onto the
    ``Workspace.search`` grep over the cloned tree via the ``ctx.runner`` handle.
    ALWAYS available (no index build, no tree-sitter needed).
  * ``symbol_query(name) -> list[SymbolHit]`` — only meaningful once the symbol
    index is BUILT (manifest opt-in OR the N6 file-count threshold). Returns the
    file + line + kind of a matching function / class / import.

Index lifecycle (D-04): the symbol index is built IN-MEMORY PER-RUN (no new DB
table, no new column) when ``should_build_index(...)`` is true — i.e. the manifest
declared ``repo.index = True`` OR the repo's source-file count exceeds the
documented N6 threshold (:data:`REPO_INDEX_FILE_THRESHOLD`). It is discarded when
the run's workspace is torn down. Embeddings are OUT of scope.

Heavy-dep isolation (REPO-02 acceptance / T-09-03-02): the ``tree_sitter`` import
(and the per-language grammar wheels) live HERE and ONLY here — this is why the
capability is APP-SIDE, reached via the handle. The kernel never imports
tree-sitter; the import-linter contract + the ``grep -rn "import tree_sitter"``
acceptance gate both pin this.

Offline grammars (RESEARCH R-C Open Risk realized): the per-language prebuilt
grammar wheels (``tree-sitter-python`` / ``-javascript`` / ``-typescript``) bundle
the compiled grammar IN the wheel, so ``Language(...)`` works with ZERO network
(proven offline in ``test_repo_index.py``). The originally-planned
``tree-sitter-language-pack`` LAZY-DOWNLOADS grammars at first use and is NOT used
here (it fails the offline accept gate).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agents.capabilities.registry import register

# ── N6 threshold (D-04) ──────────────────────────────────────────────────────
# A documented module-level constant: above this source-file count the symbol
# index is auto-built even without a manifest opt-in (large repos benefit from
# symbol lookup; small repos stay grep-only to skip the build cost). Conservative
# default; the exact value is Discretion (RESEARCH R-C). An ``app.core.config``
# override may shadow this later — the constant is the single documented default.
REPO_INDEX_FILE_THRESHOLD = 2000


# ── kernel-pure result dataclasses (like DeliverableContext) ─────────────────
@dataclass(frozen=True)
class Match:
    """A grep/glob hit: ``file:line:text`` decomposed (the DEFAULT search result)."""

    file: str
    line: int
    text: str


@dataclass(frozen=True)
class SymbolHit:
    """A symbol-index hit: a function / class / import name at ``file:line``."""

    file: str
    line: int
    kind: str  # "function" | "class" | "import"
    name: str


# ── language → (grammar loader, tree-sitter query) ───────────────────────────
# Functions + classes + imports are the minimal viable symbol set (REPO-02
# acceptance needs only "file+line of a known function/class"). Each entry maps a
# file extension to a (grammar-factory, S-expression query) pair. The grammar
# factories are the per-language prebuilt wheels (offline-bundled).
def _python_grammar() -> Any:
    import tree_sitter_python

    return tree_sitter_python.language()


def _javascript_grammar() -> Any:
    import tree_sitter_javascript

    return tree_sitter_javascript.language()


def _typescript_grammar() -> Any:
    import tree_sitter_typescript

    return tree_sitter_typescript.language_typescript()


# Capture names encode the symbol kind: ``fn`` → function, ``cls`` → class,
# ``imp`` → import. The query extracts the NAME node so ``start_point.row`` is the
# definition line.
_PY_QUERY = (
    "(function_definition name: (identifier) @fn)"
    " (class_definition name: (identifier) @cls)"
    " (import_statement) @imp"
    " (import_from_statement) @imp"
)
_JS_QUERY = (
    "(function_declaration name: (identifier) @fn)"
    " (class_declaration name: (identifier) @cls)"
    " (method_definition name: (property_identifier) @fn)"
    " (import_statement) @imp"
)
_TS_QUERY = _JS_QUERY + (
    " (interface_declaration name: (type_identifier) @cls)"
    " (type_alias_declaration name: (type_identifier) @cls)"
    " (enum_declaration name: (identifier) @cls)"
)

_CAPTURE_KIND = {"fn": "function", "cls": "class", "imp": "import"}

_LANGS: dict[str, tuple[Any, str]] = {
    ".py": (_python_grammar, _PY_QUERY),
    ".js": (_javascript_grammar, _JS_QUERY),
    ".jsx": (_javascript_grammar, _JS_QUERY),
    ".ts": (_typescript_grammar, _TS_QUERY),
    ".tsx": (_typescript_grammar, _TS_QUERY),
}


def should_build_index(*, declared: bool, file_count: int) -> bool:
    """The index-build DECISION (D-04 / INV-5): ``declared OR file_count > N6``.

    The compiler only RECORDS the manifest ``repo.index`` flag; this control flow
    lives in the capability, never the compiler. Exposed as a module function so a
    test can pin the threshold semantics without a full run.
    """
    return bool(declared) or file_count > REPO_INDEX_FILE_THRESHOLD


@register(
    "repo_index",
    "tree_sitter",
    description="Build an app-side symbol index of the source repo via tree-sitter (isolated).",
)
class RepoIndex:
    """The optional symbol index over a cloned repo (``name='tree_sitter'``).

    Stateless registered impl; per-run index state is held on the instance passed
    to :meth:`build` (callers build a fresh index per run via :meth:`build`, which
    returns a populated index object — the registered singleton is the FACTORY /
    default-search seam). ``search`` needs no build; ``symbol_query`` needs one.
    """

    name = "tree_sitter"

    def __init__(self) -> None:
        # Per-run symbol table: name -> list[SymbolHit]. Empty until build().
        self._symbols: dict[str, list[SymbolHit]] = {}
        self._built = False

    # -- the DEFAULT search (grep/glob, always available) --------------------
    def search(self, runner: Any, pattern: str, *, glob: str | None = None) -> list[Match]:
        """Grep the workspace tree for ``pattern`` via the ``Workspace.search`` handle.

        ALWAYS available (no index build). Reaches the workspace grep through the
        ``ctx.runner`` handle (``runner.workspace.search`` or ``runner.search``) so
        the capability never imports ``app.*`` / the workspace impl. ``glob`` is an
        optional path filter applied to the ``rel`` portion of each hit.
        """
        workspace = getattr(runner, "workspace", None) or runner
        raw_hits = workspace.search(pattern)
        matches: list[Match] = []
        for hit in raw_hits:
            # Workspace.search returns "rel:line:text" strings.
            parts = hit.split(":", 2)
            if len(parts) != 3:
                continue
            rel, lineno, text = parts
            if glob is not None and not _fnmatch(rel, glob):
                continue
            try:
                line = int(lineno)
            except ValueError:
                continue
            matches.append(Match(file=rel, line=line, text=text))
        return matches

    # -- the symbol index (built on opt-in / N6 threshold) -------------------
    def build(self, runner: Any, *, declared: bool = False) -> "RepoIndex":
        """Build the in-memory symbol index over the cloned repo (per-run, D-04).

        Walks the workspace's source files (reached via the handle), parses each
        supported-language file with its prebuilt grammar, and records every
        function / class / import name → :class:`SymbolHit`. Returns ``self`` (the
        populated index) so a caller can chain ``.build(...).symbol_query(...)``.

        Honors the build DECISION: if neither ``declared`` nor the N6 threshold
        fires, the index stays empty (grep-only). The ``tree_sitter`` import is
        local to this method so merely importing the module is import-light.
        """
        files = _list_source_files(runner)
        if not should_build_index(declared=declared, file_count=len(files)):
            self._built = False
            return self

        from tree_sitter import Language, Parser, Query, QueryCursor

        # Cache one (Language, Parser, Query) per extension across the walk.
        compiled: dict[str, tuple[Any, Any, Any]] = {}
        for rel, ext in files:
            spec = _LANGS.get(ext)
            if spec is None:
                continue
            if ext not in compiled:
                grammar_factory, query_src = spec
                lang = Language(grammar_factory())
                compiled[ext] = (lang, Parser(lang), Query(lang, query_src))
            lang, parser, query = compiled[ext]
            try:
                source = _read_source(runner, rel)
            except Exception:  # noqa: BLE001 — an unreadable file must not abort the index
                continue
            tree = parser.parse(source.encode("utf-8"))
            captures = QueryCursor(query).captures(tree.root_node)
            for cap_name, nodes in captures.items():
                kind = _CAPTURE_KIND.get(cap_name)
                if kind is None:
                    continue
                for node in nodes:
                    symbol_name = node.text.decode("utf-8")
                    hit = SymbolHit(
                        file=rel,
                        line=node.start_point[0] + 1,
                        kind=kind,
                        name=symbol_name,
                    )
                    self._symbols.setdefault(symbol_name, []).append(hit)
        self._built = True
        return self

    def symbol_query(self, name: str) -> list[SymbolHit]:
        """Return the :class:`SymbolHit`s for symbol ``name`` (empty if not indexed)."""
        return list(self._symbols.get(name, []))


# ── helpers (reach the workspace via the handle; no app.* import) ────────────
def _fnmatch(rel: str, glob: str) -> bool:
    from fnmatch import fnmatch

    return fnmatch(rel, glob)


def _list_source_files(runner: Any) -> list[tuple[str, str]]:
    """Return ``[(relpath, ext), ...]`` for the cloned tree via the handle.

    Prefers an explicit ``runner.workspace.list_files()`` if present; otherwise
    walks the workspace root reached via the handle. Keeps this module free of any
    ``app.*`` import — it only touches the duck-typed workspace surface.
    """
    workspace = getattr(runner, "workspace", None) or runner
    list_files = getattr(workspace, "list_files", None)
    if callable(list_files):
        rels = list_files()
    else:
        # Fall back to deriving relpaths from a root walk if the workspace exposes one.
        root = getattr(workspace, "root", None) or getattr(workspace, "_root", None)
        if root is None:
            return []
        from pathlib import Path

        root_path = Path(root)
        rels = [
            p.relative_to(root_path).as_posix()
            for p in sorted(root_path.rglob("*"))
            if p.is_file() and ".git" not in p.parts
        ]
    out: list[tuple[str, str]] = []
    for rel in rels:
        dot = rel.rfind(".")
        ext = rel[dot:] if dot != -1 else ""
        out.append((rel, ext))
    return out


def _read_source(runner: Any, rel: str) -> str:
    workspace = getattr(runner, "workspace", None) or runner
    return workspace.read_file(rel)


# Silence "imported but unused" for the field import on minimal builds.
_ = field
