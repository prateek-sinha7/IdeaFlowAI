"""SSE-only hard-cutoff banned-pattern ratchet — W5 / INV-12 (Phase 44).

This is a CI *ratchet*, not a behavior test. It machine-enforces the definition
of "the WebSocket→SSE hard cutoff is DONE": once Phase 44 deleted the ``/ws/chat``
WebSocket transport, the ``useWebSocket`` hook, and the ``SSE_TRANSPORT`` feature
flag, NOTHING may silently reintroduce them.

It scans the FIRST-PARTY SOURCE trees and FAILS CI if any of the five deleted
transport/flag tokens reappear:

    /ws/chat                     — the retired chat WebSocket route (44-07)
    useWebSocket                 — the deleted FE transport hook (44-04)
    routeWebSocket               — the Playwright WS-mock entry (44-09, mockWs.ts gone)
    NEXT_PUBLIC_SSE_TRANSPORT    — the retired FE transport flag (44-06)
    SSE_TRANSPORT_ENABLED        — the retired BE transport flag (44-07)

Scan roots (mirrors R15's ``test_banned_patterns.py`` _SCAN_ROOTS style):
  * backend/app     (Python)  — endpoints, config, run_* command/stream modules
  * backend/agents  (Python)  — the kernel + capabilities
  * frontend/src    (TS/TSX)  — the app source

``frontend/e2e`` is DELIBERATELY NOT scanned: after 44-09 the mocked harness keeps a
back-compat ``mockSse.waitForClientFrame`` alias (now asserting REST commands) and
retains historical ``useWebSocket`` mentions inside JSDoc comments — neither is a
regression, so scoping to ``frontend/src`` keeps the gate honest. (The orchestrator
guardrail + CONTEXT §2 W5 pin this scope; the plan's task text listed ``e2e`` but the
authoritative scope is source-only — see 44-10 SUMMARY "Deviations".)

Sanctioned D10 survivors that must NOT trip the gate (decision 3 / CONTEXT §0.3):
  * /ws/handoff                          — the external-IDE handoff WS route (SURVIVES)
  * frontend/src/hooks/useHandoffSocket.ts — the FE handoff hook (SURVIVES)
  * backend/app/api/websocket_handoff.py   — the BE handoff module (SURVIVES)
  * app/api/run_engine.py                  — the transport-neutral relocated infra
  * mockSse.waitForClientFrame             — the e2e back-compat REST alias (not scanned)

The bans are EXACT/word-boundary matched so the survivors pass structurally, not by
luck: ``/ws/chat\b`` never matches ``/ws/handoff``; ``\buseWebSocket\b`` never
matches ``useHandoffSocket`` (T-44-10-02 elevation-of-privilege mitigation). Comment
and docstring mentions of a banned token are IGNORED — the Python scanner strips
``#`` comments + AST-detected docstrings, and the TS scanner strips ``//`` (URL-safe)
+ ``/* */`` comments — so the many legitimate "``/ws/chat`` was retired" prose
mentions in ``config.py``/``main.py``/``run_stream.py`` docstrings do not false-red.

Non-vacuity (T-44-10-01 mitigation): because the bans currently match nothing on the
cutover-complete tree, a dead/never-matching scanner would pass silently and give
false confidence. ``test_gate_is_non_vacuous_*`` inject known-bad tokens into temp
dirs and assert the SAME scanners fire — proving the ratchet catches a real
regression.

Offline / unmarked — runs in CI (no ``requires_api_key``).
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

import pytest

# tests/agents/test_sse_cutover_banned_patterns.py
#   parents[2] -> backend/ ; parents[3] -> repo root (holds frontend/).
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]

# First-party SOURCE roots. Backend = Python; frontend = TS/TSX. e2e is excluded on
# purpose (retains the waitForClientFrame alias + historical useWebSocket comments).
_PY_ROOTS = (_BACKEND_ROOT / "app", _BACKEND_ROOT / "agents")
_TS_ROOT = _REPO_ROOT / "frontend" / "src"

_PY_SUFFIXES = (".py",)
_TS_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mts", ".cts")

# ---------------------------------------------------------------------------
# THE FIVE BANNED TOKENS — one anchored scanner each. Any code-line match (in any
# root) fails CI. Anchors are EXACT so the sanctioned survivors pass structurally:
#   * ``/ws/chat\b`` — the trailing \b matches ``/ws/chat"`` / ``/ws/chat/`` / EOL but
#     NEVER ``/ws/handoff`` (the survivor route).
#   * ``\buseWebSocket\b`` — never substring-hits ``useHandoffSocket`` (the survivor).
# ---------------------------------------------------------------------------
_BANNED: dict[str, re.Pattern[str]] = {
    "/ws/chat": re.compile(r"/ws/chat\b"),
    "useWebSocket": re.compile(r"\buseWebSocket\b"),
    "routeWebSocket": re.compile(r"\brouteWebSocket\b"),
    "NEXT_PUBLIC_SSE_TRANSPORT": re.compile(r"\bNEXT_PUBLIC_SSE_TRANSPORT\b"),
    "SSE_TRANSPORT_ENABLED": re.compile(r"\bSSE_TRANSPORT_ENABLED\b"),
}

# The sanctioned D10 survivor tokens — asserted (positively) to be immune to the
# bans above so an over-broad pattern can never silently break the handoff surface.
_SURVIVOR_TOKENS = ("/ws/handoff", "useHandoffSocket", "websocket_handoff")


# ---------------------------------------------------------------------------
# Code extraction — return only executable code lines (comments + docstrings
# stripped) so prose mentions of a banned token never trip the gate.
# ---------------------------------------------------------------------------
def _strip_py_comments(src: str) -> str:
    """Blank out ``#`` comments (inline + whole-line) via ``tokenize`` — which never
    mistakes a ``#`` inside a string literal for a comment. Line structure is
    preserved so AST line numbers stay valid."""
    lines = src.splitlines()
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return src
    for tok in toks:
        if tok.type != tokenize.COMMENT:
            continue
        (srow, scol), (_erow, ecol) = tok.start, tok.end  # comments are single-line
        line = lines[srow - 1]
        lines[srow - 1] = line[:scol] + line[ecol:]
    return "\n".join(lines)


def _python_code_lines(src: str) -> list[tuple[int, str]]:
    """(lineno, text) for Python code lines with ``#`` comments (inline + whole-line)
    stripped and AST-detected module/class/function docstrings removed. A banned
    token surviving this filter is a genuine code reference."""
    docstring_lines: set[int] = set()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        tree = None
    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(
                node,
                (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
            ):
                body = getattr(node, "body", None) or []
                if not body:
                    continue
                first = body[0]
                if (
                    isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)
                ):
                    ds = first.value
                    end = ds.end_lineno or ds.lineno
                    docstring_lines.update(range(ds.lineno, end + 1))
    stripped = _strip_py_comments(src)
    out: list[tuple[int, str]] = []
    for lineno, line in enumerate(stripped.splitlines(), 1):
        if lineno in docstring_lines:
            continue
        out.append((lineno, line))
    return out


# ``/* ... */`` (incl. JSDoc ``/** */``) block comments — spans lines.
_TS_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
# ``//`` line comments, but NOT the ``//`` in a URL scheme (``http://`` / ``ws://``)
# so a real ``ws://host/ws/chat`` regression is never truncated away before matching.
_TS_LINE_COMMENT = re.compile(r"(?<!:)//.*$", re.MULTILINE)


def _ts_code_lines(src: str) -> list[tuple[int, str]]:
    """(lineno, text) for TS/TSX code lines with ``/* */`` and (URL-safe) ``//``
    comments blanked out. Block comments are replaced with same-count newlines so
    line numbers stay accurate."""

    def _blank_block(m: re.Match[str]) -> str:
        return "\n" * m.group(0).count("\n")

    no_block = _TS_BLOCK_COMMENT.sub(_blank_block, src)
    no_line = _TS_LINE_COMMENT.sub("", no_block)
    return list(enumerate(no_line.splitlines(), 1))


def _iter_source_files(root: Path, suffixes: tuple[str, ...]):
    if not root.exists():
        return
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in suffixes:
            continue
        parts = set(path.parts)
        if "__pycache__" in parts or "node_modules" in parts:
            continue
        yield path


def _rel(path: Path) -> str:
    for base in (_REPO_ROOT, _BACKEND_ROOT):
        try:
            return path.relative_to(base).as_posix()
        except ValueError:
            continue
    return path.as_posix()


def _scan_lines(
    relpath: str, code_lines: list[tuple[int, str]]
) -> list[tuple[str, str, int, str]]:
    """Return (token, relpath, lineno, line) for every banned-token match."""
    hits: list[tuple[str, str, int, str]] = []
    for token, pattern in _BANNED.items():
        for lineno, line in code_lines:
            if pattern.search(line):
                hits.append((token, relpath, lineno, line.strip()))
    return hits


def _collect_hits() -> list[tuple[str, str, int, str]]:
    """Scan all first-party source roots and return every banned-token hit."""
    hits: list[tuple[str, str, int, str]] = []
    for root in _PY_ROOTS:
        for path in _iter_source_files(root, _PY_SUFFIXES):
            code = _python_code_lines(path.read_text(encoding="utf-8"))
            hits.extend(_scan_lines(_rel(path), code))
    for path in _iter_source_files(_TS_ROOT, _TS_SUFFIXES):
        code = _ts_code_lines(path.read_text(encoding="utf-8"))
        hits.extend(_scan_lines(_rel(path), code))
    return hits


# ===========================================================================
# HARD BAN — the cutover-complete tree must have ZERO banned-token code refs.
# ===========================================================================


def test_scan_roots_exist() -> None:
    """Sanity: the scanned roots resolve on this repo (guards a moved test file
    that would make every ban vacuously pass)."""
    assert (_BACKEND_ROOT / "app").is_dir()
    assert (_BACKEND_ROOT / "agents").is_dir()
    assert _TS_ROOT.is_dir(), (
        f"frontend/src not found at {_TS_ROOT} — the FE half of the gate would be "
        "vacuous; verify the repo-root resolution (parents[3])."
    )


@pytest.mark.parametrize("token", sorted(_BANNED))
def test_no_banned_transport_token(token: str) -> None:
    """No first-party CODE reference to a deleted WS/flag token (INV-12 hard cutoff).

    One assertion per banned token so a failure names exactly which retired symbol
    reappeared and where. Comment/docstring mentions are stripped before matching."""
    offenders = [h for h in _collect_hits() if h[0] == token]
    assert not offenders, (
        f"SSE hard-cutoff (INV-12): the retired transport/flag token `{token}` "
        "reappeared in first-party source — the WebSocket→SSE cutover must stay "
        "complete. Offenders:\n"
        + "\n".join(f"  {p}:{n}: {ln}" for _, p, n, ln in offenders)
    )


def test_gate_passes_on_current_tree() -> None:
    """Aggregate: ZERO banned-token hits across ALL roots on the cutover-complete
    tree (44-06/44-07/44-09 deleted every token)."""
    hits = _collect_hits()
    assert not hits, (
        "SSE hard-cutoff (INV-12) regression — banned transport/flag tokens found:\n"
        + "\n".join(f"  [{t}] {p}:{n}: {ln}" for t, p, n, ln in hits)
    )


def test_sanctioned_survivors_are_immune() -> None:
    """The D10 survivor tokens (/ws/handoff, useHandoffSocket, websocket_handoff)
    are structurally immune to the bans (T-44-10-02): scanning a line containing each
    survivor token yields ZERO banned hits. Proves the exact/word-boundary anchors —
    not luck — keep the handoff surface alive."""
    survivor_line = (
        'const s = openHandoff("/ws/handoff/" + t); useHandoffSocket(); '
        "# websocket_handoff.py survives"
    )
    hits = _scan_lines("virtual/survivor_check.ts", [(1, survivor_line)])
    assert not hits, (
        "OVER-BROAD BAN: a sanctioned D10 survivor token tripped the gate — the "
        f"handoff surface must survive the cutover. False hits:\n{hits}"
    )


# ===========================================================================
# FALSE-POSITIVE GUARD — comment/docstring mentions must NOT trip the gate.
# ===========================================================================


def test_gate_ignores_comment_and_docstring_mentions(tmp_path: Path) -> None:
    """The opposite failure mode: banned tokens inside comments/docstrings must NOT
    trip the gate — this is exactly why the live tree (full of "`/ws/chat` was
    retired" prose) stays green."""
    py = tmp_path / "prose_backend.py"
    py.write_text(
        '"""Module note: the /ws/chat route was retired; SSE_TRANSPORT_ENABLED gone."""\n'
        "\n"
        "def f():\n"
        '    """Docstring mentioning useWebSocket and /ws/chat historically."""\n'
        "    x = 1  # SSE_TRANSPORT_ENABLED removed in 44-07\n"
        "    return x\n",
        encoding="utf-8",
    )
    ts = tmp_path / "prose_frontend.ts"
    ts.write_text(
        "// historical: useWebSocket + routeWebSocket + NEXT_PUBLIC_SSE_TRANSPORT gone\n"
        "/* /ws/chat was the retired route; see 44-07 */\n"
        "export const ok = true;\n",
        encoding="utf-8",
    )
    py_hits = _scan_lines("prose_backend.py", _python_code_lines(py.read_text("utf-8")))
    ts_hits = _scan_lines("prose_frontend.ts", _ts_code_lines(ts.read_text("utf-8")))
    # Module/function docstrings AND the inline ``# SSE_TRANSPORT_ENABLED removed``
    # comment-on-a-code-line are all stripped (AST docstrings + tokenize comments), so
    # a prose-only file yields ZERO hits — exactly why the live tree stays green.
    assert not py_hits, f"FALSE POSITIVE: Python comment/docstring mentions tripped the gate: {py_hits}"
    assert not ts_hits, f"FALSE POSITIVE: TS comment mentions tripped the gate: {ts_hits}"


# ===========================================================================
# NON-VACUITY GUARD (T-44-10-01) — prove the scanners actually fire.
# ===========================================================================


def test_gate_is_non_vacuous_python(tmp_path: Path) -> None:
    """Inject banned tokens into a temp .py CODE line and assert the Python scanner
    flags them. Because the live tree is clean, this proves the ban is not a dead
    regex that would let a real regression through."""
    bad = tmp_path / "rogue_backend.py"
    bad.write_text(
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        '@router.websocket("/ws/chat")\n'
        "async def chat():\n"
        "    if settings.SSE_TRANSPORT_ENABLED:\n"
        "        return 1\n",
        encoding="utf-8",
    )
    code = _python_code_lines(bad.read_text(encoding="utf-8"))
    hits = {t for t, *_ in _scan_lines("rogue_backend.py", code)}
    assert "/ws/chat" in hits, (
        "NON-VACUITY FAILURE: the `/ws/chat` scanner did not flag an injected "
        "@router.websocket route — the ratchet would miss a real regression."
    )
    assert "SSE_TRANSPORT_ENABLED" in hits, (
        "NON-VACUITY FAILURE: the `SSE_TRANSPORT_ENABLED` scanner did not fire on "
        "an injected flag reference."
    )


def test_gate_is_non_vacuous_typescript(tmp_path: Path) -> None:
    """Inject the FE tokens into a temp .ts CODE line and assert the TS scanner
    flags them (useWebSocket / routeWebSocket / NEXT_PUBLIC_SSE_TRANSPORT / /ws/chat)."""
    bad = tmp_path / "rogue_frontend.ts"
    bad.write_text(
        "export function boot() {\n"
        "  const c = useWebSocket();\n"
        "  page.routeWebSocket(rx, h);\n"
        '  const url = base + "/ws/chat";\n'
        "  const f = process.env.NEXT_PUBLIC_SSE_TRANSPORT;\n"
        "  return c && f && url;\n"
        "}\n",
        encoding="utf-8",
    )
    code = _ts_code_lines(bad.read_text(encoding="utf-8"))
    hits = {t for t, *_ in _scan_lines("rogue_frontend.ts", code)}
    for token in ("useWebSocket", "routeWebSocket", "NEXT_PUBLIC_SSE_TRANSPORT", "/ws/chat"):
        assert token in hits, (
            f"NON-VACUITY FAILURE: the `{token}` scanner did not flag an injected "
            "frontend regression."
        )
