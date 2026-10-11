"""
Documentation and dead-reference contracts for the CI/CD surface (Phase 3).

Two families live here:

* F-21 / F-34: the unreachable gate-contract script and its guide are gone, and
  no file names a removed job (``fast-checks``, ``security-scan-secrets``,
  ``ci-required-shadow``) in the active voice.
* F-33 / F-37 / R3-04: ``.github/CI_STATUS.md`` is the single entry point and
  matches the live YAML, the historical design records carry a banner, the
  README shows CI/Deploy badges and the rollback runbook never invents contacts.

Every test reads repository files only; nothing here touches the network or git.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from tools.ci.pin_authority import get_authority

REPO_ROOT = Path(__file__).resolve().parents[5]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

# ---------------------------------------------------------------------------
# 3.1  Removed scripts and removed job names
# ---------------------------------------------------------------------------

REMOVED_SCRIPTS = (
    REPO_ROOT / ".github" / "scripts" / "check-workflow-gate-contract.py",
    REPO_ROOT / ".github" / "scripts" / "INTEGRATION-GUIDE.md",
)

#: Text roots scanned for references to the deleted script.
_REFERENCE_ROOTS = (
    REPO_ROOT / ".github",
    REPO_ROOT / "docs",
    REPO_ROOT / "ci",
    REPO_ROOT / "backend" / "tools" / "ci",
    REPO_ROOT / "backend" / "tests" / "unit" / "tools" / "ci",
)
_TEXT_SUFFIXES = {".md", ".yml", ".yaml", ".py", ".json", ".toml", ".sh", ".txt"}

#: Words that mark a mention as describing something that is gone.
REMOVAL_MARKER = re.compile(
    r"retired|no longer|\bgone\b|neither|\bonce\b|used to|removed|does not exist"
    r"|no workflow|\bwas\b|\bsaid\b|earlier|originally|historical",
    re.IGNORECASE,
)
REMOVED_JOB_NAMES = re.compile(r"ci-required-shadow|fast-checks|security-scan-secrets")

#: Files whose live comments must not present a removed job as current.
REMOVED_JOB_FILES = (
    "backend/tools/ci/signal_registry.py",
    "backend/tools/ci/pin_authority.py",
    "ci/gitleaks.toml",
    "ci/gitleaksignore",
    ".github/ROLLBACK_PROCEDURE.md",
)


def _unmarked_removed_job_mentions(text: str, window: int = 3) -> list[int]:
    """1-based line numbers naming a removed job with no removal marker nearby."""
    lines = text.splitlines()
    offenders: list[int] = []
    for index, line in enumerate(lines):
        if not REMOVED_JOB_NAMES.search(line):
            continue
        lo = max(0, index - window)
        hi = min(len(lines), index + window + 1)
        if not REMOVAL_MARKER.search("\n".join(lines[lo:hi])):
            offenders.append(index + 1)
    return offenders


def _iter_reference_files() -> list[Path]:
    """Every text file under the scanned roots, excluding this module."""
    found: list[Path] = []
    for root in _REFERENCE_ROOTS:
        for path in root.rglob("*"):
            if "__pycache__" in path.parts or not path.is_file():
                continue
            if path.suffix in _TEXT_SUFFIXES and path != Path(__file__).resolve():
                found.append(path)
    return found


def test_gate_contract_script_is_absent_when_contract_lives_in_pytest() -> None:
    """The deleted script and guide stay deleted and nothing points at them."""
    for path in REMOVED_SCRIPTS:
        assert not path.exists(), f"{path} was removed in Phase 3 (F-21)"

    offenders: list[str] = []
    for path in _iter_reference_files():
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for number, line in enumerate(lines, start=1):
            if "check-workflow-gate-contract" not in line:
                continue
            if not REMOVAL_MARKER.search(line):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}")
    assert not offenders, (
        "check-workflow-gate-contract is removed; these lines reference it as "
        f"if it still existed: {offenders}"
    )


@pytest.mark.parametrize("relative", REMOVED_JOB_FILES)
def test_removed_job_names_are_not_active_voice_when_mentioned(relative: str) -> None:
    """A removed job may be named only while saying it is gone."""
    text = (REPO_ROOT / relative).read_text(encoding="utf-8")
    assert (
        _unmarked_removed_job_mentions(text) == []
    ), f"{relative} names a removed job without saying it is gone"


def test_removed_job_helper_flags_active_voice_when_no_marker_nearby() -> None:
    """Self-test: an active-voice mention is flagged."""
    assert _unmarked_removed_job_mentions("Installed by: ci.yml fast-checks (v1)") == [
        1
    ]


def test_removed_job_helper_accepts_mention_when_marker_is_adjacent() -> None:
    """Self-test: a mention next to a removal marker is accepted."""
    text = (
        "Installed by: ci.yml repo-static.\nfast-checks once installed it; it is gone."
    )
    assert _unmarked_removed_job_mentions(text) == []


def test_workflows_dir_exists_when_scanning_for_references() -> None:
    """Guard against the scan silently covering nothing."""
    assert WORKFLOWS_DIR.is_dir()
    assert _iter_reference_files()


# ---------------------------------------------------------------------------
# 3.6  CI_STATUS.md as the single entry point, banners, badges, runbook
# ---------------------------------------------------------------------------

CI_STATUS = REPO_ROOT / ".github" / "CI_STATUS.md"
ROLLBACK = REPO_ROOT / ".github" / "ROLLBACK_PROCEDURE.md"
README = REPO_ROOT / "README.md"

HISTORICAL_DOCS = (
    "docs/CICD-DESIGN-DECISIONS.md",
    "docs/CICD-RULESETS-DEPLOYMENT-SUMMARY.md",
    "docs/GITHUB_CICD_SETUP.md",
    "docs/GITHUB_RULESETS_SETUP.md",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _table_row(markdown: str, cell: str) -> str:
    """The markdown table row whose first cell is exactly ``cell``."""
    for line in markdown.splitlines():
        if line.startswith(f"| {cell} |"):
            return line
    raise AssertionError(f"no table row starting with {cell!r}")


def test_ci_status_lists_every_workflow_file_when_workflows_exist() -> None:
    """A new workflow must be added to the index, or this fails."""
    text = _text(CI_STATUS)
    missing = [
        path.name
        for path in sorted(WORKFLOWS_DIR.glob("*.yml"))
        if f"`{path.name}`" not in text
    ]
    assert missing == [], f"CI_STATUS.md workflow index is missing: {missing}"


def test_ci_status_lists_every_ci_job_when_jobs_are_declared() -> None:
    """Each ci.yml job id appears, in backticks, in the job table."""
    jobs = yaml.safe_load(_text(WORKFLOWS_DIR / "ci.yml"))["jobs"]
    text = _text(CI_STATUS)
    missing = [job for job in jobs if f"| `{job}` |" not in text]
    assert missing == [], f"CI_STATUS.md job table is missing: {missing}"


def test_ci_status_names_frontend_build_as_build_owner_when_build_moved() -> None:
    """The production build belongs to frontend-build, not frontend-static."""
    text = _text(CI_STATUS)
    assert "production build" in _table_row(text, "`frontend-build`").lower()
    assert "production build" not in _table_row(text, "`frontend-static`").lower()


def test_ci_status_states_runner_and_node_when_pins_are_recorded() -> None:
    """Runner label and Node major come from the live pin authority."""
    text = _text(CI_STATUS)
    authority = get_authority()
    assert authority.runner_image in text
    assert f"Node {authority.node_runtime_version.split('.')[0]}" in text
    assert "ubuntu-latest" not in text.replace("never `ubuntu-latest`", "")


def test_ci_status_has_a_changes_job_row_when_path_filter_exists() -> None:
    assert "path filter" in _table_row(_text(CI_STATUS), "`changes`")


@pytest.mark.parametrize("relative", HISTORICAL_DOCS)
def test_historical_banner_is_first_line_when_doc_is_a_design_record(
    relative: str,
) -> None:
    """The banner is the first non-empty line and points at CI_STATUS.md."""
    first = next(
        line for line in _text(REPO_ROOT / relative).splitlines() if line.strip()
    )
    assert "Historical design record" in first
    assert ".github/CI_STATUS.md" in first


def test_github_cicd_setup_has_no_stale_region_fallback_when_snippets_show_composite() -> (
    None
):
    """The region fallback moved into the aws-deploy-auth composite (F-25)."""
    text = _text(REPO_ROOT / "docs" / "GITHUB_CICD_SETUP.md")
    body_lines = [line for line in text.splitlines() if "no longer exists" not in line]
    body = "\n".join(body_lines)
    assert "vars.AWS_REGION ||" not in body
    assert "./.github/actions/aws-deploy-auth" in text


def test_readme_badges_point_at_ci_and_deploy_workflows_when_shown() -> None:
    """Two badges, both for this repository, linking to the workflow pages."""
    text = _text(README)
    badge = re.compile(
        r"\[!\[(?P<alt>[^\]]+)\]\(https://github\.com/(?P<slug>[\w.-]+/[\w.-]+)"
        r"/actions/workflows/(?P<file>[\w.-]+\.yml)/badge\.svg[^)]*\)\]"
        r"\(https://github\.com/(?P=slug)/actions/workflows/(?P=file)\)"
    )
    found = {m.group("file"): m.group("slug") for m in badge.finditer(text)}
    assert set(found) == {"ci.yml", "deploy.yml"}
    assert len(set(found.values())) == 1, "both badges must name the same repository"
    assert (WORKFLOWS_DIR / "ci.yml").is_file()
    assert (WORKFLOWS_DIR / "deploy.yml").is_file()


def test_rollback_procedure_marks_contacts_as_todo_when_unfilled() -> None:
    """Contacts are never invented: the placeholders became an explicit TODO."""
    text = _text(ROLLBACK)
    assert "[on-call]" not in text
    assert "[escalation contact]" not in text
    _, _, after = text.partition("## Emergency Contacts")
    section = after.split("\n## ", 1)[0]
    assert any(line.startswith("**TODO") for line in section.splitlines())
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", section), "no invented e-mail"
    assert "https://" not in section, "no invented rota URL"


def test_rollback_procedure_does_not_claim_rehearsal_when_none_is_recorded() -> None:
    assert "APPROVED & REHEARSED" not in _text(ROLLBACK)


def test_rollback_procedure_lists_frontend_build_and_changes_when_jobs_are_enumerated() -> (
    None
):
    text = _text(ROLLBACK)
    assert "frontend-build" in text
    assert "changes" in text
    assert "ci-required-shadow succeeds" not in text
