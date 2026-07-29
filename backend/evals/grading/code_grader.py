"""Code-track grading: deterministic checks over a built prototype.html.

Reads the HTML from a model-track run folder and reuses the runtime's own
checkers, so grading measures exactly what the pipeline enforces. Free, no judge.
Must never import judge.py — the cheap checks stay independent of the expensive
ones.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import app.agents.render_check
import app.agents.static_check

from evals.grading import artifacts

# The build stage is the only one that produces an HTML deliverable; its graded
# response IS the file the runner read back out of the sandbox.
BUILD_AGENT_ID = "prototype-build"
BUILD_AGENT_TOKEN = "prototype_build"
DELIVERABLE_FILE = "prototype.html"
FINDINGS_KIND = "code_findings"


def grade_run_folder(dataset_run_id: str, *, workflow_dir: Path, render: bool = False) -> dict:
    """Run the deterministic checks over every row's built HTML in one run.

    Reads each row's prototype.html from the same run folder the model track
    produced, keyed by the stable row id, so a finding traces back to the brief
    that produced it. Writes findings alongside the model track's artifacts,
    where compare.py can treat them as another per-row signal.
    """
    run_dir = artifacts.run_folder(dataset_run_id, workflow_dir=Path(workflow_dir))
    result = {
        "dataset_run_id": dataset_run_id,
        "agent_id": BUILD_AGENT_ID,
        "deliverable_file": DELIVERABLE_FILE,
        "render": render,
        "status": "graded",
        "missing": [],
        "rows_checked": 0,
        "rows_ok": 0,
        "findings": {},
    }

    runs = _read_build_runs(run_dir)
    if runs is None:
        result["status"] = "nothing_to_grade"
        result["missing"] = [
            str(artifacts.artifact_path(run_dir, BUILD_AGENT_TOKEN, "run").relative_to(run_dir))
        ]
        # Says WHICH run lacks the stage, not why the stage might not exist:
        # this used to claim "the agent is not yet onboarded", which became
        # false the moment it was, and then misdirected every reader.
        result["reason"] = (
            f"this run folder has no {BUILD_AGENT_ID} stage, so there is no "
            f"{DELIVERABLE_FILE} to check. Run a config whose `agents` include it "
            f"(`grade.sh full`), or point --from-run at a run that did."
        )
        return result

    for row in runs:
        row_id = _row_id(row)
        html = row.get("response") or ""
        if not html.strip():
            result["missing"].append(row_id)
            continue
        finding = check_html(html)
        if render:
            finding["render"] = _render_findings(html)
        result["findings"][row_id] = finding
        result["rows_checked"] += 1
        result["rows_ok"] += int(finding["ok"])

    if not result["findings"]:
        result["status"] = "nothing_to_grade"
        result["reason"] = (
            f"the {BUILD_AGENT_ID} stage ran but no row returned a {DELIVERABLE_FILE} body"
        )
        return result

    _write_findings(run_dir, result)
    return result


def check_html(html: str) -> dict:
    """Structural verdict for one document, via the runtime's static_check.

    Returns ok/issues/warnings plus the parsed inventory. `render_check` is
    opt-in because it needs headless Chromium and degrades to a skip without it.
    """
    checked = app.agents.static_check.static_check(html)
    return {
        "ok": checked.ok,
        "issues": list(checked.issues),
        "warnings": list(checked.warnings),
        "summary": checked.summary(),
        "inventory": {
            "sections": list(checked.sections),
            "nav_hrefs": list(checked.nav_hrefs),
            "route_ids": list(checked.route_ids),
            "note": checked.note,
        },
    }


def _read_build_runs(run_dir: Path) -> list | None:
    """The build stage's run rows, or None when that stage never ran."""
    try:
        return artifacts.read_stage_artifact(run_dir, BUILD_AGENT_TOKEN, "run")
    except FileNotFoundError:
        return None


def _row_id(row: dict) -> str:
    """The stable row id, under either the current or the committed-run key."""
    return row.get("row_id") or row.get("scenario_id") or "unknown"


def _render_findings(html: str) -> dict:
    """Headless-render verdict for one document; a skip when Chromium is absent."""
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / DELIVERABLE_FILE
        path.write_text(html, encoding="utf-8")
        rendered = asyncio.run(app.agents.render_check.render_check(path))
    return {
        "ok": rendered.ok,
        "available": rendered.available,
        "console_errors": list(rendered.console_errors),
        "page_errors": list(rendered.page_errors),
        "coverage_errors": list(rendered.coverage_errors),
        "summary": rendered.summary(),
    }


def _write_findings(run_dir: Path, result: dict) -> None:
    """Write the findings into the model track's own artifacts folder."""
    path = artifacts.artifact_path(run_dir, BUILD_AGENT_TOKEN, FINDINGS_KIND)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
