"""tests/integration/api/test_figma_ingestor_scripts.py

Integration tests for the three new stdlib-only scripts:
- figma_extract.py: observations.json + manifest.json → source.json + mapping.json
- figma_to_html.py: frames.json + tokens.css → example.html (template contract)
- make_ds.py (sandbox copy): mapping.json → tokens.css + components.html

No DB, no LLM, no network. Pure file I/O with tmp_path.
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[3]
_SCRIPTS = _BACKEND / "skills" / "global" / "figma-ingestor" / "scripts"


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _sample_manifest() -> list[dict]:
    return [
        {"name": "frame-1.png", "mime": "image/png", "type": "image",
         "description": "Dashboard overview", "has_text": False},
        {"name": "frame-2.png", "mime": "image/png", "type": "image",
         "description": "Data table", "has_text": False},
    ]


def _sample_observations() -> dict:
    return {
        "frames": [
            {
                "index": 0, "name": "frame-1.png", "screen": "Dashboard",
                "layout": "sidebar-nav", "color_scheme": "dark",
                "bg": "#13151f", "fg": "#e0e0e0", "accent": "#5b5fef",
                "surface": "#1e2130", "surface_2": "#252a3d",
                "border": "#2a2f45", "muted": "#9aa0b4", "on_accent": "#ffffff",
                "font_weight": "medium", "font_density": "compact",
                "font_family_hint": "Inter, system-ui, sans-serif",
            },
            {
                "index": 1, "name": "frame-2.png", "screen": "Data Table",
                "layout": "sidebar-nav", "color_scheme": "dark",
                "bg": "#13151f", "fg": "#e0e0e0", "accent": "#5b5fef",
                "surface": "#1e2130", "surface_2": "#252a3d",
                "border": "#2a2f45", "muted": "#9aa0b4", "on_accent": "#ffffff",
                "font_weight": "medium", "font_density": "compact",
                "font_family_hint": "Inter, system-ui, sans-serif",
            },
        ],
        "dominant_layout": "sidebar-nav",
        "color_scheme": "dark",
        "suggested_name": "SaaS Dashboard",
    }


def _sample_frames_json() -> list[dict]:
    return [
        {"index": 0, "filename": "frame-1.png", "screen": "Dashboard",
         "description": "Dashboard overview", "layout": "sidebar-nav",
         "source": ".figma/frame-1.png"},
        {"index": 1, "filename": "frame-2.png", "screen": "Data Table",
         "description": "Data table view", "layout": "sidebar-nav",
         "source": ".figma/frame-2.png"},
    ]


def _sample_tokens_css() -> str:
    return """:root {
  --bg: #13151f;
  --fg: #e0e0e0;
  --accent: #5b5fef;
  --accent-dark: #4d4fd9;
  --surface: #1e2130;
  --surface-2: #252a3d;
  --border: #2a2f45;
  --muted: #9aa0b4;
  --on-accent: #ffffff;
  --font-display: Inter, system-ui, sans-serif;
  --font-body: Inter, system-ui, sans-serif;
  --text-base: 14px;
  --text-sm: 12px;
  --text-xs: 10px;
  --text-lg: 16px;
  --text-xl: 19px;
  --text-2xl: 22px;
  --text-3xl: 28px;
  --text-4xl: 34px;
}
"""


# ── figma_extract.py tests ────────────────────────────────────────────────────

@pytest.mark.integration
def test_figma_extract_produces_source_json(tmp_path) -> None:
    """figma_extract.py must write source.json with variables.:root block."""
    if not (_SCRIPTS / "figma_extract.py").exists():
        pytest.skip("figma_extract.py not yet created (Phase 3)")

    (tmp_path / "manifest.json").write_text(
        json.dumps(_sample_manifest()), encoding="utf-8"
    )
    (tmp_path / "observations.json").write_text(
        json.dumps(_sample_observations()), encoding="utf-8"
    )

    result = subprocess.run(
        [sys.executable, str(_SCRIPTS / "figma_extract.py"),
         "--manifest", str(tmp_path / "manifest.json"),
         "--obs", str(tmp_path / "observations.json"),
         "--out", str(tmp_path)],
        capture_output=True, text=True, cwd=str(_SCRIPTS),
    )
    assert result.returncode == 0, f"figma_extract.py failed:\n{result.stderr}"

    source_path = tmp_path / "source.json"
    assert source_path.exists(), "source.json not written"
    source = json.loads(source_path.read_text())
    assert "variables" in source, "source.json missing 'variables' key"
    assert ":root" in source["variables"], "source.json missing ':root' in variables"
    root_vars = source["variables"][":root"]
    assert "--bg" in root_vars, "source.json missing --bg in :root"
    assert "--accent" in root_vars, "source.json missing --accent in :root"


@pytest.mark.integration
def test_figma_extract_produces_mapping_json(tmp_path) -> None:
    """figma_extract.py must write mapping.json with 'tokens' containing identity tokens."""
    if not (_SCRIPTS / "figma_extract.py").exists():
        pytest.skip("figma_extract.py not yet created (Phase 3)")

    (tmp_path / "manifest.json").write_text(
        json.dumps(_sample_manifest()), encoding="utf-8"
    )
    (tmp_path / "observations.json").write_text(
        json.dumps(_sample_observations()), encoding="utf-8"
    )

    subprocess.run(
        [sys.executable, str(_SCRIPTS / "figma_extract.py"),
         "--manifest", str(tmp_path / "manifest.json"),
         "--obs", str(tmp_path / "observations.json"),
         "--out", str(tmp_path)],
        capture_output=True, text=True, cwd=str(_SCRIPTS), check=True,
    )

    mapping_path = tmp_path / "mapping.json"
    assert mapping_path.exists(), "mapping.json not written"
    mapping = json.loads(mapping_path.read_text())
    assert "tokens" in mapping, "mapping.json missing 'tokens'"
    tokens = mapping["tokens"]
    required_identity = {"--bg", "--fg", "--accent", "--surface", "--border", "--muted"}
    for t in required_identity:
        assert t in tokens, f"mapping.json missing identity token {t}"


@pytest.mark.integration
def test_figma_extract_colors_match_observations(tmp_path) -> None:
    """figma_extract.py must preserve the exact hex values from observations.json."""
    if not (_SCRIPTS / "figma_extract.py").exists():
        pytest.skip("figma_extract.py not yet created (Phase 3)")

    (tmp_path / "manifest.json").write_text(
        json.dumps(_sample_manifest()), encoding="utf-8"
    )
    (tmp_path / "observations.json").write_text(
        json.dumps(_sample_observations()), encoding="utf-8"
    )

    subprocess.run(
        [sys.executable, str(_SCRIPTS / "figma_extract.py"),
         "--manifest", str(tmp_path / "manifest.json"),
         "--obs", str(tmp_path / "observations.json"),
         "--out", str(tmp_path)],
        capture_output=True, text=True, cwd=str(_SCRIPTS), check=True,
    )

    mapping = json.loads((tmp_path / "mapping.json").read_text())
    assert mapping["tokens"]["--bg"] == "#13151f", "--bg hex must match observations"
    assert mapping["tokens"]["--accent"] == "#5b5fef", "--accent hex must match observations"


@pytest.mark.integration
def test_figma_extract_no_network_calls() -> None:
    """figma_extract.py must be pure stdlib — no imports that require network."""
    if not (_SCRIPTS / "figma_extract.py").exists():
        pytest.skip("figma_extract.py not yet created (Phase 3)")

    content = (_SCRIPTS / "figma_extract.py").read_text(encoding="utf-8")
    tree = ast.parse(content)
    imports = [
        node.names[0].name.split(".")[0] if isinstance(node, ast.Import)
        else (node.module.split(".")[0] if node.module else "")
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    forbidden = {"requests", "httpx", "aiohttp", "boto3", "anthropic", "openai"}
    found = set(imports) & forbidden
    assert not found, f"figma_extract.py must not import network libs: {found}"


# ── make_ds.py (sandbox copy) tests ──────────────────────────────────────────

@pytest.mark.integration
def test_make_ds_produces_tokens_css(tmp_path) -> None:
    """make_ds.py must write tokens.css with :root block when given valid mapping.json."""
    if not (_SCRIPTS / "make_ds.py").exists():
        pytest.skip("make_ds.py not yet created (Phase 3)")
    if not (_SCRIPTS / "figma_extract.py").exists():
        pytest.skip("figma_extract.py needed to produce mapping.json (Phase 3)")

    (tmp_path / "manifest.json").write_text(
        json.dumps(_sample_manifest()), encoding="utf-8"
    )
    (tmp_path / "observations.json").write_text(
        json.dumps(_sample_observations()), encoding="utf-8"
    )
    subprocess.run(
        [sys.executable, str(_SCRIPTS / "figma_extract.py"),
         "--manifest", str(tmp_path / "manifest.json"),
         "--obs", str(tmp_path / "observations.json"),
         "--out", str(tmp_path)],
        capture_output=True, text=True, cwd=str(_SCRIPTS), check=True,
    )

    dest = tmp_path / "output"
    dest.mkdir()
    env = {**os.environ, "OD_SCHEMA_PATH": str(_SCRIPTS / "schema")}
    result = subprocess.run(
        [sys.executable, str(_SCRIPTS / "make_ds.py"),
         str(tmp_path / "mapping.json"),
         "--dest", str(dest)],
        capture_output=True, text=True, env=env, cwd=str(_SCRIPTS),
    )
    assert result.returncode == 0, f"make_ds.py failed:\n{result.stderr}"

    tokens_css = dest / "tokens.css"
    assert tokens_css.exists(), "tokens.css not written by make_ds.py"
    css_content = tokens_css.read_text()
    assert ":root {" in css_content, "tokens.css missing :root block"
    assert "--bg:" in css_content, "tokens.css missing --bg"


@pytest.mark.integration
def test_make_ds_produces_components_html(tmp_path) -> None:
    """make_ds.py must write components.html referencing var(--*) only."""
    if not (_SCRIPTS / "make_ds.py").exists():
        pytest.skip("make_ds.py not yet created (Phase 3)")
    if not (_SCRIPTS / "figma_extract.py").exists():
        pytest.skip("figma_extract.py needed (Phase 3)")

    (tmp_path / "manifest.json").write_text(
        json.dumps(_sample_manifest()), encoding="utf-8"
    )
    (tmp_path / "observations.json").write_text(
        json.dumps(_sample_observations()), encoding="utf-8"
    )
    subprocess.run(
        [sys.executable, str(_SCRIPTS / "figma_extract.py"),
         "--manifest", str(tmp_path / "manifest.json"),
         "--obs", str(tmp_path / "observations.json"),
         "--out", str(tmp_path)],
        capture_output=True, text=True, cwd=str(_SCRIPTS), check=True,
    )

    dest = tmp_path / "output"
    dest.mkdir()
    env = {**os.environ, "OD_SCHEMA_PATH": str(_SCRIPTS / "schema")}
    subprocess.run(
        [sys.executable, str(_SCRIPTS / "make_ds.py"),
         str(tmp_path / "mapping.json"), "--dest", str(dest)],
        capture_output=True, text=True, env=env, cwd=str(_SCRIPTS), check=True,
    )

    components_html = dest / "components.html"
    assert components_html.exists(), "components.html not written"
    content = components_html.read_text()
    assert "var(--bg)" in content or "var(--accent)" in content, (
        "components.html must reference CSS variables via var(--*)"
    )


# ── figma_to_html.py tests ────────────────────────────────────────────────────

@pytest.mark.integration
def test_figma_to_html_produces_example_html(tmp_path) -> None:
    """figma_to_html.py must write a valid HTML file."""
    if not (_SCRIPTS / "figma_to_html.py").exists():
        pytest.skip("figma_to_html.py not yet created (Phase 4)")

    (tmp_path / "frames.json").write_text(
        json.dumps(_sample_frames_json()), encoding="utf-8"
    )
    (tmp_path / "tokens.css").write_text(_sample_tokens_css(), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_SCRIPTS / "figma_to_html.py"),
         "--frames", str(tmp_path / "frames.json"),
         "--tokens", str(tmp_path / "tokens.css"),
         "--prefix", "fg",
         "--out", str(tmp_path / "example.html")],
        capture_output=True, text=True, cwd=str(_SCRIPTS),
    )
    assert result.returncode == 0, f"figma_to_html.py failed:\n{result.stderr}"
    assert (tmp_path / "example.html").exists(), "example.html not written"


@pytest.mark.integration
def test_figma_to_html_template_contract_nav_items(tmp_path) -> None:
    """example.html must have .nav-item[data-go] elements (template contract)."""
    if not (_SCRIPTS / "figma_to_html.py").exists():
        pytest.skip("figma_to_html.py not yet created (Phase 4)")

    (tmp_path / "frames.json").write_text(
        json.dumps(_sample_frames_json()), encoding="utf-8"
    )
    (tmp_path / "tokens.css").write_text(_sample_tokens_css(), encoding="utf-8")
    subprocess.run(
        [sys.executable, str(_SCRIPTS / "figma_to_html.py"),
         "--frames", str(tmp_path / "frames.json"),
         "--tokens", str(tmp_path / "tokens.css"),
         "--prefix", "fg",
         "--out", str(tmp_path / "example.html")],
        capture_output=True, text=True, cwd=str(_SCRIPTS), check=True,
    )

    html = (tmp_path / "example.html").read_text()
    assert "nav-item" in html, "example.html missing nav-item class"
    assert "data-go=" in html, "example.html missing data-go attributes"
    nav_count = html.count("data-go=")
    assert nav_count >= 2, f"example.html must have at least 2 nav items, found {nav_count}"


@pytest.mark.integration
def test_figma_to_html_template_contract_pattern_sections(tmp_path) -> None:
    """example.html must have section.pattern[data-pattern] per frame (contract)."""
    if not (_SCRIPTS / "figma_to_html.py").exists():
        pytest.skip("figma_to_html.py not yet created (Phase 4)")

    (tmp_path / "frames.json").write_text(
        json.dumps(_sample_frames_json()), encoding="utf-8"
    )
    (tmp_path / "tokens.css").write_text(_sample_tokens_css(), encoding="utf-8")
    subprocess.run(
        [sys.executable, str(_SCRIPTS / "figma_to_html.py"),
         "--frames", str(tmp_path / "frames.json"),
         "--tokens", str(tmp_path / "tokens.css"),
         "--prefix", "fg",
         "--out", str(tmp_path / "example.html")],
        capture_output=True, text=True, cwd=str(_SCRIPTS), check=True,
    )

    html = (tmp_path / "example.html").read_text()
    pattern_count = len(re.findall(r"data-pattern=", html))
    assert pattern_count >= 2, (
        f"example.html must have one pattern section per frame (got {pattern_count})"
    )
    assert 'class="pattern"' in html or "class='pattern'" in html, (
        "example.html missing class=pattern on sections"
    )


@pytest.mark.integration
def test_figma_to_html_template_contract_root_css_vars(tmp_path) -> None:
    """example.html must declare :root CSS vars from the tokens file."""
    if not (_SCRIPTS / "figma_to_html.py").exists():
        pytest.skip("figma_to_html.py not yet created (Phase 4)")

    (tmp_path / "frames.json").write_text(
        json.dumps(_sample_frames_json()), encoding="utf-8"
    )
    (tmp_path / "tokens.css").write_text(_sample_tokens_css(), encoding="utf-8")
    subprocess.run(
        [sys.executable, str(_SCRIPTS / "figma_to_html.py"),
         "--frames", str(tmp_path / "frames.json"),
         "--tokens", str(tmp_path / "tokens.css"),
         "--prefix", "fg",
         "--out", str(tmp_path / "example.html")],
        capture_output=True, text=True, cwd=str(_SCRIPTS), check=True,
    )

    html = (tmp_path / "example.html").read_text()
    assert ":root" in html, "example.html must contain :root CSS vars"
    assert "--bg:" in html, "example.html must contain --bg token"
    assert "--accent:" in html, "example.html must contain --accent token"


@pytest.mark.integration
def test_figma_to_html_active_nav_item(tmp_path) -> None:
    """First nav item must have is-active class (template contract)."""
    if not (_SCRIPTS / "figma_to_html.py").exists():
        pytest.skip("figma_to_html.py not yet created (Phase 4)")

    (tmp_path / "frames.json").write_text(
        json.dumps(_sample_frames_json()), encoding="utf-8"
    )
    (tmp_path / "tokens.css").write_text(_sample_tokens_css(), encoding="utf-8")
    subprocess.run(
        [sys.executable, str(_SCRIPTS / "figma_to_html.py"),
         "--frames", str(tmp_path / "frames.json"),
         "--tokens", str(tmp_path / "tokens.css"),
         "--prefix", "fg",
         "--out", str(tmp_path / "example.html")],
        capture_output=True, text=True, cwd=str(_SCRIPTS), check=True,
    )

    html = (tmp_path / "example.html").read_text()
    assert "is-active" in html, "example.html must mark the first nav item as is-active"


@pytest.mark.integration
def test_figma_to_html_one_frame_per_section(tmp_path) -> None:
    """Number of pattern sections must equal number of frames in frames.json."""
    if not (_SCRIPTS / "figma_to_html.py").exists():
        pytest.skip("figma_to_html.py not yet created (Phase 4)")

    frames = _sample_frames_json()
    (tmp_path / "frames.json").write_text(json.dumps(frames), encoding="utf-8")
    (tmp_path / "tokens.css").write_text(_sample_tokens_css(), encoding="utf-8")
    subprocess.run(
        [sys.executable, str(_SCRIPTS / "figma_to_html.py"),
         "--frames", str(tmp_path / "frames.json"),
         "--tokens", str(tmp_path / "tokens.css"),
         "--prefix", "fg",
         "--out", str(tmp_path / "example.html")],
        capture_output=True, text=True, cwd=str(_SCRIPTS), check=True,
    )

    html = (tmp_path / "example.html").read_text()
    pattern_count = len(re.findall(r"data-pattern=", html))
    assert pattern_count == len(frames), (
        f"Expected {len(frames)} pattern sections, got {pattern_count}"
    )
