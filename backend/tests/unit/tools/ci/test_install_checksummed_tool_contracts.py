"""
Contract for ``.github/actions/install-checksummed-tool`` (F-22).

The composite gained an optional ``archive-member`` input so an archive that nests
its binary (ShellCheck: ``shellcheck-vX.Y.Z/shellcheck``) can be installed without
a second extraction step. The default must leave every existing caller unchanged,
the input must be hardened against path traversal, and the checksum must still be
verified before anything is extracted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[5]
ACTION_PATH = (
    REPO_ROOT / ".github" / "actions" / "install-checksummed-tool" / "action.yml"
)
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
DEPLOY_YML = REPO_ROOT / ".github" / "workflows" / "deploy.yml"


def _action() -> dict[str, Any]:
    return yaml.safe_load(ACTION_PATH.read_text(encoding="utf-8"))


def _script() -> str:
    return _action()["runs"]["steps"][0]["run"]


def _callers() -> list[tuple[str, dict[str, Any]]]:
    """Every (workflow name, step) that uses the composite."""
    found: list[tuple[str, dict[str, Any]]] = []
    for path in (CI_YML, DEPLOY_YML):
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job in workflow["jobs"].values():
            for step in job.get("steps") or []:
                if "install-checksummed-tool" in str(step.get("uses", "")):
                    found.append((path.name, step))
    return found


def test_archive_member_is_optional_with_empty_default_when_declared() -> None:
    """Callers that keep the binary at the archive root pass nothing."""
    declared = _action()["inputs"]["archive-member"]
    assert declared["required"] is False
    assert declared["default"] == ""


def test_script_rejects_absolute_and_parent_members_when_extracting() -> None:
    """A member must stay inside the extraction directory."""
    script = _script()
    assert "ARCHIVE_MEMBER" in script
    assert "//*" in script, "an absolute member must be rejected"
    assert "*/../*" in script, "a `..` segment must be rejected"
    assert "::error::archive-member" in script


def test_member_defaults_to_binary_name_when_input_is_empty() -> None:
    """Existing callers extract ``binary-name`` from the archive root, as before."""
    assert 'member="${ARCHIVE_MEMBER:-$BINARY_NAME}"' in _script()


def test_checksum_is_verified_before_extraction_when_installing() -> None:
    """sha256sum -c must precede every tar/unzip of the archive."""
    script = _script()
    verify = script.index("sha256sum -c")
    assert verify < script.index("tar -xzf")
    assert verify < script.index("unzip -q")


def test_extraction_uses_member_and_install_uses_binary_name_when_nested() -> None:
    """Extract by member path, install under the plain binary name."""
    script = _script()
    assert '"$archive" -C "$workdir" "$member"' in script
    assert '"${workdir}/${member}" "/usr/local/bin/${BINARY_NAME}"' in script


def test_existing_callers_need_no_archive_member_when_binary_is_at_root() -> None:
    """Only ShellCheck (nested archive) passes archive-member."""
    with_member = sorted(
        step["with"]["name"]
        for _, step in _callers()
        if "archive-member" in step.get("with", {})
    )
    assert with_member == ["shellcheck"]


def test_shellcheck_step_passes_a_relative_member_when_installed_in_ci() -> None:
    """The member is relative, carries no ``..`` and names the binary."""
    (step,) = [step for _, step in _callers() if step["with"]["name"] == "shellcheck"]
    member = step["with"]["archive-member"]
    assert not member.startswith("/")
    assert ".." not in member.split("/")
    assert member.endswith("/shellcheck")
    assert step["with"]["binary-name"] == "shellcheck"
