#!/usr/bin/env python3
"""Build .knowledge/architecture/ from the LIVE codebase.

Source of truth is `backend/` and `frontend/src/` on disk -- not a snapshot.
This replaces the previous version, which read 549 frozen per-file cards out
of `.searchable/architecture/` (a stale artifact whose generator was deleted;
see `git status`). Those cards could only ever describe the repo as it stood
on 2026-08-14, and nothing regenerated them.

Two inputs, each from a real static-analysis tool rather than a hand-rolled
import parser:

  backend/**/*.py            pydeps        (already the original generator --
                                            the old cards carry
                                            `generator: pydeps`)
  frontend/src/**/*.{ts,tsx} dependency-cruiser
                                           (already a frontend devDependency)

File coverage comes from walking DISK, not from the tools. A file that no
other module imports is still part of its module -- it just has no edges. The
old cards did exactly this (`backend/init_db.py` shipped with `imports: []`
and `imported_by: []`), so a file is never dropped merely for being
unreachable from the import graph.

Preserved across every re-run: everything ABOVE the `---` divider in each
`MOD-*.md` (the hand-authored `## Purpose` / `## Shape` / `## Why this
shape`). That text is human analysis and is not regenerable -- it is read
back off the existing file and re-emitted byte-for-byte. Only the
AUTO-GENERATED section below the divider is rebuilt.

If an extractor fails, the run ABORTS rather than writing empty dependency
sections over good data. Losing the edges silently would be worse than not
running at all.

    python3 tools/knowledge/build_architecture.py --check       # report only, no writes
    python3 tools/knowledge/build_architecture.py               # full rebuild
    python3 tools/knowledge/build_architecture.py --only MOD-backend-agents
    python3 tools/knowledge/build_architecture.py --stale-prose # which prose is out of date
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import glob
import shutil
import subprocess
from functools import lru_cache
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import quote

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUT_DIR = REPO_ROOT / ".knowledge" / "architecture"

# Longest-prefix module roots. The most specific matching root wins; order
# here does not matter.
MODULE_ROOTS = [
    # backend
    "backend/app/api",
    "backend/app/models",
    "backend/app/services",
    "backend/app/core",
    "backend/app/agents",
    "backend/app/scripts",
    "backend/app",
    "backend/agents",
    "backend/alembic/versions",
    "backend/alembic",
    "backend/evals",
    "backend/scripts",
    "backend",
    # frontend
    "frontend/src/components/analytics",
    "frontend/src/components/catalog",
    "frontend/src/components/chat",
    "frontend/src/components/handoff",
    "frontend/src/components/history",
    "frontend/src/components/home",
    "frontend/src/components/layout",
    "frontend/src/components/library",
    "frontend/src/components/preview",
    "frontend/src/components/results",
    "frontend/src/components/savedworkflows",
    "frontend/src/components/settings",
    "frontend/src/components/sidebar",
    "frontend/src/components/ui",
    "frontend/src/components/workflow",
    "frontend/src/components",
    "frontend/src/lib",
    "frontend/src/hooks",
    "frontend/src/types",
    "frontend/src/context",
    "frontend/src/data",
    "frontend/src/providers",
    "frontend/src/styles",
    "frontend/src/app",
    "frontend/src",
]

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.S)
DIVIDER = "\n---\n"
# The authoritative boundary between hand-authored prose and the generated
# section. Anchoring on this rather than on `---` is what keeps a plain
# markdown horizontal rule inside someone's prose from truncating the file.
# Keep in step with the marker emitted in main().
AUTO_MARKER = "<!-- AUTO-GENERATED BELOW THIS LINE"
# Closing delimiter. The generated block now sits ABOVE the hand-authored
# prose (right under the frontmatter), so a start marker alone no longer says
# where generation ends and prose begins.
AUTO_END = "<!-- /AUTO-GENERATED -->"

PY_EXCLUDE = {
    ".venv", "venv", "__pycache__", "node_modules", ".mypy_cache", ".pytest_cache",
    # "tests": backend/tests/ -- the test suite, not runtime code; belongs
    # nowhere in a MODULE_ROOTS-derived architecture map.
    # "runs": backend/runs/<run_id>/... -- the per-run SANDBOX (RunSandbox)
    # holding agent-GENERATED output (arbitrary user apps written mid-run,
    # e.g. a scanned run once produced backend/runs/.../todo-app/, .../
    # expense-app/backend/tests/...). That is product OUTPUT, not VELOCITY's
    # own source -- scanning it pollutes the module map with whatever a user
    # happened to have an agent build.
    "tests", "runs",
}
FE_EXCLUDE = {
    "node_modules", ".next", "dist", "build", "coverage",
    # frontend/src/test/ -- FE test suite, same reasoning as backend "tests"
    # above. Deliberately just "test" (exact component match), not a prefix:
    # frontend/src/app/test-preview/ is a real product route and stays in.
    "test",
}
FE_SUFFIXES = {".ts", ".tsx", ".js", ".jsx"}

DEFAULT_HAND_AUTHORED = (
    "## Purpose\n\nnot yet authored\n\n"
    "## Shape\n\nnot yet authored\n\n"
    "## Why this shape\n\nnot yet authored\n"
)


# --------------------------------------------------------------------------
# disk walk -- authoritative for WHICH files exist
# --------------------------------------------------------------------------

def scan_source_files() -> list[str]:
    """Every source file on disk, repo-relative, sorted. Authoritative."""
    files: list[str] = []

    backend = REPO_ROOT / "backend"
    if backend.is_dir():
        for p in backend.rglob("*.py"):
            if PY_EXCLUDE & set(p.relative_to(REPO_ROOT).parts):
                continue
            files.append(str(p.relative_to(REPO_ROOT)))

    frontend_src = REPO_ROOT / "frontend" / "src"
    if frontend_src.is_dir():
        for p in frontend_src.rglob("*"):
            if not p.is_file() or p.suffix not in FE_SUFFIXES:
                continue
            if FE_EXCLUDE & set(p.relative_to(REPO_ROOT).parts):
                continue
            files.append(str(p.relative_to(REPO_ROOT)))

    return sorted(set(files))


def assign_module(file_path: str) -> str | None:
    best = None
    for root in MODULE_ROOTS:
        if file_path == root or file_path.startswith(root + "/"):
            if best is None or len(root) > len(best):
                best = root
    return best


def module_slug(root: str) -> str:
    return "MOD-" + root.replace("/", "-")


def language_for(file_path: str) -> str:
    return "python" if file_path.endswith(".py") else "typescript"


# --------------------------------------------------------------------------
# code signature -- what the hand-authored prose was written AGAINST
# --------------------------------------------------------------------------
# The generated block tracks files and imports, so an added or deleted file is
# always visible. A RENAME inside a file is not: `engine._run_agent` becoming
# `_run_agentic_author` leaves the file list, the import graph and every
# generated line byte-identical, while the `## Shape` prose that names
# `_run_agent` quietly becomes a lie. Nothing detected that.
#
# So each card carries two hashes: `code_signature`, recomputed here on every
# run from the module's files AND their top-level symbols, and
# `prose_signature`, stamped by whoever last wrote the prose. Equal means the
# prose was written against the code as it stands. Different means it was not,
# and `--stale-prose` says so. It is a staleness FLAG, not a diff -- deciding
# what the rename means for the prose is the model's job, not a hash's.

TS_SYMBOL = re.compile(
    r"^\s*export\s+(?:default\s+)?(?:async\s+)?"
    r"(?:function\*?|class|const|let|var|interface|type|enum)\s+([A-Za-z_$][\w$]*)",
    re.M,
)


def _py_symbols(text: str) -> list[str]:
    """Module-level defs/classes/CONSTANTS plus `Class.method`, sorted.

    Methods are included qualified because that is the granularity the prose
    actually cites -- `DeepAgentRunner.astream_events`, not just the class.
    A syntax error yields no symbols rather than raising: a file mid-edit
    must not abort an architecture rebuild.
    """
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    out: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(node.name)
        elif isinstance(node, ast.ClassDef):
            out.append(node.name)
            out += [
                f"{node.name}.{sub.name}"
                for sub in node.body
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            out += [t.id for t in targets if isinstance(t, ast.Name) and t.id.isupper()]
    return sorted(set(out))


@lru_cache(maxsize=None)
def file_symbols(rel: str) -> tuple[str, ...]:
    """Public symbol names defined by one source file.

    Python is parsed properly; TS/TSX is matched by regex on `export` lines.
    A regex is enough here because the value is only ever hashed and diffed
    against itself -- a missed export costs one undetected rename, whereas a
    node/tsc dependency would cost every run.
    """
    try:
        text = (REPO_ROOT / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ()
    if rel.endswith(".py"):
        return tuple(_py_symbols(text))
    if rel.endswith((".ts", ".tsx", ".js", ".jsx")):
        return tuple(sorted(set(TS_SYMBOL.findall(text))))
    return ()


def _digest(parts: list[str]) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()[:12]


def module_signature(mfiles, imports, imported_by, external) -> str:
    parts: list[str] = []
    for f in sorted(mfiles):
        parts.append(f + "|" + ",".join(file_symbols(f)))
    parts.append("deps:" + ",".join(sorted(imports)))
    parts.append("rdeps:" + ",".join(sorted(imported_by)))
    parts.append("ext:" + ",".join(sorted(external)))
    return _digest(parts)


def file_signature(rel, deps, rdeps, external) -> str:
    return _digest([
        rel + "|" + ",".join(file_symbols(rel)),
        "deps:" + ",".join(sorted(deps)),
        "rdeps:" + ",".join(sorted(rdeps)),
        "ext:" + ",".join(sorted(external)),
    ])


FM_FIELD = re.compile(
    r"^(?P<key>prose_signature|prose_symbols_signature|code_signature|symbols_signature):\s*(?P<val>\S+)\s*$",
    re.M,
)


def read_signatures(path: Path) -> dict[str, str]:
    """{code_signature, prose_signature} as currently stamped on a card.

    Deliberately a regex over the head of the file, not a YAML load: this runs
    over 800+ cards in --stale-prose and must not pay for a parse, and a card
    whose frontmatter is damaged should report "no signature" rather than
    explode a read-only check.
    """
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:2000]
    except OSError:
        return {}
    return {m.group("key"): m.group("val") for m in FM_FIELD.finditer(head)}


def stale_prose_report() -> int:
    """List every card whose prose was authored against different code.

    Read-only and cheap -- it compares two hashes already stamped on disk and
    runs no extractor at all, so a hook can call it on every commit.
    """
    rows: list[tuple[str, str]] = []
    unauthored: list[str] = []
    for card in (
        sorted(OUT_DIR.glob(f"{DOMAIN_PREFIX}*.md"))
        + sorted(OUT_DIR.glob("MOD-*.md"))
        + sorted((OUT_DIR / FILES_DIR_NAME).rglob("*.md"))
    ):
        sig = read_signatures(card)
        code = sig.get("code_signature")
        if not code:
            continue
        prose = sig.get("prose_signature")
        rel = str(card.relative_to(REPO_ROOT))
        if prose is None:
            # No prose has ever been authored against any version of this
            # code. Only worth reporting for module and domain cards -- 789
            # file cards with no prose is the normal, intended state, not a
            # backlog.
            if card.parent == OUT_DIR:
                unauthored.append(rel)
        elif prose != code:
            rows.append((rel, f"{prose} -> {code}"))

    for rel in unauthored:
        print(f"  UNAUTHORED  {rel}")
    for rel, delta in rows:
        print(f"  STALE       {rel}  ({delta})")
    print(f"\n{len(rows)} stale, {len(unauthored)} never authored")
    return 1 if (rows or unauthored) else 0


# --------------------------------------------------------------------------
# extractors -- authoritative for EDGES only
# --------------------------------------------------------------------------

class ExtractorError(RuntimeError):
    pass


def _backend_packages() -> list[str]:
    """Top-level importable packages under backend/ (dirs with __init__.py)."""
    backend = REPO_ROOT / "backend"
    return sorted(
        p.name for p in backend.iterdir()
        if p.is_dir() and (p / "__init__.py").is_file() and p.name not in PY_EXCLUDE
    )


@lru_cache(maxsize=1)
def python_with_pydeps() -> str:
    """Path to an interpreter that can `import pydeps`.

    `sys.executable` is the obvious choice and usually right -- but not when a
    hook launches this script. pre-commit runs with a minimal PATH, where
    `python3` is macOS's Xcode stub with no third-party packages, so
    `sys.executable -m pydeps` died with "No module named pydeps" and the whole
    architecture stage aborted. Hardcoding a Homebrew path instead would break
    on the next Python upgrade and for every other machine.

    So: try the current interpreter, then any python on PATH, then the common
    Homebrew locations, and return the first that actually has the module.
    """
    seen, candidates = set(), [sys.executable]
    for name in ("python3", "python3.13", "python3.12", "python3.11", "python"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    candidates += glob.glob("/opt/homebrew/opt/python@3.*/libexec/bin/python3")
    candidates += glob.glob("/opt/homebrew/bin/python3.*")
    candidates += glob.glob("/usr/local/opt/python@3.*/libexec/bin/python3")

    for cand in candidates:
        if not cand or cand in seen:
            continue
        seen.add(cand)
        probe = subprocess.run([cand, "-c", "import pydeps"], capture_output=True)
        if probe.returncode == 0:
            return cand
    raise ExtractorError(
        "no Python interpreter with `pydeps` installed was found.\n"
        f"  tried: {', '.join(sorted(seen))}\n"
        "  install it into one of them, e.g.  python3 -m pip install pydeps"
    )


def extract_backend_edges(known: set[str]) -> tuple[dict[str, set], dict[str, set]]:
    """pydeps over backend/ -> (file -> imported in-repo files, file -> external pkgs).

    Run once PER PACKAGE, with cwd=backend/. `backend/` itself has no
    __init__.py, so `pydeps backend` treats it as a plain directory: every
    module comes back as imported by the synthetic `__main__` and no real
    inter-module edges are traced (20 of 471 refs resolved, on this repo).
    Pointing pydeps at each package from backend/ -- the same root the code
    imports against at runtime -- traces the edges properly (22k+ refs) and
    the dotted names then match the source's own `from agents.x import y`.
    """
    packages = _backend_packages()
    if not packages:
        raise ExtractorError("no importable packages found under backend/")

    data: dict = {}
    for pkg in packages:
        cmd = [
            python_with_pydeps(), "-m", "pydeps", pkg,
            "--no-output", "--show-deps", "--max-bacon=0", "--no-config",
        ]
        proc = subprocess.run(cmd, cwd=REPO_ROOT / "backend", capture_output=True, text=True)
        if proc.returncode != 0 or not proc.stdout.strip():
            raise ExtractorError(
                f"pydeps failed on package {pkg!r} (exit {proc.returncode}). "
                f"stderr:\n{proc.stderr[:800]}"
            )
        try:
            chunk = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise ExtractorError(f"pydeps produced unparseable JSON for {pkg!r}: {exc}") from exc
        for name, entry in chunk.items():
            if not isinstance(entry, dict):
                continue
            cur = data.setdefault(name, {"imports": set(), "imported_by": set(), "path": None})
            cur["imports"].update(entry.get("imports") or [])
            cur["imported_by"].update(entry.get("imported_by") or [])
            if entry.get("path") and not cur["path"]:
                cur["path"] = entry["path"]

    # Dotted name -> repo-relative path, for in-repo modules only.
    #
    # Two aliases per file, deliberately. Invoked as `pydeps backend`, pydeps
    # keys every entry `backend.agents.x`, but the source itself imports
    # `agents.x` (backend/ is the sys.path root at runtime), so the names in
    # `imports`/`imported_by` never match the keys. Registering the
    # path-derived name alongside the pydeps key makes both forms resolve.
    # Map every known file's REAL (symlink-resolved) location back to its
    # repo-relative path. pydeps reports absolute, already-resolved paths, so
    # comparing them against REPO_ROOT directly fails whenever the source tree
    # is reached through a symlink: resolve() lands outside the root,
    # relative_to() raises, and every file is silently skipped -- yielding a
    # plausible graph with no edges at all. Resolving both sides makes the
    # comparison symlink-proof.
    real_to_rel: dict[str, str] = {}
    for f in known:
        try:
            real_to_rel[str((REPO_ROOT / f).resolve())] = f
        except OSError:
            continue

    name_to_file: dict[str, str] = {}
    for name, entry in data.items():
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        if not path:
            continue
        try:
            rel = real_to_rel.get(str(Path(path).resolve()))
        except OSError:
            rel = None
        if rel is None:
            continue  # outside the repo (stdlib / site-packages)
        name_to_file[name] = rel
        stem = rel[len("backend/"):] if rel.startswith("backend/") else rel
        if stem.endswith("/__init__.py"):
            stem = stem[: -len("/__init__.py")]
        elif stem.endswith(".py"):
            stem = stem[: -len(".py")]
        name_to_file.setdefault(stem.replace("/", "."), rel)

    imports: dict[str, set] = defaultdict(set)
    external: dict[str, set] = defaultdict(set)
    for name, entry in data.items():
        if not isinstance(entry, dict):
            continue
        src = name_to_file.get(name)
        if src is None:
            continue
        for dep in entry.get("imports") or []:
            target = name_to_file.get(dep)
            if target is not None:
                if target != src:
                    imports[src].add(target)
            elif dep != "__main__":
                external[src].add(dep.split(".")[0])
        # pydeps populates `imported_by` far more completely than `imports`
        # (451 entries vs 102 on this repo), so harvest the reverse edge too.
        for dep in entry.get("imported_by") or []:
            origin = name_to_file.get(dep)
            if origin is not None and origin != src:
                imports[origin].add(src)
    return imports, external


def extract_frontend_edges(known: set[str]) -> tuple[dict[str, set], dict[str, set]]:
    """dependency-cruiser over frontend/src -> (file -> in-repo files, file -> external pkgs)."""
    fe = REPO_ROOT / "frontend"
    if not (fe / "src").is_dir():
        return {}, {}
    # --ts-config is load-bearing: tsconfig maps `@/*` -> `./src/*`, and those
    # alias imports are precisely the CROSS-module ones. Without it every
    # `@/components/...` import comes back unresolved and the module graph
    # collapses to intra-module relative imports only.
    cmd = ["npx", "--no-install", "depcruise", "src", "--output-type", "json", "--no-config"]
    if (fe / "tsconfig.json").is_file():
        cmd += ["--ts-config", "tsconfig.json"]
    proc = subprocess.run(cmd, cwd=fe, capture_output=True, text=True)
    if proc.returncode != 0 or not proc.stdout.strip():
        raise ExtractorError(
            f"dependency-cruiser failed (exit {proc.returncode}). stderr:\n{proc.stderr[:800]}"
        )
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ExtractorError(f"dependency-cruiser produced unparseable JSON: {exc}") from exc

    imports: dict[str, set] = defaultdict(set)
    external: dict[str, set] = defaultdict(set)
    for mod in data.get("modules", []):
        src_rel = mod.get("source")
        if not src_rel:
            continue
        src = f"frontend/{src_rel}"
        if src not in known:
            continue
        for dep in mod.get("dependencies") or []:
            resolved = dep.get("resolved") or ""
            target = f"frontend/{resolved}"
            if target in known:
                if target != src:
                    imports[src].add(target)
                continue
            spec = dep.get("module") or ""
            if dep.get("coreModule") or (spec and not spec.startswith(".")):
                # scoped packages keep their @scope/name form
                pkg = "/".join(spec.split("/")[:2]) if spec.startswith("@") else spec.split("/")[0]
                if pkg:
                    external[src].add(pkg)
    return imports, external


# --------------------------------------------------------------------------

class PreserveError(RuntimeError):
    """Raised when rewriting a card would destroy content we cannot regenerate."""


# ---------------------------------------------------------------------------
# Reference linking in hand-authored prose
# ---------------------------------------------------------------------------
# The prose above the marker is human analysis and its WORDING is never
# touched. But the references inside it -- `engine.py`, `MOD-backend-app`,
# `FIX-201` -- were plain text, so nothing in a module card was navigable
# without grepping for the file yourself.
#
# Linking them by hand does not hold: a source file moves, a card is renamed
# (card filenames carry a datetime), and every hand-written link silently
# points at nothing. So it is done HERE, on every generation, from the file
# list and card store as they exist at that moment. Idempotent: a token that
# is already a LIVE link is skipped. A token that is already a file link
# whose target no longer exists (the file behind it was deleted) is unwrapped
# back to plain text -- deletion is exactly the case linking must also undo,
# or the prose keeps a clickable link to nothing forever.
FILE_EXT = r"(?:py|ts|tsx|js|jsx|json|yaml|yml|sql|css)"
FILE_TOKEN = re.compile(
    r"(?<![\w/.`-])([A-Za-z0-9_][A-Za-z0-9_./-]*\." + FILE_EXT + r")(?![\w`])"
)
CODESPAN_FILE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]*\." + FILE_EXT + r"$")
SPLIT_SPANS = re.compile(r"(\[[^\]]*\]\([^)]*\)|`[^`\n]+`)")
FILE_LINK = re.compile(r"^\[([^\]]+)\]\(\.\./\.\./([^)]+)\)$")
FENCE = ("```", "~~~")


def _card_index() -> dict[str, str]:
    """id -> filename, for every card in the store."""
    out = {}
    for c in sorted((REPO_ROOT / ".knowledge" / "cards").glob("*.md")):
        m = re.search(r"^id:\s*(.+?)\s*$", c.read_text(encoding="utf-8", errors="replace"), re.M)
        if m:
            out[m.group(1).strip().strip("'\"")] = c.name
    return out


def linkify_prose(prose: str, own_files: list[str], all_files: set[str],
                  module_ids: set[str], cards: dict[str, str]) -> str:
    """Wrap file / module / card references in prose with markdown links.

    Ambiguity is left alone on purpose: `base.py` matches five files under
    backend/agents, and guessing one would be worse than plain text. Same for
    template paths like `agents/workflows/<id>/workflow.yaml`.
    """
    by_base: dict[str, set] = defaultdict(set)
    for f in all_files:
        by_base[f.rsplit("/", 1)[-1]].add(f)
    own_base: dict[str, set] = defaultdict(set)
    for f in own_files:
        own_base[f.rsplit("/", 1)[-1]].add(f)

    def resolve_symbol(tok: str) -> str | None:
        """`deep_agent_runner.DeepAgentRunner` / `sandbox.RunSandbox` -> the file.

        Prose names a symbol by its module far more often than by filename --
        `model_factory.build_model`, `chat_runner.ChatRunner` -- and those read
        as the most concrete references on the page while being the least
        followable. Only the leading module segment is resolved, and only
        against files already in THIS module, so a dotted attribute chain on a
        local variable cannot masquerade as a module path.
        """
        head = tok.split(".", 1)[0]
        if not head or "." not in tok or "/" in tok or " " in tok:
            return None
        hits = {f for f in own_files if f.rsplit("/", 1)[-1] == head + ".py"}
        return hits.pop() if len(hits) == 1 else None

    def resolve_file(tok: str) -> str | None:
        tok = tok.strip().lstrip("/")
        if "<" in tok or "*" in tok:
            return None
        if "/" in tok:
            if tok in all_files:
                return tok
            hits = {f for f in own_files if f.endswith("/" + tok)} or \
                   {f for f in all_files if f.endswith("/" + tok)}
            return hits.pop() if len(hits) == 1 else None
        hits = own_base.get(tok) or by_base.get(tok) or set()
        return next(iter(hits)) if len(hits) == 1 else None

    ids_pat = None
    if module_ids or cards:
        names = sorted(list(module_ids) + list(cards), key=len, reverse=True)
        ids_pat = re.compile(r"(?<![\w/\[-])(" + "|".join(re.escape(n) for n in names) + r")(?![\w-])")

    def link_id(m):
        name = m.group(1)
        if name in module_ids:
            return f"[{name}]({name}.md)"
        return f"[{name}](../cards/{cards[name]})"

    out, in_fence = [], False
    for line in prose.split("\n"):
        if line.lstrip().startswith(FENCE):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:                      # mermaid labels are not references
            out.append(line)
            continue
        segs = SPLIT_SPANS.split(line)
        for i, s in enumerate(segs):
            if not s:
                continue
            if s.startswith("["):
                m = FILE_LINK.match(s)
                if m and m.group(2) not in all_files:
                    segs[i] = m.group(1)  # dead file link -> unwrap to plain text
                continue                  # otherwise already linked, leave alone
            if s.startswith("`"):
                inner = s[1:-1]
                tgt = resolve_file(inner) if CODESPAN_FILE.match(inner) else resolve_symbol(inner)
                if tgt:
                    # Plain text as the link label, NOT the code span. A link
                    # whose text is a code span -- [`engine.py`](...) -- is
                    # legal CommonMark but several previewers render it as
                    # literal text instead of a link, which is worse than no
                    # link at all: it looks broken and cannot be clicked. The
                    # generated Files list above uses plain labels and renders
                    # everywhere, so match it.
                    segs[i] = f"[{inner}](../../{tgt})"
                continue
            def sub_file(m):
                tgt = resolve_file(m.group(1))
                return f"[{m.group(1)}](../../{tgt})" if tgt else m.group(1)
            s2 = FILE_TOKEN.sub(sub_file, s)
            if ids_pat is not None:
                s2 = ids_pat.sub(link_id, s2)
            segs[i] = s2
        out.append("".join(segs))
    return "\n".join(out)


# Matches the stamp in BOTH forms it is written in: YAML frontmatter in each
# MOD-*.md (`last_synced: 2026-01-01`) and JSON in modules.json
# (`  "generated_at": "2026-01-01",`). Handling only the first left modules.json
# rewriting itself on every commit while all 36 cards stayed clean.
VOLATILE_FM = re.compile(
    r"^\s*(?:\"?(?:last_synced|generated_at)\"?)\s*:.*$", re.M
)


def write_if_changed(path: Path, content: str) -> bool:
    """Write only when the SUBSTANTIVE content differs. True if it wrote.

    `last_synced` and `generated_at` record when the scan ran, not what it
    found -- so comparing them makes every card differ on every commit, and
    all 37 architecture files churn even though the code they describe is
    untouched. That noise buries real architecture changes in review, and it
    makes any regenerate-on-commit hook report a modification every time.

    So the comparison ignores those two lines, and when nothing else moved the
    file is left alone -- keeping the stamp of the commit the content was
    ACTUALLY derived from, which is the more truthful value anyway.
    """
    try:
        prior = path.read_text(encoding="utf-8")
    except OSError:
        path.write_text(content, encoding="utf-8")
        return True
    if VOLATILE_FM.sub("", prior) == VOLATILE_FM.sub("", content):
        return False
    path.write_text(content, encoding="utf-8")
    return True


def read_hand_authored(out_path: Path) -> str:
    """Recover the human-written section above the divider.

    NEVER returns the placeholder for a file that already has content. The
    `## Purpose` / `## Shape` / `## Why this shape` prose is human analysis
    and is not regenerable, so every path that cannot confidently locate it
    raises instead of quietly handing back "not yet authored" -- which would
    then be written over the real thing.

    Only a missing or empty file legitimately yields the placeholder.
    """
    if not out_path.exists():
        return DEFAULT_HAND_AUTHORED
    text = out_path.read_text()
    if not text.strip():
        return DEFAULT_HAND_AUTHORED
    m = FRONTMATTER_RE.match(text)
    if not m:
        raise PreserveError(
            f"{out_path.name}: frontmatter will not parse, so the hand-authored "
            f"section cannot be located ({len(text)} bytes at risk)"
        )

    # Validate the captured block is REALLY frontmatter before trusting it.
    #
    # FRONTMATTER_RE's lazy `.*?` stops at the first `\n---\n` it finds. If a
    # file's CLOSING delimiter is missing or damaged, that match runs on and
    # swallows the hand-authored prose, stopping instead at the prose/auto
    # divider far below. The leftover "body" is then just the old generated
    # block -- which, having no divider of its own, looks like hand-written
    # prose and gets written back as if it were. Prose destroyed, exit 0.
    # Structural validation is what makes that detectable.
    head = m.group(1)
    try:
        fm = yaml.safe_load(head)
    except yaml.YAMLError as exc:
        raise PreserveError(
            f"{out_path.name}: frontmatter is not valid YAML ({exc.__class__.__name__}); "
            f"refusing to rewrite ({len(text)} bytes at risk)"
        ) from exc
    if not isinstance(fm, dict) or "id" not in fm:
        raise PreserveError(
            f"{out_path.name}: frontmatter is not a mapping with an `id` key; "
            f"refusing to rewrite ({len(text)} bytes at risk)"
        )
    if re.search(r"^#{1,6}\s", head, re.M) or AUTO_MARKER in head:
        # A markdown heading (or our own marker) inside "frontmatter" means the
        # closing `---` was missing and the match over-ran into the body.
        raise PreserveError(
            f"{out_path.name}: closing `---` of the frontmatter block appears to be "
            f"missing (body content captured as frontmatter); refusing to rewrite "
            f"({len(text)} bytes at risk)"
        )

    body = m.group(2)

    # Split on the AUTO-GENERATED marker, never on `---`. `---` is also a
    # perfectly ordinary markdown horizontal rule, and authors do use one
    # inside `## Purpose`/`## Shape` prose -- splitting on the first one
    # silently truncated everything after it. The marker is a string we emit
    # ourselves, so it is an unambiguous boundary.
    end = body.find(AUTO_END)
    if end != -1:
        # Current layout: frontmatter, generated block, END marker, prose.
        prose = body[end + len(AUTO_END):]
        return prose.strip("\n")

    idx = body.find(AUTO_MARKER)
    if idx == -1:
        # Never auto-generated here -- the whole body is hand-written.
        return body.strip("\n")
    # Legacy layout: prose, marker, generated block running to end-of-file.
    # Read it so a card written before the block moved is migrated, not lost.
    prose = body[:idx]
    # Drop the `---` separator line we emit between prose and marker.
    prose = re.sub(r"\n-{3,}[ \t]*\s*\Z", "\n", prose)
    return prose.strip("\n")


FILES_DIR_NAME = "files"


def _rel(from_path: Path, to_path: Path) -> str:
    """POSIX relative link from one card to another path."""
    return os.path.relpath(to_path, from_path.parent).replace(os.sep, "/")


def write_file_cards(files, file_imports, file_external, file_to_module,
                     check=False):
    """One card per source file, mirroring the repo tree under architecture/files/.

    The module cards answer "what is this subsystem for". They cannot answer
    "what does THIS file depend on", because a 240-file module's edge list is
    the union of its files' edges -- true of the module, useless for locating
    one file's blast radius. That granularity is what these restore.

    Body layout matches the module cards: a generated block first, then any
    hand-authored prose, which is preserved verbatim across regeneration.
    """
    out_root = OUT_DIR / FILES_DIR_NAME
    imported_by: dict[str, set] = defaultdict(set)
    for src, deps in file_imports.items():
        for dep in deps:
            imported_by[dep].add(src)

    written = kept = 0
    for f in files:
        card = out_root / (f + ".md")
        prose = ""
        prior_prose_sig = read_signatures(card).get("prose_signature")
        if card.exists():
            try:
                prose = read_hand_authored(card)
            except PreserveError as exc:
                print(f"  SKIP (unparseable frontmatter): {exc}")
                kept += 1
                continue

        deps = sorted(d for d in file_imports.get(f, set()) if d in file_to_module)
        rdeps = sorted(imported_by.get(f, set()))
        ext = sorted(file_external.get(f, set()))
        mod_id = module_slug(file_to_module[f])

        fm = yaml.safe_dump({
            "id": f"FILE-{f}",
            "type": "architecture-file",
            "kind": "state",
            "title": f"{f.rsplit('/', 1)[-1]} — file",
            "file": f,
            "module": mod_id,
            "language": language_for(f),
            "depends_on_count": len(deps),
            "depended_on_by_count": len(rdeps),
            "code_signature": file_signature(f, deps, rdeps, ext),
            **({"prose_signature": prior_prose_sig} if prior_prose_sig else {}),
            # `last_synced` deliberately ABSENT here, unlike on the module and
            # domain cards.
            #
            # They said "the tree looked like this at commit X", which
            # `code_signature` now answers better and per-file: a commit SHA
            # moves whenever anything in the repo moves, a content hash moves
            # when THIS file does. The name was also misleading -- it recorded
            # the commit at which the content last CHANGED, not when it was
            # last verified, so all 789 sat on one old SHA while HEAD moved on.
            #
            # The real cost was structural. Because they change on every commit
            # and the content does not, `write_if_changed` has to strip them
            # before comparing (VOLATILE_FM) or all 789 cards churn on every
            # single commit. That made one regex the only thing standing
            # between this tier and an 800-file diff per commit -- an invisible
            # tripwire for anyone adding a generator or renaming a field.
            # Dropping the fields retires the tripwire for this tier entirely.
        }, sort_keys=False, default_flow_style=False, allow_unicode=True)

        lines = [
            "<!-- AUTO-GENERATED BELOW THIS LINE — regenerated by tools/knowledge/build_architecture.py -->",
            "",
            f"**Source:** [{f}]({_rel(card, REPO_ROOT / f)})",
            "",
            f"**Module:** [{mod_id}]({_rel(card, OUT_DIR / (mod_id + '.md'))})",
            "",
            f"### Depends on ({len(deps)})",
        ]
        lines += [f"- [{d}]({_rel(card, out_root / (d + '.md'))})" for d in deps] or ["- (none)"]
        lines += ["", f"### Depended on by ({len(rdeps)})"]
        lines += [f"- [{d}]({_rel(card, out_root / (d + '.md'))})" for d in rdeps] or ["- (none)"]
        lines += ["", "### External"]
        lines += [", ".join(ext) if ext else "(none)"]
        lines += [AUTO_END, ""]

        content = "---\n" + fm + "---\n\n" + "\n".join(lines) + "\n" + prose.strip("\n")
        content = content.rstrip("\n") + "\n"
        if check:
            continue
        card.parent.mkdir(parents=True, exist_ok=True)
        if write_if_changed(card, content):
            written += 1

    # Drop cards whose source file is gone -- otherwise a deleted module keeps
    # a card describing dependencies that no longer exist anywhere.
    live = {str(out_root / (f + ".md")) for f in files}
    removed = 0
    if not check and out_root.exists():
        for stale in sorted(out_root.rglob("*.md")):
            if str(stale) not in live:
                # HARD GUARD. This is the only unlink() in the whole pipeline,
                # and it exists solely to drop a per-file card whose source is
                # gone. MOD-*.md and DOMAIN-*.md are hand-authored analysis
                # that no script can reproduce -- a widened glob or a moved
                # out_root must fail loudly here rather than delete them.
                if stale.parent == OUT_DIR or stale.name.startswith(
                    ("MOD-", DOMAIN_PREFIX)
                ):
                    raise PreserveError(
                        f"refusing to delete {stale.name}: module and domain cards "
                        f"are hand-authored and are never removed by this tool"
                    )
                stale.unlink()
                removed += 1
        for d in sorted(out_root.rglob("*"), reverse=True):
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
    print(f"File cards: {written} written, {removed} removed for deleted sources"
          + (f", {kept} skipped" if kept else ""))
    return written, removed


# ---------------------------------------------------------------------------
# Domain cards -- the layer folders cannot express
# ---------------------------------------------------------------------------
# MOD-* cards are a PARTITION of the tree: one file, one module, decided by
# which directory it sits in. That is a fact, it is free, and it answers "what
# is in backend/agents". It cannot answer "how does the kernel work" -- the
# kernel is a third of one directory, and "how a run resumes" is spread across
# four.
#
# DOMAIN-* cards are an overlapping COVER, declared not derived. A domain names
# a system concern and lists its members as globs; `models/run_event.py` can
# belong to durable-state AND run-streaming at once, which no directory can
# express. Membership lives in the card's own frontmatter rather than in a
# table here, so re-scoping a domain is an edit to the knowledge base, not a
# code change.
#
# Everything else -- signature, staleness, prose preservation -- is the same
# machinery the module cards use. A domain's `code_signature` is the union of
# its members' signatures, so editing `engine.py` flags the execution-kernel
# domain stale no matter which folder module owns that file.

DOMAIN_PREFIX = "DOMAIN-"

# ---------------------------------------------------------------------------
# The watch set -- which files a domain card is answerable for
# ---------------------------------------------------------------------------
# A domain's `members:` globs are not the whole story. Its prose traces a call
# path -- `engine.py::_run_agent` -> `factory.py::create_runner` ->
# `model_factory.py::build_model` -- and roughly half those files are NOT
# members. Watching membership alone leaves the card silently wrong the moment
# someone renames a symbol in the half it only passes through.
#
# So the watch set is members PLUS every file the prose names. The card
# declares what it is answerable for by talking about it.
#
# Deliberately coarse: FILE granularity, not symbol, and no call-graph
# walking. An earlier version hashed the calls inside each traced function so
# an inserted intermediate call would move the signature. That was precision
# nobody spends -- the response to any trigger is "re-read the changed files
# and update the card", and a model re-reads the whole file regardless. Fine
# detection only pays for itself when the repair is fine, and it is not.

TRACE_REF = re.compile(r"([A-Za-z_][\w./-]*\.(?:py|ts|tsx|js|jsx))::[A-Za-z_][\w.]*")


def parse_trace_refs(prose: str) -> list[str]:
    """File names cited as `file.py::symbol` anywhere in a card's prose."""
    return sorted(set(TRACE_REF.findall(prose)))


def _basename_index(files: list[str]) -> dict[str, list[str]]:
    idx: dict[str, list[str]] = defaultdict(list)
    for f in files:
        idx[f.rsplit("/", 1)[-1]].append(f)
    return idx


def resolve_trace_file(name: str, index: dict[str, list[str]],
                       prefer: set[str]) -> str | None:
    """Map a bare `engine.py` in prose onto one real repo path.

    Prose cites files by basename, which is ambiguous across a 789-file tree.
    A member of the domain wins over a stranger; a unique basename resolves
    outright; anything still ambiguous returns None and is REPORTED rather
    than guessed, because silently hashing the wrong file is worse than
    admitting the reference cannot be pinned.
    """
    if name in files_seen_exact:
        return name
    cands = index.get(name.rsplit("/", 1)[-1], [])
    if not cands:
        return None
    if "/" in name:
        # The prose wrote part of the path -- `capabilities/registry.py` -- to
        # disambiguate two files sharing a basename. Honour it: that is the
        # author's only lever, and there ARE two registry.py in this tree.
        tail = [c for c in cands if c.endswith("/" + name) or c == name]
        if len(tail) == 1:
            return tail[0]
        cands = tail or cands
    inside = [c for c in cands if c in prefer]
    if len(inside) == 1:
        return inside[0]
    return cands[0] if len(cands) == 1 else None


files_seen_exact: set[str] = set()


def domain_watch_set(card: Path, members: list[str], index,
                     prefer: set[str] | None = None) -> tuple[list[str], list[str]]:
    """(files this card is answerable for, prose references that did not resolve).

    Members plus every file the prose names. An unresolvable reference is
    reported and skipped, never guessed -- two files can share a basename
    (there are two `registry.py` here), and hashing the wrong one is worse
    than admitting the reference cannot be pinned. Writing more of the path
    in the prose is the author's lever.

    `prefer` widens which candidate wins the "domain member beats a
    stranger" tiebreak beyond strict membership -- callers pass members plus
    the domain's own import seam, so a dependency the domain's prose talks
    about constantly (but does not own) still disambiguates against an
    unrelated same-named file elsewhere in the repo. Defaults to `members`.
    """
    try:
        prose = read_hand_authored(card)
    except PreserveError:
        return sorted(set(members)), []
    if prefer is None:
        prefer = set(members)
    watch, unresolved = set(members), []
    for name in parse_trace_refs(prose):
        target = resolve_trace_file(name, index, prefer)
        if target is None:
            unresolved.append(name)
        else:
            watch.add(target)
    return sorted(watch), unresolved


def _match_members(patterns, files: list[str]) -> tuple[list[str], list[str]]:
    """Resolve member globs against the real file list.

    Returns (matched files, patterns that matched NOTHING). An empty pattern
    is almost always a typo or a path that moved, and silently contributing no
    files would shrink a domain without anyone noticing -- so it is reported.
    """
    import fnmatch

    matched: set[str] = set()
    empty: list[str] = []
    for pat in patterns:
        hits = fnmatch.filter(files, pat)
        if not hits:
            empty.append(pat)
        matched.update(hits)
    return sorted(matched), empty


def write_domain_cards(files, file_imports, file_external, file_to_module,
                       today, check=False):
    """Regenerate the generated block of every DOMAIN-*.md that exists.

    Never CREATES a domain card -- a domain is a judgement about what the
    system is for, and inventing one from a glob would be exactly the kind of
    unverifiable "Business Logic" box the diagram rules ban. Author the card
    with its `members:`, and this fills in the rest.
    """
    cards = sorted(OUT_DIR.glob(f"{DOMAIN_PREFIX}*.md"))
    if not cards:
        return 0, []

    file_set = set(files)
    basename_idx = _basename_index(files)
    files_seen_exact.update(files)
    written = 0
    problems: list[str] = []
    covered: set[str] = set()
    summaries = []
    traced_total = 0

    for card in cards:
        did = card.stem
        text = card.read_text(encoding="utf-8")
        m = FRONTMATTER_RE.match(text)
        if not m:
            problems.append(f"{card.name}: frontmatter will not parse -- skipped")
            continue
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError as exc:
            problems.append(f"{card.name}: invalid YAML ({exc.__class__.__name__}) -- skipped")
            continue
        patterns = fm.get("members") or []
        if not isinstance(patterns, list) or not patterns:
            problems.append(f"{card.name}: no `members:` list -- nothing to resolve")
            continue

        members, empty = _match_members(patterns, files)
        for pat in empty:
            problems.append(f"{card.name}: member pattern matched no file: {pat!r}")
        if not members:
            # All of this domain's members were removed -- regenerate as an
            # empty domain rather than refuse. "Refuse" left the OLD
            # Members/Imported-by/Imports block in place, still linking to
            # files that no longer exist; falling through with `members = []`
            # produces an honest "0 files" block instead, and the dead-link
            # sweep below still runs on its prose either way.
            problems.append(f"{card.name}: resolved to ZERO files -- "
                            f"regenerating as an empty domain")
        covered |= set(members)

        try:
            prose = read_hand_authored(card)
        except PreserveError as exc:
            problems.append(str(exc))
            continue

        mods = sorted({module_slug(file_to_module[f]) for f in members})
        external = sorted({e for f in members for e in file_external.get(f, set())})
        # Files OUTSIDE the domain that import INTO it, and vice versa -- the
        # domain's real seam with the rest of the system.
        inbound = sorted({
            src for src, deps in file_imports.items()
            if src not in members and deps & set(members) and src in file_set
        })
        outbound = sorted({
            d for f in members for d in file_imports.get(f, set())
            if d not in members and d in file_set
        })

        # What this domain's prose can name without guessing: what it owns,
        # plus its own import seam. `artifact_store/store.py` is a stranger
        # to `members` (it's an outbound dependency, not owned by the
        # domain), so a bare `store.py` in prose loses to the *other*
        # store.py in the repo unless the domain's own seam is offered as
        # disambiguating context too.
        link_scope = sorted(set(members) | set(inbound) | set(outbound))

        # Members PLUS every file the prose names -- the set this card is
        # answerable for, and the set a changed-file intersection tests
        # against. Recorded on the card so `--affected` needs no re-derivation.
        watch, unresolved = domain_watch_set(card, members, basename_idx,
                                             prefer=set(link_scope))
        for ref in unresolved:
            problems.append(f"{card.name}: prose names a file that does not resolve: {ref}")

        signature = _digest(
            [f + "|" + ",".join(file_symbols(f)) for f in watch]
            + ["mods:" + ",".join(mods), "ext:" + ",".join(external)]
        )
        _prior = read_signatures(card)
        prior_prose_sig = _prior.get("prose_signature")
        prior_prose_syms = _prior.get("prose_symbols_signature")

        fm_out = {
            "id": did,
            "type": "architecture-domain",
            "kind": "state",
            "title": fm.get("title", f"{did} — domain"),
            "members": patterns,
            "member_count": len(members),
            "modules_spanned": mods,
            # Members plus every file the prose names. Bigger than
            # member_count on purpose: it is what makes a change in a file the
            # card merely PASSES THROUGH still flag the card.
            "watched_files": len(watch),
            "code_signature": signature,
            # Files + symbols only -- recomputable from disk with no extractor,
            # so a refresh trigger can ask "did anything a diagram could draw
            # actually change?" without paying for a 40s rebuild first.
            "symbols_signature": symbols_digest(watch),
            **({"prose_signature": prior_prose_sig} if prior_prose_sig else {}),
            **({"prose_symbols_signature": prior_prose_syms} if prior_prose_syms else {}),
            # `last_synced` (a date) stays -- it answers "when was this analysis
            # written", which a reader of hand-authored prose actually asks.
            # `sync_commit` is gone: it recorded the commit at which the CONTENT
            # last changed, not when the card was verified, so it read as a
            # freshness claim it could not support. `code_signature` answers the
            # real question, per card, without a repo-wide SHA in the way.
            "last_synced": today,
        }
        head = "---\n" + yaml.safe_dump(
            fm_out, default_flow_style=False, sort_keys=False, allow_unicode=True
        ) + "---\n\n"

        by_mod: dict[str, list[str]] = defaultdict(list)
        for f in members:
            by_mod[module_slug(file_to_module[f])].append(f)

        lines = [
            "<!-- AUTO-GENERATED BELOW THIS LINE — regenerated by tools/knowledge/build_architecture.py -->",
            "",
            f"### Members ({len(members)} files across {len(mods)} modules)",
        ]
        for mod in mods:
            lines += ["", f"**[{mod}]({mod}.md)**"]
            lines += [f"- [{f}](../../{quote(f)})" for f in sorted(by_mod[mod])]
        lines += ["", f"### Imported by, from outside this domain ({len(inbound)})"]
        lines += [f"- [{f}](../../{quote(f)})" for f in inbound[:25]] or ["- (none)"]
        if len(inbound) > 25:
            lines += [f"- …and {len(inbound) - 25} more"]
        lines += ["", f"### Imports, from outside this domain ({len(outbound)})"]
        lines += [f"- [{f}](../../{quote(f)})" for f in outbound[:25]] or ["- (none)"]
        if len(outbound) > 25:
            lines += [f"- …and {len(outbound) - 25} more"]
        lines += ["", "### External"]
        lines += [", ".join(external) if external else "(none)"]
        lines += [AUTO_END, ""]

        all_module_ids = {module_slug(r) for r in set(file_to_module.values())}
        prose = linkify_prose(prose, link_scope, file_set, all_module_ids, _card_index())
        content = head + "\n".join(lines) + "\n" + prose.strip("\n") + "\n"
        if not check and write_if_changed(card, content):
            written += 1
        traced_total += len(watch)
        summaries.append({"id": did, "members": len(members), "modules": mods,
                          "watched": len(watch)})

    # Domains are a COVER, not a partition -- a file in no domain is a gap in
    # the analysis, not an error. Reported so the gap is visible rather than
    # assumed to be zero.
    uncovered = sorted(set(files) - covered)
    print(f"Domain cards: {len(cards)} found, {written} written, "
          f"{len(covered)}/{len(files)} files covered "
          f"({len(uncovered)} in no domain), {traced_total} watched file(s)")
    for msg in problems:
        print(f"  WARNING: {msg}")
    return written, uncovered


# ---------------------------------------------------------------------------
# ARCHITECTURE.md -- the domain diagram gallery
# ---------------------------------------------------------------------------
# Every domain's diagram is inlined here so the whole system reads top to
# bottom in one file. It is LIFTED from the domain card, never authored twice:
# the card is the single source of truth, this is a projection of it. Two
# hand-maintained copies of the same diagram would drift, and the drift would
# be invisible.

def affected_domains(changed: list[str]) -> int:
    """Which domain cards a changeset touches. The trigger for everything else.

    Deterministic, read-only, and needs no extractor -- it intersects the
    changed files against each card's `members:` globs and the files its prose
    names. That is the whole detection story: a hook runs this on
    `git diff --name-only` and fails with the list, and the LLM repair step is
    handed the same list so it re-reads only what moved.

    Exit 1 when anything is affected, so a hook can branch on it.
    """
    import fnmatch

    changed = [c.strip() for c in changed if c.strip()]
    if not changed:
        print("no changed files given")
        return 0

    hits: list[tuple[str, list[str]]] = []
    for card in sorted(OUT_DIR.glob(f"{DOMAIN_PREFIX}*.md")):
        m = FRONTMATTER_RE.match(card.read_text(encoding="utf-8"))
        if not m:
            continue
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            continue
        patterns = fm.get("members") or []
        # The prose's own references, resolved the same way the build does.
        prose_files = set()
        try:
            for name in parse_trace_refs(read_hand_authored(card)):
                prose_files.add(name.rsplit("/", 1)[-1])
        except PreserveError:
            pass
        touched = [
            c for c in changed
            if any(fnmatch.fnmatch(c, p) for p in patterns)
            or c.rsplit("/", 1)[-1] in prose_files
        ]
        if touched:
            hits.append((card.stem, touched))

    if not hits:
        print(f"{len(changed)} changed file(s) affect no domain card")
        return 0
    print(f"{len(changed)} changed file(s) affect {len(hits)} domain card(s):\n")
    for did, touched in hits:
        print(f"  {did}")
        for t in touched[:6]:
            print(f"      {t}")
        if len(touched) > 6:
            print(f"      …and {len(touched) - 6} more")
    print("\nRe-author each card against its changed files, then:")
    print("  python3 tools/knowledge/build_architecture.py --stamp <card>")
    return 1


# The prompt lives WITH the skill, not with the tool. `/velocity diagrams` and
# this hook must behave identically -- they are the manual and automatic paths
# through the same procedure -- and the only way to guarantee that is one file
# they both read. `skills/velocity/` is the canonical copy; `.claude/` and
# `.kiro/` are rsync mirrors of it and are never read here.
DOMAIN_PROMPT = REPO_ROOT / "skills" / "velocity" / "prompts" / "architecture-domain-update.md"
if not DOMAIN_PROMPT.exists():   # pre-move layout
    DOMAIN_PROMPT = Path(__file__).resolve().parent / "prompts" / "architecture-domain-update.md"


REQUIRED_SECTIONS = ("## Purpose", "## Shape", "## In practice", "## Why this shape")

# Mermaid keywords. Using one as a NODE ID is a parse error, not a warning --
# `graph["artifacts/graph.py"]` renders as a red error box wherever the card is
# viewed, and it shipped once because nothing checked. The obvious node id for
# `graph.py` is `graph`, so this is a trap the author walks into, not a typo.
# Scoped to the FLOWCHART grammar on purpose. `state`, `note`, `loop`, `alt`,
# `participant` and friends are keywords in the stateDiagram / sequenceDiagram
# grammars, and flagging them here would fail `state["state_machine.py"]` --
# a perfectly legal flowchart node and the natural id for that file. A linter
# that cries wolf gets ignored, and the one real bug with it.
MERMAID_RESERVED = {
    "graph", "flowchart", "subgraph", "end", "class", "classDef", "click",
    "style", "linkStyle", "direction", "default", "href", "call", "callback",
}
MERMAID_FENCE = re.compile(r"```mermaid\n(.*?)```", re.S)
NODE_DECL = re.compile(r"^\s*(\w+)\s*[\[\(\{]", re.M)


def mermaid_problems(text: str) -> list[str]:
    """Reserved-word node ids in any mermaid block. Empty list = clean."""
    bad: list[str] = []
    for m in MERMAID_FENCE.finditer(text):
        body = m.group(1)
        if body.lstrip().startswith(("sequenceDiagram", "erDiagram")):
            continue  # different grammar; node-declaration syntax does not apply
        for nid in NODE_DECL.findall(body):
            if nid in MERMAID_RESERVED and nid not in bad:
                bad.append(nid)
    return bad


def symbols_digest(watch: list[str]) -> str:
    """Digest of a watch set's files and their symbols. Nothing else.

    Deliberately excludes `modules_spanned` and the external package list,
    which is what makes it computable from DISK ALONE in milliseconds -- no
    pydeps, no dependency-cruiser. That matters twice over:

      * `--needs-rebuild` only notices files ADDED or REMOVED, so an edited
        symbol never triggers the 40s rebuild, so `code_signature` never moves,
        so nothing downstream ever learns the rename happened. This digest is
        cheap enough to recompute unconditionally and closes that hole.
      * It answers the only question a refresh trigger actually has: did
        anything a diagram could DRAW change? A reworded docstring moves no
        symbol and must not cost a re-authoring run.
    """
    return _digest([f + "|" + ",".join(file_symbols(f)) for f in sorted(watch)])


def symbols_at(rev: str, rel: str) -> tuple[str, ...]:
    """A file's symbols as of `rev`. Empty if it did not exist there."""
    out = subprocess.run(["git", "show", f"{rev}:{rel}"], cwd=REPO_ROOT,
                         capture_output=True, text=True)
    if out.returncode != 0:
        return ()
    if rel.endswith(".py"):
        return tuple(_py_symbols(out.stdout))
    if rel.endswith((".ts", ".tsx", ".js", ".jsx")):
        return tuple(sorted(set(TS_SYMBOL.findall(out.stdout))))
    return ()


def symbol_delta(watch: list[str], rev: str = "HEAD") -> list[tuple[str, str, str]]:
    """(file, '+'|'-', symbol) for every symbol that moved since `rev`.

    A hash answers "did something change" and nothing else. That is enough to
    gate on and useless for everything after: a reviewer cannot tell a rename
    from a deletion, and the re-authoring prompt gets "this file changed" when
    it could be told exactly which three symbols moved.

    No extra storage is needed for this -- the previous symbol set is already
    in git. Parsing both sides is cheap next to the model run it informs.
    """
    delta: list[tuple[str, str, str]] = []
    for rel in sorted(watch):
        was, now = set(symbols_at(rev, rel)), set(file_symbols(rel))
        for s in sorted(now - was):
            delta.append((rel, "+", s))
        for s in sorted(was - now):
            delta.append((rel, "-", s))
    return delta


def explain_domains(cards: list[str] | None = None, rev: str = "HEAD") -> int:
    """Show WHAT moved under each domain since `rev`, not just that it did."""
    files = _tracked_files()
    targets = sorted(OUT_DIR.glob(f"{DOMAIN_PREFIX}*.md"))
    if cards:
        want = {Path(c).stem for c in cards}
        targets = [t for t in targets if t.stem in want]
        missing = want - {t.stem for t in targets}
        for m in sorted(missing):
            print(f"  no such domain card: {m}")
        if missing:
            return 1
    any_change = False
    for card in targets:
        watch = live_watch_set(card, files)
        stored = read_signatures(card).get("symbols_signature")
        live = symbols_digest(watch)
        delta = symbol_delta(watch, rev)
        if not delta and stored == live:
            continue
        any_change = True
        print(f"\n{card.stem}   ({len(watch)} watched files, vs {rev})")
        if stored != live:
            print(f"  symbols_signature {stored} -> {live}")
        if not delta:
            print("  no symbol moved -- the signature differs for another reason "
                  "(a watched file was added or removed)")
        for rel, sign, sym in delta:
            print(f"    {sign} {rel}::{sym}")
    if not any_change:
        print(f"no domain's symbols moved since {rev}")
    return 0


def live_watch_set(card: Path, files: list[str]) -> list[str]:
    """A card's watch set recomputed from disk, without any extractor."""
    m = FRONTMATTER_RE.match(card.read_text(encoding="utf-8"))
    if not m:
        return []
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return []
    import fnmatch
    members: set[str] = set()
    for pat in fm.get("members") or []:
        members.update(fnmatch.filter(files, pat))
    files_seen_exact.update(files)
    watch, _ = domain_watch_set(card, sorted(members), _basename_index(files))
    return watch


def _tracked_files() -> list[str]:
    """Every tracked source file, from modules.json -- no extractor needed."""
    try:
        data = json.loads((OUT_DIR / "modules.json").read_text())
        return [f for m in data["modules"] for f in m.get("files", [])]
    except (OSError, ValueError, KeyError):
        return scan_source_files()


def _validate_domain_card(card: Path) -> str | None:
    """-> a reason the card is not properly authored, or None if it is fine.

    Exit code 0 is NOT proof of work. A session-limit refusal, a model that
    replied in prose instead of editing, an aborted run -- every one of those
    returns 0 with the card untouched, and one silently did. So the artifact is
    checked rather than the exit status.
    """
    try:
        text = card.read_text(encoding="utf-8")
    except OSError as exc:
        return f"unreadable ({exc.__class__.__name__})"
    if "not yet authored" in text:
        return "still holds the `not yet authored` placeholder"
    try:
        prose = read_hand_authored(card)
    except PreserveError as exc:
        return str(exc)
    missing = [s for s in REQUIRED_SECTIONS if s not in prose]
    if missing:
        return "missing " + ", ".join(missing)
    shape = _section(prose, "Shape")
    if "```mermaid" not in shape:
        return "`## Shape` has no mermaid diagram (nothing to inline into ARCHITECTURE.md)"
    bad = mermaid_problems(prose)
    if bad:
        return ("mermaid reserved word(s) used as node id: "
                + ", ".join(repr(b) for b in bad)
                + " -- this is a parse error wherever the card renders")
    return None


def _fallback_notice(cards: list[str] | None = None) -> None:
    """Hand the work to the human, with the exact command AND its arguments.

    Printed on every path where the automatic refresh could not finish. The
    hook still exits 0 -- losing a documentation refresh must never cost
    someone their commit -- so this message is the only thing between a skipped
    refresh and a card that quietly rots.

    It names the cards explicitly. A person mid-commit will not reconstruct a
    four-step procedure from a hook's stdout, and "some cards are stale" is a
    message people learn to scroll past; a command they can paste is not.
    """
    args = " ".join(cards) if cards else ""
    print("")
    print("  These cards are now stale. To bring them up to date, run:")
    print("")
    print(f"      /velocity diagrams {args}".rstrip())
    print("")
    print("  That skill runs the same prompt this hook would have")
    print(f"  ({DOMAIN_PROMPT.relative_to(REPO_ROOT)}), re-inlines the")
    print("  diagrams into ARCHITECTURE.md, and stamps the cards current.")
    print("  Your commit is NOT blocked.")


# Pinned, not inherited. With no `--model` the CLI falls back to whatever the
# developer has in ~/.claude/settings.json -- which on this machine is
# `opus[1m]`. That made every commit-hook refresh silently run the most
# expensive model available, up to `--max-refresh` times per commit, on work
# that a very prescriptive prompt already constrains: read a handful of files,
# fix the claims a changeset invalidated, redraw one diagram.
#
# Pinning it also makes the cost of a commit predictable and identical for
# every teammate, rather than a function of their personal settings file.
# Override with KNOWLEDGE_REFRESH_MODEL for a one-off deeper pass.
DEFAULT_REFRESH_MODEL = "sonnet"


def refresh_affected(changed: list[str], timeout: int = 900,
                     max_cards: int = 3, model: str | None = None) -> int:
    """Re-author every DOMAIN card a changeset touches, via headless Claude.

    The expensive half of the loop, and deliberately the only half that needs
    a model: `--affected` decides WHAT is stale (a glob intersection,
    milliseconds); this decides what the prose should now say, which is
    judgement.

    Each card is re-authored against the changed files ONLY -- the prompt's
    incremental mode -- so a model is not invited to rewrite paragraphs that
    nothing invalidated.

    Degrades rather than blocks. No `claude` on PATH, a timeout, a non-zero
    exit: all report and return 0. A developer must never be unable to commit
    because an optional documentation refresh could not run.
    """
    import fnmatch

    model = model or os.environ.get("KNOWLEDGE_REFRESH_MODEL", DEFAULT_REFRESH_MODEL)
    if not DOMAIN_PROMPT.exists():
        print(f"  refresh skipped: {DOMAIN_PROMPT.relative_to(REPO_ROOT)} is missing")
        return 0
    template = DOMAIN_PROMPT.read_text(encoding="utf-8")
    todo: list[tuple[Path, list[str]]] = []
    for card in sorted(OUT_DIR.glob(f"{DOMAIN_PREFIX}*.md")):
        m = FRONTMATTER_RE.match(card.read_text(encoding="utf-8"))
        if not m:
            continue
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            continue
        patterns = fm.get("members") or []
        prose_files = set()
        try:
            for name in parse_trace_refs(read_hand_authored(card)):
                prose_files.add(name.rsplit("/", 1)[-1])
        except PreserveError:
            pass
        touched = [c for c in changed
                   if any(fnmatch.fnmatch(c, p) for p in patterns)
                   or c.rsplit("/", 1)[-1] in prose_files]
        if touched:
            todo.append((card, touched))

    if not todo:
        return 0

    # A file being touched is not a reason to re-author. Reformatting, a
    # reworded comment, a changed string literal -- none of them can alter a
    # diagram, and re-authoring on them would burn a model run per commit and
    # teach everyone to disable the hook. So the FILE intersection only
    # narrows the candidates; the SYMBOL digest decides.
    tracked = _tracked_files()
    substantive: list[tuple[Path, list[str]]] = []
    for card, touched in todo:
        sigs = read_signatures(card)
        # Compare against what the PROSE was written against, never against
        # `symbols_signature`. The build refreshes that field from the current
        # disk state, and phase 1 of the hook runs the build -- so by the time
        # this gate reads it, stored and live are the same value by
        # construction and the gate can never fire. It silently shipped a
        # domain whose member list had grown while its prose had not.
        # `prose_symbols_signature` only ever moves under --stamp.
        stored = sigs.get("prose_symbols_signature")
        live = symbols_digest(live_watch_set(card, tracked))
        # "The shape did not change" is only a reason to skip a card that has
        # ALREADY been authored. A card that has never been written has no
        # prose to keep current, and its symbols_signature was stamped by the
        # very first build -- so the naive check matched, skipped, and left it
        # holding `not yet authored` forever. Authoring state comes first.
        never_authored = (
            sigs.get("prose_signature") is None
            or _validate_domain_card(card) is not None
        )
        if never_authored or stored is None or stored != live:
            substantive.append((card, touched))
        else:
            print(f"    unchanged shape, skipping: {card.stem}")
    if not substantive:
        print(f"  {len(todo)} card(s) touched, none changed shape -- nothing to do")
        return 0
    todo = substantive

    # A central file has a large blast radius -- `capabilities/registry.py`
    # legitimately touches 11 of the 14 domains, because a name seam is what
    # every domain resolves through. Re-authoring 11 cards is minutes of
    # model time, and a commit hook must not do that silently. Past the cap the
    # work is REPORTED and handed back, not skipped quietly: a sweeping change
    # is exactly when a human should decide what the docs now say.
    if len(todo) > max_cards:
        print(f"  {len(todo)} domain cards affected -- over the --max-refresh "
              f"limit of {max_cards}, so nothing was re-authored.")
        print("  A change this central deserves a deliberate pass, not a "
              "commit-hook side effect.")
        _fallback_notice([c.stem for c, _ in todo])
        return 0

    print(f"  re-authoring {len(todo)} domain card(s) with model={model} ...")
    refreshed = 0
    failed: list[str] = []
    for card, touched in todo:
        rel = str(card.relative_to(REPO_ROOT))
        # Hand the model the SYMBOL delta, not just the file list. "this file
        # changed" makes it re-read and re-reason about everything; "these two
        # symbols were renamed" points it at the exact claims to fix, which is
        # what keeps the incremental mode from becoming a rewrite.
        delta = symbol_delta(live_watch_set(card, tracked))
        block = "\n".join(touched)
        if delta:
            block += ("\n\nSymbols that moved (+ added, - removed) since HEAD:\n"
                      + "\n".join(f"  {s} {f}::{sym}" for f, s, sym in delta))
        prompt = (template
                  .replace("{{CARD}}", rel)
                  .replace("{{CHANGED_FILES}}", block))
        try:
            proc = subprocess.run(
                ["claude", "-p", "--model", model,
                 "--permission-mode", "acceptEdits",
                 "--allowedTools", "Read", "Grep", "Glob", "Edit"],
                input=prompt, cwd=REPO_ROOT, capture_output=True, text=True,
                timeout=timeout,
            )
        except FileNotFoundError:
            # No `claude` on this machine, or not on the PATH a hook inherits.
            # Nothing after this can succeed either, so stop the loop rather
            # than failing once per card, and hand the WHOLE remaining set to
            # the skill.
            print("    the `claude` CLI could not be run.")
            _fallback_notice([c.stem for c, _ in todo[len(failed) + refreshed:]])
            return refreshed
        except subprocess.TimeoutExpired:
            print(f"    TIMEOUT after {timeout}s: {card.name} -- left unchanged")
            failed.append(card.name)
            continue
        if proc.returncode != 0:
            tail = (proc.stdout or proc.stderr or "").strip().splitlines()[-1:] or [""]
            print(f"    FAILED: {card.name} -- {tail[0][:120]}")
            failed.append(card.name)
            continue
        # Exit 0 is NOT proof of work. A session-limit refusal, a model that
        # answered in prose instead of editing, an aborted run -- all return 0
        # with the card untouched. That happened: a run reported rc=0 and had
        # written nothing at all. So check the artifact, not the exit code.
        problem = _validate_domain_card(card)
        if problem:
            print(f"    NOT UPDATED: {card.name} -- {problem}")
            failed.append(card.name)
            continue
        refreshed += 1
        print(f"    updated: {card.name}  ({len(touched)} changed file(s))")

    print(f"  {refreshed}/{len(todo)} card(s) re-authored")
    if failed:
        print(f"  {len(failed)} card(s) could not be refreshed automatically.")
        _fallback_notice([Path(f).stem for f in failed])
    return refreshed


MAP_START = "<!-- MODULE-MAP -->"
MAP_END = "<!-- /MODULE-MAP -->"


def write_module_map(summaries: list[dict], check=False) -> bool:
    """Rewrite the module-map tables in ARCHITECTURE.md from modules.json.

    Counts, paths and links are pure derivations, so they are generated rather
    than written. They had drifted badly while hand-maintained -- the file
    claimed "549 tracked source files" against a real 789, and "Backend --
    Python (259 files)" against a real 499 -- and nothing noticed, because a
    number in prose looks equally authoritative whether or not it is true.

    Deliberately NOT a job for the model that authors the domain prose: a
    script gets a count right every time, for free.
    """
    arch = REPO_ROOT / ".knowledge" / "ARCHITECTURE.md"
    if not arch.exists():
        return False
    text = arch.read_text(encoding="utf-8")
    if MAP_START not in text or MAP_END not in text:
        print(f"ARCHITECTURE.md has no {MAP_START} region -- module map skipped")
        return False

    by_lang = {"Backend — Python": [], "Frontend — TypeScript": []}
    for m in summaries:
        key = "Backend — Python" if m["path"].startswith("backend") else "Frontend — TypeScript"
        by_lang[key].append(m)

    total = sum(m["file_count"] for m in summaries)
    out = [MAP_START, ""]
    out.append(f"{len(summaries)} logical modules over {total} tracked source files. "
               f"Each entry links to its")
    out.append("architecture card, which carries an auto-generated file and import "
               "rollup. Module")
    out.append("cards describe FOLDERS and carry no diagrams — for how a concern "
               "actually works,")
    out.append("read the domains above.")
    for label, mods in by_lang.items():
        if not mods:
            continue
        out += ["", f"### {label} ({sum(m['file_count'] for m in mods)} files)", "",
                "| Module | Path | Files |", "|---|---|---|"]
        for m in sorted(mods, key=lambda x: (-x["file_count"], x["id"])):
            out.append(f"| [{m['id']}](architecture/{m['id']}.md) "
                       f"| `{m['path']}` | {m['file_count']} |")
    out += ["", MAP_END]

    start, end = text.index(MAP_START), text.index(MAP_END) + len(MAP_END)
    new = text[:start] + "\n".join(out) + text[end:]
    if check:
        print(f"--check: module map would list {len(summaries)} modules, {total} files")
        return False
    wrote = write_if_changed(arch, new)
    print(f"ARCHITECTURE.md module map: {len(summaries)} modules, {total} files"
          + ("" if wrote else " (unchanged)"))
    return wrote


GALLERY_START = "<!-- DOMAIN-DIAGRAMS -->"
GALLERY_END = "<!-- /DOMAIN-DIAGRAMS -->"
MERMAID_BLOCK = re.compile(r"^```mermaid\n.*?^```", re.M | re.S)
SECTION_RE = re.compile(r"^## +(.+?)\s*$", re.M)


def _section(prose: str, name: str) -> str:
    """Body of one `## <name>` section, or ''."""
    for m in SECTION_RE.finditer(prose):
        if m.group(1).strip().lower() == name.lower():
            nxt = SECTION_RE.search(prose, m.end())
            return prose[m.end(): nxt.start() if nxt else len(prose)].strip()
    return ""


def write_gallery(check=False) -> bool:
    """Rewrite the domain-diagram gallery inside .knowledge/ARCHITECTURE.md."""
    arch = REPO_ROOT / ".knowledge" / "ARCHITECTURE.md"
    if not arch.exists():
        print("ARCHITECTURE.md missing -- gallery skipped")
        return False
    text = arch.read_text(encoding="utf-8")
    if GALLERY_START not in text or GALLERY_END not in text:
        print(f"ARCHITECTURE.md has no {GALLERY_START} region -- gallery skipped")
        return False

    out = [GALLERY_START, ""]
    drawn = plain = 0
    for card in sorted(OUT_DIR.glob(f"{DOMAIN_PREFIX}*.md")):
        try:
            prose = read_hand_authored(card)
        except PreserveError:
            continue
        fm = FRONTMATTER_RE.match(card.read_text(encoding="utf-8"))
        title = card.stem
        if fm:
            try:
                title = (yaml.safe_load(fm.group(1)) or {}).get("title", title)
            except yaml.YAMLError:
                pass
        shape = _section(prose, "Shape")
        diagram = MERMAID_BLOCK.search(shape)
        out += [f"### [{title}](architecture/{card.name})", ""]
        purpose = _section(prose, "Purpose")
        if purpose and not purpose.startswith("not yet authored"):
            # First sentence only -- the gallery is an index, not a re-read of
            # every card. Links are stripped: they are relative to the card's
            # directory and would resolve one level wrong from here.
            first = re.split(r"(?<=\.)\s", purpose.strip())[0]
            out += [re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", first).replace("\n", " "), ""]
        if diagram:
            out += [diagram.group(0), ""]
            drawn += 1
        else:
            out += ["*No diagram — see the card.*", ""]
            plain += 1
    out.append(GALLERY_END)

    start = text.index(GALLERY_START)
    end = text.index(GALLERY_END) + len(GALLERY_END)
    new = text[:start] + "\n".join(out) + text[end:]
    if check:
        print(f"--check: gallery would carry {drawn} diagram(s), {plain} without")
        return False
    wrote = write_if_changed(arch, new)
    print(f"ARCHITECTURE.md gallery: {drawn} diagram(s) inlined, {plain} domain(s) "
          f"without one{'' if wrote else ' (unchanged)'}")
    return wrote


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="report only, write nothing")
    parser.add_argument(
        "--needs-rebuild", action="store_true",
        help="exit 0 if the on-disk source file list still matches modules.json, "
             "1 if it does not. ~0.07s: a pure glob, no extractors. Lets a hook "
             "decide whether the 40s scan is warranted at all.",
    )
    parser.add_argument(
        "--only", "--only-write", action="append", default=None, dest="only",
        help="restrict which MOD-*.md files are WRITTEN (repeatable). This "
             "does NOT shorten the run: pydeps and dependency-cruiser rebuild "
             "the whole import graph either way, because one module's edges "
             "cannot be derived without the others. Use it to avoid touching "
             "prose in modules another agent is editing, not to save time. "
             "modules.json is always regenerated in full.",
    )
    parser.add_argument(
        "--stale-prose", action="store_true",
        help="list cards whose `## Shape` prose was authored against a "
             "different `code_signature` than the code now has, and module "
             "cards that have never been authored. Read-only, runs no "
             "extractor. Exit 1 if anything is stale.",
    )
    parser.add_argument(
        "--stamp", action="append", default=None, metavar="CARD",
        help="mark CARD's prose as current: copy its `code_signature` to "
             "`prose_signature`. Run this AFTER re-authoring and AFTER a "
             "rebuild -- the signature now depends on the prose (it hashes "
             "the `file::symbol` trace the prose claims), so the author "
             "cannot know it in advance. Repeatable.",
    )
    parser.add_argument(
        "--affected", nargs="*", default=None, metavar="FILE",
        help="list the DOMAIN cards a changeset touches, then exit. With no "
             "arguments, reads the changed files from `git diff --name-only "
             "--cached`. Exit 1 if any card is affected. This is the hook's "
             "trigger and the input to the re-authoring prompt.",
    )
    parser.add_argument(
        "--refresh-model", default=None, metavar="MODEL",
        help=f"model for --refresh-affected (default {DEFAULT_REFRESH_MODEL!r}, "
             f"or $KNOWLEDGE_REFRESH_MODEL). Pinned rather than inherited so a "
             f"commit costs the same for everyone regardless of their CLI "
             f"default.",
    )
    parser.add_argument(
        "--max-refresh", type=int, default=3, metavar="N",
        help="with --refresh-affected, the most cards to re-author in one "
             "run (default 3). Past it the affected cards are reported and "
             "left alone -- a change touching most of the system is a "
             "deliberate documentation pass, not a commit-hook side effect.",
    )
    parser.add_argument(
        "--explain", nargs="*", default=None, metavar="CARD",
        help="show WHICH symbols moved under each domain since a revision, "
             "instead of only that a hash differs. With no arguments, checks "
             "every domain card. Read-only; pair with --since.",
    )
    parser.add_argument(
        "--since", default="HEAD", metavar="REV",
        help="revision --explain compares against (default HEAD).",
    )
    parser.add_argument(
        "--refresh-affected", nargs="*", default=None, metavar="FILE",
        help="re-author every DOMAIN card the changeset touches using headless "
             "Claude and the prompt in tools/knowledge/prompts/, then "
             "regenerate the cards, re-inline their diagrams into "
             "ARCHITECTURE.md, and stamp them current. With no arguments, "
             "reads `git diff --name-only --cached`. Never blocks: a missing "
             "`claude` CLI, a timeout or a failed run reports and exits 0.",
    )
    args = parser.parse_args()
    only = set(args.only) if args.only else None

    if args.explain is not None:
        return explain_domains(args.explain or None, args.since)

    if args.refresh_affected is not None:
        changed = args.refresh_affected
        if not changed:
            changed = subprocess.run(
                ["git", "diff", "--name-only", "--cached"],
                cwd=REPO_ROOT, capture_output=True, text=True, check=True
            ).stdout.split()
        changed = [c for c in changed if not c.startswith(".knowledge/")]
        if not changed:
            print("no source changes -- nothing to refresh")
            return 0
        if affected_domains(changed) == 0:
            return 0
        if refresh_affected(changed, max_cards=args.max_refresh,
                            model=args.refresh_model) == 0:
            return 0
        # The prose moved, so both the signature and the gallery must follow.
        # A full rebuild is the only thing that recomputes the watch set from
        # the NEW prose -- which is exactly why the author cannot stamp itself.
        print("  regenerating cards, gallery and signatures ...")
        rc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve())],
            cwd=REPO_ROOT, capture_output=True, text=True
        )
        for line in rc.stdout.splitlines():
            if any(k in line for k in ("Domain cards", "gallery", "WARNING")):
                print("  " + line.strip())
        for card in sorted(OUT_DIR.glob(f"{DOMAIN_PREFIX}*.md")):
            sigs = read_signatures(card)
            if sigs.get("code_signature") and sigs.get("prose_signature") != sigs["code_signature"]:
                subprocess.run(
                    [sys.executable, str(Path(__file__).resolve()), "--stamp", str(card)],
                    cwd=REPO_ROOT, capture_output=True, text=True,
                )
        return 0

    if args.affected is not None:
        changed = args.affected
        if not changed:
            changed = subprocess.run(
                ["git", "diff", "--name-only", "--cached"],
                cwd=REPO_ROOT, capture_output=True, text=True, check=True
            ).stdout.split()
        return affected_domains(changed)

    if args.stale_prose:
        return stale_prose_report()

    if args.stamp:
        rc = 0
        for name in args.stamp:
            p = Path(name)
            if not p.is_absolute():
                p = REPO_ROOT / name
            if not p.exists():
                p = OUT_DIR / Path(name).name
            sigs = read_signatures(p)
            code = sigs.get("code_signature")
            if not code:
                print(f"  {p.name}: no code_signature -- rebuild first"); rc = 1; continue
            # BOTH stamps move together. `prose_signature` is what --stale-prose
            # reports on; `prose_symbols_signature` is what the refresh gate
            # tests. Advancing only one leaves the other permanently disagreeing
            # -- stamp the first alone and every commit re-authors forever.
            syms = sigs.get("symbols_signature") or symbols_digest(
                live_watch_set(p, _tracked_files()))
            text = p.read_text(encoding="utf-8")
            head = text.split("---")[1] if text.count("---") >= 2 else ""
            for key, val in (("prose_signature", code),
                             ("prose_symbols_signature", syms)):
                if f"{key}:" in head:
                    text = re.sub(rf"^{key}:.*$", f"{key}: {val}", text,
                                  count=1, flags=re.M)
                else:
                    text = re.sub(r"^(code_signature: .*)$", rf"\1\n{key}: {val}",
                                  text, count=1, flags=re.M)
                head = text.split("---")[1] if text.count("---") >= 2 else ""
            p.write_text(text, encoding="utf-8")
            print(f"  stamped {p.name}: prose={code} symbols={syms}"
                  + (f" (was {sigs['prose_signature']})" if sigs.get("prose_signature") else ""))
        return rc

    files = scan_source_files()
    if not files:
        print("ERROR: no source files found under backend/ or frontend/src/.")
        return 1

    if args.needs_rebuild:
        # Compare the file list only. Import edges can also drift without the
        # list changing (an edited import), but catching that needs the very
        # extractors this flag exists to avoid -- so this answers the cheap
        # question: has a file been ADDED or REMOVED since the last scan?
        try:
            prior = json.loads((OUT_DIR / "modules.json").read_text())
            known_prior = {f for m in prior["modules"] for f in m.get("files", [])}
        except (OSError, ValueError, KeyError):
            print("modules.json missing or unreadable -- rebuild needed")
            return 1
        added = sorted(set(files) - known_prior)
        removed = sorted(known_prior - set(files))
        if not added and not removed:
            print(f"architecture current: {len(files)} source files, no additions or removals")
            return 0
        for f in added[:10]:
            print(f"  + {f}")
        for f in removed[:10]:
            print(f"  - {f}")
        print(f"rebuild needed: {len(added)} added, {len(removed)} removed")
        return 1
    known = set(files)
    print(f"Source files on disk: {len(files)}")

    unassigned = [f for f in files if assign_module(f) is None]
    if unassigned:
        print(f"ERROR: {len(unassigned)} file(s) match no MODULE_ROOTS entry:")
        for f in unassigned[:20]:
            print(f"  {f}")
        print("Add a MODULE_ROOTS entry -- refusing to silently drop files.")
        return 1

    print("Running pydeps over backend/ ...")
    try:
        be_imports, be_external = extract_backend_edges(known)
    except ExtractorError as exc:
        print(f"ERROR: {exc}")
        print("Aborting -- refusing to overwrite existing dependency data with nothing.")
        return 1
    print("Running dependency-cruiser over frontend/src ...")
    try:
        fe_imports, fe_external = extract_frontend_edges(known)
    except ExtractorError as exc:
        print(f"ERROR: {exc}")
        print("Aborting -- refusing to overwrite existing dependency data with nothing.")
        return 1

    file_imports: dict[str, set] = defaultdict(set)
    file_external: dict[str, set] = defaultdict(set)
    for d, s in ((be_imports, file_imports), (fe_imports, file_imports),
                 (be_external, file_external), (fe_external, file_external)):
        for k, v in d.items():
            s[k] |= v

    with_edges = sum(1 for f in files if file_imports.get(f))
    print(f"Files with resolved import edges: {with_edges}/{len(files)} "
          f"({len(files) - with_edges} isolated -- recorded with no edges, not dropped)")

    # Sanity guard against SILENT under-reporting. pydeps returns absolute
    # paths; if the source tree is reached through a symlink, Path.resolve()
    # lands outside REPO_ROOT, relative_to() raises, and every one of those
    # files is skipped -- producing a plausible-looking graph with almost no
    # backend edges and no error at all. Loud is better than wrong.
    for label, exts in (("backend", (".py",)), ("frontend", (".ts", ".tsx", ".js", ".jsx"))):
        pool = [f for f in files if f.endswith(exts)]
        linked = [f for f in pool if file_imports.get(f)]
        if len(pool) >= 20 and len(linked) < len(pool) * 0.10:
            print(f"  WARNING: only {len(linked)}/{len(pool)} {label} files resolved any "
                  f"import edge. Expected far more -- the extractor likely failed to map "
                  f"paths (a symlinked source tree does this). Treat the graph as suspect.")

    # ---- aggregate file edges to module edges ----
    # assign_module() is total here -- the `unassigned` guard above already
    # aborted if any file failed to match a root.
    file_to_module: dict[str, str] = {}
    for f in files:
        mod_root = assign_module(f)
        assert mod_root is not None
        file_to_module[f] = mod_root
    card_index = _card_index()
    module_files: dict[str, list[str]] = defaultdict(list)
    for f in files:
        module_files[file_to_module[f]].append(f)

    module_imports: dict[str, set] = defaultdict(set)
    module_external: dict[str, set] = defaultdict(set)
    for f in files:
        mod = file_to_module[f]
        for target in file_imports.get(f, ()):
            tmod = file_to_module.get(target)
            if tmod and tmod != mod:
                module_imports[mod].add(tmod)
        module_external[mod] |= file_external.get(f, set())

    module_imported_by: dict[str, set] = defaultdict(set)
    for mod, deps in module_imports.items():
        for dep in deps:
            module_imported_by[dep].add(mod)


    today = date.today().isoformat()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    module_summaries = []
    written = 0
    at_risk: list[str] = []   # files skipped to avoid destroying their content

    for root in sorted(MODULE_ROOTS):
        mfiles = sorted(module_files.get(root, []))
        all_module_ids = {module_slug(r) for r in module_files}
        if not mfiles:
            continue
        mid = module_slug(root)
        langs = {language_for(f) for f in mfiles}
        language = next(iter(langs)) if len(langs) == 1 else "mixed"
        imports = sorted(module_slug(m) for m in module_imports.get(root, set()))
        imported_by = sorted(module_slug(m) for m in module_imported_by.get(root, set()))
        external = sorted(module_external.get(root, set()))

        out_path = OUT_DIR / f"{mid}.md"
        prior_prose_sig = read_signatures(out_path).get("prose_signature")
        try:
            hand_authored = read_hand_authored(out_path)
        except PreserveError as exc:
            at_risk.append(str(exc))
            continue  # leave the file exactly as it is

        hand_authored = linkify_prose(
            hand_authored, mfiles, known, all_module_ids, card_index
        )

        frontmatter_data = {
            "id": mid,
            "type": "architecture",
            "kind": "state",
            "title": f"{root} — module",
            "path": root,
            "language": language,
            "file_count": len(mfiles),
            # files / imports / imported_by deliberately absent: they are
            # rendered as clickable lists in the generated block below, and
            # kept machine-readable in modules.json. Carrying them here too
            # meant a third copy that no tool read and no reader could click.
            "code_signature": module_signature(mfiles, imports, imported_by, external),
            # Carried forward verbatim. Only the step that REWRITES the prose
            # may advance it -- restamping it here would erase the staleness
            # the field exists to record.
            **({"prose_signature": prior_prose_sig} if prior_prose_sig else {}),
            "last_synced": today,
        }
        frontmatter = "---\n" + yaml.safe_dump(
            frontmatter_data, default_flow_style=False, sort_keys=False, allow_unicode=True
        ) + "---\n\n"

        auto_lines = [
            "<!-- AUTO-GENERATED BELOW THIS LINE — regenerated by tools/knowledge/build_architecture.py -->",
            "",
            f"### Files ({len(mfiles)})",
        ]
        auto_lines += [f"- [{f}](../../{quote(f)})" for f in mfiles]
        auto_lines += ["", "### Depends on"]
        auto_lines += [f"- [{m}]({m}.md)" for m in imports] if imports else ["- (none)"]
        auto_lines += ["", "### Depended on by"]
        auto_lines += [f"- [{m}]({m}.md)" for m in imported_by] if imported_by else ["- (none)"]
        auto_lines += ["", "### External"]
        auto_lines += [", ".join(external) if external else "(none)"]
        auto_lines.append(AUTO_END)
        auto_lines.append("")

        content = frontmatter + "\n".join(auto_lines) + "\n" + hand_authored.strip("\n") + "\n"
        if not args.check and (only is None or mid in only):
            if write_if_changed(out_path, content):
                written += 1

        module_summaries.append({
            "id": mid,
            "path": root,
            "language": language,
            "file_count": len(mfiles),
            "files": mfiles,
            "imports": imports,
            "imported_by": imported_by,
            "external_deps": external,
        })

    if not args.check:
        write_file_cards(files, file_imports, file_external, file_to_module,
                         check=args.check)

        # Domains resolve their members against the same file list, so they
        # must run after it is settled -- and before the gallery, which lifts
        # each domain's diagram into ARCHITECTURE.md.
        _, uncovered = write_domain_cards(files, file_imports, file_external,
                                          file_to_module, today,
                                          check=args.check)
        if uncovered:
            print(f"  {len(uncovered)} file(s) belong to no domain -- first 10:")
            for f in uncovered[:10]:
                print(f"    {f}")
        write_gallery(check=args.check)
        write_module_map(module_summaries, check=args.check)

        write_if_changed(OUT_DIR / "modules.json",
            json.dumps({"generated_at": today, "modules": module_summaries},
                       indent=2) + "\n"
        )

    total_assigned = sum(m["file_count"] for m in module_summaries)
    print(f"\nModules produced: {len(module_summaries)}")
    print(f"Files assigned:   {total_assigned}/{len(files)}")
    if total_assigned != len(files):
        print("ERROR: file assignment lost files.")
        return 1
    preserved = 0
    for m in module_summaries:
        try:
            # Compare stripped on BOTH sides. The constant carries a trailing
            # newline but read_hand_authored() strips one off anything it reads
            # back, so a raw `!=` reports every placeholder module as
            # "preserved" -- turning the one line that is supposed to prove
            # prose survived into a number that is always reassuring and
            # therefore worthless.
            if read_hand_authored(OUT_DIR / f"{m['id']}.md").strip() != DEFAULT_HAND_AUTHORED.strip():
                preserved += 1
        except PreserveError:
            pass
    print(f"Modules with hand-authored prose preserved: {preserved}")

    # Never delete. A MOD-*.md with no live module behind it (a root removed
    # from MODULE_ROOTS, a package deleted from the repo) still holds
    # hand-authored prose, so it is reported and left alone -- removing it is
    # a human decision.
    produced = {m["id"] for m in module_summaries}
    orphans = sorted(
        p.name for p in OUT_DIR.glob("MOD-*.md") if p.stem not in produced
    )
    if orphans:
        print(f"\nOrphaned MOD-*.md ({len(orphans)}) -- left untouched, not deleted:")
        for name in orphans:
            print(f"  {name}")

    if at_risk:
        print(f"\nSKIPPED to avoid destroying content ({len(at_risk)}):")
        for msg in at_risk:
            print(f"  {msg}")
        print("Fix the frontmatter by hand, then re-run. Nothing was overwritten.")

    print("--check: nothing written." if args.check else f"MOD-*.md written: {written}")
    return 1 if at_risk else 0


if __name__ == "__main__":
    raise SystemExit(main())
