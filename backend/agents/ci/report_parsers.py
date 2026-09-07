"""
Safe Parsers for CI Reports.

Provides strict parsers for JUnit, Cobertura, LCOV, and JSON reports that
fail on first error and preserve data integrity.

Requirements: 2.5, 2.6, 3.8, 3.14, 3.15
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring as safe_fromstring
from typing import Optional, Any

from .evidence_manifest import normalize_path


@dataclass
class TestCase:
    """Representation of a test case."""

    name: str
    classname: str
    time: float = 0.0
    file: Optional[str] = None
    failed: bool = False
    error: bool = False
    skipped: bool = False
    failure_message: str = ""
    error_message: str = ""


@dataclass
class JUnitReport:
    """Parsed JUnit report."""

    test_cases: list[TestCase] = field(default_factory=list)
    total_tests: int = 0
    total_failures: int = 0
    total_errors: int = 0
    total_skipped: int = 0

    def recalculate_totals(self) -> None:
        """Recalculate totals from test cases."""
        self.total_tests = len(self.test_cases)
        self.total_failures = sum(1 for tc in self.test_cases if tc.failed)
        self.total_errors = sum(1 for tc in self.test_cases if tc.error)
        self.total_skipped = sum(1 for tc in self.test_cases if tc.skipped)


@dataclass
class CoverageFile:
    """Coverage for a single file."""

    path: str
    lines_covered: int = 0
    lines_total: int = 0
    branches_covered: int = 0
    branches_total: int = 0
    functions_covered: int = 0
    functions_total: int = 0


@dataclass
class CoverageReport:
    """Parsed coverage report."""

    files: dict[str, CoverageFile] = field(default_factory=dict)
    lines_covered: int = 0
    lines_total: int = 0
    branches_covered: int = 0
    branches_total: int = 0
    functions_covered: int = 0
    functions_total: int = 0

    def get_line_percentage(self) -> float:
        """Get line coverage percentage."""
        if self.lines_total == 0:
            return 0.0
        return (self.lines_covered / self.lines_total) * 100

    def get_branch_percentage(self) -> float:
        """Get branch coverage percentage."""
        if self.branches_total == 0:
            return 0.0
        return (self.branches_covered / self.branches_total) * 100

    def get_function_percentage(self) -> float:
        """Get function coverage percentage."""
        if self.functions_total == 0:
            return 0.0
        return (self.functions_covered / self.functions_total) * 100


def parse_junit(xml_content: str) -> JUnitReport:
    """
    Parse JUnit XML report.

    Strict parsing that fails on first error. Validates XML structure and
    extracts test case information.

    Args:
        xml_content: Raw XML content

    Returns:
        Parsed JUnit report

    Raises:
        ValueError: If XML is malformed or required fields are missing
    """
    if not xml_content or not xml_content.strip():
        raise ValueError("Empty JUnit XML content")

    try:
        # defusedxml for READING: entity-expansion and external-entity
        # constructs are rejected rather than resolved (bandit B314). A
        # rejected document surfaces as the same ValueError as malformed XML,
        # so every caller keeps its single failure path.
        root = safe_fromstring(xml_content)
    except (ET.ParseError, DefusedXmlException) as e:
        raise ValueError(f"Malformed JUnit XML: {e}")

    # Root should be testsuites or testsuite
    if root.tag not in ("testsuites", "testsuite"):
        raise ValueError(f"Invalid JUnit root element: {root.tag}")

    report = JUnitReport()

    # Find all testsuite elements
    testsuites = root.findall(".//testsuite")
    if not testsuites:
        testsuites = [root] if root.tag == "testsuite" else []

    # If root is testsuites, look for direct children
    if root.tag == "testsuites":
        testsuites = root.findall("testsuite")

    # Extract test cases
    for testsuite in testsuites:
        for testcase in testsuite.findall("testcase"):
            name = testcase.get("name")
            if not name:
                raise ValueError("Test case missing 'name' attribute")

            classname = testcase.get("classname", "")
            time_str = testcase.get("time", "0")
            file_attr = testcase.get("file")

            try:
                time_val = float(time_str)
            except ValueError:
                raise ValueError(f"Invalid time value: {time_str}")

            tc = TestCase(
                name=name,
                classname=classname,
                time=time_val,
                file=file_attr,
            )

            # Check for failure, error, skipped
            if testcase.find("failure") is not None:
                tc.failed = True
                failure_elem = testcase.find("failure")
                if failure_elem is not None:
                    tc.failure_message = failure_elem.get("message", "")

            if testcase.find("error") is not None:
                tc.error = True
                error_elem = testcase.find("error")
                if error_elem is not None:
                    tc.error_message = error_elem.get("message", "")

            if testcase.find("skipped") is not None:
                tc.skipped = True

            report.test_cases.append(tc)

    report.recalculate_totals()
    return report


def parse_cobertura(xml_content: str) -> CoverageReport:
    """
    Parse Cobertura XML coverage report.

    Strict parsing with path normalization. Rejects absolute paths and
    normalizes to repository-relative paths.

    Args:
        xml_content: Raw Cobertura XML content

    Returns:
        Parsed coverage report

    Raises:
        ValueError: If XML is malformed or paths are unsafe
    """
    if not xml_content or not xml_content.strip():
        raise ValueError("Empty Cobertura XML content")

    try:
        root = safe_fromstring(xml_content)
    except (ET.ParseError, DefusedXmlException) as e:
        raise ValueError(f"Malformed Cobertura XML: {e}")

    if root.tag != "coverage":
        raise ValueError(f"Invalid Cobertura root element: {root.tag}")

    report = CoverageReport()

    # Parse packages and classes
    for package in root.findall(".//package"):
        for cls in package.findall("classes/class"):
            filename = cls.get("filename")
            if not filename:
                raise ValueError("Class missing 'filename' attribute")

            # Normalize path
            try:
                normalized_path = normalize_path(filename, root="backend")
            except ValueError as e:
                raise ValueError(f"Unsafe path in Cobertura: {e}")

            # Parse line/branch coverage
            lines_total = int(cls.get("lines-valid", "0"))
            lines_covered = int(cls.get("lines-covered", "0"))
            branches_total = int(cls.get("branches-valid", "0"))
            branches_covered = int(cls.get("branches-covered", "0"))

            cov_file = CoverageFile(
                path=normalized_path,
                lines_covered=lines_covered,
                lines_total=lines_total,
                branches_covered=branches_covered,
                branches_total=branches_total,
            )

            report.files[normalized_path] = cov_file
            report.lines_covered += lines_covered
            report.lines_total += lines_total
            report.branches_covered += branches_covered
            report.branches_total += branches_total

    return report


def parse_lcov(lcov_content: str) -> CoverageReport:
    """
    Parse LCOV coverage report.

    Strict parsing with path normalization. Rejects absolute paths, traversal,
    and symlinks. Preserves repository-relative paths.

    Args:
        lcov_content: Raw LCOV content

    Returns:
        Parsed coverage report

    Raises:
        ValueError: If format is invalid or paths are unsafe
    """
    if not lcov_content or not lcov_content.strip():
        raise ValueError("Empty LCOV content")

    report = CoverageReport()
    current_file: Optional[str] = None
    current_lines_covered = 0
    current_lines_total = 0
    current_branches_covered = 0
    current_branches_total = 0

    lines_seen: set[int] = set()

    for line_num, line in enumerate(lcov_content.split("\n"), 1):
        line = line.rstrip("\n\r")
        if not line or line.startswith("#"):
            continue

        # Split only on first colon for key:value format
        if ":" in line:
            parts = line.split(":", 1)
            key = parts[0]
            value = parts[1] if len(parts) > 1 else ""
        else:
            # Handle keywords without colons like "end_of_record"
            key = line
            value = ""

        if key == "SF":  # Source file
            # Save previous file if any
            if current_file:
                cov_file = CoverageFile(
                    path=current_file,
                    lines_covered=current_lines_covered,
                    lines_total=current_lines_total,
                    branches_covered=current_branches_covered,
                    branches_total=current_branches_total,
                )
                report.files[current_file] = cov_file

            # Normalize path
            try:
                normalized_path = normalize_path(value, root="frontend")
            except ValueError as e:
                raise ValueError(f"Unsafe path in LCOV: {e}")

            current_file = normalized_path
            current_lines_covered = 0
            current_lines_total = 0
            current_branches_covered = 0
            current_branches_total = 0
            lines_seen.clear()

        elif key == "DA":  # Line coverage
            if not current_file:
                raise ValueError(f"DA record without SF at line {line_num}")

            try:
                line_no, execution_count = value.split(",")
                line_no = int(line_no)
                execution_count = int(execution_count)
            except (ValueError, IndexError):
                raise ValueError(f"Invalid DA record at line {line_num}: {value}")

            if line_no in lines_seen:
                raise ValueError(f"Duplicate line number {line_no} in LCOV")

            lines_seen.add(line_no)
            current_lines_total += 1
            if execution_count > 0:
                current_lines_covered += 1

        elif key == "BRH":  # Branch hit
            current_branches_covered += int(value)

        elif key == "BRF":  # Branch found
            current_branches_total += int(value)

        elif key == "end_of_record":
            if current_file:
                cov_file = CoverageFile(
                    path=current_file,
                    lines_covered=current_lines_covered,
                    lines_total=current_lines_total,
                    branches_covered=current_branches_covered,
                    branches_total=current_branches_total,
                )
                report.files[current_file] = cov_file
                report.lines_covered += current_lines_covered
                report.lines_total += current_lines_total
                report.branches_covered += current_branches_covered
                report.branches_total += current_branches_total

            current_file = None
            current_lines_covered = 0
            current_lines_total = 0
            current_branches_covered = 0
            current_branches_total = 0
            lines_seen.clear()

    # Handle any remaining file
    if current_file:
        cov_file = CoverageFile(
            path=current_file,
            lines_covered=current_lines_covered,
            lines_total=current_lines_total,
            branches_covered=current_branches_covered,
            branches_total=current_branches_total,
        )
        report.files[current_file] = cov_file
        report.lines_covered += current_lines_covered
        report.lines_total += current_lines_total
        report.branches_covered += current_branches_covered
        report.branches_total += current_branches_total

    return report


def parse_json_report(
    json_content: str, schema: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    """
    Parse JSON report with schema validation.

    Strict parsing that fails on malformed JSON or schema violations.

    Args:
        json_content: Raw JSON content
        schema: Optional schema dict for validation

    Returns:
        Parsed JSON object

    Raises:
        ValueError: If JSON is malformed or schema validation fails
    """
    if not json_content or not json_content.strip():
        raise ValueError("Empty JSON content")

    try:
        data = json.loads(json_content)
    except json.JSONDecodeError as e:
        raise ValueError(f"Malformed JSON: {e}")

    # Basic schema validation if provided
    if schema:
        required_keys = schema.get("required", [])
        for key in required_keys:
            if key not in data:
                raise ValueError(f"Required key missing in JSON: {key}")

    return data
