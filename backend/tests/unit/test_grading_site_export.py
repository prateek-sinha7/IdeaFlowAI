"""Unit tests for evals.grading.site.export — one run as one shareable file.

The load-bearing test here is fidelity: the export and the run page are built
from the same section builders, and a test asserts they report the same grade,
the same phase table and the same row scores. Two renderers that could
disagree about a score would be a correctness bug, not a cosmetic one.
"""

from __future__ import annotations

import re

import pytest

from evals.grading import grades
from evals.grading.site import export, model, pages

from tests.unit.test_grading_site_model import row, runs_root, simple_stage, write_run  # noqa: F401


@pytest.fixture
def run_dir(runs_root):  # noqa: F811
    return write_run(
        runs_root,
        "260730-100000-small",
        stages=[
            simple_stage("prototype-build", [row("r1", 90), row("r2", 70)]),
            simple_stage("prototype-validate", [row("r1", 85)]),
        ],
        src={"r1": {"prototype.html": "<html><body><h1>hello</h1></body></html>"}},
        findings={"prototype-build": {"r1": {"code_score": 80}}},
    )


def test_export_writes_a_single_file_next_to_the_reports(run_dir):
    path = export.export_run(run_dir)
    assert path.name == "260730-100000-small.export.html"
    assert path.parent.name == "reports"
    assert path.read_text(encoding="utf-8").startswith("<!doctype html>")


def _section(html: str, heading: str) -> str:
    """The one `<section>` under a given heading — the unit both pages share."""
    start = html.index(f"<h2>{heading}</h2>")
    return html[start:html.index("</section>", start)]


def _numbers(html: str) -> list[str]:
    return re.findall(r"[\d]+\.?[\d]*", html)


def test_export_and_run_panel_report_the_same_numbers(run_dir):
    """The fidelity gate: same grade, same phase table, same row scores.

    The export legitimately carries more than a run panel — every stage body is
    inlined into it — so this compares the sections the two genuinely share,
    not the raw text.
    """
    run = model.load_run(run_dir, "prototype")
    site_html = pages.run_panel(run, links=pages.Links())
    export_html = export.render_export(run)
    overall = grades.compute_overall(run_dir)

    for needle in (f"{overall['score']:.1f}", f">{overall['grade']}<"):
        assert needle in site_html
        assert needle in export_html

    assert _numbers(_section(site_html, "Phase scores")) == _numbers(
        _section(export_html, "Phase scores")
    )
    assert _numbers(_section(site_html, "Rows")) == _numbers(
        _section(export_html, "Rows")
    )


def test_export_row_scores_match_the_stage_section(run_dir):
    """Every row's judge/code/combined value is the same in both renderings."""
    run = model.load_run(run_dir, "prototype")
    stage = run.stages[0]
    site_rows = _numbers(_section(pages.stage_body(run, stage, links=pages.Links()), "Rows"))
    # The export's first "Rows" is the run-level overview; the stage's own rows
    # table is inside its panel, so slice from the panel div — not the tab
    # button of the same name, which sits earlier in the document.
    export_html = export.render_export(run)
    panel = re.search(
        rf'<div class="tabpanel[^"]*" data-tab="{stage.agent_token}"', export_html
    )
    assert panel, "the export must carry a panel for every stage"
    export_rows = _numbers(_section(export_html[panel.start():], "Rows"))
    assert site_rows == export_rows


def test_export_is_self_contained(run_dir):
    html = export.render_export(model.load_run(run_dir, "prototype"))
    assert "fetch(" not in html
    assert "XMLHttpRequest" not in html
    assert not re.search(r'(src|href)="https?://', html)
    # No relative file references either: this file travels alone.
    assert 'src="../src/' not in html


def test_export_inlines_previews_as_sandboxed_srcdoc(run_dir):
    html = export.render_export(model.load_run(run_dir, "prototype"))
    frames = re.findall(r"<iframe[^>]*>", html)
    assert frames
    for frame in frames:
        assert "srcdoc=" in frame
        assert "sandbox" in frame
        assert "allow-scripts" not in frame
    assert "&lt;h1&gt;hello&lt;/h1&gt;" in html


def test_an_over_budget_preview_becomes_a_labelled_placeholder(run_dir):
    html = export.render_export(model.load_run(run_dir, "prototype"), max_bytes=10)
    assert "did not fit the export's size budget" in html
    assert "prototype.html" in html
    assert "were not inlined" in html
    assert "srcdoc=" not in html


def test_the_budget_is_honoured(run_dir):
    html = export.render_export(model.load_run(run_dir, "prototype"), max_bytes=10)
    # The shell is fixed-size; what the budget controls is the inlined payload.
    assert "<h1>hello</h1>" not in html


def test_export_discloses_that_it_carries_the_prompts(run_dir):
    html = export.render_export(model.load_run(run_dir, "prototype"))
    assert "captured system prompts" in html


def test_export_navigates_in_page_rather_than_between_files(run_dir):
    html = export.render_export(model.load_run(run_dir, "prototype"))
    assert 'data-tab="prototype_build"' in html
    assert ".html\"" not in html.split("<body>")[1]


def test_export_marks_the_transcript_as_unavailable_rather_than_broken(runs_root):  # noqa: F811
    from evals.grading import artifacts

    folder = write_run(runs_root, "260730-100000-small",
                       stages=[simple_stage("s-a", [row("r1", 90)])])
    log = artifacts.log_path(folder, "s_a", "r1")
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("transcript", encoding="utf-8")

    html = export.render_export(model.load_run(folder, "prototype"))
    assert "not available from this standalone file" in html
    assert "logs/r1/s_a.log" not in html


def test_export_is_deterministic(run_dir):
    run = model.load_run(run_dir, "prototype")
    assert export.render_export(run) == export.render_export(run)
