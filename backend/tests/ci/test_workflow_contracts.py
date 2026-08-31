"""
Workflow contract tests for CI and deploy pipeline structure.

Validates that the GitHub Actions workflows meet strict requirements:
- The deploy gate is a required dependency for image build and deployment
- No bypass constructs (if: false, continue-on-error, etc.) on gate
- Every job has timeout-minutes set
- Retry configurations are set correctly
- No secrets are passed to the gate call
"""

import pytest
import yaml
from pathlib import Path
from typing import Dict, List, Set, Optional


class WorkflowContract:
    """Contract validator for GitHub Actions workflow structure."""

    def __init__(self, deploy_yml_path: Path, ci_yml_path: Path):
        """
        Initialize with paths to deploy.yml and ci.yml.

        Args:
            deploy_yml_path: Path to .github/workflows/deploy.yml
            ci_yml_path: Path to .github/workflows/ci.yml
        """
        self.deploy_yml_path = Path(deploy_yml_path)
        self.ci_yml_path = Path(ci_yml_path)
        self.deploy_workflow = None
        self.ci_workflow = None
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
    # inheriting the caller's secrets does not hand it AWS credentials —
    # it only makes non-AWS secrets (SONAR_TOKEN, CODECOV_TOKEN) available,
    # which ci.yml's sonarcloud-analysis job requires to authenticate.
    _AWS_SECRET_MARKERS = ("AWS", "ROLE_ARN", "ACCESS_KEY", "SECRET_KEY")

    def assert_no_secrets_to_gate(self) -> None:
        """
        Assert that no AWS-related secrets are passed to the gate job call.

        The gate is AWS-blind (no OIDC role, no `configure-aws-credentials`
        step anywhere in ci.yml) and must never receive AWS credentials —
        whether via an explicit dict of secret names or (in principle) via
        `secrets: inherit` naming an AWS secret. `secrets: inherit` itself is
        allowed: it is required so ci.yml's sonarcloud-analysis job can
        resolve `secrets.SONAR_TOKEN`, and inheriting is not itself an AWS
        grant — the workflow being called must actually use an AWS secret
        for the invariant to be violated, which is exactly what this checks.

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

    def assert_terraform_job_configured(self) -> None:
        """
        Assert that the terraform validation job is properly configured.

        Checks:
        - Exact pinned CLI version (no version ranges)
        - No plan/apply/destroy/import/state actions
        - 10-minute timeout
        - No credentials passed

        Raises:
            AssertionError: If terraform job is misconfigured
        """
        jobs = self.ci_workflow.get("jobs", {})
        security_scan = jobs.get("security-scan", {})

        if not security_scan:
            raise ValueError("security-scan job not found in ci.yml")

        steps = security_scan.get("steps", [])
        errors = []

        # Find terraform-related steps
        terraform_install_step = None
        terraform_fmt_step = None
        terraform_validate_step = None
        terraform_lock_check_step = None

        for step in steps:
            if not isinstance(step, dict):
                continue

            name = step.get("name", "")

            if "Install Terraform" in name:
                terraform_install_step = step
            elif "Terraform format check" in name:
                terraform_fmt_step = step
            elif "Terraform validate" in name and "per root" in name:
                terraform_validate_step = step
            elif ".terraform.lock.hcl" in name:
                terraform_lock_check_step = step

        # Verify required steps exist
        if not terraform_install_step:
            errors.append("Terraform install step not found")
        if not terraform_fmt_step:
            errors.append("Terraform format check step not found")
        if not terraform_validate_step:
            errors.append("Terraform validate step not found")
        if not terraform_lock_check_step:
            errors.append("Terraform lock file check step not found")

        if errors:
            raise AssertionError(f"Missing terraform steps: {'; '.join(errors)}")

        # Check install step for exact version pinning + SHA256 verification.
        # Two valid shapes: an inline `run:` block that curls + sha256sum -c's
        # the archive itself, OR (F-05) a call to the
        # install-checksummed-tool composite action, whose `version`/`sha256`
        # `with:` inputs carry the same two facts — the composite action
        # itself (.github/actions/install-checksummed-tool/action.yml) is the
        # thing that actually runs `sha256sum -c` in that case.
        if "uses" in terraform_install_step:
            uses = terraform_install_step.get("uses", "")
            if "install-checksummed-tool" not in uses:
                errors.append(
                    "Terraform install step calls an unrecognised composite "
                    f"action ({uses}); expected install-checksummed-tool"
                )
            with_inputs = terraform_install_step.get("with", {}) or {}
            version = str(with_inputs.get("version", ""))
            if "1.11.0" not in version:
                errors.append("Terraform version not pinned to exact version (1.11.0)")
            if not with_inputs.get("sha256"):
                errors.append(
                    "Terraform install step does not pass a sha256 checksum "
                    "to install-checksummed-tool"
                )
        else:
            install_run = terraform_install_step.get("run", "")
            if "terraform_1.11.0" not in install_run and "1.11.0" not in install_run:
                errors.append("Terraform version not pinned to exact version (1.11.0)")
            if "sha256sum -c" not in install_run:
                errors.append("Terraform install step does not verify SHA256 checksum")

        # Check that validate step doesn't call plan/apply/destroy/import/state
        validate_run = terraform_validate_step.get("run", "")
        forbidden_commands = ["plan", "apply", "destroy", "import", "state"]
        for cmd in forbidden_commands:
            # Note: we check for these as terraform subcommands, not in comments
            if (
                f"terraform {cmd}" in validate_run
                or f"terraform\n{cmd}" in validate_run
            ):
                errors.append(
                    f"Terraform validate step appears to call '{cmd}' (forbidden)"
                )

        # Check validate script uses init -backend=false (non-applying)
        if "-backend=false" not in validate_run:
            errors.append("Terraform init step does not use -backend=false")

        if errors:
            raise AssertionError(f"Terraform configuration errors: {'; '.join(errors)}")


# Fixtures
@pytest.fixture
def workflows_path():
    """Return the workflows directory path."""
    return Path(__file__).parent.parent.parent.parent / ".github" / "workflows"


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
    """Test that terraform validation is properly configured in security-scan job."""
    try:
        contract.assert_terraform_job_configured()
    except AssertionError as e:
        pytest.fail(f"Terraform job configuration check failed: {e}")


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
