"""CI checks for the Builder's ``velocity-workflow-creator`` skill.

The skill lives in ``backend/app/agents/workflow_builder/skills/velocity-workflow-creator/`` and is
edited there; that folder is the source of truth. Edits reach users on the next
deploy, so CI checks the skill still works and still matches the platform.

Run from ``backend/``::

    uv run python -m tools.ci.builder_skill_checks --selftest
    uv run python -m tools.ci.builder_skill_checks --step-models

Modes:

``--selftest``
    Run the skill's ``selftest.py``, plain and with ``--compiler .`` (the
    platform's real compiler), under ``PYTHONDONTWRITEBYTECODE=1``. Fails when a
    run fails or when it leaves a new change in the skill folder
    (``git status --porcelain``, Req 33.1, 33.4).

``--step-models``
    Fail when a ``ModelCatalog`` entry with ``builder_step=True`` is missing from
    the model ids of the skill's ``references/catalog.json``. The Builder offers
    those models to workflow steps, and the skill's validator only knows the
    models in its snapshot (Req 33.8, 41.4).

Exit codes: 0 success, 1 the mode found a problem, 2 the environment is wrong
(not a git checkout, git missing).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Collection, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from agents.capabilities.model_catalog import ModelCatalog
from app.agents.workflow_builder.script_policy import BUILDER_SKILL_ID

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_ENVIRONMENT = 2

_GIT_TIMEOUT_SECONDS = 60
_SCRIPT_TIMEOUT_SECONDS = 600
_SCRIPT_TAIL_LINES = 40


class ToolError(RuntimeError):
    """The environment cannot support the requested mode (git missing, no checkout)."""


@dataclass(frozen=True)
class Layout:
    """Where the repository, ``backend/`` and the skill are.

    Attributes:
        repo_root: The git work tree root.
        backend_dir: The ``backend/`` folder.
    """

    repo_root: Path
    backend_dir: Path

    @property
    def skill_dir(self) -> Path:
        """The skill folder, ``backend/app/agents/workflow_builder/skills/<skill id>``."""
        return (
            self.backend_dir
            / "app"
            / "agents"
            / "workflow_builder"
            / "skills"
            / BUILDER_SKILL_ID
        )

    @property
    def scripts_dir(self) -> Path:
        """The skill's ``scripts/`` folder."""
        return self.skill_dir / "scripts"

    @property
    def skill_pathspec(self) -> str:
        """The skill folder relative to the repo root, POSIX style."""
        return self.skill_dir.relative_to(self.repo_root).as_posix()


# --------------------------------------------------------------------------
# Git and script access
# --------------------------------------------------------------------------


def run_git(repo_root: Path, args: Sequence[str]) -> bytes:
    """Run ``git <args>`` in ``repo_root`` and return its stdout.

    Uses an argument list and no shell. This is the single place the tool calls
    git, so tests can replace it.

    Raises:
        ToolError: git is missing, times out or exits non-zero.
    """
    git = shutil.which("git")
    if git is None:
        raise ToolError("git was not found on PATH")
    try:
        completed = subprocess.run(
            [git, *args],
            cwd=repo_root,
            capture_output=True,
            check=False,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ToolError(f"git {' '.join(args)} failed: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ToolError(f"git {' '.join(args)} exited {completed.returncode}: {detail}")
    return completed.stdout


def resolve_layout() -> Layout:
    """Locate the repository root and ``backend/`` from this file's position.

    Raises:
        ToolError: The folder is not inside a git work tree.
    """
    backend_dir = Path(__file__).resolve().parents[2]
    top = run_git(backend_dir, ["rev-parse", "--show-toplevel"])
    repo_root = Path(top.decode("utf-8").strip()).resolve()
    return Layout(repo_root=repo_root, backend_dir=backend_dir)


@dataclass(frozen=True)
class ScriptResult:
    """Outcome of one skill script run.

    Attributes:
        returncode: The exit code, or -1 when the script could not run or timed out.
        output: Combined stdout and stderr.
    """

    returncode: int
    output: str


def run_script(argv: Sequence[str], cwd: Path) -> ScriptResult:
    """Run ``argv`` with the current interpreter's environment and bytecode writing off.

    Uses an argument list and no shell. This is the single place the tool starts
    a skill script, so tests can replace it. The child gets
    ``PYTHONDONTWRITEBYTECODE=1`` so it cannot write ``__pycache__`` into the
    skill folder (Req 33.1, 33.4) and ``PYTHONUTF8=1`` so its output decodes the
    same on every OS.
    """
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"}
    try:
        completed = subprocess.run(
            list(argv),
            cwd=cwd,
            env=env,
            capture_output=True,
            check=False,
            timeout=_SCRIPT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return ScriptResult(-1, f"timed out after {_SCRIPT_TIMEOUT_SECONDS} s")
    except OSError as exc:
        return ScriptResult(-1, f"could not start: {exc}")
    text = (completed.stdout + completed.stderr).decode("utf-8", errors="replace")
    return ScriptResult(completed.returncode, text)


def porcelain_status(repo_root: Path, pathspecs: Sequence[str]) -> frozenset[str]:
    """Return ``git status --porcelain`` lines under ``pathspecs``.

    Untracked and ignored files are listed one per line, so a new ``.pyc`` file
    shows up even though ``.gitignore`` hides ``__pycache__``.
    """
    out = run_git(
        repo_root,
        [
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--ignored",
            "--",
            *pathspecs,
        ],
    )
    lines = out.decode("utf-8", errors="replace").splitlines()
    return frozenset(line for line in lines if line.strip())


def _emit(stream: TextIO, lines: Sequence[str]) -> None:
    stream.write("\n".join(lines) + "\n")


def _tail(text: str, lines: int = _SCRIPT_TAIL_LINES) -> list[str]:
    kept = text.rstrip().splitlines()[-lines:]
    return [f"    {line}" for line in kept]


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# --selftest
# --------------------------------------------------------------------------


def run_selftest(layout: Layout) -> int:
    """Run ``selftest.py`` plain and with ``--compiler .``, from ``backend/``.

    Afterwards ``git status --porcelain`` of the skill folder must show nothing
    new. The status is read before and after, so uncommitted work that was
    already there is not blamed on the selftest; on a clean CI checkout this is
    the same as "empty".
    """
    selftest = layout.scripts_dir / "selftest.py"
    if not selftest.is_file():
        _emit(sys.stderr, [f"selftest: {selftest} not found"])
        return EXIT_FAILED

    pathspecs = [layout.skill_pathspec]
    before = porcelain_status(layout.repo_root, pathspecs)
    runs = (
        ("plain", [sys.executable, str(selftest)]),
        ("with --compiler .", [sys.executable, str(selftest), "--compiler", "."]),
    )
    problems: list[str] = []
    for label, argv in runs:
        result = run_script(argv, layout.backend_dir)
        if result.returncode == 0:
            _emit(sys.stdout, [f"selftest OK ({label})"])
            continue
        problems.append(f"selftest {label} exited {result.returncode}")
        problems.extend(_tail(result.output))

    changed = sorted(porcelain_status(layout.repo_root, pathspecs) - before)
    if changed:
        problems.append("selftest changed files in the skill folder:")
        problems.extend(f"    {line}" for line in changed)

    if not problems:
        return EXIT_OK
    _emit(sys.stderr, ["builder skill selftest FAILED:", *(f"  {p}" for p in problems)])
    return EXIT_FAILED


# --------------------------------------------------------------------------
# --step-models
# --------------------------------------------------------------------------


def snapshot_model_ids(catalog: object) -> frozenset[str]:
    """Return the model ids listed under ``models`` in a ``catalog.json`` document.

    Raises:
        ValueError: The document has no ``models`` list of objects with string ids.
    """
    models = catalog.get("models") if isinstance(catalog, dict) else None
    if not isinstance(models, list):
        raise ValueError("catalog has no 'models' list")
    ids: set[str] = set()
    for item in models:
        model_id = item.get("id") if isinstance(item, dict) else None
        if not isinstance(model_id, str):
            raise ValueError("catalog 'models' holds an entry without a string 'id'")
        ids.add(model_id)
    return frozenset(ids)


def step_model_problems(
    step_model_ids: Iterable[str], snapshot_ids: Collection[str]
) -> list[str]:
    """Name each Step_List model id the catalog snapshot lacks (empty when all are there).

    Args:
        step_model_ids: Ids of the ``ModelEntry`` objects with ``builder_step=True``.
        snapshot_ids: Model ids in the skill's ``references/catalog.json``.
    """
    return [
        f"builder_step model missing from the catalog snapshot: {model_id}"
        for model_id in sorted(set(step_model_ids) - set(snapshot_ids))
    ]


def run_step_models(layout: Layout) -> int:
    """Check every ``builder_step`` model is in the skill's catalog snapshot."""
    catalog_path = layout.skill_dir / "references" / "catalog.json"
    label = catalog_path.relative_to(layout.repo_root).as_posix()
    try:
        snapshot_ids = snapshot_model_ids(_read_json(catalog_path))
    except (OSError, ValueError) as exc:
        _emit(
            sys.stderr,
            [f"builder skill step-models FAILED: cannot read {label}: {exc}"],
        )
        return EXIT_FAILED

    step_ids = [entry.id for entry in ModelCatalog().list() if entry.builder_step]
    problems = step_model_problems(step_ids, snapshot_ids)
    if not step_ids:
        problems.append("no ModelCatalog entry has builder_step=True")
    if problems:
        _emit(
            sys.stderr,
            [
                f"builder skill step-models FAILED against {label}."
                " Refresh the skill catalog: from backend/ run"
                f" uv run python {layout.scripts_dir.relative_to(layout.backend_dir).as_posix()}"
                "/refresh_catalog.py --source .",
                *(f"  {problem}" for problem in problems),
            ],
        )
        return EXIT_FAILED
    _emit(
        sys.stdout,
        [f"step models OK: {len(step_ids)} builder_step models are in {label}"],
    )
    return EXIT_OK


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------

# Mode name (without the leading dashes) to handler.
_MODES: dict[str, Callable[[Layout], int]] = {
    "selftest": run_selftest,
    "step-models": run_step_models,
}

_MODE_HELP = {
    "selftest": "run the skill's selftest.py plain and with --compiler ., and fail on a new file change",
    "step-models": "fail when a builder_step=True model is missing from the skill's catalog snapshot",
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tools.ci.builder_skill_checks",
        description="CI checks for the Builder's velocity-workflow-creator skill.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    for name in _MODES:
        group.add_argument(
            f"--{name}",
            dest="mode",
            action="store_const",
            const=name,
            help=_MODE_HELP.get(name),
        )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the selected mode and return the process exit code."""
    args = _build_parser().parse_args(argv)
    try:
        layout = resolve_layout()
        return _MODES[args.mode](layout)
    except ToolError as exc:
        _emit(sys.stderr, [f"builder_skill_checks: {exc}"])
        return EXIT_ENVIRONMENT


if __name__ == "__main__":
    sys.exit(main())
