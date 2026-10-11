"""
Contract for ``.github/workflows/release.yml`` and ``CHANGELOG.md`` (Phase 3.8).

A ``v*`` tag creates a GitHub Release with generated notes. The workflow is a
deliberately small, least-privilege island: tag pushes only, one job, the only
widening is ``contents: write`` on that job, no repository code is executed, and
it neither depends on nor touches the Deploy workflow. No supply-chain documents
are produced (user decision, see ci-cd-issue.md).

Whether a real tag produces a release with generated notes, the ``--prerelease``
flag for a suffixed tag and the idempotent re-run is only provable by pushing a
tag (needs-live-run).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from tools.ci.pin_authority import get_authority

REPO_ROOT = Path(__file__).resolve().parents[5]
RELEASE_YML = REPO_ROOT / ".github" / "workflows" / "release.yml"
DEPLOY_YML = REPO_ROOT / ".github" / "workflows" / "deploy.yml"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

FORBIDDEN_WORDS = ("sbom", "provenance", "attest", "cosign", "slsa", "anchore")
WIDE_PERMISSIONS = ("id-token", "packages", "statuses", "actions", "security-events")


def _text() -> str:
    return RELEASE_YML.read_text(encoding="utf-8")


def _workflow() -> dict[Any, Any]:
    return yaml.safe_load(_text())


def _triggers() -> dict[str, Any]:
    """`on:` parses as the boolean True key."""
    return _workflow()[True]


def _job() -> dict[str, Any]:
    (job,) = _workflow()["jobs"].values()
    return job


def _steps() -> list[dict[str, Any]]:
    return _job()["steps"]


def test_release_triggers_only_on_version_tag_push_when_configured() -> None:
    triggers = _triggers()
    assert set(triggers) == {"push"}
    assert triggers["push"] == {"tags": ["v*"]}


def test_release_permissions_are_least_privilege_when_declared() -> None:
    workflow = _workflow()
    assert workflow["permissions"] == {"contents": "read"}
    assert len(workflow["jobs"]) == 1, "the release workflow must stay one job"
    assert _job()["permissions"] == {"contents": "write"}
    for scope in WIDE_PERMISSIONS:
        assert scope not in workflow["permissions"]
        assert scope not in _job()["permissions"]


def test_release_job_pins_runner_and_timeout_when_defined() -> None:
    job = _job()
    assert job["runs-on"] == get_authority().runner_image
    timeout = job["timeout-minutes"]
    assert isinstance(timeout, int) and 1 <= timeout <= 30


def test_release_uses_no_unpinned_action_when_steps_run() -> None:
    """Every `uses:` (there are none today) must be a full SHA with a version comment."""
    for match in re.finditer(r"^\s*-?\s*uses:\s*(\S.*)$", _text(), re.MULTILINE):
        reference = match.group(1)
        assert re.match(r"[\w./-]+@[0-9a-f]{40}\s+#\s+v\d", reference), reference
    assert (
        "actions/checkout" not in _text()
    ), "the job runs no repository code, so it needs no checkout"


def test_release_run_block_has_no_event_interpolation_when_shell_executes() -> None:
    runs = [str(step["run"]) for step in _steps() if "run" in step]
    assert runs, "the job must have a run step"
    for script in runs:
        assert "${{" not in script, "expressions in run: are an injection surface"
    env = next(step["env"] for step in _steps() if "env" in step)
    assert env["GH_TOKEN"] == "${{ secrets.GITHUB_TOKEN }}"
    assert env["GH_REPO"] == "${{ github.repository }}"
    assert env["TAG_NAME"] == "${{ github.ref_name }}"


def test_release_generates_notes_and_verifies_tag_when_creating() -> None:
    script = "\n".join(str(step.get("run", "")) for step in _steps())
    assert "gh release create" in script
    assert "--generate-notes" in script
    assert "--verify-tag" in script
    assert "--prerelease" in script
    assert "--notes-start-tag" not in script, "GitHub picks the previous tag itself"


def test_release_validates_tag_shape_before_creating_when_tag_is_untrusted() -> None:
    script = "\n".join(str(step.get("run", "")) for step in _steps())
    assert script.index("=~") < script.index("gh release create")
    assert script.index("gh release view") < script.index("gh release create")


def test_release_has_no_sbom_provenance_or_attestation_when_scanned() -> None:
    lowered = _text().lower()
    for word in FORBIDDEN_WORDS:
        assert word not in lowered, f"release.yml must not mention {word!r}"


def test_release_does_not_touch_deploy_when_triggered() -> None:
    assert "deploy.yml" not in _text()
    assert "needs" not in _job()
    assert "workflow_run" not in _triggers()
    deploy_on = yaml.safe_load(DEPLOY_YML.read_text(encoding="utf-8"))[True]
    assert deploy_on["push"]["tags"] == ["v*"]
    assert deploy_on["push"]["branches"] == ["dev", "staging"]


def test_release_concurrency_never_cancels_when_a_release_is_running() -> None:
    concurrency = _workflow()["concurrency"]
    assert concurrency["cancel-in-progress"] is False
    assert "github.ref_name" in concurrency["group"]


def test_changelog_explains_generated_notes_when_present() -> None:
    text = CHANGELOG.read_text(encoding="utf-8")
    assert "release.yml" in text
    assert "generate" in text.lower()
    assert not re.search(r"^## \[", text, re.MULTILINE), "no invented version headings"
    assert not re.search(r"\b20\d\d-\d\d-\d\d\b", text), "no invented dates"
