"""model_graded/scenario_discovery.py — loads every
model_graded/agents/*/scenarios/*.yaml into a GradedScenario.

Kept separate from ``evals/hybrid/common/scenario_discovery.py`` (the
deterministic track's discovery module) — not extended, not imported from —
since the two tracks' scenario shapes genuinely differ
(``LiveScenario``/``GradedScenario``; see specs/005-prompt-eval-scoring/spec.md
§3.5).
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import yaml

from evals.model_graded.driver import DEFAULT_LOGS_DIR, GradedScenario
from evals.model_graded.precheck import validate_precheck_config

AGENTS_ROOT = Path(__file__).resolve().parent / "agents"

DEFAULT_MIN_PAGES = 4


def _resolve_agent_id(agent_id: str) -> None:
    """Raise if ``agent_id`` isn't a real, registered pipeline agent."""
    from agents.registry import get_agent_by_id

    if get_agent_by_id(agent_id) is None:
        raise ValueError(f"unknown agent_id '{agent_id}' — not found in agents/registry.py")


def _resolve_precheck_module(dotted: str) -> "callable":
    """Resolve ``'pkg.module:function'`` (or ``'pkg.module.function'``) to a
    callable, raising ValueError with the failing path on any import/lookup
    error — a scenario declaring a broken custom hook must fail at load
    time, not silently skip the check at run time.
    """
    module_name, _, func_name = dotted.partition(":")
    if not func_name:
        module_name, _, func_name = dotted.rpartition(".")
    if not module_name or not func_name:
        raise ValueError(
            f"precheck_module '{dotted}' must be 'module.path:function' "
            "or 'module.path.function'"
        )
    try:
        module = importlib.import_module(module_name)
        return getattr(module, func_name)
    except (ImportError, AttributeError) as exc:
        raise ValueError(f"precheck_module '{dotted}' could not be resolved: {exc}") from exc


def load_scenario_yaml(path: Path, *, logs_root: Path = DEFAULT_LOGS_DIR) -> GradedScenario:
    """Load one scenario YAML file into a GradedScenario, validating at load
    time (fail loud): id/filename match, known agent_id, a complete
    ``precheck:`` block, a non-empty ``rubric:`` block, a resolvable
    ``precheck_module`` (if declared), and a positive ``min_pages`` (if
    declared).
    """
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    scenario_id = data.get("id")
    if not scenario_id:
        raise ValueError(f"{path}: 'id' is required")
    if scenario_id != path.stem:
        raise ValueError(
            f"{path}: id '{scenario_id}' must match the filename ('{path.stem}.yaml')"
        )

    agent_id = data.get("agent_id")
    if not agent_id:
        raise ValueError(f"{path}: 'agent_id' is required")
    _resolve_agent_id(agent_id)

    fixtures_root = path.parent.parent  # scenarios/../  == the agent folder
    if "prompt_file" in data:
        prompt = (fixtures_root / data["prompt_file"]).read_text(encoding="utf-8").strip()
    elif "prompt" in data:
        prompt = str(data["prompt"]).strip()
    else:
        raise ValueError(f"{path}: needs 'prompt' or 'prompt_file'")

    precheck_config = data.get("precheck")
    if not isinstance(precheck_config, dict):
        raise ValueError(f"{path}: 'precheck' block is required")
    validate_precheck_config(precheck_config)

    rubric = data.get("rubric")
    if not rubric or not str(rubric).strip():
        raise ValueError(f"{path}: 'rubric' block is required and must be non-empty")

    min_pages = data.get("min_pages", DEFAULT_MIN_PAGES)
    if not isinstance(min_pages, int) or min_pages <= 0:
        raise ValueError(f"{path}: 'min_pages' must be a positive integer, got {min_pages!r}")
    # 'min_pages' is the scenario-level override (clarifications.md Q2); when
    # the precheck block doesn't set its own 'min_sections' explicitly, it
    # defaults to min_pages (page count == section count for a
    # <spec>-document-shaped scenario like prototype-specify's).
    if "min_sections" not in precheck_config:
        precheck_config = {**precheck_config, "min_sections": min_pages}

    precheck_module = None
    if "precheck_module" in data:
        precheck_module = _resolve_precheck_module(data["precheck_module"])

    design_md_rel = data.get("design_md")
    design_md = (
        (fixtures_root / design_md_rel).read_text(encoding="utf-8") if design_md_rel else None
    )

    return GradedScenario(
        id=scenario_id,
        agent_id=agent_id,
        prompt=prompt,
        precheck_config=precheck_config,
        rubric=str(rubric).strip(),
        min_pages=min_pages,
        design_md=design_md,
        precheck_module=precheck_module,
        logs_dir=logs_root,
        source_path=path,
    )


def _load_template(template_path: Path) -> dict:
    """Load a ``_template.yaml``: the grading config (agent_id, precheck,
    rubric, optional precheck_module, default min_pages) SHARED across every
    entry in that folder's ``dataset.json`` — no prompt of its own. Same
    validation as ``load_scenario_yaml``, minus anything prompt-specific.
    """
    data = yaml.safe_load(template_path.read_text(encoding="utf-8")) or {}

    agent_id = data.get("agent_id")
    if not agent_id:
        raise ValueError(f"{template_path}: 'agent_id' is required")
    _resolve_agent_id(agent_id)

    precheck_config = data.get("precheck")
    if not isinstance(precheck_config, dict):
        raise ValueError(f"{template_path}: 'precheck' block is required")
    validate_precheck_config(precheck_config)

    rubric = data.get("rubric")
    if not rubric or not str(rubric).strip():
        raise ValueError(f"{template_path}: 'rubric' block is required and must be non-empty")

    default_min_pages = data.get("min_pages", DEFAULT_MIN_PAGES)
    if not isinstance(default_min_pages, int) or default_min_pages <= 0:
        raise ValueError(f"{template_path}: 'min_pages' must be a positive integer")

    precheck_module = None
    if "precheck_module" in data:
        precheck_module = _resolve_precheck_module(data["precheck_module"])

    return {
        "agent_id": agent_id,
        "precheck_config": precheck_config,
        "rubric": str(rubric).strip(),
        "precheck_module": precheck_module,
        "default_min_pages": default_min_pages,
        # Tool-using / file-editing agents only (prototype-build,
        # prototype-validate): the sandbox file to read back as the graded
        # response after dispatch. None (the default) keeps every text-only
        # agent's template unaffected.
        "deliverable_file": data.get("deliverable_file"),
    }


def load_dataset_scenarios(
    template_path: Path, dataset_path: Path, *, logs_root: Path = DEFAULT_LOGS_DIR
) -> list[GradedScenario]:
    """Combine one ``_template.yaml`` (shared precheck/rubric/custom hook)
    with every entry in a ``dataset.json`` array (``id`` + ``prompt`` +
    optional ``min_pages`` override) into one ``GradedScenario`` per entry.

    This is how a new prompt/industry gets added going forward: a new
    ``dataset.json`` entry, zero new Python, zero new YAML — the template's
    grading config is reused as-is (the "no new code for a new prompt" goal
    this branch exists to satisfy, extended from one agent per Python module
    to one prompt per dataset entry).
    """
    template = _load_template(template_path)
    entries = json.loads(dataset_path.read_text(encoding="utf-8"))
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"{dataset_path}: must be a non-empty JSON array")

    scenarios = []
    seen_ids: set[str] = set()
    for i, entry in enumerate(entries):
        entry_id = entry.get("id")
        if not entry_id:
            raise ValueError(f"{dataset_path}[{i}]: 'id' is required")
        if entry_id in seen_ids:
            raise ValueError(f"{dataset_path}: duplicate dataset entry id '{entry_id}'")
        seen_ids.add(entry_id)

        prompt = entry.get("prompt")
        if not prompt or not str(prompt).strip():
            raise ValueError(f"{dataset_path}[{i}] ('{entry_id}'): 'prompt' is required")

        min_pages = entry.get("min_pages", template["default_min_pages"])
        if not isinstance(min_pages, int) or min_pages <= 0:
            raise ValueError(
                f"{dataset_path}[{i}] ('{entry_id}'): 'min_pages' must be a positive integer"
            )

        precheck_config = dict(template["precheck_config"])
        if "min_sections" not in precheck_config:
            precheck_config["min_sections"] = min_pages

        seed_files = entry.get("seed_files")
        if seed_files is not None and not isinstance(seed_files, dict):
            raise ValueError(f"{dataset_path}[{i}] ('{entry_id}'): 'seed_files' must be an object")

        scenarios.append(
            GradedScenario(
                id=entry_id,
                agent_id=template["agent_id"],
                prompt=str(prompt).strip(),
                precheck_config=precheck_config,
                rubric=template["rubric"],
                min_pages=min_pages,
                precheck_module=template["precheck_module"],
                logs_dir=logs_root,
                source_path=dataset_path,
                industry=entry.get("industry"),
                seed_files=seed_files,
                deliverable_file=template["deliverable_file"],
            )
        )

    return scenarios


def find_dataset_scenarios(
    agent_id: str,
    dataset_name: str = "dataset",
    *,
    agents_root: Path = AGENTS_ROOT,
    logs_root: Path = DEFAULT_LOGS_DIR,
) -> list[GradedScenario]:
    """Load ONE named dataset file (``<dataset_name>.json``, default
    ``"dataset"`` → ``dataset.json``) from whichever ``scenarios/`` folder's
    ``_template.yaml`` declares ``agent_id`` — the ``dataset`` CLI command's
    lookup, so ``--dataset dataset_small`` can target
    ``scenarios/dataset_small.json`` instead of the default, without
    touching ``discover_all_scenarios``'s global (``dataset.json``-only)
    scan or its id-uniqueness bookkeeping.

    Raises ``ValueError`` if no ``scenarios/`` folder declares ``agent_id``,
    or ``FileNotFoundError`` if that folder has no ``<dataset_name>.json``.
    """
    for agent_dir in sorted(p for p in agents_root.iterdir() if p.is_dir()):
        scenarios_dir = agent_dir / "scenarios"
        template_path = scenarios_dir / "_template.yaml"
        if not template_path.exists():
            continue
        template = _load_template(template_path)
        if template["agent_id"] != agent_id:
            continue

        dataset_path = scenarios_dir / f"{dataset_name}.json"
        if not dataset_path.exists():
            raise FileNotFoundError(
                f"no '{dataset_name}.json' in {scenarios_dir} for agent_id '{agent_id}'"
            )
        return load_dataset_scenarios(template_path, dataset_path, logs_root=logs_root)

    raise ValueError(f"no scenarios/_template.yaml declares agent_id '{agent_id}'")


def discover_all_scenarios(*, agents_root: Path = AGENTS_ROOT) -> dict[str, GradedScenario]:
    """Discover every model-graded scenario across agent folders.

    Two supported per-agent scenario shapes, both discovered automatically:
      1. **Template + dataset** — a ``_template.yaml`` (shared precheck/
         rubric/custom hook) paired with a ``dataset.json`` array of prompt
         entries. One ``GradedScenario`` per dataset entry. This is how
         ``prototype_specify``'s scenarios are organized.
      2. **Standalone scenario YAML** (the original shape, still supported
         for a one-off scenario) — any ``*.yaml`` under ``scenarios/`` not
         starting with ``_``, self-contained (own prompt + precheck +
         rubric).

    Raises ``ValueError`` on a duplicate scenario id across the whole branch.
    """
    combined: dict[str, GradedScenario] = {}

    def _add(scenario: GradedScenario) -> None:
        if scenario.id in combined:
            raise ValueError(
                f"duplicate model-graded scenario id '{scenario.id}': "
                f"{combined[scenario.id].source_path} vs {scenario.source_path}"
            )
        combined[scenario.id] = scenario

    for agent_dir in sorted(p for p in agents_root.iterdir() if p.is_dir()):
        scenarios_dir = agent_dir / "scenarios"
        if not scenarios_dir.is_dir():
            continue

        template_path = scenarios_dir / "_template.yaml"
        dataset_path = scenarios_dir / "dataset.json"
        if template_path.exists() and dataset_path.exists():
            for scenario in load_dataset_scenarios(template_path, dataset_path):
                _add(scenario)

        for path in sorted(scenarios_dir.glob("*.yaml")):
            if path.stem.startswith("_"):
                continue
            _add(load_scenario_yaml(path))

    return combined
