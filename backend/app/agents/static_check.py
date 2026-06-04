"""app/agents/static_check.py — no-browser structural validation for HTML prototypes.

The cheap pre-filter sibling of :mod:`app.agents.render_check`. Where ``render_check``
launches headless Chromium to prove a prototype *runs*, ``static_check`` parses the
HTML with the **standard library only** (``re`` + ``html.parser``) and catches the
structural defects that motivated per-task validation — without paying the Chromium
cost. It is fast, dependency-light, and safe to run after *every* build task.

It inspects the SPA prototype family produced by the prototype pipeline (see
``agents/prompts/prototype-plan/AGENT.md`` and the template seed): sidebar nav links
``<a class="nav-item" href="#/route">``, page sections ``<section data-page="id">``,
a JS routes map (``const routes = { id: '#/route', ... }``), ``class="is-active"`` on
the first page, and event handlers (``onclick`` / ``addEventListener``) in ``<script>``.

Checks (each emits a precise, named issue so the Phase-4 fix-loop can feed it back):
  * **routes ↔ sections** — every nav ``href`` (``#/x`` or ``#x``) resolves to a real
    ``<section data-page="x">`` (dead link = error); sections with no nav entry are
    reported as orphans (warning — non-fatal).
  * **routes map complete** — if a JS routes-map object is present, every page id
    appears as a key (missing = error); routes-map keys with no matching section are
    extra (error).
  * **handlers defined** — every ``onclick="fn(...)"`` / inline-handler-referenced
    name resolves to a ``function fn`` / ``const fn =`` / ``fn = function`` /
    ``fn = (...) =>`` definition (or an ``addEventListener``) in a ``<script>``;
    undefined handlers are errors.
  * **basic sanity** — at least one ``is-active`` section.

Intentionally NOT flagged (false-positive guards — these are valid patterns):
  * External links (``http://``, ``https://``, ``//cdn``, ``mailto:``, ``tel:``).
  * A bare ``#`` anchor, ``#`` + empty, or non-route fragments without ``data-page``
    that look like in-page anchors rather than SPA routes (we only treat ``#/...`` and
    ``#word`` hrefs as route candidates; see ``_iter_route_hrefs``).
  * ``javascript:`` URLs and inline-JS handler bodies that are not bare function calls
    (e.g. ``onclick="store.set({x:1})"``, ``onclick="this.classList.toggle('x')"``) —
    method calls, property access, assignments, and language keywords are skipped; only
    a top-level ``name(...)`` call resolves to a required handler definition.
  * Empty ``<section data-page>`` blocks — content grows per task, so emptiness is
    expected mid-build and is never a failure.
  * Routes-map *values* (path patterns, possibly with ``:params``) — only keys (page
    ids) are matched against sections.

Like ``render_check``, this is graceful: parsing never raises; a parse failure degrades
to a single issue rather than crashing the caller.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

logger = logging.getLogger("app.agents.static_check")

# A name we'd accept as a JS identifier (handler / route id / function name).
_IDENT = r"[A-Za-z_$][\w$]*"

# JS reserved words / built-in globals that an ``onclick`` body may *call* but that we
# must never demand a user-defined function for (else we'd false-positive on valid HTML).
_JS_BUILTINS: frozenset[str] = frozenset(
    {
        "alert",
        "confirm",
        "prompt",
        "console",
        "window",
        "document",
        "location",
        "history",
        "navigator",
        "event",
        "parseInt",
        "parseFloat",
        "Number",
        "String",
        "Boolean",
        "Array",
        "Object",
        "JSON",
        "Math",
        "Date",
        "setTimeout",
        "setInterval",
        "clearTimeout",
        "clearInterval",
        "fetch",
        "encodeURIComponent",
        "decodeURIComponent",
        "requestAnimationFrame",
        # control-flow keywords that can lead an expression statement
        "return",
        "if",
        "for",
        "while",
        "switch",
        "void",
        "new",
        "typeof",
        "delete",
        "this",
        "true",
        "false",
        "null",
        "undefined",
    }
)

# Inline event-handler attributes we inspect (subset — the common ones in the template).
_HANDLER_ATTRS: frozenset[str] = frozenset(
    {
        "onclick",
        "onchange",
        "oninput",
        "onsubmit",
        "onkeydown",
        "onkeyup",
        "onkeypress",
        "onmouseover",
        "onmouseout",
        "onmousedown",
        "onmouseup",
        "onfocus",
        "onblur",
        "ondblclick",
        "onload",
    }
)


@dataclass
class StaticCheckResult:
    """Structured result of :func:`static_check`.

    Mirrors :class:`app.agents.render_check.RenderResult`: an ``ok`` flag, lists of
    issues, and a one-line :meth:`summary`. ``ok`` is ``True`` iff there are no
    (fatal) ``issues``. ``warnings`` are advisory (e.g. orphan sections) and do NOT
    affect ``ok`` — the Phase-4 fix-loop should feed back ``issues`` only.
    """

    ok: bool
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Parsed inventory (handy for callers/tests; not part of the pass/fail contract).
    sections: list[str] = field(default_factory=list)
    nav_hrefs: list[str] = field(default_factory=list)
    route_ids: list[str] = field(default_factory=list)
    note: str = ""

    def summary(self) -> str:
        bits: list[str] = []
        if self.issues:
            bits.append(f"{len(self.issues)} issue(s)")
        if self.warnings:
            bits.append(f"{len(self.warnings)} warning(s)")
        if not bits:
            return "OK" if not self.note else f"OK ({self.note})"
        return "; ".join(bits)


# --------------------------------------------------------------------------- #
# HTML parsing (stdlib html.parser) — collect sections, nav hrefs, handlers.
# --------------------------------------------------------------------------- #


class _PrototypeParser(HTMLParser):
    """Collect the structural facts the validator needs from a single pass.

    Using ``html.parser`` (stdlib) for tag/attribute extraction is more robust than
    pure regex for nav links and ``data-page`` ids; the JS-level facts (routes map,
    handler definitions) are still recovered with ``re`` over ``<script>`` text, since
    they live inside script bodies that the HTML parser treats as opaque CDATA.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        # data-page id -> had an is-active class on the opening tag
        self.sections: dict[str, bool] = {}
        # every <a href> (raw value) that carries the nav-item class
        self.nav_hrefs: list[str] = []
        # every <a href> regardless of class (for a lenient fallback)
        self.all_anchor_hrefs: list[str] = []
        # (attr_name, value) for every inline handler attribute on any element
        self.inline_handlers: list[tuple[str, str]] = []
        # accumulated text of every <script> block
        self._in_script = False
        self.script_text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        amap = {k.lower(): (v or "") for k, v in attrs}

        if tag == "script":
            # Only treat as inline JS when there's no external src.
            if not amap.get("src"):
                self._in_script = True

        # data-page sections
        if "data-page" in amap:
            page_id = amap["data-page"].strip()
            if page_id:
                classes = amap.get("class", "").split()
                is_active = "is-active" in classes
                # If the same id appears twice, OR the active flag.
                self.sections[page_id] = self.sections.get(page_id, False) or is_active

        # anchors / nav links
        if tag == "a" and "href" in amap:
            href = amap["href"].strip()
            self.all_anchor_hrefs.append(href)
            classes = amap.get("class", "").split()
            if "nav-item" in classes:
                self.nav_hrefs.append(href)

        # inline event handlers on any element
        for attr_name, value in amap.items():
            if attr_name in _HANDLER_ATTRS and value.strip():
                self.inline_handlers.append((attr_name, value.strip()))

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in_script = False

    def handle_data(self, data: str) -> None:
        if self._in_script:
            self.script_text_parts.append(data)

    @property
    def script_text(self) -> str:
        return "\n".join(self.script_text_parts)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

# An href is a *route candidate* (subject to the routes↔sections check) when it is a
# fragment that looks like an SPA route: ``#/foo`` (with optional sub-segments/params)
# or ``#foo`` (a bare word fragment). We deliberately EXCLUDE: external/protocol URLs,
# a bare ``#`` (or ``#`` + empty), and ``javascript:`` — see the module docstring.
_EXTERNAL_RE = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//)", re.IGNORECASE)


def _is_route_href(href: str) -> bool:
    if not href:
        return False
    if _EXTERNAL_RE.match(href):  # http:, https:, mailto:, tel:, javascript:, //cdn …
        return False
    if not href.startswith("#"):
        return False
    frag = href[1:]
    if not frag or frag == "/":  # bare '#' or '#/' (home) — not a dead link
        return False
    return True


def _href_target_id(href: str) -> str:
    """Extract the *first path segment* of a route href as the candidate page id.

    ``#/projects`` -> ``projects`` · ``#/project/42`` -> ``project`` ·
    ``#settings`` -> ``settings``. The first segment is what the template's router
    matches against a ``data-page`` id (deeper segments are ``:params``).
    """
    frag = href[1:]
    frag = frag.lstrip("/")
    # split on '/' and '?'; take the first non-empty segment
    first = re.split(r"[/?]", frag, maxsplit=1)[0]
    return first.strip()


def _iter_route_hrefs(hrefs: list[str]) -> list[str]:
    return [h for h in hrefs if _is_route_href(h)]


def _extract_routes_map(script_text: str) -> tuple[dict[str, str] | None, list[str]]:
    """Return ``(routes_map, key_order)`` from a ``const routes = { ... }`` object.

    Returns ``(None, [])`` when no routes object is present (the check is then skipped).
    Parsing is best-effort/brace-matched over the object literal; only string-or-bare
    *keys* are extracted (values are opaque path patterns we don't validate).
    """
    m = re.search(
        r"\b(?:const|let|var)\s+routes\s*=\s*\{",
        script_text,
    )
    if not m:
        return None, []

    # Brace-match from the opening '{' to find the object literal body.
    start = m.end() - 1  # position of '{'
    depth = 0
    end = None
    for i in range(start, len(script_text)):
        c = script_text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end is None:
        # Unbalanced — treat as present-but-empty so we don't crash; no ids.
        return {}, []

    body = script_text[start + 1 : end]
    # Strip line + block comments so commented-out keys aren't counted.
    body = re.sub(r"//[^\n]*", "", body)
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.DOTALL)

    routes: dict[str, str] = {}
    order: list[str] = []
    # Match  key:  where key is 'str' | "str" | bareIdent, at the start of an entry.
    key_re = re.compile(
        rf"""(?:^|,)\s*
            (?:'(?P<sq>[^']*)'|"(?P<dq>[^"]*)"|(?P<bare>{_IDENT}))
            \s*:""",
        re.VERBOSE,
    )
    for km in key_re.finditer(body):
        key = km.group("sq") or km.group("dq") or km.group("bare") or ""
        key = key.strip()
        if key and key not in routes:
            routes[key] = ""
            order.append(key)
    return routes, order


def _extract_defined_names(script_text: str) -> set[str]:
    """Collect every name that is *defined* (callable) in the script text.

    Covers the forms the build prompt / template emit:
      * ``function foo(...)`` (incl. ``async function``)
      * ``const foo = ...`` / ``let foo = ...`` / ``var foo = ...`` (arrow, function
        expr, or any value — we treat the binding as a usable name)
      * bare assignment ``foo = function`` / ``foo = (...) =>``
      * ``window.foo = ...`` (handlers exposed on the global object)
    """
    names: set[str] = set()

    # function declarations
    for m in re.finditer(rf"\bfunction\s+({_IDENT})\s*\(", script_text):
        names.add(m.group(1))

    # const/let/var bindings (any RHS — a bound name is callable enough for our check)
    for m in re.finditer(rf"\b(?:const|let|var)\s+({_IDENT})\s*=", script_text):
        names.add(m.group(1))

    # bare assignment to a function/arrow:  foo = function | foo = (...) =>  | foo = x =>
    for m in re.finditer(
        rf"(?:^|[;{{}}\n])\s*({_IDENT})\s*=\s*(?:async\s+)?(?:function\b|\([^)]*\)\s*=>|{_IDENT}\s*=>)",
        script_text,
    ):
        names.add(m.group(1))

    # window.foo = ...  (and self.foo / globalThis.foo)
    for m in re.finditer(
        rf"\b(?:window|self|globalThis)\.({_IDENT})\s*=",
        script_text,
    ):
        names.add(m.group(1))

    return names


# A top-level function call leading an inline-handler body, e.g. ``doThing(`` or
# ``doThing (`` — but NOT a method/property access (``a.b(``), and NOT an assignment
# (``x = ...``). We anchor at the start of the (trimmed) handler value.
_CALL_RE = re.compile(rf"^\s*({_IDENT})\s*\(")


def _handler_required_name(handler_body: str) -> str | None:
    """Return the bare function name an inline handler *calls*, or ``None`` to skip.

    Conservative: returns a name only when the handler body is (begins with) a simple
    ``name(...)`` call where ``name`` is not a method access, not a known JS builtin/
    keyword, and the handler isn't an assignment/expression we can't attribute to a
    user function. This is the core false-positive guard for the handler check.
    """
    body = handler_body.strip()
    if not body:
        return None
    # Skip ``javascript:`` prefixes defensively (shouldn't appear in an attr, but safe).
    if body.lower().startswith("javascript:"):
        body = body[len("javascript:") :].strip()

    m = _CALL_RE.match(body)
    if not m:
        # Not a leading bare call (e.g. ``store.set(...)``, ``x = 1``, ``this.foo()``,
        # ``el.classList.toggle(...)`` ) — nothing we can attribute; skip.
        return None
    name = m.group(1)
    if name in _JS_BUILTINS:
        return None
    # Guard: ensure it isn't actually ``name.method(`` mis-anchored — the call regex
    # already requires ``name(`` directly, so a dot would not match. Also ensure the
    # char right after the name (before '(') isn't a '.' — defensive.
    after = body[m.end(1) :].lstrip()
    if after.startswith("."):
        return None
    return name


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def _load_html(html: str | Path) -> tuple[str, str]:
    """Resolve the input to ``(html_text, note)``.

    Accepts either an HTML **string** or a **path** (``str`` or :class:`Path`) to an
    HTML file. Detection rule: if the value is a :class:`Path`, OR a ``str`` that is a
    path to an existing file, it is read from disk; otherwise the ``str`` is treated as
    literal HTML. (A ``str`` that merely *looks* like HTML — contains ``<`` — is always
    treated as HTML, so inline markup never gets mistaken for a path.)
    """
    if isinstance(html, Path):
        return html.read_text(encoding="utf-8"), f"file: {html}"
    # str input
    if "<" not in html and "\n" not in html:
        # Looks like a bare path (no markup, single line) — try the filesystem.
        p = Path(html)
        try:
            if p.is_file():
                return p.read_text(encoding="utf-8"), f"file: {p}"
        except OSError:
            pass
    return html, "inline html"


def static_check(html: str | Path) -> StaticCheckResult:
    """Validate a single-file HTML prototype's structure without a browser.

    Parameters
    ----------
    html:
        Either a path to an HTML file (a :class:`pathlib.Path`, or a ``str`` path to an
        existing file) **or** a raw HTML string. See :func:`_load_html` for the exact
        detection rule.

    Returns
    -------
    StaticCheckResult
        ``ok = not issues``. Read ``result.issues`` (precise, named messages) to feed
        the Phase-4 fix-loop; ``result.warnings`` are advisory (orphan sections) and do
        not affect ``ok``. Parsing never raises — a malformed document degrades to a
        single issue.
    """
    try:
        html_text, note = _load_html(html)
    except OSError as exc:
        return StaticCheckResult(ok=False, issues=[f"could not read input: {exc}"])

    issues: list[str] = []
    warnings: list[str] = []

    parser = _PrototypeParser()
    try:
        parser.feed(html_text)
        parser.close()
    except Exception as exc:  # noqa: BLE001 — a parse blow-up is a (soft) defect, not a crash
        logger.warning("static_check: HTML parse error (%s)", exc)
        return StaticCheckResult(
            ok=False,
            issues=[f"HTML failed to parse: {exc}"],
            note=note,
        )

    sections = parser.sections  # id -> is_active
    section_ids = set(sections)
    script_text = parser.script_text

    # --- routes ↔ sections (nav hrefs resolve to real sections) -------------- #
    nav_hrefs = parser.nav_hrefs
    # Fallback: if no .nav-item links exist, consider all anchors as nav candidates
    # (some templates omit the class). This stays conservative because _is_route_href
    # filters to fragment routes only.
    candidate_hrefs = nav_hrefs if nav_hrefs else parser.all_anchor_hrefs
    route_hrefs = _iter_route_hrefs(candidate_hrefs)

    linked_ids: set[str] = set()
    for href in route_hrefs:
        target = _href_target_id(href)
        if not target:
            continue
        linked_ids.add(target)
        if target not in section_ids:
            issues.append(
                f"dead nav link: href '{href}' has no matching "
                f'<section data-page="{target}">'
            )

    # orphan sections — defined but no nav entry (advisory warning, not a failure)
    for sid in sorted(section_ids - linked_ids):
        warnings.append(
            f'orphan section: <section data-page="{sid}"> has no nav link (#/{sid})'
        )

    # --- routes map complete (if a routes object is present) ------------------ #
    routes_map, route_key_order = _extract_routes_map(script_text)
    route_ids = list(route_key_order)
    if routes_map is not None:
        route_keys = set(routes_map)
        # every section id should be a key
        for sid in sorted(section_ids - route_keys):
            issues.append(
                f"routes map missing page id '{sid}' "
                f'(section <section data-page="{sid}"> has no routes entry)'
            )
        # every routes key should map to a real section
        for key in sorted(route_keys - section_ids):
            issues.append(
                f"routes map has extra id '{key}' with no matching "
                f'<section data-page="{key}">'
            )

    # --- handlers defined ---------------------------------------------------- #
    defined = _extract_defined_names(script_text)
    seen_missing: set[str] = set()
    for attr_name, body in parser.inline_handlers:
        name = _handler_required_name(body)
        if name is None:
            continue
        if name not in defined and name not in seen_missing:
            seen_missing.add(name)
            issues.append(
                f"undefined handler: {attr_name}=\"{body}\" calls '{name}' "
                f"which is not defined in any <script>"
            )

    # --- basic sanity: at least one is-active section ------------------------ #
    if section_ids and not any(sections.values()):
        issues.append(
            'no active page: expected one <section data-page> with class="is-active"'
        )

    return StaticCheckResult(
        ok=not issues,
        issues=issues,
        warnings=warnings,
        sections=sorted(section_ids),
        nav_hrefs=list(nav_hrefs),
        route_ids=route_ids,
        note=note,
    )
