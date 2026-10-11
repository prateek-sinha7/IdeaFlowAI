"""
Contracts for ``.github/actions/setup-backend`` dependency modes (F-17).

The composite installs one of three locked graphs, chosen by ``dev-deps``:

* ``"true"``     -> the dev group (pytest, coverage, ruff, pyright, ...);
* ``"ci-tools"`` -> ONLY the ``ci-tools`` group, for jobs that just run
  ``tools/ci/run_checks.py`` or a ``python -m tools.ci.<gate>`` gate;
* ``"false"``    -> production dependencies only.

What is pinned here:

* the install ``case`` has exactly those three branches plus an erroring
  default, so a typo cannot silently fall through to some other graph;
* the ci-tools branch installs only that group and exports ``UV_NO_SYNC=1``
  (without it, the jobs' later ``uv run --frozen`` re-syncs the default groups,
  i.e. the full prod+dev graph);
* the uv download cache is keyed per mode;
* the ``ci-tools`` group is exact, matches ``uv.lock``, and is exactly the
  third-party import closure of the gate entry points;
* every ``setup-backend`` use in ci.yml / deploy.yml requests the mode this
  table says, so a pytest/linter job cannot be moved to ci-tools (and a gate
  job cannot drift back to the full graph) without editing this table.
"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[5]
BACKEND_DIR = REPO_ROOT / "backend"
ACTION_PATH = REPO_ROOT / ".github" / "actions" / "setup-backend" / "action.yml"
TOOLS_CI_DIR = BACKEND_DIR / "tools" / "ci"
SETUP_BACKEND_USES = "./.github/actions/setup-backend"

#: The install modes, in the order the case statement lists them.
MODES = ("true", "ci-tools", "false")

#: The exact ci-tools group (normalised distribution name -> pinned version).
CI_TOOLS_PINS = {"defusedxml": "0.7.1", "pyyaml": "6.0.3", "requests": "2.34.2"}

#: Entry points a ci-tools job runs. ``__init__.py`` is included because
#: ``python -m tools.ci.<gate>`` imports the package first.
GATE_ENTRY_POINTS = ("__init__.py", "ci_gate.py", "scan_accepts.py", "run_checks.py")

#: Third-party top-level import name -> distribution in the ci-tools group.
IMPORT_TO_DISTRIBUTION = {
    "yaml": "pyyaml",
    "defusedxml": "defusedxml",
    "requests": "requests",
}

#: (workflow, job) -> the dev-deps mode its setup-backend step must request.
EXPECTED_JOB_MODES = {
    ("ci.yml", "repo-static"): "ci-tools",
    ("ci.yml", "backend-inventory"): "true",
    ("ci.yml", "backend-static"): "true",
    ("ci.yml", "backend-offline"): "true",
    ("ci.yml", "backend-postgres"): "true",
    ("ci.yml", "backend-evidence"): "true",
    ("ci.yml", "frontend-static"): "ci-tools",
    ("ci.yml", "frontend-evidence"): "ci-tools",
    ("ci.yml", "security"): "ci-tools",
    ("ci.yml", "container-scan"): "ci-tools",
    ("ci.yml", "ci-evidence"): "ci-tools",
    ("deploy.yml", "build"): "ci-tools",
}

_REQUIREMENT = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*==\s*([^\s;]+)\s*$")
_CASE_LABEL = re.compile(r"^\s*([^\s()]+)\)\s*$")


def _normalise(name: str) -> str:
    """PEP 503 normalised distribution name."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _action() -> dict[str, Any]:
    """The parsed setup-backend composite."""
    return yaml.safe_load(ACTION_PATH.read_text(encoding="utf-8"))


def _step(name_prefix: str) -> dict[str, Any]:
    """The composite step whose name starts with ``name_prefix``."""
    matches = [
        step
        for step in _action()["runs"]["steps"]
        if str(step.get("name", "")).startswith(name_prefix)
    ]
    assert len(matches) == 1, f"expected one step named {name_prefix!r}*"
    return matches[0]


def _case_branches(script: str) -> dict[str, list[str]]:
    """Map each label of the ``case "$DEV_DEPS"`` statement to its body lines."""
    lines = script.splitlines()
    starts = [i for i, ln in enumerate(lines) if ln.strip() == 'case "$DEV_DEPS" in']
    assert len(starts) == 1, 'install step must contain one `case "$DEV_DEPS" in`'
    branches: dict[str, list[str]] = {}
    label: str | None = None
    for line in lines[starts[0] + 1 :]:
        stripped = line.strip()
        if stripped == "esac":
            break
        match = _CASE_LABEL.match(line)
        if label is None and match:
            label = match.group(1)
            branches[label] = []
        elif stripped == ";;":
            label = None
        elif label is not None and stripped and not stripped.startswith("#"):
            branches[label].append(stripped)
    return branches


def _install_branches() -> dict[str, list[str]]:
    """The install step's case branches."""
    return _case_branches(_step("Install dependencies")["run"])


def _pins(requirements: list[str]) -> dict[str, str]:
    """Parse exact ``name==version`` requirements into a normalised mapping."""
    pins: dict[str, str] = {}
    for requirement in requirements:
        match = _REQUIREMENT.match(requirement)
        assert match, f"not an exact `name==version` pin: {requirement!r}"
        pins[_normalise(match.group(1))] = match.group(2)
    return pins


def _dependency_groups() -> dict[str, list[str]]:
    """``[dependency-groups]`` from backend/pyproject.toml."""
    pyproject = tomllib.loads(
        (BACKEND_DIR / "pyproject.toml").read_text(encoding="utf-8")
    )
    return pyproject["dependency-groups"]


def _lock() -> dict[str, Any]:
    """The parsed backend/uv.lock."""
    return tomllib.loads((BACKEND_DIR / "uv.lock").read_text(encoding="utf-8"))


def _module_file(module: str) -> Path:
    """Resolve a ``tools.ci[.x]`` module name to its file in the flat package."""
    parts = module.split(".")[2:]
    if not parts:
        return TOOLS_CI_DIR / "__init__.py"
    return TOOLS_CI_DIR.joinpath(*parts).with_suffix(".py")


def _imported_modules(node: ast.AST) -> list[str]:
    """Absolute module names one import node may load (tools.ci-relative)."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if not isinstance(node, ast.ImportFrom):
        return []
    if node.level == 0:
        base = node.module or ""
    else:
        assert (
            node.level == 1
        ), "tools/ci is a flat package; deeper relative imports are unexpected"
        base = "tools.ci" + (f".{node.module}" if node.module else "")
    modules = [base]
    if base.startswith("tools.ci"):
        # `from tools.ci import x` / `from . import x` may name a submodule.
        modules += [f"{base}.{alias.name}" for alias in node.names]
    return modules


def _third_party_import_closure() -> dict[str, set[str]]:
    """Third-party top-level names reachable from the gate entry points.

    Follows ``tools.ci.*`` and relative imports (including function-local ones)
    through the package. Returns top-level name -> files that import it.
    """
    stdlib = set(sys.stdlib_module_names)
    pending = [TOOLS_CI_DIR / name for name in GATE_ENTRY_POINTS]
    visited: set[Path] = set()
    third_party: dict[str, set[str]] = {}
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        visited.add(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            for module in _imported_modules(node):
                top = module.split(".")[0]
                if module.startswith("tools.ci"):
                    candidate = _module_file(module)
                    if candidate.exists():
                        pending.append(candidate)
                elif top and top not in stdlib and top != "tools":
                    third_party.setdefault(top, set()).add(path.name)
    return third_party


def _setup_backend_uses() -> dict[tuple[str, str], list[str]]:
    """(workflow, job) -> the dev-deps value of each setup-backend step in it."""
    uses: dict[tuple[str, str], list[str]] = {}
    for workflow in ("ci.yml", "deploy.yml"):
        path = REPO_ROOT / ".github" / "workflows" / workflow
        jobs = yaml.safe_load(path.read_text(encoding="utf-8"))["jobs"]
        for job_name, job in jobs.items():
            for step in job.get("steps", []) or []:
                if step.get("uses") == SETUP_BACKEND_USES:
                    mode = (step.get("with") or {}).get("dev-deps", "true")
                    uses.setdefault((workflow, job_name), []).append(str(mode))
    return uses


def test_setup_backend_rejects_unknown_mode_when_dev_deps_unrecognised() -> None:
    """Exactly true / ci-tools / false are accepted; anything else errors and exits 1."""
    branches = _install_branches()

    assert tuple(branches) == (*MODES, "*")
    default = branches["*"]
    assert any(line.startswith('echo "::error::') for line in default), default
    assert default[-1] == "exit 1"
    assert not any(line.startswith("uv sync") for line in default)


def test_setup_backend_installs_only_ci_tools_group_when_mode_ci_tools() -> None:
    """ci-tools installs only its group and stops later `uv run` from syncing more."""
    branches = _install_branches()

    assert branches["ci-tools"] == [
        "uv sync --locked --only-group ci-tools",
        'echo "UV_NO_SYNC=1" >> "$GITHUB_ENV"',
    ]
    assert branches["true"] == ["uv sync --locked --group dev"]
    assert branches["false"] == ["uv sync --locked --no-dev"]


def test_setup_backend_cache_suffix_separates_modes_when_caching() -> None:
    """Each mode is a different graph, so each gets its own uv cache suffix."""
    suffix = _step("Setup uv")["with"]["cache-suffix"]

    assert suffix.endswith(
        "-${{ inputs.dev-deps == 'true' && 'dev' || "
        "(inputs.dev-deps == 'ci-tools' && 'ci-tools' || 'prod') }}"
    ), suffix


def test_setup_backend_describes_three_modes_when_input_documented() -> None:
    """The input description names every accepted value."""
    description = _action()["inputs"]["dev-deps"]["description"]

    for mode in MODES:
        assert f'"{mode}"' in description


def test_ci_tools_group_is_exact_and_locked_when_declared() -> None:
    """The group is exactly the three pins, each equal to its uv.lock version."""
    groups = _dependency_groups()
    ci_tools = _pins(groups["ci-tools"])

    assert ci_tools == CI_TOOLS_PINS

    dev_defusedxml = [
        req for req in groups["dev"] if _normalise(req.split("==")[0]) == "defusedxml"
    ]
    assert _pins(dev_defusedxml) == {"defusedxml": ci_tools["defusedxml"]}

    lock = _lock()
    locked_versions: dict[str, set[str]] = {}
    for package in lock["package"]:
        locked_versions.setdefault(_normalise(package["name"]), set()).add(
            package["version"]
        )
    for name, version in ci_tools.items():
        assert (
            locked_versions.get(name) == {version}
        ), f"ci-tools pins {name}=={version} but uv.lock has {locked_versions.get(name)}"

    (root,) = [p for p in lock["package"] if p["name"] == "velocityai"]
    assert {_normalise(d["name"]) for d in root["dev-dependencies"]["ci-tools"]} == set(
        CI_TOOLS_PINS
    )
    assert {
        _normalise(d["name"]): d["specifier"]
        for d in root["metadata"]["requires-dev"]["ci-tools"]
    } == {name: f"=={version}" for name, version in CI_TOOLS_PINS.items()}


def test_ci_tools_group_covers_gate_imports_when_modules_load() -> None:
    """The group is exactly the third-party closure of what ci-tools jobs import."""
    closure = _third_party_import_closure()

    unmapped = {
        name: sorted(files)
        for name, files in closure.items()
        if name not in IMPORT_TO_DISTRIBUTION
    }
    assert not unmapped, f"gate modules import third-party packages the ci-tools group does not map: {unmapped}"
    needed = {IMPORT_TO_DISTRIBUTION[name] for name in closure}
    assert needed == set(_pins(_dependency_groups()["ci-tools"]))


def test_closure_rejects_unmapped_import_when_name_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The closure walk reports a third-party name the mapping does not know."""
    (tmp_path / "__init__.py").write_text("from . import gate\n", encoding="utf-8")
    (tmp_path / "gate.py").write_text(
        "import json\nimport yaml\n\ndef f():\n    import numpy\n", encoding="utf-8"
    )
    monkeypatch.setitem(globals(), "TOOLS_CI_DIR", tmp_path)
    monkeypatch.setitem(globals(), "GATE_ENTRY_POINTS", ("__init__.py",))

    closure = _third_party_import_closure()

    assert set(closure) == {"yaml", "numpy"}
    assert set(closure) - set(IMPORT_TO_DISTRIBUTION) == {"numpy"}


def test_job_dev_deps_mode_matches_expected_when_job_uses_setup_backend() -> None:
    """Every setup-backend use is in the table, and requests the mode it lists."""
    uses = _setup_backend_uses()

    assert set(uses) == set(EXPECTED_JOB_MODES), (
        f"setup-backend uses not in the table: {sorted(set(uses) - set(EXPECTED_JOB_MODES))}; "
        f"table rows with no use: {sorted(set(EXPECTED_JOB_MODES) - set(uses))}"
    )
    mismatched = {
        key: modes for key, modes in uses.items() if modes != [EXPECTED_JOB_MODES[key]]
    }
    assert not mismatched, f"dev-deps mode differs from the table: {mismatched}"
    assert all(mode in MODES for modes in uses.values() for mode in modes)
