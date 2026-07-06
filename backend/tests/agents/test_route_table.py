"""tests/agents/test_route_table.py — unit coverage for the shared route resolver.

quick-260701-go2 (round 3): the ONE new shared module both prototype validators
import. Pure, stdlib-only, offline — no browser, no LLM. Proves:
  * parse_routes_table handles BOTH the object-literal (page-id values — A's form)
    AND the array-of-objects (B's form) declarations, in authored order;
  * parse_routes_table returns None for an href-valued object map (the template
    ``{id: '#/route'}`` convention), a table-less script, and unbalanced input
    (→ legacy first-segment path, INV-3);
  * resolve_route mirrors B/A matchRoute EXACTLY (exact, alias, :id parametric,
    first-match-wins with authored order, normalized path).
"""

from __future__ import annotations

from app.agents.route_table import parse_routes_table, resolve_route

# ── Representative declarations (small, inline) ──────────────────────────────

# A's form: object literal, page-id values (key == value here, as in the fixture).
_A_SCRIPT = """
    const routes = {
      'dashboard': 'dashboard',
      'inventory-list': 'inventory-list',
      'inventory-detail': 'inventory-detail',
      'settings': 'settings'
    };
"""

# B's form: array of {pattern, page} with aliases + parametric entries + comments.
_B_SCRIPT = """
    const routes = [
      { pattern: 'dashboard',           page: 'dashboard' },
      { pattern: 'inventory-list',      page: 'inventory-list' },
      { pattern: 'inventory/create',    page: 'inventory-create' },   // alias
      { pattern: 'certificate-list',    page: 'certificate-list' },
      { pattern: 'certificates',        page: 'certificate-list' },   // alias
      { pattern: 'certificates/create', page: 'certificate-create' }, // alias
      { pattern: 'certificate-detail',  page: 'certificate-detail' },
      // Parametric detail routes — matched LAST; capture the trailing id.
      { pattern: 'inventory/:id',       page: 'inventory-detail' },
      { pattern: 'certificates/:id',    page: 'certificate-detail' },
    ];
"""

# href-valued object (the template convention) — NOT a resolvable table.
_HREF_SCRIPT = "const routes = { dashboard: '#/dashboard', reports: '#/reports' };"


# ════════════════════════════════════════════════════════════════════════════
# parse_routes_table
# ════════════════════════════════════════════════════════════════════════════


def test_parse_object_form_page_id_values():
    table = parse_routes_table(_A_SCRIPT)
    assert table == [
        ("dashboard", "dashboard"),
        ("inventory-list", "inventory-list"),
        ("inventory-detail", "inventory-detail"),
        ("settings", "settings"),
    ]


def test_parse_array_form_ordered_with_aliases_and_parametric():
    table = parse_routes_table(_B_SCRIPT)
    assert table == [
        ("dashboard", "dashboard"),
        ("inventory-list", "inventory-list"),
        ("inventory/create", "inventory-create"),
        ("certificate-list", "certificate-list"),
        ("certificates", "certificate-list"),
        ("certificates/create", "certificate-create"),
        ("certificate-detail", "certificate-detail"),
        ("inventory/:id", "inventory-detail"),
        ("certificates/:id", "certificate-detail"),
    ]


def test_parse_href_valued_object_returns_none():
    # The template ``{id: '#/route'}`` convention is NOT a resolvable table → None
    # (legacy first-segment path + _extract_routes_map still handle it, INV-3).
    assert parse_routes_table(_HREF_SCRIPT) is None


def test_parse_slash_leading_value_object_returns_none():
    assert parse_routes_table("const routes = { home: '/home', about: '/about' };") is None


def test_parse_empty_valued_object_returns_none():
    assert parse_routes_table("const routes = { home: '', about: '' };") is None


def test_parse_no_routes_declaration_returns_none():
    assert parse_routes_table("function go(){ location.hash = '#/x'; }") is None
    assert parse_routes_table("") is None


def test_parse_unbalanced_returns_none():
    assert parse_routes_table("const routes = { home: 'home', ") is None
    assert parse_routes_table("const routes = [ { pattern: 'x', page: 'x' } ") is None


def test_parse_comments_do_not_leak_into_values():
    table = parse_routes_table(_B_SCRIPT)
    assert table is not None
    for pattern, page in table:
        assert "//" not in pattern and "//" not in page
        assert "alias" not in page


# ════════════════════════════════════════════════════════════════════════════
# resolve_route — mirrors B/A matchRoute EXACTLY
# ════════════════════════════════════════════════════════════════════════════


def test_resolve_parametric_id():
    b = parse_routes_table(_B_SCRIPT)
    assert resolve_route(b, "#/inventory/4521") == "inventory-detail"


def test_resolve_alias_before_parametric_order_wins():
    b = parse_routes_table(_B_SCRIPT)
    # inventory/create is authored BEFORE inventory/:id → alias wins.
    assert resolve_route(b, "#/inventory/create") == "inventory-create"


def test_resolve_certificates_parametric_and_alias():
    b = parse_routes_table(_B_SCRIPT)
    assert resolve_route(b, "#/certificates/892") == "certificate-detail"
    assert resolve_route(b, "#/certificates/create") == "certificate-create"
    assert resolve_route(b, "#/certificates") == "certificate-list"


def test_resolve_exact():
    b = parse_routes_table(_B_SCRIPT)
    assert resolve_route(b, "#/dashboard") == "dashboard"


def test_resolve_miss_returns_none():
    b = parse_routes_table(_B_SCRIPT)
    assert resolve_route(b, "#/nope") is None


def test_resolve_object_form_exact():
    a = parse_routes_table(_A_SCRIPT)
    assert resolve_route(a, "#/inventory-list") == "inventory-list"


def test_resolve_object_form_has_no_parametric():
    a = parse_routes_table(_A_SCRIPT)
    # A's object has no :id entry → a parametric path misses (→ app fallback).
    assert resolve_route(a, "#/inventory/4521") is None


def test_resolve_path_normalization():
    b = parse_routes_table(_B_SCRIPT)
    # leading '#', leading '/', trailing '/', and '?query' are all stripped.
    assert resolve_route(b, "#/dashboard/") == "dashboard"
    assert resolve_route(b, "dashboard") == "dashboard"
    assert resolve_route(b, "#/certificates?status=active") == "certificate-list"
    assert resolve_route(b, "#/inventory/4521?tab=specs") == "inventory-detail"


def test_resolve_regex_injection_guard():
    # A pattern with regex metacharacters must be escaped (no injection / catastrophic
    # backtracking); a literal '.' in a base must match a literal '.', not any char.
    table = [("a.b/:id", "detail")]
    assert resolve_route(table, "#/a.b/7") == "detail"
    assert resolve_route(table, "#/axb/7") is None
