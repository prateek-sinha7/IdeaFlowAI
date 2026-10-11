"""
Concurrency and matrix contract for ``.github/workflows/cognito-reconcile.yml``.

F-10 / F-29 / F-27. Both jobs in this workflow run ``docker compose exec`` on the
box deploy.yml's ``deploy`` job runs ``docker compose up`` on, so each must sit in
that environment's ``deploy-<env>`` concurrency group. Three ways that broke or
could break, each pinned here:

* a workflow-level ``concurrency:`` block that resolves to the same
  ``deploy-<env>`` name as a job-level group deadlocks the run on manual
  dispatch (GitHub cancels it), so there must be none;
* a group computed from a literal (``'dev'``) instead of ``matrix.environment``
  silently names the wrong environment as soon as the scheduled matrix grows;
* ``retry-cognito-deletions`` must run over the SAME matrix as ``reconcile``
  (byte-identical ``include`` expression) so the two cannot disagree about
  which environments the schedule covers.

Which environments the schedule may name is guarded separately by
``TestScheduledJobsAreNotReviewerGated`` in test_ruleset_workflow_contract.py.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[5]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "cognito-reconcile.yml"

#: The two jobs that command the host.
HOST_JOBS = ("reconcile", "retry-cognito-deletions")

#: The environment a run targets: the matrix leg on a schedule, else the input.
ENVIRONMENT_EXPRESSION = (
    "${{ github.event_name == 'schedule' && matrix.environment || inputs.environment }}"
)

#: Shared with deploy.yml's `deploy` job and provision.yml (`deploy-<env>`).
CONCURRENCY_GROUP = (
    "deploy-${{ github.event_name == 'schedule' && matrix.environment"
    " || inputs.environment }}"
)


def _workflow() -> dict[Any, Any]:
    """The parsed workflow (``on:`` parses as the boolean True key)."""
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8")) or {}


def _job(job_name: str) -> dict[str, Any]:
    """One job's mapping."""
    return _workflow()["jobs"][job_name]


def test_workflow_declares_no_top_level_concurrency_when_jobs_share_deploy_groups() -> (
    None
):
    """A workflow-level group with the jobs' `deploy-<env>` name deadlocks dispatch runs."""
    assert "concurrency" not in _workflow()


@pytest.mark.parametrize("job_name", HOST_JOBS)
def test_job_concurrency_group_tracks_target_environment_when_scheduled_or_dispatched(
    job_name: str,
) -> None:
    """Each job queues in its target environment's deploy group and never cancels a running one."""
    concurrency = _job(job_name)["concurrency"]

    assert concurrency["group"] == CONCURRENCY_GROUP
    assert concurrency["cancel-in-progress"] is False


@pytest.mark.parametrize("job_name", HOST_JOBS)
def test_job_strategy_disables_fail_fast_when_matrix_runs(job_name: str) -> None:
    """One environment's failure must not cancel another environment's leg."""
    assert _job(job_name)["strategy"]["fail-fast"] is False


def test_matrix_include_expressions_are_identical_when_jobs_share_matrix() -> None:
    """retry-cognito-deletions runs over exactly reconcile's matrix."""
    includes = {
        job_name: _job(job_name)["strategy"]["matrix"]["include"]
        for job_name in HOST_JOBS
    }

    assert isinstance(includes["reconcile"], str)
    assert "github.event_name == 'schedule'" in includes["reconcile"]
    assert includes["retry-cognito-deletions"] == includes["reconcile"]
    assert set(_job("reconcile")["strategy"]["matrix"]) == {"include"}
    assert set(_job("retry-cognito-deletions")["strategy"]["matrix"]) == {"include"}


def test_matrix_include_yields_one_leg_when_dispatched() -> None:
    """A manual run must not get an empty matrix; GitHub fails such a job before any step runs."""
    include = _job("reconcile")["strategy"]["matrix"]["include"]
    dispatch_branch = include.split("||", 1)[1]

    assert "fromJson('[]')" not in include
    assert "inputs.environment" in dispatch_branch
    assert '"environment":"{0}"' in dispatch_branch


def _github_format(template: str, *args: str) -> str:
    """GitHub's ``format()``: ``{{``/``}}`` are literal braces, ``{N}`` is an argument.

    Any other lone brace is an invalid format string, which GitHub rejects at
    expression evaluation, so it raises here too.
    """
    out: list[str] = []
    index = 0
    while index < len(template):
        char = template[index]
        pair = template[index : index + 2]
        if pair in ("{{", "}}"):
            out.append(char)
            index += 2
        elif char == "{":
            close = template.index("}", index)
            out.append(args[int(template[index + 1 : close])])
            index = close + 1
        elif char == "}":
            raise ValueError(f"lone '}}' at {index} in {template!r}")
        else:
            out.append(char)
            index += 1
    return "".join(out)


#: The dispatch branch of the shared include: a one-leg matrix from the input.
DISPATCH_BRANCH_PATTERN = re.compile(
    r"\|\|\s*fromJson\(format\('(?P<template>[^']*)',\s*inputs\.environment\)\)\s*}}$"
)

#: The schedule branch stays dev-only (F-14; TestScheduledJobsAreNotReviewerGated).
SCHEDULE_BRANCH = (
    "${{ github.event_name == 'schedule' && fromJson('[{\"environment\":\"dev\"}]')"
)


def _dispatch_environment_options() -> list[str]:
    """The choice options for the ``environment`` workflow_dispatch input."""
    on_block = _workflow()[True]
    return on_block["workflow_dispatch"]["inputs"]["environment"]["options"]


@pytest.mark.parametrize("job_name", HOST_JOBS)
def test_matrix_include_builds_single_input_environment_leg_when_dispatched(
    job_name: str,
) -> None:
    """Every dispatch choice yields exactly one leg naming that environment; schedule stays dev."""
    include = _job(job_name)["strategy"]["matrix"]["include"]
    match = DISPATCH_BRANCH_PATTERN.search(include)
    options = _dispatch_environment_options()

    assert include.startswith(SCHEDULE_BRANCH)
    assert match is not None, include
    assert _job(job_name)["environment"] == ENVIRONMENT_EXPRESSION
    assert options == ["dev", "stage", "prod"]
    for environment in options:
        legs = json.loads(_github_format(match["template"], environment))
        assert legs == [{"environment": environment}]


def test_matrix_include_strings_are_identical_when_compared_across_host_jobs() -> None:
    """The decided dispatch fix lives in both jobs as the same literal string."""
    reconcile, retry = (
        _job(job_name)["strategy"]["matrix"]["include"] for job_name in HOST_JOBS
    )

    assert isinstance(reconcile, str)
    assert isinstance(retry, str)
    assert reconcile == retry
    assert DISPATCH_BRANCH_PATTERN.search(retry) is not None


def test_github_format_rejects_template_when_literal_braces_are_not_doubled() -> None:
    """Pins why the workflow doubles braces: an unescaped `{"environment"...` is invalid."""
    with pytest.raises(ValueError):
        _github_format('[{"environment":"{0}"}]', "dev")


@pytest.mark.parametrize("job_name", HOST_JOBS)
def test_job_environment_uses_matrix_or_input_when_resolved(job_name: str) -> None:
    """`environment:` and the run name resolve the same way the concurrency group does."""
    job = _job(job_name)

    assert job["environment"] == ENVIRONMENT_EXPRESSION
    assert ENVIRONMENT_EXPRESSION in job["name"]
