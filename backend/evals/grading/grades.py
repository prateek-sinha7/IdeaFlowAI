"""The run's blended score, in one place: the arithmetic every report agrees on.

Extracted from `markdown_report` so the HTML dashboard can import the grade
without importing the markdown renderer — and so there is exactly one
implementation of it. A harness whose purpose is catching scoring
inconsistency cannot ship two versions of its own scoring.

`markdown_report` re-exports everything here, so every existing caller and
every existing test keeps working at its current import path.
"""

from __future__ import annotations

from pathlib import Path

from evals.grading import artifacts
from evals.grading.code import code_grader

# The letter scale for the run's headline grade. Descending thresholds on the
# 0-100 blended score; anything below the last band is an F — a failing run.
# A++ is deliberately above the top rubric anchor band (95): it is reachable
# only when the judge found nothing to criticise AND the code track agrees.
GRADE_BANDS = (
    (97, "A++"),
    (93, "A+"),
    (90, "A"),
    (80, "B"),
    (70, "C"),
    (60, "D"),
    (50, "E"),
)
FAIL_GRADE = "F"


def letter_grade(score: float) -> str:
    """Map a 0-100 blended score onto the A++..F scale."""
    for threshold, letter in GRADE_BANDS:
        if score >= threshold:
            return letter
    return FAIL_GRADE


def compute_overall(run_dir: Path) -> dict | None:
    """The run's single blended score over every (stage, row) cell.

    Per cell: the judge score blended with the code score (0.7/0.3) where both
    exist. A cell whose row FAILED — precheck fail, dispatch error, or skipped
    because its upstream broke — scores 0: a chain that stops producing is a
    failing run, not a run with fewer data points. Excluded rather than
    zeroed: negative-test rows (their correctness is the `caught` metric) and
    rows that passed precheck but were never judged (no_judge runs, judge
    infrastructure failures) — those carry no quality information either way.

    Returns {score, grade, counted, failed_cells}, or None when nothing was
    gradable at all.
    """
    run_dir = Path(run_dir)
    try:
        summary = artifacts.read_run_summary(run_dir)
    except FileNotFoundError:
        return None
    cells: list[float] = []
    failed_cells = 0
    stages: dict[str, dict] = {}
    for stage in summary.get("stages") or []:
        score = stage_score(run_dir, stage)
        code = code_grader.read_findings(run_dir, agent_token(stage)) or {}
        findings = code.get("findings") or {}
        stage_cells: list[float] = []
        for row in score.get("results") or []:
            if row.get("expect") == "fail":
                continue
            code_score = (findings.get(row.get("row_id")) or {}).get("code_score")
            value = cell_value(row, code_score)
            if value is None:
                continue
            stage_cells.append(value)
            if value == 0.0:
                failed_cells += 1
        cells.extend(stage_cells)
        if stage_cells:
            # The per-phase view of the same arithmetic, so the table's
            # `effective` column and the headline visibly share one formula.
            stages[stage.get("agent_id")] = {
                "effective": sum(stage_cells) / len(stage_cells),
                "cells": len(stage_cells),
                "failed": sum(1 for value in stage_cells if value == 0.0),
            }
    if not cells:
        return None
    overall = sum(cells) / len(cells)
    return {
        "score": overall,
        "grade": letter_grade(overall),
        "counted": len(cells),
        "failed_cells": failed_cells,
        "stages": stages,
    }


def cell_value(row: dict, code_score) -> float | None:
    """One (stage, row) cell's contribution — 0 for failure, None for no signal."""
    if row.get("errored"):
        return 0.0
    if row.get("precheck_passed") is None:
        # Negatives are excluded before this, so a positive row that was never
        # prechecked was never dispatched — its upstream broke. The failure
        # propagating must cost the run, not shrink the denominator.
        return 0.0
    if row.get("precheck_passed") is False:
        return 0.0
    judge_score = row.get("score")
    if judge_score is None and code_score is None:
        return None  # passed precheck, never judged (no_judge / judge outage)
    return float(code_grader.blended_score(judge_score, code_score))


def agent_token(stage: dict) -> str:
    """`prototype-specify` -> `prototype_specify`, the artifact file-name form."""
    return str(stage.get("agent_id", "")).replace("-", "_")


def stage_score(run_dir: Path, stage: dict) -> dict:
    """One stage's stored score artifact, or empty when it never wrote one."""
    try:
        return artifacts.read_stage_artifact(run_dir, agent_token(stage), "score")
    except FileNotFoundError:
        return {}


# The private name `markdown_report` used before the extraction, kept so the
# move is byte-for-byte behaviour-preserving for any caller that reached for it.
_cell_value = cell_value
