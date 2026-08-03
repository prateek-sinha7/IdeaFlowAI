"""Every run's artifacts consolidated into one dataset — the report's only input.

The grading harness scatters its record across four JSON artifacts per stage,
per run, plus captured prompts, code findings and deliverables. This module
folds all of it into a single serialisable structure covering the whole evals
tree, written once to `evals_data.json` and inlined into the one report.

Why one dataset rather than each page reading what it needs: a page that
re-reads artifacts is a page that can disagree with its neighbours about what a
run scored. Consolidating first means every view — the trend, the matrix, the
row detail — is a projection of exactly the same numbers.

Serialisable throughout: plain dicts, lists, strings and numbers. Paths are
stored relative to the runs root so the dataset stays portable and the report
can build links from it.
"""

from __future__ import annotations

import json
from pathlib import Path

from evals.grading.site import aggregate, model

DATASET_NAME = "evals_data.json"

# The dataset's own shape version. Bumped when a consumer would need to change;
# the report checks nothing, but a stored file that outlives a rewrite should
# say what it is.
SCHEMA_VERSION = 1


def build(site: model.Site) -> dict:
    """Consolidate the whole tree — every run, every stage, every row — into one dict."""
    workflows = []
    for workflow in site.workflows:
        aggregates = aggregate.build(workflow)
        workflows.append(
            {
                "name": workflow.name,
                "run_count": len(workflow.runs),
                "included_count": len(workflow.included),
                "runs": [_run(run, site.runs_root) for run in workflow.runs],
                "aggregates": _aggregates(aggregates),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "workflows": workflows,
        "totals": {
            "runs": len(site.all_runs),
            "included": sum(len(workflow.included) for workflow in site.workflows),
            "workflows": len(site.workflows),
        },
    }


def write(site: model.Site) -> Path:
    """Write `evals_data.json` at the runs root and return its path."""
    path = Path(site.runs_root) / DATASET_NAME
    path.write_text(
        json.dumps(build(site), indent=2, ensure_ascii=False, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )
    return path


# ── one run ───────────────────────────────────────────────────────────────


def _run(run: model.Run, runs_root: Path) -> dict:
    return {
        "dataset_run_id": run.dataset_run_id,
        "workflow": run.workflow,
        "dir": _relative(run.run_dir, runs_root),
        "run_class": run.run_class,
        "class_reason": run.class_reason,
        "charted": run.charted,
        "status": run.status,
        "created_at": run.created_at,
        "finished_at": run.finished_at,
        "workflow_id": run.workflow_id,
        "dataset_id": run.dataset_id,
        "config_run_id": run.config_run_id,
        "row_count": run.row_count,
        "not_run": list(run.not_run),
        "overrides": dict(run.overrides),
        "model_under_test": dict(run.model_under_test),
        "judge": dict(run.judge),
        "options": dict(run.options),
        "overall": run.overall,
        "errors": list(run.errors),
        "stages": [_stage(stage) for stage in run.stages],
        "matrix": _matrix(run.matrix),
    }


def _stage(stage: model.Stage) -> dict:
    return {
        "agent_id": stage.agent_id,
        "agent_token": stage.agent_token,
        "counts": stage.counts,
        "scores": stage.scores,
        "dimensions": stage.dimensions,
        "tokens": stage.tokens,
        "hashes": stage.hashes,
        "warnings": list(stage.warnings),
        "baseline": stage.baseline,
        "recurring_strengths": list(stage.recurring_strengths),
        "recurring_weaknesses": list(stage.recurring_weaknesses),
        "effective": stage.effective,
        "failed_cells": stage.failed_cells,
        "has_system_prompt": stage.system_prompt is not None,
        "rows": [_row(row) for row in stage.rows],
    }


def _row(row: model.Row) -> dict:
    return {
        "row_id": row.row_id,
        "expect": row.expect,
        "precheck_passed": row.precheck_passed,
        "precheck_reason": row.precheck_reason,
        "errored": row.errored,
        "judge_score": row.judge_score,
        "code_score": row.code_score,
        "combined": row.combined,
        "cell_value": row.cell_value,
        "cell_kind": row.cell_kind,
        "failed": row.failed,
        "passed": row.passed,
        "sub_scores": row.sub_scores,
        "rationale": row.rationale,
        "strengths": list(row.strengths),
        "weaknesses": list(row.weaknesses),
        "evidence": row.evidence,
        "score_caps": row.score_caps,
        "judge_error": row.judge_error,
        "skipped_reason": row.skipped_reason,
        "brief": row.brief,
        "deliverables": [
            {
                "filename": deliverable.filename,
                "kind": deliverable.kind,
                "size_bytes": deliverable.size_bytes,
            }
            for deliverable in row.deliverables
        ],
        "has_log": row.log_path is not None,
    }


def _matrix(matrix: model.Matrix) -> dict:
    return {
        "stage_ids": list(matrix.stage_ids),
        "row_ids": list(matrix.row_ids),
        # JSON has no tuple keys, so cells travel as a list of records.
        "cells": [
            {
                "stage_id": stage_id,
                "row_id": row_id,
                "value": cell.value,
                "kind": cell.kind,
                "run_count": cell.run_count,
                "spread": cell.spread,
            }
            for (stage_id, row_id), cell in sorted(matrix.cells.items())
        ],
    }


# ── the cross-run views ───────────────────────────────────────────────────


def _aggregates(result: aggregate.Aggregates) -> dict:
    return {
        "stage_ids": list(result.stage_ids),
        "trend": [
            {
                "dataset_run_id": point.dataset_run_id,
                "created_at": point.created_at,
                "score": point.score,
                "grade": point.grade,
                "per_stage": point.per_stage,
            }
            for point in result.trend
        ],
        "references": [
            {"dataset_run_id": line.dataset_run_id, "score": line.score, "grade": line.grade}
            for line in result.references
        ],
        "dimensions_by_stage": result.dimensions_by_stage,
        "dimensions_by_run": result.dimensions_by_run,
        "matrix": _matrix(result.matrix),
        "tokens": list(result.tokens),
        "code_health": list(result.code_health),
        "prompt_history": [
            {
                "agent_id": history.agent_id,
                "noise_band": history.noise_band,
                "versions": [
                    {
                        "prompt_hash": version.prompt_hash,
                        "short_hash": version.short_hash,
                        "first_seen": version.first_seen,
                        "run_ids": list(version.run_ids),
                        "run_count": version.run_count,
                        "average_score": version.average_score,
                        "delta": version.delta,
                        "target_met": version.target_met,
                        "is_baseline": version.is_baseline,
                        "verdict": version.verdict,
                        "has_prompt_text": version.prompt_text is not None,
                        "missing_reason": version.missing_reason,
                    }
                    for version in history.versions
                ],
            }
            for history in result.prompt_history
        ],
    }


def _relative(path: Path, root: Path) -> str:
    """A run folder's location relative to the runs root, for portable links."""
    try:
        return str(Path(path).relative_to(root))
    except ValueError:
        return str(path)
