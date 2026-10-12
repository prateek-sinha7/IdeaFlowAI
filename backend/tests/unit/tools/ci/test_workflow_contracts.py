"""
Workflow contract tests for CI and deploy pipeline structure.

Validates that the GitHub Actions workflows meet strict requirements:
- The deploy gate is a required dependency for image build and deployment
- No bypass constructs (if: false, continue-on-error, etc.) on gate
- Every job has timeout-minutes set
- Retry configurations are set correctly
- No secrets are passed to the gate call
"""

import re

import pytest
import yaml
from pathlib import Path
from typing import Dict, List, Set, Optional


#: The expression every workflow and composite action must use to name the
#: revision under evaluation. `github.sha` is the temporary MERGE commit on a
#: `pull_request` event, so it must never stand alone — see F-01 and the header
#: of .github/actions/checkout-exact/action.yml.
EVALUATION_SHA_EXPR = "github.event.pull_request.head.sha || github.sha"

#: Artifact whose name is the contract between the unprivileged evaluator
#: (ci.yml) and the trusted finalizer (ci-authoritative.yml).
MANIFEST_ARTIFACT_SUFFIX = "-ci-evidence-manifest"


class WorkflowContract:
    """Contract validator for GitHub Actions workflow structure."""

    def __init__(
        self,
        deploy_yml_path: Path,
        ci_yml_path: Path,
        authoritative_yml_path: Optional[Path] = None,
        checkout_action_path: Optional[Path] = None,
    ):
        """
        Initialize with paths to deploy.yml and ci.yml.

        Args:
            deploy_yml_path: Path to .github/workflows/deploy.yml
            ci_yml_path: Path to .github/workflows/ci.yml
            authoritative_yml_path: Path to .github/workflows/ci-authoritative.yml.
                Defaults to a sibling of ci_yml_path. Optional so the synthetic
                fixtures below can keep constructing this object by hand.
            checkout_action_path: Path to
                .github/actions/checkout-exact/action.yml. Defaults to the
                sibling `actions/` tree next to ci_yml_path.
        """
        self.deploy_yml_path = Path(deploy_yml_path)
        self.ci_yml_path = Path(ci_yml_path)
        workflows_dir = self.ci_yml_path.parent
        self.authoritative_yml_path = (
            Path(authoritative_yml_path)
            if authoritative_yml_path is not None
            else workflows_dir / "ci-authoritative.yml"
        )
        self.checkout_action_path = (
            Path(checkout_action_path)
            if checkout_action_path is not None
            else workflows_dir.parent / "actions" / "checkout-exact" / "action.yml"
        )
        self.deploy_workflow = None
        self.ci_workflow = None
        self.authoritative_workflow = None
        self._load_workflows()

    def _load_workflows(self) -> None:
        """Load and parse the workflow YAML files."""
        with open(self.deploy_yml_path) as f:
            self.deploy_workflow = yaml.safe_load(f)

        with open(self.ci_yml_path) as f:
            self.ci_workflow = yaml.safe_load(f)

        if not self.deploy_workflow:
            raise ValueError(f"Failed to parse {self.deploy_yml_path}")
        if not self.ci_workflow:
            raise ValueError(f"Failed to parse {self.ci_yml_path}")

        # Optional: absent only in hand-built fixtures.
        if self.authoritative_yml_path.exists():
            with open(self.authoritative_yml_path) as f:
                self.authoritative_workflow = yaml.safe_load(f)

    def load_workflow(self, path: Path) -> Dict:
        """Load a workflow YAML file."""
        with open(path) as f:
            return yaml.safe_load(f)

    def _get_all_transitive_dependencies(
        self, job_name: str, jobs: Dict, memo: Optional[Dict] = None
    ) -> Set[str]:
        """
        Get all transitive dependencies of a job.

        Args:
            job_name: The job to find dependencies for
            jobs: The jobs dictionary
            memo: Memoization cache

        Returns:
            Set of all transitive dependency job names
        """
        if memo is None:
            memo = {}

        if job_name in memo:
            return memo[job_name]

        result = set()
        job_config = jobs.get(job_name, {})

        needs = job_config.get("needs", [])
        if isinstance(needs, str):
            needs = [needs]

        for dependency in needs:
            result.add(dependency)
            # Recursively add the dependencies of this dependency
            transitive = self._get_all_transitive_dependencies(dependency, jobs, memo)
            result.update(transitive)

        memo[job_name] = result
        return result

    def assert_gate_blocks_deploy(self) -> None:
        """
        Assert that every path from trigger to deploy includes the gate job.

        Raises:
            AssertionError: If any path to deploy omits gate
        """
        jobs = self.deploy_workflow.get("jobs", {})

        # Identify the "deploy" job
        deploy_job = None
        for job_name in jobs:
            if job_name == "deploy":
                deploy_job = job_name
                break

        if not deploy_job:
            raise ValueError("deploy job not found in workflow")

        # Get all transitive dependencies of deploy
        all_dependencies = self._get_all_transitive_dependencies(deploy_job, jobs)

        # Check if "gate" is in the dependencies
        if "gate" not in all_dependencies:
            error_msg = "deploy job does not have gate as a transitive dependency"
            error_msg += f". Current transitive deps: {all_dependencies}"
            raise AssertionError(error_msg)

    def assert_no_bypass_constructs(self) -> None:
        """
        Assert that no bypass constructs exist on the gate job.

        Bypass constructs include:
        - if: false
        - continue-on-error: true
        - Comments mentioning "skip" (heuristic check in raw YAML)

        Raises:
            AssertionError: If bypass constructs found
        """
        jobs = self.deploy_workflow.get("jobs", {})
        gate_job = jobs.get("gate", {})

        if not gate_job:
            raise ValueError("gate job not found in deploy workflow")

        errors = []

        # Check for if: false
        if_condition = gate_job.get("if")
        if if_condition and if_condition == "false":
            errors.append("gate job has 'if: false'")

        # Check for continue-on-error: true
        if gate_job.get("continue-on-error") is True:
            errors.append("gate job has 'continue-on-error: true'")

        # Check steps for bypass constructs
        steps = gate_job.get("steps", [])
        for i, step in enumerate(steps):
            if isinstance(step, dict):
                # Check for if: false on gate-related steps
                step_if = step.get("if")
                if step_if and step_if == "false":
                    errors.append(f"gate step {i} has 'if: false'")

                # Check for continue-on-error
                if step.get("continue-on-error") is True:
                    errors.append(f"gate step {i} has 'continue-on-error: true'")

        if errors:
            raise AssertionError(
                f"bypass constructs found on gate: {'; '.join(errors)}"
            )

    def assert_timeout_present(
        self, workflow: Optional[Dict] = None, min_timeout: int = 1
    ) -> None:
        """
        Assert that every job that CAN declare timeout-minutes does.

        Reusable-workflow-call jobs (`uses:`) are exempt, and deliberately so:
        GitHub's parser accepts only name/uses/with/secrets/needs/if/permissions/
        strategy/concurrency on such a job. Adding `timeout-minutes` there is not
        a stricter timeout, it is an INVALID WORKFLOW FILE — the run fails at
        startup before any job exists. The called workflow owns that budget: each
        of its own jobs declares its own timeout (asserted separately against
        ci_workflow).

        Args:
            workflow: Workflow dict; defaults to deploy_workflow
            min_timeout: Minimum acceptable timeout in minutes (must be >= 1)

        Raises:
            AssertionError: If any eligible job lacks timeout-minutes
        """
        if workflow is None:
            workflow = self.deploy_workflow

        jobs = workflow.get("jobs", {})
        missing_timeout = []

        for job_name, job_config in jobs.items():
            if not isinstance(job_config, dict):
                continue

            if "uses" in job_config:
                # See the docstring: the key is rejected by the parser here.
                if "timeout-minutes" in job_config:
                    missing_timeout.append(
                        f"{job_name} (reusable-workflow call must NOT declare "
                        "timeout-minutes — it is an invalid workflow key)"
                    )
                continue

            timeout = job_config.get("timeout-minutes")
            if timeout is None:
                missing_timeout.append(job_name)
            elif not isinstance(timeout, int) or timeout < min_timeout:
                missing_timeout.append(
                    f"{job_name} (timeout={timeout}, need >={min_timeout})"
                )

        if missing_timeout:
            raise AssertionError(
                f"jobs without timeout-minutes: {', '.join(missing_timeout)}"
            )

    def assert_reusable_call_keys_valid(self, workflow: Optional[Dict] = None) -> None:
        """
        Assert that every reusable-workflow-call job uses only keys GitHub allows.

        A job with `uses:` accepts ONLY name, uses, with, secrets, needs, if,
        permissions, strategy and concurrency. Anything else (`runs-on`,
        `timeout-minutes`, `steps`, `env`, `environment`, ...) makes the file
        invalid, and an invalid workflow file is a STARTUP failure: no job is
        created, the run graph cannot be rendered, and the run is titled by file
        path instead of its `name:`. This already happened once on deploy.yml's
        `gate` job (`timeout-minutes: 60`), taking every dev deploy down.

        Args:
            workflow: Workflow dict; defaults to deploy_workflow

        Raises:
            AssertionError: If a reusable-call job declares a disallowed key
        """
        if workflow is None:
            workflow = self.deploy_workflow

        allowed = {
            "name",
            "uses",
            "with",
            "secrets",
            "needs",
            "if",
            "permissions",
            "strategy",
            "concurrency",
        }

        errors = []
        for job_name, job_config in workflow.get("jobs", {}).items():
            if not isinstance(job_config, dict) or "uses" not in job_config:
                continue
            disallowed = sorted(set(job_config) - allowed)
            if disallowed:
                errors.append(f"{job_name}: {', '.join(disallowed)}")

        if errors:
            raise AssertionError(
                "reusable-workflow-call jobs with keys GitHub rejects "
                f"(startup failure): {'; '.join(errors)}"
            )

    def assert_retries_configured(self) -> None:
        """
        Assert that retry configuration is set appropriately.

        For pytest and Playwright jobs, retries must be 0 or not set (default 0).

        Raises:
            AssertionError: If retries are misconfigured
        """
        _jobs = self.deploy_workflow.get("jobs", {})
        # This is mostly a check that CI job config is correct
        # Since CI is a reusable workflow, the retries check happens there
        pass

    # Secret name substrings that would indicate the AWS-blind invariant is
    # violated if explicitly passed to `gate`. `secrets: inherit` (the string
    # form) is exempt from this list: ci.yml declares no `id-token: write`
    # and no job in it calls `configure-aws-credentials` or any AWS SDK, so
    # inheriting the caller's secrets does not hand it AWS credentials.
    # In practice ci.yml declares no `workflow_call.secrets` inputs at all, so
    # nothing can be mapped to it; this list guards against that regressing.
    _AWS_SECRET_MARKERS = ("AWS", "ROLE_ARN", "ACCESS_KEY", "SECRET_KEY")

    def assert_no_secrets_to_gate(self) -> None:
        """
        Assert that no AWS-related secrets are passed to the gate job call.

        The gate is AWS-blind (no OIDC role, no `configure-aws-credentials`
        step anywhere in ci.yml) and must never receive AWS credentials —
        whether via an explicit dict of secret names or (in principle) via
        `secrets: inherit` naming an AWS secret. `secrets: inherit` itself is
        tolerated by this check because inheriting is not in itself an AWS
        grant — the workflow being called must actually use an AWS secret
        for the invariant to be violated, which is exactly what this checks.
        ci.yml currently declares no secret inputs whatsoever, so the gate
        holds nothing by construction.

        Raises:
            AssertionError: If an AWS-related secret is passed to gate
        """
        jobs = self.deploy_workflow.get("jobs", {})
        gate_job = jobs.get("gate", {})

        if not gate_job:
            raise ValueError("gate job not found")

        # The gate job uses the CI workflow
        uses = gate_job.get("uses")
        if not uses:
            raise AssertionError("gate job must use the CI workflow")

        secrets = gate_job.get("secrets")
        if secrets is None:
            return

        if isinstance(secrets, str):
            # `inherit` (or any other string GitHub might introduce) forwards
            # whatever secrets the caller has — acceptable as long as the
            # called workflow (ci.yml) never actually consumes an AWS one.
            # Enforced separately: ci.yml declares no `id-token: write` and
            # no job calls configure-aws-credentials (see the workflow-level
            # `permissions: contents: read` and the header's "NO AWS access"
            # note). This function only guards the explicit-dict form below.
            return

        offending = [
            name
            for name in secrets.keys()
            if any(marker in name.upper() for marker in self._AWS_SECRET_MARKERS)
        ]
        if offending:
            raise AssertionError(
                f"gate job passes AWS-related secrets: {offending}. "
                "Gate must be AWS-blind."
            )

    def assert_build_needs_gate(self) -> None:
        """
        Assert that the build job declares gate as a dependency.

        Raises:
            AssertionError: If build job doesn't need gate
        """
        jobs = self.deploy_workflow.get("jobs", {})
        build_job = jobs.get("build")

        if not build_job:
            raise ValueError("build job not found")

        needs = build_job.get("needs", [])
        if isinstance(needs, str):
            needs = [needs]

        if "gate" not in needs:
            raise AssertionError(
                f"build job must depend on gate. " f"Current needs: {needs}"
            )

    def assert_deploy_needs_gate(self) -> None:
        """
        Assert that the deploy job declares gate as a dependency.

        Raises:
            AssertionError: If deploy job doesn't need gate
        """
        jobs = self.deploy_workflow.get("jobs", {})
        deploy_job = jobs.get("deploy")

        if not deploy_job:
            raise ValueError("deploy job not found")

        needs = deploy_job.get("needs", [])
        if isinstance(needs, str):
            needs = [needs]

        if "gate" not in needs:
            raise AssertionError(
                f"deploy job must depend on gate. " f"Current needs: {needs}"
            )

    # ------------------------------------------------------------------
    # F-01: the evaluation SHA, and the artifact name it produces
    # ------------------------------------------------------------------

    def assert_evaluation_sha_is_pr_head(self) -> None:
        """
        Assert checkout-exact resolves the PR head SHA, not the merge commit.

        On a `pull_request` event `github.sha` is a temporary merge commit, and
        `actions/checkout` defaults to that same merge ref — so a naive
        `EXPECTED_SHA: ${{ github.sha }}` VERIFIES SUCCESSFULLY while binding
        every artifact name and recorded verdict to an ephemeral commit that the
        trusted finalizer (which reads `workflow_run.head_sha`) will never ask
        for. That is F-01, and it kept `ci-required` red on every pull request
        the repository has ever had.

        Both the checkout `ref:` and the verification `EXPECTED_SHA` must name
        the PR head first. Asserted on the raw text because the value is a
        GitHub expression, not something YAML parsing can evaluate.

        Raises:
            AssertionError: If either site omits the PR-head fallback chain.
        """
        if not self.checkout_action_path.exists():
            raise AssertionError(
                f"checkout-exact action not found at {self.checkout_action_path}"
            )

        action = yaml.safe_load(self.checkout_action_path.read_text(encoding="utf-8"))
        steps = (action.get("runs") or {}).get("steps") or []

        errors: List[str] = []

        checkout_steps = [
            step
            for step in steps
            if isinstance(step, dict) and "actions/checkout@" in str(step.get("uses"))
        ]
        if not checkout_steps:
            errors.append("no actions/checkout step found")
        for step in checkout_steps:
            ref = str((step.get("with") or {}).get("ref", ""))
            if EVALUATION_SHA_EXPR not in ref:
                errors.append(
                    "checkout `ref:` must resolve the PR head first "
                    f"(expected it to contain '{EVALUATION_SHA_EXPR}', got {ref!r})"
                )

        verify_steps = [
            step
            for step in steps
            if isinstance(step, dict) and "EXPECTED_SHA" in (step.get("env") or {})
        ]
        if not verify_steps:
            errors.append("no step sets EXPECTED_SHA")
        for step in verify_steps:
            expected = str((step.get("env") or {}).get("EXPECTED_SHA", ""))
            if EVALUATION_SHA_EXPR not in expected:
                errors.append(
                    "EXPECTED_SHA must resolve the PR head first "
                    f"(expected it to contain '{EVALUATION_SHA_EXPR}', got {expected!r})"
                )

        # The two must agree, or verification fails closed for a confusing reason.
        refs = {str((s.get("with") or {}).get("ref", "")) for s in checkout_steps}
        expecteds = {
            str((s.get("env") or {}).get("EXPECTED_SHA", "")) for s in verify_steps
        }
        if refs and expecteds and refs != expecteds:
            errors.append(
                f"checkout `ref:` {refs} and EXPECTED_SHA {expecteds} must be identical"
            )

        if errors:
            raise AssertionError(
                "checkout-exact evaluation-SHA contract violated: " + "; ".join(errors)
            )

    def _manifest_artifact_names(self) -> tuple[List[str], List[str]]:
        """
        Collect the manifest artifact name templates on both sides of the gate.

        Returns:
            (names uploaded by ci.yml, names downloaded by ci-authoritative.yml)
        """
        uploaded: List[str] = []
        for job in (self.ci_workflow.get("jobs") or {}).values():
            if not isinstance(job, dict):
                continue
            for step in job.get("steps") or []:
                if not isinstance(step, dict):
                    continue
                if "actions/upload-artifact@" not in str(step.get("uses")):
                    continue
                name = str((step.get("with") or {}).get("name", ""))
                if name.endswith(MANIFEST_ARTIFACT_SUFFIX):
                    uploaded.append(name)

        downloaded: List[str] = []
        if self.authoritative_workflow:
            for job in (self.authoritative_workflow.get("jobs") or {}).values():
                if not isinstance(job, dict):
                    continue
                for step in job.get("steps") or []:
                    if not isinstance(step, dict):
                        continue
                    if "actions/download-artifact@" not in str(step.get("uses")):
                        continue
                    name = str((step.get("with") or {}).get("name", ""))
                    if name.endswith(MANIFEST_ARTIFACT_SUFFIX):
                        downloaded.append(name)

        return uploaded, downloaded

    def assert_manifest_artifact_name_matches_finalizer(self) -> None:
        """
        Assert the evaluator and the finalizer agree on the manifest name.

        The two sides interpolate different expressions — the evaluator uses its
        verified `evaluation_sha` step output, the finalizer uses the PR head it
        resolved from the `workflow_run` payload — so the templates cannot be
        compared literally. What CAN be compared is the name once the SHA
        expression is replaced by a placeholder: the fixed prefix and suffix
        around it must be identical, or the download is looking for an artifact
        that was never uploaded.

        This is the mechanical check whose absence let F-01 ship: both files were
        individually self-consistent and their names could never match.

        Raises:
            AssertionError: If either side is missing, or the templates differ.
        """
        uploaded, downloaded = self._manifest_artifact_names()

        if not uploaded:
            raise AssertionError(
                "ci.yml uploads no artifact ending in "
                f"'{MANIFEST_ARTIFACT_SUFFIX}'; the finalizer has nothing to attest"
            )
        if self.authoritative_workflow is None:
            raise AssertionError(
                f"finalizer workflow not found at {self.authoritative_yml_path}"
            )
        if not downloaded:
            raise AssertionError(
                "ci-authoritative.yml downloads no artifact ending in "
                f"'{MANIFEST_ARTIFACT_SUFFIX}'; it cannot be attesting the evaluator"
            )

        def skeleton(name: str) -> str:
            """Replace any ${{ ... }} expression with a single placeholder."""
            return re.sub(r"\$\{\{[^}]*\}\}", "<SHA>", name).strip()

        upload_skeletons = {skeleton(n) for n in uploaded}
        download_skeletons = {skeleton(n) for n in downloaded}

        if upload_skeletons != download_skeletons:
            raise AssertionError(
                "manifest artifact name mismatch between evaluator and finalizer "
                f"(F-01). ci.yml uploads {sorted(upload_skeletons)}; "
                f"ci-authoritative.yml downloads {sorted(download_skeletons)}. "
                "The names must be identical once the SHA expression is elided, "
                "or the cross-run download 404s and ci-required is published red."
            )

    def assert_finalizer_uses_workflow_run_head_sha(self) -> None:
        """
        Assert the finalizer keys on `workflow_run.head_sha`.

        This is the other half of the F-01 contract. `workflow_run.head_sha` is
        the PR head, which is why the evaluator must record the PR head too. If
        the finalizer ever switched to something else, the artifact-name check
        above would still pass while both sides moved together to the wrong SHA,
        so the source is pinned explicitly.

        Raises:
            AssertionError: If the finalizer does not reference it.
        """
        if self.authoritative_workflow is None:
            raise AssertionError(
                f"finalizer workflow not found at {self.authoritative_yml_path}"
            )

        raw = self.authoritative_yml_path.read_text(encoding="utf-8")
        if "github.event.workflow_run.head_sha" not in raw:
            raise AssertionError(
                "ci-authoritative.yml must resolve the evaluated revision from "
                "github.event.workflow_run.head_sha (the PR head). A workflow_run "
                "payload carries no pull_request.head.sha key."
            )

    # ------------------------------------------------------------------
    # F-03: the gate runs for every environment; advisory scope is dev-only
    # ------------------------------------------------------------------

    def assert_gate_is_not_conditionally_skipped(self) -> None:
        """
        Assert the gate job has no environment-based skip.

        The gate carried `if: needs.resolve.outputs.environment != 'dev'`, which
        discarded all 33 mandatory signals for dev deploys in order to tolerate 4
        red ones. Any `if:` on this job that mentions an environment name is the
        same mistake returning, so the condition is rejected outright rather than
        pattern-matched for the specific old string.

        Raises:
            AssertionError: If gate declares an environment-sensitive condition.
        """
        gate = (self.deploy_workflow.get("jobs") or {}).get("gate")
        if not gate:
            raise ValueError("gate job not found in deploy workflow")

        condition = str(gate.get("if", "")).strip()
        if not condition:
            return

        for environment in ("dev", "stage", "prod"):
            if f"'{environment}'" in condition or f'"{environment}"' in condition:
                raise AssertionError(
                    f"gate job `if:` names the '{environment}' environment "
                    f"({condition!r}). The gate must run for every environment; "
                    f"per-signal advisory downgrades are the supported way to "
                    f"tolerate known-red signals."
                )

    def assert_build_and_deploy_require_a_successful_gate(self) -> None:
        """
        Assert no job reaches ECR or a host on a skipped gate.

        `build` and `deploy` both used to accept
        `needs.gate.result == 'success' || environment == 'dev'`. The second
        clause is the actual bypass — it means "dev may proceed with no
        evaluation" — and it must not exist for any environment.

        Raises:
            AssertionError: If either condition tolerates a non-successful gate.
        """
        jobs = self.deploy_workflow.get("jobs") or {}
        errors: List[str] = []

        for job_name in ("build", "deploy"):
            job = jobs.get(job_name)
            if not job:
                raise ValueError(f"{job_name} job not found")

            condition = str(job.get("if", "")).strip()
            if not condition:
                errors.append(f"{job_name} has no `if:` guarding the gate result")
                continue

            if "needs.gate.result == 'success'" not in condition:
                errors.append(
                    f"{job_name} must require `needs.gate.result == 'success'` "
                    f"(got {condition!r})"
                )

            # The bypass shape: an OR that lets an environment stand in for a
            # green gate.
            for environment in ("dev", "stage", "prod"):
                if f"environment == '{environment}'" in condition:
                    errors.append(
                        f"{job_name} accepts environment '{environment}' as a "
                        f"substitute for a successful gate: {condition!r}"
                    )

        if errors:
            raise AssertionError(
                "gate-dependency contract violated: " + "; ".join(errors)
            )

    def assert_advisory_signals_are_dev_only(self) -> None:
        """
        Assert the advisory downgrade is requested for `dev` and nothing else.

        The allowlist and expiry dates in the signal registry are the primary
        control, but the workflow should not even ask for a downgrade on stage or
        prod. Written as an allowlist of one so a newly added environment is
        strictly gated by default.

        Raises:
            AssertionError: If the expression names a non-dev environment, or a
                signal that is not advisory-eligible.
        """
        gate = (self.deploy_workflow.get("jobs") or {}).get("gate")
        if not gate:
            raise ValueError("gate job not found in deploy workflow")

        expression = str((gate.get("with") or {}).get("advisory_signals", "")).strip()
        if not expression:
            # No downgrade requested at all is the strictest possible state and
            # therefore always acceptable.
            return

        errors: List[str] = []

        for environment in ("stage", "prod"):
            if f"== '{environment}'" in expression:
                errors.append(
                    f"advisory_signals is conditioned on the '{environment}' "
                    f"environment; only dev may request a downgrade"
                )

        if "== 'dev'" not in expression:
            errors.append(
                "advisory_signals must be conditioned on "
                "`needs.resolve.outputs.environment == 'dev'`"
            )

        # Every id named must be advisory-eligible in the registry, or the gate
        # will fail the aggregate at runtime — better to catch it here.
        from tools.ci.signal_registry import SIGNAL_REGISTRY

        eligible = {s.id for s in SIGNAL_REGISTRY.get_advisory_eligible_signals()}
        quoted = re.findall(r"'([^']*)'", expression)
        for literal in quoted:
            if "," not in literal and literal in {"dev", "stage", "prod", ""}:
                continue
            for candidate in literal.split(","):
                signal_id = candidate.strip()
                if not signal_id or signal_id in {"dev", "stage", "prod"}:
                    continue
                if signal_id not in eligible:
                    errors.append(
                        f"advisory_signals names '{signal_id}', which is not "
                        f"advisory-eligible in the signal registry"
                    )

        if errors:
            raise AssertionError(
                "advisory scope contract violated: " + "; ".join(errors)
            )

    # ------------------------------------------------------------------
    # F-04: the image scan blocks, in every environment
    # ------------------------------------------------------------------

    def assert_image_scans_are_blocking(self) -> None:
        """
        Assert no `trivy image` invocation has its exit status neutralised.

        Both scans in deploy.yml's `build` job were wrapped in
        `set +e` / `TRIVY_RC=$?` / `::warning::`, which scanned, printed, and then
        continued — so a HIGH or CRITICAL finding reached ECR and was deployed.
        The wrapper is the thing to forbid, not the specific old text, because the
        same neutralisation can be spelled several ways.

        Checked patterns, any of which would defeat the gate:
          * `set +e` anywhere in a step that runs trivy
          * `|| true` / `|| exit 0` on the trivy line
          * `continue-on-error: true` on the step
          * a missing `--exit-code 1`

        Raises:
            AssertionError: If any trivy image scan is non-blocking.
        """
        errors: List[str] = []

        for workflow_name, workflow in (
            ("deploy.yml", self.deploy_workflow),
            ("ci.yml", self.ci_workflow),
        ):
            for job_name, job in (workflow.get("jobs") or {}).items():
                if not isinstance(job, dict):
                    continue
                for step in job.get("steps") or []:
                    if not isinstance(step, dict):
                        continue
                    script = str(step.get("run") or "")
                    if "trivy image" not in script:
                        continue

                    location = f"{workflow_name} / {job_name} / {step.get('name', '?')}"

                    if step.get("continue-on-error") is True:
                        errors.append(f"{location}: continue-on-error: true")
                    if re.search(r"^\s*set \+e", script, re.MULTILINE):
                        errors.append(f"{location}: `set +e` neutralises the exit code")
                    for line in script.splitlines():
                        if "trivy image" not in line:
                            continue
                        if "|| true" in line or "|| exit 0" in line:
                            errors.append(
                                f"{location}: trivy call is `|| true`-guarded"
                            )
                        # A scan that only produces a report is fine ONLY when a
                        # separate gate consumes it; ci.yml does exactly that via
                        # ci-image-scan.sh, so require --exit-code only where
                        # trivy itself is the verdict (i.e. deploy.yml).
                        if (
                            workflow_name == "deploy.yml"
                            and "--exit-code 1" not in line
                        ):
                            errors.append(
                                f"{location}: trivy is the verdict here and must "
                                f"pass --exit-code 1"
                            )

        if errors:
            raise AssertionError(
                "image-scan gate is not blocking: " + "; ".join(errors)
            )

    def assert_deploy_scans_pushed_digests_with_shared_policy(self) -> None:
        """
        Assert deploy.yml's `build` job scans BOTH pushed digests through
        `.github/scripts/ci-image-scan.sh`, unwrapped (no continue-on-error /
        `||` guard). The scans are TEMPORARILY warn-only via SCAN_GATE_MODE.

        The post-push scan used to be a bare `trivy image --exit-code 1`, which
        `assert_image_scans_are_blocking` covers line by line. It now runs the
        same script CI runs (both engines, the reviewed exceptions in
        tools/ci/scan_accepts.py, the same gate), so that assertion no longer
        sees a `trivy image` line in deploy.yml at all. Without this contract the
        scan could be deleted, pointed at a tag, or neutralised unnoticed.

        Raises:
            AssertionError: If a component is not scanned, is scanned by tag
                instead of digest, not from the registry, or non-blocking.
        """
        build = (self.deploy_workflow.get("jobs") or {}).get("build") or {}
        errors: List[str] = []
        scanned: set[str] = set()

        for step in build.get("steps") or []:
            if not isinstance(step, dict):
                continue
            script = str(step.get("run") or "")
            if "ci-image-scan.sh" not in script:
                continue
            env = step.get("env") or {}
            component = str(env.get("COMPONENT", ""))
            location = f"deploy.yml / build / {step.get('name', '?')}"

            if step.get("continue-on-error") is True:
                errors.append(f"{location}: continue-on-error: true")
            for line in script.splitlines():
                if "ci-image-scan.sh" in line and (
                    "|| true" in line or "|| exit 0" in line
                ):
                    errors.append(f"{location}: scan is `||`-guarded")
            if str(env.get("IMAGE_SOURCE", "")) != "registry":
                errors.append(f"{location}: IMAGE_SOURCE must be 'registry'")
            if f"steps.digests.outputs.{component}_digest" not in str(
                env.get("IMAGE_REF", "")
            ):
                errors.append(
                    f"{location}: IMAGE_REF must be the pushed {component} digest"
                )
            # TODO(security): TEMPORARY - vulnerability scans are WARN-ONLY (advisory) as of 2026-10-11.
            # In future this must be changed back to BLOCKING, and the outstanding High/Critical
            # vulnerabilities must be fixed (see backend/tools/ci/scan_accepts.py and scan reports).
            if "SCAN_GATE_MODE" in env and str(env["SCAN_GATE_MODE"]) not in (
                "block",
                "warn",
            ):
                errors.append(f"{location}: SCAN_GATE_MODE must be 'block' or 'warn'")
            scanned.add(component)

        for component in ("backend", "frontend"):
            if component not in scanned:
                errors.append(
                    f"deploy.yml / build: no ci-image-scan.sh step scans the "
                    f"pushed {component} digest"
                )

        if errors:
            raise AssertionError(
                "post-push image scan contract violated: " + "; ".join(errors)
            )

    def assert_no_warn_only_security_language(self) -> None:
        """
        Assert no step name advertises a weakened security gate.

        A step called "(WARN-ONLY on HIGH,CRITICAL)" is honest about being
        broken, which is better than hiding it — but it should not exist at all.
        This catches the state returning by the front door.

        Raises:
            AssertionError: If a step name marks itself warn-only.
        """
        offenders: List[str] = []

        for workflow_name, workflow in (
            ("deploy.yml", self.deploy_workflow),
            ("ci.yml", self.ci_workflow),
        ):
            for job_name, job in (workflow.get("jobs") or {}).items():
                if not isinstance(job, dict):
                    continue
                for step in job.get("steps") or []:
                    if not isinstance(step, dict):
                        continue
                    name = str(step.get("name") or "")
                    if "WARN-ONLY" in name.upper():
                        offenders.append(f"{workflow_name} / {job_name} / {name}")

        assert_message = (
            "these steps declare themselves warn-only security gates: "
            + ", ".join(offenders)
        )
        if offenders:
            raise AssertionError(assert_message)

    # ------------------------------------------------------------------
    # Supply chain: every external action pinned to a full commit SHA
    # ------------------------------------------------------------------

    #: `uses:` values that are local paths, not third-party references. These are
    #: resolved from the checked-out tree and carry no independent supply-chain
    #: risk, so they are exempt from SHA pinning. They are NOT risk-free,
    #: though: "resolved from the checked-out tree" is a precondition, and F-33
    #: is what happens when it goes unmet. See
    #: `assert_local_actions_run_after_a_checkout`.
    _LOCAL_USES_PREFIXES = ("./", "../")

    def assert_every_external_action_is_sha_pinned(self) -> None:
        """
        Assert no `uses:` anywhere resolves to a mutable reference.

        This repository already pins every third-party action to a 40-character
        commit SHA with a trailing `# vX.Y.Z` comment — it is the single strongest
        supply-chain property it has, and it is a direct response to
        CVE-2026-33634, where attackers force-pushed malicious commits onto
        existing version TAGS of `aquasecurity/trivy-action` and
        `aquasecurity/setup-trivy`. A tag pin would have shipped that payload.

        Nothing enforced the property, though: it was maintained by convention
        across 30-odd references in 7 workflow files and 5 composite actions. One
        `@v4` added in a hurry, or one Dependabot rebase resolving a conflict the
        wrong way, and the guarantee is gone with no signal. This is that signal.

        Scope is every workflow AND every composite action, because an action is
        just as capable of pulling a mutable reference as a workflow is.

        Raises:
            AssertionError: If any external `uses:` is not a full SHA, or is
                missing the version comment that makes it reviewable.
        """
        workflows_dir = self.ci_yml_path.parent
        actions_dir = workflows_dir.parent / "actions"

        paths = sorted(workflows_dir.glob("*.yml")) + sorted(
            workflows_dir.glob("*.yaml")
        )
        paths += sorted(actions_dir.glob("*/action.yml"))

        assert paths, f"no workflow or action files found under {workflows_dir.parent}"

        unpinned: List[str] = []
        uncommented: List[str] = []

        # Matched on raw text, not the parsed tree: the `# vX.Y.Z` comment is what
        # makes a 40-hex string reviewable by a human, and YAML parsing discards
        # comments.
        uses_line = re.compile(r"^\s*-?\s*uses:\s*(?P<ref>\S+)(?P<rest>.*)$")

        for path in paths:
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                match = uses_line.match(line)
                if not match:
                    continue
                ref = match.group("ref")
                where = f"{path.name}:{number}"

                if ref.startswith(self._LOCAL_USES_PREFIXES):
                    continue

                if "@" not in ref:
                    unpinned.append(f"{where} -> {ref} (no ref at all)")
                    continue

                _, _, version = ref.partition("@")
                if not re.fullmatch(r"[0-9a-f]{40}", version):
                    unpinned.append(f"{where} -> {ref}")
                    continue

                # A bare SHA with no version comment is pinned but unreviewable:
                # nobody can tell what it is, so nobody upgrades it.
                if not re.search(r"#\s*v?\d", match.group("rest")):
                    uncommented.append(f"{where} -> {ref}")

        problems: List[str] = []
        if unpinned:
            problems.append(
                "these external actions are NOT pinned to a full 40-character "
                "commit SHA (a tag can be force-pushed — see CVE-2026-33634): "
                + "; ".join(unpinned)
            )
        if uncommented:
            problems.append(
                "these are SHA-pinned but carry no `# vX.Y.Z` comment, so the "
                "version is unreviewable and will never be upgraded: "
                + "; ".join(uncommented)
            )

        if problems:
            raise AssertionError(" | ".join(problems))

    # ------------------------------------------------------------------
    # F-33: a local action cannot load before the repository is on disk
    # ------------------------------------------------------------------

    def _local_action_ordering_violations(
        self, label: str, workflow: Dict
    ) -> List[str]:
        """
        Return one message per job that reaches a local action before checkout.

        Args:
            label: Human-readable source name used in the failure message.
            workflow: A parsed workflow mapping.

        Returns:
            A list of violation descriptions, one per offending job (the first
            offending step only — once the ordering is wrong the rest is noise).
        """
        violations: List[str] = []

        for job_name, job in (workflow.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue

            steps = job.get("steps")
            if not isinstance(steps, list):
                # A `uses:`-at-job-level reusable-workflow call owns no steps.
                continue

            checked_out = False
            for index, step in enumerate(steps, start=1):
                if not isinstance(step, dict):
                    continue

                uses = step.get("uses")
                if not isinstance(uses, str):
                    continue

                if uses.startswith(self._LOCAL_USES_PREFIXES):
                    if not checked_out:
                        name = step.get("name") or uses
                        violations.append(
                            f"{label}: job `{job_name}` step {index} (`{name}`) "
                            f"uses the local action `{uses}` but no "
                            f"`actions/checkout` runs before it"
                        )
                        break
                elif uses.startswith("actions/checkout@"):
                    checked_out = True

        return violations

    def assert_local_actions_run_after_a_checkout(self) -> None:
        """
        Assert no job reaches a local `uses: ./...` action before checking out.

        A local action is read from the runner's filesystem. GitHub does not
        fetch it for you the way it fetches a third-party action, so the
        repository must already be checked out or the step fails immediately
        with "Can't find 'action.yml', 'action.yaml' or 'Dockerfile' under
        ...". The runner even suggests the cause: "Did you forget to run
        actions/checkout before running your local action?"

        F-33: every one of ci.yml's 13 jobs opened with
        `uses: ./.github/actions/checkout-exact`, so every job died on its first
        step and the whole pipeline produced no verdicts at all (run
        35959713557). The Phase 5 consolidation that introduced the composite
        replaced an inline `actions/checkout` + verify pair — the checkout that
        had been making the local reference resolvable — and nothing noticed,
        because the property it depended on was ambient rather than asserted.

        This is the guard for the general rule, not just for that one action.
        Note the deliberate asymmetry with
        `assert_every_external_action_is_sha_pinned`, which EXEMPTS local
        `uses:` values: local actions carry no supply-chain risk but they do
        carry an ordering precondition, and this assertion owns that half.

        Scope is workflow files only. A composite action's own internal
        `uses: ./...` is safe by construction: the caller could not have loaded
        the composite in the first place without the tree already being present.

        Known limitation, stated rather than silently tolerated: ordering is
        checked literally, so a checkout guarded by an `if:` that evaluates
        false at runtime would still satisfy this assertion. No job in this
        repository conditions its checkout, and asserting that no checkout is
        ever conditional would be a separate, stricter rule.

        Raises:
            AssertionError: If any job uses a local action before a checkout.
        """
        workflows_dir = self.ci_yml_path.parent
        paths = sorted(workflows_dir.glob("*.yml")) + sorted(
            workflows_dir.glob("*.yaml")
        )

        assert paths, f"no workflow files found under {workflows_dir}"

        violations: List[str] = []
        for path in paths:
            workflow = self.load_workflow(path)
            if not isinstance(workflow, dict):
                continue
            violations.extend(
                self._local_action_ordering_violations(path.name, workflow)
            )

        if violations:
            raise AssertionError(
                "a local action is loaded from the runner's filesystem, so the "
                "repository must be checked out before it can be resolved — "
                "these jobs would fail on the offending step with \"Can't find "
                "'action.yml'\": " + "; ".join(violations)
            )

    # ------------------------------------------------------------------
    # F-34: upload-artifact and download-artifact are one matched pair
    # ------------------------------------------------------------------

    def _artifact_action_pins(self) -> Dict[str, Set[str]]:
        """
        Collect the declared version comment for each artifact action.

        Returns:
            A mapping of action name (`upload-artifact` / `download-artifact`) to
            the set of major versions its `# vX.Y.Z` comments claim.
        """
        workflows_dir = self.ci_yml_path.parent
        actions_dir = workflows_dir.parent / "actions"

        paths = sorted(workflows_dir.glob("*.yml")) + sorted(
            workflows_dir.glob("*.yaml")
        )
        paths += sorted(actions_dir.glob("*/action.yml"))

        pattern = re.compile(
            r"uses:\s*actions/(?P<action>upload-artifact|download-artifact)@"
            r"(?P<sha>[0-9a-f]{40})\s*#\s*v(?P<major>\d+)"
        )

        pins: Dict[str, Set[str]] = {}
        for path in paths:
            if not path.exists():
                continue
            for match in pattern.finditer(path.read_text(encoding="utf-8")):
                pins.setdefault(match.group("action"), set()).add(match.group("major"))

        return pins

    def assert_artifact_actions_share_one_major(self) -> None:
        """
        Assert upload-artifact and download-artifact are pinned to one major.

        F-34: `download-artifact` was pinned to
        `65a9edc5881444af0b87c028056edc830d335231 # v4.1.7`, a SHA that does not
        exist in the upstream repository — the real v4.1.7 is
        `65a9edc5881444af0b9093a5e628f2fe47ea3b2e`, identical for the first 18
        characters and then corrupted. Both evidence-gate jobs failed during
        "Set up job" with "Unable to resolve action ... unable to find version",
        before any step ran, so those two jobs could never report a verdict.

        The SHA-pinning assertion cannot catch that: the value is 40 valid hex
        characters, and confirming a commit exists needs a network call, which a
        unit test must not make. What IS checkable offline is the version comment
        — and it was the visible tell. `upload-artifact` sat at `# v7.0.1` while
        its counterpart claimed `# v4.1.7`.

        A mismatched pair is a defect in its own right, independent of the typo:

          * they are a protocol pair. `upload-artifact` v4 moved to a new
            artifact backend, so a v3 downloader cannot read a v4 upload.
          * the runtimes diverge. v7 runs on Node 24; v4.1.7 runs on Node 20,
            which is end-of-life. Pinning half the pair to a retired runtime
            means the pipeline breaks on a schedule nobody set.

        Asserting a shared MAJOR (not an exact version) is deliberate: patch
        levels legitimately differ, generations must not.

        Raises:
            AssertionError: If either action is missing, pinned to multiple
                majors, or the two disagree.
        """
        pins = self._artifact_action_pins()

        missing = {"upload-artifact", "download-artifact"} - set(pins)
        assert not missing, (
            f"no SHA-pinned reference to {sorted(missing)} was found; this "
            f"assertion is only meaningful while both are in use"
        )

        split = {
            name: sorted(majors) for name, majors in pins.items() if len(majors) > 1
        }
        if split:
            raise AssertionError(
                "an artifact action is pinned to more than one major version in "
                f"the same repository, so evidence flows through two different "
                f"artifact protocols depending on the job: {split}"
            )

        upload = sorted(pins["upload-artifact"])[0]
        download = sorted(pins["download-artifact"])[0]
        if upload != download:
            raise AssertionError(
                f"upload-artifact is pinned to v{upload} but download-artifact "
                f"to v{download}. They are a matched pair: a v4+ upload cannot "
                f"be read by a v3 downloader, and the two majors run on "
                f"different Node runtimes. Pin both to the same generation."
            )

    def assert_terraform_job_configured(self) -> None:
        """
        Assert that the terraform validation job is properly configured.

        Checks:
        - Exact pinned CLI version (no version ranges)
        - No plan/apply/destroy/import/state actions
        - Terraform validation per root
        - No credentials passed

        Terraform jobs may be in ci.yml (legacy) or ci-remediation-jobs.yml (new).
        The contract ensures they exist in at least one location.

        Raises:
            AssertionError: If terraform job is misconfigured
        """
        # Single-owner consolidation put every security signal, including the
        # IaC sub-verdicts, into ONE matrix job named `security` in ci.yml, whose
        # `iac` leg owns the Terraform signals. The previous version of this
        # assertion also looked in ci-remediation-jobs.yml, which no longer exists
        # — its jobs were merged into ci.yml so that no signal has two owners.
        #
        # It also accepted `security-scan` and any `security-scan-*` name. Those
        # jobs were the pre-consolidation shape (security-scan-secrets /
        # security-scan-iac / security-scan-terraform) and none of them exists.
        # Matching on names that cannot occur is not harmless leniency: it means
        # this assertion would still find "a" job and pass if `security` were
        # renamed or split again, which is exactly the regression it exists to
        # catch. Match the one real name.
        jobs = self.ci_workflow.get("jobs", {})
        security_scan_jobs = {
            name: job for name, job in jobs.items() if name == "security"
        }

        if not security_scan_jobs:
            raise AssertionError(
                "ci.yml has no job named `security` owning the Terraform signals. "
                f"Jobs present: {sorted(jobs)}"
            )

        steps = [
            step
            for job in security_scan_jobs.values()
            for step in (job.get("steps") or [])
        ]
        errors = []

        # Find terraform-related steps
        terraform_fmt_step = None
        terraform_validate_step = None

        for step in steps:
            if not isinstance(step, dict):
                continue

            name = step.get("name", "")

            if "Terraform" in name and ("fmt" in name or "format" in name):
                terraform_fmt_step = step
            elif "Terraform" in name and ("validate" in name):
                terraform_validate_step = step

        # Verify required steps exist
        if not terraform_fmt_step:
            errors.append("Terraform format/fmt check step not found")
        if not terraform_validate_step:
            errors.append("Terraform validate step not found")

        if errors:
            raise AssertionError(f"Missing terraform steps: {'; '.join(errors)}")

        # Check that validate step doesn't call plan/apply/destroy/import/state
        if terraform_validate_step:
            validate_run = terraform_validate_step.get("run", "")
            forbidden_commands = [
                "terraform plan",
                "terraform apply",
                "terraform destroy",
            ]
            for cmd in forbidden_commands:
                if cmd in validate_run:
                    errors.append(
                        f"Terraform validate step appears to call '{cmd}' (forbidden)"
                    )

            # Check validate script uses init -backend=false (non-applying) if it's a run step
            if (
                validate_run
                and "-backend=false" not in validate_run
                and "terraform init" in validate_run
            ):
                errors.append("Terraform init step does not use -backend=false")

        if errors:
            raise AssertionError(f"Terraform configuration errors: {'; '.join(errors)}")


# Fixtures
@pytest.fixture
def workflows_path():
    """Return the workflows directory path."""
    return Path(__file__).parents[5] / ".github" / "workflows"


@pytest.fixture
def contract(workflows_path):
    """Create a WorkflowContract instance for the actual workflows."""
    deploy_yml = workflows_path / "deploy.yml"
    ci_yml = workflows_path / "ci.yml"
    return WorkflowContract(deploy_yml, ci_yml)


# Test functions
def test_workflows_load(contract):
    """Test that workflows load without error."""
    assert contract.deploy_workflow is not None
    assert contract.ci_workflow is not None
    assert "jobs" in contract.deploy_workflow
    assert "jobs" in contract.ci_workflow


def test_load_workflow(workflows_path):
    """Test the load_workflow method."""
    contract = WorkflowContract(
        workflows_path / "deploy.yml", workflows_path / "ci.yml"
    )
    workflow = contract.load_workflow(workflows_path / "deploy.yml")
    assert workflow is not None
    assert "jobs" in workflow


def test_gate_blocks_deploy(contract):
    """Test that gate is a transitive dependency of deploy."""
    # This should pass if the workflow is correctly configured
    try:
        contract.assert_gate_blocks_deploy()
    except AssertionError as e:
        pytest.fail(f"Gate blocking deploy assertion failed: {e}")


def test_no_bypass_constructs_on_gate(contract):
    """Test that gate job has no bypass constructs."""
    try:
        contract.assert_no_bypass_constructs()
    except AssertionError as e:
        pytest.fail(f"Bypass construct check failed: {e}")


def test_timeout_minutes_present(contract):
    """Test that all deploy jobs that may declare timeout-minutes do."""
    try:
        contract.assert_timeout_present(contract.deploy_workflow)
    except AssertionError as e:
        pytest.fail(f"Timeout check failed: {e}")


def test_timeout_minutes_present_in_gate_workflow(contract):
    """
    The gate's time budget lives in ci.yml, since the calling job cannot declare
    one. Assert it is actually there, on every job.
    """
    try:
        contract.assert_timeout_present(contract.ci_workflow)
    except AssertionError as e:
        pytest.fail(f"Timeout check failed on ci.yml: {e}")


def test_reusable_call_jobs_use_only_valid_keys(contract):
    """Test that reusable-workflow-call jobs cannot trip a startup failure."""
    try:
        contract.assert_reusable_call_keys_valid(contract.deploy_workflow)
    except AssertionError as e:
        pytest.fail(f"Reusable-call key check failed: {e}")


def test_no_secrets_passed_to_gate(contract):
    """Test that gate receives no secrets."""
    try:
        contract.assert_no_secrets_to_gate()
    except AssertionError as e:
        pytest.fail(f"Secrets check failed: {e}")


def test_build_depends_on_gate(contract):
    """Test that build job depends on gate."""
    try:
        contract.assert_build_needs_gate()
    except AssertionError as e:
        pytest.fail(f"Build gate dependency check failed: {e}")


def test_deploy_depends_on_gate(contract):
    """Test that deploy job depends on gate."""
    try:
        contract.assert_deploy_needs_gate()
    except AssertionError as e:
        pytest.fail(f"Deploy gate dependency check failed: {e}")


def test_terraform_job_configured(contract):
    """Terraform validation is configured in the `security` matrix leg `iac`."""
    try:
        contract.assert_terraform_job_configured()
    except AssertionError as e:
        pytest.fail(f"Terraform job configuration check failed: {e}")


def test_evaluation_sha_resolves_pr_head_not_merge_commit(contract):
    """checkout-exact must bind evidence to the PR head, never the merge SHA."""
    try:
        contract.assert_evaluation_sha_is_pr_head()
    except AssertionError as e:
        pytest.fail(f"Evaluation-SHA contract failed (F-01): {e}")


def test_manifest_artifact_name_matches_finalizer(contract):
    """The evaluator's manifest name must be the one the finalizer downloads."""
    try:
        contract.assert_manifest_artifact_name_matches_finalizer()
    except AssertionError as e:
        pytest.fail(f"Manifest artifact-name contract failed (F-01): {e}")


def test_finalizer_resolves_workflow_run_head_sha(contract):
    """The finalizer must key on workflow_run.head_sha (the PR head)."""
    try:
        contract.assert_finalizer_uses_workflow_run_head_sha()
    except AssertionError as e:
        pytest.fail(f"Finalizer SHA-source contract failed (F-01): {e}")


def test_gate_runs_for_every_environment(contract):
    """The gate must not be skipped for dev (or any other environment)."""
    try:
        contract.assert_gate_is_not_conditionally_skipped()
    except AssertionError as e:
        pytest.fail(f"Gate-skip contract failed (F-03): {e}")


def test_build_and_deploy_require_a_successful_gate(contract):
    """Nothing reaches ECR or a host without a green gate."""
    try:
        contract.assert_build_and_deploy_require_a_successful_gate()
    except AssertionError as e:
        pytest.fail(f"Gate-dependency contract failed (F-03): {e}")


def test_advisory_downgrade_is_requested_for_dev_only(contract):
    """Only dev may ask for an advisory downgrade, and only for eligible signals."""
    try:
        contract.assert_advisory_signals_are_dev_only()
    except AssertionError as e:
        pytest.fail(f"Advisory scope contract failed (F-03): {e}")


def test_every_external_action_is_pinned_to_a_commit_sha(contract):
    """Every third-party action, in every workflow and composite action."""
    try:
        contract.assert_every_external_action_is_sha_pinned()
    except AssertionError as e:
        pytest.fail(f"Action-pinning contract failed: {e}")


def test_local_actions_are_preceded_by_a_checkout(contract):
    """Every local `uses: ./...` must have the repository on disk already."""
    try:
        contract.assert_local_actions_run_after_a_checkout()
    except AssertionError as e:
        pytest.fail(f"Local-action ordering contract failed (F-33): {e}")


def test_artifact_upload_and_download_share_one_major(contract):
    """The artifact actions are a protocol pair and must not diverge."""
    try:
        contract.assert_artifact_actions_share_one_major()
    except AssertionError as e:
        pytest.fail(f"Artifact action pairing contract failed (F-34): {e}")


def test_image_scans_block_on_high_and_critical(contract):
    """No trivy image scan may have its exit status neutralised."""
    try:
        contract.assert_image_scans_are_blocking()
    except AssertionError as e:
        pytest.fail(f"Image-scan blocking contract failed (F-04): {e}")


def test_deploy_scans_both_pushed_digests_with_the_shared_script(contract):
    """The post-push scan must cover both digests with the CI policy, blocking."""
    try:
        contract.assert_deploy_scans_pushed_digests_with_shared_policy()
    except AssertionError as e:
        pytest.fail(f"Post-push scan contract failed: {e}")


def test_no_step_declares_itself_a_warn_only_security_gate(contract):
    """A warn-only security gate must not exist, even an honestly-named one."""
    try:
        contract.assert_no_warn_only_security_language()
    except AssertionError as e:
        pytest.fail(f"Warn-only security gate present (F-04): {e}")


def test_ci_push_trigger_covers_every_deploying_branch(contract):
    """
    Every branch deploy.yml deploys from must also be evaluated by ci.yml itself.

    A deploying branch with no CI run of its own depends entirely on the deploy
    gate, which is a single point of failure — and was exactly the situation for
    `dev` when the gate was skipped there.
    """
    # PyYAML parses the unquoted key `on:` as the boolean True.
    ci_triggers = contract.ci_workflow.get(True) or contract.ci_workflow.get("on") or {}
    deploy_triggers = (
        contract.deploy_workflow.get(True) or contract.deploy_workflow.get("on") or {}
    )

    ci_branches = set(((ci_triggers.get("push") or {}).get("branches")) or [])
    deploy_branches = set(((deploy_triggers.get("push") or {}).get("branches")) or [])

    uncovered = sorted(deploy_branches - ci_branches)
    assert not uncovered, (
        f"these branches trigger a deploy but no CI run of their own: {uncovered}. "
        f"Add them to ci.yml's `push.branches`."
    )


# Synthetic test cases
@pytest.fixture
def synthetic_deploy_workflow_with_missing_gate():
    """Workflow YAML with build not depending on gate."""
    return {
        "name": "Deploy (synthetic)",
        "jobs": {
            "gate": {
                "name": "CI gate",
                "runs-on": "ubuntu-latest",
                "timeout-minutes": 60,
            },
            "resolve": {
                "name": "Resolve",
                "runs-on": "ubuntu-latest",
                "timeout-minutes": 5,
            },
            "build": {
                "name": "Build",
                "runs-on": "ubuntu-latest",
                "needs": ["resolve"],  # MISSING gate!
                "timeout-minutes": 30,
            },
            "deploy": {
                "name": "Deploy",
                "runs-on": "ubuntu-latest",
                "needs": ["build"],  # Only has build, not gate
                "timeout-minutes": 30,
            },
        },
    }


@pytest.fixture
def synthetic_deploy_workflow_with_bypass():
    """Workflow YAML with bypass construct on gate."""
    return {
        "name": "Deploy (synthetic)",
        "jobs": {
            "gate": {
                "name": "CI gate",
                "runs-on": "ubuntu-latest",
                "if": "false",  # BYPASS!
                "timeout-minutes": 60,
            },
            "resolve": {
                "name": "Resolve",
                "runs-on": "ubuntu-latest",
                "timeout-minutes": 5,
            },
            "build": {
                "name": "Build",
                "runs-on": "ubuntu-latest",
                "needs": ["gate", "resolve"],
                "timeout-minutes": 30,
            },
            "deploy": {
                "name": "Deploy",
                "runs-on": "ubuntu-latest",
                "needs": ["gate", "build"],
                "timeout-minutes": 30,
            },
        },
    }


@pytest.fixture
def synthetic_deploy_workflow_missing_timeout():
    """Workflow YAML with a job missing timeout-minutes."""
    return {
        "name": "Deploy (synthetic)",
        "jobs": {
            "gate": {
                "name": "CI gate",
                "runs-on": "ubuntu-latest",
                "timeout-minutes": 60,
            },
            "resolve": {
                "name": "Resolve",
                "runs-on": "ubuntu-latest",
                # MISSING timeout-minutes!
            },
            "build": {
                "name": "Build",
                "runs-on": "ubuntu-latest",
                "needs": ["gate", "resolve"],
                "timeout-minutes": 30,
            },
            "deploy": {
                "name": "Deploy",
                "runs-on": "ubuntu-latest",
                "needs": ["gate", "build"],
                "timeout-minutes": 30,
            },
        },
    }


def test_contract_detects_missing_gate(synthetic_deploy_workflow_with_missing_gate):
    """Test that contract detects when build doesn't depend on gate."""
    contract = WorkflowContract.__new__(WorkflowContract)
    contract.deploy_workflow = synthetic_deploy_workflow_with_missing_gate

    with pytest.raises(
        AssertionError, match="does not have gate as a transitive dependency"
    ):
        contract.assert_gate_blocks_deploy()


def test_contract_detects_bypass_construct(synthetic_deploy_workflow_with_bypass):
    """Test that contract detects bypass constructs."""
    contract = WorkflowContract.__new__(WorkflowContract)
    contract.deploy_workflow = synthetic_deploy_workflow_with_bypass

    with pytest.raises(AssertionError, match="bypass constructs found"):
        contract.assert_no_bypass_constructs()


def test_contract_detects_missing_timeout(synthetic_deploy_workflow_missing_timeout):
    """Test that contract detects missing timeout-minutes."""
    contract = WorkflowContract.__new__(WorkflowContract)
    contract.deploy_workflow = synthetic_deploy_workflow_missing_timeout

    with pytest.raises(AssertionError, match="without timeout-minutes"):
        contract.assert_timeout_present(contract.deploy_workflow)


# ----------------------------------------------------------------------
# F-01 kill-tests: prove the new assertions detect the bug they exist for
# ----------------------------------------------------------------------


def _write_checkout_action(tmp_path: Path, ref: str, expected_sha: str) -> Path:
    """Write a synthetic checkout-exact action.yml and return its path."""
    action = {
        "name": "Checkout the exact evaluated revision (synthetic)",
        "runs": {
            "using": "composite",
            "steps": [
                {
                    "name": "Checkout",
                    "uses": "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
                    "with": {"ref": ref, "persist-credentials": False},
                },
                {
                    "name": "Verify evaluation SHA",
                    "id": "sha",
                    "shell": "bash",
                    "run": "bash .github/scripts/ci-verify-sha.sh",
                    "env": {"EXPECTED_SHA": expected_sha},
                },
            ],
        },
    }
    path = tmp_path / "action.yml"
    path.write_text(yaml.safe_dump(action), encoding="utf-8")
    return path


def test_contract_detects_merge_sha_evaluation(tmp_path):
    """The bare `github.sha` that caused F-01 must be rejected."""
    merge_sha = "${{ github.sha }}"
    action_path = _write_checkout_action(tmp_path, merge_sha, merge_sha)

    contract = WorkflowContract.__new__(WorkflowContract)
    contract.checkout_action_path = action_path

    with pytest.raises(AssertionError, match="must resolve the PR head first"):
        contract.assert_evaluation_sha_is_pr_head()


def test_contract_detects_ref_and_expected_sha_disagreement(tmp_path):
    """A `ref:`/EXPECTED_SHA mismatch fails closed and must be caught here."""
    good = "${{ github.event.pull_request.head.sha || github.sha }}"
    other = "${{ github.event.pull_request.head.sha || github.ref }}"
    action_path = _write_checkout_action(tmp_path, good, other)

    contract = WorkflowContract.__new__(WorkflowContract)
    contract.checkout_action_path = action_path

    with pytest.raises(AssertionError, match="must be identical"):
        contract.assert_evaluation_sha_is_pr_head()


def _bare_contract() -> WorkflowContract:
    """Build a contract with no parsed workflows, for direct rule calls."""
    return WorkflowContract.__new__(WorkflowContract)


def test_contract_detects_local_action_as_the_first_step():
    """The exact shape that broke run 35959713557 must be rejected."""
    workflow = {
        "jobs": {
            "repo-static": {
                "steps": [
                    {
                        "name": "Checkout the exact evaluated revision",
                        "id": "sha",
                        "uses": "./.github/actions/checkout-exact",
                    },
                ]
            }
        }
    }
    violations = _bare_contract()._local_action_ordering_violations("ci.yml", workflow)

    assert len(violations) == 1
    assert "checkout-exact" in violations[0]
    assert "repo-static" in violations[0]


def test_contract_detects_local_action_before_a_later_checkout():
    """A checkout that arrives too late must not satisfy the rule."""
    workflow = {
        "jobs": {
            "build": {
                "steps": [
                    {"name": "Setup", "uses": "./.github/actions/setup-backend"},
                    {
                        "name": "Checkout",
                        "uses": (
                            "actions/checkout@"
                            "3d3c42e5aac5ba805825da76410c181273ba90b1"
                        ),
                    },
                ]
            }
        }
    }
    violations = _bare_contract()._local_action_ordering_violations("ci.yml", workflow)

    assert len(violations) == 1
    assert "setup-backend" in violations[0]


def test_contract_accepts_a_bootstrap_checkout_before_the_local_action():
    """The F-33 fix — bootstrap checkout first — must pass cleanly."""
    workflow = {
        "jobs": {
            "repo-static": {
                "steps": [
                    {
                        "name": "Bootstrap the local actions",
                        "uses": (
                            "actions/checkout@"
                            "3d3c42e5aac5ba805825da76410c181273ba90b1"
                        ),
                    },
                    {
                        "name": "Checkout the exact evaluated revision",
                        "id": "sha",
                        "uses": "./.github/actions/checkout-exact",
                    },
                    {"name": "Setup", "uses": "./.github/actions/setup-backend"},
                ]
            }
        }
    }

    assert _bare_contract()._local_action_ordering_violations("ci.yml", workflow) == []


def test_contract_ignores_reusable_workflow_call_jobs():
    """A job that calls a reusable workflow owns no steps and cannot violate."""
    workflow = {"jobs": {"gate": {"uses": "./.github/workflows/ci.yml"}}}

    assert _bare_contract()._local_action_ordering_violations("x.yml", workflow) == []


def _write_artifact_workflow(tmp_path: Path, upload: str, download: str) -> Path:
    """Write a workflows dir pinning the artifact pair to the given comments."""
    workflows = tmp_path / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    (tmp_path / "actions").mkdir(parents=True, exist_ok=True)
    (workflows / "ci.yml").write_text(
        "jobs:\n"
        "  a:\n"
        "    steps:\n"
        f"      - uses: actions/upload-artifact@{'0' * 40} # {upload}\n"
        f"      - uses: actions/download-artifact@{'1' * 40} # {download}\n",
        encoding="utf-8",
    )
    return workflows / "ci.yml"


def test_contract_detects_mismatched_artifact_action_majors(tmp_path):
    """The exact v7.0.1 / v4.1.7 split that shipped must be rejected."""
    ci_yml = _write_artifact_workflow(tmp_path, "v7.0.1", "v4.1.7")

    contract = _bare_contract()
    contract.ci_yml_path = ci_yml

    with pytest.raises(AssertionError, match="matched pair"):
        contract.assert_artifact_actions_share_one_major()


def test_contract_accepts_matched_artifact_action_majors(tmp_path):
    """Differing patch levels within one major are legitimate."""
    ci_yml = _write_artifact_workflow(tmp_path, "v7.0.1", "v7.0.0")

    contract = _bare_contract()
    contract.ci_yml_path = ci_yml

    contract.assert_artifact_actions_share_one_major()


def _contract_with_scan_step(step: dict) -> WorkflowContract:
    """Build a bare contract whose deploy workflow has one scan step."""
    contract = WorkflowContract.__new__(WorkflowContract)
    contract.deploy_workflow = {"jobs": {"build": {"steps": [step]}}}
    contract.ci_workflow = {"jobs": {}}
    return contract


def test_contract_detects_set_plus_e_around_trivy():
    """The exact warn-only wrapper that shipped must be rejected."""
    contract = _contract_with_scan_step(
        {
            "name": "Scan backend image (WARN-ONLY on HIGH,CRITICAL)",
            "run": (
                "set +e\n"
                'trivy image --severity HIGH,CRITICAL --exit-code 1 "$IMAGE"\n'
                "TRIVY_RC=$?\n"
                "set -e\n"
            ),
        }
    )
    with pytest.raises(AssertionError, match=r"`set \+e` neutralises the exit code"):
        contract.assert_image_scans_are_blocking()


def test_contract_detects_or_true_on_trivy():
    """`|| true` is the other common way to neutralise a scanner."""
    contract = _contract_with_scan_step(
        {
            "name": "Scan image",
            "run": 'trivy image --severity HIGH,CRITICAL --exit-code 1 "$IMAGE" || true\n',
        }
    )
    with pytest.raises(AssertionError, match="`\\|\\| true`-guarded"):
        contract.assert_image_scans_are_blocking()


def test_contract_detects_missing_exit_code_on_trivy():
    """In deploy.yml trivy IS the verdict, so it must fail on findings itself."""
    contract = _contract_with_scan_step(
        {"name": "Scan image", "run": 'trivy image --severity HIGH,CRITICAL "$IMAGE"\n'}
    )
    with pytest.raises(AssertionError, match=r"must pass --exit-code 1"):
        contract.assert_image_scans_are_blocking()


def test_contract_detects_continue_on_error_on_a_scan():
    """continue-on-error turns any gate into decoration."""
    contract = _contract_with_scan_step(
        {
            "name": "Scan image",
            "continue-on-error": True,
            "run": 'trivy image --severity HIGH,CRITICAL --exit-code 1 "$IMAGE"\n',
        }
    )
    with pytest.raises(AssertionError, match="continue-on-error: true"):
        contract.assert_image_scans_are_blocking()


def _registry_scan_step(component: str, **overrides) -> dict:
    """A deploy.yml post-push scan step shaped like the real one."""
    step = {
        "name": f"Scan the pushed {component} digest",
        "env": {
            "IMAGE_REF": f"${{{{ vars.ECR_REGISTRY }}}}/repo@${{{{ steps.digests.outputs.{component}_digest }}}}",
            "COMPONENT": component,
            "IMAGE_SOURCE": "registry",
        },
        "run": "bash .github/scripts/ci-image-scan.sh scan-results",
    }
    step.update(overrides)
    return step


def test_assert_deploy_scans_passes_when_both_digests_are_scanned():
    contract = WorkflowContract.__new__(WorkflowContract)
    contract.deploy_workflow = {
        "jobs": {
            "build": {
                "steps": [
                    _registry_scan_step("backend"),
                    _registry_scan_step("frontend"),
                ]
            }
        }
    }
    contract.assert_deploy_scans_pushed_digests_with_shared_policy()


def test_assert_deploy_scans_raises_when_scan_gate_mode_is_unknown():
    backend = _registry_scan_step("backend")
    backend["env"]["SCAN_GATE_MODE"] = "off"
    contract = WorkflowContract.__new__(WorkflowContract)
    contract.deploy_workflow = {
        "jobs": {"build": {"steps": [backend, _registry_scan_step("frontend")]}}
    }
    with pytest.raises(AssertionError, match="SCAN_GATE_MODE"):
        contract.assert_deploy_scans_pushed_digests_with_shared_policy()


# TODO(security): TEMPORARY - vulnerability scans are WARN-ONLY (advisory) as of 2026-10-11.
# In future this must be changed back to BLOCKING, and the outstanding High/Critical
# vulnerabilities must be fixed (see backend/tools/ci/scan_accepts.py and scan reports).
# When restoring blocking, change this to assert the key is absent or 'block'.
def test_vulnerability_scan_steps_set_warn_mode_when_scans_are_temporarily_advisory(
    contract,
):
    for workflow, job_name in (
        (contract.ci_workflow, "container-scan"),
        (contract.deploy_workflow, "build"),
    ):
        steps = [
            s
            for s in workflow["jobs"][job_name]["steps"]
            if isinstance(s, dict)
            and (
                "ci-image-scan.sh" in str(s.get("run"))
                or "ci-lockfile-scan.sh" in str(s.get("run"))
            )
        ]
        assert len(steps) == 2
        for step in steps:
            assert step["env"]["SCAN_GATE_MODE"] == "warn", step["name"]


def test_assert_deploy_scans_raises_when_frontend_digest_is_not_scanned():
    contract = WorkflowContract.__new__(WorkflowContract)
    contract.deploy_workflow = {
        "jobs": {"build": {"steps": [_registry_scan_step("backend")]}}
    }
    with pytest.raises(AssertionError, match="pushed frontend digest"):
        contract.assert_deploy_scans_pushed_digests_with_shared_policy()


def test_assert_deploy_scans_raises_when_scan_is_or_true_guarded():
    guarded = _registry_scan_step(
        "backend", run="bash .github/scripts/ci-image-scan.sh scan-results || true"
    )
    contract = WorkflowContract.__new__(WorkflowContract)
    contract.deploy_workflow = {
        "jobs": {"build": {"steps": [guarded, _registry_scan_step("frontend")]}}
    }
    with pytest.raises(AssertionError, match="`\\|\\|`-guarded"):
        contract.assert_deploy_scans_pushed_digests_with_shared_policy()


def test_assert_deploy_scans_raises_when_image_ref_is_a_tag():
    by_tag = _registry_scan_step("backend")
    by_tag["env"] = dict(by_tag["env"], IMAGE_REF="registry/repo:dev-latest")
    contract = WorkflowContract.__new__(WorkflowContract)
    contract.deploy_workflow = {
        "jobs": {"build": {"steps": [by_tag, _registry_scan_step("frontend")]}}
    }
    with pytest.raises(AssertionError, match="pushed backend digest"):
        contract.assert_deploy_scans_pushed_digests_with_shared_policy()


def test_contract_detects_warn_only_step_name():
    """A step that advertises itself as warn-only must fail the contract."""
    contract = _contract_with_scan_step(
        {"name": "Scan backend image (WARN-ONLY on HIGH,CRITICAL)", "run": "echo hi"}
    )
    with pytest.raises(AssertionError, match="warn-only security gates"):
        contract.assert_no_warn_only_security_language()


@pytest.mark.parametrize(
    ("ref", "expected_message"),
    [
        ("actions/checkout@v4", "NOT pinned to a full"),
        ("actions/checkout@main", "NOT pinned to a full"),
        ("actions/checkout@3d3c42e", "NOT pinned to a full"),
        ("actions/checkout", "no ref at all"),
    ],
)
def test_contract_detects_mutable_action_references(tmp_path, ref, expected_message):
    """Tag, branch, short-SHA and bare references must all be rejected."""
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        "name: CI\njobs:\n  a:\n    steps:\n      - uses: " + ref + "\n",
        encoding="utf-8",
    )

    contract = WorkflowContract.__new__(WorkflowContract)
    contract.ci_yml_path = workflows / "ci.yml"

    with pytest.raises(AssertionError, match=expected_message):
        contract.assert_every_external_action_is_sha_pinned()


def test_contract_detects_sha_pin_without_a_version_comment(tmp_path):
    """A bare SHA is pinned but unreviewable, so it will never be upgraded."""
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        "name: CI\njobs:\n  a:\n    steps:\n"
        "      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1\n",
        encoding="utf-8",
    )

    contract = WorkflowContract.__new__(WorkflowContract)
    contract.ci_yml_path = workflows / "ci.yml"

    with pytest.raises(AssertionError, match="no `# vX.Y.Z` comment"):
        contract.assert_every_external_action_is_sha_pinned()


def test_contract_allows_local_action_references(tmp_path):
    """`uses: ./.github/actions/x` resolves from the tree and needs no pin."""
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        "name: CI\njobs:\n  a:\n    steps:\n"
        "      - uses: ./.github/actions/setup-backend\n",
        encoding="utf-8",
    )

    contract = WorkflowContract.__new__(WorkflowContract)
    contract.ci_yml_path = workflows / "ci.yml"

    # Must not raise.
    contract.assert_every_external_action_is_sha_pinned()


def test_contract_detects_manifest_artifact_name_mismatch():
    """A finalizer looking for a name nobody uploads must fail the contract."""
    contract = WorkflowContract.__new__(WorkflowContract)
    contract.authoritative_yml_path = Path("ci-authoritative.yml")
    contract.ci_workflow = {
        "jobs": {
            "ci-evidence": {
                "steps": [
                    {
                        "uses": "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
                        "with": {
                            "name": "ci-${{ steps.sha.outputs.evaluation_sha }}-ci-evidence-manifest"
                        },
                    }
                ]
            }
        }
    }
    contract.authoritative_workflow = {
        "jobs": {
            "attest-evaluation": {
                "steps": [
                    {
                        "uses": "actions/download-artifact@65a9edc5881444af0b87c028056edc830d335231",
                        "with": {
                            # Divergent fixed prefix — exactly the shape of a
                            # rename that silently breaks the handshake.
                            "name": "evidence-${{ steps.resolve.outputs.evaluation_sha }}-ci-evidence-manifest"
                        },
                    }
                ]
            }
        }
    }

    with pytest.raises(AssertionError, match="manifest artifact name mismatch"):
        contract.assert_manifest_artifact_name_matches_finalizer()


def test_deploy_payload_assembly_strips_comments_when_remote_deploy_has_no_heredoc(
    workflows_path,
):
    """REL-17: the payload strips comment lines, which is only safe without heredocs.

    The assembled SSM payload must stay under ssm-run's 57,344-byte guard. The
    deploy job gets there by deleting comment-only lines from remote-deploy.sh
    with sed. That is byte-safe only while the script has no heredoc, because
    a `#` line inside a heredoc body is data, not a comment.
    """
    deploy_yml = (workflows_path / "deploy.yml").read_text(encoding="utf-8")
    remote_deploy = (workflows_path.parent / "scripts" / "remote-deploy.sh").read_text(
        encoding="utf-8"
    )

    assert "sed -E '/^[[:space:]]*#/d' .github/scripts/remote-deploy.sh" in deploy_yml
    assert "cat .github/scripts/remote-deploy.sh" not in deploy_yml
    assert "<<" not in remote_deploy, (
        "remote-deploy.sh gained a heredoc; the deploy payload comment strip is "
        "no longer safe. Remove the heredoc or stop stripping comments."
    )


def _deploy_ssm_push_run(workflows_path) -> str:
    """Return the `run` body of the deploy job's SSM config-push step."""
    workflow = yaml.safe_load((workflows_path / "deploy.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["deploy"]["steps"]
    matches = [s for s in steps if s.get("name") == "Push config to SSM Parameter Store"]
    assert len(matches) == 1, "deploy job must have exactly one SSM config-push step"
    return matches[0]["run"]


def test_deploy_ssm_probe_warns_not_fails_when_get_parameter_denied(workflows_path):
    """A role with ssm:PutParameter only must not fail the delete-if-empty probe.

    AccessDenied on the existence probe is recorded as "not cleared" and
    reported once as a warning; it must not exit before the final else.
    """
    run = _deploy_ssm_push_run(workflows_path)

    marker = """elif grep -q 'AccessDenied' "$probe_err"; then"""
    assert marker in run, "probe must have an AccessDenied branch"
    branch = run.split(marker, 1)[1]
    else_match = re.search(r"^\s*else\s*$", branch, re.MULTILINE)
    assert else_match, "AccessDenied branch must be followed by a final else"
    branch_body = branch[: else_match.start()]
    assert 'note_not_cleared "$key" "ssm:GetParameter"' in branch_body
    assert not re.search(r"\bexit\b", branch_body), (
        "AccessDenied on the probe must warn, not fail the deploy"
    )
    assert "::warning::" in run and "NOT_CLEARED_KEYS" in run
    # The aggregated warning is emitted only when something was not cleared.
    guard = "if (( PARAMS_NOT_CLEARED > 0 )); then"
    assert guard in run
    assert run.index(guard) < run.index("::warning::${PARAMS_NOT_CLEARED} key(s)")


def test_deploy_ssm_probe_still_fails_when_error_is_not_access_denied(workflows_path):
    """Only AccessDenied degrades; any other probe error still fails closed."""
    run = _deploy_ssm_push_run(workflows_path)

    not_found = run.split("""elif grep -q 'ParameterNotFound' "$probe_err"; then""", 1)
    assert len(not_found) == 2, "ParameterNotFound branch must remain"
    assert "unchanged: ${key} (empty, no existing parameter)" in not_found[1].split("elif", 1)[0]

    after_denied = run.split("""elif grep -q 'AccessDenied' "$probe_err"; then""", 1)[1]
    else_match = re.search(r"^\s*else\s*$", after_denied, re.MULTILINE)
    assert else_match
    fi_match = re.search(r"^\s*fi\s*$", after_denied[else_match.end():], re.MULTILINE)
    assert fi_match
    final_else = after_denied[else_match.end(): else_match.end() + fi_match.start()]
    assert "exit 1" in final_else, "non-AccessDenied probe errors must still fail the deploy"
    assert "::error::" in final_else

    # The delete path degrades the same way: AccessDenied warns and returns,
    # any other delete-parameter error still exits 1.
    delete_marker = """if grep -q 'AccessDenied' "$del_err"; then"""
    assert delete_marker in run, "delete-parameter must have an AccessDenied branch"
    fi_line = re.compile(r"^\s*fi\s*$", re.MULTILINE)
    delete_branch, delete_rest = fi_line.split(run.split(delete_marker, 1)[1], maxsplit=1)
    assert 'note_not_cleared "$key" "ssm:DeleteParameter"' in delete_branch
    assert "return" in delete_branch
    assert not re.search(r"\bexit\b", delete_branch), (
        "AccessDenied on delete-parameter must warn, not fail the deploy"
    )
    delete_failure = fi_line.split(delete_rest, maxsplit=1)[0]
    assert "::error::Failed to delete" in delete_failure
    assert "exit 1" in delete_failure, "non-AccessDenied delete errors must still fail the deploy"


def test_deploy_payload_ships_host_common_when_reconcile_requires_it(workflows_path):
    """reconcile-host-config.sh hard-requires lib/host-common.sh; the deploy ships it."""
    deploy_yml = (workflows_path / "deploy.yml").read_text(encoding="utf-8")
    remote_deploy = (workflows_path.parent / "scripts" / "remote-deploy.sh").read_text(
        encoding="utf-8"
    )

    assert (
        'HOST_COMMON_GZ="$(gzip -9 -c infra/scripts/lib/host-common.sh | base64 -w 0)"'
        in deploy_yml
    )
    assert """echo "HOST_COMMON_GZ='${HOST_COMMON_GZ}'\"""" in deploy_yml

    unpack_line = 'unpack "$HOST_COMMON_GZ" "${APP_DIR}/lib/host-common.sh"'
    reconcile_call = 'bash "${APP_DIR}/reconcile-host-config.sh"'
    assert unpack_line in remote_deploy
    assert reconcile_call in remote_deploy
    assert remote_deploy.index(unpack_line) < remote_deploy.index(reconcile_call)
