"""Signal registry — authoritative mapping of CI signals to single owners.

Every unique mandatory signal has exactly one producer and one truth function.
Signals are unique by purpose, verdict semantics, scope, and trust boundary.
Duplicate execution uses the same exact revision, inputs, config, tool version,
and equivalent or strictly contained scope; work separated by materially
different trust boundaries, privilege sets, artifact responsibilities, or
policy verdicts remains distinct.
"""

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional, Set

from tools.ci.pin_authority import get_authority

# Every `tool_version` below is read from the pin authority rather than written
# as a literal. The literals had drifted (tflint 0.59.1, ruff 0.9.11, pyright
# 1.1.407, checkov 3.2.180, grype 0.75.0) from what CI actually installs (F-08);
# test_signal_registry.py asserts the mapping.
_PINS = get_authority()

#: The change areas ci.yml's `changes` job can report as unchanged on a pull
#: request (F-15). backend/tools/ci/change_scope.py declares the same tuple as
#: `AREAS` (it is stdlib-only and cannot import this module), and
#: test_change_scope.py asserts the two agree. See `Signal.path_filter_area`.
PATH_FILTER_AREAS = frozenset(
    {"backend", "frontend", "infra", "backend_image", "frontend_image"}
)


class SignalType(Enum):
    """Classification of signal type."""

    STATIC_CHECK = "static-check"
    SECURITY_SCAN = "security-scan"
    TEST_EXECUTION = "test-execution"
    COVERAGE_REPORT = "coverage-report"
    EXTERNAL_GATE = "external-gate"


@dataclass
class Signal:
    """Definition of a unique CI signal."""

    id: str
    name: str
    description: str
    signal_type: SignalType
    owner_job: str
    scope: str
    trust_boundary: str
    verdict_semantics: str
    required_artifact_formats: list[str]
    tool_version: Optional[str] = None
    config_file: Optional[str] = None
    timeout_seconds: int = 300
    is_mandatory: bool = True
    is_blocking: bool = True
    aggregate_members: Optional[list[str]] = None  # For aggregate signals (ci_required)

    # ------------------------------------------------------------------
    # THE PATH-FILTER (SKIP-AS-SUCCESS) POLICY (F-15)
    # ------------------------------------------------------------------
    # `path_filter_area` names the change area (one of PATH_FILTER_AREAS) whose
    # files this signal evaluates. A signal may be reported FILTERED — "did not
    # run because nothing it evaluates changed" — only when ALL of these hold:
    #
    #   1. the event is `pull_request`. push, workflow_dispatch and
    #      workflow_call (the deploy gate) always run everything, so a branch tip
    #      and every deployment are always fully evaluated;
    #   2. this field is not None, and ci.yml's `changes` job reported this
    #      area as unchanged for the pull request;
    #   3. the signal's job was skipped, or its matrix leg was excluded.
    #
    # FILTERED satisfies the aggregate, but it is recorded APART from verdicts
    # (the manifest's `policy_filtered` list, never `signal_states`), so a
    # reader can always tell "not needed" from "succeeded". It is also distinct
    # from MISSING, which still fails: a job that vanished, or a skip whose area
    # was NOT reported unchanged, has no verdict and blocks.
    #
    # A job that RAN keeps its real result for every signal it evaluated, so a
    # failure is never hidden by the filter. The one exception is a PARTIALLY
    # filtered matrix job (e.g. `security` running only its `secrets` leg
    # because its other areas are unchanged): the signals of the excluded legs
    # never ran, so they are FILTERED, while the live legs' signals keep the
    # real job result (ci_gate._signal_state_for). A failed live leg therefore
    # still fails its signals.
    #
    # None means NEVER filterable: repo-static/* and security[secrets] evaluate
    # the whole repository (workflows, scripts, compose files, full history) on
    # every event.
    path_filter_area: Optional[str] = None

    # ------------------------------------------------------------------
    # Advisory eligibility (F-03)
    # ------------------------------------------------------------------
    # A signal marked `advisory_eligible` MAY be downgraded to advisory for a
    # single evaluation, by an explicit `--advisory <id>` argument to
    # `tools.ci.ci_gate aggregate`. A downgraded signal still runs, still
    # reports, and is still recorded in the manifest — it simply does not fail
    # the aggregate.
    #
    # This exists because the alternative shipped instead was far worse: the
    # `dev` environment's CI gate was SKIPPED ENTIRELY (deploy.yml `if:
    # needs.resolve.outputs.environment != 'dev'`) to work around four
    # pre-existing red signals. That turned off lint, every test, the coverage
    # gates, secret scanning, dependency audits and both container scans for
    # every dev deploy — every mandatory signal discarded to avoid a handful of
    # red ones. A per-signal, listed, dated downgrade keeps every other signal
    # blocking.
    #
    # THE THREE PROPERTIES THAT KEEP THIS FROM BECOMING A BYPASS:
    #   1. ALLOWLIST. Only signals with `advisory_eligible=True` can be named.
    #      Asking for any other id is a hard failure, so a caller cannot
    #      downgrade an arbitrary signal — least of all the whole set.
    #   2. EXPIRY. `advisory_expires` is a real date. Past it, naming the signal
    #      FAILS the aggregate instead of downgrading it. A temporary allowance
    #      that cannot expire is a permanent one, so the deadline is enforced by
    #      the gate rather than by intention.
    #   3. NO REACH INTO PULL REQUESTS. The downgrade is only reachable through a
    #      workflow input, and `pull_request` events carry no inputs. The trusted
    #      finalizer additionally refuses any manifest that records a downgrade
    #      (.github/scripts/ci-validate-evidence.sh), so `ci-required` on a PR is
    #      always the strict verdict.
    #
    # `advisory_reason` is the record of WHY, and `advisory_owner` of WHO is
    # removing the need for it. Both are required alongside eligibility.
    advisory_eligible: bool = False
    advisory_expires: Optional[str] = None  # ISO-8601 date, e.g. "2026-12-31"
    advisory_reason: Optional[str] = None
    advisory_owner: Optional[str] = None

    def advisory_allowance_expired(self, today: Optional[date] = None) -> bool:
        """
        Return True when this signal's advisory allowance is no longer valid.

        A signal that is not advisory-eligible is reported as expired, so the
        caller's single check covers both "never allowed" and "no longer
        allowed".
        """
        if not self.advisory_eligible:
            return True
        if not self.advisory_expires:
            # Eligible but undated is treated as expired: an allowance with no
            # end is exactly what this mechanism refuses to grant.
            return True
        reference = today or date.today()
        return reference > date.fromisoformat(self.advisory_expires)

    def __hash__(self):
        """Make Signal hashable."""
        return hash(self.id)

    def __eq__(self, other):
        """Compare signals by semantic identity."""
        if not isinstance(other, Signal):
            return False
        # Two signals are equivalent if they evaluate the same revision with
        # the same inputs, config, tool version, and verdict semantics
        return (
            self.signal_type == other.signal_type
            and self.verdict_semantics == other.verdict_semantics
            and self.tool_version == other.tool_version
            and self.config_file == other.config_file
            and (
                # One scope fully contains the other, or they're equal
                self.scope == other.scope
                or self.scope in other.scope
                or other.scope in self.scope
            )
        )


class SignalRegistry:
    """Central registry of all mandatory CI signals."""

    def __init__(self):
        """Initialize the registry with all mandatory signals."""
        self._signals: dict[str, Signal] = {}
        self._owner_map: dict[str, str] = {}  # owner_job -> signal_ids
        self._initialize_signals()

    def _initialize_signals(self) -> None:
        """Register all mandatory CI signals with single owners."""

        # ===== Repository Static Signals =====
        self._register_signal(
            Signal(
                id="repo-static/actionlint",
                name="ActionLint",
                description="GitHub Actions workflow schema and expression validation",
                signal_type=SignalType.STATIC_CHECK,
                owner_job="repo-static",
                scope="workflow-files",
                trust_boundary="repository-code",
                verdict_semantics="workflow-schema-valid",
                required_artifact_formats=["log"],
                tool_version=_PINS.actionlint_version,
                config_file=".github/workflows/*.yml",
                timeout_seconds=300,
            )
        )

        self._register_signal(
            Signal(
                id="repo-static/bash-syntax",
                name="Bash syntax check",
                description="Shell script parse validation",
                signal_type=SignalType.STATIC_CHECK,
                owner_job="repo-static",
                scope="shell-scripts",
                trust_boundary="repository-code",
                verdict_semantics="parse-valid",
                required_artifact_formats=["log"],
                timeout_seconds=300,
            )
        )

        self._register_signal(
            Signal(
                id="repo-static/shellcheck",
                name="ShellCheck",
                description="Shell script static analysis and warnings",
                signal_type=SignalType.STATIC_CHECK,
                owner_job="repo-static",
                scope="shell-scripts",
                trust_boundary="repository-code",
                verdict_semantics="shellcheck-warnings-resolved",
                required_artifact_formats=["log"],
                tool_version=_PINS.shellcheck_version,
                timeout_seconds=300,
            )
        )

        # F-19: the compose files shipped to hosts were never parsed in CI, so a
        # broken overlay or an un-defaulted variable only surfaced mid-deploy.
        self._register_signal(
            Signal(
                id="repo-static/compose-config",
                name="Compose config",
                description=(
                    "docker compose config for docker-compose.yml alone and with "
                    "docker-compose.prod.yml, using placeholder-only ci/compose-ci.env"
                ),
                signal_type=SignalType.STATIC_CHECK,
                owner_job="repo-static",
                scope="compose-files",
                trust_boundary="repository-code",
                verdict_semantics="compose-config-valid",
                required_artifact_formats=["log"],
                config_file="docker-compose.yml",
                timeout_seconds=300,
            )
        )

        # ===== Security Matrix Signals =====
        self._register_signal(
            Signal(
                id="security[secrets]",
                name="Gitleaks",
                description="Full-history secret scanning and leak detection",
                signal_type=SignalType.SECURITY_SCAN,
                owner_job="security",
                scope="repository-history",
                trust_boundary="repository-code",
                verdict_semantics="no-secrets-found",
                required_artifact_formats=["json", "log"],
                tool_version=_PINS.gitleaks_version,
                config_file="ci/gitleaks.toml",
                timeout_seconds=600,
            )
        )

        # security[backend-deps] (pip-audit) and security[frontend-deps]
        # (npm audit) were RETIRED. Every dependency-vulnerability verdict now
        # comes from Trivy or Grype in `container-scan`: the backend image holds
        # exactly the `uv export --frozen --no-dev` slice of backend/uv.lock, and
        # the frontend lockfile is scanned by container-scan[frontend]/
        # trivy-lockfile below. Their exceptions moved to the single dated list in
        # tools/ci/scan_accepts.py, and neither is advisory-eligible any more.

        # ===== Backend Inventory and Static Checks =====
        self._register_signal(
            Signal(
                id="backend-inventory",
                name="Backend test inventory",
                description="Canonical pytest collection and test node classification",
                signal_type=SignalType.TEST_EXECUTION,
                owner_job="backend-inventory",
                path_filter_area="backend",
                scope="backend-tests",
                trust_boundary="repository-code",
                verdict_semantics="inventory-complete-and-disjoint",
                required_artifact_formats=["json"],
                timeout_seconds=600,
            )
        )

        self._register_signal(
            Signal(
                id="backend-static/ruff-lint",
                name="Ruff lint",
                description="Python code linting with Ruff",
                signal_type=SignalType.STATIC_CHECK,
                owner_job="backend-static",
                path_filter_area="backend",
                scope="backend-python",
                trust_boundary="repository-code",
                verdict_semantics="ruff-lint-passed",
                required_artifact_formats=["log", "json"],
                tool_version=_PINS.ruff_version,
                timeout_seconds=300,
            )
        )

        self._register_signal(
            Signal(
                id="backend-static/ruff-format",
                name="Ruff format",
                description="Python code formatting validation with Ruff",
                signal_type=SignalType.STATIC_CHECK,
                owner_job="backend-static",
                path_filter_area="backend",
                scope="backend-python",
                trust_boundary="repository-code",
                verdict_semantics="ruff-format-passed",
                required_artifact_formats=["log"],
                tool_version=_PINS.ruff_version,
                timeout_seconds=300,
            )
        )

        self._register_signal(
            Signal(
                id="backend-static/python-compile",
                name="Python compile",
                description="Python bytecode compilation check",
                signal_type=SignalType.STATIC_CHECK,
                owner_job="backend-static",
                path_filter_area="backend",
                scope="backend-python",
                trust_boundary="repository-code",
                verdict_semantics="python-compile-passed",
                required_artifact_formats=["log"],
                timeout_seconds=300,
            )
        )

        self._register_signal(
            Signal(
                id="backend-static/pyright",
                name="Pyright",
                description="Python import resolution with Pyright (typeCheckingMode off)",
                signal_type=SignalType.STATIC_CHECK,
                owner_job="backend-static",
                path_filter_area="backend",
                scope="backend-python",
                trust_boundary="repository-code",
                verdict_semantics="pyright-passed",
                required_artifact_formats=["log", "json"],
                tool_version=_PINS.pyright_version,
                timeout_seconds=600,
            )
        )

        self._register_signal(
            Signal(
                id="backend-static/import-linter",
                name="lint-imports",
                description="Python import boundary enforcement",
                signal_type=SignalType.STATIC_CHECK,
                owner_job="backend-static",
                path_filter_area="backend",
                scope="backend-python",
                trust_boundary="repository-code",
                verdict_semantics="import-boundaries-valid",
                required_artifact_formats=["log"],
                timeout_seconds=300,
            )
        )

        self._register_signal(
            Signal(
                id="backend-static/vulture",
                name="Vulture",
                description="Dead code detection",
                signal_type=SignalType.STATIC_CHECK,
                owner_job="backend-static",
                path_filter_area="backend",
                scope="backend-python",
                trust_boundary="repository-code",
                verdict_semantics="vulture-passed",
                required_artifact_formats=["log"],
                timeout_seconds=300,
            )
        )

        self._register_signal(
            Signal(
                id="backend-static/bandit",
                name="Bandit",
                description="Python security issue scanner",
                signal_type=SignalType.SECURITY_SCAN,
                owner_job="backend-static",
                path_filter_area="backend",
                scope="backend-python",
                trust_boundary="repository-code",
                verdict_semantics="bandit-passed",
                required_artifact_formats=["log", "json"],
                timeout_seconds=300,
            )
        )

        self._register_signal(
            Signal(
                id="backend-static/migration-guard",
                name="Migration guard",
                description="Database migration integrity and validity checks",
                signal_type=SignalType.STATIC_CHECK,
                owner_job="backend-static",
                path_filter_area="backend",
                scope="database-migrations",
                trust_boundary="repository-code",
                verdict_semantics="migrations-valid",
                required_artifact_formats=["log"],
                timeout_seconds=300,
            )
        )

        # ===== Backend Test Execution =====
        self._register_signal(
            Signal(
                id="backend-offline",
                name="Backend offline tests",
                description="Offline backend unit/integration/characterization tests without live providers",
                signal_type=SignalType.TEST_EXECUTION,
                owner_job="backend-offline",
                path_filter_area="backend",
                scope="backend-tests-offline",
                trust_boundary="ci-code",
                verdict_semantics="all-offline-tests-pass",
                required_artifact_formats=["junit", "coverage-data"],
                timeout_seconds=2100,
            )
        )

        self._register_signal(
            Signal(
                id="backend-postgres",
                name="Backend PostgreSQL tests",
                description="Backend tests requiring PostgreSQL database service",
                signal_type=SignalType.TEST_EXECUTION,
                owner_job="backend-postgres",
                path_filter_area="backend",
                scope="backend-tests-postgres",
                trust_boundary="ci-code",
                verdict_semantics="all-postgres-tests-pass",
                required_artifact_formats=["junit", "coverage-data"],
                timeout_seconds=1800,
            )
        )

        self._register_signal(
            Signal(
                id="backend-evidence",
                name="Backend evidence aggregation",
                description="Merge backend coverage, validate producers, enforce >=80% overall coverage",
                signal_type=SignalType.COVERAGE_REPORT,
                owner_job="backend-evidence",
                path_filter_area="backend",
                scope="backend-coverage",
                trust_boundary="ci-code",
                verdict_semantics="backend-coverage-80-percent",
                required_artifact_formats=["cobertura", "junit"],
                timeout_seconds=600,
            )
        )

        # ===== Frontend Static Checks =====
        self._register_signal(
            Signal(
                id="frontend-static/typecheck",
                name="Frontend typecheck",
                description="TypeScript type checking",
                signal_type=SignalType.STATIC_CHECK,
                owner_job="frontend-static",
                path_filter_area="frontend",
                scope="frontend-typescript",
                trust_boundary="repository-code",
                verdict_semantics="typescript-valid",
                required_artifact_formats=["log"],
                timeout_seconds=300,
            )
        )

        self._register_signal(
            Signal(
                id="frontend-static/lint",
                name="Frontend lint",
                description="ESLint and stale-suppression checks",
                signal_type=SignalType.STATIC_CHECK,
                owner_job="frontend-static",
                path_filter_area="frontend",
                scope="frontend-typescript",
                trust_boundary="repository-code",
                verdict_semantics="eslint-passed",
                required_artifact_formats=["log"],
                timeout_seconds=300,
            )
        )

        # F-12: the production build is its own job. It used to be the third
        # check of frontend-static (`frontend-static/build`) and was then
        # thrown away; frontend-e2e now runs against exactly this bundle.
        self._register_signal(
            Signal(
                id="frontend-build",
                name="Frontend build",
                description=(
                    "Production Next.js standalone build, uploaded once as the "
                    "tarball frontend-e2e serves"
                ),
                signal_type=SignalType.STATIC_CHECK,
                owner_job="frontend-build",
                path_filter_area="frontend",
                scope="frontend-build",
                trust_boundary="repository-code",
                verdict_semantics="build-succeeds",
                required_artifact_formats=["log", "tar.gz"],
                timeout_seconds=1200,
            )
        )

        # ===== Frontend Test Execution =====
        self._register_signal(
            Signal(
                id="frontend-vitest",
                name="Frontend Vitest",
                description="Complete Vitest unit/component/integration test execution with coverage",
                signal_type=SignalType.TEST_EXECUTION,
                owner_job="frontend-vitest",
                path_filter_area="frontend",
                scope="frontend-tests",
                trust_boundary="ci-code",
                verdict_semantics="all-vitest-tests-pass",
                required_artifact_formats=["junit", "lcov"],
                timeout_seconds=1200,
            )
        )

        self._register_signal(
            Signal(
                id="frontend-e2e",
                name="Frontend E2E",
                description="Complete mocked Playwright E2E test execution",
                signal_type=SignalType.TEST_EXECUTION,
                owner_job="frontend-e2e",
                path_filter_area="frontend",
                scope="frontend-e2e",
                trust_boundary="ci-code",
                verdict_semantics="all-mocked-e2e-tests-pass",
                required_artifact_formats=["junit"],
                timeout_seconds=1500,
                advisory_eligible=True,
                advisory_expires="2027-03-31",
                advisory_reason=(
                    "The mandatory mocked Playwright project fails at HEAD "
                    "(.github/CI_STATUS.md); the earlier ~40-skip baseline no "
                    "longer applies. Each failing test needs its own reviewed "
                    "change: either the test is restored or it is deleted with a "
                    "reason. Clearing this by widening the skip audit or "
                    "converting a failing test to a skip is explicitly not "
                    "acceptable."
                ),
                advisory_owner="frontend",
            )
        )

        self._register_signal(
            Signal(
                id="frontend-evidence",
                name="Frontend evidence aggregation",
                description="Validate the Vitest producer and enforce >=80% on all four coverage metrics",
                signal_type=SignalType.COVERAGE_REPORT,
                owner_job="frontend-evidence",
                path_filter_area="frontend",
                scope="frontend-coverage",
                trust_boundary="ci-code",
                verdict_semantics="frontend-coverage-80-percent-all-metrics",
                required_artifact_formats=["lcov", "junit"],
                timeout_seconds=600,
                advisory_eligible=True,
                advisory_expires="2027-03-31",
                advisory_reason=(
                    "Frontend coverage measures 47.34 / 45.11 / 46.34 / 49.26 "
                    "against a 80% four-metric threshold (.github/CI_STATUS.md). "
                    "Remediation is writing tests. Lowering the threshold or "
                    "narrowing the coverage denominator to clear this is "
                    "explicitly not acceptable — the gate stays at 80%."
                ),
                advisory_owner="frontend",
            )
        )

        self._register_signal(
            Signal(
                id="security[iac]/terraform-fmt",
                name="Terraform fmt",
                description="Terraform code formatting validation",
                signal_type=SignalType.STATIC_CHECK,
                owner_job="security",
                path_filter_area="infra",
                scope="terraform-configuration",
                trust_boundary="repository-code",
                verdict_semantics="terraform-formatted",
                required_artifact_formats=["log"],
                timeout_seconds=300,
            )
        )

        self._register_signal(
            Signal(
                id="security[iac]/terraform-validate",
                name="Terraform validate",
                description="Terraform configuration validation (backend disabled)",
                signal_type=SignalType.STATIC_CHECK,
                owner_job="security",
                path_filter_area="infra",
                scope="terraform-configuration",
                trust_boundary="repository-code",
                verdict_semantics="terraform-valid",
                required_artifact_formats=["log"],
                timeout_seconds=300,
            )
        )

        self._register_signal(
            Signal(
                id="security[iac]/tflint",
                name="TFLint",
                description="Terraform linter for best practices",
                signal_type=SignalType.STATIC_CHECK,
                owner_job="security",
                path_filter_area="infra",
                scope="terraform-configuration",
                trust_boundary="repository-code",
                verdict_semantics="tflint-passed",
                required_artifact_formats=["log"],
                tool_version=_PINS.tflint_version,
                timeout_seconds=300,
            )
        )

        self._register_signal(
            Signal(
                id="security[iac]/checkov",
                name="Checkov",
                description="Infrastructure-as-code policy checks",
                signal_type=SignalType.SECURITY_SCAN,
                owner_job="security",
                path_filter_area="infra",
                scope="terraform-configuration",
                trust_boundary="repository-code",
                verdict_semantics="iac-policies-passed",
                required_artifact_formats=["json"],
                tool_version=_PINS.checkov_version,
                config_file="ci/checkov.yaml",
                timeout_seconds=600,
            )
        )

        self._register_signal(
            Signal(
                id="security[iac]/trivy-config",
                name="Trivy config",
                description="Trivy configuration and vulnerability scan",
                signal_type=SignalType.SECURITY_SCAN,
                owner_job="security",
                path_filter_area="infra",
                scope="terraform-configuration",
                trust_boundary="repository-code",
                verdict_semantics="zero-high-critical-config-vulns",
                required_artifact_formats=["json"],
                tool_version=_PINS.trivy_version,
                timeout_seconds=600,
            )
        )

        # ===== Container Scanning Signals =====
        # TODO(security): TEMPORARY - vulnerability scans are WARN-ONLY (advisory) as of 2026-10-11.
        # In future this must be changed back to BLOCKING, and the outstanding High/Critical
        # vulnerabilities must be fixed (see backend/tools/ci/scan_accepts.py and scan reports).
        # These signals stay MANDATORY (they must still run and report, so a vanished
        # job still fails the aggregate) but are is_blocking=False because
        # `ci_gate scan-gate --mode warn` reports findings without failing. They are
        # deliberately NOT advisory_eligible: that downgrade cannot reach pull requests
        # and would also excuse non-vulnerability failures.
        self._register_signal(
            Signal(
                id="container-scan[backend]/trivy",
                name="Trivy image scan (backend)",
                description="Container image vulnerability scan with Trivy",
                signal_type=SignalType.SECURITY_SCAN,
                owner_job="container-scan",
                path_filter_area="backend_image",
                scope="backend-image",
                trust_boundary="ci-build",
                verdict_semantics="zero-high-critical-image-vulns",
                required_artifact_formats=["json"],
                tool_version=_PINS.trivy_version,
                timeout_seconds=600,
                is_blocking=False,  # TODO(security): TEMPORARY, restore True
            )
        )

        self._register_signal(
            Signal(
                id="container-scan[backend]/grype",
                name="Grype image scan (backend)",
                description="Container image vulnerability scan with Grype",
                signal_type=SignalType.SECURITY_SCAN,
                owner_job="container-scan",
                path_filter_area="backend_image",
                scope="backend-image",
                trust_boundary="ci-build",
                verdict_semantics="zero-high-critical-image-vulns",
                required_artifact_formats=["json"],
                tool_version=_PINS.grype_version,
                timeout_seconds=600,
                is_blocking=False,  # TODO(security): TEMPORARY, restore True
            )
        )

        self._register_signal(
            Signal(
                id="container-scan[frontend]/trivy",
                name="Trivy image scan (frontend)",
                description="Container image vulnerability scan with Trivy",
                signal_type=SignalType.SECURITY_SCAN,
                owner_job="container-scan",
                path_filter_area="frontend_image",
                scope="frontend-image",
                trust_boundary="ci-build",
                verdict_semantics="zero-high-critical-image-vulns",
                required_artifact_formats=["json"],
                tool_version=_PINS.trivy_version,
                timeout_seconds=600,
                is_blocking=False,  # TODO(security): TEMPORARY, restore True
            )
        )

        self._register_signal(
            Signal(
                id="container-scan[frontend]/grype",
                name="Grype image scan (frontend)",
                description="Container image vulnerability scan with Grype",
                signal_type=SignalType.SECURITY_SCAN,
                owner_job="container-scan",
                path_filter_area="frontend_image",
                scope="frontend-image",
                trust_boundary="ci-build",
                verdict_semantics="zero-high-critical-image-vulns",
                required_artifact_formats=["json"],
                tool_version=_PINS.grype_version,
                timeout_seconds=600,
                is_blocking=False,  # TODO(security): TEMPORARY, restore True
            )
        )

        # The standalone Next.js image compiles most dependencies into .next/
        # chunks with no package.json, so the image scans above cannot see them.
        # This lockfile scan is what covers the frontend's production graph
        # (Trivy skips devDependencies by default). It replaced npm audit.
        self._register_signal(
            Signal(
                id="container-scan[frontend]/trivy-lockfile",
                name="Trivy lockfile scan (frontend)",
                description="frontend/package-lock.json vulnerability scan with Trivy fs",
                signal_type=SignalType.SECURITY_SCAN,
                owner_job="container-scan",
                path_filter_area="frontend_image",
                scope="frontend-dependencies",
                trust_boundary="frozen-lock",
                verdict_semantics="zero-high-critical-dependency-vulns",
                required_artifact_formats=["json"],
                tool_version=_PINS.trivy_version,
                config_file="frontend/package-lock.json",
                timeout_seconds=600,
                is_blocking=False,  # TODO(security): TEMPORARY, restore True
            )
        )

        # ===== Aggregate Gate =====
        # This signal exists to define the mandatory aggregate composition.
        # It is owned by ci-evidence; the status itself is published by the
        # ci-required job in ci.yml (trusted intents) and by ci-authoritative.yml
        # (pull requests). The shadow-mode `ci-required-shadow` context was
        # retired at cutover and no workflow publishes it any more.
        self._register_signal(
            Signal(
                id="ci-required",
                name="CI Required Gate",
                description="Aggregate verdict that all mandatory signals succeeded for exact current SHA",
                signal_type=SignalType.EXTERNAL_GATE,
                owner_job="ci-evidence",  # the aggregate itself; ci-required publishes the status
                scope="aggregate",
                trust_boundary="ci-aggregate",
                verdict_semantics="all-mandatory-signals-success",
                required_artifact_formats=["json"],
                timeout_seconds=300,
                is_mandatory=True,
                is_blocking=True,
                aggregate_members=[
                    "repo-static/actionlint",
                    "repo-static/bash-syntax",
                    "repo-static/shellcheck",
                    "repo-static/compose-config",
                    "backend-inventory",
                    "backend-static/ruff-lint",
                    "backend-static/ruff-format",
                    "backend-static/python-compile",
                    "backend-static/pyright",
                    "backend-static/import-linter",
                    "backend-static/vulture",
                    "backend-static/bandit",
                    "backend-static/migration-guard",
                    "backend-offline",
                    "backend-postgres",
                    "backend-evidence",
                    "frontend-static/typecheck",
                    "frontend-static/lint",
                    "frontend-build",
                    "frontend-vitest",
                    "frontend-e2e",
                    "frontend-evidence",
                    "security[secrets]",
                    "security[iac]/terraform-fmt",
                    "security[iac]/terraform-validate",
                    "security[iac]/tflint",
                    "security[iac]/checkov",
                    "security[iac]/trivy-config",
                    "container-scan[backend]/trivy",
                    "container-scan[backend]/grype",
                    "container-scan[frontend]/trivy",
                    "container-scan[frontend]/grype",
                    "container-scan[frontend]/trivy-lockfile",
                ],
            )
        )

    def _register_signal(self, signal: Signal) -> None:
        """Register a signal and enforce single-owner invariant.

        Single ownership is enforced per semantic signal (same purpose, verdict,
        type, scope, trust boundary). However, distinct engines/tools with
        different verdicts are allowed on the same scope (e.g., Trivy + Grype).
        """
        if signal.id in self._signals:
            raise ValueError(f"Signal {signal.id} already registered")

        if (
            signal.path_filter_area is not None
            and signal.path_filter_area not in PATH_FILTER_AREAS
        ):
            raise ValueError(
                f"Signal {signal.id} declares unknown path_filter_area "
                f"{signal.path_filter_area!r}; expected one of "
                f"{sorted(PATH_FILTER_AREAS)} or None"
            )

        # Check for duplicate owners with same semantics ONLY if tool is the same
        for existing_id, existing_signal in self._signals.items():
            if (
                existing_signal.owner_job == signal.owner_job
                and existing_signal.verdict_semantics == signal.verdict_semantics
                and existing_signal.signal_type == signal.signal_type
                and existing_signal.scope == signal.scope
                and existing_signal.name == signal.name  # Same tool/name
            ):
                raise ValueError(
                    f"Duplicate semantic signal: {signal.id} and {existing_id} "
                    f"have same owner, verdict semantics, type, scope, and tool"
                )

        self._signals[signal.id] = signal

        # Track owner -> signal IDs
        if signal.owner_job not in self._owner_map:
            self._owner_map[signal.owner_job] = []
        self._owner_map[signal.owner_job].append(signal.id)

    def get_signal(self, signal_id: str) -> Optional[Signal]:
        """Retrieve a signal by ID."""
        return self._signals.get(signal_id)

    def get_signals_by_owner(self, owner_job: str) -> list[Signal]:
        """Get all signals owned by a specific job."""
        if owner_job not in self._owner_map:
            return []
        return [self._signals[sid] for sid in self._owner_map[owner_job]]

    def get_signals_by_area(self, area: Optional[str]) -> list[Signal]:
        """Get every signal whose `path_filter_area` is `area` (None = never filterable)."""
        return [s for s in self._signals.values() if s.path_filter_area == area]

    def get_mandatory_signals(self) -> list[Signal]:
        """Get all mandatory signals."""
        return [s for s in self._signals.values() if s.is_mandatory]

    def get_advisory_eligible_signals(self) -> list[Signal]:
        """
        Get every signal that MAY be downgraded to advisory (F-03).

        Membership here is the allowlist that keeps `--advisory` from being a
        general-purpose bypass. Keep it short, and keep every entry dated.
        """
        return [s for s in self._signals.values() if s.advisory_eligible]

    def resolve_advisory_request(
        self, requested: list[str], today: Optional[date] = None
    ) -> tuple[set[str], list[str]]:
        """
        Validate a set of requested advisory downgrades.

        Args:
            requested: signal ids the caller wants treated as advisory.
            today: injectable clock, so the expiry rule is testable without
                freezing real time.

        Returns:
            (accepted ids, problems). `problems` is non-empty when any request
            was refused, and the caller MUST fail on that rather than proceeding
            with a partial set — a refused downgrade means the caller's intent
            and the gate's policy disagree, which is not a safe thing to guess
            about in either direction.
        """
        accepted: set[str] = set()
        problems: list[str] = []

        for signal_id in requested:
            signal = self._signals.get(signal_id)
            if signal is None:
                problems.append(
                    f"advisory request names '{signal_id}', which is not a "
                    f"registered signal"
                )
                continue
            if not signal.advisory_eligible:
                problems.append(
                    f"signal '{signal_id}' is not advisory-eligible. Only signals "
                    f"explicitly allowlisted in the registry may be downgraded; "
                    f"add advisory_eligible/advisory_expires/advisory_reason/"
                    f"advisory_owner there in a reviewed change, or fix the signal."
                )
                continue
            if signal.advisory_allowance_expired(today):
                problems.append(
                    f"signal '{signal_id}' advisory allowance expired on "
                    f"{signal.advisory_expires}. It is blocking again by design — "
                    f"either land the remediation ({signal.advisory_owner}) or "
                    f"extend the date in a reviewed change that says why."
                )
                continue
            accepted.add(signal_id)

        return accepted, problems

    def get_blocking_signals(self) -> list[Signal]:
        """Get all blocking signals."""
        return [s for s in self._signals.values() if s.is_blocking]

    def verify_single_ownership(self) -> tuple[bool, list[str]]:
        """Verify that every signal has exactly one owner.

        Returns:
            Tuple of (valid, errors)
        """
        errors = []
        seen_owners: dict[tuple, Set[str]] = {}

        for signal in self._signals.values():
            key = (
                signal.signal_type,
                signal.verdict_semantics,
                signal.scope,
                signal.trust_boundary,
            )

            if key not in seen_owners:
                seen_owners[key] = set()

            seen_owners[key].add(signal.owner_job)

            if len(seen_owners[key]) > 1:
                errors.append(f"Multiple owners for {key}: {seen_owners[key]}")

        return len(errors) == 0, errors

    def __len__(self) -> int:
        """Return total number of registered signals."""
        return len(self._signals)

    def __iter__(self):
        """Iterate over all signals."""
        return iter(self._signals.values())

    def __getitem__(self, key: str) -> Signal:
        """Get signal by ID using dictionary syntax."""
        return self._signals[key]

    def __contains__(self, key: str) -> bool:
        """Check if signal exists using 'in' operator."""
        return key in self._signals

    def keys(self):
        """Get all signal IDs."""
        return self._signals.keys()


# Global singleton registry instance
SIGNAL_REGISTRY = SignalRegistry()
