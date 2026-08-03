"""One run folder, read into the shape every page renders. No HTML lives here.

Reads only what a run already wrote — the summary, the resolved config, each
stage's artifacts, the captured prompts, the deliverables — and never builds a
path by hand: `artifacts` owns every one of those.

The grade is imported from `grades`, not recomputed. What this module *does*
add is the one thing no existing module records: `cell_kind`. Four different
failures all score 0 today — a dispatch error, a failed precheck, a chain
broken upstream, and a judge that fell over — and an average erases the
difference between them. The matrix is only worth drawing if it can tell them
apart.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from evals.grading import artifacts, grades
from evals.grading.code import code_grader
from evals.grading.model import scoring

# A run folder is named `<YYMMDD>-<HHMMSS>-<dataset>`. Anything else was put
# there by hand — a golden reference, a rescued fixture — and is not a
# measurement in the series.
TIMESTAMPED = re.compile(r"^\d{6}-\d{6}-")
COPY_SUFFIX = "-copy"
COMPLETE_STATUSES = frozenset({"completed", "complete", "finished", "ok"})

# Deliverable kinds, by suffix. `html` gets a sandboxed preview, `markdown` an
# escaped source block, everything else a link.
HTML_SUFFIXES = frozenset({".html", ".htm"})
MARKDOWN_SUFFIXES = frozenset({".md", ".markdown"})

# Run classes. Only `run` feeds a chart; the rest are listed and badged, never
# silently dropped — a chart that omits data without saying so is worse than
# no chart.
CLASS_RUN = "run"
CLASS_REFERENCE = "reference"
CLASS_COPY = "copy"
CLASS_PARTIAL = "partial"
CLASS_ERROR = "error"
CHARTED_CLASSES = frozenset({CLASS_RUN})

# What one (stage, row) cell was. `ok` carries a real score; the four failure
# kinds all score 0 and must stay distinguishable; the last two are excluded
# from the average entirely.
KIND_OK = "ok"
KIND_ERRORED = "errored"
KIND_BROKEN_CHAIN = "broken_chain"
KIND_PRECHECK_FAIL = "precheck_fail"
KIND_JUDGE_FAILED = "judge_failed"
KIND_NEGATIVE = "negative"
KIND_UNJUDGED = "unjudged"
FAILURE_KINDS = frozenset(
    {KIND_ERRORED, KIND_BROKEN_CHAIN, KIND_PRECHECK_FAIL, KIND_JUDGE_FAILED}
)


# ── the view-model ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Deliverable:
    """One file an agent produced for one row, under `src/<row_id>/`."""

    filename: str
    path: Path
    kind: str
    size_bytes: int


@dataclass(frozen=True)
class Row:
    """One (stage, row) cell, with everything known about it in one place."""

    row_id: str
    expect: str | None = None
    precheck_passed: bool | None = None
    precheck_reason: str | None = None
    errored: bool = False
    judge_score: float | None = None
    code_score: float | None = None
    combined: float | None = None
    cell_value: float | None = None
    cell_kind: str = KIND_OK
    passed: bool | None = None
    sub_scores: dict = field(default_factory=dict)
    rationale: str | None = None
    strengths: list = field(default_factory=list)
    weaknesses: list = field(default_factory=list)
    evidence: dict = field(default_factory=dict)
    score_caps: dict = field(default_factory=dict)
    judge_error: str | None = None
    skipped_reason: str | None = None
    brief: str = ""
    deliverables: tuple[Deliverable, ...] = ()
    log_path: Path | None = None
    code_finding: dict = field(default_factory=dict)

    @property
    def failed(self) -> bool:
        """Whether this cell counted as an outright failure (scored 0)."""
        return self.cell_kind in FAILURE_KINDS and self.cell_value == 0.0


@dataclass(frozen=True)
class Stage:
    """One phase of one run: its aggregates, its rows, and the prompt that ran."""

    agent_id: str
    agent_token: str
    counts: dict = field(default_factory=dict)
    scores: dict = field(default_factory=dict)
    dimensions: dict = field(default_factory=dict)
    tokens: dict = field(default_factory=dict)
    hashes: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    baseline: dict = field(default_factory=dict)
    recurring_strengths: list = field(default_factory=list)
    recurring_weaknesses: list = field(default_factory=list)
    rows: tuple[Row, ...] = ()
    system_prompt: str | None = None
    advice_path: Path | None = None
    code_deliverable_file: str | None = None
    effective: float | None = None
    failed_cells: int = 0

    @property
    def dimension_ids(self) -> list[str]:
        return list(self.dimensions.keys())


@dataclass(frozen=True)
class MatrixCell:
    """One cell of the stage x row grid, at run scope or aggregated across runs."""

    value: float | None
    kind: str
    run_count: int = 1
    spread: float | None = None


@dataclass(frozen=True)
class Matrix:
    """Stages down, dataset rows across. A missing pair is absent, not zero."""

    stage_ids: tuple[str, ...] = ()
    row_ids: tuple[str, ...] = ()
    cells: dict = field(default_factory=dict)

    def cell(self, stage_id: str, row_id: str) -> MatrixCell | None:
        return self.cells.get((stage_id, row_id))


@dataclass(frozen=True)
class Run:
    """One run folder, classified and fully loaded."""

    dataset_run_id: str
    run_dir: Path
    workflow: str
    run_class: str = CLASS_RUN
    class_reason: str | None = None
    status: str = "unknown"
    created_at: str | None = None
    finished_at: str | None = None
    workflow_id: str | None = None
    dataset_id: str | None = None
    config_run_id: str | None = None
    row_count: int | None = None
    not_run: list = field(default_factory=list)
    overrides: dict = field(default_factory=dict)
    model_under_test: dict = field(default_factory=dict)
    judge: dict = field(default_factory=dict)
    options: dict = field(default_factory=dict)
    overall: dict | None = None
    stages: tuple[Stage, ...] = ()
    matrix: Matrix = field(default_factory=Matrix)
    errors: tuple[str, ...] = ()

    @property
    def charted(self) -> bool:
        """Whether this run may contribute to an aggregate."""
        return self.run_class in CHARTED_CLASSES

    @property
    def score(self) -> float | None:
        return (self.overall or {}).get("score")

    @property
    def grade(self) -> str | None:
        return (self.overall or {}).get("grade")

    def stage(self, agent_id: str) -> Stage | None:
        for stage in self.stages:
            if stage.agent_id == agent_id or stage.agent_token == agent_id:
                return stage
        return None


@dataclass(frozen=True)
class Workflow:
    """Every run of one workflow, newest first."""

    name: str
    runs: tuple[Run, ...] = ()

    @property
    def included(self) -> list[Run]:
        """The only runs an aggregate may use."""
        return [run for run in self.runs if run.charted]

    @property
    def references(self) -> list[Run]:
        """Hand-placed golden/fixture runs — ceiling lines, not trend points."""
        return [run for run in self.runs if run.run_class == CLASS_REFERENCE]

    @property
    def excluded(self) -> list[Run]:
        return [run for run in self.runs if not run.charted]


@dataclass(frozen=True)
class Site:
    """The whole `.runs/` tree. Carries no render timestamp, by design."""

    runs_root: Path
    workflows: tuple[Workflow, ...] = ()

    @property
    def all_runs(self) -> list[Run]:
        return [run for workflow in self.workflows for run in workflow.runs]


# ── discovery and classification ──────────────────────────────────────────


def discover(runs_root: Path) -> Site:
    """Load every run under `<runs_root>/<workflow>/`, newest first."""
    runs_root = Path(runs_root)
    if not runs_root.is_dir():
        raise FileNotFoundError(f"no runs root at {runs_root}")
    workflows = [
        Workflow(
            name=workflow_dir.name,
            runs=tuple(load_run(run_dir, workflow_dir.name) for run_dir in _folders(workflow_dir)),
        )
        for workflow_dir in _folders(runs_root)
    ]
    return Site(runs_root=runs_root, workflows=tuple(workflows))


def _folders(parent: Path) -> list[Path]:
    """Child directories, newest-first by name, skipping housekeeping dot-dirs.

    Folder names are timestamp-prefixed, so a descending lexical sort IS
    chronological — no date parsing, and nothing to get wrong across timezones.
    """
    return sorted(
        (path for path in parent.glob("*") if path.is_dir() and not path.name.startswith(".")),
        key=lambda path: path.name,
        reverse=True,
    )


def classify(run_dir: Path, summary: dict | None, overall: dict | None, stages) -> tuple[str, str]:
    """Which class this run belongs to, and why — in strict precedence order."""
    name = Path(run_dir).name
    if summary is None:
        return CLASS_ERROR, "run_summary.json is missing or unreadable"
    if name.endswith(COPY_SUFFIX):
        return CLASS_COPY, f"folder name ends in '{COPY_SUFFIX}' — a duplicate, not a run"
    if not TIMESTAMPED.match(name):
        return CLASS_REFERENCE, "folder name carries no run timestamp — a hand-placed reference"
    status = str(summary.get("status") or "unknown")
    if status.lower() not in COMPLETE_STATUSES:
        return CLASS_PARTIAL, f"status is '{status}'"
    stale = [
        stage.get("agent_id")
        for stage in summary.get("stages") or []
        if stage.get("status") in ("stale", "not_run")
    ]
    if stale:
        return CLASS_PARTIAL, f"stages did not run cleanly: {', '.join(str(s) for s in stale)}"
    if summary.get("not_run"):
        listed = ", ".join(str(agent) for agent in summary["not_run"])
        return CLASS_PARTIAL, f"stages never ran: {listed}"
    if overall is None:
        return CLASS_PARTIAL, "nothing in this run was gradable"
    if not stages:
        return CLASS_PARTIAL, "no stage wrote a score artifact"
    return CLASS_RUN, "complete run"


# ── loading one run ───────────────────────────────────────────────────────


def load_run(run_dir: Path, workflow: str) -> Run:
    """One run folder as a `Run`. A missing input omits its section, never raises."""
    run_dir = Path(run_dir)
    errors: list[str] = []
    summary = _read_summary(run_dir, errors)
    if summary is None:
        run_class, reason = classify(run_dir, None, None, ())
        return Run(
            dataset_run_id=run_dir.name,
            run_dir=run_dir,
            workflow=workflow,
            run_class=run_class,
            class_reason=reason,
            errors=tuple(errors),
        )

    config = _read_config(run_dir, errors)
    overall = _safe(lambda: grades.compute_overall(run_dir), errors, "grade")
    stages = tuple(
        _load_stage(run_dir, stage, overall, errors)
        for stage in summary.get("stages") or []
        if _has_score(run_dir, stage)
    )
    run_class, reason = classify(run_dir, summary, overall, stages)
    if errors and run_class == CLASS_RUN:
        run_class, reason = CLASS_ERROR, errors[0]

    return Run(
        dataset_run_id=summary.get("dataset_run_id") or run_dir.name,
        run_dir=run_dir,
        workflow=workflow,
        run_class=run_class,
        class_reason=reason,
        status=str(summary.get("status") or "unknown"),
        created_at=summary.get("created_at"),
        finished_at=summary.get("finished_at"),
        workflow_id=summary.get("workflow_id"),
        dataset_id=summary.get("dataset_id"),
        config_run_id=summary.get("run_id"),
        row_count=summary.get("row_count"),
        not_run=list(summary.get("not_run") or []),
        overrides=dict((summary.get("config") or {}).get("overrides") or {}),
        model_under_test=dict(config.get("agent_under_test") or {}),
        judge=dict(config.get("judge") or {}),
        options=dict(config.get("options") or {}),
        overall=overall,
        stages=stages,
        matrix=build_matrix(stages),
        errors=tuple(errors),
    )


def _load_stage(run_dir: Path, stage: dict, overall: dict | None, errors: list[str]) -> Stage:
    """One stage: its score artifact joined to its grades, runs and code findings."""
    token = grades.agent_token(stage)
    agent_id = str(stage.get("agent_id") or token)
    score = _read_artifact(run_dir, token, "score", errors) or {}
    grade_entries = _read_artifact(run_dir, token, "grade", errors) or []
    run_entries = _read_artifact(run_dir, token, "run", errors) or []
    code = code_grader.read_findings(run_dir, token) or {}
    findings = code.get("findings") or {}

    grades_by_id = {_row_id(entry): entry for entry in grade_entries}
    briefs = {_row_id(entry): entry.get("prompt", "") for entry in run_entries}
    hashes = dict(score.get("hashes") or {})
    # The prompt hash is stamped on each dispatched ROW, not on the stage's
    # score artifact — which is why grouping by it has to reach into the run
    # entries. Without this every run reads as one "unknown" prompt version and
    # the whole did-my-edit-help view says nothing.
    hashes.setdefault("system_prompt_hash", _prompt_hash(run_entries))
    rows = tuple(
        _load_row(run_dir, token, result, grades_by_id, briefs, findings)
        for result in score.get("results") or []
    )
    per_stage = ((overall or {}).get("stages") or {}).get(agent_id) or {}
    advice = artifacts.advice_markdown_path(run_dir, token)

    return Stage(
        agent_id=agent_id,
        agent_token=token,
        counts=score.get("counts") or {},
        scores=score.get("scores") or {},
        dimensions=score.get("dimensions") or {},
        tokens=score.get("tokens") or {},
        hashes=hashes,
        warnings=list(score.get("warnings") or []),
        baseline=score.get("baseline") or {},
        recurring_strengths=list(score.get("recurring_strengths") or []),
        recurring_weaknesses=list(score.get("recurring_weaknesses") or []),
        rows=rows,
        system_prompt=_read_prompt(run_dir, token),
        advice_path=advice if advice.exists() else None,
        code_deliverable_file=code.get("deliverable_file"),
        effective=per_stage.get("effective"),
        failed_cells=per_stage.get("failed") or 0,
    )


def _load_row(run_dir, token, result, grades_by_id, briefs, findings) -> Row:
    """One row of one stage, joined across all four artifact kinds."""
    row_id = str(result.get("row_id") or result.get("scenario_id") or result.get("id") or "")
    grade = grades_by_id.get(row_id) or {}
    finding = findings.get(row_id) or {}
    code_score = finding.get("code_score")
    judge_score = result.get("score")
    log = artifacts.log_path(run_dir, token, row_id)

    return Row(
        row_id=row_id,
        expect=result.get("expect"),
        precheck_passed=result.get("precheck_passed"),
        precheck_reason=grade.get("precheck_reason"),
        errored=bool(result.get("errored")),
        judge_score=judge_score,
        code_score=code_score,
        combined=code_grader.blended_score(judge_score, code_score),
        cell_value=grades.cell_value(result, code_score),
        cell_kind=cell_kind(result, grade, code_score),
        passed=result.get("passed"),
        sub_scores=grade.get("sub_scores") or {},
        rationale=grade.get("rationale"),
        strengths=list(grade.get("strengths") or []),
        weaknesses=list(grade.get("weaknesses") or []),
        evidence=grade.get("evidence") or {},
        score_caps=grade.get("score_caps") or {},
        judge_error=scoring.judge_error_reason(grade) if grade else None,
        skipped_reason=grade.get("skipped_reason"),
        brief=briefs.get(row_id, ""),
        deliverables=_deliverables(run_dir, row_id),
        log_path=log if log.exists() else None,
        code_finding=finding,
    )


def cell_kind(result: dict, grade: dict, code_score) -> str:
    """Which of the seven situations this cell is — the distinction a mean loses.

    Ordered by precedence. The four failure kinds all score 0 in the average,
    which is exactly why they must not be shown as the same thing: a phase that
    scored 0 because its upstream broke needs a different fix from one whose
    output failed its precheck.
    """
    if result.get("expect") == "fail":
        return KIND_NEGATIVE
    if result.get("errored"):
        return KIND_ERRORED
    if result.get("precheck_passed") is None:
        return KIND_BROKEN_CHAIN
    if result.get("precheck_passed") is False:
        return KIND_PRECHECK_FAIL
    if grade and scoring.judge_errored(grade):
        return KIND_JUDGE_FAILED
    if result.get("score") is None and code_score is None:
        return KIND_UNJUDGED
    return KIND_OK


def build_matrix(stages) -> Matrix:
    """The stage x row grid for one run. Absent pairs stay absent."""
    stage_ids = tuple(stage.agent_id for stage in stages)
    row_ids: list[str] = []
    cells: dict = {}
    for stage in stages:
        for row in stage.rows:
            if row.row_id not in row_ids:
                row_ids.append(row.row_id)
            cells[(stage.agent_id, row.row_id)] = MatrixCell(
                value=row.cell_value, kind=row.cell_kind
            )
    return Matrix(stage_ids=stage_ids, row_ids=tuple(sorted(row_ids)), cells=cells)


# ── deliverables ──────────────────────────────────────────────────────────


def _deliverables(run_dir: Path, row_id: str) -> tuple[Deliverable, ...]:
    """Every file this row produced, largest last, or nothing when none were kept."""
    src = artifacts.src_dir(run_dir, row_id)
    if not src.is_dir():
        return ()
    found = []
    for path in sorted(src.glob("*")):
        if not path.is_file():
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        found.append(
            Deliverable(
                filename=path.name, path=path, kind=deliverable_kind(path), size_bytes=size
            )
        )
    return tuple(found)


def deliverable_kind(path: Path) -> str:
    """`html` gets a sandboxed preview, `markdown` a source block, else a link."""
    suffix = path.suffix.lower()
    if suffix in HTML_SUFFIXES:
        return "html"
    if suffix in MARKDOWN_SUFFIXES:
        return "markdown"
    return "other"


# ── guarded reads ─────────────────────────────────────────────────────────


def _read_summary(run_dir: Path, errors: list[str]) -> dict | None:
    """The run summary, or None with the reason recorded — never an exception."""
    try:
        return artifacts.read_run_summary(run_dir)
    except FileNotFoundError:
        errors.append("run_summary.json is missing")
    except (ValueError, OSError) as error:
        errors.append(f"run_summary.json is unreadable: {error}")
    return None


def _read_config(run_dir: Path, errors: list[str]) -> dict:
    """The resolved config, or empty — an older folder may not have one."""
    try:
        return artifacts.read_resolved_config(run_dir) or {}
    except FileNotFoundError:
        return {}
    except (ValueError, OSError) as error:
        errors.append(f"{artifacts.RESOLVED_CONFIG_NAME} is unreadable: {error}")
        return {}


def _read_artifact(run_dir: Path, token: str, kind: str, errors: list[str]):
    """One stage artifact, or None when this run never wrote that kind."""
    try:
        return artifacts.read_stage_artifact(run_dir, token, kind)
    except FileNotFoundError:
        return None
    except (ValueError, OSError) as error:
        errors.append(f"{token}_{kind}.json is unreadable: {error}")
        return None


def _read_prompt(run_dir: Path, token: str) -> str | None:
    """The captured system prompt — absent on folders predating prompt capture."""
    try:
        return artifacts.read_system_prompt(run_dir, token)
    except (FileNotFoundError, OSError):
        return None


def _safe(call, errors: list[str], label: str):
    """Run a read that may raise, recording the failure instead of propagating."""
    try:
        return call()
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        errors.append(f"{label} could not be computed: {error}")
        return None


def _has_score(run_dir: Path, stage: dict) -> bool:
    """A stage without a score artifact is not a stage this site can show."""
    token = grades.agent_token(stage)
    return bool(token) and artifacts.artifact_path(run_dir, token, "score").exists()


def _prompt_hash(run_entries) -> str | None:
    """The system-prompt hash this stage ran under, from its first dispatched row.

    Every row of a stage shares one composed prompt, so the first row that
    recorded a hash speaks for the stage.
    """
    for entry in run_entries or []:
        found = entry.get("system_prompt_hash")
        if found:
            return found
    return None


def _row_id(entry: dict) -> str:
    """The join key, tolerating all three historical id field names."""
    return str(entry.get("row_id") or entry.get("scenario_id") or entry.get("id") or "")
