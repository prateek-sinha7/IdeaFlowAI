"""Load and validate every config file, and merge the run's settings.

Four kinds: the run config (`--config`), `workflow.yaml`, `<agent>_rubric.yaml`
and `datasets/<name>.json`. Also asserts the workflow mirrors the real registry,
and computes the three hashes that decide whether runs are comparable.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import agents.registry
import yaml

from evals.grading import hooks

WORKFLOWS_ROOT = Path(__file__).resolve().parent / "model" / "workflows"

# `build_model` only branches on this one; every other value — including
# "anthropic" and "bedrock" — is silently ignored and falls through the chain.
HONOURED_PROVIDERS = ("mistral",)

# Row ids from a retired per-agent naming scheme. They break the cross-stage
# join, which is a lookup of the SAME row id in every stage's artifacts.
AGENT_SUFFIXES = ("_plan", "_analyze", "_build", "_validate")

# What a score MEANS. `baseline` is excluded on purpose: ratcheting a threshold
# must not look like a change to the rubric.
RUBRIC_HASH_KEYS = ("precheck", "judge", "rubric", "dimensions", "anchors")

# An empty `dataset` means "use the workflow's own `default_dataset`".
DEFAULTS: dict = {
    "run_id": "adhoc",
    "track": "model",
    "workflow": "prototype",
    "dataset": "",
    "agents": "all",
    "from_run": None,
    "rows": None,
    "limit": None,
    "agent_under_test": {"provider": None, "model": None},
    "judge": {"provider": None, "model": None, "threshold": None},
    "options": {"concurrency": 3, "no_judge": False, "repeats": 1},
}

SECTIONS = ("agent_under_test", "judge", "options")


@dataclass(frozen=True)
class RunConfig:
    """The fully merged settings for one run: defaults < config file < CLI."""

    run_id: str
    track: str
    workflow: str
    dataset: str
    agents: object
    from_run: str | None
    rows: list[str] | None
    limit: int | None
    agent_under_test: dict
    judge: dict
    options: dict
    overrides: dict


def load_run_config(path: Path | None, cli_overrides: dict) -> RunConfig:
    """Merge defaults, the config file and CLI flags into one RunConfig.

    Every CLI value that differs from the config is recorded in `overrides` — a
    run whose flags diverged is not reproducible from that config and must say
    so rather than look identical to one that was.
    """
    merged = copy.deepcopy(DEFAULTS)
    _apply_file(merged, _read_run_config_file(path))

    overrides: dict = {}
    _apply_cli(merged, cli_overrides or {}, overrides)

    _validate_run_config(merged)
    return RunConfig(**merged, overrides=overrides)


def load_workflow(workflow: str) -> dict:
    """Load `workflow.yaml` and ASSERT it mirrors the real registry.

    The stage list must equal `agents.registry.get_pipeline_agents()` in
    membership AND order, and each stage's `from:` must equal that agent's real
    `consumes` frontmatter. Without this the file becomes the drifting second
    source of truth it warns against.
    """
    path = WORKFLOWS_ROOT / workflow / "workflow.yaml"
    if not path.is_file():
        raise ValueError(f"workflow '{workflow}': no workflow.yaml at '{path}'")

    data = _read_yaml(path)
    stages = data.get("stages")
    if not isinstance(stages, list) or not stages:
        raise ValueError(f"workflow file '{path}' declares no stages")

    _assert_mirrors_registry(data.get("pipeline_type", workflow), stages, path)
    data["workflow_dir"] = str(path.parent)
    return data


def load_rubric(workflow_dir: Path, agent_id: str) -> dict:
    """Load `<agent_token>_rubric.yaml` and resolve its `validate:` hook.

    Validates dimension weights sum to 100, every forbidden pattern compiles,
    and warns when `judge.provider` names a provider build_model cannot honour
    (only "mistral" is honoured; others fall through silently).
    """
    path = Path(workflow_dir) / f"{_agent_token(agent_id)}_rubric.yaml"
    if not path.is_file():
        raise ValueError(f"agent '{agent_id}': no rubric at '{path}'")

    rubric = _read_yaml(path)
    _validate_dimensions(rubric.get("dimensions"), path)

    precheck = rubric.get("precheck") or {}
    _validate_forbidden(precheck.get("forbidden") or [], path)

    reference = precheck.get("validate")
    rubric["validate_hook"] = (
        hooks.load_callable(reference, relative_to=path) if reference else None
    )
    rubric["provider_warning"] = _provider_warning(rubric.get("judge") or {}, path)
    rubric["path"] = str(path)
    return rubric


def load_dataset(reference: str, *, workflow_dir: Path, agent_id: str) -> dict:
    """Load a dataset by PATH, relative to the workflow folder if not absolute.

    Validates row ids are unique and carry no agent suffix, and enforces the
    optional `for_agent` guard so one stage's generated output cannot be fed to
    the wrong agent.
    """
    path = Path(reference)
    if not path.is_absolute():
        path = Path(workflow_dir) / path
    if not path.is_file():
        raise ValueError(f"dataset '{reference}' not found (looked in '{path}')")

    dataset = json.loads(path.read_text())
    if not dataset.get("dataset_id"):
        raise ValueError(f"dataset '{path}' has no dataset_id")

    for_agent = dataset.get("for_agent")
    if for_agent and for_agent != agent_id:
        raise ValueError(
            f"dataset '{path}' declares for_agent '{for_agent}' "
            f"but is being run against agent '{agent_id}'"
        )

    _validate_rows(dataset.get("rows"), path)
    return dataset


def compute_hashes(run_config: RunConfig, rubric: dict, dataset: dict) -> dict:
    """The three hashes that decide comparability.

    `rubric_hash` covers precheck + judge + rubric + dimensions + anchors and
    EXCLUDES `baseline` — ratcheting a threshold must not look like a change to
    what a score means. `dataset_hash` covers the rows, because editing a brief
    moves scores as much as editing the rubric. `config_hash` covers the merged
    run config.
    """
    settings = asdict(run_config)
    settings.pop("overrides")
    return {
        "config_hash": _hash(settings),
        "rubric_hash": _hash({key: rubric.get(key) for key in RUBRIC_HASH_KEYS}),
        "dataset_hash": _hash(dataset.get("rows")),
    }


def _read_run_config_file(path: Path | None) -> dict:
    """Read the run config file, or an empty mapping for an ad-hoc CLI run."""
    if path is None:
        return {}
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"run config '{path}' does not exist")
    return _read_yaml(path)


def _read_yaml(path: Path) -> dict:
    """Parse a YAML file into a mapping, naming the file on any failure."""
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as error:
        raise ValueError(f"config file '{path}' is not valid YAML: {error}") from error
    if not isinstance(data, dict):
        raise ValueError(f"config file '{path}' must contain a mapping")
    return data


def _apply_file(merged: dict, values: dict) -> None:
    """Overlay the config file onto the defaults, rejecting unknown keys."""
    for key, value in values.items():
        if key not in merged:
            raise ValueError(f"run config: unknown key '{key}'")
        if key in SECTIONS:
            _apply_section(merged[key], value, key)
        else:
            merged[key] = value


def _apply_section(target: dict, values: dict, section: str) -> None:
    """Overlay one nested section, rejecting unknown keys within it."""
    if not isinstance(values, dict):
        raise ValueError(f"run config: '{section}' must be a mapping")
    for key, value in values.items():
        if key not in target:
            raise ValueError(f"run config: unknown key '{section}.{key}'")
        target[key] = value


def _apply_cli(merged: dict, cli_overrides: dict, overrides: dict) -> None:
    """Apply CLI values, recording every one that differs from the config."""
    for key, value in cli_overrides.items():
        if key not in merged:
            raise ValueError(f"CLI override: unknown key '{key}'")
        if key in SECTIONS:
            if not isinstance(value, dict):
                raise ValueError(f"CLI override: '{key}' must be a mapping")
            for inner_key, inner_value in value.items():
                if inner_key not in merged[key]:
                    raise ValueError(f"CLI override: unknown key '{key}.{inner_key}'")
                _record(merged[key], inner_key, inner_value, f"{key}.{inner_key}", overrides)
        else:
            _record(merged, key, value, key, overrides)


def _record(target: dict, key: str, value, dotted: str, overrides: dict) -> None:
    """Set one CLI value, recording it under its dotted name when it differs."""
    if target[key] == value:
        return
    overrides[dotted] = {"config": target[key], "cli": value}
    target[key] = value


def _validate_run_config(merged: dict) -> None:
    """Reject a merged run config that could not produce a meaningful run."""
    if merged["track"] not in ("model", "code"):
        raise ValueError(f"run config: track must be 'model' or 'code', got {merged['track']!r}")
    if not merged["workflow"]:
        raise ValueError("run config: workflow is required")

    selected = merged["agents"]
    is_agent_list = isinstance(selected, list) and all(isinstance(a, str) for a in selected)
    if selected != "all" and not (is_agent_list and selected):
        raise ValueError(f"run config: agents must be 'all' or a list of agent ids, got {selected!r}")

    if merged["rows"] is not None and not isinstance(merged["rows"], list):
        raise ValueError(f"run config: rows must be null or a list, got {merged['rows']!r}")
    _validate_positive(merged["limit"], "limit", allow_none=True)
    _validate_positive(merged["options"]["concurrency"], "options.concurrency", allow_none=False)
    _validate_positive(merged["options"]["repeats"], "options.repeats", allow_none=False)
    if not isinstance(merged["options"]["no_judge"], bool):
        raise ValueError("run config: options.no_judge must be true or false")


def _validate_positive(value, name: str, *, allow_none: bool) -> None:
    """Require a positive integer, optionally allowing null."""
    if value is None and allow_none:
        return
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"run config: {name} must be a positive integer, got {value!r}")


def _assert_mirrors_registry(pipeline_type: str, stages: list, path: Path) -> None:
    """Assert the stage list and every `from:` mirror the real registry."""
    specs = agents.registry.get_pipeline_agents(pipeline_type)
    declared = [stage.get("agent_id") for stage in stages]
    actual = [spec.id for spec in specs]
    if declared != actual:
        raise ValueError(
            f"workflow file '{path}' has drifted from the registry: stages are "
            f"{declared} but get_pipeline_agents('{pipeline_type}') is {actual} "
            "(membership and order must both match)"
        )

    for stage, spec in zip(stages, specs):
        sources = list((stage.get("input") or {}).get("from") or [])
        if sources != list(spec.consumes):
            raise ValueError(
                f"workflow file '{path}': stage '{spec.id}' declares from={sources} "
                f"but its AGENT.md consumes={list(spec.consumes)}"
            )


def _agent_token(agent_id: str) -> str:
    """`prototype-specify` -> `prototype_specify`, the file-name form."""
    return agent_id.replace("-", "_")


def _validate_dimensions(dimensions, path: Path) -> None:
    """Require dimensions with unique ids whose weights sum to exactly 100."""
    if not isinstance(dimensions, list) or not dimensions:
        raise ValueError(f"rubric '{path}' declares no dimensions")

    ids = [dimension.get("id") for dimension in dimensions]
    if not all(ids):
        raise ValueError(f"rubric '{path}': every dimension needs an id")
    if len(set(ids)) != len(ids):
        raise ValueError(f"rubric '{path}': duplicate dimension ids in {ids}")

    total = sum(dimension.get("weight", 0) for dimension in dimensions)
    if total != 100:
        raise ValueError(
            f"rubric '{path}': dimension weights sum to {total}, not 100 "
            f"({dict(zip(ids, (d.get('weight') for d in dimensions)))})"
        )


def _validate_forbidden(forbidden: list, path: Path) -> None:
    """Require every forbidden entry to carry a compiling pattern and a reason."""
    for entry in forbidden:
        if not isinstance(entry, dict) or not entry.get("pattern"):
            raise ValueError(f"rubric '{path}': forbidden entry {entry!r} has no pattern")
        if not entry.get("reason"):
            raise ValueError(
                f"rubric '{path}': forbidden pattern {entry['pattern']!r} has no reason "
                "(a rejection with no reason cannot be acted on)"
            )
        try:
            re.compile(entry["pattern"])
        except re.error as error:
            raise ValueError(
                f"rubric '{path}': forbidden pattern {entry['pattern']!r} "
                f"is not a valid regex: {error}"
            ) from error


def _provider_warning(judge: dict, path: Path) -> str | None:
    """Warn — never raise — when build_model cannot honour the pinned provider."""
    provider = judge.get("provider")
    if not provider or provider in HONOURED_PROVIDERS:
        return None
    return (
        f"rubric '{path}' pins judge provider '{provider}', which build_model does not "
        f"honour (only {', '.join(HONOURED_PROVIDERS)}); the judge will fall through "
        "the implicit chain and the artifacts will record what actually resolved"
    )


def _validate_rows(rows, path: Path) -> None:
    """Require rows with unique, unsuffixed ids and the three mandatory fields."""
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"dataset '{path}' has no rows")

    seen: set[str] = set()
    for row in rows:
        for field in ("id", "industry", "prompt"):
            if not row.get(field):
                raise ValueError(f"dataset '{path}': row {row!r} has no '{field}'")

        row_id = row["id"]
        if row_id in seen:
            raise ValueError(
                f"dataset '{path}': duplicate row id '{row_id}' "
                "(row ids are the cross-stage join key and must be unique)"
            )
        seen.add(row_id)

        suffix = next((s for s in AGENT_SUFFIXES if row_id.endswith(s)), None)
        if suffix:
            raise ValueError(
                f"dataset '{path}': row id '{row_id}' carries the agent suffix "
                f"'{suffix}' from the retired per-agent naming scheme — a suffixed id "
                "cannot be joined against the same row in another stage"
            )


def _hash(payload) -> str:
    """Hash a payload canonically, so key order never changes the digest."""
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
