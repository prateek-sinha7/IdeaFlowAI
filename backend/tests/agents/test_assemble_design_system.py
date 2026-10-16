"""Design-system reach of the assembler: theme keys, the shell's use of them, templates, warnings."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from agents.capabilities.assemble_step import (
    THEME_PATH,
    _template_theme,
    assemble,
    assemble_prototype,
    load_theme,
)
from agents.capabilities.screen_inventory import parse_inventory
from agents.capabilities.template_kit import TemplateKit

_ONE = '{"screens": [{"id": "home", "title": "Home"}]}'
_PART = '<section class="screen" id="home"><h1>Home</h1></section>'
_SHELL = (
    Path(__file__).resolve().parents[2]
    / "agents"
    / "capabilities"
    / "assemble_shell.html"
)


def _kit(*variables: str) -> TemplateKit:
    return TemplateKit(
        sources=["example.html"],
        css_blocks=[],
        classes=[],
        variables=set(variables),
    )


class _Sandbox:
    def __init__(self, files: dict[str, str]):
        self.files = dict(files)

    def read(self, path):
        return self.files.get(path)

    def write(self, path, content):
        self.files[path] = content


class _Ctx:
    def __init__(self, files: dict[str, str]):
        self.runner = type("Runner", (), {})()
        self.runner.sandbox = _Sandbox(files)
        self.deliverable = type("Deliverable", (), {"name": "prototype.html"})()


# ── Task A: the theme keys and the colour grammar ───────────────────────────────


@pytest.mark.parametrize(
    "key, value, declaration",
    [
        (
            "font_family_heading",
            "Georgia, serif",
            "--font-family-heading:Georgia, serif",
        ),
        ("radius_interactive", "9999px", "--radius-interactive:9999px"),
        ("on_primary", "#ffffff", "--color-on-primary:#ffffff"),
    ],
)
def test_each_new_theme_key_is_applied(key, value, declaration):
    css, report = load_theme(json.dumps({key: value}))
    assert report["status"] == "applied"
    assert report["applied"] == [key]
    assert declaration in css


@pytest.mark.parametrize(
    "value",
    [
        "rgb(10, 20, 30)",
        "#11223344",
        "oklch(70% 0.1 200)",
        "hsla(120deg 50% 40% / 0.5)",
    ],
)
def test_colour_keys_accept_hex_and_colour_functions(value):
    css, report = load_theme(json.dumps({"primary": value}))
    assert report["applied"] == ["primary"]
    assert f"--color-primary:{value}" in css


def test_colour_keys_reject_css_injection():
    css, report = load_theme(json.dumps({"primary": "red; } body{"}))
    assert css == ""
    assert report["status"] == "invalid"
    assert set(report["rejected"]) == {"primary"}


def test_radius_interactive_accepts_four_digits_but_border_radius_does_not():
    _, report = load_theme(json.dumps({"border_radius": "9999px"}))
    assert report["rejected"] == {"border_radius": "bad value '9999px'"}


# ── Task B: the shell uses every theme variable ─────────────────────────────────


def test_shell_defaults_put_the_page_ground_behind_the_cards():
    doc, _ = assemble(parse_inventory(_ONE), {"home": _PART})
    assert "--color-background:#f5f5f5" in doc
    assert "--color-surface:#ffffff" in doc
    assert "var(--color-on-primary)" in doc


def test_shell_has_no_hard_coded_white_paint_left():
    text = _SHELL.read_text(encoding="utf-8")
    assert not re.search(
        r"(?:background|color|border-bottom):#fff(?![0-9a-fA-F])", text
    )
    assert (
        "html,body{margin:0;padding:0;height:100%;background:var(--color-background)"
        in text
    )
    assert "font-family:var(--font-family-heading, var(--font-family))" in text
    assert "border-radius:var(--radius-interactive, var(--border-radius))" in text


# ── Task C: the whole theme onto a template ─────────────────────────────────────

_TPL_VARS = {
    "--accent",
    "--accent-soft",
    "--accent-dark",
    "--bg",
    "--ink",
    "--font-body",
    "--font-display",
    "--radius",
}
_TPL_THEME = json.dumps(
    {
        "primary": "#ff385c",
        "background": "#fafafa",
        "text": "#222222",
        "font_family": "Inter, sans-serif",
        "border_radius": "12px",
    }
)


def test_every_declared_candidate_gets_its_theme_value():
    css, themed, unapplied = _template_theme(_TPL_THEME, _kit(*_TPL_VARS))
    for var in (
        "--accent",
        "--bg",
        "--ink",
        "--font-body",
        "--font-display",
        "--radius",
    ):
        assert var in themed, var
    assert "--accent:#ff385c" in css
    assert "--bg:#fafafa" in css
    assert "--ink:#222222" in css
    assert "--font-body:Inter, sans-serif" in css
    assert "--radius:12px" in css


def test_accent_shades_are_derived_from_the_primary():
    css, _, _ = _template_theme(_TPL_THEME, _kit(*_TPL_VARS))
    assert "--accent-soft:color-mix(in srgb, #ff385c 14%, white)" in css
    assert "--accent-dark:color-mix(in srgb, #ff385c 78%, black)" in css


def test_the_heading_variable_takes_the_font_family_when_no_heading_font_is_given():
    css, _, _ = _template_theme(_TPL_THEME, _kit(*_TPL_VARS))
    assert "--font-display:Inter, sans-serif" in css


def test_a_body_font_rule_follows_the_variables_when_font_family_is_applied():
    css, _, _ = _template_theme(_TPL_THEME, _kit(*_TPL_VARS))
    assert "body{font-family:Inter, sans-serif}" in css
    assert css.index("--accent:") < css.index("body{font-family:")


def test_unapplied_lists_applied_keys_that_reach_no_template_variable():
    theme = json.dumps({**json.loads(_TPL_THEME), "surface_2": "#eeeeee"})
    _, _, unapplied = _template_theme(theme, _kit(*_TPL_VARS))
    assert unapplied == ["surface_2"]


def test_a_role_with_no_template_variable_falls_back_to_a_rule():
    theme = json.dumps({**json.loads(_TPL_THEME), "surface": "#eeeeee"})
    css, _, unapplied = _template_theme(theme, _kit(*_TPL_VARS))
    assert (
        "#slot-content :is(.card,.panel,.tile,.box,.surface){background:#eeeeee}" in css
    )
    assert "surface" not in unapplied


def test_the_report_carries_unapplied_keys_into_the_validation():
    doc, validation = assemble(
        parse_inventory(_ONE),
        {"home": _PART},
        template=_kit(*_TPL_VARS),
        theme=json.dumps({**json.loads(_TPL_THEME), "surface_2": "#eeeeee"}),
    )
    assert validation["template"]["unapplied_keys"] == ["surface_2"]
    assert "body{font-family:Inter, sans-serif}" in doc


# ── Task D: loud warnings ───────────────────────────────────────────────────────


def test_a_design_system_without_a_theme_file_raises_a_design_warning():
    ctx = _Ctx(
        {
            "build/screens.json": _ONE,
            "parts/home.html": _PART,
            ".context/selections.json": json.dumps({"ds_id": "acme"}),
        }
    )
    summary = assemble_prototype(ctx)
    files = ctx.runner.sandbox.files
    validation = json.loads(files["build/validation.json"])
    assert validation["design_warnings"] == [
        f"design system 'acme' attached but {THEME_PATH} is missing or has no valid key — the prototype uses the shell defaults"
    ]
    assert "Design warnings: design system 'acme' attached" in summary


def test_a_chosen_template_with_no_template_files_raises_a_design_warning():
    ctx = _Ctx(
        {
            "build/screens.json": _ONE,
            "parts/home.html": _PART,
            ".context/selections.json": json.dumps({"template_id": "tpl-x"}),
        }
    )
    assemble_prototype(ctx)
    validation = json.loads(ctx.runner.sandbox.files["build/validation.json"])
    assert validation["design_warnings"] == [
        "template 'tpl-x' chosen but none of its files (.context/design/template/example.html, assets/template.html) could be read — the shell's own look was used"
    ]


def test_no_selections_means_no_design_warnings_and_invalid_selections_never_raise():
    ctx = _Ctx({"build/screens.json": _ONE, "parts/home.html": _PART})
    summary = assemble_prototype(ctx)
    assert (
        json.loads(ctx.runner.sandbox.files["build/validation.json"])["design_warnings"]
        == []
    )
    assert "Design warnings" not in summary

    ctx = _Ctx(
        {
            "build/screens.json": _ONE,
            "parts/home.html": _PART,
            ".context/selections.json": "{not json",
        }
    )
    assemble_prototype(ctx)
    assert (
        json.loads(ctx.runner.sandbox.files["build/validation.json"])["design_warnings"]
        == []
    )


def _chrome_kit(*variables: str) -> TemplateKit:
    kit = _kit(*variables)
    kit.chrome_vars = ["--navy"]
    return kit


def test_a_dark_bar_takes_the_design_systems_dark_neutral_not_its_brand_colour():
    theme = json.dumps(
        {"primary": "#c96442", "primary_dark": "#a84e32", "secondary": "#30302e"}
    )
    css, _, unapplied = _template_theme(theme, _chrome_kit("--accent", "--navy"))
    assert "--navy:#30302e" in css
    assert "secondary" not in unapplied


def test_a_dark_bar_falls_back_to_primary_dark_when_no_neutral_is_dark():
    theme = json.dumps(
        {"primary": "#c96442", "primary_dark": "#a84e32", "secondary": "#eeeeee"}
    )
    css, _, _ = _template_theme(theme, _chrome_kit("--accent", "--navy"))
    assert "--navy:#a84e32" in css


def test_headings_get_the_heading_font_and_text_colour():
    theme = json.dumps(
        {"text": "#141413", "font_family_heading": '"Anthropic Serif", Georgia, serif'}
    )
    css, _, unapplied = _template_theme(theme, _kit("--fg"))
    assert (
        '#slot-content :is(h1,h2,h3,h4){font-family:"Anthropic Serif", Georgia, serif}'
        in css
    )
    assert "#slot-content :is(h1,h2,h3,h4){color:#141413}" in css
    assert "font_family_heading" not in unapplied


def test_short_radius_names_and_interactive_radius_reach_the_template():
    theme = json.dumps(
        {"border_radius": "8px", "radius_interactive": "12px", "on_primary": "#faf9f5"}
    )
    css, _, unapplied = _template_theme(theme, _kit("--r-md", "--r-lg"))
    assert "--r-md:8px" in css and "--r-lg:8px" in css
    assert "{border-radius:12px}" in css
    assert ".btn-primary{color:#faf9f5}" in css
    assert unapplied == []


def test_list_screen_fields_count_by_their_labels_on_the_screen():
    spec = (
        "### home — Home\n\n**Fields:**\n\n| Field | Control |\n|---|---|\n"
        "| Broker | Text (table column) |\n| Insured | Text (table column) |\n\n**Actions:**\n"
    )
    part = '<section class="screen" id="home"><table><tr><th>Broker</th><th>Insured</th></tr></table></section>'
    _, validation = assemble(
        parse_inventory(_ONE), {"home": part}, spec=spec, template=_kit()
    )
    screen = validation["screens"][0]
    assert screen["fields"] == {"expected": 2, "found": 2}
    assert not any("fields:" in i for i in screen["issues"])


def test_spec_fields_stop_at_the_next_bold_block():
    from agents.capabilities.screen_inventory import spec_fields

    section = (
        "### q — Queue\n\n**Fields:**\n\n| Field | Control |\n|---|---|\n| Broker | Text |\n\n"
        "**Actions:**\n\n| Control | What it does |\n|---|---|\n| Assign | assigns |\n\n"
        "**Data:** Submission entity — broker.\n"
    )
    assert spec_fields(section) == ["Broker"]


def test_spec_section_does_not_match_a_longer_id_with_the_same_prefix():
    from agents.capabilities.screen_inventory import spec_section

    spec = "### search-results — Results\nR\n### search — Search\nS\n"
    assert spec_section(spec, "search").startswith("### search — Search")


def test_web_fonts_named_by_the_theme_are_loaded_and_system_fonts_are_not():
    theme = json.dumps(
        {
            "font_family": '"Open Sans", Verdana, sans-serif',
            "font_family_heading": "Georgia, serif",
        }
    )
    doc, _ = assemble(parse_inventory(_ONE), {"home": _PART}, theme=theme)
    assert (
        "fonts.googleapis.com/css2?family=Open+Sans:wght@400;500;600;700&display=swap"
        in doc
    )
    assert "family=Georgia" not in doc
    doc2, _ = assemble(
        parse_inventory(_ONE),
        {"home": _PART},
        theme=json.dumps({"font_family": "system-ui, sans-serif"}),
    )
    assert "fonts.googleapis.com" not in doc2


def test_a_template_without_its_own_frame_drops_the_shells_screen_card():
    doc, _ = assemble(parse_inventory(_ONE), {"home": _PART}, template=_kit("--accent"))
    assert "#slot-content>.screen{display:none;background" not in doc
    assert "#slot-content>.screen.active{display:block!important}" in doc
    plain, _ = assemble(parse_inventory(_ONE), {"home": _PART})
    assert "#slot-content>.screen{display:none;background" in plain


def test_wizard_steps_reached_only_by_next_or_back_are_not_menu_pages():
    from agents.capabilities.assemble_step import nav_pages

    inv = parse_inventory(
        json.dumps(
            {
                "entry": "list",
                "screens": [
                    {
                        "id": "list",
                        "title": "Quotes",
                        "section": "Quotes",
                        "transitions": [
                            {"label": "New quote", "attr": "data-goto", "to": "step-1"}
                        ],
                    },
                    {
                        "id": "step-1",
                        "title": "Step 1",
                        "section": "Quotes",
                        "transitions": [
                            {"label": "Next", "attr": "data-goto", "to": "step-2"}
                        ],
                    },
                    {
                        "id": "step-2",
                        "title": "Step 2",
                        "section": "Quotes",
                        "transitions": [
                            {"label": "Back", "attr": "data-goto", "to": "step-1"},
                            {"label": "Continue", "attr": "data-goto", "to": "step-3"},
                        ],
                    },
                    {
                        "id": "step-3",
                        "title": "Step 3",
                        "section": "Quotes",
                        "transitions": [
                            {"label": "Back", "attr": "data-goto", "to": "step-2"}
                        ],
                    },
                ],
            }
        )
    )
    assert [s.id for s in nav_pages(inv)] == ["list", "step-1"]
