"""Pure aggregation: turn per-row results into numbers you can act on.

Takes plain dicts (the run/grade artifact shapes), returns plain dicts. No I/O,
no model calls, no imports from this package — this is the file you read to
understand what a score means, and the one whose silent failure costs a run.
"""

from __future__ import annotations

import re
import statistics

# Words every weakness sentence carries; keeping them would cluster unrelated
# criticisms together purely because both are written in English.
STOPWORDS = frozenset(
    {
        "also",
        "been",
        "being",
        "could",
        "does",
        "from",
        "have",
        "here",
        "into",
        "just",
        "more",
        "most",
        "much",
        "only",
        "page",
        "pages",
        "should",
        "some",
        "spec",
        "such",
        "than",
        "that",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "very",
        "what",
        "when",
        "which",
        "while",
        "with",
        "would",
    }
)

# Two weaknesses belong together when this share of the smaller token set is
# shared. Deliberately a flat threshold: explainable beats clever.
CLUSTER_OVERLAP = 0.5

# The hashes a baseline must match before its thresholds mean anything.
HASH_NAMES = ("config", "rubric", "dataset")


def weighted_total(sub_scores: dict[str, int], dimensions: list[dict]) -> float:
    """Weighted 0-100 total: sum(score_i * weight_i) / 100.

    Each dimension is scored 0-100 by the judge; weights (summing to 100) are
    applied here, never baked into the judge schema — so a weight edit is
    recomputable over stored sub-scores instead of requiring a re-run.
    """
    total = 0.0
    for dimension in dimensions:
        dimension_id = dimension["id"]
        if dimension_id not in sub_scores:
            raise ValueError(
                f"sub_scores is missing rubric dimension {dimension_id!r}; "
                f"got {sorted(sub_scores)}"
            )
        total += float(sub_scores[dimension_id]) * float(dimension["weight"])
    return total / 100.0


def summarize_stage(runs: list[dict], grades: list[dict], rubric: dict) -> dict:
    """Aggregate one stage into its `score.json` payload.

    Reports: counts; `precheck_pass_rate` over `expect: pass` rows only;
    `negative_rows_correct` for `expect: fail` rows (correct = precheck_passed
    != expected-fail); `average_precheck_passed`, `average_all` and
    `average_clean_chain` (rows whose whole upstream chain passed);
    stddev/min/max/median/`distinct_scores`; PER-DIMENSION aggregates; and
    `recurring_weaknesses` — judge weaknesses clustered across rows with row ids
    and quoted evidence, ranked by frequency.
    """
    dimensions = rubric.get("dimensions") or []
    warnings: list[str] = []
    rows = _join(runs, grades, dimensions, warnings)

    positive_rows = [row for row in rows if row["expect"] != "fail"]
    negative_rows = [row for row in rows if row["expect"] == "fail"]
    scored_rows = [row for row in rows if row["score"] is not None]

    summary = {
        "counts": _counts(rows),
        "precheck_pass_rate": _rate(
            sum(1 for row in positive_rows if row["precheck_passed"] is True),
            len(positive_rows),
        ),
        "negative_rows_correct": _negative_rows_correct(negative_rows),
        "scores": _score_stats(scored_rows),
        "dimensions": _dimension_stats(rows, dimensions),
        "recurring_weaknesses": _cluster_weaknesses(rows),
        "signals": _signals(rows),
        "tokens": _tokens(rows),
        "results": [_result(row) for row in rows],
    }
    warnings.extend(_warnings(rows, scored_rows, summary, rubric.get("anchors") or {}))
    summary["warnings"] = warnings
    return summary


def evaluate_baseline(summary: dict, baseline: dict, hashes: dict) -> dict:
    """PASS/FAIL verdict against the rubric's committed baseline.

    Checks min_precheck_pass_rate, min_average_score, min_negative_correct,
    min_distinct_scores and max_expected_stddev — the last two are a two-sided
    signal guard: a judge returning one value is dead, an implausibly tight
    spread is dying. REFUSES to evaluate (verdict "REFUSED") when any of the
    config/rubric/dataset hashes differs from what `baseline.set_from` recorded,
    or when the judge resolved to a model other than the pinned one.
    """
    thresholds = {
        name: baseline.get(name)
        for name in (
            "min_precheck_pass_rate",
            "min_average_score",
            "min_negative_correct",
            "min_distinct_scores",
            "max_expected_stddev",
        )
    }
    refusals = _refusals(baseline.get("set_from"), hashes)
    if refusals:
        return {**thresholds, "verdict": "REFUSED", "failures": refusals}

    failures = _threshold_failures(summary, thresholds)
    return {
        **thresholds,
        "verdict": "FAIL" if failures else "PASS",
        "failures": failures,
    }


# ── joining runs and grades ───────────────────────────────────────────────


def judge_errored(grade: dict) -> bool:
    """Whether the judge failed on this row, reading either key spelling.

    Grade entries name it `judge_errored`; folders written before that rename
    used a bare `errored` that collided with run.json's dispatch error. Reading
    both keeps every stored run readable.
    """
    if not grade:
        return False
    return bool(grade.get("judge_errored", grade.get("errored")))


def judge_error_reason(grade: dict):
    """The judge's failure reason, reading either key spelling."""
    if not grade:
        return None
    return grade.get("judge_error_reason", grade.get("error_reason"))


def _row_id(entry: dict) -> str | None:
    """The join key for a run or grade entry, tolerating either id field name."""
    return entry.get("scenario_id") or entry.get("row_id") or entry.get("id")


def _join(
    runs: list[dict], grades: list[dict], dimensions: list[dict], warnings: list[str]
) -> list[dict]:
    """Join runs to grades by row id into one flat dict per row."""
    grades_by_id = {_row_id(grade): grade for grade in grades}
    rows = []
    for run in runs:
        row_id = _row_id(run)
        grade = grades_by_id.get(row_id, {})
        chain = run.get("upstream_chain") or []
        rows.append(
            {
                "row_id": row_id,
                "expect": run.get("expect") or "pass",
                "errored": bool(run.get("errored")),
                "skip_reason": run.get("skip_reason") or grade.get("skipped_reason"),
                "precheck_passed": grade.get("precheck_passed", run.get("precheck_passed")),
                "judged": bool(grade.get("judged")),
                # The JUDGE's own failure, distinct from the dispatch's `errored`
                # above: the agent answered fine and the grader is what broke.
                "signal": run.get("signal"),
                "judge_errored": judge_errored(grade),
                "judge_error_reason": judge_error_reason(grade),
                "sub_scores": grade.get("sub_scores"),
                "score": _row_score(row_id, grade, dimensions, warnings),
                "passed": grade.get("passed"),
                "weaknesses": grade.get("weaknesses") or [],
                "clean_chain": all(step.get("precheck_passed") is True for step in chain),
                "tokens_in": run.get("tokens_in") or 0,
                "tokens_out": run.get("tokens_out") or 0,
                "judge_tokens_in": grade.get("judge_tokens_in") or 0,
                "judge_tokens_out": grade.get("judge_tokens_out") or 0,
            }
        )
    return rows


def _row_score(
    row_id: str | None, grade: dict, dimensions: list[dict], warnings: list[str]
) -> float | None:
    """One row's total: recomputed from stored sub-scores when possible."""
    sub_scores = grade.get("sub_scores")
    stored = grade.get("score")
    if not isinstance(sub_scores, dict) or not dimensions:
        return stored
    missing = [dimension["id"] for dimension in dimensions if dimension["id"] not in sub_scores]
    if missing:
        warnings.append(
            f"SUB-SCORES INCOMPLETE: row {row_id} is missing dimension(s) "
            f"{', '.join(missing)}; the stored total was used instead."
        )
        return stored
    return weighted_total(sub_scores, dimensions)


# ── aggregates ────────────────────────────────────────────────────────────


def _rate(part: int, whole: int) -> float | None:
    """A ratio, or None when there is nothing to divide by."""
    return part / whole if whole else None


def _mean(values: list[float]) -> float | None:
    """Arithmetic mean, or None for an empty list."""
    return statistics.fmean(values) if values else None


def _counts(rows: list[dict]) -> dict:
    """Row-level counts: dispatched, errored, prechecked, judged."""
    return {
        "rows": len(rows),
        "dispatched": sum(1 for row in rows if not row["skip_reason"]),
        "errored": sum(1 for row in rows if row["errored"]),
        "precheck_passed": sum(1 for row in rows if row["precheck_passed"] is True),
        "precheck_failed": sum(1 for row in rows if row["precheck_passed"] is False),
        "judged": sum(1 for row in rows if row["judged"]),
        "judge_errored": sum(1 for row in rows if row["judge_errored"]),
    }


def _negative_rows_correct(negative_rows: list[dict]) -> dict:
    """`expect: fail` outcomes — correct means the precheck did NOT pass them."""
    correct = sum(1 for row in negative_rows if row["precheck_passed"] is not True)
    return {
        "correct": correct,
        "total": len(negative_rows),
        "rate": _rate(correct, len(negative_rows)),
    }


def _score_stats(scored_rows: list[dict]) -> dict:
    """The three averages plus spread — the two-sided signal guard's inputs."""
    scores = [row["score"] for row in scored_rows]
    distinct = sorted({round(score, 6) for score in scores})
    return {
        "average_precheck_passed": _mean(
            [row["score"] for row in scored_rows if row["precheck_passed"] is True]
        ),
        "average_all": _mean(scores),
        "average_clean_chain": _mean(
            [row["score"] for row in scored_rows if row["clean_chain"]]
        ),
        "median": statistics.median(scores) if scores else None,
        "min": min(scores) if scores else None,
        "max": max(scores) if scores else None,
        "stddev": statistics.pstdev(scores) if scores else None,
        "distinct_scores": distinct,
        "distinct_score_count": len(distinct),
    }


def _dimension_stats(rows: list[dict], dimensions: list[dict]) -> dict:
    """Per-dimension mean/median/stddev/min/max — which paragraph to rewrite."""
    stats = {}
    for dimension in dimensions:
        dimension_id = dimension["id"]
        values = [
            float(row["sub_scores"][dimension_id])
            for row in rows
            if isinstance(row["sub_scores"], dict) and dimension_id in row["sub_scores"]
        ]
        stats[dimension_id] = {
            "count": len(values),
            "mean": _mean(values),
            "median": statistics.median(values) if values else None,
            "stddev": statistics.pstdev(values) if values else None,
            "min": min(values) if values else None,
            "max": max(values) if values else None,
        }
    return stats


def _signals(rows: list[dict]) -> dict:
    """Count each declared verdict value, and how many rows raised an alert.

    A stage whose output nothing consumes can still be saying something the run
    should not march past — this is what makes it countable.
    """
    values: dict[str, int] = {}
    alerts = []
    name = None
    for row in rows:
        signal = row.get("signal")
        if not signal:
            continue
        name = signal.get("name")
        value = str(signal.get("value"))
        values[value] = values.get(value, 0) + 1
        if signal.get("alert"):
            alerts.append(row["row_id"])
    if not values:
        return {}
    return {"name": name, "counts": values, "alert_rows": alerts}


def _tokens(rows: list[dict]) -> dict:
    """Token totals across the stage, split by who spent them.

    `in`/`out`/`total` cover the WHOLE stage — agent plus judge. They used to
    count the agent only, which under-stated a judged run by roughly half and
    made every cost estimate wrong. The breakdown keeps both attributable.
    """
    agent = _token_pair(rows, "tokens_in", "tokens_out")
    judge = _token_pair(rows, "judge_tokens_in", "judge_tokens_out")
    return {
        "in": agent["in"] + judge["in"],
        "out": agent["out"] + judge["out"],
        "total": agent["total"] + judge["total"],
        "agent": agent,
        "judge": judge,
    }


def _token_pair(rows: list[dict], in_key: str, out_key: str) -> dict:
    """One spender's in/out/total across every row."""
    tokens_in = sum(row.get(in_key) or 0 for row in rows)
    tokens_out = sum(row.get(out_key) or 0 for row in rows)
    return {"in": tokens_in, "out": tokens_out, "total": tokens_in + tokens_out}


def _result(row: dict) -> dict:
    """The per-row line kept in the payload for drill-down."""
    return {
        "row_id": row["row_id"],
        "expect": row["expect"],
        "errored": row["errored"],
        "precheck_passed": row["precheck_passed"],
        "clean_chain": row["clean_chain"],
        "score": row["score"],
        "passed": row["passed"],
    }


# ── weakness clustering ───────────────────────────────────────────────────


def _tokenize(text: str) -> frozenset[str]:
    """Meaningful lowercase tokens of a weakness — its clustering signature."""
    words = re.sub(r"[^a-z0-9]+", " ", text.lower()).split()
    return frozenset(word for word in words if len(word) > 3 and word not in STOPWORDS)


def _cluster_weaknesses(rows: list[dict]) -> list[dict]:
    """Cluster judge weaknesses across rows, ranked by how many rows show them."""
    clusters: list[dict] = []
    for row in rows:
        for weakness in row["weaknesses"]:
            tokens = _tokenize(weakness)
            if not tokens:
                continue
            cluster = _matching_cluster(clusters, tokens)
            if cluster is None:
                clusters.append(
                    {"tokens": tokens, "row_ids": [row["row_id"]], "evidence": weakness}
                )
            elif row["row_id"] not in cluster["row_ids"]:
                cluster["row_ids"].append(row["row_id"])

    ranked = sorted(clusters, key=lambda cluster: -len(cluster["row_ids"]))
    return [
        {
            "keywords": sorted(cluster["tokens"]),
            "count": len(cluster["row_ids"]),
            "row_ids": cluster["row_ids"],
            "evidence": cluster["evidence"],
        }
        for cluster in ranked
    ]


def _matching_cluster(clusters: list[dict], tokens: frozenset[str]) -> dict | None:
    """The first cluster sharing enough tokens with `tokens`, if any."""
    for cluster in clusters:
        shared = len(cluster["tokens"] & tokens)
        smaller = min(len(cluster["tokens"]), len(tokens))
        if smaller and shared / smaller >= CLUSTER_OVERLAP:
            return cluster
    return None


# ── warnings ──────────────────────────────────────────────────────────────

# A judge that only ever emits two numbers has almost no resolution, however
# many distinct WEIGHTED totals that arithmetic produces downstream.
MIN_SUB_SCORE_VOCABULARY = 3


def _resolution_warnings(scored_rows: list[dict], anchors: dict) -> list[str]:
    """Catch a judge whose totals look varied but whose sub-scores are not.

    Weighting 40/40/20 turns two sub-score values into several distinct totals,
    so `distinct_score_count` can look healthy while the judge is really
    choosing between "90" and "95". These read the sub-scores directly.
    """
    values = sorted(
        {
            value
            for row in scored_rows
            if isinstance(row["sub_scores"], dict)
            for value in row["sub_scores"].values()
        }
    )
    if not values or len(scored_rows) < 2:
        return []

    warnings = []
    if len(values) < MIN_SUB_SCORE_VOCABULARY:
        warnings.append(
            f"LOW JUDGE RESOLUTION: across {len(scored_rows)} rows the judge used only "
            f"{len(values)} distinct sub-score value(s) — {values}. The weighted totals "
            "look more varied than the judgement behind them; a small regression would "
            "not move them."
        )
    top_band = _top_anchor(anchors)
    if top_band is not None and min(values) >= top_band:
        warnings.append(
            f"SCORE CEILING: every sub-score sits in the top anchor band (>= {top_band}), "
            "so the rubric is not distinguishing good from excellent. There is no room "
            "left to reward an improvement."
        )
    return warnings


def _top_anchor(anchors: dict) -> int | None:
    """The highest anchor band in the rubric, or None when none are defined."""
    bands = [int(band) for band in anchors if str(band).lstrip("-").isdigit()]
    return max(bands) if bands else None


def _warnings(
    rows: list[dict], scored_rows: list[dict], summary: dict, anchors: dict
) -> list[str]:
    """Conditions that make a headline number untrustworthy."""
    warnings = []
    stats = summary["scores"]
    if len(scored_rows) > 1 and stats["distinct_score_count"] == 1:
        warnings.append(
            f"NO JUDGE SIGNAL: all {len(scored_rows)} scored rows returned exactly "
            f"{stats['distinct_scores'][0]} (stddev 0.0, 1 distinct value). This run "
            "could not have detected any regression."
        )
    warnings.extend(_resolution_warnings(scored_rows, anchors))
    # A judge that errors on every row leaves the same empty aggregates as
    # `no_judge: true`. Without this the run prints "no judge" and exits 0 —
    # a total grading failure indistinguishable from a config choice.
    judge_failed = [row["row_id"] for row in rows if row["judge_errored"]]
    if judge_failed:
        reason = next(
            (row["judge_error_reason"] for row in rows if row["judge_errored"]), "unknown"
        )
        warnings.append(
            f"JUDGE FAILED: {len(judge_failed)} row(s) "
            f"({', '.join(str(row_id) for row_id in judge_failed)}) were dispatched and "
            f"sent to the judge, but the judge returned no usable verdict. These rows cost "
            f"tokens and produced no score. First reason: {str(reason).splitlines()[0]}"
        )
    judged_after_failure = [
        row["row_id"] for row in rows if row["judged"] and row["precheck_passed"] is False
    ]
    if judged_after_failure:
        warnings.append(
            f"JUDGE RAN ON PRECHECK-FAILED ROWS: {len(judged_after_failure)} row(s) "
            f"({', '.join(str(row_id) for row_id in judged_after_failure)}) were scored "
            "despite failing the precheck, and are folded into the averages."
        )
    if scored_rows and not any(isinstance(row["sub_scores"], dict) for row in scored_rows):
        warnings.append(
            "SUB-SCORES ABSENT: no row carries per-dimension scores, so no dimension can "
            "be attributed and no weight change can be recomputed."
        )
    starved = [
        row["row_id"]
        for row in rows
        if not row["errored"] and not row["skip_reason"] and not row["tokens_out"]
    ]
    if starved:
        warnings.append(
            f"TOKENS UNDER-REPORTED: {len(starved)} dispatched row(s) report zero output "
            "tokens — usual for tool-using agents, so the totals are a lower bound."
        )
    return warnings


# ── baseline ──────────────────────────────────────────────────────────────


def _refusals(set_from: object, hashes: dict) -> list[str]:
    """Reasons this run is not comparable to the baseline's calibration run."""
    if not isinstance(set_from, dict):
        return [
            f"baseline is not calibrated: set_from is {set_from!r}, not a record of the "
            "calibration run's hashes"
        ]

    refusals = []
    for name in HASH_NAMES:
        recorded = set_from.get(f"{name}_hash", set_from.get(name))
        actual = hashes.get(f"{name}_hash", hashes.get(name))
        if recorded is not None and actual != recorded:
            refusals.append(
                f"{name}_hash {actual!r} differs from the calibrated {recorded!r} — "
                "this run is not comparable to the baseline"
            )

    pinned = set_from.get("judge_resolved_model_id") or hashes.get("judge_pinned_model_id")
    resolved = hashes.get("judge_resolved_model_id")
    if pinned and resolved and resolved != pinned:
        refusals.append(
            f"judge resolved to {resolved!r}, not the pinned {pinned!r} — an "
            "uncalibrated judge makes the scores non-comparable"
        )
    return refusals


def _threshold_failures(summary: dict, thresholds: dict) -> list[str]:
    """The baseline checks this summary fails, each named with its numbers."""
    stats = summary.get("scores") or {}
    failures = []

    pass_rate = summary.get("precheck_pass_rate")
    minimum = thresholds["min_precheck_pass_rate"]
    if minimum is not None and pass_rate is not None and pass_rate < minimum:
        failures.append(f"precheck_pass_rate {pass_rate:.2f} < {minimum:.2f}")

    average = stats.get("average_precheck_passed")
    if average is None:
        average = stats.get("average_all")
    minimum = thresholds["min_average_score"]
    if minimum is not None and average is not None and average < minimum:
        failures.append(f"average_score {average:.2f} < {minimum}")

    negative = summary.get("negative_rows_correct") or {}
    minimum = thresholds["min_negative_correct"]
    if minimum is not None and negative.get("rate") is not None and negative["rate"] < minimum:
        failures.append(
            f"negative_rows_correct {negative['correct']}/{negative['total']} "
            f"({negative['rate']:.2f}) < {minimum:.2f}"
        )

    distinct = stats.get("distinct_score_count")
    minimum = thresholds["min_distinct_scores"]
    if minimum is not None and distinct is not None and distinct < minimum:
        failures.append(
            f"distinct_score_count {distinct} < {minimum} (the judge is returning too few "
            "distinct values to detect a regression)"
        )

    stddev = stats.get("stddev")
    maximum = thresholds["max_expected_stddev"]
    if maximum is not None and stddev is not None and stddev > maximum:
        failures.append(f"stddev {stddev:.2f} > max_expected_stddev {maximum}")

    return failures
