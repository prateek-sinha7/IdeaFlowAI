"""Signal registry — authoritative mapping of CI signals to single owners.

Every unique mandatory signal has exactly one producer and one truth function.
Signals are unique by purpose, verdict semantics, scope, and trust boundary.
Duplicate execution uses the same exact revision, inputs, config, tool version,
and equivalent or strictly contained scope; work separated by materially
different trust boundaries, privilege sets, artifact responsibilities, or
policy verdicts remains distinct.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Set


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
                tool_version="1.7.12",
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
                tool_version="8.30.1",
                config_file="ci/gitleaks.toml",
                timeout_seconds=600,
            )
        )

        self._register_signal(
            Signal(
                id="security[backend-deps]",
                name="pip-audit",
                description="Python dependency audit and vulnerability detection",
                signal_type=SignalType.SECURITY_SCAN,
                owner_job="security",
                scope="backend-dependencies",
                trust_boundary="frozen-lock",
                verdict_semantics="zero-high-critical-dependencies",
                required_artifact_formats=["json"],
                tool_version="(via uv frozen)",
                config_file="backend/pyproject.toml",
                timeout_seconds=600,
            )
        )

        self._register_signal(
            Signal(
                id="security[frontend-deps]",
                name="npm-audit",
                description="NPM dependency audit and vulnerability detection",
                signal_type=SignalType.SECURITY_SCAN,
                owner_job="security",
                scope="frontend-dependencies",
                trust_boundary="frozen-lock",
                verdict_semantics="zero-high-critical-dependencies",
                required_artifact_formats=["json"],
                tool_version="(npm built-in)",
                config_file="frontend/package-lock.json",
                timeout_seconds=600,
            )
        )

        # ===== Backend Inventory and Static Checks =====
        self._register_signal(
            Signal(
                id="backend-inventory",
                name="Backend test inventory",
                description="Canonical pytest collection and test node classification",
                signal_type=SignalType.TEST_EXECUTION,
                owner_job="backend-inventory",
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
                scope="backend-python",
                trust_boundary="repository-code",
                verdict_semantics="ruff-lint-passed",
                required_artifact_formats=["log", "json"],
                tool_version="0.9.11",
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
                scope="backend-python",
                trust_boundary="repository-code",
                verdict_semantics="ruff-format-passed",
                required_artifact_formats=["log"],
                tool_version="0.9.11",
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
                description="Python type checking with Pyright",
                signal_type=SignalType.STATIC_CHECK,
                owner_job="backend-static",
                scope="backend-python",
                trust_boundary="repository-code",
                verdict_semantics="pyright-passed",
                required_artifact_formats=["log", "json"],
                tool_version="1.1.407",
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
                scope="frontend-typescript",
                trust_boundary="repository-code",
                verdict_semantics="eslint-passed",
                required_artifact_formats=["log"],
                timeout_seconds=300,
            )
        )

        self._register_signal(
            Signal(
                id="frontend-static/build",
                name="Frontend build",
                description="Production Next.js build validation",
                signal_type=SignalType.STATIC_CHECK,
                owner_job="frontend-static",
                scope="frontend-build",
                trust_boundary="repository-code",
                verdict_semantics="build-succeeds",
                required_artifact_formats=["log"],
                timeout_seconds=720,
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
                scope="frontend-e2e",
                trust_boundary="ci-code",
                verdict_semantics="all-mocked-e2e-tests-pass",
                required_artifact_formats=["junit"],
                timeout_seconds=1500,
            )
        )

        self._register_signal(
            Signal(
                id="frontend-evidence",
                name="Frontend evidence aggregation",
                description="Merge frontend coverage/E2E, validate producers, enforce >=80% all metrics",
                signal_type=SignalType.COVERAGE_REPORT,
                owner_job="frontend-evidence",
                scope="frontend-coverage",
                trust_boundary="ci-code",
                verdict_semantics="frontend-coverage-80-percent-all-metrics",
                required_artifact_formats=["lcov", "junit"],
                timeout_seconds=600,
            )
        )

        self._register_signal(
            Signal(
                id="security[iac]/terraform-fmt",
                name="Terraform fmt",
                description="Terraform code formatting validation",
                signal_type=SignalType.STATIC_CHECK,
                owner_job="security",
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
                scope="terraform-configuration",
                trust_boundary="repository-code",
                verdict_semantics="tflint-passed",
                required_artifact_formats=["log"],
                tool_version="0.59.1",
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
                scope="terraform-configuration",
                trust_boundary="repository-code",
                verdict_semantics="iac-policies-passed",
                required_artifact_formats=["json"],
                tool_version="3.2.180",
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
                scope="terraform-configuration",
                trust_boundary="repository-code",
                verdict_semantics="zero-high-critical-config-vulns",
                required_artifact_formats=["json"],
                tool_version="0.69.3",
                timeout_seconds=600,
            )
        )

        # ===== Container Scanning Signals =====
        self._register_signal(
            Signal(
                id="container-scan[backend]/trivy",
                name="Trivy image scan (backend)",
                description="Container image vulnerability scan with Trivy",
                signal_type=SignalType.SECURITY_SCAN,
                owner_job="container-scan",
                scope="backend-image",
                trust_boundary="ci-build",
                verdict_semantics="zero-high-critical-image-vulns",
                required_artifact_formats=["json"],
                tool_version="0.69.3",
                timeout_seconds=600,
            )
        )

        self._register_signal(
            Signal(
                id="container-scan[backend]/grype",
                name="Grype image scan (backend)",
                description="Container image vulnerability scan with Grype",
                signal_type=SignalType.SECURITY_SCAN,
                owner_job="container-scan",
                scope="backend-image",
                trust_boundary="ci-build",
                verdict_semantics="zero-high-critical-image-vulns",
                required_artifact_formats=["json"],
                tool_version="0.75.0",
                timeout_seconds=600,
            )
        )

        self._register_signal(
            Signal(
                id="container-scan[frontend]/trivy",
                name="Trivy image scan (frontend)",
                description="Container image vulnerability scan with Trivy",
                signal_type=SignalType.SECURITY_SCAN,
                owner_job="container-scan",
                scope="frontend-image",
                trust_boundary="ci-build",
                verdict_semantics="zero-high-critical-image-vulns",
                required_artifact_formats=["json"],
                tool_version="0.69.3",
                timeout_seconds=600,
            )
        )

        self._register_signal(
            Signal(
                id="container-scan[frontend]/grype",
                name="Grype image scan (frontend)",
                description="Container image vulnerability scan with Grype",
                signal_type=SignalType.SECURITY_SCAN,
                owner_job="container-scan",
                scope="frontend-image",
                trust_boundary="ci-build",
                verdict_semantics="zero-high-critical-image-vulns",
                required_artifact_formats=["json"],
                tool_version="0.75.0",
                timeout_seconds=600,
            )
        )

        # ===== Sonar Quality Gate =====
        self._register_signal(
            Signal(
                id="sonar-analysis",
                name="Sonar analysis",
                description="SonarCloud/SonarQube static analysis completion",
                signal_type=SignalType.EXTERNAL_GATE,
                owner_job="sonar-pr",
                scope="source-analysis",
                trust_boundary="sonar-service",
                verdict_semantics="sonar-analysis-complete",
                required_artifact_formats=["json"],
                timeout_seconds=600,
            )
        )

        self._register_signal(
            Signal(
                id="sonar-quality-gate",
                name="Sonar quality gate",
                description="SonarCloud/SonarQube quality gate verdict",
                signal_type=SignalType.EXTERNAL_GATE,
                owner_job="sonar-pr",
                scope="source-analysis",
                trust_boundary="sonar-service",
                verdict_semantics="sonar-quality-gate-passed",
                required_artifact_formats=["json"],
                timeout_seconds=600,
            )
        )

        # ===== Aggregate Gate (ci-evidence and ci-required-shadow during shadow mode) =====
        # This signal exists to define the mandatory aggregate composition
        # During shadow (Tasks 3.19-3.25), publishes as ci-required-shadow
        # After cutover (Task 3.26+), renamed to ci-required
        self._register_signal(
            Signal(
                id="ci-required",
                name="CI Required Gate",
                description="Aggregate verdict that all mandatory signals succeeded for exact current SHA",
                signal_type=SignalType.EXTERNAL_GATE,
                owner_job="ci-evidence",  # Shadow mode: ci-evidence or ci-required-shadow job
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
                    "frontend-static/build",
                    "frontend-vitest",
                    "frontend-e2e",
                    "frontend-evidence",
                    "security[secrets]",
                    "security[backend-deps]",
                    "security[frontend-deps]",
                    "security[iac]/terraform-fmt",
                    "security[iac]/terraform-validate",
                    "security[iac]/tflint",
                    "security[iac]/checkov",
                    "security[iac]/trivy-config",
                    "container-scan[backend]/trivy",
                    "container-scan[backend]/grype",
                    "container-scan[frontend]/trivy",
                    "container-scan[frontend]/grype",
                    "sonar-analysis",
                    "sonar-quality-gate",
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

    def get_mandatory_signals(self) -> list[Signal]:
        """Get all mandatory signals."""
        return [s for s in self._signals.values() if s.is_mandatory]

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
