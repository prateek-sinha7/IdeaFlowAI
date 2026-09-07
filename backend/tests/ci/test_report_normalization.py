"""
Tests for report parsing, normalization, and merging.

Tests JUnit, Cobertura, and LCOV parsing with path normalization.

Requirements: 2.5, 2.6, 3.8, 3.14, 3.15
"""

import pytest
from hypothesis import given, strategies as st

from agents.ci.report_parsers import (
    parse_junit,
    parse_cobertura,
    parse_lcov,
    parse_json_report,
    JUnitReport,
    CoverageReport,
    TestCase,
)
from agents.ci.report_merger import (
    merge_junit_reports,
    merge_coverage_reports,
    validate_merged_output,
)


# ===== JUnit Parsing Tests =====


class TestJUnitParsing:
    """Test JUnit XML parsing."""

    def test_parse_valid_junit_single_test(self):
        """Valid JUnit with single test should parse."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="TestSuite" tests="1" failures="0" errors="0" skipped="0">
  <testcase name="test_example" classname="tests.TestClass" time="0.1"/>
</testsuite>
"""
        report = parse_junit(xml)
        assert report.total_tests == 1
        assert report.total_failures == 0
        assert len(report.test_cases) == 1
        assert report.test_cases[0].name == "test_example"

    def test_parse_junit_with_failure(self):
        """JUnit with failure should be parsed."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="TestSuite" tests="1" failures="1" errors="0" skipped="0">
  <testcase name="test_fail" classname="tests.TestClass" time="0.5">
    <failure message="AssertionError"/>
  </testcase>
</testsuite>
"""
        report = parse_junit(xml)
        assert report.total_tests == 1
        assert report.total_failures == 1
        assert report.test_cases[0].failed is True

    def test_parse_junit_with_error(self):
        """JUnit with error should be parsed."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="TestSuite" tests="1" failures="0" errors="1" skipped="0">
  <testcase name="test_error" classname="tests.TestClass" time="0.5">
    <error message="RuntimeError"/>
  </testcase>
</testsuite>
"""
        report = parse_junit(xml)
        assert report.total_tests == 1
        assert report.total_errors == 1
        assert report.test_cases[0].error is True

    def test_parse_junit_with_skipped(self):
        """JUnit with skipped should be parsed."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="TestSuite" tests="1" failures="0" errors="0" skipped="1">
  <testcase name="test_skip" classname="tests.TestClass" time="0">
    <skipped/>
  </testcase>
</testsuite>
"""
        report = parse_junit(xml)
        assert report.total_tests == 1
        assert report.total_skipped == 1
        assert report.test_cases[0].skipped is True

    def test_parse_junit_multiple_suites(self):
        """JUnit with multiple suites should merge."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<testsuites>
  <testsuite name="Suite1" tests="1" failures="0" errors="0" skipped="0">
    <testcase name="test1" classname="TestClass1" time="0.1"/>
  </testsuite>
  <testsuite name="Suite2" tests="1" failures="0" errors="0" skipped="0">
    <testcase name="test2" classname="TestClass2" time="0.2"/>
  </testsuite>
</testsuites>
"""
        report = parse_junit(xml)
        assert report.total_tests == 2
        assert len(report.test_cases) == 2

    def test_parse_junit_empty_content(self):
        """Empty XML should fail."""
        with pytest.raises(ValueError, match="Empty JUnit"):
            parse_junit("")

    def test_parse_junit_invalid_xml(self):
        """Invalid XML should fail."""
        with pytest.raises(ValueError, match="Malformed JUnit"):
            parse_junit("<testsuite><invalid>")

    def test_parse_junit_wrong_root(self):
        """Wrong root element should fail."""
        xml = "<invalidroot></invalidroot>"
        with pytest.raises(ValueError, match="Invalid JUnit root"):
            parse_junit(xml)

    def test_parse_junit_missing_name(self):
        """Test case without name should fail."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="TestSuite" tests="1" failures="0" errors="0" skipped="0">
  <testcase classname="tests.TestClass" time="0.1"/>
</testsuite>
"""
        with pytest.raises(ValueError, match="missing 'name'"):
            parse_junit(xml)

    def test_parse_junit_invalid_time(self):
        """Invalid time value should fail."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="TestSuite" tests="1" failures="0" errors="0" skipped="0">
  <testcase name="test" classname="TestClass" time="not_a_number"/>
</testsuite>
"""
        with pytest.raises(ValueError, match="Invalid time"):
            parse_junit(xml)


# ===== Cobertura Parsing Tests =====


class TestCoberturaParsingAndNormalization:
    """Test Cobertura XML parsing with path normalization."""

    def test_parse_valid_cobertura(self):
        """Valid Cobertura should parse."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<coverage version="1.0">
  <packages>
    <package>
      <classes>
        <class name="MyClass" filename="backend/src/main.py"
               lines-valid="10" lines-covered="8"
               branches-valid="5" branches-covered="4"/>
      </classes>
    </package>
  </packages>
</coverage>
"""
        report = parse_cobertura(xml)
        assert len(report.files) == 1
        assert report.lines_total == 10
        assert report.lines_covered == 8
        assert report.branches_total == 5
        assert report.branches_covered == 4

    def test_parse_cobertura_path_normalization(self):
        """Cobertura paths should be normalized."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<coverage version="1.0">
  <packages>
    <package>
      <classes>
        <class name="MyClass" filename="./backend/src/main.py"
               lines-valid="10" lines-covered="8"
               branches-valid="0" branches-covered="0"/>
      </classes>
    </package>
  </packages>
</coverage>
"""
        report = parse_cobertura(xml)
        # Path should be normalized without leading ./
        assert "backend/src/main.py" in report.files

    def test_parse_cobertura_absolute_path_rejected(self):
        """Absolute paths in Cobertura should be rejected."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<coverage version="1.0">
  <packages>
    <package>
      <classes>
        <class name="MyClass" filename="/etc/passwd"
               lines-valid="10" lines-covered="8"
               branches-valid="0" branches-covered="0"/>
      </classes>
    </package>
  </packages>
</coverage>
"""
        with pytest.raises(ValueError, match="Unsafe path"):
            parse_cobertura(xml)

    def test_parse_cobertura_traversal_rejected(self):
        """Traversal paths in Cobertura should be rejected."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<coverage version="1.0">
  <packages>
    <package>
      <classes>
        <class name="MyClass" filename="../../etc/passwd"
               lines-valid="10" lines-covered="8"
               branches-valid="0" branches-covered="0"/>
      </classes>
    </package>
  </packages>
</coverage>
"""
        with pytest.raises(ValueError, match="Unsafe path"):
            parse_cobertura(xml)

    def test_parse_cobertura_empty(self):
        """Empty Cobertura should fail."""
        with pytest.raises(ValueError, match="Empty Cobertura"):
            parse_cobertura("")

    def test_parse_cobertura_invalid_xml(self):
        """Invalid XML should fail."""
        with pytest.raises(ValueError, match="Malformed Cobertura"):
            parse_cobertura("<coverage><broken>")


# ===== LCOV Parsing Tests =====


class TestLcovParsingAndNormalization:
    """Test LCOV parsing with path normalization."""

    def test_parse_valid_lcov(self):
        """Valid LCOV should parse."""
        lcov = """TN:Test Suite
SF:frontend/src/component.ts
FN:10,myFunction
FNDA:2,myFunction
FNH:1
FNF:1
DA:10,1
DA:11,1
DA:12,0
LH:2
LF:3
BRH:2
BRF:4
end_of_record
"""
        report = parse_lcov(lcov)
        assert len(report.files) == 1
        assert report.lines_total == 3
        assert report.lines_covered == 2

    def test_parse_lcov_multiple_files(self):
        """LCOV with multiple files should parse."""
        lcov = """SF:frontend/src/component1.ts
DA:1,1
DA:2,0
LH:1
LF:2
end_of_record
SF:frontend/src/component2.ts
DA:1,1
LH:1
LF:1
end_of_record
"""
        report = parse_lcov(lcov)
        assert len(report.files) == 2
        assert report.lines_total == 3
        assert report.lines_covered == 2

    def test_parse_lcov_path_normalization(self):
        """LCOV paths should be normalized."""
        lcov = """SF:./frontend/src/component.ts
DA:1,1
LH:1
LF:1
end_of_record
"""
        report = parse_lcov(lcov)
        # Path should be normalized
        assert len(report.files) == 1

    def test_parse_lcov_windows_separators(self):
        """LCOV with Windows separators should be normalized."""
        lcov = r"""SF:frontend\src\component.ts
DA:1,1
LH:1
LF:1
end_of_record
"""
        report = parse_lcov(lcov)
        assert len(report.files) == 1

    def test_parse_lcov_absolute_path_rejected(self):
        """Absolute paths in LCOV should be rejected."""
        lcov = """SF:/etc/passwd
DA:1,1
LH:1
LF:1
end_of_record
"""
        with pytest.raises(ValueError, match="Unsafe path"):
            parse_lcov(lcov)

    def test_parse_lcov_traversal_rejected(self):
        """Traversal in LCOV should be rejected."""
        lcov = """SF:../../etc/passwd
DA:1,1
LH:1
LF:1
end_of_record
"""
        with pytest.raises(ValueError, match="Unsafe path"):
            parse_lcov(lcov)

    def test_parse_lcov_empty(self):
        """Empty LCOV should fail."""
        with pytest.raises(ValueError, match="Empty LCOV"):
            parse_lcov("")

    def test_parse_lcov_invalid_format(self):
        """Invalid LCOV format (no files) should result in empty report."""
        lcov = """this is not valid lcov format
but no SF lines"""
        report = parse_lcov(lcov)
        # Lines without colons are silently skipped, so this will result in empty report
        assert len(report.files) == 0

    def test_parse_lcov_da_without_sf(self):
        """DA record without SF should fail."""
        lcov = """DA:1,1
LH:1
LF:1
end_of_record
"""
        with pytest.raises(ValueError, match="without SF"):
            parse_lcov(lcov)

    def test_parse_lcov_duplicate_line(self):
        """Duplicate line number should be rejected."""
        lcov = """SF:frontend/src/component.ts
DA:1,1
DA:1,0
LH:1
LF:2
end_of_record
"""
        with pytest.raises(ValueError, match="Duplicate line"):
            parse_lcov(lcov)


# ===== JSON Parsing Tests =====


class TestJsonReporting:
    """Test JSON report parsing."""

    def test_parse_valid_json(self):
        """Valid JSON should parse."""
        json_str = '{"name": "test", "count": 42}'
        result = parse_json_report(json_str)
        assert result["name"] == "test"
        assert result["count"] == 42

    def test_parse_json_with_schema(self):
        """JSON with schema validation should pass if valid."""
        json_str = '{"name": "test", "count": 42}'
        schema = {"required": ["name", "count"]}
        result = parse_json_report(json_str, schema)
        assert result["name"] == "test"

    def test_parse_json_missing_required_field(self):
        """JSON missing required field should fail."""
        json_str = '{"name": "test"}'
        schema = {"required": ["name", "count"]}
        with pytest.raises(ValueError, match="Required key missing"):
            parse_json_report(json_str, schema)

    def test_parse_json_invalid(self):
        """Invalid JSON should fail."""
        with pytest.raises(ValueError, match="Malformed JSON"):
            parse_json_report("{invalid json}")

    def test_parse_json_empty(self):
        """Empty JSON should fail."""
        with pytest.raises(ValueError, match="Empty JSON"):
            parse_json_report("")


# ===== Report Merging Tests =====


class TestJUnitMerging:
    """Test JUnit report merging."""

    def test_merge_junit_single_report(self):
        """Merging single report should work."""
        report1 = JUnitReport()
        report1.test_cases = [
            TestCase(name="test1", classname="Class1"),
            TestCase(name="test2", classname="Class2"),
        ]
        report1.recalculate_totals()

        result = merge_junit_reports([report1], {"producer1": "success"})
        assert result.producer_count == 1
        assert len(result.merged_report.test_cases) == 2

    def test_merge_junit_multiple_reports(self):
        """Merging multiple reports should combine tests."""
        report1 = JUnitReport()
        report1.test_cases = [TestCase(name="test1", classname="Class1")]
        report1.recalculate_totals()

        report2 = JUnitReport()
        report2.test_cases = [TestCase(name="test2", classname="Class2")]
        report2.recalculate_totals()

        result = merge_junit_reports(
            [report1, report2],
            {"producer1": "success", "producer2": "success"},
        )
        assert result.producer_count == 2
        assert len(result.merged_report.test_cases) == 2

    def test_merge_junit_duplicate_test(self):
        """Duplicate test cases should error."""
        report1 = JUnitReport()
        report1.test_cases = [TestCase(name="test", classname="Class")]
        report1.recalculate_totals()

        report2 = JUnitReport()
        report2.test_cases = [TestCase(name="test", classname="Class")]
        report2.recalculate_totals()

        with pytest.raises(ValueError, match="Merge errors"):
            merge_junit_reports(
                [report1, report2],
                {"producer1": "success", "producer2": "success"},
            )

    def test_merge_junit_empty_list(self):
        """Merging empty list should fail."""
        with pytest.raises(ValueError, match="Cannot merge empty"):
            merge_junit_reports([], {})


# ===== Coverage Merging Tests =====


class TestCoverageMerging:
    """Test coverage report merging."""

    def test_merge_coverage_single_report(self):
        """Merging single coverage report should work."""
        from agents.ci.report_parsers import CoverageFile

        report = CoverageReport()
        report.files["file1.py"] = CoverageFile(
            path="file1.py", lines_covered=10, lines_total=20
        )
        report.lines_covered = 10
        report.lines_total = 20

        result = merge_coverage_reports([report], ["producer1"])
        assert result.producer_count == 1
        assert len(result.merged_report.files) == 1

    def test_merge_coverage_duplicate_file(self):
        """Duplicate files in coverage should error."""
        from agents.ci.report_parsers import CoverageFile

        report1 = CoverageReport()
        report1.files["file.py"] = CoverageFile(
            path="file.py", lines_covered=10, lines_total=20
        )

        report2 = CoverageReport()
        report2.files["file.py"] = CoverageFile(
            path="file.py", lines_covered=5, lines_total=15
        )

        with pytest.raises(ValueError, match="Merge errors"):
            merge_coverage_reports([report1, report2], ["producer1", "producer2"])


# ===== Merged Output Validation Tests =====


def test_validate_merged_junit_output():
    """Validation should accept valid JUnit output."""
    report = JUnitReport(total_tests=10)
    report.test_cases = [
        TestCase(name=f"test{i}", classname="Class") for i in range(10)
    ]

    errors = validate_merged_output(report, expected_count=10)
    assert errors == []


def test_validate_merged_junit_count_mismatch():
    """Validation should fail on count mismatch."""
    report = JUnitReport(total_tests=10)
    report.test_cases = [
        TestCase(name=f"test{i}", classname="Class") for i in range(10)
    ]

    errors = validate_merged_output(report, expected_count=20)
    assert any("count" in err.lower() for err in errors)
