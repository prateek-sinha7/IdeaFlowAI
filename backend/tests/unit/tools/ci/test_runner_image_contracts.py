"""
Runner-image contract (F-22): no workflow may run on a floating label.

``ubuntu-latest`` re-points to a new image on GitHub's schedule, which changes the
preinstalled jq / AWS CLI / gh / docker versions under a workflow with no diff in
this repository. Every ``runs-on`` must therefore equal the exact label recorded in
``backend/tools/ci/pin_authority.py`` (``runner_image``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from tools.ci.pin_authority import get_authority

REPO_ROOT = Path(__file__).resolve().parents[5]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
WORKFLOW_FILES = sorted(WORKFLOWS_DIR.glob("*.yml"))


def _runs_on_violations(
    name: str, workflow: dict[Any, Any], expected: str
) -> list[str]:
    """Jobs in ``workflow`` whose ``runs-on`` is not exactly ``expected``.

    Jobs without ``runs-on`` are reusable-workflow calls (``uses:``) and run on the
    callee's runner, so they are skipped.
    """
    violations: list[str] = []
    for job_id, job in (workflow.get("jobs") or {}).items():
        if not isinstance(job, dict) or "runs-on" not in job:
            continue
        runs_on = job["runs-on"]
        if runs_on != expected:
            violations.append(f"{name}:{job_id} runs-on={runs_on!r}")
    return violations


def test_workflow_files_are_discovered_when_scanning_runners() -> None:
    """Guard against the parametrised scan silently covering nothing."""
    assert WORKFLOW_FILES, "no workflow files found"


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=lambda p: p.name)
def test_every_job_runs_on_the_authority_runner_image_when_it_declares_a_label(
    path: Path,
) -> None:
    """A list, an expression or any other label is a violation."""
    workflow = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    expected = get_authority().runner_image
    assert _runs_on_violations(path.name, workflow, expected) == []


def test_no_workflow_or_composite_mentions_floating_runner_label_when_scanned() -> None:
    """Belt and braces: the literal ``ubuntu-latest`` appears nowhere in workflows."""
    offenders = [
        p.name
        for p in WORKFLOW_FILES
        if "ubuntu-latest" in p.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_runs_on_helper_flags_floating_label_when_ubuntu_latest() -> None:
    """Self-test: a floating label is a tested failure."""
    workflow = {"jobs": {"build": {"runs-on": "ubuntu-latest"}}}
    assert _runs_on_violations("x.yml", workflow, "ubuntu-24.04") == [
        "x.yml:build runs-on='ubuntu-latest'"
    ]


def test_runs_on_helper_flags_list_and_expression_when_label_is_not_a_string() -> None:
    """Self-test: a list or an expression cannot be proven pinned."""
    workflow = {
        "jobs": {
            "a": {"runs-on": ["ubuntu-24.04"]},
            "b": {"runs-on": "${{ matrix.os }}"},
        }
    }
    assert len(_runs_on_violations("x.yml", workflow, "ubuntu-24.04")) == 2


def test_runs_on_helper_accepts_pinned_label_when_ubuntu_24_04() -> None:
    """Self-test: the pinned label and reusable-workflow calls pass."""
    workflow = {
        "jobs": {
            "build": {"runs-on": "ubuntu-24.04"},
            "gate": {"uses": "./.github/workflows/ci.yml"},
        }
    }
    assert _runs_on_violations("x.yml", workflow, "ubuntu-24.04") == []
