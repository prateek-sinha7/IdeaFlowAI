"""Model-grade a Harbor trial's artifact with evals/minimal's real judge.

Runs on python3.11 (the backend interpreter) and imports `evals.minimal.judge`
directly — the SAME judge, rubric and severity pricing `evals/minimal` uses, not
a reimplementation. The only new thing here is where the artifact comes from: a
Harbor job folder instead of a `.runs/` phase file.

That is the whole point of the split. Harbor code-grades inside the container
and hands back the deliverable; the model grader reads that deliverable on the
host. Neither knows about the other.

Usage (from backend/, after a `harbor run`):
    python3.11 evals/harbor/model_grade.py                  # newest job
    python3.11 evals/harbor/model_grade.py <job-dir>
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import sys

import yaml

from evals.minimal import judge

HARBOR = pathlib.Path(__file__).resolve().parent
MINIMAL = HARBOR.parent / "minimal"
STAGE = "specify"

sys.path.insert(0, str(HARBOR))
import trial_paths  # noqa: E402  — needs HARBOR on the path first


def newest_job() -> pathlib.Path:
    jobs = sorted((HARBOR / "jobs").glob("*/"), key=lambda p: p.name)
    if not jobs:
        raise SystemExit("no harbor jobs found — run `harbor run` first")
    return jobs[-1]


def find_trial(job: pathlib.Path) -> pathlib.Path:
    for child in sorted(job.iterdir()):
        if child.is_dir() and (child / "artifacts").exists():
            return child
    raise SystemExit(f"no trial with artifacts in {job}")


def main() -> int:
    job = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else newest_job()
    trial = find_trial(job)

    spec = trial / "artifacts" / "app" / "spec.md"
    if not spec.exists():
        raise SystemExit(
            f"{spec} missing — task.toml needs `artifacts = [\"/app/spec.md\"]` "
            "or the deliverable never leaves the container"
        )
    response = spec.read_text(encoding="utf-8")

    # The brief the agent was given, and the rubric evals/minimal judges with.
    # Both come from the task THIS trial ran — a fixed path would grade a
    # mission-control spec against the warehouse-slotting brief.
    task = trial_paths.task_dir(trial)
    instruction = (task / "instruction.md").read_text(encoding="utf-8")
    rubric = yaml.safe_load((MINIMAL / "rubrics" / f"{STAGE}.yaml").read_text(encoding="utf-8"))
    system_prompt = (task / "agent" / "system_prompt.md").read_text(encoding="utf-8")

    code_grade = json.loads((trial / "verifier" / "reward.json").read_text(encoding="utf-8"))

    verdict = asyncio.run(judge.judge(
        response, rubric=rubric, prompt=instruction, system_prompt=system_prompt,
    ))

    print(f"job    : {job.name}")
    print(f"trial  : {trial.name}")
    print(f"words  : {code_grade.get('words')}")
    print()
    print("── CODE GRADE (Harbor verifier, deterministic, free) ──")
    for key in ("reward", "build_ready", "pages", "routes", "entities",
                "fields", "formats", "interactions", "missing_count"):
        if key in code_grade:
            print(f"  {key:<14} {code_grade[key]}")
    print()
    print("── MODEL GRADE (evals/minimal judge.py, severity-priced) ──")
    if verdict.errored:
        print(f"  ERRORED: {verdict.error_reason}")
        return 1
    for dim_id, self_score in verdict.sub_scores.items():
        priced = verdict.sub_scores_priced.get(dim_id, self_score)
        print(f"  {dim_id:<32} self={self_score:>3}  priced={priced:>3}")
        for finding in verdict.findings.get(dim_id, []):
            print(f"      [{finding['severity']:<8} -{finding['cost']:>2}] {finding['text'][:94]}")
    mean_self = sum(verdict.sub_scores.values()) / max(1, len(verdict.sub_scores))
    mean_priced = sum(verdict.sub_scores_priced.values()) / max(1, len(verdict.sub_scores_priced))
    print()
    print(f"  MEAN self-scored : {mean_self:.1f}")
    print(f"  MEAN priced      : {mean_priced:.1f}   <-- severity-priced, the honest one")
    print(f"  tokens           : in={verdict.tokens_in} out={verdict.tokens_out}")

    out = trial / "model_grade.json"
    out.write_text(json.dumps({
        "code_grade": code_grade,
        "model_grade": {
            "sub_scores": verdict.sub_scores,
            "sub_scores_priced": verdict.sub_scores_priced,
            "findings": verdict.findings,
            "mean_self": mean_self,
            "mean_priced": mean_priced,
        },
    }, indent=2), encoding="utf-8")
    print(f"\nwritten: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
