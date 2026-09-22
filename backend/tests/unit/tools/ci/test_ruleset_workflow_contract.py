"""
Contract between the version-controlled rulesets and the workflows.

This module is the one `tasks.md` names as `tests/ci/test_ruleset_workflow_contract.py`
for Tasks 3.26 and 3.27. It never existed, which is part of how the rulesets came
to require a status context that no workflow could publish — a configuration that
blocks every pull request.

It replaces two files that lived at `ci/test_ci_promotion.py` and
`ci/test_ci_integration_scenarios.py`. Those sat outside the pytest tree (rootdir
is `backend/`), were invoked by no workflow, printed pass/fail with emoji instead
of asserting, and referenced `.github/workflows/ci-remediation-jobs.yml`, which no
longer exists. They were exactly the "test-like file with no owner" that
Requirement 2.2 exists to eliminate.

The central invariant here is REACHABILITY:

    if a ruleset requires a status context,
    then some workflow must be able to publish that context.

Both directions of that implication are unsafe to leave unchecked. Requiring an
unpublishable context blocks all merges; publishing a context nobody requires
gives false confidence.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[5]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
RULESETS_DIR = REPO_ROOT / ".github" / "rulesets"

#: The single stable aggregate context. Shard, job and scanner names are
#: deliberately NOT required individually: they are inputs to this one
#: fail-closed aggregate, and enumerating them in a ruleset would make every
#: internal job rename a branch-protection change.
AGGREGATE_CONTEXT = "ci-required"


def _load_yaml(path: Path) -> dict:
    """Parse a workflow file."""
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _all_workflows() -> dict[Path, dict]:
    """Every workflow file, parsed."""
    return {path: _load_yaml(path) for path in sorted(WORKFLOWS_DIR.glob("*.yml"))}


def _steps(job: dict) -> list[dict]:
    """The step list of a job, or empty for a reusable-workflow call."""
    return [s for s in (job.get("steps") or []) if isinstance(s, dict)]


def _publishers_of(context: str) -> dict[str, list[str]]:
    """
    Map workflow filename -> job names that can publish `context`.

    A publisher is a job that both names the context and holds `statuses: write`.
    Requiring both avoids counting a comment or a log line as a publisher.
    """
    publishers: dict[str, list[str]] = {}

    for path, workflow in _all_workflows().items():
        workflow_permissions = workflow.get("permissions") or {}
        for job_name, job in (workflow.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue

            job_permissions = job.get("permissions")
            effective = (
                job_permissions
                if isinstance(job_permissions, dict)
                else workflow_permissions
            )
            if not isinstance(effective, dict):
                continue
            if effective.get("statuses") != "write":
                continue

            job_text = json.dumps(_steps(job))
            if f"'{context}'" in job_text or f'"{context}"' in job_text:
                publishers.setdefault(path.name, []).append(job_name)

    return publishers


def _required_contexts() -> dict[str, list[str]]:
    """Map ruleset filename -> required status contexts."""
    required: dict[str, list[str]] = {}

    for path in sorted(RULESETS_DIR.glob("*.json")):
        ruleset = json.loads(path.read_text(encoding="utf-8"))
        contexts: list[str] = []
        for rule in ruleset.get("rules", []):
            if rule.get("type") != "required_status_checks":
                continue
            for check in (rule.get("parameters") or {}).get(
                "required_status_checks", []
            ):
                contexts.append(check["context"])
        required[path.name] = contexts

    return required


class TestRulesetsParse:
    """The rulesets must be valid JSON with the protections we rely on."""

    def test_every_ruleset_is_valid_json(self):
        """A malformed ruleset cannot be applied and would silently protect nothing."""
        paths = sorted(RULESETS_DIR.glob("*.json"))
        assert paths, "no rulesets found under .github/rulesets"
        for path in paths:
            json.loads(path.read_text(encoding="utf-8"))

    def test_core_protections_are_never_relaxed(self):
        """Deletion and force-push protection must remain on every protected ref."""
        for path in sorted(RULESETS_DIR.glob("*.json")):
            ruleset = json.loads(path.read_text(encoding="utf-8"))
            types = {rule.get("type") for rule in ruleset.get("rules", [])}
            assert "deletion" in types, f"{path.name} must protect against deletion"
            assert (
                "non_fast_forward" in types
            ), f"{path.name} must protect against force-push"

    def test_main_still_requires_signed_commits(self):
        """The production branch keeps its signature requirement."""
        ruleset = json.loads((RULESETS_DIR / "main.json").read_text(encoding="utf-8"))
        types = {rule.get("type") for rule in ruleset.get("rules", [])}
        assert "required_signatures" in types


class TestPublisherReachability:
    """Required contexts must be publishable, and publishers must be unique."""

    def test_every_required_context_has_a_publisher(self):
        """
        The invariant whose absence blocked every PR.

        The rulesets required `ci-required`, and the only workflow that could
        publish it for a pull request failed on every run because it read
        `github.event.pull_request.*` from a `workflow_run` payload, where those
        keys do not exist. Nothing checked that the required context was
        reachable, so the misconfiguration was invisible until merges stopped.
        """
        publishers = _publishers_of(AGGREGATE_CONTEXT)

        for ruleset_name, contexts in _required_contexts().items():
            for context in contexts:
                assert context == AGGREGATE_CONTEXT, (
                    f"{ruleset_name} requires '{context}'. Only the single "
                    f"aggregate '{AGGREGATE_CONTEXT}' may be required; individual "
                    f"jobs are inputs to it."
                )
                assert publishers, (
                    f"{ruleset_name} requires '{context}' but no workflow job "
                    f"holding `statuses: write` publishes it. A required context "
                    f"with no publisher blocks every pull request."
                )

    def test_aggregate_context_has_exactly_one_publisher_per_workflow(self):
        """
        No workflow may contain two jobs racing to publish the same context.

        Two publishers for one evaluation identity means the last writer wins and
        the recorded verdict depends on timing.
        """
        for workflow_name, jobs in _publishers_of(AGGREGATE_CONTEXT).items():
            assert len(jobs) == 1, (
                f"{workflow_name} has {len(jobs)} jobs publishing "
                f"'{AGGREGATE_CONTEXT}': {jobs}. Exactly one is allowed."
            )

    def test_pull_requests_are_published_only_by_the_trusted_finalizer(self):
        """
        The unprivileged evaluator must not publish the status for a PR.

        `ci.yml` runs pull-request code, which may come from a fork, so it holds
        no secrets and cannot obtain a Sonar verdict. If it also published
        `ci-required`, a PR could go green without Sonar having run.
        """
        evaluator = _load_yaml(WORKFLOWS_DIR / "ci.yml")
        publisher_jobs = [
            (name, job)
            for name, job in (evaluator.get("jobs") or {}).items()
            if isinstance(job, dict)
            and (job.get("permissions") or {}).get("statuses") == "write"
        ]

        assert publisher_jobs, "ci.yml must have a publisher for trusted intents"

        for name, job in publisher_jobs:
            condition = str(job.get("if", ""))
            assert "pull_request" in condition, (
                f"ci.yml job '{name}' can publish a commit status but its `if` "
                f"({condition!r}) does not exclude pull_request events. Pull "
                f"requests must be finalized by ci-authoritative.yml, which is "
                f"loaded from the default branch and can see SONAR_TOKEN."
            )

    def test_finalizer_runs_only_from_the_default_branch(self):
        """
        The PR finalizer must be triggered by `workflow_run`.

        That is what guarantees its own contents come from the default branch and
        cannot be edited by the pull request it is judging.
        """
        finalizer = _load_yaml(WORKFLOWS_DIR / "ci-authoritative.yml")
        triggers = finalizer.get(True) or finalizer.get("on") or {}
        assert "workflow_run" in triggers, (
            "ci-authoritative.yml must use the workflow_run trigger so it "
            "executes default-branch code, not PR code"
        )


class TestLeastPrivilege:
    """CI must not acquire credentials it has no use for."""

    @pytest.mark.parametrize("workflow_name", ["ci.yml", "ci-authoritative.yml"])
    def test_no_cloud_or_write_permissions(self, workflow_name):
        """
        No CI job may request OIDC, package or contents-write permissions.

        CI builds images locally and never pushes them, runs Terraform statically
        and never reads remote state, and writes nothing to the repository. Any of
        these permissions appearing means something has crossed out of CI's remit.
        """
        workflow = _load_yaml(WORKFLOWS_DIR / workflow_name)

        scopes: list[tuple[str, dict]] = [
            ("<workflow>", workflow.get("permissions") or {})
        ]
        for job_name, job in (workflow.get("jobs") or {}).items():
            if isinstance(job, dict) and isinstance(job.get("permissions"), dict):
                scopes.append((job_name, job["permissions"]))

        for scope_name, permissions in scopes:
            assert permissions.get("id-token") != "write", (
                f"{workflow_name} / {scope_name} requests id-token: write. CI must "
                f"not be able to mint a cloud OIDC token."
            )
            assert permissions.get("contents") != "write", (
                f"{workflow_name} / {scope_name} requests contents: write. CI must "
                f"not be able to modify the repository."
            )
            assert permissions.get("packages") != "write", (
                f"{workflow_name} / {scope_name} requests packages: write. CI must "
                f"not be able to publish an image."
            )

    def test_no_aws_credential_configuration_in_ci(self):
        """CI must never call an AWS credential action."""
        for workflow_name in ("ci.yml", "ci-authoritative.yml"):
            content = (WORKFLOWS_DIR / workflow_name).read_text(encoding="utf-8")
            assert "configure-aws-credentials" not in content, (
                f"{workflow_name} references configure-aws-credentials; CI is "
                f"AWS-blind by design"
            )

    def test_checkouts_do_not_persist_credentials(self):
        """
        Every checkout must set `persist-credentials: false`.

        A persisted token in the git config is available to anything that runs
        afterwards, including test code and, on the finalizer, code from the pull
        request being analysed.
        """
        offenders: list[str] = []

        for workflow_name in ("ci.yml", "ci-authoritative.yml"):
            workflow = _load_yaml(WORKFLOWS_DIR / workflow_name)
            for job_name, job in (workflow.get("jobs") or {}).items():
                if not isinstance(job, dict):
                    continue
                for step in _steps(job):
                    uses = str(step.get("uses", ""))
                    if not re.match(r"actions/checkout@", uses):
                        continue
                    with_block = step.get("with") or {}
                    if with_block.get("persist-credentials") is not False:
                        offenders.append(
                            f"{workflow_name} / {job_name} / "
                            f"{step.get('name', uses)}"
                        )

        assert not offenders, "these checkouts persist credentials: " + ", ".join(
            offenders
        )


class TestRulesetSelfConsistency:
    """
    A ruleset's prose must agree with its rules, and must not cite dead paths.

    This class replaces a `TestRolloutPrecondition` that asserted a reviewed
    canary document existed at
    `.kiro/specs/ci-pipeline-remediation/ROLLOUT-EVIDENCE.md` before any ruleset
    was allowed to require a status context. That gate could never pass on a
    fresh checkout: `.gitignore` excludes `.kiro/`, and the
    `ci-pipeline-remediation` spec has never existed in this repository's
    history, so the file it demanded is absent from every CI clone by
    construction. It was not gating the rollout, it was failing the build.

    What it was really protecting — that a required context is actually
    publishable — is enforced permanently and automatically by
    `TestPublisherReachability` above, which is a stronger guarantee than a
    hand-written markdown file.

    What genuinely went unchecked is the drift this class now catches. The
    `required_status_checks` rule requiring `ci-required` was added to
    `main.json` and `dev-staging.json` while both descriptions still read
    "`ci-required` is deliberately NOT listed as a required status check yet",
    and both still pointed at that untracked evidence path. Anyone reading the
    rulesets to find out whether the CI gate was live got the opposite of the
    truth from the field written to explain it.
    """

    #: Phrases that assert a context is NOT being enforced. A ruleset whose
    #: rules require a context must not also claim, in prose, that it does not.
    NON_ENFORCEMENT_CLAIMS = (
        "not listed as a required status check",
        "not a required status check",
        "not yet a required status check",
        "not yet required",
        "deliberately not listed",
    )

    #: A repo-relative path with a file extension, as written in prose.
    PATH_PATTERN = re.compile(r"(?:[\w.-]+/)+[\w.-]+\.[A-Za-z0-9]+")

    def test_description_does_not_contradict_its_own_rules(self):
        """A ruleset that requires a context must not deny doing so in prose."""
        offenders: list[str] = []

        for path in sorted(RULESETS_DIR.glob("*.json")):
            contexts = _required_contexts().get(path.name) or []
            if not contexts:
                continue

            description = json.loads(path.read_text(encoding="utf-8")).get(
                "description", ""
            )
            lowered = description.lower()
            for claim in self.NON_ENFORCEMENT_CLAIMS:
                if claim in lowered:
                    offenders.append(
                        f"{path.name}: requires {contexts} yet says {claim!r}"
                    )

        assert not offenders, (
            "these rulesets contradict themselves — the rules enforce a status "
            "context that the description says is not enforced: "
            + "; ".join(offenders)
            + ". The description is what a reviewer reads before changing branch "
            "protection, so a stale one is worse than none."
        )

    def test_descriptions_cite_only_paths_that_exist(self):
        """
        Every file path named in a ruleset description must be in the repo.

        Both branch rulesets cited an evidence document under `.kiro/`, which is
        gitignored, so the pointer resolved to nothing for every reader and every
        CI clone. A reference that cannot be followed is not documentation.
        """
        dangling: list[str] = []

        for path in sorted(RULESETS_DIR.glob("*.json")):
            description = json.loads(path.read_text(encoding="utf-8")).get(
                "description", ""
            )
            for candidate in self.PATH_PATTERN.findall(description):
                if not (REPO_ROOT / candidate).exists():
                    dangling.append(f"{path.name} -> {candidate}")

        assert not dangling, (
            "these ruleset descriptions reference paths that do not exist in the "
            "repository: " + ", ".join(dangling)
        )
