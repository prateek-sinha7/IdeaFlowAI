"""Cross-pipeline scenario discovery: scans every
workflow/<domain>/<variant>/scenarios/*.yaml (exactly 2 levels below
workflow/ — see common/__init__.py's docstring for the convention and what
to update if a 3rd nesting level is ever added) and returns a flat,
id-checked registry. This is what a SECOND pipeline (e.g.
workflow/ppt/revision/) plugs into automatically — nothing here needs
editing, only a new scenarios/ folder + checkers module in that new phase
folder.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from tests.evals.common.live_scenario import LiveScenario, load_scenario_yaml

EVALS_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_ROOT = EVALS_ROOT / "workflow"


def discover_scenarios_in(phase_dir: Path, checkers: dict) -> dict[str, LiveScenario]:
    """Load every scenarios/*.yaml under ONE phase folder (e.g.
    workflow/prototype/revision/). `checkers` and `fixtures_root=phase_dir`
    are passed straight through to load_scenario_yaml. Files whose stem
    starts with `_` are skipped (the _TEMPLATE.yaml convention).
    """
    scenarios_dir = phase_dir / "scenarios"
    out: dict[str, LiveScenario] = {}
    if not scenarios_dir.is_dir():
        return out
    for path in sorted(scenarios_dir.glob("*.yaml")):
        if path.stem.startswith("_"):
            continue
        out[path.stem] = load_scenario_yaml(
            path, checkers=checkers, fixtures_root=phase_dir, logs_root=EVALS_ROOT,
        )
    return out


def discover_all_scenarios() -> dict[str, LiveScenario]:
    """Walk workflow/*/*/scenarios dirs, import each phase folder's
    checkers.py (convention: every phase folder with a scenarios/ dir MUST
    have a sibling checkers.py exposing CHECKERS: dict), and merge all
    scenario ids into one flat dict.

    Raises ValueError on a duplicate scenario id across phase folders — ids
    are meant to be short/local, so a collision means two phases picked the
    same id, a real authoring error to catch, not to silently shadow.

    This is what live_benchmark.py / validate_scenario.py call instead of
    importing one hardcoded pipeline's scenario dict.
    """
    combined: dict[str, LiveScenario] = {}
    for scenarios_dir in sorted(WORKFLOW_ROOT.glob("*/*/scenarios")):
        phase_dir = scenarios_dir.parent  # workflow/<domain>/<variant>/
        rel = phase_dir.relative_to(WORKFLOW_ROOT)  # e.g. Path("prototype/revision")
        module_name = "tests.evals.workflow." + ".".join((*rel.parts, "checkers"))
        checkers_mod = importlib.import_module(module_name)
        found = discover_scenarios_in(phase_dir, checkers_mod.CHECKERS)
        for sid, scenario in found.items():
            if sid in combined:
                raise ValueError(
                    f"duplicate live-scenario id '{sid}': "
                    f"{combined[sid].source_path} vs {scenario.source_path}"
                )
            combined[sid] = scenario
    return combined
