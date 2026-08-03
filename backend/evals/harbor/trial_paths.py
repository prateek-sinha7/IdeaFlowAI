"""Locate the task a trial came from, for the host-side graders.

`model_grade.py` and `spec_judge.py` both need the brief the agent was given and
the vocabulary the code grader used. Both used to hardcode `prototype-specify`,
which was correct while exactly one task existed and silently wrong the moment a
second scenario appeared: mission-control specs would have been graded against
the warehouse-slotting brief, scoring perfectly plausible nonsense.

Harbor names a trial directory `<task>__<hash>`, so the task is recoverable from
the path with no extra flag to pass and nothing to keep in sync.
"""

from __future__ import annotations

import pathlib

HARBOR = pathlib.Path(__file__).resolve().parent


def task_dir(trial: pathlib.Path) -> pathlib.Path:
    """`harbor/<scenario>-<stage>/` for a `jobs/<job>/<trial>/` directory."""
    task = HARBOR / trial.name.split("__")[0]
    if not task.is_dir():
        raise SystemExit(
            f"trial {trial.name!r} names task {task.name!r}, which does not exist. "
            "If the task was renamed, its old jobs cannot be re-graded."
        )
    return task


def trial_of(artifact: pathlib.Path) -> pathlib.Path:
    """The trial directory holding `jobs/<job>/<trial>/artifacts/app/<file>`."""
    return artifact.resolve().parents[2]


def contract(trial: pathlib.Path) -> dict:
    """The scenario contract that graded this trial.

    Read from the task's synced copy rather than from `scenarios/`, so a
    re-grade uses the vocabulary the run actually used even if the scenario has
    been edited since.
    """
    import json

    path = task_dir(trial) / "tests" / "contract.common.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
