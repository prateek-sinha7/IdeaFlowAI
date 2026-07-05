"""app/agents/route_table.py — shared, pure route-table resolver for the validators.

The single source of route semantics for BOTH prototype validators
(:mod:`app.agents.static_check` and :mod:`app.agents.render_check`). It parses the
app's JS route declaration into an ordered ``(pattern, page)`` table and resolves a
nav path through it exactly as the app's ``matchRoute`` would — so a validator judges
a route by the page it ACTUALLY resolves to (alias / ``:id`` parametric included),
not by a naive first-path-segment heuristic.

Two declaration forms are recognised (mirroring the SPA prototype family):

  * **Array form** (B's fixed router)::

        const routes = [
          { pattern: 'inventory/create', page: 'inventory-create' },  // alias
          { pattern: 'inventory/:id',    page: 'inventory-detail' },  // parametric
        ];

  * **Object form** with **page-id values** (A's router)::

        const routes = { 'dashboard': 'dashboard', 'inventory-list': 'inventory-list' };

An **href-valued** object map — the template convention ``const routes = { id: '#/route' }``
(values start with ``#`` or ``/``, or are empty) — is deliberately NOT treated as a
resolvable table: :func:`parse_routes_table` returns ``None`` so the caller falls back
to its legacy first-path-segment path (INV-3 byte/event-identical for the goldens, the
trimmed fixture, and every href-valued template).

Pure + stdlib-only (``re``). This module imports NOTHING from ``static_check`` or
``render_check`` — the dependency is strictly one-way (validators → route_table).
Parsing never raises: malformed / unbalanced / declaration-less input returns ``None``.
"""

from __future__ import annotations

import re

# A JS identifier we accept as a bare key/value (unquoted page id / route key).
_IDENT = r"[A-Za-z_$][\w$-]*"

# The `const|let|var routes =` anchor (mirrors static_check._extract_routes_map).
_ROUTES_DECL_RE = re.compile(r"\b(?:const|let|var)\s+routes\s*=\s*")


def _strip_comments(text: str) -> str:
    """Remove ``//`` line comments and ``/* ... */`` block comments from JS text."""
    text = re.sub(r"//[^\n]*", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return text


def _match_balanced(text: str, start: int, open_ch: str, close_ch: str) -> int | None:
    """Return the index of the ``close_ch`` matching the ``open_ch`` at ``start``.

    Single-pass depth counter (bounded — never loops); returns ``None`` if the
    delimiters are unbalanced (adversarial/oversized input degrades to ``None``).
    """
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i
    return None


# Object-literal entry:  key: value  where each side is 'str' | "str" | bareIdent.
_OBJ_ENTRY_RE = re.compile(
    rf"""(?:^|,)\s*
        (?:'(?P<ksq>[^']*)'|"(?P<kdq>[^"]*)"|(?P<kbare>{_IDENT}))
        \s*:\s*
        (?:'(?P<vsq>[^']*)'|"(?P<vdq>[^"]*)"|(?P<vbare>{_IDENT}))
    """,
    re.VERBOSE,
)

# Array object:  { pattern: '...', page: '...' }  (either key order, keys may repeat
# other unrelated keys we ignore). We extract the pattern + page string values.
_PATTERN_VAL_RE = re.compile(r"""pattern\s*:\s*(['"])(?P<val>.*?)\1""")
_PAGE_VAL_RE = re.compile(r"""page\s*:\s*(['"])(?P<val>.*?)\1""")


def _parse_array(body: str) -> list[tuple[str, str]] | None:
    """Parse the body of an array-of-objects ``[ {pattern, page}, ... ]``."""
    table: list[tuple[str, str]] = []
    idx = 0
    while True:
        open_brace = body.find("{", idx)
        if open_brace == -1:
            break
        close_brace = _match_balanced(body, open_brace, "{", "}")
        if close_brace is None:
            return None  # unbalanced object → not a resolvable table
        obj = body[open_brace : close_brace + 1]
        pm = _PATTERN_VAL_RE.search(obj)
        gm = _PAGE_VAL_RE.search(obj)
        if pm and gm:
            table.append((pm.group("val").strip(), gm.group("val").strip()))
        idx = close_brace + 1
    return table or None


def _parse_object(body: str) -> list[tuple[str, str]] | None:
    """Parse the body of an object literal ``{ key: value, ... }``.

    Returns ``None`` (NOT a resolvable table) if ANY value is empty or looks like an
    href (starts with ``#`` or ``/``) — the template ``{id: '#/route'}`` convention.
    """
    table: list[tuple[str, str]] = []
    for m in _OBJ_ENTRY_RE.finditer(body):
        key = m.group("ksq")
        if key is None:
            key = m.group("kdq")
        if key is None:
            key = m.group("kbare")
        value = m.group("vsq")
        if value is None:
            value = m.group("vdq")
        if value is None:
            value = m.group("vbare")
        key = (key or "").strip()
        value = (value or "").strip()
        if not key:
            continue
        # DISAMBIGUATION: an href/empty value → NOT a page-id table → bail to None so
        # the caller keeps its legacy first-segment path (INV-3).
        if not value or value.startswith("#") or value.startswith("/"):
            return None
        table.append((key, value))
    return table or None


def parse_routes_table(script_text: str) -> list[tuple[str, str]] | None:
    """Parse a JS ``routes`` declaration into an ordered ``(pattern, page)`` table.

    Handles the array-of-objects form (B) and the page-id-valued object form (A).
    Returns ``None`` for an href-valued object map, a table-less script, unbalanced
    input, or zero extracted entries — the caller then uses its legacy path.
    """
    if not script_text:
        return None
    m = _ROUTES_DECL_RE.search(script_text)
    if not m:
        return None

    # First non-space char after '=' decides the form.
    rest = script_text[m.end() :]
    stripped = rest.lstrip()
    if not stripped:
        return None
    lead = stripped[0]
    # Offset of that lead char within the original script_text.
    lead_off = m.end() + (len(rest) - len(stripped))

    if lead == "[":
        close = _match_balanced(script_text, lead_off, "[", "]")
        if close is None:
            return None
        body = _strip_comments(script_text[lead_off + 1 : close])
        return _parse_array(body)
    if lead == "{":
        close = _match_balanced(script_text, lead_off, "{", "}")
        if close is None:
            return None
        body = _strip_comments(script_text[lead_off + 1 : close])
        return _parse_object(body)
    return None


def _clean_path(path: str) -> str:
    """Normalise a nav path to matchRoute's ``cleanPath``.

    Strips a single leading ``#``, drops a ``?query`` suffix, then strips a leading
    and a trailing ``/`` (mirrors parseHash + matchRoute).
    """
    p = (path or "").strip()
    if p.startswith("#"):
        p = p[1:]
    p = p.split("?", 1)[0]
    if p.startswith("/"):
        p = p[1:]
    if p.endswith("/"):
        p = p[:-1]
    return p


def resolve_route(table: list[tuple[str, str]], path: str) -> str | None:
    """Resolve ``path`` through ``table`` exactly as the app's ``matchRoute`` would.

    First-match-wins over the authored order: a ``:id`` pattern matches
    ``^{base}/([^/]+)$`` (``base`` regex-escaped — injection/backtracking guard); any
    other pattern matches by exact equality. Returns the target page id, or ``None``
    when nothing matches (the route would hit the app's fallback — unreachable via the
    table).
    """
    if not table:
        return None
    clean = _clean_path(path)
    for pattern, page in table:
        if ":id" in pattern:
            base = pattern.replace("/:id", "")
            if re.fullmatch(re.escape(base) + r"/([^/]+)", clean):
                return page
        elif clean == pattern:
            return page
    return None
