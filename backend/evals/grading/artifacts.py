"""Read and write the run folder. Pure I/O, no logic, no model calls.

Sole owner of every path under `.runs/<dataset_run_id>/` and of run-id minting,
so no other module builds a path by hand. Also owns the append-only guard that
stops a re-run silently destroying a previous stage's captured responses.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

import yaml

RUNS_DIR_NAME = ".runs"
# A grading root is the folder holding both of these; run output goes at its
# top level rather than inside the checked-in workflow config tree.
GRADING_ROOT_MARKERS = ("configs", "model")
ARTIFACTS_DIR_NAME = "artifacts"
SUPERSEDED_DIR_NAME = "superseded"
PROMPTS_DIR_NAME = "prompts"
LOGS_DIR_NAME = "logs"
REPORTS_DIR_NAME = "reports"
RUN_SUMMARY_NAME = "run_summary.json"
RESOLVED_CONFIG_NAME = "grade_config.resolved.yaml"
_SUPERSEDED_PATTERN = re.compile(r"_a(\d+)_")


def new_dataset_run_id(dataset_id: str) -> str:
    """Mint `{YYMMDD-HHMMSS}-{dataset_id}` — timestamp first so runs sort."""
    return f"{datetime.now().strftime('%y%m%d-%H%M%S')}-{dataset_id}"


def runs_root(workflow_dir: Path) -> Path:
    """`<grading root>/.runs/<workflow>/` — run output, outside the config tree.

    Output does not live under `model/workflows/<workflow>/` because that folder
    is checked-in config: mixing mutable, gitignored artifacts into it forces
    every loader, glob and doc tool to special-case skipping `.runs`. Keeping it
    at the grading root also gives the code track somewhere to write, since it
    shares a run folder with the model track by `dataset_run_id`.

    Falls back to `<workflow_dir>/.runs/` for a standalone workflow folder with
    no grading root above it — which is what a test copying one into a tmp dir
    gets, so its output stays inside the tmp dir.
    """
    workflow_dir = Path(workflow_dir)
    for parent in workflow_dir.parents:
        if all((parent / marker).is_dir() for marker in GRADING_ROOT_MARKERS):
            return parent / RUNS_DIR_NAME / workflow_dir.name
    return workflow_dir / RUNS_DIR_NAME


def run_folder(dataset_run_id: str, *, workflow_dir: Path) -> Path:
    """`<grading root>/.runs/<workflow>/<dataset_run_id>/`, created if absent."""
    run_dir = runs_root(workflow_dir) / dataset_run_id
    for name in (ARTIFACTS_DIR_NAME, PROMPTS_DIR_NAME, LOGS_DIR_NAME):
        (run_dir / name).mkdir(parents=True, exist_ok=True)
    return run_dir


def artifacts_dir(run_dir: Path) -> Path:
    """The `artifacts/` folder holding this run's four files per stage."""
    return Path(run_dir) / ARTIFACTS_DIR_NAME


def artifact_path(run_dir: Path, agent_token: str, kind: str) -> Path:
    """Path of one artifact: `artifacts/<agent_token>_<kind>.json`."""
    return artifacts_dir(run_dir) / f"{agent_token}_{kind}.json"


def reports_dir(run_dir: Path) -> Path:
    """The `reports/` folder: the human-readable rendering of this run."""
    path = Path(run_dir) / REPORTS_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def src_dir(run_dir: Path, row_id: str) -> Path:
    """`<run>/src/<brief>/` — one folder holding that brief's whole document set.

    Keyed by BRIEF rather than by agent, because spec.md, tasks.md and
    prototype.html for one brief are one project: you read them together. The
    artifacts/ JSON is the machine's record; this is the human's.
    """
    return Path(run_dir) / "src" / str(row_id)


def write_src_file(run_dir, row_id: str, filename: str, content: str) -> Path | None:
    """Write one stage's output as a real file, never failing the run over it."""
    if run_dir is None or not filename or not content:
        return None
    try:
        path = src_dir(run_dir, row_id) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path
    except OSError:
        return None


def log_path(run_dir: Path, agent_token: str, row_id: str) -> Path:
    """Path of one dispatch transcript: `logs/<row_id>/<agent_token>.log`.

    Keyed by ROW first, like src/: one brief's transcripts across every stage
    are one story, and reading them together is how a bad final HTML is traced
    back to the stage that introduced it.
    """
    return Path(run_dir) / LOGS_DIR_NAME / str(row_id) / f"{agent_token}.log"


def compute_system_prompt_hash(system_prompt: str) -> str:
    """`sha256:<hex>` of a composed prompt, for prompt-drift detection."""
    digest = hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def guard_append_only(
    run_dir: Path, agent_token: str, *, replace: bool, keep: tuple[str, ...] = ()
) -> None:
    """Refuse to overwrite a stage's artifacts unless `replace` is set.

    Silent overwrite is unrecoverable — the captured response text is gone. With
    `replace`, move the existing artifacts to `superseded/<agent_token>_a<N>_*.json`.

    `keep` names artifact kinds left IN PLACE rather than superseded. A rejudge
    keeps `code_findings`: the responses it re-scores are unchanged, so the
    deterministic findings over them are still true — whereas a live --replace
    produces new responses and must supersede them as stale.
    """
    existing = artifact_path(run_dir, agent_token, "run")
    if not existing.exists():
        return
    if not replace:
        raise FileExistsError(
            f"{existing} already exists — the run folder is append-only. "
            f"Pass --replace to supersede this stage's artifacts."
        )
    attempt = _next_supersede_attempt(run_dir, agent_token)
    target_dir = artifacts_dir(run_dir) / SUPERSEDED_DIR_NAME
    target_dir.mkdir(parents=True, exist_ok=True)
    kept = {f"{agent_token}_{kind}.json" for kind in keep}
    for path in sorted(artifacts_dir(run_dir).glob(f"{agent_token}_*.json")):
        if path.name in kept:
            continue
        kind = path.name[len(agent_token) + 1 :]
        path.rename(target_dir / f"{agent_token}_a{attempt}_{kind}")


def _next_supersede_attempt(run_dir: Path, agent_token: str) -> int:
    """Next `a<N>` index for this agent, so a supersede never clobbers one."""
    target_dir = artifacts_dir(run_dir) / SUPERSEDED_DIR_NAME
    used = []
    for path in target_dir.glob(f"{agent_token}_a*.json"):
        found = _SUPERSEDED_PATTERN.search(path.name[len(agent_token) :])
        if found:
            used.append(int(found.group(1)))
    return max(used, default=0) + 1


def write_stage(run_dir: Path, agent_token: str, *, runs, grades, score, output) -> None:
    """Write this stage's run/grade/score/output JSON, once, at end of stage."""
    for kind, payload in (
        ("run", runs),
        ("grade", grades),
        ("score", score),
        ("output", output),
    ):
        _write_json(artifact_path(run_dir, agent_token, kind), payload)


def write_resolved_config(run_dir: Path, config: dict) -> None:
    """Write `grade_config.resolved.yaml` — BEFORE the first dispatch.

    Every value after defaults, config file and CLI overrides are merged, so a
    crashed run is still re-runnable via `--config <this file>`.
    """
    path = Path(run_dir) / RESOLVED_CONFIG_NAME
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def read_resolved_config(run_dir: Path) -> dict:
    """Read back `grade_config.resolved.yaml` from a run folder."""
    path = Path(run_dir) / RESOLVED_CONFIG_NAME
    if not path.exists():
        raise FileNotFoundError(f"no resolved config at {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def write_system_prompt(run_dir: Path, agent_token: str, prompt: str) -> None:
    """Write `prompts/<agent_token>_system_prompt.md` — the composed prompt.

    A hash proves two runs differed; only the text shows HOW.
    """
    path = Path(run_dir) / PROMPTS_DIR_NAME / f"{agent_token}_system_prompt.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(prompt, encoding="utf-8")


def read_system_prompt(run_dir: Path, agent_token: str) -> str:
    """Read back the composed prompt captured for one stage."""
    path = Path(run_dir) / PROMPTS_DIR_NAME / f"{agent_token}_system_prompt.md"
    if not path.exists():
        raise FileNotFoundError(f"no captured system prompt at {path}")
    return path.read_text(encoding="utf-8")


def advice_markdown_path(run_dir: Path, agent_token: str) -> Path:
    """`reports/prompt_advice_<agent_token>.md` — the advisor's human artifact."""
    return Path(run_dir) / REPORTS_DIR_NAME / f"prompt_advice_{agent_token}.md"


def advice_json_path(run_dir: Path, agent_token: str) -> Path:
    """`reports/prompt_advice_<agent_token>.json` — the same advice, machine-readable."""
    return Path(run_dir) / REPORTS_DIR_NAME / f"prompt_advice_{agent_token}.json"


def write_advice_json(run_dir: Path, agent_token: str, payload: dict) -> None:
    """Write the advisor's structured advice beside its markdown rendering.

    The markdown is what a person reads; this is what `apply-advice` applies.
    They are written from the same object, so they cannot disagree — and only
    this one preserves `current_text` verbatim, which is what makes an exact,
    unambiguous match against the prompt body possible.
    """
    _write_json(advice_json_path(run_dir, agent_token), payload)


def read_advice_json(run_dir: Path, agent_token: str) -> dict:
    """Read back structured advice; raise naming the fix when it was never written.

    Runs graded before this sidecar existed have only the markdown. Re-advising
    an existing run is cheap — one judge call, no agent dispatches — but that is
    not obvious from a bare "file not found", so the error says it.
    """
    path = advice_json_path(run_dir, agent_token)
    if not path.exists():
        raise FileNotFoundError(
            f"no structured advice at {path} — run "
            f"`grade.sh advise {Path(run_dir).name}` to generate it "
            "(one judge call per stage, no agent dispatches)"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def write_run_summary(run_dir: Path, summary: dict) -> None:
    """Write `run_summary.json`: status running before a stage, again after."""
    _write_json(Path(run_dir) / RUN_SUMMARY_NAME, summary)


def read_run_summary(run_dir: Path) -> dict:
    """Read `run_summary.json` — the whole run's stage and row index."""
    path = Path(run_dir) / RUN_SUMMARY_NAME
    if not path.exists():
        raise FileNotFoundError(f"no run summary at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def append_stage_run(summary: dict, entry: dict) -> dict:
    """Append one entry to the append-only `stage_runs` list, in place."""
    summary.setdefault("stage_runs", []).append(entry)
    return summary


def mark_stale_after(summary: dict, agent_id: str) -> dict:
    """Mark every stage after `agent_id` stale — its input no longer exists."""
    stages = summary.get("stages", [])
    seen = False
    for stage in stages:
        if seen and stage.get("status") not in (None, "not_run"):
            stage["status"] = "stale"
        if stage.get("agent_id") == agent_id:
            seen = True
    return summary


def read_stage_output(run_dir: Path, agent_token: str) -> dict:
    """Read a stage's `output.json` — the next stage's input envelope."""
    path = artifact_path(run_dir, agent_token, "output")
    if not path.exists():
        raise FileNotFoundError(
            f"no stage output at {path} — run {agent_token} before the stage that consumes it"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def read_stage_artifact(run_dir: Path, agent_token: str, kind: str):
    """Read one of a stage's artifacts by kind (`run`, `grade`, `score`, `output`)."""
    path = artifact_path(run_dir, agent_token, kind)
    if not path.exists():
        raise FileNotFoundError(f"no {kind} artifact at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload) -> None:
    """Write one JSON artifact, pretty-printed and newline-terminated."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
