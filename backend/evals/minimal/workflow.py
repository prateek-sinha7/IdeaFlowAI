"""Workflow resolution: which agents a config runs, and where its rubrics,
datasets and checkers live.

THE ONE PLACE that knows a workflow is a directory. Everything else in this
package takes a stage name and a resolved config and never asks what pipeline
it belongs to, which is what lets `prototype`, `ppt` or anything else run
through the same harness with no Python change.

    workflows/<id>/
      workflow.yaml          order + per-stage agent_id / seed_as / deliverable / checks
      rubrics/<stage>.yaml   one per stage in `order`
      datasets/<name>.json   the briefs

A config (configs/*.yaml) names a workflow and a dataset; `resolve_config`
folds the two into the single flat dict the rest of the package already
reads, so `run.py`/`cli.py`/`checks.py` see exactly the shape they always saw.

Named `workflow.py` (singular) against the `workflows/` directory beside it
deliberately: same-named module and namespace package in one package resolve
by import-machinery precedence rather than by anything a reader can see.

Rubrics are per-workflow rather than global because stage names are
eval-local labels, not agent ids: `prototype` and `ppt` both have a
`validate` stage and they are not the same thing. A flat `rubrics/<stage>.yaml`
silently graded one with the other's rubric.
"""

from __future__ import annotations

from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
WORKFLOWS_DIR = HERE / "workflows"
CONFIGS_DIR = HERE / "configs"


def list_workflows() -> list[str]:
    """Every workflow id on disk — a directory holding a `workflow.yaml`."""
    if not WORKFLOWS_DIR.exists():
        return []
    return sorted(p.name for p in WORKFLOWS_DIR.iterdir() if (p / "workflow.yaml").exists())


def load_workflow(workflow_id: str) -> dict:
    """One workflow definition, with a failure that names the fix.

    An unknown id is the single most likely mistake when adding a workflow
    (a typo in a config, or a directory without its `workflow.yaml`), so it
    lists what does exist rather than raising a bare file-not-found.
    """
    path = WORKFLOWS_DIR / workflow_id / "workflow.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"no workflow {workflow_id!r} at {path} — known workflows: {list_workflows()}"
        )
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def resolve_config(config: str | Path | dict) -> dict:
    """A config file (or dict) folded together with the workflow it names.

    Precedence: the CONFIG wins over the workflow definition, so a config can
    override one stage's deliverable for an experiment without copying the
    whole chain. `order` and `agents` are the only keys that come from the
    workflow at all; everything else (dataset, provider, model) is the
    config's own.

    `dataset_id` is read off the DATASET file rather than restated in the
    config — one fact, one place. A config may still pin its own to label an
    experiment ("prototype_smoke_thinking").

    A config with `order`/`agents` inline and no `workflow:` is passed through
    untouched. That is not only backward compatibility: it is how a one-off
    chain gets tried without minting a workflow directory for it.
    """
    resolved = dict(config) if isinstance(config, dict) else _read_config(config)
    workflow_id = resolved.get("workflow")
    if workflow_id:
        workflow = load_workflow(workflow_id)
        resolved = {
            "order": workflow.get("order") or [],
            "agents": workflow.get("agents") or {},
            **resolved,
        }
    if not resolved.get("order") or not resolved.get("agents"):
        raise ValueError(
            "config resolves to no stages: name a `workflow:` (one of "
            f"{list_workflows()}) or declare `order:` and `agents:` inline"
        )
    if not resolved.get("dataset_id"):
        resolved["dataset_id"] = _dataset_id(resolved, workflow_id)
    return resolved


def load_rubric(config: dict, stage: str) -> dict:
    """The rubric for one stage of one workflow.

    `config` is the run's own resolved snapshot, so a rubric is always looked
    up against the workflow that actually ran — never re-derived from an agent
    id, which is a guess that breaks the moment two workflows share an agent
    (the od-ppt-* agents are shared with `od_ppt` exactly this way).
    """
    workflow_id = workflow_of(config)
    path = WORKFLOWS_DIR / (workflow_id or "") / "rubrics" / f"{stage}.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"no rubric for stage {stage!r} of workflow {workflow_id!r} at {path}"
        )
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def dataset_path(config: dict, workflow_id: str | None = None) -> Path:
    """Where this config's dataset lives.

    Resolution order: an absolute/relative path as given, then the named
    workflow's own `datasets/`. Datasets are per-workflow because a brief is
    written FOR a pipeline — a deck brief run through `prototype` produces a
    scored, plausible-looking run measuring nothing.
    """
    dataset = config.get("dataset")
    if not dataset:
        raise ValueError("config names no `dataset:`")
    path = Path(dataset)
    if path.is_absolute() or path.exists():
        return path
    workflow_id = workflow_id or config.get("workflow")
    candidate = WORKFLOWS_DIR / (workflow_id or "") / "datasets" / dataset
    if candidate.exists():
        return candidate
    raise FileNotFoundError(
        f"no dataset {dataset!r} for workflow {workflow_id!r} — looked in {candidate.parent}"
    )


def workflow_of(config: dict) -> str | None:
    """Which workflow a config — a run snapshot, or a workflow definition
    itself — belongs to.

    `workflow:` when a config named one, `id:` when this IS a workflow
    definition. Only then the agent-id prefix (`prototype-specify` ->
    `prototype`), which is what runs stored before workflows existed have to be
    read by, and is still right for an inline one-off chain.

    The prefix is a LAST resort, not a rule: `ppt` dispatches the `od-ppt-*`
    agents, so the prefix says "od" and would send every ppt rubric lookup to a
    workflow that does not exist. It is a guess that happens to be right for
    `prototype`, which is the only reason it survived this long.
    """
    for key in ("workflow", "id"):
        if config.get(key):
            return str(config[key])
    prefixes = {
        str(defn.get("agent_id", "")).split("-")[0]
        for defn in (config.get("agents") or {}).values()
        if defn and defn.get("agent_id")
    }
    prefixes.discard("")
    return "+".join(sorted(prefixes)) if prefixes else None


def stage_def(config: dict, stage: str) -> dict:
    """One stage's definition out of a resolved config — `{}` if absent."""
    return (config.get("agents") or {}).get(stage) or {}


def _read_config(config: str | Path) -> dict:
    path = Path(config)
    if not path.is_absolute() and not path.exists():
        path = CONFIGS_DIR / path.name
    if not path.exists():
        raise FileNotFoundError(f"no config at {config}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _dataset_id(config: dict, workflow_id: str | None) -> str:
    """The dataset's own declared id, so it is stated once and travels with
    the rows it names. Falls back to the filename stem."""
    import json

    path = dataset_path(config, workflow_id)
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("dataset_id") or path.stem
    except (json.JSONDecodeError, OSError):
        return path.stem
