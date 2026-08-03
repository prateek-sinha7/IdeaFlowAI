"""Unit tests for evals.grading.site.builder — consolidation, output, and safety.

The build produces exactly two files for the whole tree — `evals_data.json` and
`report.html` — and nothing per run. Three properties are tested hardest:

- exactly those two files appear, and no per-run page is left behind,
- one unreadable run folder never fails the build, and
- a failing build never fails a grading run, or costs it its markdown report.
  A run that spent real tokens must not be reported as failed because a
  rendering helper raised.
"""

from __future__ import annotations

import json

import pytest

from evals.grading import artifacts, markdown_report
from evals.grading.site import builder, dataset, model

from tests.unit.test_grading_site_model import row, runs_root, simple_stage, write_run  # noqa: F401


@pytest.fixture
def tree(runs_root):  # noqa: F811
    write_run(runs_root, "260730-100000-small",
              stages=[simple_stage("stage-a", [row("r1", 90)])])
    write_run(runs_root, "260730-110000-small",
              stages=[simple_stage("stage-a", [row("r1", 70)])])
    return runs_root.parent


# ── T12: building ─────────────────────────────────────────────────────────


def test_build_writes_one_report_and_one_dataset(tree):
    report = builder.build_site(tree)
    assert report == tree / "report.html"
    assert report.exists()
    assert (tree / dataset.DATASET_NAME).exists()


def test_build_writes_no_per_run_pages(tree):
    """The whole point of the consolidation: nothing lands in a run folder."""
    builder.build_site(tree)
    stray = [path for path in tree.rglob("*.html") if path.parent != tree]
    assert stray == []


def test_the_only_generated_files_are_the_report_and_its_data(tree):
    before = {path for path in tree.rglob("*") if path.is_file()}
    builder.build_site(tree)
    after = {path for path in tree.rglob("*") if path.is_file()}
    assert {path.name for path in after - before} == {"report.html", dataset.DATASET_NAME}


def test_build_reports_its_counts(tree):
    report = builder.build(tree)
    assert report.scanned == 2
    assert report.included == 2
    assert "scanned 2" in report.line()


def test_build_raises_only_when_the_root_is_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        builder.build_site(tmp_path / "nope")


def test_one_unreadable_folder_never_fails_the_build(tree):
    broken = tree / "prototype" / "260730-120000-small"
    broken.mkdir(parents=True)
    (broken / artifacts.RUN_SUMMARY_NAME).write_text("{oops", encoding="utf-8")

    report = builder.build(tree)
    assert report.included == 2
    assert len(report.errors) == 1
    assert "260730-120000-small" in report.errors[0]
    assert report.report.exists()


def test_every_run_appears_in_the_one_report(tree):
    html = builder.build_site(tree).read_text(encoding="utf-8")
    for name in ("260730-100000-small", "260730-110000-small"):
        assert f'data-tab="run:{name}"' in html


def test_the_dataset_carries_every_run(tree):
    import json

    builder.build_site(tree)
    data = json.loads((tree / dataset.DATASET_NAME).read_text(encoding="utf-8"))
    assert data["totals"]["runs"] == 2
    ids = {run["dataset_run_id"] for run in data["workflows"][0]["runs"]}
    assert ids == {"260730-100000-small", "260730-110000-small"}


def test_pages_written_by_the_superseded_shape_are_removed(tree):
    """A tree built by an older version must not keep serving stale pages."""
    reports = tree / "prototype" / "260730-100000-small" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "run.html").write_text("stale", encoding="utf-8")
    (reports / "stage_a.html").write_text("stale", encoding="utf-8")
    (tree / "index.html").write_text("stale", encoding="utf-8")

    report = builder.build(tree)
    assert report.removed == 3
    assert not (reports / "run.html").exists()
    assert not (reports / "stage_a.html").exists()
    assert not (tree / "index.html").exists()


# ── T21: the report always covers every run ──────────────────────────────


def test_every_build_refreshes_the_whole_report(tree):
    """One file spans every run, so there is nothing to skip and nothing stale."""
    builder.build_site(tree)
    report = tree / "report.html"
    report.write_text("stale", encoding="utf-8")
    builder.build(tree)
    assert report.read_text(encoding="utf-8") != "stale"


def test_force_is_accepted_and_changes_nothing(tree):
    builder.build_site(tree, force=True)
    first = (tree / "report.html").read_text(encoding="utf-8")
    builder.build_site(tree, force=False)
    assert (tree / "report.html").read_text(encoding="utf-8") == first


def test_output_is_byte_identical_across_builds(tree):
    builder.build_site(tree)
    first = (tree / "report.html").read_text(encoding="utf-8")
    data_first = (tree / dataset.DATASET_NAME).read_text(encoding="utf-8")

    builder.build_site(tree)
    assert (tree / "report.html").read_text(encoding="utf-8") == first
    assert (tree / dataset.DATASET_NAME).read_text(encoding="utf-8") == data_first


# ── T22: the auto-rebuild must never be load-bearing ──────────────────────


def test_rebuild_for_run_refreshes_the_one_report(tree):
    page = builder.rebuild_for_run(tree / "prototype" / "260730-100000-small")
    assert page is not None and page.exists()
    assert page == tree / "report.html"


def test_rebuild_for_run_swallows_every_failure(tree, monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("rendering blew up")

    monkeypatch.setattr(builder, "build", explode)
    assert builder.rebuild_for_run(tree / "prototype" / "260730-100000-small") is None


def test_write_report_still_returns_the_markdown_when_the_site_build_raises(
    tree, monkeypatch
):
    """The invariant: a reporting bug must not fail work that already succeeded."""
    def explode(*args, **kwargs):
        raise RuntimeError("site build blew up")

    monkeypatch.setattr(builder, "build", explode)
    run_dir = tree / "prototype" / "260730-100000-small"
    path = markdown_report.write_report(run_dir)
    assert path.name == "report.md"
    assert path.exists()


def test_write_report_writes_the_markdown_and_refreshes_the_report(tree):
    run_dir = tree / "prototype" / "260730-100000-small"
    markdown_report.write_report(run_dir)
    assert (run_dir / "reports" / "report.md").exists()
    assert (tree / "report.html").exists()
    # …and leaves no HTML beside the markdown.
    assert list((run_dir / "reports").glob("*.html")) == []


def test_a_run_folder_outside_a_runs_tree_still_builds(tmp_path):
    """`rebuild_for_run` is called from paths that may not sit under `.runs/`."""
    folder = tmp_path / "loose" / "260730-100000-small"
    (folder / "artifacts").mkdir(parents=True)
    (folder / artifacts.RUN_SUMMARY_NAME).write_text(
        json.dumps({"dataset_run_id": "260730-100000-small", "status": "completed",
                    "stages": [{"agent_id": "stage-a"}]}),
        encoding="utf-8",
    )
    artifacts.artifact_path(folder, "stage_a", "score").write_text(
        json.dumps({"results": [{"row_id": "r1", "precheck_passed": True, "score": 90}]}),
        encoding="utf-8",
    )
    page = builder.rebuild_for_run(folder)
    assert page is not None and page.exists()


def test_the_runs_root_is_found_from_any_depth(tree):
    """The report lives at `.runs/`, so the build must locate it from a run folder."""
    run_dir = tree / "prototype" / "260730-100000-small"
    assert builder._runs_root_of(run_dir) == tree
