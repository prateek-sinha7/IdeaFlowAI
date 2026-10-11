"""
Schema guard for ``.github/dependabot.yml`` (F-05 / F-30).

An unrecognised key invalidates the WHOLE file, which silently disables every
ecosystem (no error anywhere, only an absence of pull requests). These tests keep
the file to known v2 keys, keep ``reviewers:`` out (CODEOWNERS owns review) and
require a deliberate ``open-pull-requests-limit`` on every ecosystem.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[5]
DEPENDABOT = REPO_ROOT / ".github" / "dependabot.yml"

#: Keys GitHub's dependabot.yml options reference allows on an ``updates`` entry.
#: Extend this from https://docs.github.com/en/code-security/dependabot/working-with-dependabot/dependabot-options-reference
#: when GitHub adds keys; do not widen it to make a typo pass.
ALLOWED_UPDATE_KEYS = frozenset(
    {
        "package-ecosystem",
        "directory",
        "directories",
        "schedule",
        "allow",
        "assignees",
        "commit-message",
        "cooldown",
        "groups",
        "ignore",
        "insecure-external-code-execution",
        "labels",
        "milestone",
        "multi-ecosystem-group",
        "open-pull-requests-limit",
        "pull-request-branch-name",
        "rebase-strategy",
        "registries",
        "target-branch",
        "vendor",
        "versioning-strategy",
    }
)

#: Names that caused the F-05 outage: they are not part of the schema.
KNOWN_BAD_KEYS = frozenset({"ignore-conditions", "dependency-update-type"})


def _config() -> dict[str, Any]:
    return yaml.safe_load(DEPENDABOT.read_text(encoding="utf-8"))


def _updates() -> list[dict[str, Any]]:
    return _config()["updates"]


def _ids(update: dict[str, Any]) -> str:
    return f"{update['package-ecosystem']}:{update.get('directory', '?')}"


def test_dependabot_declares_schema_version_two_when_parsed() -> None:
    """Only v2 exists; anything else is ignored by GitHub."""
    assert _config()["version"] == 2


@pytest.mark.parametrize("update", _updates(), ids=_ids)
def test_update_has_required_keys_when_declared(update: dict[str, Any]) -> None:
    """Every ecosystem names itself, a directory and a schedule interval."""
    assert update["package-ecosystem"]
    assert update.get("directory") or update.get("directories")
    assert update["schedule"]["interval"]


def test_no_update_declares_reviewers_when_codeowners_covers_review() -> None:
    """`reviewers:` is deprecated in favour of CODEOWNERS and was removed."""
    assert [_ids(u) for u in _updates() if "reviewers" in u] == []


@pytest.mark.parametrize("update", _updates(), ids=_ids)
def test_every_update_sets_open_pull_requests_limit_when_configured(
    update: dict[str, Any],
) -> None:
    """A deliberate positive limit, never the implicit default of 5."""
    limit = update.get("open-pull-requests-limit")
    assert isinstance(limit, int) and not isinstance(limit, bool)
    assert limit > 0


@pytest.mark.parametrize("update", _updates(), ids=_ids)
def test_update_keys_are_valid_v2_keys_when_file_is_parsed(
    update: dict[str, Any],
) -> None:
    """Unknown keys invalidate the whole file; reject them by name and by allowlist."""
    keys = set(update)
    assert not keys & KNOWN_BAD_KEYS, f"{sorted(keys & KNOWN_BAD_KEYS)} are not v2 keys"
    assert keys <= ALLOWED_UPDATE_KEYS, (
        f"unknown dependabot keys {sorted(keys - ALLOWED_UPDATE_KEYS)}; an unknown key "
        f"disables every ecosystem in the file"
    )


def test_python_ecosystem_is_uv_when_lock_is_the_resolution_authority() -> None:
    """uv.lock is what CI installs from; `pip` would edit requirements*.txt."""
    backend = [u for u in _updates() if u.get("directory") == "/backend"]
    ecosystems = {u["package-ecosystem"] for u in backend}
    assert "uv" in ecosystems
    assert "pip" not in {u["package-ecosystem"] for u in _updates()}


def test_github_actions_ecosystem_covers_root_when_workflows_live_there() -> None:
    """`/` finds the workflows; the composite actions need their own glob entry."""
    actions = [u for u in _updates() if u["package-ecosystem"] == "github-actions"]
    assert len(actions) == 1
    dirs = actions[0].get("directories") or [actions[0]["directory"]]
    assert "/" in dirs
    assert "/.github/actions/*" in dirs
