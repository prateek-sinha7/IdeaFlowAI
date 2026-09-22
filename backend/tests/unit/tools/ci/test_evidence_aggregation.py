"""
Property-Based Tests for Evidence Aggregation.

Validates that evidence aggregators correctly merge producer outputs,
enforce coverage thresholds, validate completeness, and compute verdicts.

**Validates: Requirements 2.5, 2.6, 2.13, 2.14, 3.8, 3.14, 3.15**
"""

import pytest
from hypothesis import given, strategies as st
from pathlib import Path
from datetime import datetime

from tools.ci.evidence_aggregator import (
    BackendEvidenceAggregator,
    FrontendEvidenceAggregator,
    CIEvidenceAggregator,
    ProducerEvidence,
    ProducerOutcome,
    BackendEvidenceResult,
    FrontendEvidenceResult,
)
from tools.ci.evidence_manifest import EvidenceManifest
from tools.ci.report_parsers import JUnitReport, CoverageReport, TestCase, CoverageFile
from tools.ci.aggregate_truth import SignalResult, SignalState


class TestBackendEvidenceAggregator:
    """Test backend evidence aggregation."""

    def test_both_producers_successful_merges_coverage(self, tmp_path):
        """Test merging coverage from successful offline and postgres producers."""
        sha = "a" * 40
        aggregator = BackendEvidenceAggregator(sha, tmp_path)

        # Create offline evidence
        offline_junit = JUnitReport()
        offline_junit.total_tests = 100
        offline_junit.passed_tests = 100
        offline_junit.test_cases = [
            TestCase(f"test_a_{i}", "test_module", f"test_a_{i}", None, False, None)
            for i in range(100)
        ]
        offline_junit.recalculate_totals()

        offline_coverage = CoverageReport()
        offline_coverage.files["backend/app/main.py"] = CoverageFile(
            "backend/app/main.py", 80, 100, 40, 50, 20, 25
        )
        offline_coverage.lines_covered = 80
        offline_coverage.lines_total = 100

        offline_manifest = EvidenceManifest(
            evaluation_sha=sha, producer="backend-offline", outcome="success"
        )
        offline_evidence = ProducerEvidence(
            name="backend-offline",
            outcome=ProducerOutcome.SUCCESS,
            manifest=offline_manifest,
            junit_report=offline_junit,
            coverage_report=offline_coverage,
        )

        # Create postgres evidence
        postgres_junit = JUnitReport()
        postgres_junit.total_tests = 50
        postgres_junit.passed_tests = 50
        postgres_junit.test_cases = [
            TestCase(f"test_pg_{i}", "test_db", f"test_pg_{i}", None, False, None)
            for i in range(50)
        ]
        postgres_junit.recalculate_totals()

        postgres_coverage = CoverageReport()
        postgres_coverage.files["backend/agents/test.py"] = CoverageFile(
            "backend/agents/test.py", 50, 50, 25, 30, 10, 15
        )
        postgres_coverage.lines_covered = 50
        postgres_coverage.lines_total = 50

        postgres_manifest = EvidenceManifest(
            evaluation_sha=sha, producer="backend-postgres", outcome="success"
        )
        postgres_evidence = ProducerEvidence(
            name="backend-postgres",
            outcome=ProducerOutcome.SUCCESS,
            manifest=postgres_manifest,
            junit_report=postgres_junit,
            coverage_report=postgres_coverage,
        )

        # Aggregate
        result = aggregator.aggregate(
            offline_evidence, postgres_evidence, inventory_sha256="inventory_digest"
        )

        assert result.success
        assert result.total_tests == 150
        assert result.passed_tests == 150
        assert result.failed_tests == 0
        assert result.coverage_lines_percent >= 80.0

    def test_failed_producer_makes_aggregate_fail(self, tmp_path):
        """Test that failed producer fails the aggregate."""
        sha = "a" * 40
        aggregator = BackendEvidenceAggregator(sha, tmp_path)

        offline_evidence = ProducerEvidence(
            name="backend-offline",
            outcome=ProducerOutcome.FAILURE,
            errors=["Test execution failed"],
        )

        postgres_evidence = ProducerEvidence(
            name="backend-postgres",
            outcome=ProducerOutcome.SUCCESS,
            manifest=EvidenceManifest(evaluation_sha=sha),
        )

        result = aggregator.aggregate(
            offline_evidence, postgres_evidence, inventory_sha256="digest"
        )

        assert not result.success
        assert len(result.errors) > 0

    def test_stale_sha_fails_aggregate(self, tmp_path):
        """Test that stale SHA fails aggregate."""
        sha = "a" * 40
        stale_sha = "b" * 40
        aggregator = BackendEvidenceAggregator(sha, tmp_path)

        offline_evidence = ProducerEvidence(
            name="backend-offline",
            outcome=ProducerOutcome.SUCCESS,
            manifest=EvidenceManifest(evaluation_sha=stale_sha),
        )

        postgres_evidence = ProducerEvidence(
            name="backend-postgres",
            outcome=ProducerOutcome.SUCCESS,
            manifest=EvidenceManifest(evaluation_sha=sha),
        )

        result = aggregator.aggregate(
            offline_evidence, postgres_evidence, inventory_sha256="digest"
        )

        assert not result.success
        assert any("stale SHA" in error for error in result.errors)

    def test_coverage_below_threshold_fails(self, tmp_path):
        """Test that coverage below threshold fails."""
        sha = "a" * 40
        aggregator = BackendEvidenceAggregator(sha, tmp_path, coverage_threshold=80.0)

        # Create low-coverage reports
        offline_coverage = CoverageReport()
        offline_coverage.files["backend/app/main.py"] = CoverageFile(
            "backend/app/main.py",
            50,
            100,  # 50% coverage
        )
        offline_coverage.lines_covered = 50
        offline_coverage.lines_total = 100

        offline_manifest = EvidenceManifest(evaluation_sha=sha)
        offline_evidence = ProducerEvidence(
            name="backend-offline",
            outcome=ProducerOutcome.SUCCESS,
            manifest=offline_manifest,
            coverage_report=offline_coverage,
        )

        postgres_manifest = EvidenceManifest(evaluation_sha=sha)
        postgres_evidence = ProducerEvidence(
            name="backend-postgres",
            outcome=ProducerOutcome.SUCCESS,
            manifest=postgres_manifest,
        )

        result = aggregator.aggregate(
            offline_evidence, postgres_evidence, inventory_sha256="digest"
        )

        assert not result.success
        assert any("coverage" in error for error in result.errors)

    def test_merged_files_created(self, tmp_path):
        """Test that merged JUnit and coverage files are created."""
        sha = "a" * 40
        aggregator = BackendEvidenceAggregator(sha, tmp_path)

        offline_junit = JUnitReport()
        offline_junit.total_tests = 10
        offline_junit.passed_tests = 10
        offline_junit.test_cases = [
            TestCase("test_a", "mod", "test_a", None, False, None)
        ]
        offline_junit.recalculate_totals()

        offline_coverage = CoverageReport()
        offline_coverage.lines_covered = 90
        offline_coverage.lines_total = 100

        offline_manifest = EvidenceManifest(evaluation_sha=sha)
        offline_evidence = ProducerEvidence(
            name="backend-offline",
            outcome=ProducerOutcome.SUCCESS,
            manifest=offline_manifest,
            junit_report=offline_junit,
            coverage_report=offline_coverage,
        )

        postgres_manifest = EvidenceManifest(evaluation_sha=sha)
        postgres_evidence = ProducerEvidence(
            name="backend-postgres",
            outcome=ProducerOutcome.SUCCESS,
            manifest=postgres_manifest,
        )

        result = aggregator.aggregate(
            offline_evidence, postgres_evidence, inventory_sha256="digest"
        )

        assert result.merged_junit_path is not None
        assert result.merged_junit_path.exists()
        assert result.merged_coverage_path is not None
        assert result.merged_coverage_path.exists()
        assert result.manifest_path is not None
        assert result.manifest_path.exists()


class TestFrontendEvidenceAggregator:
    """Test frontend evidence aggregation."""

    def test_both_producers_successful_merges_all_metrics(self, tmp_path):
        """Test merging Vitest and E2E producers with all coverage metrics."""
        sha = "a" * 40
        aggregator = FrontendEvidenceAggregator(sha, tmp_path)

        # Create Vitest evidence
        vitest_junit = JUnitReport()
        vitest_junit.total_tests = 50
        vitest_junit.passed_tests = 50
        vitest_junit.test_cases = [
            TestCase(f"test_{i}", "component", f"test_{i}", None, False, None)
            for i in range(50)
        ]
        vitest_junit.recalculate_totals()

        vitest_coverage = CoverageReport()
        vitest_coverage.lines_covered = 800
        vitest_coverage.lines_total = 1000
        vitest_coverage.branches_covered = 400
        vitest_coverage.branches_total = 500
        vitest_coverage.functions_covered = 40
        vitest_coverage.functions_total = 50

        vitest_manifest = EvidenceManifest(evaluation_sha=sha)
        vitest_evidence = ProducerEvidence(
            name="frontend-vitest",
            outcome=ProducerOutcome.SUCCESS,
            manifest=vitest_manifest,
            junit_report=vitest_junit,
            coverage_report=vitest_coverage,
        )

        # Create E2E evidence
        e2e_junit = JUnitReport()
        e2e_junit.total_tests = 20
        e2e_junit.passed_tests = 20
        e2e_junit.test_cases = [
            TestCase(f"e2e_{i}", "e2e", f"e2e_{i}", None, False, None)
            for i in range(20)
        ]
        e2e_junit.recalculate_totals()

        e2e_manifest = EvidenceManifest(evaluation_sha=sha)
        e2e_evidence = ProducerEvidence(
            name="frontend-e2e",
            outcome=ProducerOutcome.SUCCESS,
            manifest=e2e_manifest,
            junit_report=e2e_junit,
        )

        result = aggregator.aggregate(vitest_evidence, e2e_evidence)

        assert result.success
        assert result.vitest_total == 70
        assert result.vitest_passed == 70
        assert result.coverage_statements >= 80.0
        assert result.coverage_branches >= 80.0
        assert result.coverage_functions >= 80.0
        assert result.coverage_lines >= 80.0

    def test_missing_vitest_fails(self, tmp_path):
        """Test that missing Vitest producer fails aggregate."""
        sha = "a" * 40
        aggregator = FrontendEvidenceAggregator(sha, tmp_path)

        vitest_evidence = ProducerEvidence(
            name="frontend-vitest",
            outcome=ProducerOutcome.MISSING,
        )

        e2e_evidence = ProducerEvidence(
            name="frontend-e2e",
            outcome=ProducerOutcome.SUCCESS,
            manifest=EvidenceManifest(evaluation_sha=sha),
        )

        result = aggregator.aggregate(vitest_evidence, e2e_evidence)

        assert not result.success

    def test_coverage_metric_boundary_80_percent(self, tmp_path):
        """Test coverage threshold at exact boundary (80.0%)."""
        sha = "a" * 40
        aggregator = FrontendEvidenceAggregator(sha, tmp_path, coverage_threshold=80.0)

        vitest_coverage = CoverageReport()
        vitest_coverage.lines_covered = 800
        vitest_coverage.lines_total = 1000  # Exactly 80.0%

        vitest_evidence = ProducerEvidence(
            name="frontend-vitest",
            outcome=ProducerOutcome.SUCCESS,
            manifest=EvidenceManifest(evaluation_sha=sha),
            coverage_report=vitest_coverage,
        )

        e2e_evidence = ProducerEvidence(
            name="frontend-e2e",
            outcome=ProducerOutcome.SUCCESS,
            manifest=EvidenceManifest(evaluation_sha=sha),
        )

        result = aggregator.aggregate(vitest_evidence, e2e_evidence)

        # 80.0% should pass
        assert result.success

    def test_coverage_metric_boundary_79_99_percent(self, tmp_path):
        """Test coverage threshold just below boundary (79.99%)."""
        sha = "a" * 40
        aggregator = FrontendEvidenceAggregator(sha, tmp_path, coverage_threshold=80.0)

        vitest_coverage = CoverageReport()
        vitest_coverage.lines_covered = 7999
        vitest_coverage.lines_total = 10000  # 79.99%

        vitest_evidence = ProducerEvidence(
            name="frontend-vitest",
            outcome=ProducerOutcome.SUCCESS,
            manifest=EvidenceManifest(evaluation_sha=sha),
            coverage_report=vitest_coverage,
        )

        e2e_evidence = ProducerEvidence(
            name="frontend-e2e",
            outcome=ProducerOutcome.SUCCESS,
            manifest=EvidenceManifest(evaluation_sha=sha),
        )

        result = aggregator.aggregate(vitest_evidence, e2e_evidence)

        # 79.99% should fail
        assert not result.success


class TestCIEvidenceAggregator:
    """Test CI-wide evidence aggregation."""

    def test_successful_backend_and_frontend_succeeds(self, tmp_path):
        """Test that successful backend and frontend aggregation produces success."""
        sha = "a" * 40
        aggregator = CIEvidenceAggregator(sha, tmp_path)

        backend_result = BackendEvidenceResult(
            evaluation_sha=sha, inventory_sha256="backend_inv", success=True
        )

        frontend_result = FrontendEvidenceResult(
            evaluation_sha=sha, success=True, coverage_statements=85.0
        )

        result = aggregator.aggregate(backend_result, frontend_result, {})

        assert result.success
        assert result.backend_success
        assert result.frontend_success

    def test_failed_backend_fails_aggregate(self, tmp_path):
        """Test that failed backend fails the aggregate."""
        sha = "a" * 40
        aggregator = CIEvidenceAggregator(sha, tmp_path)

        backend_result = BackendEvidenceResult(
            evaluation_sha=sha,
            inventory_sha256="backend_inv",
            success=False,
            errors=["Coverage below threshold"],
        )

        frontend_result = FrontendEvidenceResult(
            evaluation_sha=sha, success=True, coverage_statements=85.0
        )

        result = aggregator.aggregate(backend_result, frontend_result, {})

        assert not result.success

    def test_failed_other_signals_fail_aggregate(self, tmp_path):
        """Test that failed other signals fail the aggregate."""
        sha = "a" * 40
        aggregator = CIEvidenceAggregator(sha, tmp_path)

        backend_result = BackendEvidenceResult(
            evaluation_sha=sha, inventory_sha256="backend_inv", success=True
        )

        frontend_result = FrontendEvidenceResult(
            evaluation_sha=sha, success=True, coverage_statements=85.0
        )

        other_signals = {
            "gitleaks": SignalResult(
                "gitleaks", SignalState.FAILURE, sha, datetime.now()
            )
        }

        result = aggregator.aggregate(backend_result, frontend_result, other_signals)

        assert not result.success
        assert "gitleaks" in result.failed_signals

    def test_sha_mismatch_backend_fails(self, tmp_path):
        """Test that SHA mismatch in backend result fails."""
        sha = "a" * 40
        stale_sha = "b" * 40
        aggregator = CIEvidenceAggregator(sha, tmp_path)

        backend_result = BackendEvidenceResult(
            evaluation_sha=stale_sha, inventory_sha256="backend_inv", success=True
        )

        frontend_result = FrontendEvidenceResult(
            evaluation_sha=sha, success=True, coverage_statements=85.0
        )

        result = aggregator.aggregate(backend_result, frontend_result, {})

        assert not result.success
        assert len(result.errors) > 0
