"""Pure comparison: did editing the prompt actually help?

Takes two or more runs' artifact dicts and reports deltas — per row, per
dimension, and per prompt version. Includes a noise guard, because with a
stochastic judge a small average move is usually nothing.
"""

from __future__ import annotations

import math
import statistics

# The aggregates compared run-to-run. Names match `scoring.summarize_stage`;
# every one of them is "higher is better", which is what makes the sign of a
# delta readable as improved/regressed without a per-metric direction table.
AGGREGATE_METRICS = (
    "average_all",
    "average_precheck_passed",
    "average_clean_chain",
    "precheck_pass_rate",
    "distinct_score_count",
)

# The metric the headline band and the comparison verdict are reported on.
HEADLINE_METRIC = "average_all"

# Two-sided ~95% coverage of a roughly normal noise distribution. Deliberately
# conservative rather than 1: a wrongly declared improvement gets written into
# an AGENT.md and stays, while a wrongly declared "within-noise" only costs one
# more run.
SIGMA_MULTIPLIER = 2.0

# The smallest move worth calling real, per metric, even when the repeats
# happen to agree exactly — two identical samples are not evidence of a
# zero-variance judge. Score-scale metrics (0-100) get one point; the 0-1
# precheck rate gets one point of a hundred.
DEFAULT_MIN_THRESHOLD = 1.0
MIN_THRESHOLD = {"precheck_pass_rate": 0.01}


def compare_runs(runs: list[dict]) -> dict:
    """Delta report across two or more runs of the same dataset.

    Reports per-row score deltas and which rows flipped precheck or crossed the
    judge threshold; per-dimension deltas so a regression is attributable to a
    specific rubric dimension; and any rows present in one run but not another.
    """
    if len(runs) < 2:
        raise ValueError(f"compare_runs needs at least two runs, got {len(runs)}")

    noise = noise_band(runs)
    baseline = runs[0]
    return {
        "baseline": _identity(baseline),
        "runs": [_identity(run) for run in runs],
        "noise": noise,
        "comparisons": [_compare_pair(baseline, run, noise) for run in runs[1:]],
    }


def group_by_prompt(runs: list[dict]) -> dict:
    """Group runs by `system_prompt_hash`, chronologically by first-seen.

    The "did my edit help?" view: a sequence of prompt versions with each one's
    aggregate and a met/not-met flag against the baseline, so a series of edits
    reads as a trend rather than a pile of runs.
    """
    grouped: dict[object, list[dict]] = {}
    first_seen: dict[object, str] = {}
    for run in _chronological(runs):
        prompt_hash = run.get("system_prompt_hash")
        grouped.setdefault(prompt_hash, []).append(run)
        first_seen.setdefault(prompt_hash, _timestamp(run))

    order = sorted(grouped, key=lambda prompt_hash: first_seen[prompt_hash])
    groups = {
        prompt_hash: _prompt_group(prompt_hash, grouped[prompt_hash], first_seen[prompt_hash])
        for prompt_hash in order
    }
    target = groups[order[0]]["average_score"] if order else None
    for group in groups.values():
        group["target"] = target
        group["target_met"] = _target_met(group["average_score"], target)

    return {
        "baseline": order[0] if order else None,
        "target": target,
        "order": order,
        "groups": groups,
    }


def noise_band(runs: list[dict]) -> dict:
    """Observed run-to-run variance, from repeats of one config + prompt hash.

    `compare_runs` uses this to refuse to call a delta an improvement when it
    sits inside the band. Reading noise as progress is as damaging as a judge
    that returns a constant, and more seductive because it looks like the loop
    is working.
    """
    groups = _repeat_groups(runs)
    metrics = _bands(groups, _metric_values)
    dimensions = _bands(groups, _dimension_values)
    headline = metrics.get(HEADLINE_METRIC)
    return {
        "band": headline,
        "verdict": "ok" if headline else "unknown-variance",
        "reason": None
        if headline
        else (
            "no two runs share a config_hash and system_prompt_hash, so run-to-run "
            f"variance in {HEADLINE_METRIC} was never observed and no delta can be "
            "called real"
        ),
        "repeat_groups": [
            {
                "config_hash": group[0].get("config_hash"),
                "system_prompt_hash": group[0].get("system_prompt_hash"),
                "runs": [_run_id(run) for run in group],
            }
            for group in groups
        ],
        "metrics": metrics,
        "dimensions": dimensions,
    }


# ── run identity and payload access ───────────────────────────────────────


def _run_id(run: dict) -> str | None:
    """A run's stable id, tolerating either id field name."""
    return run.get("dataset_run_id") or run.get("run_id") or run.get("id")


def _timestamp(run: dict) -> str:
    """A run's wall-clock start, used only for chronological ordering."""
    return run.get("timestamp") or run.get("created_at") or ""


def _chronological(runs: list[dict]) -> list[dict]:
    """Runs oldest-first, so "first seen" means earliest, not first in the list."""
    ordered = sorted(enumerate(runs), key=lambda pair: (_timestamp(pair[1]), pair[0]))
    return [run for _, run in ordered]


def _summary(run: dict) -> dict:
    """The `scoring.summarize_stage` payload carried by a run."""
    summary = run.get("summary") or run.get("score")
    return summary if isinstance(summary, dict) else {}


def _identity(run: dict) -> dict:
    """The fields that say which run this is and what spec produced it."""
    return {
        "run_id": _run_id(run),
        "timestamp": _timestamp(run),
        "config_hash": run.get("config_hash"),
        "system_prompt_hash": run.get("system_prompt_hash"),
    }


def _metric_values(run: dict) -> dict[str, float | None]:
    """This run's aggregate metrics, flattened out of the summary."""
    summary = _summary(run)
    scores = summary.get("scores") or {}
    values = {name: scores.get(name) for name in AGGREGATE_METRICS}
    values["precheck_pass_rate"] = summary.get("precheck_pass_rate")
    return values


def _dimension_values(run: dict) -> dict[str, float | None]:
    """This run's per-dimension means — the attributable half of a regression."""
    dimensions = _summary(run).get("dimensions") or {}
    return {name: stats.get("mean") for name, stats in dimensions.items()}


def _rows_by_id(run: dict) -> dict[object, dict]:
    """This run's per-row results, keyed by the stable row id."""
    return {row.get("row_id"): row for row in _summary(run).get("results") or []}


# ── the noise band ────────────────────────────────────────────────────────


def _repeat_groups(runs: list[dict]) -> list[list[dict]]:
    """Runs grouped into repeats of one identical spec, groups of 2 or more only."""
    grouped: dict[tuple, list[dict]] = {}
    for run in runs:
        key = (run.get("config_hash"), run.get("system_prompt_hash"))
        grouped.setdefault(key, []).append(run)
    return [group for group in grouped.values() if len(group) > 1]


def _threshold_floor(key: str) -> float:
    """The smallest threshold this metric is allowed to have."""
    return MIN_THRESHOLD.get(key, DEFAULT_MIN_THRESHOLD)


def _bands(groups: list[list[dict]], extract) -> dict[str, dict]:
    """A band per key, pooling each repeat group's deviations from its own mean.

    Pooling within groups rather than across all runs is what keeps a real
    prompt-driven difference out of the variance estimate.
    """
    deviations: dict[str, list[float]] = {}
    samples: dict[str, int] = {}
    groups_used: dict[str, int] = {}
    group_means: dict[str, list[float]] = {}

    for group in groups:
        collected: dict[str, list[float]] = {}
        for run in group:
            for key, value in extract(run).items():
                if value is not None:
                    collected.setdefault(key, []).append(float(value))
        for key, values in collected.items():
            if len(values) < 2:
                continue
            mean = statistics.fmean(values)
            deviations.setdefault(key, []).extend(value - mean for value in values)
            samples[key] = samples.get(key, 0) + len(values)
            groups_used[key] = groups_used.get(key, 0) + 1
            group_means.setdefault(key, []).append(mean)

    bands = {}
    for key, values in deviations.items():
        degrees_of_freedom = samples[key] - groups_used[key]
        pooled = math.sqrt(sum(value * value for value in values) / degrees_of_freedom)
        bands[key] = {
            "mean": statistics.fmean(group_means[key]),
            "stddev": pooled,
            "threshold": max(SIGMA_MULTIPLIER * pooled, _threshold_floor(key)),
            "samples": samples[key],
        }
    return bands


def _verdict(delta: float | None, band: dict | None) -> str:
    """Name a delta, refusing "improved" for anything inside the noise band."""
    if delta is None:
        return "unknown"
    if delta == 0:
        return "stable"
    if band is None:
        return "unknown-variance"
    if abs(delta) <= band["threshold"]:
        return "within-noise"
    return "improved" if delta > 0 else "regressed"


# ── one pair of runs ──────────────────────────────────────────────────────


def _compare_pair(before: dict, after: dict, noise: dict) -> dict:
    """Every delta between the baseline run and one later run."""
    aggregates = _aggregate_deltas(before, after, noise["metrics"])
    rows = _row_deltas(before, after)
    return {
        "run_id": _run_id(after),
        "against": _run_id(before),
        "verdict": aggregates[HEADLINE_METRIC]["verdict"],
        "headline_metric": HEADLINE_METRIC,
        "aggregates": aggregates,
        "dimensions": _dimension_deltas(before, after, noise["dimensions"]),
        "rows": rows,
        "precheck_flips": [row for row in rows if row["precheck_flip"]],
        "threshold_crossings": [row for row in rows if row["threshold_cross"]],
        "only_in_baseline": _missing(before, after),
        "only_in_run": _missing(after, before),
    }


def _delta(before: float | None, after: float | None) -> float | None:
    """after - before, or None when either side is missing."""
    if before is None or after is None:
        return None
    return float(after) - float(before)


def _entry(before, after, band: dict | None) -> dict:
    """One before/after/delta line with its noise-aware verdict."""
    delta = _delta(before, after)
    return {
        "before": before,
        "after": after,
        "delta": delta,
        "verdict": _verdict(delta, band),
        "band": band,
    }


def _aggregate_deltas(before: dict, after: dict, bands: dict) -> dict:
    """Each aggregate's move, verdicted against that metric's own band."""
    before_values = _metric_values(before)
    after_values = _metric_values(after)
    return {
        name: _entry(before_values.get(name), after_values.get(name), bands.get(name))
        for name in AGGREGATE_METRICS
    }


def _dimension_deltas(before: dict, after: dict, bands: dict) -> dict:
    """Each rubric dimension's move — which paragraph of the AGENT.md to rewrite."""
    before_values = _dimension_values(before)
    after_values = _dimension_values(after)
    names = sorted(set(before_values) | set(after_values))
    return {
        name: _entry(before_values.get(name), after_values.get(name), bands.get(name))
        for name in names
    }


def _flip(before: object, after: object) -> str | None:
    """Name a boolean flip in either direction, or None when it did not move."""
    if before is None or after is None or bool(before) == bool(after):
        return None
    return "fail->pass" if after else "pass->fail"


def _row_deltas(before: dict, after: dict) -> list[dict]:
    """Per-row score deltas plus precheck and judge-threshold flips."""
    before_rows = _rows_by_id(before)
    after_rows = _rows_by_id(after)
    rows = []
    for row_id in sorted(set(before_rows) & set(after_rows), key=str):
        before_row = before_rows[row_id]
        after_row = after_rows[row_id]
        rows.append(
            {
                "row_id": row_id,
                "before": before_row.get("score"),
                "after": after_row.get("score"),
                "delta": _delta(before_row.get("score"), after_row.get("score")),
                "precheck_flip": _flip(
                    before_row.get("precheck_passed"), after_row.get("precheck_passed")
                ),
                "threshold_cross": _flip(before_row.get("passed"), after_row.get("passed")),
            }
        )
    return rows


def _missing(present: dict, absent: dict) -> list:
    """Row ids in one run but not the other — reported, never silently dropped."""
    return sorted(set(_rows_by_id(present)) - set(_rows_by_id(absent)), key=str)


# ── prompt versions ───────────────────────────────────────────────────────


def _prompt_group(prompt_hash: object, group: list[dict], first_seen: str) -> dict:
    """One prompt version's aggregate across every run that used it."""
    averages = [
        value
        for value in (_metric_values(run)[HEADLINE_METRIC] for run in group)
        if value is not None
    ]
    rates = [
        value
        for value in (_metric_values(run)["precheck_pass_rate"] for run in group)
        if value is not None
    ]
    return {
        "system_prompt_hash": prompt_hash,
        "first_seen": first_seen,
        "runs": [_run_id(run) for run in group],
        "total_runs": len(group),
        "average_score": statistics.fmean(averages) if averages else None,
        "precheck_pass_rate": statistics.fmean(rates) if rates else None,
    }


def _target_met(average: float | None, target: float | None) -> bool | None:
    """Whether this prompt version held the baseline version's average."""
    if average is None or target is None:
        return None
    return average >= target
