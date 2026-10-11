"""
Contract tests for the ``aws-deploy-auth`` composite and its callers (F-25).

``.github/actions/aws-deploy-auth/action.yml`` is the one place that resolves the
AWS region (``vars.AWS_REGION``, else ``eu-central-1``), validates the target EC2
instance id, and only THEN assumes the per-environment role over OIDC. Before it
existed, deploy.yml, provision.yml and cognito-reconcile.yml each carried their
own ``AWS_REGION_DEFAULT`` env, a ``vars.AWS_REGION || env.AWS_REGION_DEFAULT``
expression at every region site, and an instance-id check that two of the five
AWS jobs never had.

These tests pin that consolidation so it cannot quietly regress:

* the composite's inputs, outputs, pin and step order;
* every job holding ``id-token: write`` is exactly a composite user, and no job
  anywhere calls ``configure-aws-credentials`` directly;
* the old fallback expression is gone from the three AWS workflows;
* every region / instance-id site in a composite-using job reads the
  composite's validated outputs, and every sparse checkout lists the composite.

All checks parse the committed YAML with ``yaml.safe_load`` and assert on
structure; the only raw-text checks are for the ``# vX.Y.Z`` pin comment (YAML
drops comments) and for forbidden tokens.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[5]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
COMPOSITE_PATH = REPO_ROOT / ".github" / "actions" / "aws-deploy-auth" / "action.yml"

#: The local reference every caller must use.
COMPOSITE_USES = "./.github/actions/aws-deploy-auth"

#: Directory a sparse checkout must list for ``uses: ./...`` to resolve.
COMPOSITE_SPARSE_ENTRY = ".github/actions/aws-deploy-auth/"

#: The one configure-aws-credentials pin (FIX-NODE20-01: v6.2.3 runs on node24).
CONFIGURE_AWS_CREDENTIALS = "aws-actions/configure-aws-credentials"
CONFIGURE_AWS_CREDENTIALS_SHA = "e6de054238d6b7531b4efff3b6587d9aade6a06c"
CONFIGURE_AWS_CREDENTIALS_VERSION = "v6.2.3"

#: The instance-id shape check moved here from provision.yml / cognito-reconcile.yml.
INSTANCE_ID_PATTERN = "^i-[0-9a-f]{8,17}$"

#: Workflow -> the jobs that assume an AWS role. Explicit, so a new AWS job is
#: a deliberate edit here rather than something the scan silently absorbs.
AWS_JOBS: dict[str, frozenset[str]] = {
    "deploy.yml": frozenset({"build", "deploy"}),
    "provision.yml": frozenset({"provision"}),
    "cognito-reconcile.yml": frozenset({"reconcile", "retry-cognito-deletions"}),
}

#: The only composite caller that commands no EC2 instance.
CALLERS_WITHOUT_INSTANCE = frozenset({("deploy.yml", "build")})

REGION_OUTPUT = "${{ steps.aws.outputs.region }}"
INSTANCE_ID_OUTPUT = "${{ steps.aws.outputs.instance-id }}"
INSTANCE_ID_VARIABLE = "${{ vars.EC2_INSTANCE_ID }}"


def _load_yaml(path: Path) -> dict[str, Any]:
    """Parse a YAML file into a mapping (empty mapping for an empty file)."""
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _composite() -> dict[str, Any]:
    """The parsed aws-deploy-auth composite."""
    return _load_yaml(COMPOSITE_PATH)


def _composite_steps() -> list[dict[str, Any]]:
    """The composite's step list."""
    return list(_composite()["runs"]["steps"])


def _jobs(workflow_name: str) -> dict[str, dict[str, Any]]:
    """The job mapping of a workflow under .github/workflows."""
    workflow = _load_yaml(WORKFLOWS_DIR / workflow_name)
    return {
        name: job
        for name, job in (workflow.get("jobs") or {}).items()
        if isinstance(job, dict)
    }


def _steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    """A job's steps (empty for a reusable-workflow call)."""
    return [step for step in (job.get("steps") or []) if isinstance(step, dict)]


def _composite_step(job: dict[str, Any]) -> dict[str, Any] | None:
    """The job's aws-deploy-auth step, or None when it does not use one."""
    for step in _steps(job):
        if step.get("uses") == COMPOSITE_USES:
            return step
    return None


def _composite_callers() -> list[tuple[str, str, dict[str, Any]]]:
    """(workflow, job name, job) for every job in AWS_JOBS' workflows that uses the composite."""
    callers: list[tuple[str, str, dict[str, Any]]] = []
    for workflow_name in sorted(AWS_JOBS):
        for job_name, job in _jobs(workflow_name).items():
            if _composite_step(job) is not None:
                callers.append((workflow_name, job_name, job))
    return callers


def _caller_ids() -> list[str]:
    """Readable pytest ids for _composite_callers()."""
    return [f"{workflow}/{job}" for workflow, job, _ in _composite_callers()]


def _has_id_token_write(job: dict[str, Any]) -> bool:
    """True when the job grants itself ``id-token: write``."""
    permissions = job.get("permissions")
    return isinstance(permissions, dict) and permissions.get("id-token") == "write"


class TestCompositeDefinition:
    """The composite's own interface and step order."""

    def test_composite_inputs_match_contract_when_declared(self) -> None:
        """Inputs and defaults are exactly the documented interface."""
        inputs = _composite()["inputs"]

        assert set(inputs) == {
            "role-to-assume",
            "region",
            "default-region",
            "instance-id",
            "require-instance-id",
        }
        assert inputs["role-to-assume"]["required"] is True
        assert "default" not in inputs["role-to-assume"]
        assert inputs["region"]["default"] == ""
        assert inputs["default-region"]["default"] == "eu-central-1"
        assert inputs["instance-id"]["default"] == ""
        assert inputs["require-instance-id"]["default"] == "false"

    def test_composite_outputs_expose_validated_values_when_declared(self) -> None:
        """region and instance-id come from the validation step, not from raw inputs."""
        outputs = _composite()["outputs"]

        assert set(outputs) == {"region", "instance-id"}
        assert outputs["region"]["value"] == "${{ steps.resolve.outputs.region }}"
        assert (
            outputs["instance-id"]["value"]
            == "${{ steps.resolve.outputs.instance-id }}"
        )

    def test_composite_credentials_step_is_sha_pinned_when_configuring_aws(
        self,
    ) -> None:
        """The OIDC step uses the full-SHA v6.2.3 pin with its version comment."""
        expected = f"{CONFIGURE_AWS_CREDENTIALS}@{CONFIGURE_AWS_CREDENTIALS_SHA}"
        uses = [step.get("uses") for step in _composite_steps() if step.get("uses")]

        assert uses == [expected]
        raw = COMPOSITE_PATH.read_text(encoding="utf-8")
        assert re.search(
            rf"uses:\s*{re.escape(expected)}\s+#\s*{re.escape(CONFIGURE_AWS_CREDENTIALS_VERSION)}\s*$",
            raw,
            re.MULTILINE,
        )

    def test_composite_validates_before_minting_credentials_when_steps_run(
        self,
    ) -> None:
        """The `resolve` step (with the instance-id regex) precedes the OIDC step."""
        steps = _composite_steps()
        resolve_index = next(
            i for i, step in enumerate(steps) if step.get("id") == "resolve"
        )
        credentials_index = next(
            i
            for i, step in enumerate(steps)
            if str(step.get("uses", "")).startswith(CONFIGURE_AWS_CREDENTIALS)
        )

        assert resolve_index < credentials_index
        assert INSTANCE_ID_PATTERN in steps[resolve_index]["run"]
        credentials = steps[credentials_index]["with"]
        assert credentials == {
            "role-to-assume": "${{ inputs.role-to-assume }}",
            "aws-region": "${{ steps.resolve.outputs.region }}",
        }

    def test_composite_passes_inputs_through_env_when_validating(self) -> None:
        """No `${{ }}` is interpolated into the validation script body."""
        resolve = next(
            step for step in _composite_steps() if step.get("id") == "resolve"
        )

        assert "${{" not in resolve["run"]
        assert resolve["env"] == {
            "REGION_INPUT": "${{ inputs.region }}",
            "DEFAULT_REGION": "${{ inputs.default-region }}",
            "INSTANCE_ID": "${{ inputs.instance-id }}",
            "REQUIRE_INSTANCE_ID": "${{ inputs.require-instance-id }}",
        }

    def test_composite_rejects_unknown_require_flag_when_validating(self) -> None:
        """require-instance-id accepts only true/false and an empty required id fails."""
        script = next(
            step for step in _composite_steps() if step.get("id") == "resolve"
        )["run"]

        assert re.search(r"true\|false\)\s*;;", script)
        assert "EC2_INSTANCE_ID is not set on this job's GitHub Environment" in script

    def test_composite_references_no_secrets_when_parsed(self) -> None:
        """The role ARN is a variable; the composite never reads `secrets.`."""
        assert "secrets." not in COMPOSITE_PATH.read_text(encoding="utf-8")


class TestCompositeCallers:
    """deploy.yml, provision.yml and cognito-reconcile.yml use the composite uniformly."""

    @pytest.mark.parametrize("workflow_name", sorted(AWS_JOBS))
    def test_id_token_jobs_equal_composite_users_when_workflow_parsed(
        self, workflow_name: str
    ) -> None:
        """Exactly the jobs that assume a role hold `id-token: write`, and all use the composite."""
        jobs = _jobs(workflow_name)
        id_token_jobs = {name for name, job in jobs.items() if _has_id_token_write(job)}
        composite_jobs = {
            name for name, job in jobs.items() if _composite_step(job) is not None
        }

        assert id_token_jobs == set(AWS_JOBS[workflow_name])
        assert composite_jobs == set(AWS_JOBS[workflow_name])

    def test_no_job_configures_aws_credentials_directly_when_composite_exists(
        self,
    ) -> None:
        """configure-aws-credentials is reachable only through the composite."""
        offenders = [
            f"{path.name}/{job_name}"
            for path in sorted(WORKFLOWS_DIR.glob("*.yml"))
            for job_name, job in _jobs(path.name).items()
            for step in _steps(job)
            if str(step.get("uses", "")).startswith(CONFIGURE_AWS_CREDENTIALS)
        ]

        assert offenders == []

    @pytest.mark.parametrize("workflow_name", sorted(AWS_JOBS))
    def test_workflow_has_no_region_fallback_when_composite_resolves_region(
        self, workflow_name: str
    ) -> None:
        """The per-workflow fallback env and its `||` expression are gone."""
        raw = (WORKFLOWS_DIR / workflow_name).read_text(encoding="utf-8")

        assert "AWS_REGION_DEFAULT" not in raw
        assert not re.search(r"vars\.AWS_REGION\s*\|\|", raw)

    @pytest.mark.parametrize(
        ("workflow_name", "job_name", "job"), _composite_callers(), ids=_caller_ids()
    )
    def test_composite_step_is_wired_when_job_assumes_role(
        self, workflow_name: str, job_name: str, job: dict[str, Any]
    ) -> None:
        """The step has id `aws`, passes vars.AWS_REGION, and an instance id iff it commands a host."""
        step = _composite_step(job)
        assert step is not None
        inputs = step.get("with") or {}

        assert step.get("id") == "aws"
        assert inputs.get("region") == "${{ vars.AWS_REGION }}"
        assert str(inputs.get("role-to-assume", "")).startswith("${{ vars.AWS_")
        if (workflow_name, job_name) in CALLERS_WITHOUT_INSTANCE:
            assert "instance-id" not in inputs
            assert "require-instance-id" not in inputs
        else:
            assert inputs.get("instance-id") == INSTANCE_ID_VARIABLE
            assert inputs.get("require-instance-id") == "true"

    @pytest.mark.parametrize(
        ("workflow_name", "job_name", "job"), _composite_callers(), ids=_caller_ids()
    )
    def test_sparse_checkout_lists_composite_when_job_uses_it(
        self, workflow_name: str, job_name: str, job: dict[str, Any]
    ) -> None:
        """A sparse checkout must include the composite dir or `uses: ./...` cannot resolve."""
        for step in _steps(job):
            if not str(step.get("uses", "")).startswith("actions/checkout@"):
                continue
            sparse = (step.get("with") or {}).get("sparse-checkout")
            if sparse is None:
                continue
            entries = [line.strip() for line in str(sparse).splitlines()]
            assert (
                COMPOSITE_SPARSE_ENTRY in entries
            ), f"{workflow_name}/{job_name} sparse checkout omits {COMPOSITE_SPARSE_ENTRY}"

    @pytest.mark.parametrize(
        ("workflow_name", "job_name", "job"), _composite_callers(), ids=_caller_ids()
    )
    def test_region_and_instance_sites_read_composite_outputs_when_job_uses_composite(
        self, workflow_name: str, job_name: str, job: dict[str, Any]
    ) -> None:
        """Every AWS_REGION / aws-region / instance-id / INSTANCE_ID site reads `steps.aws.outputs`."""
        offenders: list[str] = []
        for step in _steps(job):
            if step.get("uses") == COMPOSITE_USES:
                continue
            label = step.get("name") or step.get("id") or "<unnamed>"
            env = step.get("env") or {}
            inputs = step.get("with") or {}
            for key, expected in (
                ("AWS_REGION", REGION_OUTPUT),
                ("INSTANCE_ID", INSTANCE_ID_OUTPUT),
            ):
                if key in env and env[key] != expected:
                    offenders.append(f"{label}: env.{key}={env[key]!r}")
            for key, expected in (
                ("aws-region", REGION_OUTPUT),
                ("instance-id", INSTANCE_ID_OUTPUT),
            ):
                if key in inputs and inputs[key] != expected:
                    offenders.append(f"{label}: with.{key}={inputs[key]!r}")
            serialized = yaml.safe_dump(step)
            if "vars.EC2_INSTANCE_ID" in serialized:
                offenders.append(f"{label}: reads vars.EC2_INSTANCE_ID directly")

        assert offenders == [], f"{workflow_name}/{job_name}: {offenders}"

    @pytest.mark.parametrize(
        ("workflow_name", "job_name", "job"), _composite_callers(), ids=_caller_ids()
    )
    def test_ssm_run_targets_validated_instance_when_invoked(
        self, workflow_name: str, job_name: str, job: dict[str, Any]
    ) -> None:
        """ssm-run's instance-id and region come from the composite, after it ran."""
        steps = _steps(job)
        composite_index = next(
            i for i, step in enumerate(steps) if step.get("uses") == COMPOSITE_USES
        )
        ssm_runs = [
            (i, step)
            for i, step in enumerate(steps)
            if step.get("uses") == "./.github/actions/ssm-run"
        ]

        if (workflow_name, job_name) in CALLERS_WITHOUT_INSTANCE:
            assert ssm_runs == []
            return
        assert ssm_runs, f"{workflow_name}/{job_name} commands no host via ssm-run"
        for index, step in ssm_runs:
            assert index > composite_index
            assert step["with"]["instance-id"] == INSTANCE_ID_OUTPUT
            assert step["with"]["aws-region"] == REGION_OUTPUT
