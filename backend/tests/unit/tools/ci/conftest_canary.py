"""
Fault injection fixtures and helpers for shadow/canary evaluation testing.

This module provides fixtures for testing all 12 canary scenarios:
1. Cache determinism (same SHA, empty and warm caches)
2. New SHA evaluation
3. Fork PR canary
4. PR head supersession
5. Trusted reusable invocation
6. Artifact corruption injection
7. Failed producer injection
8. Unavailable PostgreSQL
9. High/Critical dependency finding
10. High/Critical container finding
11. Stale SHA detection
12. Clean positive canary

All fixtures normalize results and provide fault injection helpers.
"""

import json
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime
import hashlib
from enum import Enum
import pytest


class EvaluationState(str, Enum):
    """Enumeration of evaluation result states."""

    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"
    MISSING = "missing"
    UNAVAILABLE = "unavailable"


@dataclass
class ArtifactManifest:
    """Manifest record for a single evidence artifact."""

    path: str
    format: str  # junit, coverage-data, execution-inventory, lcov, cobertura
    bytes_: int
    sha256: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "format": self.format,
            "bytes": self.bytes_,
            "sha256": self.sha256,
        }


@dataclass
class ProducerEvidence:
    """Evidence record from one producer job."""

    schema_version: int
    repository: str
    evaluation_sha: str
    run_id: int
    run_attempt: int
    producer: str
    inventory_sha256: Optional[str]
    command_sha256: Optional[str]
    tool_versions: Dict[str, str]
    outcome: str  # success, failure, etc.
    files: List[ArtifactManifest]
    timestamp: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["files"] = [f.to_dict() for f in self.files]
        if self.timestamp is None:
            data["timestamp"] = datetime.utcnow().isoformat() + "Z"
        return data

    def normalize_for_comparison(self) -> Dict[str, Any]:
        """Return manifest without run ID, attempt, or timestamps for cache comparison."""
        data = self.to_dict()
        del data["run_id"]
        del data["run_attempt"]
        if "timestamp" in data:
            del data["timestamp"]
        return data


@dataclass
class EvaluationResult:
    """Result of one CI evaluation."""

    evaluation_sha: str
    repository: str
    run_id: int
    run_attempt: int
    ci_evidence_outcome: str  # success, failure, etc.
    ci_required_shadow_outcome: Optional[str]  # shadow status only, not authoritative

    # Signal results: signal_name -> state
    signal_verdicts: Dict[str, str]

    # Coverage results
    backend_coverage_overall: Optional[float]
    frontend_coverage_statements: Optional[float]
    frontend_coverage_branches: Optional[float]
    frontend_coverage_functions: Optional[float]
    frontend_coverage_lines: Optional[float]

    # Findings
    high_critical_software_findings: int

    # Test execution
    backend_offline_test_count: Optional[int]
    backend_postgres_test_count: Optional[int]
    frontend_vitest_test_count: Optional[int]
    frontend_e2e_test_count: Optional[int]

    # Artifacts
    producer_evidences: List[ProducerEvidence]

    timestamp: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["producer_evidences"] = [e.to_dict() for e in self.producer_evidences]
        if self.timestamp is None:
            data["timestamp"] = datetime.utcnow().isoformat() + "Z"
        return data

    def normalize_for_comparison(self) -> Dict[str, Any]:
        """Return result without run ID, attempt, or timestamps for cache comparison."""
        data = self.to_dict()
        del data["run_id"]
        del data["run_attempt"]
        if "timestamp" in data:
            del data["timestamp"]
        # Normalize producer evidences
        data["producer_evidences"] = [
            e
            for evidence in self.producer_evidences
            for e in [evidence.normalize_for_comparison()]
        ]
        return data

    def is_success(self) -> bool:
        """Check if this result represents a successful evaluation."""
        return (
            self.ci_evidence_outcome == "success"
            and all(v == "success" for v in self.signal_verdicts.values())
            and self.backend_coverage_overall is not None
            and self.backend_coverage_overall >= 80.0
            and self.frontend_coverage_statements is not None
            and self.frontend_coverage_statements >= 80.0
            and self.frontend_coverage_branches is not None
            and self.frontend_coverage_branches >= 80.0
            and self.frontend_coverage_functions is not None
            and self.frontend_coverage_functions >= 80.0
            and self.frontend_coverage_lines is not None
            and self.frontend_coverage_lines >= 80.0
            and self.high_critical_software_findings == 0
        )


@pytest.fixture
def mock_github_api():
    """Provide a mock GitHub API context."""
    api = MagicMock()

    # Commit status operations
    api.create_status = MagicMock(return_value={"state": "pending"})
    api.update_status = MagicMock(return_value={"state": "success"})

    # Check run operations
    api.create_check_run = MagicMock(return_value={"id": 123456})
    api.update_check_run = MagicMock(
        return_value={"id": 123456, "conclusion": "success"}
    )

    # Artifact operations
    api.upload_artifact = MagicMock(return_value={"id": 789012})
    api.download_artifact = MagicMock(return_value={})

    # PR operations
    api.get_pr_head_sha = MagicMock(return_value="abc123def456" * 3 + "789abc")
    api.list_pr_commits = MagicMock(return_value=[])

    return api

    # Metrics
    api.get_coverage = MagicMock(return_value={"coverage": 85.0})

    return api


@pytest.fixture
def mock_artifact_store(tmp_path):
    """Provide a temporary artifact store context."""
    store_dir = tmp_path / "artifacts"
    store_dir.mkdir()

    class ArtifactStore:
        def __init__(self, base_dir):
            self.base_dir = base_dir

        def store_artifact(
            self, path: str, content: bytes, metadata: Dict[str, Any]
        ) -> str:
            """Store an artifact and return checksum."""
            file_path = self.base_dir / path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(content)

            sha256 = hashlib.sha256(content).hexdigest()
            metadata_path = self.base_dir / f"{path}.meta.json"
            metadata["sha256"] = sha256
            metadata_path.write_text(json.dumps(metadata))

            return sha256

        def get_artifact(self, path: str) -> Tuple[bytes, Dict[str, Any]]:
            """Retrieve an artifact and its metadata."""
            file_path = self.base_dir / path
            if not file_path.exists():
                raise FileNotFoundError(f"Artifact not found: {path}")

            content = file_path.read_bytes()
            metadata_path = self.base_dir / f"{path}.meta.json"
            metadata = {}
            if metadata_path.exists():
                metadata = json.loads(metadata_path.read_text())

            return content, metadata

        def list_artifacts(self, prefix: str = "") -> List[str]:
            """List all artifacts matching a prefix."""
            results = []
            for f in self.base_dir.rglob("*"):
                if f.is_file() and not f.name.endswith(".meta.json"):
                    rel_path = str(f.relative_to(self.base_dir))
                    if rel_path.startswith(prefix):
                        results.append(rel_path)
            return sorted(results)

    return ArtifactStore(store_dir)


@pytest.fixture
def evaluation_builder(mock_artifact_store):
    """Provide a builder for constructing EvaluationResult fixtures."""

    class EvaluationBuilder:
        def __init__(self):
            self.sha = "abc123def456" * 3 + "789abc"
            self.run_id = 12345678
            self.run_attempt = 1
            self.repository = "test-repo"
            self.producer_evidences: List[ProducerEvidence] = []

        def with_sha(self, sha: str) -> "EvaluationBuilder":
            self.sha = sha
            return self

        def with_run_id(self, run_id: int) -> "EvaluationBuilder":
            self.run_id = run_id
            return self

        def with_run_attempt(self, attempt: int) -> "EvaluationBuilder":
            self.run_attempt = attempt
            return self

        def add_producer_evidence(
            self,
            producer: str,
            outcome: str,
            tool_versions: Optional[Dict[str, str]] = None,
            files: Optional[List[ArtifactManifest]] = None,
        ) -> "EvaluationBuilder":
            if tool_versions is None:
                tool_versions = {"pytest": "8.0.0", "python": "3.13.0"}
            if files is None:
                files = []

            evidence = ProducerEvidence(
                schema_version=1,
                repository=self.repository,
                evaluation_sha=self.sha,
                run_id=self.run_id,
                run_attempt=self.run_attempt,
                producer=producer,
                inventory_sha256="inv123",
                command_sha256="cmd456",
                tool_versions=tool_versions,
                outcome=outcome,
                files=files,
            )
            self.producer_evidences.append(evidence)
            return self

        def build_success(self) -> EvaluationResult:
            """Build a successful evaluation result."""
            return EvaluationResult(
                evaluation_sha=self.sha,
                repository=self.repository,
                run_id=self.run_id,
                run_attempt=self.run_attempt,
                ci_evidence_outcome="success",
                ci_required_shadow_outcome="success",
                signal_verdicts={
                    "repo-static": "success",
                    "backend-inventory": "success",
                    "backend-static": "success",
                    "backend-offline": "success",
                    "backend-postgres": "success",
                    "backend-evidence": "success",
                    "frontend-build": "success",
                    "frontend-static": "success",
                    "frontend-vitest": "success",
                    "frontend-e2e": "success",
                    "frontend-evidence": "success",
                    "security[secrets]": "success",
                    "security[iac]": "success",
                    "container-scan[backend]": "success",
                    "container-scan[frontend]": "success",
                },
                backend_coverage_overall=85.5,
                frontend_coverage_statements=82.3,
                frontend_coverage_branches=81.1,
                frontend_coverage_functions=83.4,
                frontend_coverage_lines=84.2,
                high_critical_software_findings=0,
                backend_offline_test_count=1500,
                backend_postgres_test_count=200,
                frontend_vitest_test_count=850,
                frontend_e2e_test_count=194,
                producer_evidences=self.producer_evidences,
            )

        def build_failure(self, reason: str) -> EvaluationResult:
            """Build a failed evaluation result."""
            result = self.build_success()
            result.ci_evidence_outcome = "failure"
            result.ci_required_shadow_outcome = "failure"
            # Update verdicts based on reason
            if "container" in reason.lower():
                result.signal_verdicts["container-scan[backend]"] = "failure"
            if "coverage" in reason.lower():
                result.backend_coverage_overall = 75.0
            if "findings" in reason.lower():
                result.high_critical_software_findings = 2
                result.signal_verdicts["container-scan[frontend]"] = "failure"
            return result

    return EvaluationBuilder()


@pytest.fixture
def artifact_fault_injector():
    """Provide artifact corruption fault injection helpers."""

    class ArtifactFaultInjector:
        def inject_traversal_path(self) -> ArtifactManifest:
            """Create artifact with traversal path."""
            return ArtifactManifest(
                path="../../../etc/passwd",
                format="junit",
                bytes_=100,
                sha256="fake",
            )

        def inject_malformed_json(self) -> bytes:
            """Create malformed JSON content."""
            return b'{"incomplete": "json"'

        def inject_malformed_xml(self) -> bytes:
            """Create malformed XML content."""
            return b'<junit><testcase name="test"</junit>'

        def inject_checksum_mismatch(self) -> Tuple[bytes, str]:
            """Create content with mismatched checksum."""
            content = b'<junit><testcase name="test" /></junit>'
            wrong_hash = (
                "0000000000000000000000000000000000000000000000000000000000000000"
            )
            return content, wrong_hash

        def inject_oversized_file(self, size_bytes: int = 200 * 1024 * 1024) -> bytes:
            """Create oversized file content."""
            return b"X" * size_bytes

    return ArtifactFaultInjector()


@pytest.fixture
def producer_fault_injector():
    """Provide producer failure fault injection helpers."""

    class ProducerFaultInjector:
        def inject_failed_producer(
            self,
            result: EvaluationResult,
            producer_name: str,
        ) -> EvaluationResult:
            """Mark a producer as failed."""
            result.signal_verdicts[producer_name] = "failure"
            result.ci_evidence_outcome = "failure"
            result.ci_required_shadow_outcome = "failure"

            # Update producer evidences
            for evidence in result.producer_evidences:
                if evidence.producer == producer_name:
                    evidence.outcome = "failure"

            return result

        def inject_missing_producer(
            self,
            result: EvaluationResult,
            producer_name: str,
        ) -> EvaluationResult:
            """Remove a producer entirely."""
            result.signal_verdicts.pop(producer_name, None)
            result.producer_evidences = [
                e for e in result.producer_evidences if e.producer != producer_name
            ]
            result.ci_evidence_outcome = "failure"
            result.ci_required_shadow_outcome = "failure"
            return result

    return ProducerFaultInjector()


@pytest.fixture
def database_fault_injector():
    """Provide database fault injection helpers."""

    class DatabaseFaultInjector:
        def inject_postgres_unavailable(
            self,
            result: EvaluationResult,
        ) -> EvaluationResult:
            """Simulate PostgreSQL service unavailable."""
            result.signal_verdicts["backend-postgres"] = "failure"
            result.backend_postgres_test_count = None
            result.ci_evidence_outcome = "failure"
            result.ci_required_shadow_outcome = "failure"
            return result

        def inject_postgres_readiness_failure(
            self,
            result: EvaluationResult,
        ) -> EvaluationResult:
            """Simulate PostgreSQL readiness probe failure."""
            result.signal_verdicts["backend-postgres"] = "failure"
            result.backend_postgres_test_count = 0
            result.ci_evidence_outcome = "failure"
            result.ci_required_shadow_outcome = "failure"
            return result

    return DatabaseFaultInjector()


@pytest.fixture
def dependency_fault_injector():
    """Provide dependency/vulnerability fault injection helpers."""

    class DependencyFaultInjector:
        def inject_high_severity_finding(self) -> Dict[str, Any]:
            """Create a HIGH severity finding."""
            return {
                "scanner": "pip-audit",
                "advisory_id": "PYPA-2024-001",
                "package": "python-jose",
                "version": "3.3.0",
                "severity": "HIGH",
                "fixed_in": "3.4.0",
                "vulnerability": "Improper Input Validation",
            }

        def inject_critical_severity_finding(self) -> Dict[str, Any]:
            """Create a CRITICAL severity finding."""
            return {
                "scanner": "trivy",
                "vulnerability_id": "CVE-2024-12345",
                "package": "libssl",
                "version": "1.1.0",
                "severity": "CRITICAL",
                "image": "python:3.13-slim",
                "fixed_in": "1.1.1",
            }

        def inject_unfixed_high_finding(self) -> Dict[str, Any]:
            """Create a HIGH severity unfixed finding."""
            return {
                "scanner": "npm-audit",
                "advisory_id": "GHSA-xxxx-yyyy-zzzz",
                "package": "image-size",
                "version": "1.0.0",
                "severity": "HIGH",
                "fixed_in": None,  # No fix available
                "vulnerability": "Prototype Pollution",
            }

    return DependencyFaultInjector()


@pytest.fixture
def stale_sha_injector():
    """Provide stale SHA fault injection helpers."""

    class StaleShaInjector:
        def inject_wrong_sha(
            self,
            result: EvaluationResult,
            wrong_sha: str,
        ) -> EvaluationResult:
            """Modify result to report wrong SHA."""
            # This simulates ci-evidence reporting an incorrect SHA
            result.evaluation_sha = wrong_sha
            return result

        def inject_mismatched_sha(
            self,
            result: EvaluationResult,
            expected_sha: str,
        ) -> EvaluationResult:
            """Create SHA mismatch between result and evidence."""
            result.signal_verdicts["backend-evidence"] = "failure"
            result.ci_evidence_outcome = "failure"
            result.ci_required_shadow_outcome = "failure"
            return result

    return StaleShaInjector()


@pytest.fixture
def cache_determinism_validator():
    """Provide cache determinism comparison logic."""

    class CacheDeterminismValidator:
        @staticmethod
        def normalize_result(result: EvaluationResult) -> Dict[str, Any]:
            """Normalize a result for comparison (remove run-specific fields)."""
            normalized = result.normalize_for_comparison()
            return normalized

        @staticmethod
        def compare_results(
            result1: EvaluationResult,
            result2: EvaluationResult,
        ) -> Tuple[bool, List[str]]:
            """
            Compare two results for cache determinism.

            Returns (are_equivalent, differences)
            """
            norm1 = CacheDeterminismValidator.normalize_result(result1)
            norm2 = CacheDeterminismValidator.normalize_result(result2)

            differences = []

            # Compare all fields except run-specific ones
            for key in norm1:
                if norm1[key] != norm2.get(key):
                    differences.append(
                        f"Mismatch in {key}: {norm1[key]} vs {norm2.get(key)}"
                    )

            # Check all 4 frontend coverage metrics
            if norm1.get("frontend_coverage_statements") != norm2.get(
                "frontend_coverage_statements"
            ):
                differences.append(
                    f"Frontend statements coverage: "
                    f"{norm1.get('frontend_coverage_statements')} vs "
                    f"{norm2.get('frontend_coverage_statements')}"
                )

            are_equivalent = len(differences) == 0
            return are_equivalent, differences

    return CacheDeterminismValidator()
