"""model_graded/report.py — per-run report files, readable in place.

Each run gets its own small, pretty-printed JSON files inside ITS OWN log
folder (``model_graded/logs/<run_id>/``) — ``run.json`` (what was asked,
what came back, the deterministic pre-check result) and ``grade.json``
(the judge's score/verdict/strengths/weaknesses), rather than one
ever-growing shared file. Opening either file directly in an editor shows
exactly one run's data, not a giant single-line JSONL blob.

The "report" (summarize/worst/by-hash) is a VIEW computed by scanning every
run folder under ``model_graded/logs/`` and merging each run's ``run.json``
with its ``grade.json`` (when present) — there is no separate accumulating
store to keep in sync.

Pure data plumbing: no model calls, no agent knowledge, no import of
``driver.py``/``judge.py``/``precheck.py``/``build_model``/``create_runner``
(Component Boundaries).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

_MODEL_GRADED_ROOT = Path(__file__).resolve().parent
DEFAULT_LOGS_ROOT = _MODEL_GRADED_ROOT / "logs"

RUN_FILENAME = "run.json"
GRADE_FILENAME = "grade.json"

REQUIRED_RUN_FIELDS = (
    "timestamp",
    "run_id",
    "scenario_id",
    "agent_id",
    "provider",  # what was REQUESTED via --provider (often None — the default chain)
    "model",  # what was REQUESTED via --model (often None)
    "resolved_model_id",  # what ACTUALLY ran, off the built model instance — always populated
    "system_prompt_path",
    "system_prompt_hash",
    "prompt",
    "response",
    "precheck_passed",
    "precheck_reason",
    "tokens_in",
    "tokens_out",
)

REQUIRED_GRADE_FIELDS = (
    "run_id",
    "judge_provider",  # what was REQUESTED via --judge-provider (often None)
    "judge_model",  # what was REQUESTED via --judge-model (often None)
    "judge_resolved_model_id",  # what ACTUALLY graded — always populated
    "judge_threshold",
    "score",
    "passed",
    "rationale",
    "strengths",
    "weaknesses",
    "errored",
    "error_reason",
)


def compute_system_prompt_hash(system_prompt_path: str) -> str:
    """``sha256:<hex>`` of the on-disk file at ``system_prompt_path``,
    computed fresh every call — never cached — so runs can detect prompt
    drift between them.
    """
    content = Path(system_prompt_path).read_bytes()
    return "sha256:" + hashlib.sha256(content).hexdigest()


def write_run(run_dir: Path, run: dict) -> None:
    """Write ``run_dir/run.json`` — the record of what was asked and what
    came back for ONE run. Raises on any missing required field BEFORE
    writing. Pretty-printed (indent=2) so it's directly readable.
    """
    missing = [f for f in REQUIRED_RUN_FIELDS if f not in run]
    if missing:
        raise ValueError(f"run entry missing required field(s): {missing}")

    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / RUN_FILENAME).write_text(
        json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_grade(run_dir: Path, grade: dict) -> None:
    """Write ``run_dir/grade.json`` — the judge's verdict for ONE run.
    Raises on any missing required field BEFORE writing.
    """
    missing = [f for f in REQUIRED_GRADE_FIELDS if f not in grade]
    if missing:
        raise ValueError(f"grade entry missing required field(s): {missing}")

    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / GRADE_FILENAME).write_text(
        json.dumps(grade, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


SCORE_FILENAME = "score.json"


def write_batch_run(run_dir: Path, runs: list[dict]) -> None:
    """Write ``run_dir/run.json`` as a JSON ARRAY — one entry per dataset
    item — for a single "one run per dataset" invocation (as opposed to
    ``write_run``'s one-dict-per-file shape for a single scenario run).
    Each entry is validated against ``REQUIRED_RUN_FIELDS`` before anything
    is written.
    """
    for i, run in enumerate(runs):
        missing = [f for f in REQUIRED_RUN_FIELDS if f not in run]
        if missing:
            raise ValueError(f"run entry [{i}] missing required field(s): {missing}")

    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / RUN_FILENAME).write_text(
        json.dumps(runs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_batch_grade(run_dir: Path, grades: list[dict]) -> None:
    """Write ``run_dir/grade.json`` as a JSON ARRAY — one entry per dataset
    item, aligned with ``write_batch_run``'s array (same ``run_id`` values).
    """
    for i, grade in enumerate(grades):
        missing = [f for f in REQUIRED_GRADE_FIELDS if f not in grade]
        if missing:
            raise ValueError(f"grade entry [{i}] missing required field(s): {missing}")

    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / GRADE_FILENAME).write_text(
        json.dumps(grades, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


DATASET_FILENAME = "dataset.json"


def write_dataset(run_dir: Path, entries: list[dict]) -> None:
    """Write ``run_dir/dataset.json`` — a NEXT-STAGE dataset.json artifact
    generated from a ``dataset`` run's own outputs: one ``{id, industry,
    prompt}`` entry per (non-errored) dataset item, where ``prompt`` is
    THIS stage's response — the exact shape ``load_dataset_scenarios``
    expects, so it can be dropped straight into the next pipeline agent's
    ``scenarios/dataset.json`` (paired with that agent's own
    ``_template.yaml``) with zero reformatting.
    """
    for i, entry in enumerate(entries):
        missing = [f for f in ("id", "industry", "prompt") if f not in entry]
        if missing:
            raise ValueError(f"dataset entry [{i}] missing required field(s): {missing}")

    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / DATASET_FILENAME).write_text(
        json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def write_score(run_dir: Path, score: dict) -> None:
    """Write ``run_dir/score.json`` — the batch-level summary (per-item
    score + the average) for a "one run per dataset" invocation, living in
    the SAME folder as that run's ``run.json``/``grade.json``.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / SCORE_FILENAME).write_text(
        json.dumps(score, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _flatten(run: dict, grade: dict | None) -> dict:
    """Merge one run.json + its optional grade.json into a single flat
    entry dict — the shape summarize()/worst() operate on. Keeps the same
    judge_* field names the rest of this module already used, so callers
    don't need to know about the two-file split.
    """
    entry = dict(run)
    entry["run_dir"] = str(run.get("run_dir", ""))
    if grade is None:
        entry.update(
            judge_score=None,
            judge_passed=None,
            judge_rationale=None,
            judge_strengths=None,
            judge_weaknesses=None,
            judge_resolved_model_id=None,
            judge_errored=False,
        )
    else:
        entry.update(
            judge_score=grade["score"],
            judge_passed=grade["passed"],
            judge_rationale=grade["rationale"],
            judge_strengths=grade["strengths"],
            judge_weaknesses=grade["weaknesses"],
            judge_resolved_model_id=grade.get("judge_resolved_model_id"),
            judge_errored=grade["errored"],
        )
    return entry


def load_run_entries(*, logs_root: Path | None = None) -> list[dict]:
    """Scan every ``<logs_root>/<run_id>/`` folder, read its ``run.json``
    (skipping folders without one — e.g. a folder that only ever got a
    ``log.txt`` from an errored run), merge in ``grade.json`` when present,
    and return the flattened entries oldest-first (by ``timestamp``).

    Returns an empty list if ``logs_root`` doesn't exist yet — never raises
    for that case.
    """
    if logs_root is None:
        logs_root = DEFAULT_LOGS_ROOT
    if not logs_root.exists():
        return []

    entries = []
    for run_dir in sorted(logs_root.iterdir()):
        run_file = run_dir / RUN_FILENAME
        if not run_dir.is_dir() or not run_file.exists():
            continue
        run_data = json.loads(run_file.read_text(encoding="utf-8"))

        grade_file = run_dir / GRADE_FILENAME
        grade_data = (
            json.loads(grade_file.read_text(encoding="utf-8")) if grade_file.exists() else None
        )

        if isinstance(run_data, list):
            # A batch ("one run per dataset") folder: run.json/grade.json are
            # arrays, one entry per dataset item, aligned by run_id.
            grades_by_run_id = (
                {g.get("run_id"): g for g in grade_data} if isinstance(grade_data, list) else {}
            )
            for run in run_data:
                run.setdefault("run_dir", str(run_dir))
                entries.append(_flatten(run, grades_by_run_id.get(run.get("run_id"))))
        else:
            run_data.setdefault("run_dir", str(run_dir))
            grade = grade_data if isinstance(grade_data, dict) else None
            entries.append(_flatten(run_data, grade))

    entries.sort(key=lambda e: e.get("timestamp", ""))
    return entries


def _empty_summary() -> dict:
    return {
        "total": 0,
        "precheck_pass_rate": None,
        "judge_pass_rate": None,
        "avg_judge_score": None,
        "groups": {},
    }


def _summarize_group(rows: list[dict], *, target: int | None) -> dict:
    total = len(rows)
    precheck_passes = sum(1 for r in rows if r.get("precheck_passed"))
    graded_rows = [r for r in rows if r.get("judge_score") is not None]
    judge_passes = sum(1 for r in graded_rows if r.get("judge_passed"))
    avg_score = (
        sum(r["judge_score"] for r in graded_rows) / len(graded_rows) if graded_rows else None
    )
    summary = {
        "total": total,
        "precheck_pass_rate": precheck_passes / total if total else None,
        "judge_pass_rate": judge_passes / len(graded_rows) if graded_rows else None,
        "avg_judge_score": avg_score,
    }
    if target is not None and avg_score is not None:
        summary["target"] = target
        summary["target_met"] = avg_score >= target
    return summary


def summarize(
    entries: list[dict],
    *,
    group_by: str | None = "agent_id",
    last_n: int | None = None,
    target: int | None = None,
) -> dict:
    """Aggregate stats over ``entries``: total runs, overall pre-check pass
    rate, overall judge pass rate, average judge score — plus a breakdown by
    ``group_by`` ("agent_id" | "scenario_id" | "system_prompt_hash").

    When ``group_by == "system_prompt_hash"``, groups are ordered
    chronologically by each hash's first-seen ``timestamp`` (Story 6,
    clarifications.md Q7) — a prompt-version trend, not an arbitrary order.
    ``target``, when given, adds a met/not-met flag to each group's summary.

    ``last_n`` filters to only the most recent N entries BEFORE any other
    computation. Never raises on an empty ``entries`` list.
    """
    if last_n is not None:
        entries = entries[-last_n:]

    if not entries:
        return _empty_summary()

    overall = _summarize_group(entries, target=None)
    overall["groups"] = {}

    if group_by:
        groups: dict[str, list[dict]] = {}
        first_seen: dict[str, str] = {}
        for entry in entries:
            key = entry.get(group_by)
            groups.setdefault(key, []).append(entry)
            first_seen.setdefault(key, entry.get("timestamp", ""))

        ordered_keys = (
            sorted(groups, key=lambda k: first_seen[k])
            if group_by == "system_prompt_hash"
            else sorted(groups)
        )
        overall["groups"] = {
            key: _summarize_group(groups[key], target=target) for key in ordered_keys
        }

    return overall


def worst(entries: list[dict], n: int) -> list[dict]:
    """The ``n`` graded entries with the lowest ``judge_score``, ascending —
    raw entries, no synthesis (clarifications.md Q6). Entries never graded
    (``judge_score is None``) are excluded.
    """
    graded = [e for e in entries if e.get("judge_score") is not None]
    graded_sorted = sorted(graded, key=lambda e: e["judge_score"])
    return graded_sorted[:n]
