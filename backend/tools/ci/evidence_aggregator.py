"""
Evidence Aggregation for CI Pipeline.

Implements backend, frontend, and aggregate evidence collection and validation
for the shadow evaluator phase. Validates producer completeness, merges coverage
and JUnit reports, enforces coverage thresholds, and computes the final aggregate
verdict.

Requirements: 2.5, 2.6, 2.13, 2.14, 3.8, 3.14, 3.15
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

from tools.ci.evidence_manifest import EvidenceManifest, FileRecord
from tools.ci.report_parsers import JUnitReport, CoverageReport
from tools.ci.report_merger import merge_junit_reports, merge_coverage_reports
from tools.ci.aggregate_truth import SignalResult, SignalState


class ProducerOutcome(str, Enum):
    """Outcome states for evidence producers."""

    SUCCESS = "success"
    FAILURE = "failure"
    MISSING = "missing"
    INVALID = "invalid"


@dataclass
class ProducerEvidence:
    """Evidence from a single producer."""

    name: str
    outcome: ProducerOutcome
    manifest: Optional[EvidenceManifest] = None
    junit_report: Optional[JUnitReport] = None
    coverage_report: Optional[CoverageReport] = None
    errors: list[str] = field(default_factory=list)


@dataclass
class BackendEvidenceResult:
    """Result of backend evidence aggregation."""

    evaluation_sha: str
    inventory_sha256: str
    success: bool
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    skipped_tests: int = 0
    coverage_percent: float = 0.0
    coverage_lines_percent: float = 0.0
    producer_outcomes: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    merged_junit_path: Optional[Path] = None
    merged_coverage_path: Optional[Path] = None
    manifest_path: Optional[Path] = None


@dataclass
class FrontendEvidenceResult:
    """Result of frontend evidence aggregation."""

    evaluation_sha: str
    success: bool
    vitest_total: int = 0
    vitest_passed: int = 0
    vitest_failed: int = 0
    vitest_skipped: int = 0
    e2e_total: int = 0
    e2e_passed: int = 0
    e2e_failed: int = 0
    e2e_skipped: int = 0
    coverage_statements: float = 0.0
    coverage_branches: float = 0.0
    coverage_functions: float = 0.0
    coverage_lines: float = 0.0
    producer_outcomes: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    merged_junit_path: Optional[Path] = None
    merged_lcov_path: Optional[Path] = None
    manifest_path: Optional[Path] = None


class BackendEvidenceAggregator:
    """Aggregates backend test and coverage evidence."""

    def __init__(
        self,
        evaluation_sha: str,
        output_dir: Path,
        coverage_threshold: float = 80.0,
    ):
        """Initialize aggregator.

        Args:
            evaluation_sha: Exact 40-character SHA for this evaluation
            output_dir: Directory for aggregated outputs
            coverage_threshold: Required coverage percentage (default 80.0)
        """
        self.evaluation_sha = evaluation_sha
        self.output_dir = Path(output_dir)
        self.coverage_threshold = coverage_threshold
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def aggregate(
        self,
        offline_evidence: ProducerEvidence,
        postgres_evidence: ProducerEvidence,
        inventory_sha256: str,
    ) -> BackendEvidenceResult:
        """Aggregate backend evidence from offline and PostgreSQL producers.

        Args:
            offline_evidence: Evidence from offline partition
            postgres_evidence: Evidence from PostgreSQL partition
            inventory_sha256: SHA-256 digest of inventory manifest

        Returns:
            Aggregation result with merged reports and verdict
        """
        result = BackendEvidenceResult(
            evaluation_sha=self.evaluation_sha,
            inventory_sha256=inventory_sha256,
            success=True,
        )

        # Validate producer outcomes
        producers = {
            "backend-offline": offline_evidence,
            "backend-postgres": postgres_evidence,
        }
        for producer_name, evidence in producers.items():
            result.producer_outcomes[producer_name] = evidence.outcome.value
            if evidence.outcome != ProducerOutcome.SUCCESS:
                result.errors.append(
                    f"{producer_name}: {evidence.outcome.value} "
                    f"({'; '.join(evidence.errors) if evidence.errors else 'no details'})"
                )

        # If any mandatory producer failed, the aggregate fails
        if any(e.outcome != ProducerOutcome.SUCCESS for e in producers.values()):
            result.success = False
            return result

        # Validate manifests exist
        for producer_name, evidence in producers.items():
            if evidence.manifest is None:
                result.errors.append(f"{producer_name}: manifest missing")
                result.success = False
                continue

            # Validate SHA matches
            if evidence.manifest.evaluation_sha != self.evaluation_sha:
                result.errors.append(
                    f"{producer_name}: stale SHA "
                    f"({evidence.manifest.evaluation_sha[:8]} != {self.evaluation_sha[:8]})"
                )
                result.success = False

        if not result.success:
            return result

        # Merge JUnit reports
        junit_reports = []
        for evidence in [offline_evidence, postgres_evidence]:
            if evidence.junit_report:
                junit_reports.append(evidence.junit_report)

        if junit_reports:
            try:
                merge_result = merge_junit_reports(
                    junit_reports,
                    result.producer_outcomes,
                )
                merged_junit = merge_result.merged_report
                result.total_tests = merged_junit.total_tests
                result.passed_tests = (
                    merged_junit.total_tests
                    - merged_junit.total_failures
                    - merged_junit.total_errors
                    - merged_junit.total_skipped
                )
                result.failed_tests = (
                    merged_junit.total_failures + merged_junit.total_errors
                )
                result.skipped_tests = merged_junit.total_skipped

                # Write merged JUnit
                merged_junit_xml = self._create_junit_xml(merged_junit)
                result.merged_junit_path = self.output_dir / "junit-backend.xml"
                result.merged_junit_path.write_text(merged_junit_xml)
            except ValueError as e:
                result.errors.append(f"JUnit merge failed: {e}")
                result.success = False

        # Merge coverage reports
        coverage_reports = []
        coverage_producers = []
        for i, evidence in enumerate([offline_evidence, postgres_evidence]):
            if evidence.coverage_report:
                coverage_reports.append(evidence.coverage_report)
                coverage_producers.append(["backend-offline", "backend-postgres"][i])

        if coverage_reports:
            try:
                merge_result = merge_coverage_reports(
                    coverage_reports,
                    coverage_producers,
                )
                merged_coverage = merge_result.merged_report
                result.coverage_lines_percent = merged_coverage.get_line_percentage()

                # Check threshold
                if result.coverage_lines_percent < self.coverage_threshold:
                    result.errors.append(
                        f"Backend coverage {result.coverage_lines_percent:.2f}% "
                        f"< threshold {self.coverage_threshold}%"
                    )
                    result.success = False

                # Write merged coverage as Cobertura XML
                merged_coverage_xml = self._create_cobertura_xml(merged_coverage)
                result.merged_coverage_path = self.output_dir / "coverage.xml"
                result.merged_coverage_path.write_text(merged_coverage_xml)
            except ValueError as e:
                result.errors.append(f"Coverage merge failed: {e}")
                result.success = False

        # Create evidence manifest
        manifest = EvidenceManifest(
            schema_version=1,
            repository="IdeaFlowAI",
            evaluation_sha=self.evaluation_sha,
            producer="backend-evidence",
            inventory_sha256=inventory_sha256,
            outcome="success" if result.success else "failure",
            tool_versions={"python": "3.13", "pytest": "latest"},
            timestamps={"aggregated_at": datetime.utcnow().isoformat()},
        )

        # Add files using absolute paths (add_file handles validation)
        # Store relative paths in manifest records
        if result.merged_junit_path and result.merged_junit_path.exists():
            try:
                manifest.add_file(result.merged_junit_path, "junit")
            except ValueError:
                # Path is absolute, so we add it manually with relative name
                file_record = FileRecord(
                    path=result.merged_junit_path.name,
                    format="junit",
                    bytes=result.merged_junit_path.stat().st_size,
                    sha256=self._compute_file_sha256(result.merged_junit_path),
                )
                manifest.files.append(file_record)

        if result.merged_coverage_path and result.merged_coverage_path.exists():
            try:
                manifest.add_file(result.merged_coverage_path, "cobertura")
            except ValueError:
                # Path is absolute, so we add it manually with relative name
                file_record = FileRecord(
                    path=result.merged_coverage_path.name,
                    format="cobertura",
                    bytes=result.merged_coverage_path.stat().st_size,
                    sha256=self._compute_file_sha256(result.merged_coverage_path),
                )
                manifest.files.append(file_record)

        manifest.save(self.output_dir / "manifest.json")
        result.manifest_path = self.output_dir / "manifest.json"

        return result

    def _create_junit_xml(self, report: JUnitReport) -> str:
        """Create JUnit XML from report."""
        root = ET.Element("testsuites")
        root.set("tests", str(report.total_tests))
        failures = report.total_failures + report.total_errors
        root.set("failures", str(failures))
        root.set("skipped", str(report.total_skipped))
        root.set("time", "0")

        testsuite = ET.SubElement(root, "testsuite")
        testsuite.set("name", "backend-tests")
        testsuite.set("tests", str(report.total_tests))
        testsuite.set("failures", str(failures))
        testsuite.set("skipped", str(report.total_skipped))
        testsuite.set("time", "0")

        for test_case in report.test_cases:
            tc_elem = ET.SubElement(testsuite, "testcase")
            tc_elem.set("classname", test_case.classname)
            tc_elem.set("name", test_case.name)
            if test_case.time:
                tc_elem.set("time", str(test_case.time))

            if test_case.failure_message:
                failure_elem = ET.SubElement(tc_elem, "failure")
                failure_elem.set("message", test_case.failure_message)
                if test_case.failure_text:
                    failure_elem.text = test_case.failure_text

            if test_case.skipped:
                ET.SubElement(tc_elem, "skipped")

        return ET.tostring(root, encoding="unicode")

    def _create_cobertura_xml(self, report: CoverageReport) -> str:
        """Create Cobertura XML from coverage report."""
        root = ET.Element("coverage")
        root.set("line-rate", str(report.get_line_percentage() / 100))
        root.set("branch-rate", str(report.get_branch_percentage() / 100))
        root.set("lines-valid", str(report.lines_total))
        root.set("lines-covered", str(report.lines_covered))
        root.set("line-rate", str(report.get_line_percentage() / 100))
        root.set("timestamp", str(int(datetime.utcnow().timestamp() * 1000)))

        packages = ET.SubElement(root, "packages")
        for filepath, file_cov in report.files.items():
            package = ET.SubElement(packages, "package")
            package.set("name", filepath)
            package.set("line-rate", "1.0")
            package.set("branch-rate", "1.0")

        return ET.tostring(root, encoding="unicode")

    @staticmethod
    def _compute_file_sha256(file_path: Path) -> str:
        """Compute SHA-256 hash of a file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()


class FrontendEvidenceAggregator:
    """Aggregates frontend test and coverage evidence."""

    def __init__(
        self,
        evaluation_sha: str,
        output_dir: Path,
        coverage_threshold: float = 80.0,
    ):
        """Initialize aggregator.

        Args:
            evaluation_sha: Exact 40-character SHA for this evaluation
            output_dir: Directory for aggregated outputs
            coverage_threshold: Required coverage percentage for all metrics
        """
        self.evaluation_sha = evaluation_sha
        self.output_dir = Path(output_dir)
        self.coverage_threshold = coverage_threshold
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def aggregate(
        self,
        vitest_evidence: ProducerEvidence,
        e2e_evidence: ProducerEvidence,
    ) -> FrontendEvidenceResult:
        """Aggregate frontend evidence from Vitest and E2E producers.

        Args:
            vitest_evidence: Evidence from Vitest execution
            e2e_evidence: Evidence from E2E/Playwright execution

        Returns:
            Aggregation result with merged reports and verdict
        """
        result = FrontendEvidenceResult(
            evaluation_sha=self.evaluation_sha,
            success=True,
        )

        # Validate producers
        producers = {"frontend-vitest": vitest_evidence, "frontend-e2e": e2e_evidence}
        for producer_name, evidence in producers.items():
            result.producer_outcomes[producer_name] = evidence.outcome.value
            if evidence.outcome != ProducerOutcome.SUCCESS:
                result.errors.append(
                    f"{producer_name}: {evidence.outcome.value} "
                    f"({'; '.join(evidence.errors) if evidence.errors else 'no details'})"
                )

        # If any producer failed, the aggregate fails
        if any(e.outcome != ProducerOutcome.SUCCESS for e in producers.values()):
            result.success = False
            return result

        # Validate manifests
        for producer_name, evidence in producers.items():
            if evidence.manifest is None:
                result.errors.append(f"{producer_name}: manifest missing")
                result.success = False
                continue

            if evidence.manifest.evaluation_sha != self.evaluation_sha:
                result.errors.append(
                    f"{producer_name}: stale SHA "
                    f"({evidence.manifest.evaluation_sha[:8]} != {self.evaluation_sha[:8]})"
                )
                result.success = False

        if not result.success:
            return result

        # Merge JUnit reports
        junit_reports = []
        for evidence in [vitest_evidence, e2e_evidence]:
            if evidence.junit_report:
                junit_reports.append(evidence.junit_report)

        if junit_reports:
            try:
                merge_result = merge_junit_reports(
                    junit_reports,
                    result.producer_outcomes,
                )
                merged_junit = merge_result.merged_report
                result.vitest_total = merged_junit.total_tests
                result.vitest_passed = (
                    merged_junit.total_tests
                    - merged_junit.total_failures
                    - merged_junit.total_errors
                    - merged_junit.total_skipped
                )
                result.vitest_failed = (
                    merged_junit.total_failures + merged_junit.total_errors
                )
                result.vitest_skipped = merged_junit.total_skipped

                # Write merged JUnit
                merged_junit_xml = self._create_junit_xml(merged_junit)
                result.merged_junit_path = self.output_dir / "junit-frontend.xml"
                result.merged_junit_path.write_text(merged_junit_xml)
            except ValueError as e:
                result.errors.append(f"JUnit merge failed: {e}")
                result.success = False

        # Merge LCOV reports (normalized)
        coverage_reports = []
        coverage_producers = []
        for i, evidence in enumerate([vitest_evidence, e2e_evidence]):
            if evidence.coverage_report:
                coverage_reports.append(evidence.coverage_report)
                coverage_producers.append(["frontend-vitest", "frontend-e2e"][i])

        if coverage_reports:
            try:
                # For frontend, we enforce all four metrics
                merged_coverage = self._merge_lcov_reports(coverage_reports)
                result.coverage_statements = merged_coverage.get_line_percentage()
                result.coverage_branches = merged_coverage.get_branch_percentage()
                result.coverage_functions = merged_coverage.get_function_percentage()
                result.coverage_lines = merged_coverage.get_line_percentage()

                # Check all thresholds
                thresholds = {
                    "statements": result.coverage_statements,
                    "branches": result.coverage_branches,
                    "functions": result.coverage_functions,
                    "lines": result.coverage_lines,
                }
                for metric, value in thresholds.items():
                    # Only check threshold for metrics that have been measured (total > 0)
                    # Skip metrics with zero total as they indicate no data for that metric type
                    if metric == "statements" and merged_coverage.lines_total > 0:
                        if value < self.coverage_threshold:
                            result.errors.append(
                                f"Frontend {metric} coverage {value:.2f}% "
                                f"< threshold {self.coverage_threshold}%"
                            )
                            result.success = False
                    elif metric == "branches" and merged_coverage.branches_total > 0:
                        if value < self.coverage_threshold:
                            result.errors.append(
                                f"Frontend {metric} coverage {value:.2f}% "
                                f"< threshold {self.coverage_threshold}%"
                            )
                            result.success = False
                    elif metric == "functions" and merged_coverage.functions_total > 0:
                        if value < self.coverage_threshold:
                            result.errors.append(
                                f"Frontend {metric} coverage {value:.2f}% "
                                f"< threshold {self.coverage_threshold}%"
                            )
                            result.success = False
                    elif metric == "lines" and merged_coverage.lines_total > 0:
                        if value < self.coverage_threshold:
                            result.errors.append(
                                f"Frontend {metric} coverage {value:.2f}% "
                                f"< threshold {self.coverage_threshold}%"
                            )
                            result.success = False

                # Write merged LCOV
                merged_lcov = self._create_lcov_report(merged_coverage)
                result.merged_lcov_path = self.output_dir / "lcov.info"
                result.merged_lcov_path.write_text(merged_lcov)
            except ValueError as e:
                result.errors.append(f"LCOV merge failed: {e}")
                result.success = False

        # Create evidence manifest
        manifest = EvidenceManifest(
            schema_version=1,
            repository="IdeaFlowAI",
            evaluation_sha=self.evaluation_sha,
            producer="frontend-evidence",
            outcome="success" if result.success else "failure",
            tool_versions={"node": "24", "vitest": "latest", "playwright": "1.60.0"},
            timestamps={"aggregated_at": datetime.utcnow().isoformat()},
        )

        # Add files using absolute paths (add_file handles validation)
        # Store relative paths in manifest records
        if result.merged_junit_path and result.merged_junit_path.exists():
            try:
                manifest.add_file(result.merged_junit_path, "junit")
            except ValueError:
                # Path is absolute, so we add it manually with relative name
                file_record = FileRecord(
                    path=result.merged_junit_path.name,
                    format="junit",
                    bytes=result.merged_junit_path.stat().st_size,
                    sha256=self._compute_file_sha256(result.merged_junit_path),
                )
                manifest.files.append(file_record)

        if result.merged_lcov_path and result.merged_lcov_path.exists():
            try:
                manifest.add_file(result.merged_lcov_path, "lcov")
            except ValueError:
                # Path is absolute, so we add it manually with relative name
                file_record = FileRecord(
                    path=result.merged_lcov_path.name,
                    format="lcov",
                    bytes=result.merged_lcov_path.stat().st_size,
                    sha256=self._compute_file_sha256(result.merged_lcov_path),
                )
                manifest.files.append(file_record)

        manifest.save(self.output_dir / "manifest.json")
        result.manifest_path = self.output_dir / "manifest.json"

        return result

    def _merge_lcov_reports(self, reports: list[CoverageReport]) -> CoverageReport:
        """Merge LCOV reports, normalizing paths."""
        merged = CoverageReport()
        seen_files = set()

        for report in reports:
            # If report has file-level details, use those
            if report.files:
                for filepath, file_cov in report.files.items():
                    # Normalize path to repository-relative
                    normalized_path = self._normalize_path(filepath, "frontend")
                    if normalized_path in seen_files:
                        raise ValueError(
                            f"Duplicate file in coverage: {normalized_path}"
                        )
                    seen_files.add(normalized_path)

                    merged.files[normalized_path] = file_cov
                    merged.lines_covered += file_cov.lines_covered
                    merged.lines_total += file_cov.lines_total
                    merged.branches_covered += file_cov.branches_covered
                    merged.branches_total += file_cov.branches_total
                    merged.functions_covered += file_cov.functions_covered
                    merged.functions_total += file_cov.functions_total
            else:
                # If no file-level details, use report-level totals
                merged.lines_covered += report.lines_covered
                merged.lines_total += report.lines_total
                merged.branches_covered += report.branches_covered
                merged.branches_total += report.branches_total
                merged.functions_covered += report.functions_covered
                merged.functions_total += report.functions_total

        return merged

    def _normalize_path(self, filepath: str, root: str) -> str:
        """Normalize file path to repository-relative format."""
        path = Path(filepath)
        # Remove leading slashes and resolve relative paths
        parts = path.parts
        if root in parts:
            root_idx = parts.index(root)
            return str(Path(*parts[root_idx:]))
        return filepath

    def _create_junit_xml(self, report: JUnitReport) -> str:
        """Create JUnit XML from report."""
        root = ET.Element("testsuites")
        root.set("tests", str(report.total_tests))
        failures = report.total_failures + report.total_errors
        root.set("failures", str(failures))
        root.set("skipped", str(report.total_skipped))
        root.set("time", "0")

        testsuite = ET.SubElement(root, "testsuite")
        testsuite.set("name", "frontend-tests")
        testsuite.set("tests", str(report.total_tests))
        testsuite.set("failures", str(failures))
        testsuite.set("skipped", str(report.total_skipped))
        testsuite.set("time", "0")

        for test_case in report.test_cases:
            tc_elem = ET.SubElement(testsuite, "testcase")
            tc_elem.set("classname", test_case.classname)
            tc_elem.set("name", test_case.name)
            if test_case.time:
                tc_elem.set("time", str(test_case.time))

            if test_case.failure_message:
                failure_elem = ET.SubElement(tc_elem, "failure")
                failure_elem.set("message", test_case.failure_message)
                if test_case.failure_text:
                    failure_elem.text = test_case.failure_text

            if test_case.skipped:
                ET.SubElement(tc_elem, "skipped")

        return ET.tostring(root, encoding="unicode")

    def _create_lcov_report(self, report: CoverageReport) -> str:
        """Create LCOV format report."""
        lines = []
        lines.append("TN:Frontend Coverage")
        lines.append(f"LF:{report.lines_total}")
        lines.append(f"LH:{report.lines_covered}")
        lines.append(f"BRF:{report.branches_total}")
        lines.append(f"BRH:{report.branches_covered}")
        lines.append(f"FN:{report.functions_total}")
        lines.append(f"FNH:{report.functions_covered}")

        for filepath, file_cov in report.files.items():
            lines.append(f"SF:{filepath}")
            lines.append(f"FN:1,{file_cov.functions_total}")
            lines.append(f"FNH:{file_cov.functions_covered}")
            lines.append(f"BRF:{file_cov.branches_total}")
            lines.append(f"BRH:{file_cov.branches_covered}")
            lines.append(f"LF:{file_cov.lines_total}")
            lines.append(f"LH:{file_cov.lines_covered}")
            lines.append("end_of_record")

        return "\n".join(lines)

    @staticmethod
    def _compute_file_sha256(file_path: Path) -> str:
        """Compute SHA-256 hash of a file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()


@dataclass
class CIEvidenceResult:
    """Result of CI-wide evidence aggregation."""

    evaluation_sha: str
    success: bool = False
    backend_success: bool = False
    frontend_success: bool = False
    all_mandatory_signals_success: bool = False
    missing_signals: set[str] = field(default_factory=set)
    failed_signals: set[str] = field(default_factory=set)
    signal_results: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class CIEvidenceAggregator:
    """Aggregates all CI evidence and computes final verdict."""

    def __init__(self, evaluation_sha: str, output_dir: Path):
        """Initialize aggregator.

        Args:
            evaluation_sha: Exact 40-character SHA for this evaluation
            output_dir: Directory for evidence output
        """
        self.evaluation_sha = evaluation_sha
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def aggregate(
        self,
        backend_result: Optional[BackendEvidenceResult],
        frontend_result: Optional[FrontendEvidenceResult],
        other_signal_results: dict[str, SignalResult],
    ) -> CIEvidenceResult:
        """Aggregate all evidence and determine verdict.

        Args:
            backend_result: Aggregated backend evidence
            frontend_result: Aggregated frontend evidence
            other_signal_results: Results from other evaluator jobs

        Returns:
            Final CI evidence result
        """
        result = CIEvidenceResult(
            evaluation_sha=self.evaluation_sha,
            success=True,
            backend_success=True,
            frontend_success=True,
            all_mandatory_signals_success=True,
        )

        # Validate SHA alignment
        if backend_result and backend_result.evaluation_sha != self.evaluation_sha:
            result.errors.append(
                f"Backend SHA mismatch: {backend_result.evaluation_sha[:8]} "
                f"!= {self.evaluation_sha[:8]}"
            )
            result.success = False
        if frontend_result and frontend_result.evaluation_sha != self.evaluation_sha:
            result.errors.append(
                f"Frontend SHA mismatch: {frontend_result.evaluation_sha[:8]} "
                f"!= {self.evaluation_sha[:8]}"
            )
            result.success = False

        # Check backend evidence
        result.backend_success = backend_result.success if backend_result else False
        if not result.backend_success:
            result.errors.append("Backend evidence aggregation failed")
            result.success = False

        # Check frontend evidence
        result.frontend_success = frontend_result.success if frontend_result else False
        if not result.frontend_success:
            result.errors.append("Frontend evidence aggregation failed")
            result.success = False

        # Check other signals
        for signal_name, signal_result in other_signal_results.items():
            result.signal_results[signal_name] = signal_result.state.value
            if signal_result.state != SignalState.SUCCESS:
                result.failed_signals.add(signal_name)
                result.success = False

        # Aggregate
        result.all_mandatory_signals_success = (
            result.backend_success
            and result.frontend_success
            and len(result.failed_signals) == 0
        )

        # Write summary
        summary = {
            "evaluation_sha": self.evaluation_sha,
            "success": result.success,
            "backend_success": result.backend_success,
            "frontend_success": result.frontend_success,
            "signal_results": result.signal_results,
            "errors": result.errors,
            "timestamp": datetime.utcnow().isoformat(),
        }
        summary_path = self.output_dir / "ci-evidence-summary.json"
        summary_path.write_text(json.dumps(summary, indent=2))

        return result
