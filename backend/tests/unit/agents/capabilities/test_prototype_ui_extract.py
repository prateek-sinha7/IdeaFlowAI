"""Unit tests for ``build_navigation`` in agents/capabilities/prototype_ui_extract.py.

A tall screen is materialised as image-1.png … image-N.png (top to bottom); the
navigation must list every one in numeric order, not only the first slice.
"""

from __future__ import annotations

from pathlib import Path

from agents.capabilities.prototype_ui_extract import build_navigation

_SCREEN_MD = "# Screen: Tall\nid: tall · kind: page\n"


def _page(root: Path, number: str, images: list[str]) -> Path:
    page = root / "pages" / number
    page.mkdir(parents=True)
    (page / "text.md").write_text(_SCREEN_MD, encoding="utf-8")
    for name in images:
        (page / name).write_bytes(b"png")
    return page


def test_build_navigation_lists_every_tile_in_order_when_screen_has_three_images(
    tmp_path: Path,
) -> None:
    _page(tmp_path, "01", ["image-3.png", "image-1.png", "image-2.png"])

    (screen,) = build_navigation(tmp_path)["screens"]

    assert screen["screenshots"] == [
        "build/ui/screens/pages/01/image-1.png",
        "build/ui/screens/pages/01/image-2.png",
        "build/ui/screens/pages/01/image-3.png",
    ]
    assert screen["screenshot"] == "build/ui/screens/pages/01/image-1.png"


def test_build_navigation_orders_tiles_numerically_when_screen_has_ten_or_more(
    tmp_path: Path,
) -> None:
    _page(tmp_path, "01", [f"image-{k}.png" for k in range(1, 12)])

    (screen,) = build_navigation(tmp_path)["screens"]

    assert [p.rsplit("/", 1)[1] for p in screen["screenshots"]] == [
        f"image-{k}.png" for k in range(1, 12)
    ]


def test_build_navigation_ignores_other_pngs_when_page_has_non_tile_images(
    tmp_path: Path,
) -> None:
    _page(tmp_path, "01", ["image-1.png", "image-x.png", "thumb.png"])

    (screen,) = build_navigation(tmp_path)["screens"]

    assert screen["screenshots"] == ["build/ui/screens/pages/01/image-1.png"]


def test_build_navigation_has_no_screenshot_when_page_has_no_images(
    tmp_path: Path,
) -> None:
    _page(tmp_path, "01", [])

    (screen,) = build_navigation(tmp_path)["screens"]

    assert screen["screenshot"] is None
    assert screen["screenshots"] == []
