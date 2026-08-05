"""Pure aggregation and comparison: did editing the prompt actually help?

Zero I/O, no imports from this package, no model calls — `aggregate()` and
`compare()` only ever look at the dicts they're handed. `noise_band()` and
`compare_runs()` are ported unmodified from `_source/compare.py`; they were
the one component of the old system that reliably told the truth, so only
their data-access helpers (`_aggregate`, `_metric_values`) were adapted to
the new, flatter run shape:

    {"run_id": ..., "system_prompt_hash": ..., "config_hash": ...,
     "timestamp": ..., "aggregate": {"mean", "median", "stddev", "n", "distinct"}}
"""

from __future__ import annotations

import math
import statistics

# stddev/n/distinct ride along for the dead-judge guard, not as quality
# signals; mean is the headline metric everything else verdicts against.
AGGREGATE_METRICS = ("mean", "median", "stddev", "n", "distinct")
HEADLINE_METRIC = "mean"

# ~95% coverage of a roughly normal noise distribution, deliberately
# conservative: a false "improved" gets written into an AGENT.md and stays,
# a false "within-noise" only costs one more run.
SIGMA_MULTIPLIER = 2.0
# Smallest move worth calling real even if repeats happen to agree exactly.
DEFAULT_MIN_THRESHOLD = 1.0
MIN_THRESHOLD: dict[str, float] = {}


def aggregate(rows: list[dict]) -> dict:
    """Summarize a list of scored rows into the shape `compare()` reads.

    `n` is the row count; `distinct` counts distinct score values — the
    dead-judge guard, since a judge returning the same score every time
    should be visible rather than averaging away.
    """
    scores = [float(row["score"]) for row in rows]
    return {
        "mean": statistics.fmean(scores) if scores else None,
        "median": statistics.median(scores) if scores else None,
        "stddev": statistics.stdev(scores) if len(scores) > 1 else 0.0,
        "n": len(rows),
        "distinct": len(set(scores)),
    }


def compare(a: dict, b: dict, *others: dict) -> dict:
    """Noise-guarded delta between two (or more) runs.

    Refuses outright — R-05 — when either `a` or `b` has fewer than two
    samples in its `aggregate()`; a comparison against an unsampled arm is a
    guess, not a result. Additional runs may be passed to compute the noise
    band across a larger repeat set; the verdict is always `a` vs `b`.
    """
    for label, run in (("a", a), ("b", b)):
        n = (run.get("aggregate") or {}).get("n")
        if n is None or n < 2:
            return {
                "error": (
                    f"compare refuses: arm '{label}' ({_run_id(run)!r}) has "
                    f"n={n!r} samples, need n>=2 (R-05)"
                )
            }
    return compare_runs([a, b, *others])


def compare_runs(runs: list[dict]) -> dict:
    """Delta report across two or more runs of the same dataset.

    Reports each aggregate metric's move, verdicted against that metric's
    own noise band, for every later run against the first (`runs[0]`).
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


def noise_band(runs: list[dict]) -> dict:
    """Observed run-to-run variance, from repeats of one config + prompt hash.

    `compare_runs` uses this to refuse to call a delta an improvement when it
    sits inside the band. Reading noise as progress is as damaging as a judge
    that returns a constant, and more seductive because it looks like the
    loop is working.
    """
    groups = _repeat_groups(runs)
    metrics = _bands(groups, _metric_values)
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
    }


# ── run identity and payload access ───────────────────────────────────────


def _run_id(run: dict) -> str | None:
    """A run's stable id, tolerating either id field name."""
    return run.get("run_id") or run.get("id")


def _timestamp(run: dict) -> str:
    """A run's wall-clock start, used only for chronological ordering."""
    return run.get("timestamp") or run.get("created_at") or ""


def _identity(run: dict) -> dict:
    """The fields that say which run this is and what spec produced it."""
    return {
        "run_id": _run_id(run),
        "timestamp": _timestamp(run),
        "config_hash": run.get("config_hash"),
        "system_prompt_hash": run.get("system_prompt_hash"),
    }


def _aggregate(run: dict) -> dict:
    """This run's stored `aggregate()` payload."""
    payload = run.get("aggregate")
    return payload if isinstance(payload, dict) else {}


def _metric_values(run: dict) -> dict[str, float | None]:
    """This run's aggregate metrics, flattened out of `aggregate`."""
    values = _aggregate(run)
    return {name: values.get(name) for name in AGGREGATE_METRICS}


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
    """Every aggregate-metric delta between the baseline run and one later run."""
    aggregates = _aggregate_deltas(before, after, noise["metrics"])
    return {
        "run_id": _run_id(after),
        "against": _run_id(before),
        "verdict": aggregates[HEADLINE_METRIC]["verdict"],
        "headline_metric": HEADLINE_METRIC,
        "aggregates": aggregates,
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
    """Each aggregate metric's move, verdicted against that metric's own band."""
    before_values = _metric_values(before)
    after_values = _metric_values(after)
    return {
        name: _entry(before_values.get(name), after_values.get(name), bands.get(name))
        for name in AGGREGATE_METRICS
    }
