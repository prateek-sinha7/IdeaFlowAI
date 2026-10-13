"""backend/tests/agents/test_html_extract.py — the HTML/HTM route in extract_text (spec 021 T12).

Coverage:
  a. prototype_v2-shell fixture: 4 screens, options+[value=...] exact, validation
     attrs, data-goto targets, hidden-state message, image-1.png, rendered_by
     chromium, the shell runtime listed but not copied.
  b. a generic form page (two <section>s + a native <dialog>) -> 3 screens.
  c. a screen a script builds at load (not in the static markup) -> found only on
     the browser route.
  d. the static fallback (launcher forced to raise) on fixture a: rendered_by
     static, static_reason set, screens still found, no screenshots, receipt says
     static.
  e. the manifest carries every PDF-manifest key; shards carry the PDF shard keys.
  f. a .htm upload lands in the SAME .extract/html/<slug>/ as its .html sibling.
  g. a second extract with unchanged bytes rebuilds nothing; changed bytes rebuild.
  h. the async extract_text() entry point (sandbox-bound, as the PDF tests use it)
     returns a receipt for an html upload.

Browser-dependent assertions (a, c, and any screenshot check) are marked
``requires_chromium`` and skip cleanly when Chromium cannot launch in the test
environment — checked once, at import time, by ``_chromium_available()``.
"""

from __future__ import annotations

import json
import pathlib

import pytest

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "html"


def _chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return False
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=["--no-sandbox"])
            browser.close()
        return True
    except Exception:
        return False


_CHROMIUM_AVAILABLE = _chromium_available()

requires_chromium = pytest.mark.skipif(
    not _CHROMIUM_AVAILABLE, reason="Chromium not available in this test environment"
)


class _Sandbox:
    """Minimal sandbox mock, matching test_file_extract_tools.py's convention."""

    def __init__(self, root: pathlib.Path):
        self.root = root

    def path_for(self, relpath: str) -> pathlib.Path:
        if str(relpath).startswith("/"):
            raise ValueError(f"absolute paths not allowed: {relpath}")
        resolved = (self.root / relpath).resolve()
        if not resolved.is_relative_to(self.root.resolve()):
            raise ValueError(f"path escape attempt: {relpath}")
        return resolved


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    from app.agents.tools import file_extract_tools

    monkeypatch.setattr(file_extract_tools, "_SANDBOX", _Sandbox(tmp_path))
    (tmp_path / ".uploads").mkdir(exist_ok=True)
    return tmp_path


def _upload(
    root: pathlib.Path, fixture_name: str, upload_name: str | None = None
) -> str:
    """Copy a fixture into .uploads/ and return its sandbox-relative path."""
    name = upload_name or fixture_name
    dest = root / ".uploads" / name
    dest.write_bytes((FIXTURES / fixture_name).read_bytes())
    return f".uploads/{name}"


def _doc_dir(root: pathlib.Path, slug: str) -> pathlib.Path:
    return root / ".extract" / "html" / slug


def _manifest(root: pathlib.Path, slug: str) -> dict:
    return json.loads((_doc_dir(root, slug) / "manifest.json").read_text())


def _page_text(root: pathlib.Path, slug: str, page: int) -> str:
    return (_doc_dir(root, slug) / "pages" / f"{page:02d}" / "text.md").read_text()


def _screen_page_text(root: pathlib.Path, manifest: dict, screen_id: str) -> str:
    entry = next(s for s in manifest["screens"] if s["id"] == screen_id)
    return _page_text(root, manifest["slug"], entry["page"])


def _all_page_texts(root: pathlib.Path, manifest: dict) -> list[str]:
    return [
        _page_text(root, manifest["slug"], n)
        for n in range(1, manifest["page_count"] + 1)
    ]


# ---------------------------------------------------------------------------
# a. prototype_v2-shell fixture
# ---------------------------------------------------------------------------


@requires_chromium
class TestShellPrototype:
    def test_four_screens_rendered_by_chromium(self, sandbox):
        from app.agents.tools import file_extract_tools

        path = _upload(sandbox, "shell_prototype.html")
        result = file_extract_tools._extract_html_sync(path)

        assert "Materialised" in result
        assert "Screens: 4 (rendered by chromium)" in result

        manifest = _manifest(sandbox, "shell-prototype")
        assert manifest["rendered_by"] == "chromium"
        assert manifest["static_reason"] is None
        ids = sorted(s["id"] for s in manifest["screens"])
        assert ids == ["anchor", "beacon", "confirm-dialog", "crimson"]

    def test_option_values_copied_exactly(self, sandbox):
        from app.agents.tools import file_extract_tools

        path = _upload(sandbox, "shell_prototype.html")
        file_extract_tools._extract_html_sync(path)
        manifest = _manifest(sandbox, "shell-prototype")

        anchor = _screen_page_text(sandbox, manifest, "anchor")
        assert "Auto [value=AUTO]" in anchor
        assert "Home [value=HOME]" in anchor
        assert "Renters [value=RENT]" in anchor
        assert "Umbrella [value=UMB]" in anchor

    def test_validation_attributes_present(self, sandbox):
        from app.agents.tools import file_extract_tools

        path = _upload(sandbox, "shell_prototype.html")
        file_extract_tools._extract_html_sync(path)
        manifest = _manifest(sandbox, "shell-prototype")

        anchor = _screen_page_text(sandbox, manifest, "anchor")
        assert "min=2026-01-01" in anchor

        beacon = _screen_page_text(sandbox, manifest, "beacon")
        assert "pattern=[A-Za-z ]+" in beacon
        assert "minlength=2" in beacon
        assert "maxlength=60" in beacon

    def test_data_goto_target_in_actions(self, sandbox):
        from app.agents.tools import file_extract_tools

        path = _upload(sandbox, "shell_prototype.html")
        file_extract_tools._extract_html_sync(path)
        manifest = _manifest(sandbox, "shell-prototype")

        anchor = _screen_page_text(sandbox, manifest, "anchor")
        assert "## Actions" in anchor
        assert "data-goto=beacon" in anchor

    def test_hidden_message_captured(self, sandbox):
        from app.agents.tools import file_extract_tools

        path = _upload(sandbox, "shell_prototype.html")
        file_extract_tools._extract_html_sync(path)
        manifest = _manifest(sandbox, "shell-prototype")

        anchor = _screen_page_text(sandbox, manifest, "anchor")
        assert "## Hidden states and messages" in anchor
        assert "anchor--error" in anchor
        assert "Effective Date cannot be in the past" in anchor

    def test_image_1_exists_for_every_screen(self, sandbox):
        from app.agents.tools import file_extract_tools

        path = _upload(sandbox, "shell_prototype.html")
        file_extract_tools._extract_html_sync(path)
        manifest = _manifest(sandbox, "shell-prototype")

        for entry in manifest["screens"]:
            page_dir = (
                _doc_dir(sandbox, "shell-prototype") / "pages" / f"{entry['page']:02d}"
            )
            png = page_dir / "image-1.png"
            assert png.is_file(), f"missing screenshot for {entry['id']}"
            assert png.stat().st_size > 0
            assert "@[[image-1.png]]" in (page_dir / "text.md").read_text()

    def test_scripts_index_lists_shell_runtime_without_copying_it(self, sandbox):
        from app.agents.tools import file_extract_tools

        path = _upload(sandbox, "shell_prototype.html")
        file_extract_tools._extract_html_sync(path)
        manifest = _manifest(sandbox, "shell-prototype")

        pages = _all_page_texts(sandbox, manifest)
        index_pages = [p for p in pages if p.startswith("# Scripts index")]
        assert len(index_pages) == 1
        assert "shell_runtime" in index_pages[0]

        # The shell's own source is never copied into a page.
        assert not any(p.startswith("# Script ") for p in pages)
        assert not any("window.__prototype = {" in p for p in pages)


# ---------------------------------------------------------------------------
# b. generic form page
# ---------------------------------------------------------------------------


def test_generic_form_three_screens(sandbox):
    from app.agents.tools import file_extract_tools

    path = _upload(sandbox, "generic_form.html")
    result = file_extract_tools._extract_html_sync(path)

    assert "Materialised" in result
    manifest = _manifest(sandbox, "generic-form")
    ids = sorted(s["id"] for s in manifest["screens"])
    assert ids == ["help-dialog", "step-one", "step-two"]


# ---------------------------------------------------------------------------
# c. a screen a script builds at load
# ---------------------------------------------------------------------------


@requires_chromium
def test_script_built_screen_found_on_browser_route(sandbox):
    from app.agents.tools import file_extract_tools

    path = _upload(sandbox, "dynamic_screen.html")
    file_extract_tools._extract_html_sync(path)
    manifest = _manifest(sandbox, "dynamic-screen")

    assert manifest["rendered_by"] == "chromium"
    ids = [s["id"] for s in manifest["screens"]]
    assert "dynamic-screen" in ids

    dyn = _screen_page_text(sandbox, manifest, "dynamic-screen")
    assert "Note" in dyn
    assert "data-goto=elsewhere" in dyn


# ---------------------------------------------------------------------------
# d. static fallback
# ---------------------------------------------------------------------------


def test_static_fallback_on_launch_failure(sandbox, monkeypatch):
    from app.agents.tools import file_extract_tools, html_extract

    def _boom(source_path):
        raise html_extract.BrowserUnavailable("forced failure for test")

    monkeypatch.setattr(html_extract, "_gather_browser", _boom)

    path = _upload(sandbox, "shell_prototype.html")
    result = file_extract_tools._extract_html_sync(path)

    assert "rendered by static" in result
    assert "static fallback:" in result
    assert "forced failure for test" in result

    manifest = _manifest(sandbox, "shell-prototype")
    assert manifest["rendered_by"] == "static"
    assert manifest["static_reason"] == "forced failure for test"

    # Screens are still found — fixture a's shell screens are all in static markup.
    ids = sorted(s["id"] for s in manifest["screens"])
    assert ids == ["anchor", "beacon", "confirm-dialog", "crimson"]

    # No screenshots on the static route.
    for entry in manifest["screens"]:
        page_dir = (
            _doc_dir(sandbox, "shell-prototype") / "pages" / f"{entry['page']:02d}"
        )
        assert not (page_dir / "image-1.png").exists()
        assert "@[[image-1.png]]" not in (page_dir / "text.md").read_text()


# ---------------------------------------------------------------------------
# e. manifest / shard keys
# ---------------------------------------------------------------------------


def test_manifest_has_every_pdf_manifest_key(sandbox):
    from app.agents.tools import file_extract_tools

    path = _upload(sandbox, "generic_form.html")
    file_extract_tools._extract_html_sync(path)
    manifest = _manifest(sandbox, "generic-form")

    for key in (
        "source",
        "source_sha256",
        "source_format",
        "converted_by",
        "slug",
        "page_count",
        "scale",
        "created_at",
        "pages",
        "shards",
        "shard_basis",
        "totals",
    ):
        assert key in manifest, f"missing PDF-manifest key: {key}"

    assert manifest["source_format"] == "html"
    assert manifest["converted_by"] is None

    for key in ("rendered_by", "static_reason", "screens"):
        assert key in manifest

    assert manifest["shards"], "expected at least one shard"
    for shard in manifest["shards"]:
        for key in (
            "id",
            "slug",
            "format",
            "pages",
            "page_range",
            "est_tokens",
            "source",
            "out",
            "over_budget",
        ):
            assert key in shard, f"missing PDF-shard key: {key}"


# ---------------------------------------------------------------------------
# f. .htm shares the .html format directory
# ---------------------------------------------------------------------------


def test_htm_upload_shares_the_html_format_directory(sandbox):
    from app.agents.tools import file_extract_tools

    path = _upload(sandbox, "generic_form.html", upload_name="generic_form.htm")
    file_extract_tools._extract_html_sync(path)

    assert (_doc_dir(sandbox, "generic-form") / "manifest.json").is_file()
    assert not (sandbox / ".extract" / "htm").exists()

    manifest = _manifest(sandbox, "generic-form")
    assert manifest["source_format"] == "html"
    assert manifest["source"] == "generic_form.htm"


# ---------------------------------------------------------------------------
# g. rebuild only on changed bytes
# ---------------------------------------------------------------------------


def test_rebuilds_only_when_bytes_change(sandbox):
    from app.agents.tools import file_extract_tools

    path = _upload(sandbox, "generic_form.html")
    first = file_extract_tools._extract_html_sync(path)
    assert "Processed:" in first
    assert "(rebuilt)" in first
    sha_before = _manifest(sandbox, "generic-form")["source_sha256"]

    second = file_extract_tools._extract_html_sync(path)
    assert "nothing new to materialise" in second
    assert _manifest(sandbox, "generic-form")["source_sha256"] == sha_before

    upload_path = sandbox / ".uploads" / "generic_form.html"
    upload_path.write_bytes(upload_path.read_bytes() + b"\n<!-- changed -->\n")

    third = file_extract_tools._extract_html_sync(path)
    assert "(rebuilt)" in third
    assert _manifest(sandbox, "generic-form")["source_sha256"] != sha_before


# ---------------------------------------------------------------------------
# h. the async extract_text() entry point
# ---------------------------------------------------------------------------


def test_extract_text_async_entry_returns_receipt(sandbox):
    import asyncio

    from app.agents.tools import file_extract_tools

    path = _upload(sandbox, "generic_form.html")
    result = asyncio.run(file_extract_tools.extract_text(path))

    assert "Materialised" in result
    assert "Screens:" in result
    assert (_doc_dir(sandbox, "generic-form") / "manifest.json").is_file()
