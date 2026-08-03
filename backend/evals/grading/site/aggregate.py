"""Across runs: the trends, the heatmaps, the matrix, and the prompt versions.

The only arithmetic in this package that no existing module owns — means,
spreads and chronological grouping over many runs. Everything a single run
already knows is imported, not recomputed.

Two rules hold throughout:

- Only `included` runs (class `run`) enter an aggregate. References, copies,
  partials and unreadable folders are listed elsewhere and badged; a golden
  fixture is a ceiling to draw, not a measurement to average.
- The prompt-version verdicts come from `compare.group_by_prompt` verbatim.
  Deciding for ourselves whether a delta beat the noise would be a second
  opinion where the harness is supposed to have one.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from evals.grading import artifacts, compare
from evals.grading.site import model


@dataclass(frozen=True)
class TrendPoint:
    """One run's position in the quality trend."""

    dataset_run_id: str
    created_at: str | None
    score: float | None
    grade: str | None
    per_stage: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ReferenceLine:
    """A hand-placed golden: a target to draw across the chart, not a data point."""

    dataset_run_id: str
    score: float | None
    grade: str | None


@dataclass(frozen=True)
class PromptVersion:
    """One `system_prompt_hash`, its runs, its aggregate, and the verdict."""

    prompt_hash: str | None
    short_hash: str
    first_seen: str
    run_ids: tuple[str, ...]
    run_count: int
    average_score: float | None
    precheck_pass_rate: float | None
    delta: float | None
    target: float | None
    target_met: bool | None
    is_baseline: bool
    prompt_text: str | None
    missing_reason: str | None

    @property
    def verdict(self) -> str:
        """`baseline`, `improved`, `regressed`, or `within noise` — never invented."""
        if self.is_baseline:
            return "baseline"
        if self.delta is None:
            return "unknown"
        if self.target_met is False:
            return "regressed"
        return "improved" if self.delta > 0 else "held"


@dataclass(frozen=True)
class PromptHistory:
    """Every prompt version of one agent, oldest first."""

    agent_id: str
    versions: tuple[PromptVersion, ...] = ()
    noise: dict = field(default_factory=dict)

    @property
    def noise_band(self) -> float | None:
        """The 2σ threshold `compare` observed, or None when it saw no repeats.

        `compare.noise_band` returns the headline metric's band under `band`,
        and the number that decides whether a delta is real is its `threshold`
        — already floored at 1.0 there, so nothing is re-derived here.
        """
        return (self.noise.get("band") or {}).get("threshold")


@dataclass(frozen=True)
class Aggregates:
    """Everything the dashboard draws, for one workflow."""

    workflow: str
    run_count: int = 0
    included_count: int = 0
    trend: tuple[TrendPoint, ...] = ()
    references: tuple[ReferenceLine, ...] = ()
    stage_ids: tuple[str, ...] = ()
    dimensions_by_stage: dict = field(default_factory=dict)
    dimensions_by_run: dict = field(default_factory=dict)
    matrix: model.Matrix = field(default_factory=model.Matrix)
    tokens: tuple[dict, ...] = ()
    code_health: tuple[dict, ...] = ()
    prompt_history: tuple[PromptHistory, ...] = ()

    @property
    def has_trend(self) -> bool:
        return len(self.trend) >= 2


def build(workflow: model.Workflow) -> Aggregates:
    """Every cross-run view for one workflow, over its included runs only."""
    included = workflow.included
    chronological = list(reversed(included))  # `runs` is newest-first
    stage_ids = _stage_order(included)
    return Aggregates(
        workflow=workflow.name,
        run_count=len(workflow.runs),
        included_count=len(included),
        trend=tuple(_trend_point(run) for run in chronological),
        references=tuple(
            ReferenceLine(run.dataset_run_id, run.score, run.grade)
            for run in workflow.references
        ),
        stage_ids=stage_ids,
        dimensions_by_stage=_dimensions_by_stage(included),
        dimensions_by_run=_dimensions_by_run(chronological),
        matrix=cross_run_matrix(included),
        tokens=tuple(_token_row(run) for run in chronological),
        code_health=tuple(_health_row(run) for run in chronological),
        prompt_history=tuple(prompt_history(included, stage_ids)),
    )


def _stage_order(runs) -> tuple[str, ...]:
    """Stage ids in pipeline order, as first observed across the runs."""
    order: list[str] = []
    for run in runs:
        for stage in run.stages:
            if stage.agent_id not in order:
                order.append(stage.agent_id)
    return tuple(order)


def _trend_point(run: model.Run) -> TrendPoint:
    return TrendPoint(
        dataset_run_id=run.dataset_run_id,
        created_at=run.created_at,
        score=run.score,
        grade=run.grade,
        per_stage={stage.agent_id: stage.effective for stage in run.stages},
    )


# ── dimensions ────────────────────────────────────────────────────────────


def _dimensions_by_stage(runs) -> dict:
    """dimension -> stage -> mean over every included run.

    The chronic-weakness view: one paragraph of one AGENT.md that never
    improves shows up here as a row that is dark all the way across.
    """
    collected: dict[str, dict[str, list[float]]] = {}
    for run in runs:
        for stage in run.stages:
            for name, stats in (stage.dimensions or {}).items():
                mean = stats.get("mean")
                if mean is None:
                    continue
                collected.setdefault(name, {}).setdefault(stage.agent_id, []).append(float(mean))
    return {
        name: {stage: statistics.fmean(values) for stage, values in by_stage.items()}
        for name, by_stage in sorted(collected.items())
    }


def _dimensions_by_run(runs) -> dict:
    """dimension -> run -> mean across that run's stages."""
    collected: dict[str, dict[str, list[float]]] = {}
    for run in runs:
        for stage in run.stages:
            for name, stats in (stage.dimensions or {}).items():
                mean = stats.get("mean")
                if mean is None:
                    continue
                collected.setdefault(name, {}).setdefault(run.dataset_run_id, []).append(
                    float(mean)
                )
    return {
        name: {run_id: statistics.fmean(values) for run_id, values in by_run.items()}
        for name, by_run in sorted(collected.items())
    }


def worst_first(dimensions: dict) -> list[str]:
    """Dimension names, weakest overall mean first — where to look, in order."""
    def mean_of(name: str) -> float:
        values = [value for value in dimensions[name].values() if value is not None]
        return statistics.fmean(values) if values else 0.0

    return sorted(dimensions, key=mean_of)


# ── the cross-run matrix ──────────────────────────────────────────────────


def cross_run_matrix(runs) -> model.Matrix:
    """Stage x row averaged over runs, carrying spread and contributing count.

    A mean over two runs and a mean over fifteen must not look alike, so every
    cell says how many runs it stands on.
    """
    values: dict[tuple[str, str], list[float]] = {}
    kinds: dict[tuple[str, str], set[str]] = {}
    stage_ids: list[str] = []
    row_ids: list[str] = []

    for run in runs:
        for stage in run.stages:
            if stage.agent_id not in stage_ids:
                stage_ids.append(stage.agent_id)
            for row in stage.rows:
                if row.row_id not in row_ids:
                    row_ids.append(row.row_id)
                key = (stage.agent_id, row.row_id)
                kinds.setdefault(key, set()).add(row.cell_kind)
                if row.cell_value is not None:
                    values.setdefault(key, []).append(row.cell_value)

    cells = {}
    for key, kind_set in kinds.items():
        observed = values.get(key, [])
        cells[key] = model.MatrixCell(
            value=statistics.fmean(observed) if observed else None,
            kind=_dominant_kind(kind_set),
            run_count=len(observed) or len(kind_set),
            spread=statistics.pstdev(observed) if len(observed) > 1 else None,
        )
    return model.Matrix(
        stage_ids=tuple(stage_ids), row_ids=tuple(sorted(row_ids)), cells=cells
    )


def _dominant_kind(kinds: set[str]) -> str:
    """The kind worth showing when runs disagree — a failure outranks an ok."""
    for kind in (
        model.KIND_ERRORED,
        model.KIND_BROKEN_CHAIN,
        model.KIND_PRECHECK_FAIL,
        model.KIND_JUDGE_FAILED,
        model.KIND_UNJUDGED,
        model.KIND_NEGATIVE,
    ):
        if kind in kinds:
            return kind
    return model.KIND_OK


# ── cost and code health ──────────────────────────────────────────────────


def _token_row(run: model.Run) -> dict:
    """What one run spent, split by who spent it."""
    agent_total = judge_total = 0
    per_stage = {}
    for stage in run.stages:
        tokens = stage.tokens or {}
        agent = (tokens.get("agent") or {}).get("total") or 0
        judge = (tokens.get("judge") or {}).get("total") or 0
        agent_total += agent
        judge_total += judge
        per_stage[stage.agent_id] = {"agent": agent, "judge": judge}
    return {
        "dataset_run_id": run.dataset_run_id,
        "created_at": run.created_at,
        "agent": agent_total,
        "judge": judge_total,
        "total": agent_total + judge_total,
        "per_stage": per_stage,
    }


def _health_row(run: model.Run) -> dict:
    """The code track's reliability signal for one run.

    Exercised counts travel with the failure counts, because "0 failed" and
    "nothing was clickable to begin with" are not the same result.
    """
    counters = {
        "console_errors": 0,
        "page_errors": 0,
        "dead_navs": 0,
        "interaction_failures": 0,
        "interactions_exercised": 0,
        "static_issues": 0,
        "rows_with_findings": 0,
    }
    for stage in run.stages:
        for row in stage.rows:
            finding = row.code_finding or {}
            if not finding:
                continue
            counters["rows_with_findings"] += 1
            rendered = finding.get("render") or {}
            interactions = finding.get("interactions") or {}
            failures = interactions.get("failures") or []
            actions = interactions.get("actions") or []
            counters["console_errors"] += len(rendered.get("console_errors") or [])
            counters["page_errors"] += len(rendered.get("page_errors") or [])
            counters["dead_navs"] += sum(
                1 for nav in rendered.get("nav_results") or [] if not nav.get("ok")
            )
            counters["interaction_failures"] += len(failures)
            counters["interactions_exercised"] += len(actions) + len(failures)
            counters["static_issues"] += len(finding.get("issues") or [])
    return {
        "dataset_run_id": run.dataset_run_id,
        "created_at": run.created_at,
        **counters,
    }


# ── prompt versions ───────────────────────────────────────────────────────


def prompt_history(runs, stage_ids) -> list[PromptHistory]:
    """One history per agent: versions by prompt hash, with `compare`'s verdicts."""
    histories = []
    for agent_id in stage_ids:
        payloads = [_compare_payload(run, agent_id) for run in runs]
        payloads = [payload for payload in payloads if payload]
        if not payloads:
            continue
        grouped = compare.group_by_prompt(payloads)
        noise = compare.noise_band(payloads)
        texts = _prompt_texts(runs, agent_id)
        histories.append(
            PromptHistory(
                agent_id=agent_id,
                versions=tuple(_versions(grouped, texts)),
                noise=noise,
            )
        )
    return histories


def _compare_payload(run: model.Run, agent_id: str) -> dict | None:
    """One run, in the shape `compare` reads: identity plus the stage summary."""
    stage = run.stage(agent_id)
    if stage is None:
        return None
    return {
        "dataset_run_id": run.dataset_run_id,
        "timestamp": run.created_at or "",
        "config_hash": stage.hashes.get("config_hash") or run.config_run_id,
        "system_prompt_hash": stage.hashes.get("system_prompt_hash"),
        "summary": {
            "scores": stage.scores,
            "dimensions": stage.dimensions,
            "precheck_pass_rate": (stage.scores or {}).get("precheck_pass_rate"),
        },
    }


def _prompt_texts(runs, agent_id: str) -> dict:
    """hash -> the captured prompt text, but only where the text proves it.

    A run folder can hold a captured prompt whose hash does not match the one
    its rows recorded — most commonly when the rows recorded no hash at all and
    fell back to the hash of the empty string. Attaching the text anyway would
    let the diff view show two prompts as "the difference between these
    versions" when they are nothing of the kind. So the text is admitted only
    when re-hashing it reproduces the version's hash.
    """
    texts = {}
    for run in runs:
        stage = run.stage(agent_id)
        if stage is None or not stage.system_prompt:
            continue
        claimed = stage.hashes.get("system_prompt_hash")
        if not claimed:
            continue
        if artifacts.compute_system_prompt_hash(stage.system_prompt) != claimed:
            continue
        texts.setdefault(claimed, stage.system_prompt)
    return texts


def _versions(grouped: dict, texts: dict) -> list[PromptVersion]:
    """`compare.group_by_prompt`'s groups, wrapped — with no value altered."""
    baseline_hash = grouped.get("baseline")
    target = grouped.get("target")
    versions = []
    for prompt_hash in grouped.get("order") or []:
        group = (grouped.get("groups") or {}).get(prompt_hash) or {}
        average = group.get("average_score")
        text = texts.get(prompt_hash)
        versions.append(
            PromptVersion(
                prompt_hash=prompt_hash,
                short_hash=_short(prompt_hash),
                first_seen=group.get("first_seen") or "",
                run_ids=tuple(group.get("runs") or []),
                run_count=group.get("total_runs") or 0,
                average_score=average,
                precheck_pass_rate=group.get("precheck_pass_rate"),
                delta=None
                if average is None or target is None
                else average - target,
                target=target,
                target_met=group.get("target_met"),
                is_baseline=prompt_hash == baseline_hash,
                prompt_text=text,
                missing_reason=None
                if text
                else (
                    "no captured prompt matches this hash — the folder either predates "
                    "prompt capture, or its rows recorded no hash at all"
                ),
            )
        )
    return versions


def _short(prompt_hash) -> str:
    """A sha256 shortened for display, or an honest label for an absent one."""
    if not prompt_hash:
        return "unknown"
    return str(prompt_hash).replace("sha256:", "")[:12]


def within_noise(delta: float | None, band: float | None) -> bool:
    """Whether a delta sits inside the observed run-to-run variance.

    The band itself comes from `compare.noise_band`; this only compares against
    it, so the rule for what counts as real lives in one place.
    """
    if delta is None or band is None:
        return False
    return abs(delta) <= abs(band)
