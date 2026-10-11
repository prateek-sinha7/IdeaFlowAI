"""
Scope contract for backend-static's ruff and pyright over repo-root Python (F-18).

The tracked Python under repo-root ``tools/`` and ``scripts/`` used to be
checked by nothing: ``ruff check .`` from backend/ never left backend/, and
pyright's ``include`` named only app/agents/tools. These tests pin the scope in
every place that defines it, so the CI runner, the configs and the pre-commit
hooks cannot drift apart:

* ci/backend-static-checks.json passes ``--config pyproject.toml`` and the
  ``../tools ../scripts`` paths to both ruff checks (without ``--config``, files
  outside backend/ would get ruff's defaults, not backend's rules);
* backend/pyrightconfig.json includes them, excludes the gitignored
  ``tools/loadtest``, and gives ``tools/knowledge`` its own import root;
* backend/pyproject.toml's ruff ``extend-exclude`` drops ``tools/loadtest``;
* the deliberate gaps (``scripts/generate-skills.js`` for ESLint) are written
  down with a reason;
* the pre-commit ruff hooks fire on the same trees with the same config.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[5]
BACKEND_DIR = REPO_ROOT / "backend"
CHECKS_PATH = REPO_ROOT / "ci" / "backend-static-checks.json"
PYRIGHT_CONFIG_PATH = BACKEND_DIR / "pyrightconfig.json"
PRE_COMMIT_PATH = REPO_ROOT / ".pre-commit-config.yaml"

RUFF_CHECK_IDS = ("ruff-lint", "ruff-format")
RUFF_HOOK_IDS = ("ruff", "ruff-format")


def _checks_config() -> dict[str, Any]:
    """The parsed backend-static check list."""
    return json.loads(CHECKS_PATH.read_text(encoding="utf-8"))


def _command(check_id: str) -> list[str]:
    """argv of one backend-static check."""
    (check,) = [c for c in _checks_config()["checks"] if c["check_id"] == check_id]
    return check["command"]


def _pyright_config() -> dict[str, Any]:
    """backend/pyrightconfig.json (strict UTF-8: a BOM makes pyright ignore the file)."""
    raw = PYRIGHT_CONFIG_PATH.read_bytes()
    assert not raw.startswith(
        b"\xef\xbb\xbf"
    ), "pyrightconfig.json must not start with a BOM"
    return json.loads(raw.decode("utf-8"))


def _ruff_hook(hook_id: str) -> dict[str, Any]:
    """One hook from the ruff-pre-commit repo entry."""
    config = yaml.safe_load(PRE_COMMIT_PATH.read_text(encoding="utf-8"))
    (repo,) = [r for r in config["repos"] if r["repo"].endswith("/ruff-pre-commit")]
    (hook,) = [h for h in repo["hooks"] if h["id"] == hook_id]
    return hook


@pytest.mark.parametrize("check_id", RUFF_CHECK_IDS)
def test_ruff_check_covers_repo_root_python_when_run_from_backend(
    check_id: str,
) -> None:
    """Both ruff checks lint backend/ plus ../tools and ../scripts with backend's config."""
    command = _command(check_id)

    config_at = command.index("--config")
    assert command[config_at + 1] == "pyproject.toml"
    assert command[-3:] == [".", "../tools", "../scripts"]
    assert command[:4] == ["uv", "run", "--frozen", "ruff"]


def test_ruff_format_check_stays_report_only_when_scope_widened() -> None:
    """The format check must never rewrite files in CI."""
    assert "--check" in _command("ruff-format")


def test_pyright_command_takes_scope_from_config_when_run() -> None:
    """pyright's scope lives in pyrightconfig.json, not in argv."""
    assert _command("pyright") == ["uv", "run", "--frozen", "pyright"]


def test_pyright_config_includes_repo_root_python_when_resolving_imports() -> None:
    """include adds ../tools and ../scripts; the gitignored loadtest stays out."""
    config = _pyright_config()

    assert {"app", "agents", "tools", "../tools", "../scripts"} <= set(
        config["include"]
    )
    assert "../tools/loadtest" in config["exclude"]


def test_pyright_config_scopes_sibling_imports_when_tools_knowledge_resolves() -> None:
    """tools/knowledge gets its own import root, limited to that directory."""
    environments = _pyright_config()["executionEnvironments"]

    assert environments == [
        {"root": "../tools/knowledge", "extraPaths": ["../tools/knowledge"]}
    ]


def test_ruff_extend_exclude_drops_loadtest_when_linting_repo_root() -> None:
    """ruff skips the gitignored load-test harness, matching CI checkouts."""
    pyproject = tomllib.loads(
        (BACKEND_DIR / "pyproject.toml").read_text(encoding="utf-8")
    )

    assert "../tools/loadtest" in pyproject["tool"]["ruff"]["extend-exclude"]


def test_scope_exclusions_document_generate_skills_when_eslint_skips_it() -> None:
    """The one unlinted JS file is a written decision, not an oversight."""
    exclusions = _checks_config()["scope_exclusions"]

    (entry,) = [e for e in exclusions if e["path"] == "scripts/generate-skills.js"]
    assert entry["tool"] == "eslint"
    assert entry["reason"].strip()
    assert all(str(e.get("reason", "")).strip() for e in exclusions)


@pytest.mark.parametrize("hook_id", RUFF_HOOK_IDS)
@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("tools/a.py", True),
        ("scripts/a.py", True),
        ("backend/app/a.py", True),
        ("frontend/a.py", False),
        ("tools/a.js", False),
    ],
)
def test_pre_commit_ruff_hook_matches_scope_when_file_staged(
    hook_id: str, path: str, expected: bool
) -> None:
    """The hooks fire on the same trees CI lints."""
    pattern = re.compile(_ruff_hook(hook_id)["files"])

    assert bool(pattern.search(path)) is expected


@pytest.mark.parametrize("hook_id", RUFF_HOOK_IDS)
def test_pre_commit_ruff_hook_uses_backend_config_when_run_from_repo_root(
    hook_id: str,
) -> None:
    """Explicit --config, so tools/ and scripts/ get backend's rules, not ruff's defaults."""
    args = _ruff_hook(hook_id)["args"]

    assert "--config=backend/pyproject.toml" in args
    assert "--force-exclude" in args
