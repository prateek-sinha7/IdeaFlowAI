"""Unit tests for evals.grading.code_grader — the free, deterministic track.

Offline only: no model, no network, no Chromium. Covers the structural verdict on
a good and a broken document, per-row findings over a synthetic run folder, the
replay against the real committed example-run, and the two hard boundaries —
render is opt-in, and this module never imports judge.py.
"""

from __future__ import annotations

import ast
import shutil
from pathlib import Path

from evals.grading import artifacts, code_grader

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


def _write_build_stage(run_dir: Path, rows: list[dict]) -> None:
    """Write a fake prototype-build run artifact through artifacts.py."""
    artifacts.write_stage(
        run_dir,
        code_grader.BUILD_AGENT_TOKEN,
        runs=rows,
        grades=[],
        score={},
        output={},
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

    result = code_grader.grade_run_folder("260729-000000-demo", workflow_dir=tmp_path)

    assert result["status"] == "graded"
    assert set(result["findings"]) == {"billing_console", "clinic_portal"}
    assert result["findings"]["billing_console"]["ok"] is True
    assert result["findings"]["clinic_portal"]["ok"] is False
    assert result["rows_checked"] == 2
    assert result["rows_ok"] == 1


def test_grade_run_folder_writes_findings_into_the_same_run_folder(tmp_path):
    """compare.py reads the findings as another per-row signal, so they persist."""
    run_dir = artifacts.run_folder("260729-000000-demo", workflow_dir=tmp_path)
    _write_build_stage(run_dir, [{"row_id": "billing_console", "response": GOOD_HTML}])

    code_grader.grade_run_folder("260729-000000-demo", workflow_dir=tmp_path)

    written = artifacts.read_stage_artifact(
        run_dir, code_grader.BUILD_AGENT_TOKEN, code_grader.FINDINGS_KIND
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

    assert result["missing"] == ["clinic_portal"]
    assert result["rows_checked"] == 1


def test_grade_run_folder_replays_the_real_example_run(tmp_path):
    """The committed run has only prototype-specify: a clear no-build result."""
    run_dir = tmp_path / artifacts.RUNS_DIR_NAME / "example-run"
    shutil.copytree(EXAMPLE_RUN, run_dir)

    result = code_grader.grade_run_folder("example-run", workflow_dir=tmp_path)

    assert result["status"] == "nothing_to_grade"
    assert result["findings"] == {}
    assert "prototype_build_run.json" in result["missing"][0]
    assert code_grader.BUILD_AGENT_ID in result["reason"]


def test_render_is_off_by_default(tmp_path, monkeypatch):
    """render=False must make no Chromium call at all."""

    def fail(*args, **kwargs):
        raise AssertionError("render_check must not run when render=False")

    monkeypatch.setattr(code_grader.app.agents.render_check, "render_check", fail)
    run_dir = artifacts.run_folder("260729-000000-demo", workflow_dir=tmp_path)
    _write_build_stage(run_dir, [{"row_id": "billing_console", "response": GOOD_HTML}])

    result = code_grader.grade_run_folder("260729-000000-demo", workflow_dir=tmp_path)

    assert "render" not in result["findings"]["billing_console"]


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
