"""Backlog.pdf / Backlog.zip packaging for the backlog workflow (backlog_export.py)."""
from __future__ import annotations

import asyncio
import datetime
import io
import json
import zipfile

import agents.capabilities.backlog_export as export
from agents.capabilities.backlog_export import (
    DELIVERABLES,
    build_cover,
    build_html,
    build_zip,
    export_backlog,
)
from app.agents.sandbox import RunSandbox


def _sandbox(tmp_path) -> RunSandbox:
    sb = RunSandbox("u", "r", runs_root=str(tmp_path))
    sb.ensure()
    sb.write("solution.md", "# Solution\n\nThe <script>x</script> clinic portal.\n")
    sb.write("architecture.md", "# Architecture\n\n```mermaid\nflowchart TD\n  A --> B\n```\n")
    sb.write("backlog.md", "# Backlog\n\n## EPIC-01 Sign in\n\n| id | title |\n|---|---|\n| US-01 | Sign in |\n\n"
             "```gherkin\n@US-01\nScenario: Owner signs in\n  Given an owner \"Ann\"\n```\n")
    sb.write("backlog.json", json.dumps({
        "backlog": {"product": "PawCare Clinic Portal", "features": 2, "epics": 3},
        "stories": [{"points": 5, "requirements": [{}, {}]}]}))
    sb.write("synthesis.md", "# not a deliverable")
    return sb


def test_html_has_every_present_document_in_reading_order(tmp_path):
    page, entries = build_html(_sandbox(tmp_path))

    assert page.index('id="solution.md"') < page.index('id="architecture.md"') < page.index('id="backlog.md"')
    assert 'id="api.md"' not in page  # absent file, absent section
    assert "<table>" in page and "US-01" in page
    assert '<pre class="mermaid-src">flowchart TD' in page
    # Agent-written Markdown never injects markup into the page.
    assert "<script>" not in page
    assert "not a deliverable" not in page
    # Gherkin keywords, tags and quoted values are marked for colour.
    assert '<span class="gk-kw">Given</span>' in page and '<span class="gk-tag">@US-01</span>' in page
    # Short id cells stay on one line.
    assert '<td class="nw">US-01</td>' in page


def test_contents_lists_chapters_and_their_sections_with_page_numbers(tmp_path):
    sb = _sandbox(tmp_path)
    _, entries = build_html(sb)
    assert [(lvl, title) for lvl, _hid, title in entries] == [
        (1, "Solution"), (1, "Architecture"), (1, "Backlog"), (2, "EPIC-01 Sign in")]

    # The measuring pass prints a placeholder; the second prints the pages it read.
    first, _ = build_html(sb)
    assert '<span class="p">000</span>' in first
    numbered, _ = build_html(sb, {hid: 7 for _lvl, hid, _t in entries})
    assert '<span class="p">7</span>' in numbered and '<span class="p">000</span>' not in numbered


def test_cover_carries_the_product_and_its_numbers(tmp_path):
    cover = build_cover(_sandbox(tmp_path), datetime.date(2026, 9, 25))

    assert "PawCare Clinic Portal" in cover and "September 25, 2026" in cover
    for number, label in (("2", "Features"), ("3", "Epics"), ("1", "User stories"),
                          ("2", "Requirements"), ("5", "Story points")):
        assert f"<b>{number}</b><span>{label}</span>" in cover


def test_zip_holds_each_deliverable_separately_plus_the_pdf(tmp_path):
    data = build_zip(_sandbox(tmp_path), b"%PDF-1.7 fake")

    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    assert names == ["backlog.md", "backlog.json", "solution.md", "architecture.md", "Backlog.pdf"]
    assert set(names) - {"Backlog.pdf"} <= set(DELIVERABLES)


def test_no_browser_still_writes_the_zip_and_says_why(tmp_path, monkeypatch):
    async def _no_browser(_sandbox):
        raise RuntimeError("Executable doesn't exist")

    monkeypatch.setattr(export, "render_pdf", _no_browser)
    sb = _sandbox(tmp_path)

    note = asyncio.run(export_backlog(sb))

    assert "Backlog.pdf not written" in note
    assert not sb.path_for("Backlog.pdf").exists()
    names = zipfile.ZipFile(sb.path_for("Backlog.zip")).namelist()
    assert "Backlog.pdf" not in names and "backlog.md" in names


def test_the_packaged_binaries_are_kept_out_of_the_run_history(tmp_path, monkeypatch):
    """The commit's binary scan refuses a PDF; both files are rebuilt every final
    assembly, so the sandbox .gitignore lists them — once, however often it runs."""
    async def _no_browser(_sandbox):
        raise RuntimeError("no browser")

    monkeypatch.setattr(export, "render_pdf", _no_browser)
    sb = _sandbox(tmp_path)
    sb.path_for(".gitignore").write_text(".uploads/\n")

    asyncio.run(export_backlog(sb))
    asyncio.run(export_backlog(sb))

    lines = sb.path_for(".gitignore").read_text().splitlines()
    assert lines == [".uploads/", "/Backlog.pdf", "/Backlog.zip"]


def test_the_build_order_is_packaged_and_read_just_before_the_backlog():
    assert "build-order.md" in DELIVERABLES
    chapters = [name for name, _title, _lede in export.PDF_SECTIONS]
    assert chapters.index("build-order.md") == chapters.index("backlog.md") - 1


def test_gaps_are_the_last_pdf_chapter_and_ride_in_the_zip(tmp_path):
    assert [name for name, _t, _l in export.PDF_SECTIONS][-1] == "gaps.md"
    sb = _sandbox(tmp_path)
    sb.write("gaps.md", "# Coverage gaps\n\n| Id | Type |\n|---|---|\n| API-34 | endpoints |\n")
    page, _ = build_html(sb)
    assert page.index('id="backlog.md"') < page.index('id="gaps.md"')
    with zipfile.ZipFile(io.BytesIO(build_zip(sb, None))) as zf:
        assert "gaps.md" in zf.namelist()


def test_without_gaps_there_is_no_gaps_chapter(tmp_path):
    page, _ = build_html(_sandbox(tmp_path))
    assert 'id="gaps.md"' not in page
