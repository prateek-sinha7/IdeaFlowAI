"""Unit tests for evals.grading.site.pages / views / charts — the render layer.

Covers T7-T11, T13-T18. The escaping, determinism and self-containment tests
here are the ones that make this feature safe to point at real runs: judge
rationales quote agent output, and the agents under test emit HTML documents,
so untrusted markup on these pages is a certainty rather than a risk.
"""

from __future__ import annotations

import pathlib
import re
import shutil

import pytest

from evals.grading import grades
from evals.grading.site import aggregate, charts, model, pages, views

from tests.unit.test_grading_site_model import row, runs_root, simple_stage, write_run  # noqa: F401


def run_html(run) -> str:
    """One run's drill-down panel, as the single report embeds it."""
    return pages.run_panel(run, links=pages.Links())


def stage_html(run, stage) -> str:
    """One stage's section, as it appears inside a run panel."""
    return pages.stage_body(run, stage, links=pages.Links())


def report_html(runs_root) -> str:
    """The whole consolidated report — one document over every run."""
    site = model.discover(runs_root.parent)
    return views.render_report(
        site, {workflow.name: aggregate.build(workflow) for workflow in site.workflows}
    )


# Everything a naive f-string renderer would break or execute.
HOSTILE = "<script>alert(1)</script> </td> </script> & \" ' </html>"


@pytest.fixture
def loaded(runs_root):  # noqa: F811
    """One fully-populated run, rendered from real artifacts."""
    run_dir = write_run(
        runs_root,
        "260730-100000-small",
        stages=[(
            "prototype-build",
            {
                "score": {
                    "results": [
                        row("r1", 90),
                        {"row_id": "r2", "errored": True},
                        {"row_id": "r3", "precheck_passed": None},
                        {"row_id": "r4", "precheck_passed": False},
                        {"row_id": "r5", "expect": "fail", "precheck_passed": False},
                    ],
                    "counts": {"rows": 5, "judged": 1},
                    "scores": {"average_all": 90.0, "median": 90.0, "min": 90.0, "max": 90.0},
                    "dimensions": {"fidelity": {"mean": 90.0, "count": 1},
                                   "a11y": {"mean": 40.0, "count": 1}},
                    "tokens": {"agent": {"in": 10, "out": 20, "total": 30},
                               "judge": {"in": 5, "out": 5, "total": 10},
                               "in": 15, "out": 25, "total": 40},
                    "hashes": {"system_prompt_hash": "sha256:abc123def4567890",
                               "rubric_hash": "sha256:rrr", "dataset_hash": "sha256:ddd"},
                    "warnings": ["a warning worth reading first"],
                    "baseline": {"verdict": "fail", "failures": ["below the floor"]},
                    "recurring_weaknesses": [{"evidence": "cramped nav", "row_ids": ["r1"]}],
                },
                "grade": [{
                    "row_id": "r1",
                    "sub_scores": {"fidelity": 90, "a11y": 40},
                    "rationale": f"the header is {HOSTILE}",
                    "strengths": [f"strength {HOSTILE}"],
                    "weaknesses": [f"weakness {HOSTILE}"],
                    "evidence": {"fidelity": f"quote {HOSTILE}"},
                    "score_caps": {"a11y": {"reported": 60, "capped_to": 40, "weaknesses": 2}},
                }],
                "run": [{"row_id": "r1", "prompt": f"brief {HOSTILE}"}],
            },
        )],
        config={"agent_under_test": {"provider": "anthropic", "model": "opus"},
                "judge": {"provider": "anthropic", "model": "sonnet"},
                "options": {"concurrency": 2, "repeats": 1}},
        findings={"prototype-build": {"r1": {
            "code_score": 70,
            "issues": [f"static {HOSTILE}"],
            "render": {"console_errors": [f"console {HOSTILE}"], "page_errors": [],
                       "nav_results": [{"ok": False, "href": "#a", "expected": "a",
                                        "activated": "b"}]},
            "interactions": {"available": True, "actions": [1], "failures": []},
        }}},
        overrides={"judge_model": "haiku"},
        src={"r1": {"prototype.html": f"<html><body>{HOSTILE}</body></html>",
                    "spec.md": f"# Spec {HOSTILE}"}},
    )
    return model.load_run(run_dir, "prototype")


# ── T9: escaping ──────────────────────────────────────────────────────────


def test_esc_escapes_every_dangerous_character():
    assert pages.esc("<b>&\"'") == "&lt;b&gt;&amp;&quot;&#x27;"


def test_esc_renders_absent_values_as_a_dash():
    assert pages.esc(None) == pages.DASH


def test_hostile_model_text_never_reaches_the_page_as_markup(loaded):
    """The failure mode the reference snippet has: unescaped model output."""
    html = stage_html(loaded, loaded.stages[0])
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "the header is &lt;script&gt;" in html


@pytest.mark.parametrize(
    "needle",
    ["brief &lt;script&gt;", "strength &lt;script&gt;", "weakness &lt;script&gt;",
     "quote &lt;script&gt;", "static &lt;script&gt;", "console &lt;script&gt;"],
)
def test_every_text_surface_is_escaped(loaded, needle):
    html = stage_html(loaded, loaded.stages[0])
    assert needle in html


def test_a_deliverable_of_raw_html_is_shown_as_source_not_injected(loaded):
    html = stage_html(loaded, loaded.stages[0])
    assert "<html><body><script>alert(1)" not in html
    assert "&lt;html&gt;&lt;body&gt;" in html


def test_inlined_json_cannot_close_its_own_script_block():
    block = pages.json_block("data", {"text": "</script><script>alert(1)</script>"})
    assert "</script><script>" not in block
    assert "<\\/script>" in block


def test_no_literal_none_reaches_the_page(loaded):
    html = run_html(loaded)
    assert ">None<" not in html
    assert '"None"' not in html


# ── T9: self-containment and sandboxing ───────────────────────────────────


def test_pages_request_nothing_external(runs_root):  # noqa: F811
    write_run(runs_root, "260730-100000-small", stages=[simple_stage("s-a", [row("r1", 90)])])
    for html in (report_html(runs_root),):
        assert "fetch(" not in html
        assert "XMLHttpRequest" not in html
        assert not re.search(r'(src|href)="https?://', html)
        assert not re.search(r'(src|href)="//', html)


def test_every_preview_iframe_is_sandboxed_without_scripts(loaded):
    html = stage_html(loaded, loaded.stages[0])
    frames = re.findall(r"<iframe[^>]*>", html)
    assert frames, "the fixture has an html deliverable, so it must render a preview"
    for frame in frames:
        assert "sandbox" in frame
        assert "allow-scripts" not in frame
        assert "allow-same-origin" not in frame


# ── T9: determinism ───────────────────────────────────────────────────────


def test_rendering_twice_is_byte_identical(loaded, runs_root):  # noqa: F811
    assert run_html(loaded) == run_html(loaded)
    assert report_html(runs_root) == report_html(runs_root)


def test_pages_carry_no_render_timestamp(runs_root):  # noqa: F811
    """A timestamp would break determinism, and any diff-based review of output."""
    write_run(runs_root, "260730-100000-small", stages=[simple_stage("s-a", [row("r1", 90)])])
    html = report_html(runs_root)
    assert "generated at" not in html.lower()
    assert not re.search(r"20\d\d-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+", html)


def test_no_score_arithmetic_is_shipped_to_javascript():
    """Boundary rule B4: JS sorts and filters; it never computes a grade."""
    from evals.grading.site import assets

    assert "0.7" not in assets.JS
    assert "blended" not in assets.JS.lower()
    assert "letter_grade" not in assets.JS


# ── T8: the run page ──────────────────────────────────────────────────────


def test_run_page_grade_matches_compute_overall(loaded):
    html = run_html(loaded)
    overall = grades.compute_overall(loaded.run_dir)
    assert f"{overall['score']:.1f}" in html
    assert f">{overall['grade']}<" in html


def test_run_page_states_when_cells_failed_outright(loaded):
    html = run_html(loaded)
    assert "failed outright" in html


def test_run_page_warns_when_overrides_broke_reproducibility(loaded):
    html = run_html(loaded)
    assert "diverged from its config" in html
    assert "judge_model=haiku" in html


def test_a_run_with_no_grade_says_so_instead_of_inventing_one(runs_root):  # noqa: F811
    run_dir = write_run(runs_root, "260730-100000-small",
                        stages=[simple_stage("s-a", [row("r1", score=None)])])
    html = run_html(model.load_run(run_dir, "prototype"))
    assert "No grade" in html
    assert "none has been invented" in html


def test_run_panel_gives_every_phase_its_own_tab(loaded):
    html = run_html(loaded)
    assert 'data-phasetab="prototype_build"' in html
    assert 'data-phasepanel="prototype_build"' in html
    assert 'id="stage-prototype_build-260730-100000-small"' in html
    assert 'data-phasescope="260730-100000-small"' in html


def test_the_run_panel_is_ordered_provenance_phases_rows_then_detail(loaded):
    """The layout is the point: what produced the numbers, then the numbers."""
    html = run_html(loaded)
    assert (html.index("<h2>Provenance</h2>")
            < html.index("<h2>Phase scores</h2>")
            < html.index("<h2>Rows</h2>")
            < html.index("<h2>Phase detail</h2>"))


def test_phase_tabs_carry_an_issue_count(loaded):
    html = run_html(loaded)
    assert 'data-phasetab="prototype_build"' in html
    assert 'class="pill' in html.split('data-phasetab="prototype_build"')[1][:200]


# ── T10: the stage page ───────────────────────────────────────────────────


def test_stage_page_puts_warnings_above_the_numbers(loaded):
    html = stage_html(loaded, loaded.stages[0])
    assert html.index("a warning worth reading first") < html.index("Dimensions")


def test_stage_page_shows_the_baseline_failure(loaded):
    html = stage_html(loaded, loaded.stages[0])
    assert "below the floor" in html


def test_stage_page_orders_dimensions_worst_first(loaded):
    html = stage_html(loaded, loaded.stages[0])
    assert html.index("<code>a11y</code>") < html.index("<code>fidelity</code>")


def test_row_detail_carries_every_field(loaded):
    html = stage_html(loaded, loaded.stages[0])
    assert "Rationale" in html
    assert "Score reductions" in html
    assert "60" in html and "40" in html          # reduced from -> to
    assert "Evidence" in html
    assert "Code track" in html
    assert "dead nav" in html


@pytest.mark.parametrize(
    ("row_id", "expected"),
    [("r2", "dispatch errored"), ("r3", "never dispatched"), ("r5", "negative test")],
)
def test_row_notes_explain_a_missing_score(loaded, row_id, expected):
    html = stage_html(loaded, loaded.stages[0])
    assert expected in html


def test_rows_carry_filter_flags_and_a_search_haystack(loaded):
    html = stage_html(loaded, loaded.stages[0])
    assert 'data-flags="failed"' in html
    assert "negative" in html
    assert "data-search=" in html
    assert "capped" in html


def test_rows_are_expandable_and_deep_linkable(loaded):
    html = stage_html(loaded, loaded.stages[0])
    assert 'data-expand="r1"' in html
    assert 'id="detail-r1"' in html


# ── T11: deliverables ─────────────────────────────────────────────────────


def test_markdown_deliverables_render_as_escaped_source(loaded):
    html = stage_html(loaded, loaded.stages[0])
    assert "# Spec &lt;script&gt;" in html


def test_a_row_without_deliverables_says_so(runs_root):  # noqa: F811
    run_dir = write_run(runs_root, "260730-100000-small",
                        stages=[simple_stage("s-a", [row("r1", 90)])])
    run = model.load_run(run_dir, "prototype")
    html = stage_html(run, run.stages[0])
    assert "No deliverable was captured" in html


# ── T16: the matrix ───────────────────────────────────────────────────────


def test_matrix_distinguishes_the_four_zero_scoring_kinds(loaded):
    html = run_html(loaded)
    assert pages.KIND_GLYPH[model.KIND_ERRORED] in html
    assert pages.KIND_GLYPH[model.KIND_BROKEN_CHAIN] in html
    assert pages.KIND_GLYPH[model.KIND_PRECHECK_FAIL] in html
    assert "upstream broke" in html


def test_matrix_cells_link_to_the_expanded_row(loaded):
    html = run_html(loaded)
    assert "#row=r1" in html


def test_a_missing_pair_renders_as_not_applicable(runs_root):  # noqa: F811
    """A stage that never saw a row shows a dash, never a zero."""
    run_dir = write_run(runs_root, "260730-100000-small", stages=[
        simple_stage("s-a", [row("r1", 90), row("r2", 80)]),
        simple_stage("s-b", [row("r1", 60)]),
    ])
    html = run_html(model.load_run(run_dir, "prototype"))
    rows_table = html[html.index("<h2>Rows</h2>"):html.index("<h2>Phase detail</h2>")]
    assert f'<span class="muted">{pages.DASH}</span>' in rows_table


# ── T14: charts ───────────────────────────────────────────────────────────


def test_charts_emit_well_formed_svg():
    svg = charts.line_chart([("a", 90.0), ("b", 70.0)], label="test")
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert 'aria-label="test"' in svg


@pytest.mark.parametrize(
    "points",
    [[], [("only", 90.0)], [("a", 50.0), ("b", 50.0)], [("a", None), ("b", 80.0)]],
)
def test_charts_survive_degenerate_input(points):
    result = charts.line_chart(points, label="test")
    assert result  # a message or an svg, never an exception


def test_every_plotted_value_is_also_available_as_text():
    svg = charts.line_chart([("run-a", 87.5)], label="test")
    assert "<title>" in svg and "87.5" in svg
    bars = charts.bar_chart([("fidelity", 42.0)], label="dims")
    assert "42.0" in bars


def test_band_track_uses_the_real_grade_bands():
    track = charts.band_track(85.0, grades.GRADE_BANDS)
    for _, letter in grades.GRADE_BANDS:
        assert f">{letter}<" in track
    assert "85.0" in track


def test_charts_bake_in_no_colours():
    """Themeable means variables, not hex — the page decides light or dark."""
    svg = charts.line_chart([("a", 90.0)], label="t") + charts.bar_chart([("a", 9.0)], label="t")
    assert not re.search(r"#[0-9a-fA-F]{6}", svg)


def test_band_class_matches_the_score_bands():
    assert charts.band_class(95) == "high"
    assert charts.band_class(75) == "mid"
    assert charts.band_class(20) == "low"
    assert charts.band_class(None) == "flat"


# ── T13, T15, T17, T18: the dashboard ─────────────────────────────────────


def _dashboard(runs_root):  # noqa: F811
    return report_html(runs_root)


def test_dashboard_lists_every_run_and_badges_the_excluded(runs_root):  # noqa: F811
    write_run(runs_root, "260730-100000-small", stages=[simple_stage("s-a", [row("r1", 90)])])
    write_run(runs_root, "golden-mission-control",
              stages=[simple_stage("s-a", [row("r1", 100)])])
    write_run(runs_root, "260729-100000-small-copy",
              stages=[simple_stage("s-a", [row("r1", 10)])])
    html = _dashboard(runs_root)

    assert "260730-100000-small" in html
    assert "golden-mission-control" in html
    assert 'class="badge reference"' in html
    assert 'class="badge copy"' in html
    assert "show excluded only" in html


def test_dashboard_names_an_unreadable_folder(runs_root):  # noqa: F811
    write_run(runs_root, "260730-100000-small", stages=[simple_stage("s-a", [row("r1", 90)])])
    broken = runs_root / "260730-110000-small"
    broken.mkdir(parents=True)
    (broken / "run_summary.json").write_text("{oops", encoding="utf-8")
    html = _dashboard(runs_root)
    assert "Unreadable folders" in html
    assert "260730-110000-small" in html


def test_an_empty_tree_renders_an_empty_state(tmp_path):
    root = tmp_path / ".runs"
    root.mkdir()
    site = model.discover(root)
    html = views.render_report(site, {})
    assert "No runs found" in html


def test_workflow_selector_is_hidden_with_a_single_workflow(runs_root):  # noqa: F811
    write_run(runs_root, "260730-100000-small", stages=[simple_stage("s-a", [row("r1", 90)])])
    html = _dashboard(runs_root)
    assert "<h2>prototype</h2>" not in html


def test_trend_view_draws_references_as_lines_not_points(runs_root):  # noqa: F811
    write_run(runs_root, "260730-100000-small", stages=[simple_stage("s-a", [row("r1", 80)])])
    write_run(runs_root, "260730-110000-small", stages=[simple_stage("s-a", [row("r1", 90)])])
    write_run(runs_root, "golden-mission-control",
              stages=[simple_stage("s-a", [row("r1", 100)])])
    html = _dashboard(runs_root)
    assert "refline" in html
    assert "golden-mission-control" in html
    assert "a target to clear" in html


def test_a_single_run_explains_why_there_is_no_trend(runs_root):  # noqa: F811
    write_run(runs_root, "260730-100000-small", stages=[simple_stage("s-a", [row("r1", 90)])])
    html = _dashboard(runs_root)
    assert "a line needs two points" in html


def test_prompt_view_reports_a_small_delta_as_noise_not_improvement(runs_root):  # noqa: F811
    for name, prompt_hash, score in [
        ("260730-100000-small", "sha256:aaa", 85.0),
        ("260730-110000-small", "sha256:aaa", 85.4),
        ("260730-120000-small", "sha256:bbb", 85.2),
    ]:
        write_run(
            runs_root, name,
            stages=[simple_stage("s-a", [row("r1", score)], scores={"average_all": score},
                                 hashes={"system_prompt_hash": prompt_hash})],
            created_at=f"2026-07-30T{name[7:9]}:00:00",
            prompts={"s-a": f"prompt {prompt_hash}"},
        )
    html = _dashboard(runs_root)
    assert "within noise" in html
    assert "noise band" in html or "run-to-run noise" in html


def test_prompt_view_diffs_two_captured_prompts(runs_root):  # noqa: F811
    from evals.grading import artifacts

    for name, text in [
        ("260730-100000-small", "line one\nline two\n"),
        ("260730-110000-small", "line one\nline two CHANGED\n"),
    ]:
        write_run(
            runs_root, name,
            stages=[simple_stage("s-a", [row("r1", 90)],
                                 hashes={"system_prompt_hash":
                                         artifacts.compute_system_prompt_hash(text)})],
            created_at=f"2026-07-30T{name[7:9]}:00:00",
            prompts={"s-a": text},
        )
    html = _dashboard(runs_root)
    assert "What changed between versions" in html
    assert "CHANGED" in html
    assert 'class="add"' in html or 'class="del"' in html


def test_the_diff_opens_on_oldest_to_newest(runs_root):  # noqa: F811
    """Defaulting both selects to one version would open on an empty panel."""
    from evals.grading import artifacts

    for name, text in [
        ("260730-100000-small", "before\n"),
        ("260730-110000-small", "after\n"),
    ]:
        write_run(
            runs_root, name,
            stages=[simple_stage("s-a", [row("r1", 90)],
                                 hashes={"system_prompt_hash":
                                         artifacts.compute_system_prompt_hash(text)})],
            created_at=f"2026-07-30T{name[7:9]}:00:00",
            prompts={"s-a": text},
        )
    html = _dashboard(runs_root)
    selected = re.findall(r'<option value="(\w+)" selected>', html)
    assert len(selected) == 2
    assert selected[0] != selected[1]


def test_a_captured_prompt_that_does_not_hash_to_the_version_is_refused(runs_root):  # noqa: F811
    """A folder can hold a prompt whose hash is not the one its rows recorded.

    Showing it anyway would present two unrelated prompts as "what changed
    between these versions" — a confident, wrong answer.
    """
    write_run(
        runs_root, "260730-100000-small",
        stages=[simple_stage("s-a", [row("r1", 90)],
                             hashes={"system_prompt_hash": "sha256:notthetextshash"})],
        prompts={"s-a": "some prompt text that hashes to something else"},
    )
    html = _dashboard(runs_root)
    assert "No captured prompt" in html
    assert "rows recorded no hash" in html or "predates prompt capture" in html


def test_a_version_without_a_captured_prompt_disables_the_diff_with_a_reason(runs_root):  # noqa: F811
    write_run(runs_root, "260730-100000-small",
              stages=[simple_stage("s-a", [row("r1", 90)],
                                   hashes={"system_prompt_hash": "sha256:aaa"})])
    html = _dashboard(runs_root)
    assert "No captured prompt" in html
    assert "predates prompt capture" in html


def test_dimension_heatmap_is_worst_first(runs_root):  # noqa: F811
    write_run(runs_root, "260730-100000-small", stages=[
        simple_stage("s-a", [row("r1", 90)],
                     dimensions={"fidelity": {"mean": 90.0}, "a11y": {"mean": 40.0}}),
    ])
    html = _dashboard(runs_root)
    assert html.index("<code>a11y</code>") < html.index("<code>fidelity</code>")


def test_cost_view_splits_agent_and_judge_spend(runs_root):  # noqa: F811
    write_run(runs_root, "260730-100000-small", stages=[
        simple_stage("s-a", [row("r1", 90)],
                     tokens={"agent": {"total": 5000}, "judge": {"total": 1200}}),
    ])
    html = _dashboard(runs_root)
    assert "5.0k" in html
    assert "1.2k" in html


def test_code_health_shows_what_was_tried_not_just_what_failed(runs_root):  # noqa: F811
    write_run(
        runs_root, "260730-100000-small",
        stages=[simple_stage("s-a", [row("r1", 90)])],
        findings={"s-a": {"r1": {"code_score": 80, "interactions": {
            "available": True, "actions": [1, 2, 3], "failures": [{"action": "click"}]}}}},
    )
    html = _dashboard(runs_root)
    assert "1 / 4" in html
    assert "nothing was clickable" in html


def test_dashboard_is_deterministic(runs_root):  # noqa: F811
    write_run(runs_root, "260730-100000-small", stages=[simple_stage("s-a", [row("r1", 90)])])
    assert _dashboard(runs_root) == _dashboard(runs_root)


# ── column sorting (the JS the report actually ships) ─────────────────────


def test_sorting_never_uses_parsefloat():
    """The regression guard for a silently dead column.

    `parseFloat('2026-07-30T15:48:05Z')` is 2026, so every timestamp in a
    column compared equal and the "started" column never sorted. Numeric
    detection must be strict about the whole string.
    """
    from evals.grading.site import assets

    code = "\n".join(
        line for line in assets.JS.splitlines() if not line.strip().startswith("//")
    )
    assert "parseFloat(" not in code, "sorting must not use parseFloat — see asNumber()"
    assert "function asNumber" in assets.JS


def test_the_started_column_emits_a_sortable_timestamp(runs_root):  # noqa: F811
    write_run(runs_root, "260730-100000-small",
              stages=[simple_stage("s-a", [row("r1", 90)])],
              created_at="2026-07-30T10:00:00")
    html = report_html(runs_root)
    assert 'data-sort="2026-07-30T10:00:00"' in html


def test_a_run_without_a_start_time_sorts_as_missing(runs_root):  # noqa: F811
    write_run(runs_root, "260730-100000-small",
              stages=[simple_stage("s-a", [row("r1", 90)])], created_at=None)
    html = report_html(runs_root)
    assert 'data-sort=""' in html


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_shipped_sort_comparator_behaves(tmp_path):
    """Runs the comparator from assets.py in node — the real logic, not a copy."""
    import subprocess

    from evals.grading.site import assets

    script = pathlib.Path(__file__).with_name("test_grading_site_sorting.js")
    assets_path = pathlib.Path(assets.__file__)
    result = subprocess.run(
        ["node", str(script), str(assets_path)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "passed" in result.stdout


# ── chart labels must not be clipped ──────────────────────────────────────


def test_bar_chart_labels_are_never_clipped_off_canvas():
    """A fixed gutter cut `design_system_coherence` down to "herence" on screen."""
    svg = charts.bar_chart(
        [("design_system_coherence", 93.0), ("a11y", 40.0)], label="dims"
    )
    xs = [float(x) for x in re.findall(r'<text x="([\d.]+)"', svg)]
    assert min(xs) > 0, "a label was positioned off the left of the canvas"
    assert max(xs) < charts.WIDTH, "a value ran off the right of the canvas"


def test_a_long_label_is_ellipsised_and_keeps_its_full_name_in_a_title():
    svg = charts.bar_chart([("a_very_long_dimension_name_indeed", 50.0)], label="dims")
    assert "…" in svg
    assert "<title>a_very_long_dimension_name_indeed" in svg


def test_phase_tabs_show_problems_and_strengths_separately(loaded):
    html = run_html(loaded)
    tab = html.split('data-phasetab="prototype_build"')[1][:400]
    assert 'class="tabcount"' in tab
    assert tab.count('class="pill') >= 2


def test_the_phase_detail_tables_are_separate_and_counted(loaded):
    html = stage_html(loaded, loaded.stages[0])
    for title in ("Weaknesses", "Code findings", "Strengths"):
        assert f"{title}<span" in html.replace(" ", "") or title in html
    assert 'class="sechead"' in html


def test_row_detail_no_longer_repeats_the_grouped_lists(loaded):
    """They are in the phase tables now; repeating them per row was the mess."""
    html = stage_html(loaded, loaded.stages[0])
    assert "<h3>Strengths</h3>" not in html
    assert "<h3>Weaknesses</h3>" not in html
