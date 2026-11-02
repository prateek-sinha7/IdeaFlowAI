"""Unit tests for screenshot tiling and folder versioning in ``app/agents/tools/html_extract.py``.

Every image is built in memory with Pillow; the only disk use is ``tmp_path``.
No Chromium: ``materialise_html`` is driven down its static route.
"""

from __future__ import annotations

import io
import json
import random
from pathlib import Path

import pytest
from PIL import Image

from app.agents.tools import html_extract
from app.agents.tools.html_extract import (
    _render_screen_md,
    _screenshot_screen,
    _tile_screenshot,
    _write_screen_page,
    materialise_html,
)

_REC = {"id": "a", "title": "A", "kind": "page", "selector": "#a", "show": "visible"}


def _png(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _row_coded(height: int, width: int = 8) -> bytes:
    """A PNG whose row ``y`` is painted ``(y & 255, (y >> 8) & 255, 0)``."""
    im = Image.new("RGB", (width, height))
    rows = [((y & 255), (y >> 8) & 255, 0) for y in range(height)]
    im.putdata([rows[y] for y in range(height) for _ in range(width)])
    return _png(im)


def _noise(width: int, height: int) -> bytes:
    data = random.Random(0).randbytes(width * height * 3)
    return _png(Image.frombytes("RGB", (width, height), data))


def _open(tile: bytes) -> Image.Image:
    return Image.open(io.BytesIO(tile)).convert("RGB")


def _row_of(im: Image.Image, y: int) -> int:
    r, g, _ = im.getpixel((0, y))
    return r + (g << 8)


def _source_rows(tile: bytes) -> tuple[int, int]:
    im = _open(tile)
    return _row_of(im, 0), _row_of(im, im.height - 1)


# ── _tile_screenshot ─────────────────────────────────────────────────────────


def test_tile_screenshot_returns_original_bytes_when_within_every_limit():
    png = _png(Image.new("RGB", (1280, 900), (10, 20, 30)))

    tiles, shown, total = _tile_screenshot(png)

    assert tiles == [png]
    assert tiles[0] is png
    assert (shown, total) == (900, 900)


def test_tile_screenshot_returns_overlapping_full_width_slices_when_taller_than_tile_side():
    tiles, shown, total = _tile_screenshot(_row_coded(5000))

    assert len(tiles) == 3
    spans = [_source_rows(t) for t in tiles]
    for tile in tiles:
        im = _open(tile)
        assert im.width == 8
        assert im.height <= 2000
    assert spans[0][0] == 0
    assert spans[-1][1] == 4999
    for (_, prev_end), (next_start, _) in zip(spans[:-2], spans[1:-1], strict=True):
        assert prev_end - next_start + 1 == 40
    assert spans[-2][1] - spans[-1][0] + 1 >= 40
    assert (shown, total) == (5000, 5000)


def test_tile_screenshot_returns_18_tiles_when_screen_is_35113_px_tall():
    tiles, shown, total = _tile_screenshot(_row_coded(35_113))

    assert len(tiles) == 18
    assert all(_open(t).height <= 2000 for t in tiles)
    assert _source_rows(tiles[-1])[1] == 35_112
    assert shown == total == 35_113


def test_tile_screenshot_reports_shown_below_total_when_taller_than_twenty_tiles():
    tiles, shown, total = _tile_screenshot(_row_coded(40_000))

    assert len(tiles) == 20
    assert all(_open(t).height == 2000 for t in tiles)
    assert (shown, total) == (39_240, 40_000)
    assert _source_rows(tiles[-1])[1] == 39_239


def test_tile_screenshot_scales_tile_to_2000_px_when_wider_than_tile_side():
    tiles, _, _ = _tile_screenshot(_png(Image.new("RGB", (3000, 500), (1, 2, 3))))

    assert len(tiles) == 1
    assert _open(tiles[0]).size == (2000, 333)


def test_tile_screenshot_scales_only_to_side_cap_when_that_alone_meets_byte_cap(
    monkeypatch: pytest.MonkeyPatch,
):
    # Issue 2 pin: the old code multiplied a byte factor measured on the ORIGINAL
    # size onto the side-cap scale and produced a ~1162 px wide image here.
    monkeypatch.setattr(html_extract, "_MAX_SCREENSHOT_BYTES", 200_000)

    tiles, _, _ = _tile_screenshot(_noise(4000, 40))

    assert len(tiles) == 1
    assert _open(tiles[0]).width == 2000


def test_tile_screenshot_shrinks_tile_under_byte_cap_when_png_is_over_cap(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(html_extract, "_MAX_SCREENSHOT_BYTES", 50_000)

    tiles, _, _ = _tile_screenshot(_noise(200, 150))

    assert len(tiles) == 1
    assert len(tiles[0]) <= 50_000
    im = _open(tiles[0])
    assert abs(im.width / im.height - 4 / 3) < 0.02
    assert 120 <= im.width < 150


def test_tile_screenshot_returns_input_unchanged_when_bytes_are_undecodable():
    assert _tile_screenshot(b"not an image") == ([b"not an image"], 0, 0)


# ── _screenshot_screen ───────────────────────────────────────────────────────


class _FakeLocator:
    def __init__(self, shot: bytes) -> None:
        self._shot = shot

    def screenshot(self, timeout: int) -> bytes:
        return self._shot


class _FakePage:
    def __init__(self, shot: bytes) -> None:
        self._shot = shot

    def locator(self, selector: str) -> _FakeLocator:
        return _FakeLocator(self._shot)


def test_screenshot_screen_returns_full_size_bytes_when_element_is_tall():
    png = _row_coded(5000)

    assert _screenshot_screen(_FakePage(png), "#a") == png


# ── _render_screen_md / _write_screen_page ───────────────────────────────────


def test_render_screen_md_starts_with_one_image_line_when_screenshot_is_one_tile():
    lines = _render_screen_md(_REC, 1, 900, 900).splitlines()

    assert lines[0] == "@[[image-1.png]]"
    assert lines[1].startswith("# Screen:")
    assert lines[3] == ""
    text = "\n".join(lines)
    assert "Screenshot:" not in text
    assert "The screenshot shows" not in text


def test_render_screen_md_lists_every_tile_and_part_line_when_screenshot_has_three_tiles():
    lines = _render_screen_md(_REC, 3, 5000, 5000).splitlines()

    assert lines[0:3] == ["@[[image-1.png]]", "@[[image-2.png]]", "@[[image-3.png]]"]
    assert lines[3] == "# Screen: A"
    assert lines[4].startswith("id: a · kind: page")
    assert lines[5] == (
        "Screenshot: 3 parts, top to bottom, one per image line above. "
        "Together they are this one screen."
    )


def test_render_screen_md_adds_cut_off_line_when_shown_px_is_below_total_px():
    text = _render_screen_md(_REC, 20, 39_240, 40_000)

    assert (
        "The screenshot shows the top 39240 of 40000 px; "
        "the rest of this screen is only in the sections below."
    ) in text


def test_render_screen_md_has_no_image_line_when_there_is_no_screenshot():
    lines = _render_screen_md(_REC, 0, 0, 0).splitlines()

    assert lines[0] == "# Screen: A"


def test_write_screen_page_writes_every_tile_and_lists_them_when_screenshot_is_tall(
    tmp_path: Path,
):
    meta = _write_screen_page(tmp_path, {**_REC, "screenshot": _row_coded(5000)})

    assert meta["images"] == ["image-1.png", "image-2.png", "image-3.png"]
    for name in meta["images"]:
        assert (tmp_path / name).is_file()
    md = (tmp_path / "text.md").read_text(encoding="utf-8")
    assert md.splitlines()[0:3] == [
        "@[[image-1.png]]",
        "@[[image-2.png]]",
        "@[[image-3.png]]",
    ]


# ── materialise_html reuse vs rebuild ────────────────────────────────────────

_HTML = (
    b'<html><body><section id="a"><h2>A</h2><button>Go</button></section></body></html>'
)


@pytest.fixture
def static_route(monkeypatch: pytest.MonkeyPatch) -> None:
    def _no_browser(_path: Path):
        raise html_extract.BrowserUnavailable("no browser in unit tests")

    monkeypatch.setattr(html_extract, "_gather_browser", _no_browser)


def _materialise(tmp_path: Path) -> dict:
    source = tmp_path / "a.html"
    source.write_bytes(_HTML)
    return materialise_html(source, _HTML, tmp_path / "extract" / "a", "a.html", "a")


def _edit_manifest(tmp_path: Path, edit) -> None:
    path = tmp_path / "extract" / "a" / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    edit(manifest)
    path.write_text(json.dumps(manifest), encoding="utf-8")


def test_materialise_html_reuses_folder_when_sha_and_format_version_match(
    tmp_path: Path, static_route: None
):
    first = _materialise(tmp_path)
    second = _materialise(tmp_path)

    assert first["rebuilt"] is True
    assert first["manifest"]["format_version"] == 2
    assert second["rebuilt"] is False


def test_materialise_html_rebuilds_folder_when_manifest_lacks_format_version(
    tmp_path: Path, static_route: None
):
    _materialise(tmp_path)
    _edit_manifest(tmp_path, lambda m: m.pop("format_version"))

    result = _materialise(tmp_path)

    assert result["rebuilt"] is True
    assert result["manifest"]["format_version"] == 2


def test_materialise_html_rebuilds_folder_when_format_version_is_older(
    tmp_path: Path, static_route: None
):
    _materialise(tmp_path)
    _edit_manifest(tmp_path, lambda m: m.update(format_version=1))

    result = _materialise(tmp_path)

    assert result["rebuilt"] is True
    assert result["manifest"]["format_version"] == 2
