"""Unit tests for agents/capabilities/assemble_step.py."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from agents.capabilities.assemble_step import (
    COVERAGE_THRESHOLD,
    AssembleStepFailed,
    MechanicalAssembleStrategy,
    assemble,
    assemble_prototype,
    extract_section,
    namespace_ids,
    strip_forbidden,
)
from agents.capabilities.screen_inventory import parse_inventory


class TestExtractSection:
    """Test the extract_section() function."""

    def test_extract_exact_section_id(self):
        html = '<section class="screen" id="home">Home content</section>'
        section, notes = extract_section(html, "home")
        assert section is not None
        assert 'id="home"' in section

    def test_extract_adds_screen_class_if_missing(self):
        html = '<section id="home">Home content</section>'
        section, notes = extract_section(html, "home")
        assert 'class="screen"' in section or 'class="' in section
        assert "screen" in section
        assert any("missing class=screen" in n for n in notes)

    def test_extract_falls_back_to_first_screen_section(self):
        html = '<section id="wrong">Wrong</section><section class="screen" id="other">Other</section>'
        section, notes = extract_section(html, "home")
        assert section is not None
        assert any("no section with id" in n for n in notes)

    def test_extract_no_section_returns_none(self):
        html = "<div>No section here</div>"
        section, notes = extract_section(html, "home")
        assert section is None
        assert any("no <section>" in n for n in notes)

    def test_extract_empty_text_returns_none(self):
        section, notes = extract_section("", "home")
        assert section is None
        assert any("empty" in n for n in notes)

    def test_extract_nested_sections_preserved(self):
        html = '<section class="screen" id="home"><section class="subsection">Sub</section></section>'
        section, notes = extract_section(html, "home")
        assert section is not None
        assert '<section class="subsection">' in section


class TestStripForbidden:
    """Test the strip_forbidden() function."""

    def test_strip_script_tags(self):
        html = '<section><script>alert("x")</script>Content</section>'
        result, notes = strip_forbidden(html)
        assert "<script>" not in result
        assert "Content" in result
        assert any("removed" in n and "script" in n for n in notes)

    def test_strip_style_tags(self):
        html = "<section><style>.x { color: red; }</style>Content</section>"
        result, notes = strip_forbidden(html)
        assert "<style>" not in result
        assert "Content" in result
        assert any("removed" in n and "style" in n for n in notes)

    def test_strip_link_tags(self):
        html = '<section><link rel="stylesheet" href="style.css">Content</section>'
        result, notes = strip_forbidden(html)
        assert "<link" not in result
        assert "Content" in result
        assert any("removed" in n and "link" in n for n in notes)

    def test_strip_multiple_forbidden(self):
        html = '<section><script>x</script><style>y</style><link href="z">Content</section>'
        result, notes = strip_forbidden(html)
        assert "<script>" not in result
        assert "<style>" not in result
        assert "<link" not in result
        assert "Content" in result

    def test_strip_no_forbidden_empty_notes(self):
        html = "<section>Clean content</section>"
        result, notes = strip_forbidden(html)
        assert result == html
        assert len(notes) == 0


class TestNamespaceIds:
    """Test the namespace_ids() function."""

    def test_namespace_prefixes_inner_ids(self):
        html = '<section id="home"><div id="panel-a">A</div></section>'
        result, dups, local = namespace_ids(html, "home", set())
        # Inner id should be prefixed
        assert 'id="home--panel-a"' in result
        # Root id should NOT be prefixed
        assert 'id="home"' in result

    def test_namespace_maps_for_references(self):
        html = '<section id="home"><label for="field-1">Label</label><input id="field-1"></section>'
        result, dups, local = namespace_ids(html, "home", set())
        # Both the id and the for reference should be prefixed
        assert 'id="home--field-1"' in result
        assert 'for="home--field-1"' in result

    def test_namespace_reports_duplicate_ids(self):
        html = '<section id="home"><div id="dup">1</div><div id="dup">2</div></section>'
        result, dups, local = namespace_ids(html, "home", set())
        assert "home--dup" in dups or "dup" in dups

    def test_namespace_reserved_ids_reported_as_shadowed(self):
        html = '<section id="home"><div id="settings">Shadowing</div></section>'
        reserved = {"settings"}  # settings is a reserved screen id
        result, dups, local = namespace_ids(html, "home", reserved)
        # The id should still be prefixed
        assert 'id="home--settings"' in result
        # And reported as shadowed
        assert any("shadowed" in str(d) for d in dups)

    def test_namespace_data_tab_references_mapped(self):
        html = '<section id="home"><div data-tab="panel-a">Tab</div><div id="panel-a">Content</div></section>'
        result, dups, local = namespace_ids(html, "home", set())
        # Both should be prefixed
        assert 'data-tab="home--panel-a"' in result
        assert 'id="home--panel-a"' in result

    def test_namespace_aria_labelledby_with_multiple_tokens(self):
        html = '<section id="home"><div aria-labelledby="label-1 label-2">Content</div><span id="label-1">L1</span><span id="label-2">L2</span></section>'
        result, dups, local = namespace_ids(html, "home", set())
        # Both tokens should be prefixed
        assert 'aria-labelledby="home--label-1 home--label-2"' in result

    def test_namespace_href_hash_references(self):
        html = '<section id="home"><a href="#panel-1">Link</a><div id="panel-1">Panel</div></section>'
        result, dups, local = namespace_ids(html, "home", set())
        # href hash reference should be prefixed
        assert 'href="#home--panel-1"' in result

    def test_namespace_returns_local_ids_after(self):
        html = '<section id="home"><div id="a">A</div><div id="b">B</div></section>'
        result, dups, local = namespace_ids(html, "home", set())
        # local_ids_after should contain prefixed versions
        assert "home--a" in local
        assert "home--b" in local


class TestAssemble:
    """Test the assemble() function."""

    def test_assemble_basic_prototype(self):
        inv = parse_inventory('{"screens": [{"id": "home"}]}')
        parts = {"home": '<section class="screen" id="home">Home</section>'}
        html, validation = assemble(inv, parts)

        assert "<!DOCTYPE" in html or "<!doctype" in html.lower()
        assert validation["passed"] is not None
        assert "home" in validation["entry"]

    def test_assemble_with_missing_part(self):
        inv = parse_inventory('{"screens": [{"id": "home"}]}')
        parts = {}  # Missing part
        html, validation = assemble(inv, parts)

        assert validation["totals"]["missing"] == 1
        assert "home" in validation["missing"]
        assert 'data-stub="true"' in html

    def test_assemble_with_invalid_part(self):
        inv = parse_inventory('{"screens": [{"id": "home"}]}')
        parts = {"home": "<div>No section</div>"}
        html, validation = assemble(inv, parts)

        assert validation["totals"]["invalid"] == 1
        assert "home" in validation["missing"]

    def test_assemble_dialog_wrapped(self):
        inv = parse_inventory('{"screens": [{"id": "modal", "kind": "dialog"}]}')
        parts = {"modal": '<section class="screen" id="modal">Modal content</section>'}
        html, validation = assemble(inv, parts)

        assert 'class="dialog"' in html
        assert 'id="dialog-modal"' in html

    def test_assemble_entry_marked_active(self):
        inv = parse_inventory('{"screens": [{"id": "home"}], "entry": "home"}')
        parts = {"home": '<section class="screen" id="home">Home</section>'}
        html, validation = assemble(inv, parts)

        # Entry should have class="active"
        assert 'class="screen active"' in html

    def test_assemble_coverage_calculation(self):
        inv = parse_inventory('{"screens": [{"id": "s1"}, {"id": "s2"}]}')
        parts = {"s1": '<section class="screen" id="s1">S1</section>'}
        html, validation = assemble(inv, parts)

        # 1 out of 2 = 50%
        assert validation["coverage"] == 0.5
        assert validation["totals"]["built"] == 1
        assert validation["totals"]["missing"] == 1

    def test_assemble_below_threshold_fails(self):
        inv = parse_inventory('{"screens": [{"id": "s1"}, {"id": "s2"}]}')
        parts = {"s1": '<section class="screen" id="s1">S1</section>'}
        html, validation = assemble(inv, parts, threshold=0.9)

        # Coverage 0.5 < threshold 0.9
        assert validation["passed"] is False

    def test_assemble_validation_broken_transitions(self):
        inv = parse_inventory(
            '{"screens": [{"id": "home", "transitions": [{"label": "Go", "to": "unknown"}]}]}'
        )
        parts = {
            "home": '<section class="screen" id="home"><button data-goto="unknown">Go</button></section>'
        }
        html, validation = assemble(inv, parts)

        # Should report broken transition
        report = validation["screens"][0]
        assert len(report["broken_transitions"]) > 0

    def test_assemble_validation_missing_transitions(self):
        inv = parse_inventory(
            '{"screens": [{"id": "home", "transitions": [{"label": "Go", "to": "about"}]}]}'
        )
        parts = {
            "home": '<section class="screen" id="home">Home</section>',
            "about": "...",
        }
        html, validation = assemble(inv, parts)

        # Should report missing expected transition
        report = validation["screens"][0]
        assert len(report["missing_transitions"]) > 0

    def test_assemble_validation_json_written(self):
        inv = parse_inventory('{"screens": [{"id": "home"}]}')
        parts = {"home": '<section class="screen" id="home">Home</section>'}
        html, validation = assemble(inv, parts)

        # Validation should be a valid dict
        assert isinstance(validation, dict)
        assert "version" in validation
        assert "coverage" in validation


class TestAssemblePrototype:
    """Test the assemble_prototype() function."""

    def test_assemble_prototype_writes_html(self):
        # Fake sandbox with read/write dicts
        class FakeSandbox:
            def __init__(self):
                self.files = {}

            def read(self, path):
                return self.files.get(path)

            def write(self, path, content):
                self.files[path] = content

        class FakeRunner:
            def __init__(self):
                self.sandbox = FakeSandbox()

        class FakeDeliverable:
            name = "prototype.html"

        class FakeCtx:
            def __init__(self):
                self.runner = FakeRunner()
                self.deliverable = FakeDeliverable()

        ctx = FakeCtx()
        ctx.runner.sandbox.write(
            "build/screens.json",
            '{"screens": [{"id": "home"}]}',
        )
        ctx.runner.sandbox.write(
            "parts/home.html",
            '<section class="screen" id="home">Home</section>',
        )

        result = assemble_prototype(ctx)

        assert isinstance(result, str)
        assert "prototype.html" in result or "Assembled" in result
        assert "prototype.html" in ctx.runner.sandbox.files

    def test_assemble_prototype_missing_inventory_raises(self):
        class FakeSandbox:
            def read(self, path):
                return None

        class FakeRunner:
            def __init__(self):
                self.sandbox = FakeSandbox()

        class FakeCtx:
            def __init__(self):
                self.runner = FakeRunner()

        ctx = FakeCtx()

        with pytest.raises(AssembleStepFailed, match="does not exist"):
            assemble_prototype(ctx)

    def test_assemble_prototype_invalid_json_raises(self):
        class FakeSandbox:
            def read(self, path):
                if path == "build/screens.json":
                    return "{invalid json}"
                return None

        class FakeRunner:
            def __init__(self):
                self.sandbox = FakeSandbox()

        class FakeCtx:
            def __init__(self):
                self.runner = FakeRunner()

        ctx = FakeCtx()

        with pytest.raises(AssembleStepFailed):
            assemble_prototype(ctx)

    def test_assemble_prototype_below_threshold_raises(self):
        class FakeSandbox:
            def __init__(self):
                self.files = {}

            def read(self, path):
                if path == "build/screens.json":
                    return '{"screens": [{"id": "home"}, {"id": "about"}]}'
                return None

            def write(self, path, content):
                self.files[path] = content

        class FakeRunner:
            def __init__(self):
                self.sandbox = FakeSandbox()

        class FakeCtx:
            def __init__(self):
                self.runner = FakeRunner()

        ctx = FakeCtx()

        with pytest.raises(AssembleStepFailed, match="coverage threshold"):
            assemble_prototype(ctx)


class TestMechanicalAssembleStrategy:
    """Test the MechanicalAssembleStrategy class."""

    def test_mechanical_assemble_strategy_has_name(self):
        strategy = MechanicalAssembleStrategy(spec=None, index=0, total=1, results=[])
        assert strategy.name == "assemble_prototype"

    @pytest.mark.asyncio
    async def test_mechanical_assemble_strategy_run_success(self):
        class FakeSandbox:
            def __init__(self):
                self.files = {}

            def read(self, path):
                return self.files.get(path)

            def write(self, path, content):
                self.files[path] = content

        class FakeRunner:
            def __init__(self):
                self.sandbox = FakeSandbox()

        class FakeSpec:
            id = "assemble-step"
            name = "Assemble"

        class FakeCtx:
            def __init__(self):
                self.runner = FakeRunner()

        ctx = FakeCtx()
        ctx.runner.sandbox.write(
            "build/screens.json",
            '{"screens": [{"id": "home"}]}',
        )
        ctx.runner.sandbox.write(
            "parts/home.html",
            '<section class="screen" id="home">Home</section>',
        )

        spec = FakeSpec()
        strategy = MechanicalAssembleStrategy(spec=spec, index=0, total=1, results=[])

        events = []
        async for event in strategy.run(None, ctx):
            events.append(event)

        # Should yield agent_start, agent_chunk, agent_complete
        event_types = [e["type"] for e in events]
        assert "agent_start" in event_types
        assert "agent_chunk" in event_types
        assert "agent_complete" in event_types

    @pytest.mark.asyncio
    async def test_mechanical_assemble_strategy_run_failure(self):
        class FakeSandbox:
            def read(self, path):
                return None  # No screens.json

        class FakeRunner:
            def __init__(self):
                self.sandbox = FakeSandbox()

        class FakeSpec:
            id = "assemble-step"
            name = "Assemble"

        class FakeCtx:
            def __init__(self):
                self.runner = FakeRunner()

        ctx = FakeCtx()
        spec = FakeSpec()
        strategy = MechanicalAssembleStrategy(spec=spec, index=0, total=1, results=[])

        with pytest.raises(AssembleStepFailed):
            async for event in strategy.run(None, ctx):
                pass


class TestValidationStructure:
    """Test the validation.json output structure."""

    def test_validation_has_required_fields(self):
        inv = parse_inventory('{"screens": [{"id": "home"}]}')
        parts = {"home": '<section class="screen" id="home">Home</section>'}
        html, validation = assemble(inv, parts)

        required = [
            "version",
            "generated_by",
            "passed",
            "coverage",
            "threshold",
            "totals",
            "entry",
            "missing",
            "degraded",
            "screens",
            "document",
            "summary",
        ]
        for field in required:
            assert field in validation, f"Missing field: {field}"

    def test_validation_totals_structure(self):
        inv = parse_inventory('{"screens": [{"id": "home"}]}')
        parts = {"home": '<section class="screen" id="home">Home</section>'}
        html, validation = assemble(inv, parts)

        totals = validation["totals"]
        assert "screens" in totals
        assert "built" in totals
        assert "ok" in totals
        assert "degraded" in totals
        assert "missing" in totals
        assert "invalid" in totals

    def test_validation_screen_report(self):
        inv = parse_inventory('{"screens": [{"id": "home"}]}')
        parts = {"home": '<section class="screen" id="home">Home</section>'}
        html, validation = assemble(inv, parts)

        report = validation["screens"][0]
        assert "id" in report
        assert "title" in report
        assert "kind" in report
        assert "status" in report
        assert "issues" in report


class TestPrototypeShell:
    """Test that the prototype includes the required shell structure."""

    def test_prototype_has_nav_slot(self):
        inv = parse_inventory('{"screens": [{"id": "home"}]}')
        parts = {"home": '<section class="screen" id="home">Home</section>'}
        html, _ = assemble(inv, parts)

        assert 'id="slot-nav"' in html

    def test_prototype_has_content_slot(self):
        inv = parse_inventory('{"screens": [{"id": "home"}]}')
        parts = {"home": '<section class="screen" id="home">Home</section>'}
        html, _ = assemble(inv, parts)

        assert 'id="slot-content"' in html

    def test_prototype_has_overlays_slot(self):
        inv = parse_inventory('{"screens": [{"id": "home"}]}')
        parts = {"home": '<section class="screen" id="home">Home</section>'}
        html, _ = assemble(inv, parts)

        assert 'id="slot-overlays"' in html

    def test_prototype_has_dialog_css_rule(self):
        inv = parse_inventory('{"screens": [{"id": "home"}]}')
        parts = {"home": '<section class="screen" id="home">Home</section>'}
        html, _ = assemble(inv, parts)

        # Should have CSS rule to hide dialogs
        assert "#slot-overlays .dialog" in html or ".dialog{display:none" in html


def test_in_screen_states_are_namespaced_validated_and_in_the_shell():
    """data-show / data-hide target a local `.state`; the shell carries the mechanism and
    a dialog opened from a dialog replaces it (QA run 11 findings 1 and 2)."""
    from agents.capabilities.assemble_step import assemble, namespace_ids
    from agents.capabilities.screen_inventory import parse_inventory

    sec = (
        '<section class="screen" id="edm"><button data-show="confirm">Finalize</button>'
        '<div class="state" id="confirm"><button data-hide="confirm">No</button></div>'
        '<button data-show="ghost">Broken</button></section>'
    )
    out, dups, local = namespace_ids(sec, "edm", set())
    assert (
        'id="edm--confirm"' in out
        and 'data-show="edm--confirm"' in out
        and 'data-hide="edm--confirm"' in out
    )
    inv = parse_inventory('{"entry":"edm","screens":[{"id":"edm","title":"EDM"}]}')
    doc, val = assemble(inv, {"edm": sec})
    s = val["screens"][0]
    assert s["status"] == "degraded"
    assert any(
        b["attr"] == "data-show" and b["to"] == "ghost" for b in s["broken_transitions"]
    )  # unknown target stays unprefixed
    assert ".state{display:none}" in doc and ".state.open{display:revert}" in doc
    assert "closeDialog(); openDialog(v);" in doc and "[data-show],[data-hide]" in doc


# ── theme: build/theme.json → :root override (prototype v4 design context) ──────────
from agents.capabilities.assemble_step import THEME_KEYS, THEME_PATH, load_theme  # noqa: E402

_ONE = '{"screens": [{"id": "home", "title": "Home"}]}'
_PART = '<section class="screen" id="home"><h1>Home</h1></section>'


def _assemble_with_theme(theme):
    inv = parse_inventory(_ONE)
    return assemble(inv, {"home": _PART}, theme=theme)


def test_theme_absent_keeps_the_default_shell_and_reports_default():
    doc, validation = _assemble_with_theme(None)
    assert validation["theme"] == {"status": "default", "applied": [], "rejected": {}}
    assert "__THEME__" not in doc
    assert doc.count(":root{") == 1  # only the shell's own block


def test_theme_applied_overrides_root_after_the_shell_defaults():
    doc, validation = _assemble_with_theme(
        '{"primary": "#ff385c", "font_family": "Inter, Arial, sans-serif", "border_radius": "12px"}'
    )
    assert validation["theme"]["status"] == "applied"
    assert validation["theme"]["applied"] == ["primary", "font_family", "border_radius"]
    override = ":root{--color-primary:#ff385c;--font-family:Inter, Arial, sans-serif;--border-radius:12px}"
    assert override in doc
    assert doc.index("--color-primary:#003f7f") < doc.index(
        override
    )  # override wins by order


def test_theme_rejects_unknown_keys_and_bad_values_but_applies_the_rest():
    doc, validation = _assemble_with_theme(
        '{"primary": "#123456", "shadow": "0 0 1px", "text": "red", "border_radius": "1000px", "background": "#fff"}'
    )
    th = validation["theme"]
    assert th["status"] == "applied"
    assert th["applied"] == ["primary", "background"]
    assert set(th["rejected"]) == {"shadow", "text", "border_radius"}
    assert "--color-primary:#123456" in doc and "--color-background:#fff" in doc
    assert "--color-text:red" not in doc and "1000px" not in doc


def test_theme_invalid_json_is_reported_and_ignored():
    doc, validation = _assemble_with_theme("{not json")
    assert validation["theme"]["status"] == "invalid"
    assert "_" in validation["theme"]["rejected"]
    assert doc.count(":root{") == 1


def test_theme_keys_map_onto_shell_variables_that_exist():
    shell = (
        Path(__file__).resolve().parents[2]
        / "agents"
        / "capabilities"
        / "assemble_shell.html"
    )
    text = shell.read_text()
    for var in THEME_KEYS.values():
        assert f"{var}:" in text, var
    assert "__THEME__" in text


def test_assemble_prototype_reads_theme_from_the_sandbox():
    class Sandbox:
        def __init__(self):
            self.files = {}

        def read(self, p):
            return self.files.get(p)

        def write(self, p, c):
            self.files[p] = c

    class Ctx:
        class runner:
            pass

        class deliverable:
            name = "prototype.html"

    ctx = Ctx()
    ctx.runner = Ctx.runner()
    ctx.runner.sandbox = Sandbox()
    ctx.runner.sandbox.write("build/screens.json", _ONE)
    ctx.runner.sandbox.write("parts/home.html", _PART)
    ctx.runner.sandbox.write(THEME_PATH, '{"secondary": "#00aa00"}')
    summary = assemble_prototype(ctx)
    assert "--color-secondary:#00aa00" in ctx.runner.sandbox.files["prototype.html"]
    assert "Theme applied from build/theme.json: secondary" in summary
    assert json.loads(ctx.runner.sandbox.files["build/validation.json"])["theme"][
        "applied"
    ] == ["secondary"]


# ── v4 assembler checks: double navigation attributes, untriggered states, field count ─
_TWO = '{"screens": [{"id": "a", "title": "A", "transitions": [{"label": "Go", "attr": "data-goto", "to": "b"}]}, {"id": "b", "title": "B"}]}'


def test_double_navigation_attribute_loses_data_tab_and_is_reported():
    inv = parse_inventory(_TWO)
    part = '<section class="screen" id="a"><a class="tab-link" data-tab="x" data-goto="b">Go</a><div class="tab-panel" id="x"></div></section>'
    doc, v = assemble(
        inv, {"a": part, "b": '<section class="screen" id="b">B</section>'}
    )
    a = next(s for s in v["screens"] if s["id"] == "a")
    assert (
        'data-goto="b"' in doc
        and 'data-tab="x"' not in doc.split('id="b"')[0].split('id="a"')[1]
    )
    assert any("removed data-tab" in i for i in a["issues"])
    assert a["status"] == "ok"  # fixed by code, not a build failure


def test_state_nothing_reveals_is_degraded_and_named():
    inv = parse_inventory(_TWO)
    part = (
        '<section class="screen" id="a"><button class="btn" data-goto="b">Go</button>'
        '<div class="state" id="results">r</div><div class="state" id="empty">e</div>'
        '<button class="btn" data-show="empty">Show</button></section>'
    )
    _, v = assemble(inv, {"a": part, "b": '<section class="screen" id="b">B</section>'})
    a = next(s for s in v["screens"] if s["id"] == "a")
    assert a["status"] == "degraded"
    assert a["untriggered_states"] == ["a--results"]
    assert any("state(s) nothing reveals: a--results" in i for i in a["issues"])


def test_field_count_against_the_spec_marks_thin_screens_degraded():
    inv = parse_inventory(_TWO)
    spec = "## Screens\n### a — A\n- Fields:\n  - One [text]\n  - Two [text]\n  - Three [text]\n  - Four [text]\n  - Five [text]\n### b — B\n"
    thin = '<section class="screen" id="a"><input class="form-control" id="one"><button data-goto="b">Go</button></section>'
    full = (
        '<section class="screen" id="a">'
        + "".join(f'<input class="form-control" id="f{i}">' for i in range(5))
        + '<button data-goto="b">Go</button></section>'
    )
    _, v1 = assemble(
        inv, {"a": thin, "b": "<section class='screen' id='b'>B</section>"}, spec=spec
    )
    _, v2 = assemble(
        inv, {"a": full, "b": "<section class='screen' id='b'>B</section>"}, spec=spec
    )
    a1 = next(s for s in v1["screens"] if s["id"] == "a")
    a2 = next(s for s in v2["screens"] if s["id"] == "a")
    assert a1["fields"] == {"expected": 5, "found": 1} and a1["status"] == "degraded"
    assert any("fields: 1 built of 5" in i for i in a1["issues"])
    assert a2["fields"] == {"expected": 5, "found": 5} and a2["status"] == "ok"


# ── the design template (template_kit) ──────────────────────────────────────────
from agents.capabilities.assemble_step import GUARD_CSS, nav_pages  # noqa: E402
from agents.capabilities.template_kit import TEMPLATE_DIR, load_template_kit  # noqa: E402

_EXAMPLE = """<!doctype html><html><head>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans">
<style>:root{--accent:#0f62fe;--bg:#fff;--fg:#161616;--navy:#001d6c}
body{display:grid}.topbar{background:var(--navy)}.nav-item{color:#fff}.nav-item.is-active{font-weight:700}
.card{border:1px solid var(--accent)}.screen{padding:4px}</style></head>
<body><header class="topbar" id="accounts"><span class="brand-name">Northstar</span>
<nav class="nav"><a class="nav-item is-active" data-page-link="accounts" onclick="go()">Accounts</a>
<a class="nav-item" data-page-link="queue">Queue</a></nav></header>
<main class="page"><section class="screen">example page</section></main>
<div class="toast">Saved</div><script>function go(){}</script></body></html>"""
_INV = json.dumps({"title": "PawCare", "entry": "list", "screens": [
    {"id": "list", "title": "Pets", "transitions": [{"label": "New", "attr": "data-goto", "to": "pet-create"}]},
    {"id": "pet-create", "title": "Pet Create"},
    {"id": "reports", "title": "Reports"},
]})
_PARTS = {s: f'<section class="screen" id="{s}"><input id="n"><select id="k"></select></section>'
          for s in ("list", "pet-create", "reports")}


def _kit(files):
    return load_template_kit(lambda p: files.get(p[len(TEMPLATE_DIR) + 1:]))


def test_no_template_files_means_no_kit():
    assert _kit({}) is None


def test_a_template_brings_its_frame_css_and_theme_and_keeps_the_runtime():
    doc, validation = assemble(parse_inventory(_INV), _PARTS, template=_kit({"example.html": _EXAMPLE}),
                               theme='{"primary": "#ff385c", "background": "#fafafa", "surface": "#eeeeee"}')
    assert 'class="shell-header"' not in doc and '<header class="topbar">' in doc
    assert '<main id="slot-content" class="page">' in doc
    # The template's nav items become the prototype's screens, record pages left out.
    assert '<a class="nav-item" href="#list" data-goto="list">Pets</a>' in doc
    assert 'data-goto="pet-create">' not in doc.split('id="slot-content"')[0]
    assert "links[k].classList.toggle('is-active', " in doc
    # The frame keeps its look and loses its behaviour and example content.
    assert 'id="accounts"' not in doc and "data-page-link" not in doc and "onclick" not in doc
    assert "Saved" not in doc and "example page" not in doc and ">PawCare<" in doc
    # CSS order: shell, template, guard, theme — and the DS lands on declared vars only.
    assert doc.index(".nav-item.is-active") < doc.index(GUARD_CSS) < doc.index("--accent:#ff385c")
    assert "--bg:#fafafa" in doc and "--surface:" not in doc.split(GUARD_CSS)[1]
    assert "fonts.googleapis.com" in doc
    assert validation["template"]["frame"] == "template"
    # The dark bar's own --navy takes the DS too (no primary_dark given, so primary).
    assert validation["template"]["themed_vars"] == ["--accent", "--bg", "--navy"]
    assert "--navy:#ff385c" in doc


def test_a_template_without_a_frame_keeps_the_shell_frame_with_its_css():
    doc, validation = assemble(parse_inventory(_INV), _PARTS,
                               template=_kit({"example.html": "<style>.card{color:red}</style><p>x</p>"}))
    assert 'class="shell-header"' in doc and ".card{color:red}" in doc and GUARD_CSS in doc
    assert validation["template"]["frame"] == "shell"


def test_fields_are_counted_as_controls_when_builders_use_the_template():
    spec = "### list\n| Field | Control |\n|---|---|\n| Name | text |\n| Kind | select |\n"
    kit = _kit({"example.html": _EXAMPLE})
    _, with_template = assemble(parse_inventory(_INV), _PARTS, template=kit, spec=spec)
    _, shell_only = assemble(parse_inventory(_INV), _PARTS, spec=spec)
    by_id = lambda v: {s["id"]: s for s in v["screens"]}  # noqa: E731
    assert by_id(with_template)["list"]["fields"]["found"] == 2
    assert by_id(shell_only)["list"]["fields"]["found"] == 0   # no form-control class


def test_record_pages_reached_from_a_list_stay_out_of_the_menu():
    inv = parse_inventory(_INV)
    assert [s.id for s in nav_pages(inv)] == ["list", "reports"]
    lonely = parse_inventory(json.dumps({"entry": "a", "screens": [{"id": "a"}, {"id": "b-edit", "title": "B Edit"}]}))
    assert [s.id for s in nav_pages(lonely)] == ["a", "b-edit"]   # nothing leads to it: it stays


# ── sections: a menu of product areas, the area's pages as tabs ─────────────────
from agents.capabilities.assemble_step import SECTION_CSS, nav_model  # noqa: E402

_SECTIONED = json.dumps({"title": "PawCare", "entry": "pets", "screens": [
    {"id": "login", "title": "Sign in", "section": "_auth",
     "transitions": [{"label": "Sign in", "attr": "data-submit", "to": "pets"}]},
    {"id": "pets", "title": "Pets", "section": "Care",
     "transitions": [{"label": "New", "attr": "data-goto", "to": "pet-create"}]},
    {"id": "visits", "title": "Visit history", "section": "Care", "tab": "Visits"},
    {"id": "pet-create", "title": "Pet Create", "section": "Care"},
    {"id": "users", "title": "Users", "section": "Admin"},
    {"id": "my-profile", "title": "My Profile", "section": "Admin"},
]})
_SEC_PARTS = {s: f'<section class="screen" id="{s}"><p>{s}</p></section>'
              for s in ("login", "pets", "visits", "pet-create", "users", "my-profile")}


def test_the_menu_is_the_sections_and_the_sections_pages_are_tabs():
    doc, validation = assemble(parse_inventory(_SECTIONED), _SEC_PARTS)
    nav = doc.split('<nav id="slot-nav"')[1].split("</nav>")[0]
    assert nav.count("data-section=") == 2 and ">Care<" in nav and ">Admin<" in nav
    assert "Sign in" not in nav and "Pet Create" not in nav
    tabs = doc.split('<nav id="slot-tabs"')[1].split("</nav>")[0]
    assert 'data-tabs-for="care"' in tabs and ">Visits<" in tabs    # the short tab label
    assert "pet-create" not in tabs                                   # a record page is not a tab
    # The prototype opens on the app, not on a sign-in wall; a create page lights its
    # list's section and tab.
    assert validation["entry"] == "pets" and 'var ENTRY = "pets"' in doc
    place = json.loads(doc.split("var PLACE = ")[1].split(", ACTIVE")[0])
    assert place["pet-create"] == ["care", "pets"] and place["login"] == ["_auth", ""]
    # The account menu replaces the shell's greeting; the build status is not shipped.
    assert 'data-goto="my-profile">My profile</a>' in doc and 'data-goto="login">Sign out</a>' in doc
    assert "Welcome, Reviewer" not in doc and 'class="shell-status"' not in doc.split("</style>")[-1]
    assert SECTION_CSS in doc


def test_without_sections_the_menu_is_flat_as_before():
    doc, _ = assemble(parse_inventory(_INV), _PARTS)
    assert "data-section" not in doc and 'id="slot-tabs"' not in doc and "var PLACE" not in doc
    assert nav_model(parse_inventory(_INV)) is None
    assert 'class="nav-link" href="#list"' in doc


def test_a_template_frame_gets_sections_its_demo_content_removed_and_the_menu_at_the_avatar():
    example = _EXAMPLE.replace("</nav></header>",
                               '</nav><span class="env-pill">UAT</span><span class="brand-sub">SPECIALTY</span>'
                               '<input placeholder="Search accounts…"><span class="avatar">AR</span></header>')
    doc, _ = assemble(parse_inventory(_SECTIONED), _SEC_PARTS, template=_kit({"example.html": example}))
    header = doc.split('<header class="topbar">')[1].split("</header>")[0]
    assert "UAT" not in header and "SPECIALTY" not in header and ">AR<" not in header
    assert 'placeholder="Search…"' in header and 'class="proto-user"' in header
    assert 'class="nav-item" href="#pets" data-goto="pets" data-section="care">Care<' in header
    assert "var PLACE" in doc and '"is-active"' in doc      # the template's own active class


def test_a_control_that_moves_the_user_loses_its_data_show():
    # Run 87e02c32: Sign in carried data-submit and data-show; the runtime checks
    # data-show first, so it only ever showed the error and never signed in.
    inv = parse_inventory(json.dumps({"entry": "login", "screens": [
        {"id": "login", "transitions": [{"label": "Sign in", "attr": "data-submit", "to": "home"}]},
        {"id": "home"}]}))
    part = ('<section class="screen" id="login"><button data-submit="home" data-show="err">Sign in</button>'
            '<div class="state" id="err">Wrong password</div></section>')
    doc, validation = assemble(inv, {"login": part, "home": '<section class="screen" id="home"></section>'})
    button = doc.split("Sign in</button>")[0].rsplit("<button", 1)[1]
    assert 'data-submit="home"' in button and "data-show" not in button
    login = next(s for s in validation["screens"] if s["id"] == "login")
    assert any("removed data-show" in i for i in login["issues"])


def test_every_page_sits_in_the_templates_own_column():
    example = _EXAMPLE.replace('<section class="screen">example page</section>',
                               '<section class="screen"><div class="wrap">example page</div></section>')
    kit = _kit({"example.html": example})
    parts = dict(_PARTS, reports='<section class="screen" id="reports"><div class="wrap"><p>r</p></div></section>')
    doc, _ = assemble(parse_inventory(_INV), parts, template=kit)
    assert '<section class="screen active" id="list"><div class="wrap"><input' in doc     # wrapped by code
    assert doc.count('<div class="wrap"><div class="wrap">') == 0                          # never twice
    assert doc.index(":where(#slot-nav,#slot-tabs)") < doc.index(".nav-item{")   # reset first: the template wins


def test_a_sign_in_page_that_leads_nowhere_is_wired_into_the_app():
    # Run 9b6f1bfb: Sign In was a plain submit button, and nothing led from Login into the app.
    parts = dict(_SEC_PARTS, login='<section class="screen" id="login"><form><input id="u">'
                                   '<button type="submit" class="btn btn-primary">Sign in</button></form></section>')
    doc, validation = assemble(parse_inventory(_SECTIONED), parts)
    assert '<button type="submit" class="btn btn-primary" data-submit="pets">Sign in</button>' in doc
    login = next(s for s in validation["screens"] if s["id"] == "login")
    assert any("sign-in button wired to pets" in i for i in login["issues"])


def test_a_sign_in_page_that_already_leads_into_the_app_is_left_alone():
    parts = dict(_SEC_PARTS, login='<section class="screen" id="login">'
                                   '<button class="btn" data-submit="users">Go</button></section>')
    doc, _ = assemble(parse_inventory(_SECTIONED), parts)
    assert 'data-submit="users">Go</button>' in doc and 'data-submit="pets"' not in doc.split('id="login"')[1].split("</section>")[0]
