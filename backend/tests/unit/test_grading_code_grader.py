"""Unit tests for evals.grading.code_grader — the free, deterministic track.

Offline only: no model, no network, no Chromium. Covers the structural verdict on
a good and a broken document, per-row findings over a synthetic run folder, the
replay against the real committed example-run, and the two hard boundaries —
render is opt-in, and this module never imports judge.py.
"""

from __future__ import annotations

import ast
import shutil

import pytest
from pathlib import Path

from evals.grading import artifacts
from evals.grading.code import code_grader

EXAMPLE_RUN = (
    Path(__file__).resolve().parents[2]
    / "evals/grading/model/workflows/prototype/example-run"
)

GOOD_HTML = """<!doctype html>
<html><body>
<nav>
  <a class="nav-item" href="#/invoices" onclick="navigateTo('#/invoices')">Invoices</a>
  <a class="nav-item" href="#/customers" onclick="navigateTo('#/customers')">Customers</a>
</nav>
<section data-page="invoices" class="is-active"><h1>Invoices</h1></section>
<section data-page="customers"><h1>Customers</h1></section>
<script>
  const routes = { invoices: '#/invoices', customers: '#/customers' };
  function navigateTo(route) { location.hash = route; }
</script>
</body></html>
"""

DANGLING_HTML = """<!doctype html>
<html><body>
<nav>
  <a class="nav-item" href="#/invoices" onclick="navigateTo('#/invoices')">Invoices</a>
  <a class="nav-item" href="#/customers" onclick="navigateTo('#/customers')">Customers</a>
</nav>
<section data-page="customers" class="is-active"><h1>Customers</h1></section>
<script>
  const routes = { customers: '#/customers' };
  function navigateTo(route) { location.hash = route; }
</script>
</body></html>
"""


# The build stage's declaration — the first entry of the graded-stage table.
BUILD = code_grader.GRADED_STAGES[0]


def _write_build_stage(run_dir: Path, rows: list[dict]) -> None:
    """Write a fake prototype-build run artifact through artifacts.py."""
    artifacts.write_stage(
        run_dir,
        BUILD["token"],
        runs=rows,
        grades=[],
        score={},
        output={},
    )


def _build_result(result: dict) -> dict:
    """The build stage's entry out of a grade_run_folder result."""
    return next(
        stage for stage in result["stages"] if stage["agent_id"] == BUILD["agent_id"]
    )


def test_check_html_accepts_a_consistent_document():
    """Routes match sections and handlers are defined -> ok, no issues."""
    verdict = code_grader.check_html(GOOD_HTML)
    assert verdict["ok"] is True
    assert verdict["issues"] == []
    assert set(verdict["inventory"]["sections"]) == {"invoices", "customers"}


def test_check_html_names_a_dangling_nav_route():
    """A nav link with no matching section fails and the issue names the route."""
    verdict = code_grader.check_html(DANGLING_HTML)
    assert verdict["ok"] is False
    assert any("invoices" in issue for issue in verdict["issues"])


def test_grade_run_folder_keys_findings_by_row_id(tmp_path):
    """Each row's HTML is checked and filed under that row's stable id."""
    run_dir = artifacts.run_folder("260729-000000-demo", workflow_dir=tmp_path)
    _write_build_stage(
        run_dir,
        [
            {"row_id": "billing_console", "response": GOOD_HTML},
            {"row_id": "clinic_portal", "response": DANGLING_HTML},
        ],
    )

    # Static-only: this test is about KEYING, not scores. The default now runs
    # the browser checks too (spec 008 T8), which is slower and not what is
    # under test here.
    result = code_grader.grade_run_folder(
        "260729-000000-demo", workflow_dir=tmp_path, render=False, interactions=False
    )

    assert result["status"] == "graded"
    stage = _build_result(result)
    assert set(stage["findings"]) == {"billing_console", "clinic_portal"}
    assert stage["findings"]["billing_console"]["ok"] is True
    assert stage["findings"]["clinic_portal"]["ok"] is False
    assert stage["rows_checked"] == 2
    assert stage["rows_ok"] == 1
    # Every graded row carries the deterministic 0-100 code score, and the
    # clean document outranks the one with a dangling route.
    scores = {row: f["code_score"] for row, f in stage["findings"].items()}
    assert scores["billing_console"] == 100.0
    assert scores["clinic_portal"] < scores["billing_console"]
    assert stage["average_code_score"] is not None


def test_grade_run_folder_writes_findings_into_the_same_run_folder(tmp_path):
    """compare.py reads the findings as another per-row signal, so they persist."""
    run_dir = artifacts.run_folder("260729-000000-demo", workflow_dir=tmp_path)
    _write_build_stage(run_dir, [{"row_id": "billing_console", "response": GOOD_HTML}])

    code_grader.grade_run_folder("260729-000000-demo", workflow_dir=tmp_path)

    written = artifacts.read_stage_artifact(
        run_dir, BUILD["token"], code_grader.FINDINGS_KIND
    )
    assert written["findings"]["billing_console"]["ok"] is True


def test_grade_run_folder_reports_rows_with_no_deliverable(tmp_path):
    """An errored row has no HTML — it is named as missing, never crashed on."""
    run_dir = artifacts.run_folder("260729-000000-demo", workflow_dir=tmp_path)
    _write_build_stage(
        run_dir,
        [
            {"row_id": "billing_console", "response": GOOD_HTML},
            {"row_id": "clinic_portal", "response": ""},
        ],
    )

    result = code_grader.grade_run_folder("260729-000000-demo", workflow_dir=tmp_path)

    stage = _build_result(result)
    assert stage["missing"] == ["clinic_portal"]
    assert stage["rows_checked"] == 1


@pytest.mark.skipif(not EXAMPLE_RUN.exists(), reason="example-run not present")
def test_grade_run_folder_replays_the_real_example_run(tmp_path):
    """The committed run has only prototype-specify: a clear no-build result."""
    run_dir = tmp_path / artifacts.RUNS_DIR_NAME / "example-run"
    shutil.copytree(EXAMPLE_RUN, run_dir)

    result = code_grader.grade_run_folder("example-run", workflow_dir=tmp_path)

    assert result["status"] == "nothing_to_grade"
    assert result["stages"] == []
    assert BUILD["agent_id"] in result["reason"]


def test_render_can_be_turned_off_explicitly(tmp_path, monkeypatch):
    """render=False must make no Chromium call at all.

    The DEFAULT is now True (spec 008 T8): a caller that omitted the flags used
    to grade on `static_check` alone, and since the precheck already requires
    `static_check.ok` that scores ~100 by construction — an inflated code score
    which would then raise the ceiling band and defeat the point of having one.
    Turning it off is still supported; it just has to be asked for.
    """

    def fail(*args, **kwargs):
        raise AssertionError("render_check must not run when render=False")

    monkeypatch.setattr(code_grader.app.agents.render_check, "render_check", fail)
    run_dir = artifacts.run_folder("260729-000000-demo", workflow_dir=tmp_path)
    _write_build_stage(run_dir, [{"row_id": "billing_console", "response": GOOD_HTML}])

    result = code_grader.grade_run_folder(
        "260729-000000-demo", workflow_dir=tmp_path, render=False, interactions=False
    )

    finding = _build_result(result)["findings"]["billing_console"]
    assert "render" not in finding
    assert "interactions" not in finding


def test_compute_code_score_subtracts_named_penalties():
    """The score is the documented arithmetic, not an opinion."""
    clean = {"issues": [], "warnings": []}
    assert code_grader.compute_code_score(clean) == 100.0

    broken = {
        "issues": ["dangling route"],  # -15
        "warnings": ["minor"],  # -3
        "render": {
            "available": True,
            "console_errors": ["boom"],  # -10
            "page_errors": [],
            "nav_results": [{"ok": True}, {"ok": False}],  # -10
            "coverage_errors": [],
        },
        "interactions": {"available": True, "failures": [{"action": "click"}]},  # -10
    }
    assert code_grader.compute_code_score(broken) == 100 - 15 - 3 - 10 - 10 - 10

    # A skipped check subtracts nothing — the score is a lower bound, not a guess.
    skipped = {"issues": [], "warnings": [], "render": {"available": False},
               "interactions": {"available": False}}
    assert code_grader.compute_code_score(skipped) == 100.0


def test_blended_score_prefers_whichever_exists():
    """0.7 judge + 0.3 code where both graded; the survivor where only one did."""
    assert code_grader.blended_score(90, 100) == 90 * 0.7 + 100 * 0.3
    assert code_grader.blended_score(None, 80) == 80
    assert code_grader.blended_score(90, None) == 90


def test_code_grader_does_not_import_judge():
    """The free track must never be hostage to the expensive one."""
    source = Path(code_grader.__file__).read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(f"{node.module or ''}.{alias.name}" for alias in node.names)
    assert not any("judge" in name for name in imported), imported


def test_every_checked_row_gets_a_check_transcript(tmp_path):
    """What was exercised is evidence, logged beside the row's dispatch transcripts."""
    run_dir = artifacts.run_folder("260729-000000-demo", workflow_dir=tmp_path)
    _write_build_stage(run_dir, [{"row_id": "billing_console", "response": GOOD_HTML}])

    # Static-only: the transcript's CONTENT is under test, not the browser checks.
    code_grader.grade_run_folder(
        "260729-000000-demo", workflow_dir=tmp_path, render=False, interactions=False
    )

    log = run_dir / "logs" / "billing_console" / "prototype_build_code_checks.log"
    assert log.exists()
    text = log.read_text(encoding="utf-8")
    assert "code score: 100.0" in text
    assert "[static] ok" in text
    assert "[render] not run" in text
    assert "[interactions] not run" in text


# ── T7/T8: the code-track ceiling band (spec 008-grading-calibration) ─────
#
# The judge may see quality no checker can measure — but not a grade and a half
# of it. A floor gate at code<40 was considered and rejected: the precheck's
# validate hook already fails a row on `not static_check(...).ok`, so a
# structurally broken document never reaches the judge and the gate would be
# dead code. The unguarded region is the MIDDLE of the range.


@pytest.mark.parametrize(
    "judge_score, code_score, expected, why",
    [
        (92, 100, 92 * 0.7 + 100 * 0.3, "clean code track — the golden is unaffected"),
        (92, 85, 92 * 0.7 + 85 * 0.3, "within the band, plain blend"),
        (92, 70, 85.0, "three dead navs bound the judge's opinion"),
        (90, 40, 55.0, "half broken"),
        (90, 0, 15.0, "verifiably broken is an F, not the D (63.0) the raw blend gives"),
    ],
)
def test_blended_score_is_bounded_by_the_code_track(judge_score, code_score, expected, why):
    assert code_grader.blended_score(judge_score, code_score) == pytest.approx(expected), why


def test_the_band_only_ever_lowers_a_score():
    """A `min` by construction — the band can never inflate a cell."""
    for judge_score in range(0, 101, 7):
        for code_score in range(0, 101, 7):
            raw = (1 - code_grader.CODE_WEIGHT) * judge_score + code_grader.CODE_WEIGHT * code_score
            assert code_grader.blended_score(judge_score, code_score) <= raw + 1e-9


def test_the_band_binds_exactly_at_its_edge():
    """Boundary: a blend landing exactly on `code + CODE_BAND` is not reduced."""
    code_score = 70
    ceiling = code_score + code_grader.CODE_BAND
    # Pick the judge score whose raw blend sits exactly on the ceiling.
    judge_score = (ceiling - code_grader.CODE_WEIGHT * code_score) / (1 - code_grader.CODE_WEIGHT)
    assert code_grader.blended_score(judge_score, code_score) == pytest.approx(ceiling)
    assert code_grader.blended_score(judge_score + 5, code_score) == pytest.approx(ceiling)


def test_a_single_track_score_is_never_banded():
    """With only one track there is nothing to bound against."""
    assert code_grader.blended_score(None, 80) == 80
    assert code_grader.blended_score(90, None) == 90


def test_code_track_defaults_to_running_every_check():
    """A caller that forgets the flags must not silently grade on statics alone.

    The precheck already requires `static_check.ok`, so a static-only grade
    scores ~100 by construction — an inflated code score that would then RAISE
    the band's ceiling and defeat the point of having one.
    """
    import inspect

    signature = inspect.signature(code_grader.grade_run_folder)
    assert signature.parameters["render"].default is True
    assert signature.parameters["interactions"].default is True
