"""Merge the host-side grades into each trial's result.json so the viewer shows them.

Why this is needed
------------------
`harbor view jobs` reads `jobs/<job>/<trial>/result.json` from disk on every
request, and renders `verifier_result.rewards` as the score columns. Only the
in-container verifier writes that dict. Our model grades run afterwards on the
host — `judge.py` needs python3.11, and `spec_judge.py` needs an API key we do
not want inside the container — so they land in sibling files the viewer has
never heard of, and the UI shows a code grade only.

Merging them into `rewards` puts all three graders in one table. Because the
scanner re-reads from disk there is nothing to rebuild: refresh the page.

Why not just run the judges in the verifier
-------------------------------------------
Then every trial spends judge tokens, the container needs the key, and — the
real objection — a verifier that raises makes Harbor score the trial as an
*exception* rather than a zero, so a judge failing on a 429 would delete the
trial from the aggregate instead of failing it. Keeping the judges outside the
trial keeps their failures from being able to do that.

Keys are namespaced (`judge_`, `spec_`) so they can never collide with a
verifier metric, and the merge is idempotent — re-running overwrites its own
keys and touches nothing else.
"""

from __future__ import annotations

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent


def grades_for(trial: pathlib.Path) -> dict:
    """Flat, numeric-only scores from whichever host-side grade files exist.

    Numeric only, deliberately: the viewer's reward model is floats, and a
    string in there is the same pydantic float_parsing failure that took down
    a whole trial when the verifier tried to return a diagnostic message.
    """
    out: dict[str, float] = {}

    model_grade = trial / "model_grade.json"
    if model_grade.exists():
        data = json.loads(model_grade.read_text(encoding="utf-8")).get("model_grade") or {}
        if "mean_priced" in data:
            out["judge_mean_priced"] = round(float(data["mean_priced"]), 1)
        if "mean_self" in data:
            out["judge_mean_self"] = round(float(data["mean_self"]), 1)
        for dim, score in (data.get("sub_scores_priced") or {}).items():
            out[f"judge_{dim}"] = float(score)

    # spec_judge writes one level up from the trial (next to artifacts/), so
    # check both spellings rather than assume.
    for candidate in (trial / "spec_judge.json", trial.parent / "spec_judge.json"):
        if not candidate.exists():
            continue
        data = json.loads(candidate.read_text(encoding="utf-8"))
        out["spec_score"] = float(data.get("score", 0))
        for severity, count in (data.get("counts") or {}).items():
            out[f"spec_{severity}"] = float(count)
        out["spec_contradictions"] = float(data.get("contradictions_found_by_python", 0))
        break

    return out


def mirror_into_artifacts(trial: pathlib.Path) -> list[str]:
    """Copy the grade files under `artifacts/` so the UI can show them.

    The viewer has an Artifacts tab and a `/files` endpoint. `/files` already
    lists these, but the shipped tab bar (Trajectory, Agent, Verifier,
    Artifacts, Config, Lock, Log, Exception, Analysis) has no Files tab — so a
    file sitting beside `artifacts/` is reachable by API and invisible in the
    browser. Copying rather than moving keeps the canonical path stable for
    anything reading them from disk.
    """
    dest = trial / "artifacts" / "grades"
    copied = []
    for name in ("model_grade.json", "spec_judge.json"):
        source = trial / name
        if source.exists():
            dest.mkdir(parents=True, exist_ok=True)
            (dest / name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            copied.append(name)
    return copied


def publish(job: pathlib.Path) -> int:
    published = 0
    for trial in sorted(p for p in job.iterdir() if p.is_dir()):
        result = trial / "result.json"
        if not result.exists():
            continue
        mirrored = mirror_into_artifacts(trial)
        extra = grades_for(trial)
        if not extra:
            continue
        if mirrored:
            print(f"  {trial.name}: artifacts/grades/ <- {', '.join(mirrored)}")
        data = json.loads(result.read_text(encoding="utf-8"))
        verifier = data.setdefault("verifier_result", {}) or {}
        rewards = verifier.setdefault("rewards", {}) or {}
        rewards.update(extra)
        verifier["rewards"] = rewards
        data["verifier_result"] = verifier
        result.write_text(json.dumps(data, indent=2), encoding="utf-8")
        published += 1
        print(f"  {trial.name}: +{len(extra)} metrics {sorted(extra)[:4]}…")
    return published


def main() -> int:
    if len(sys.argv) > 1:
        jobs = [pathlib.Path(sys.argv[1])]
    else:
        jobs = sorted(p for p in (HERE / "jobs").iterdir() if p.is_dir())
    total = 0
    for job in jobs:
        print(f"{job.name}:")
        total += publish(job)
    print(f"\n{total} trial(s) updated — refresh http://127.0.0.1:8080")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
