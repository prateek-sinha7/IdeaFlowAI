"""Unit tests for frame splitting in ``app/api/run_figma_frames.py``.

A PNG/JPEG frame over the model's per-image limits is split into full-width
parts (the same tiling as HTML screenshots); one that fits, or cannot be
decoded, is stored as uploaded. Pure helpers only: no DB, no HTTP client;
images are built in memory and the only disk use is ``tmp_path``.
"""

from __future__ import annotations

import io
import random
from pathlib import Path

import pytest
from PIL import Image

from app.agents.sandbox import RunSandbox
from app.agents.tools import html_extract
from app.api.run_figma_frames import _frame_parts, _write_frame_parts


def _png(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _sandbox(tmp_path: Path) -> RunSandbox:
    sandbox = RunSandbox("u1", "r1", runs_root=str(tmp_path))
    sandbox.ensure()
    return sandbox


def test_frame_parts_returns_none_when_frame_fits_every_limit():
    assert _frame_parts(_png(Image.new("RGB", (1440, 900), (5, 5, 5)))) is None


def test_frame_parts_returns_none_when_bytes_cannot_be_decoded():
    stub = bytes([0xFF, 0xD8, 0xFF, 0xE0] + [0] * 16 + [0xFF, 0xD9])

    assert _frame_parts(stub) is None


def test_frame_parts_returns_full_width_tiles_when_frame_is_taller_than_tile_side():
    split = _frame_parts(_png(Image.new("RGB", (1440, 10_000), (9, 9, 9))))

    assert split is not None
    tiles, note = split
    assert len(tiles) == 6
    for tile in tiles:
        with Image.open(io.BytesIO(tile)) as im:
            assert im.width == 1440
            assert im.height <= 2000
    assert note == "6 part(s), top to bottom; together they are this one frame."


def test_frame_parts_returns_part_under_byte_cap_when_frame_exceeds_cap(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(html_extract, "_MAX_SCREENSHOT_BYTES", 50_000)
    noise = random.Random(0).randbytes(200 * 150 * 3)

    split = _frame_parts(_png(Image.frombytes("RGB", (200, 150), noise)))

    assert split is not None
    tiles, _ = split
    assert len(tiles) == 1
    assert len(tiles[0]) <= 50_000


def test_frame_parts_notes_cut_off_when_frame_is_taller_than_twenty_tiles():
    split = _frame_parts(_png(Image.new("RGB", (8, 40_000), (1, 1, 1))))

    assert split is not None
    tiles, note = split
    assert len(tiles) == 20
    assert note.endswith("The parts show the top 39240 of 40000 px.")


def test_write_frame_parts_writes_every_part_and_returns_manifest_fields_when_frame_was_split(
    tmp_path: Path,
):
    sandbox = _sandbox(tmp_path)
    tiles = [b"tile-one", b"tile-two"]

    fields = _write_frame_parts(sandbox, "frame-3.png", (tiles, "2 part(s), note"))

    assert fields == {
        "parts": ["frame-3-part-1.png", "frame-3-part-2.png"],
        "parts_note": "2 part(s), note",
    }
    assert sandbox.path_for(".figma/frame-3-part-1.png").read_bytes() == b"tile-one"
    assert sandbox.path_for(".figma/frame-3-part-2.png").read_bytes() == b"tile-two"


def test_write_frame_parts_writes_nothing_when_frame_fits(tmp_path: Path):
    sandbox = _sandbox(tmp_path)

    assert _write_frame_parts(sandbox, "frame-1.png", None) == {}
    figma = sandbox.path_for(".figma")
    assert not figma.exists() or not list(figma.glob("*-part-*"))
