"""extract_prototype_ui — the prototype's look and feel into build/ui/, by code."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import pytest

from agents.capabilities.prototype_ui_extract import (
    build_navigation,
    build_tokens,
    extract_prototype_ui,
    find_source,
    readable_on,
    stage_chained_prototype,
    to_hex,
)
from app.agents.sandbox import RunSandbox

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "html"


def _sandbox(tmp_path: Path) -> RunSandbox:
    sb = RunSandbox("u", "r", runs_root=str(tmp_path))
    sb.ensure()
    return sb


class _Runner:
    def __init__(self, sandbox: RunSandbox) -> None:
        self.sandbox = sandbox

    async def materialise_html(self, *args) -> None:
        from app.agents.tools.html_extract import materialise_html

        await asyncio.to_thread(materialise_html, *args)


def _runner(sandbox: RunSandbox) -> _Runner:
    return _Runner(sandbox)


def test_colours_normalise_to_upper_hex_and_transparent_is_none():
    assert to_hex("rgb(47, 111, 235)") == "#2F6FEB"
    assert to_hex("rgba(0, 0, 0, 0)") is None
    assert to_hex("#abc") == "#AABBCC"
    assert to_hex("inherit") is None


def test_text_on_a_colour_is_whichever_contrasts_more():
    assert readable_on("#3C2CDA") == "#FFFFFF"
    assert readable_on("#F39200") == "#15161A"  # white on orange is ~2.3:1


def test_tokens_take_the_effective_variable_and_rank_the_palette_by_use():
    probe = {
        # The prototype declares --color-primary twice; the browser hands back the one that won.
        "variables": {
            "--color-primary": "#2F6FEB",
            "--color-text": "#111111",
            "--color-error": "#C62828",
        },
        "tally": {
            "colors": {
                "rgb(17, 17, 17)": {"count": 9, "roles": {"text": 9}},
                "rgb(47, 111, 235)": {"count": 3, "roles": {"background": 3}},
            },
            "fonts": {"Inter, sans-serif": {"count": 12, "roles": {}}},
            "sizes": {"14px|400|p": {"count": 7, "roles": {}}},
            "radii": {"8px": {"count": 4, "roles": {}}},
            "shadows": {},
        },
        "body": {
            "fontFamily": "Inter, sans-serif",
            "color": "rgb(17, 17, 17)",
            "background": "rgb(255, 255, 255)",
        },
    }
    tokens = build_tokens(probe)

    assert tokens["brand"] == {
        "primary": "#2F6FEB",
        "on_primary": readable_on("#2F6FEB"),
    }
    assert [c["hex"] for c in tokens["colors"]] == ["#111111", "#2F6FEB", "#C62828"]
    assert tokens["colors"][0]["variables"] == ["--color-text"]
    # A declared colour the opening screen never shows is still in the palette.
    assert tokens["colors"][2] == {
        "hex": "#C62828",
        "count": 0,
        "roles": {},
        "variables": ["--color-error"],
    }
    assert tokens["type_scale"] == [
        {"size": "14px", "weight": "400", "tag": "p", "count": 7}
    ]


def test_navigation_is_read_from_the_per_screen_pages(tmp_path):
    page = tmp_path / "pages" / "01"
    page.mkdir(parents=True)
    (page / "text.md").write_text(
        "# Screen: Dashboard\nid: dashboard · kind: page\n\n## Actions\n| Label | Goes to or does |\n|---|---|\n"
        "| My Pets | data-goto=my-pets |\n| My Pets | data-goto=my-pets |\n| Refresh |  |\n"
    )
    (page / "image-1.png").write_bytes(b"png")

    nav = build_navigation(tmp_path)

    assert nav["screens"] == [
        {
            "id": "dashboard",
            "title": "Dashboard",
            "screenshot": "build/ui/screens/pages/01/image-1.png",
        }
    ]
    assert nav["edges"] == [{"from": "dashboard", "to": "my-pets", "label": "My Pets"}]


def test_a_chained_prototype_wins_and_is_staged_as_an_upload(tmp_path):
    sb = _sandbox(tmp_path)
    sb.path_for(".uploads").mkdir(parents=True, exist_ok=True)
    sb.path_for(".uploads/brief.pdf").write_bytes(b"%PDF")
    sb.path_for(".uploads/manifest.json").write_text(
        json.dumps([{"name": "brief.pdf"}])
    )
    assert find_source(sb) is None

    sb.path_for(".context").mkdir(parents=True, exist_ok=True)
    sb.path_for(".context/prototype.html").write_text("<html></html>")
    assert find_source(sb) == ".context/prototype.html"

    assert stage_chained_prototype(sb) is True
    assert sb.path_for(".uploads/prototype.html").read_text() == "<html></html>"
    names = [
        e["name"] for e in json.loads(sb.path_for(".uploads/manifest.json").read_text())
    ]
    assert names == ["brief.pdf", "prototype.html"]
    # Staging twice never duplicates, and never replaces the user's own upload.
    assert stage_chained_prototype(sb) is False


def test_no_prototype_writes_only_the_reason(tmp_path):
    sb = _sandbox(tmp_path)

    note = asyncio.run(extract_prototype_ui(_runner(sb)))

    assert note.startswith("No prototype")
    assert json.loads(sb.path_for("build/ui/source.json").read_text())["source"] is None
    assert not sb.path_for("build/ui/tokens.json").exists()


def test_a_real_prototype_renders_into_tokens_components_screens_and_navigation(
    tmp_path,
):
    pytest.importorskip("playwright")
    sb = _sandbox(tmp_path)
    sb.path_for(".uploads").mkdir(parents=True, exist_ok=True)
    shutil.copy(
        FIXTURES / "shell_prototype.html", sb.path_for(".uploads/prototype.html")
    )

    note = asyncio.run(extract_prototype_ui(_runner(sb)))
    if "could not be rendered" in note:
        pytest.skip(f"no browser here: {note}")

    tokens = json.loads(sb.path_for("build/ui/tokens.json").read_text())
    nav = json.loads(sb.path_for("build/ui/navigation.json").read_text())
    components = json.loads(sb.path_for("build/ui/components.json").read_text())
    assert tokens["colors"] and tokens["fonts"]
    assert nav["screens"] and any(
        e["to"] in ("beacon", "crimson") for e in nav["edges"]
    )
    assert "button" in components
    assert components["button"]["style"]["color"].startswith("#")


def test_the_backlog_workflow_extracts_first_and_writes_ui_ux_after_the_solution():
    from agents.execution_engine.engine import compile_for_run

    compiled = compile_for_run("backlog")
    ids = [s.id.split(":", 1)[1] for s in compiled.steps]

    assert (
        ids[0] == "us-ui-extract"
        and compiled.steps[0].mechanical == "extract_prototype_ui"
    )
    assert ids.index("us-uiux") == ids.index("us-solution") + 1
    assert compiled.deliverable.chains_from is True


def test_screenshots_are_kept_out_of_the_run_history(tmp_path):
    """The run-history commit's binary scan refuses PNGs; a refused screenshot
    once blocked every commit of run 53d022e9. build/ui ignores its own PNGs."""
    sb = _sandbox(tmp_path)

    asyncio.run(extract_prototype_ui(_runner(sb)))

    assert sb.path_for("build/ui/.gitignore").read_text() == "*.png\n"
