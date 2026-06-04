"""Tests for app.agents.static_check — the no-browser prototype structural validator.

Proves the Phase-4 static pre-filter behaves: a CLEAN multi-page SPA prototype passes
(``ok=True``, no issues), and each deliberately-broken variant trips the SPECIFIC issue
it should (``ok=False`` with a precise, named message the fix-loop can feed back), while
valid-but-tricky patterns (external links, bare ``#``, method-call handlers) are NOT
flagged (no false positives).

The HTML fixtures mirror the shape the prototype pipeline emits (see
``agents/prompts/prototype-plan/AGENT.md`` and the template seed in
``app/agents/registry.py``): ``<a class="nav-item" href="#/route">`` nav links,
``<section data-page="id">`` page sections (first ``class="is-active"``), a
``const routes = { id: '#/route' }`` map, and ``onclick`` / ``addEventListener``
handlers in a ``<script>`` block.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agents.static_check import StaticCheckResult, static_check


# --------------------------------------------------------------------------- #
# Fixtures / builders
# --------------------------------------------------------------------------- #


def _clean_prototype() -> str:
    """A well-formed 3-page SPA: nav↔sections resolve, routes map complete, handlers
    defined, first page is-active. This must validate clean (the control)."""
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Acme Console</title>
  <style>
    :root { --bg: #ffffff; --fg: #0f172a; --accent: #2563eb; }
    [data-page] { display: none; }
    [data-page].is-active { display: block; }
  </style>
</head>
<body data-od-id="app">
  <nav class="sidebar" data-od-id="nav">
    <a class="nav-item" href="#/dashboard">Dashboard</a>
    <a class="nav-item" href="#/projects">Projects</a>
    <a class="nav-item" href="#/settings">Settings</a>
  </nav>
  <main data-od-id="main">
    <section data-page="dashboard" class="is-active">
      <h1>Dashboard</h1>
      <button onclick="refreshDashboard()">Refresh</button>
    </section>
    <section data-page="projects">
      <h1>Projects</h1>
      <button onclick="createProject()">New</button>
      <input onchange="filterProjects(this.value)">
    </section>
    <section data-page="settings">
      <h1>Settings</h1>
      <form onsubmit="saveSettings(event)">
        <button type="submit">Save</button>
      </form>
    </section>
  </main>
  <script>
    const store = (() => { let s = {}; return { get: k => s[k], set: p => { s = {...s, ...p}; } }; })();
    const routes = {
      dashboard: '#/dashboard',
      projects: '#/projects',
      settings: '#/settings',
    };
    function route() {
      const id = (location.hash || '#/dashboard').slice(2);
      document.querySelectorAll('[data-page]').forEach(el => {
        el.classList.toggle('is-active', el.dataset.page === id);
      });
    }
    window.addEventListener('hashchange', route);
    window.addEventListener('DOMContentLoaded', route);

    function refreshDashboard() { store.set({ refreshed: Date.now() }); }
    const createProject = () => { store.set({ creating: true }); };
    filterProjects = function (q) { store.set({ filter: q }); };
    function saveSettings(e) { e.preventDefault(); store.set({ saved: true }); }
  </script>
</body>
</html>"""


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #


def test_clean_prototype_passes() -> None:
    """A clean multi-page prototype → ok=True, no issues, no warnings."""
    result = static_check(_clean_prototype())
    assert isinstance(result, StaticCheckResult)
    assert result.ok is True, f"expected clean pass, got issues={result.issues}"
    assert result.issues == []
    assert result.warnings == []
    # Inventory is populated for callers/tests.
    assert result.sections == ["dashboard", "projects", "settings"]
    assert set(result.route_ids) == {"dashboard", "projects", "settings"}
    assert result.summary() in {"OK", "OK (inline html)"}


def test_summary_and_ok_contract() -> None:
    """ok == (not issues); summary reflects issue/warning counts."""
    clean = static_check(_clean_prototype())
    assert clean.ok == (not clean.issues)
    assert clean.summary().startswith("OK")

    broken = static_check(_clean_prototype().replace("#/projects", "#/ghost"))
    assert broken.ok is False
    assert broken.ok == (not broken.issues)
    assert "issue" in broken.summary()


# --------------------------------------------------------------------------- #
# (a) dead nav link — href with no matching section
# --------------------------------------------------------------------------- #


def test_dead_nav_link_is_flagged() -> None:
    """A nav link '#/ghost' with no <section data-page="ghost"> → ok=False, named."""
    html = """<!doctype html><body>
      <a class="nav-item" href="#/home">Home</a>
      <a class="nav-item" href="#/ghost">Ghost</a>
      <section data-page="home" class="is-active"></section>
      <script>const routes = { home: '#/home' };</script>
    </body>"""
    result = static_check(html)
    assert result.ok is False
    dead = [i for i in result.issues if "dead nav link" in i]
    assert len(dead) == 1
    assert "#/ghost" in dead[0]
    assert 'data-page="ghost"' in dead[0]
    # The real page ('home') must NOT be flagged as dead.
    assert not any("#/home" in i for i in dead)


# --------------------------------------------------------------------------- #
# (b) undefined handler — onclick referencing a non-existent function
# --------------------------------------------------------------------------- #


def test_undefined_handler_is_flagged() -> None:
    """onclick="doThing()" with no doThing definition → ok=False, names doThing."""
    html = """<!doctype html><body>
      <a class="nav-item" href="#/home">Home</a>
      <section data-page="home" class="is-active">
        <button onclick="doThing()">Do</button>
      </section>
      <script>const routes = { home: '#/home' };</script>
    </body>"""
    result = static_check(html)
    assert result.ok is False
    undef = [i for i in result.issues if "undefined handler" in i]
    assert len(undef) == 1
    assert "doThing" in undef[0]
    assert "onclick" in undef[0]


def test_defined_handler_not_flagged_various_forms() -> None:
    """function decl, const-arrow, bare-assign, and window.fn defs all satisfy."""
    html = """<!doctype html><body>
      <a class="nav-item" href="#/home">Home</a>
      <section data-page="home" class="is-active">
        <button onclick="a()">a</button>
        <button onclick="b()">b</button>
        <button onclick="c()">c</button>
        <button onclick="d()">d</button>
      </section>
      <script>
        const routes = { home: '#/home' };
        function a() {}
        const b = () => {};
        c = function () {};
        window.d = () => {};
      </script>
    </body>"""
    result = static_check(html)
    assert result.ok is True, f"unexpected issues={result.issues}"
    assert not any("undefined handler" in i for i in result.issues)


# --------------------------------------------------------------------------- #
# (c) routes map missing / extra a page id
# --------------------------------------------------------------------------- #


def test_routes_map_missing_id_is_flagged() -> None:
    """A routes map missing a real section's id → ok=False, names the id."""
    html = """<!doctype html><body>
      <a class="nav-item" href="#/home">Home</a>
      <a class="nav-item" href="#/about">About</a>
      <section data-page="home" class="is-active"></section>
      <section data-page="about"></section>
      <script>const routes = { home: '#/home' };</script>
    </body>"""
    result = static_check(html)
    assert result.ok is False
    missing = [i for i in result.issues if "routes map missing page id" in i]
    assert len(missing) == 1
    assert "'about'" in missing[0]


def test_routes_map_extra_id_is_flagged() -> None:
    """A routes key with no matching section → ok=False, named as extra."""
    html = """<!doctype html><body>
      <a class="nav-item" href="#/home">Home</a>
      <section data-page="home" class="is-active"></section>
      <script>const routes = { home: '#/home', phantom: '#/phantom' };</script>
    </body>"""
    result = static_check(html)
    assert result.ok is False
    extra = [i for i in result.issues if "routes map has extra id" in i]
    assert len(extra) == 1
    assert "'phantom'" in extra[0]


def test_no_routes_map_skips_routes_check() -> None:
    """When no routes object is present, the routes-map check is skipped (not failed)."""
    html = """<!doctype html><body>
      <a class="nav-item" href="#/home">Home</a>
      <section data-page="home" class="is-active"></section>
      <script>window.addEventListener('hashchange', function () {});</script>
    </body>"""
    result = static_check(html)
    assert result.ok is True, f"unexpected issues={result.issues}"
    assert result.route_ids == []
    assert not any("routes map" in i for i in result.issues)


# --------------------------------------------------------------------------- #
# (d) false-positive guards — valid patterns must NOT be flagged
# --------------------------------------------------------------------------- #


def test_external_links_and_bare_hash_not_flagged() -> None:
    """External http(s)/mailto/tel links + a bare '#' anchor → no dead-link issue."""
    html = """<!doctype html><body>
      <a class="nav-item" href="#/home">Home</a>
      <a class="nav-item" href="http://example.com">External HTTP</a>
      <a class="nav-item" href="https://example.com/docs">External HTTPS</a>
      <a class="nav-item" href="//cdn.example.com/x">Protocol-relative</a>
      <a class="nav-item" href="mailto:hi@example.com">Email</a>
      <a class="nav-item" href="tel:+15551234">Phone</a>
      <a class="nav-item" href="#">Top</a>
      <a class="nav-item" href="#/">Root</a>
      <section data-page="home" class="is-active"></section>
      <script>const routes = { home: '#/home' };</script>
    </body>"""
    result = static_check(html)
    assert result.ok is True, f"false positive(s): {result.issues}"
    assert result.issues == []


def test_method_call_and_expression_handlers_not_flagged() -> None:
    """Inline handlers that are method calls / property access / assignments / keywords
    must NOT demand a top-level function definition."""
    html = """<!doctype html><body>
      <a class="nav-item" href="#/home">Home</a>
      <section data-page="home" class="is-active">
        <button onclick="store.set({open: true})">store method</button>
        <button onclick="this.classList.toggle('on')">this method</button>
        <button onclick="location.hash = '#/home'">assignment</button>
        <button onclick="return false">keyword</button>
        <button onclick="alert('hi')">builtin alert</button>
        <input onchange="console.log(this.value)">
      </section>
      <script>
        const routes = { home: '#/home' };
        const store = { set() {} };
      </script>
    </body>"""
    result = static_check(html)
    assert result.ok is True, f"false positive(s): {result.issues}"
    assert not any("undefined handler" in i for i in result.issues)


def test_javascript_url_handler_not_flagged() -> None:
    """A handler prefixed javascript: that's a builtin/expression isn't a missing fn."""
    html = """<!doctype html><body>
      <a class="nav-item" href="#/home">Home</a>
      <section data-page="home" class="is-active">
        <a href="#/home" onclick="javascript:void(0)">noop</a>
      </section>
      <script>const routes = { home: '#/home' };</script>
    </body>"""
    result = static_check(html)
    assert result.ok is True, f"false positive(s): {result.issues}"


def test_empty_sections_not_flagged() -> None:
    """Empty <section data-page> blocks are expected mid-build → never a failure."""
    html = """<!doctype html><body>
      <a class="nav-item" href="#/home">Home</a>
      <a class="nav-item" href="#/reports">Reports</a>
      <section data-page="home" class="is-active"></section>
      <section data-page="reports"></section>
      <script>const routes = { home: '#/home', reports: '#/reports' };</script>
    </body>"""
    result = static_check(html)
    assert result.ok is True, f"unexpected issues={result.issues}"


def test_param_route_href_resolves_to_section() -> None:
    """A nav href with a :param segment ('#/project/42') resolves via its first
    segment to <section data-page="project"> — not flagged dead."""
    html = """<!doctype html><body>
      <a class="nav-item" href="#/projects">Projects</a>
      <a class="nav-item" href="#/project/42">Project 42</a>
      <section data-page="projects" class="is-active"></section>
      <section data-page="project"></section>
      <script>const routes = { projects: '#/projects', project: '#/project/:id' };</script>
    </body>"""
    result = static_check(html)
    assert result.ok is True, f"unexpected issues={result.issues}"


# --------------------------------------------------------------------------- #
# Other checks: orphan sections (warning), is-active sanity
# --------------------------------------------------------------------------- #


def test_orphan_section_is_warning_not_failure() -> None:
    """A section with no nav link is an advisory warning, not a failing issue."""
    html = """<!doctype html><body>
      <a class="nav-item" href="#/home">Home</a>
      <section data-page="home" class="is-active"></section>
      <section data-page="hidden"></section>
      <script>const routes = { home: '#/home', hidden: '#/hidden' };</script>
    </body>"""
    result = static_check(html)
    assert result.ok is True, f"orphan should not fail; issues={result.issues}"
    assert any("orphan section" in w and "hidden" in w for w in result.warnings)


def test_missing_is_active_is_flagged() -> None:
    """A multi-section doc with no is-active section → ok=False (no visible page)."""
    html = """<!doctype html><body>
      <a class="nav-item" href="#/home">Home</a>
      <section data-page="home"></section>
      <script>const routes = { home: '#/home' };</script>
    </body>"""
    result = static_check(html)
    assert result.ok is False
    assert any("no active page" in i for i in result.issues)


def test_multiple_distinct_issues_collected() -> None:
    """All independent defects in one doc are surfaced together (fix-loop sees them all)."""
    html = """<!doctype html><body>
      <a class="nav-item" href="#/home">Home</a>
      <a class="nav-item" href="#/ghost">Ghost</a>
      <section data-page="home" class="is-active">
        <button onclick="missingFn()">x</button>
      </section>
      <section data-page="orphanPage"></section>
      <script>const routes = { home: '#/home' };</script>
    </body>"""
    result = static_check(html)
    assert result.ok is False
    joined = " || ".join(result.issues)
    assert "dead nav link" in joined and "#/ghost" in joined
    assert "undefined handler" in joined and "missingFn" in joined
    # orphanPage is both a routes-map-missing issue AND a nav orphan warning.
    assert any("routes map missing page id 'orphanPage'" in i for i in result.issues)
    assert any("orphan section" in w and "orphanPage" in w for w in result.warnings)


# --------------------------------------------------------------------------- #
# Input modes: Path, str-path, str-html
# --------------------------------------------------------------------------- #


def test_accepts_path_input(tmp_path: Path) -> None:
    """A pathlib.Path to an HTML file is read from disk and validated."""
    p = tmp_path / "prototype.html"
    p.write_text(_clean_prototype(), encoding="utf-8")
    result = static_check(p)
    assert result.ok is True, f"issues={result.issues}"
    assert result.note.startswith("file:")


def test_accepts_str_path_input(tmp_path: Path) -> None:
    """A str path to an existing file is read from disk (not treated as HTML)."""
    p = tmp_path / "prototype.html"
    p.write_text(_clean_prototype(), encoding="utf-8")
    result = static_check(str(p))
    assert result.ok is True, f"issues={result.issues}"
    assert result.note.startswith("file:")


def test_accepts_str_html_input() -> None:
    """A raw HTML string (containing markup) is treated as inline HTML."""
    result = static_check(_clean_prototype())
    assert result.ok is True
    assert result.note == "inline html"


def test_str_path_and_file_agree(tmp_path: Path) -> None:
    """The same broken HTML yields the same verdict whether passed inline or as a file."""
    broken = _clean_prototype().replace("#/settings", "#/ghost")
    inline = static_check(broken)
    p = tmp_path / "p.html"
    p.write_text(broken, encoding="utf-8")
    onfile = static_check(p)
    assert inline.ok is False and onfile.ok is False
    assert {i for i in inline.issues} == {i for i in onfile.issues}


# --------------------------------------------------------------------------- #
# Robustness: never raises
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "html",
    [
        "",  # empty string
        "<!doctype html><html><body></body></html>",  # no sections at all
        "not html at all just text",  # garbage (single line, treated as path-probe→html)
        "<html><body><div>no sections, no nav</div></body></html>",  # nothing to check
    ],
)
def test_no_defects_when_nothing_to_check(html: str) -> None:
    """Parsing never raises; docs with no sections and no route nav links have no
    defects to report → ok=True."""
    result = static_check(html)
    assert isinstance(result, StaticCheckResult)
    assert result.ok is True
    assert result.issues == []


def test_does_not_raise_on_malformed_html() -> None:
    """A malformed/unclosed document still returns a structured result (never raises);
    a lone non-active section is correctly reported as 'no active page'."""
    result = static_check("<section data-page='x'>unclosed")
    assert isinstance(result, StaticCheckResult)
    assert isinstance(result.ok, bool)
    # It parsed a section but none is active → a real (named) defect, not a crash.
    assert result.ok is False
    assert any("no active page" in i for i in result.issues)
