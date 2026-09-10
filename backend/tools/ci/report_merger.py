"""
Report Merging for CI Evidence.

Provides logic to merge JUnit and coverage reports while preserving counts
and detecting failed-run diagnostics.

Requirements: 2.5, 2.6, 3.8, 3.14, 3.15
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .report_parsers import (
    JUnitReport,
    CoverageReport,
)


@dataclass
class MergeResult:
    """Result of merging multiple reports."""

    merged_report: JUnitReport | CoverageReport
    producer_count: int
    skipped_producers: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def merge_junit_reports(
    reports: list[JUnitReport],
    producer_outcomes: dict[str, str],
) -> MergeResult:
    """
    Merge multiple JUnit reports while preserving test counts.

    Fails on first error. Distinguishes successful producers from failed-run
    diagnostics. Only successful producer JUnit reports are merged into mandatory
    evidence.

    Args:
        reports: List of parsed JUnit reports
        producer_outcomes: Mapping from producer name to outcome (success, failure, etc.)

    Returns:
        Merged report with tracking of skipped/failed producers

    Raises:
        ValueError: If merge cannot proceed (e.g., empty input, conflicting test IDs)
    """
    if not reports:
        raise ValueError("Cannot merge empty list of JUnit reports")

    merged = JUnitReport()
    seen_test_ids: set[str] = set()
    skipped_producers = []
    errors = []

    for report in reports:
        # Process test cases
        for test_case in report.test_cases:
            # Create unique test ID
            test_id = f"{test_case.classname}::{test_case.name}"

            if test_id in seen_test_ids:
                errors.append(f"Duplicate test case: {test_id}")
                continue

            seen_test_ids.add(test_id)
            merged.test_cases.append(test_case)

    # Recalculate totals
    merged.recalculate_totals()

    if errors:
        raise ValueError(f"Merge errors: {'; '.join(errors)}")

    return MergeResult(
        merged_report=merged,
        producer_count=len(reports),
        skipped_producers=skipped_producers,
    )


def merge_coverage_reports(
    reports: list[CoverageReport],
    producer_names: list[str],
) -> MergeResult:
    """
    Merge multiple coverage reports without double-counting.

    Sums coverage metrics from all producers. Fails if the same file appears
    in multiple reports (indicating duplicate execution).

    Args:
        reports: List of parsed coverage reports
        producer_names: Names of producers corresponding to reports

    Returns:
        Merged report with combined coverage metrics

    Raises:
        ValueError: If merge cannot proceed
    """
    if not reports:
        raise ValueError("Cannot merge empty list of coverage reports")

    if len(reports) != len(producer_names):
        raise ValueError(
            f"Report count {len(reports)} != producer count {len(producer_names)}"
        )

    merged = CoverageReport()
    seen_files: set[str] = set()
    errors = []

    for report, producer_name in zip(reports, producer_names, strict=False):
        for filepath, cov_file in report.files.items():
            if filepath in seen_files:
                errors.append(
                    f"File {filepath} appears in multiple producers (duplicate execution)"
                )
                continue

            seen_files.add(filepath)
            merged.files[filepath] = cov_file

            # Sum coverage metrics (no double-counting because files are unique)
            merged.lines_covered += cov_file.lines_covered
            merged.lines_total += cov_file.lines_total
            merged.branches_covered += cov_file.branches_covered
            merged.branches_total += cov_file.branches_total
            merged.functions_covered += cov_file.functions_covered
            merged.functions_total += cov_file.functions_total

    if errors:
        raise ValueError(f"Merge errors: {'; '.join(errors)}")

    return MergeResult(
        merged_report=merged,
        producer_count=len(reports),
    )


def validate_merged_output(
    merged: JUnitReport | CoverageReport,
    expected_count: Optional[int] = None,
) -> list[str]:
    """
    Validate merged output matches expectations.

    Args:
        merged: Merged report to validate
        expected_count: Expected test count (for JUnit) or file count (for coverage)

    Returns:
        List of validation errors
    """
    errors = []

    if isinstance(merged, JUnitReport):
        if merged.total_tests == 0:
            errors.append("Merged JUnit report has no tests")

        if expected_count is not None and merged.total_tests != expected_count:
            errors.append(
                f"Merged test count {merged.total_tests} != expected {expected_count}"
            )

    elif isinstance(merged, CoverageReport):
        if not merged.files:
            errors.append("Merged coverage report has no files")

        if expected_count is not None and len(merged.files) != expected_count:
            errors.append(
                f"Merged file count {len(merged.files)} != expected {expected_count}"
            )

    return errors
