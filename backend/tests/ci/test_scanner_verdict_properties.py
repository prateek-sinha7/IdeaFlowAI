"""
Property-based tests for scanner verdict parsing and policy.

**Validates: Requirements 2.8, 2.9, 3.9, 3.15**
"""

import json
from typing import Any, Dict, List, Optional

import pytest
from hypothesis import given, settings, strategies as st, assume

from agents.ci.scanner_parsers import (
    parse_pip_audit_json,
    parse_npm_audit_json,
    parse_trivy_json,
    parse_grype_json,
    parse_checkov_json,
    parse_gitleaks_json,
    ParserError,
)
from agents.ci.scanner_policy import (
    ZeroHighCriticalPolicy,
    merge_verdicts,
    validate_no_severity_exceptions,
)
from agents.ci.scanner_verdict import (
    Finding,
    ScannerVerdict,
    SeverityLevel,
    map_severity,
)


# ============================================================================
# Strategies for Hypothesis property-based testing
# ============================================================================


def severity_strategy() -> st.SearchStrategy[SeverityLevel]:
    """Generate valid severity levels."""
    return st.sampled_from(list(SeverityLevel))


def finding_strategy() -> st.SearchStrategy[Finding]:
    """Generate valid findings."""
    return st.builds(
        Finding,
        id=st.text(min_size=1, max_size=50),
        severity=severity_strategy(),
        description=st.text(max_size=200),
        path=st.text(max_size=100),
        scanner=st.sampled_from(
            ["pip-audit", "npm", "trivy", "grype", "checkov", "gitleaks"]
        ),
    )


# ============================================================================
# Test severity mapping
# ============================================================================


class TestSeverityMapping:
    """Test severity classification across scanners."""

    @given(scanner=st.text(), raw_severity=st.text())
    @settings(max_examples=100)
    def test_severity_mapping_normalization(self, scanner: str, raw_severity: str):
        """Test that valid severities normalize correctly."""
        valid_severities = [
            "critical",
            "high",
            "medium",
            "low",
            "info",
            "CRITICAL",
            "HIGH",
        ]

        if raw_severity in valid_severities:
            result = map_severity(scanner, raw_severity)
            assert isinstance(result, SeverityLevel)
            assert result in list(SeverityLevel)

    def test_severity_is_blocking(self):
        """Test blocking severity classification."""
        assert SeverityLevel.CRITICAL.is_blocking()
        assert SeverityLevel.HIGH.is_blocking()
        assert not SeverityLevel.MEDIUM.is_blocking()
        assert not SeverityLevel.LOW.is_blocking()
        assert not SeverityLevel.INFO.is_blocking()


# ============================================================================
# pip-audit parser tests
# ============================================================================


class TestPipAuditParser:
    """Test pip-audit JSON parser."""

    def test_empty_report_failure(self):
        """Empty report should fail."""
        verdict = parse_pip_audit_json("")
        assert not verdict.success
        assert "Empty" in verdict.error

    def test_malformed_json_failure(self):
        """Malformed JSON should fail."""
        verdict = parse_pip_audit_json("{invalid json")
        assert not verdict.success
        assert "Malformed" in verdict.error or "JSON" in verdict.error

    def test_missing_vulnerabilities_field_failure(self):
        """Report missing vulnerabilities field should fail."""
        verdict = parse_pip_audit_json(json.dumps({"scanned_file": "requirements.txt"}))
        assert not verdict.success
        assert "vulnerabilities" in verdict.error.lower()

    def test_empty_vulnerabilities_array_success(self):
        """Report with empty vulnerabilities should succeed."""
        report = json.dumps(
            {
                "vulnerabilities": [],
                "scanned_file": "requirements.txt",
            }
        )
        verdict = parse_pip_audit_json(report)
        assert verdict.success
        assert len(verdict.findings) == 0
        assert verdict.high_count == 0
        assert verdict.critical_count == 0

    @given(findings_count=st.integers(min_value=1, max_value=5))
    def test_high_critical_findings_block(self, findings_count: int):
        """Any HIGH or CRITICAL finding should block the verdict."""
        vulnerabilities = []
        for i in range(findings_count):
            vulnerabilities.append(
                {
                    "id": f"CVE-2024-{i:05d}",
                    "description": f"Vuln {i}",
                    "service": f"package-{i}",
                    "cvss_v3_score": 9.0,  # CRITICAL
                    "fix_available": False,
                }
            )

        report = json.dumps(
            {
                "vulnerabilities": vulnerabilities,
                "scanned_file": "requirements.txt",
            }
        )
        verdict = parse_pip_audit_json(report)

        assert not verdict.success
        assert verdict.critical_count == findings_count
        assert verdict.has_blocking_findings()

    def test_cvss_score_mapping(self):
        """Test CVSS score to severity mapping."""
        test_cases = [
            (9.5, SeverityLevel.CRITICAL),  # 9.0+
            (8.5, SeverityLevel.HIGH),  # 7.0-8.9
            (5.0, SeverityLevel.MEDIUM),  # 4.0-6.9
            (2.0, SeverityLevel.LOW),  # <4.0
        ]

        for cvss, expected_severity in test_cases:
            report = json.dumps(
                {
                    "vulnerabilities": [
                        {
                            "id": "CVE-2024-test",
                            "description": "Test",
                            "service": "test-pkg",
                            "cvss_v3_score": cvss,
                        }
                    ],
                    "scanned_file": "requirements.txt",
                }
            )
            verdict = parse_pip_audit_json(report)
            assert len(verdict.findings) == 1
            assert verdict.findings[0].severity == expected_severity

    def test_missing_id_field_failure(self):
        """Vulnerability without ID should fail."""
        report = json.dumps(
            {
                "vulnerabilities": [
                    {
                        "description": "No ID",
                        "service": "test",
                    }
                ],
                "scanned_file": "requirements.txt",
            }
        )
        verdict = parse_pip_audit_json(report)
        assert not verdict.success
        assert "id" in verdict.error.lower()


# ============================================================================
# npm audit parser tests
# ============================================================================


class TestNpmAuditParser:
    """Test npm audit JSON parser."""

    def test_empty_report_failure(self):
        """Empty report should fail."""
        verdict = parse_npm_audit_json("")
        assert not verdict.success

    def test_malformed_json_failure(self):
        """Malformed JSON should fail."""
        verdict = parse_npm_audit_json("{invalid}")
        assert not verdict.success

    def test_empty_vulnerabilities_success(self):
        """Empty vulnerabilities object should succeed."""
        report = json.dumps(
            {
                "vulnerabilities": {},
                "metadata": {"vulnerabilities": {"high": 0, "critical": 0}},
            }
        )
        verdict = parse_npm_audit_json(report)
        assert verdict.success
        assert len(verdict.findings) == 0

    @given(severity=st.sampled_from(["critical", "high", "moderate", "low"]))
    def test_severity_classification(self, severity: str):
        """Test that severity is correctly classified."""
        report = json.dumps(
            {
                "vulnerabilities": {
                    "test-pkg": {
                        "severity": severity,
                        "vulnerabilities": [],
                    }
                },
                "metadata": {"vulnerabilities": {}},
            }
        )
        verdict = parse_npm_audit_json(report)

        if severity in ("critical", "high"):
            assert not verdict.success
            assert verdict.has_blocking_findings()
        else:
            assert verdict.success

    def test_high_critical_block_verdict(self):
        """HIGH and CRITICAL findings should block verdict."""
        report = json.dumps(
            {
                "vulnerabilities": {
                    "pkg-high": {
                        "severity": "high",
                        "vulnerabilities": [],
                    },
                    "pkg-crit": {
                        "severity": "critical",
                        "vulnerabilities": [],
                    },
                },
                "metadata": {"vulnerabilities": {}},
            }
        )
        verdict = parse_npm_audit_json(report)

        assert not verdict.success
        assert verdict.high_count == 1
        assert verdict.critical_count == 1
        assert verdict.blocking_count == 2


# ============================================================================
# Trivy parser tests
# ============================================================================


class TestTrivyParser:
    """Test Trivy JSON parser."""

    def test_empty_report_failure(self):
        """Empty report should fail."""
        verdict = parse_trivy_json("")
        assert not verdict.success

    def test_malformed_json_failure(self):
        """Malformed JSON should fail."""
        verdict = parse_trivy_json("{bad}")
        assert not verdict.success

    def test_empty_results_success(self):
        """Empty results should succeed."""
        report = json.dumps(
            {
                "SchemaVersion": 2,
                "Results": [],
            }
        )
        verdict = parse_trivy_json(report)
        assert verdict.success
        assert len(verdict.findings) == 0

    @given(severity=st.sampled_from(["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"]))
    def test_severity_in_vulnerabilities(self, severity: str):
        """Test severity classification in vulnerability results."""
        report = json.dumps(
            {
                "SchemaVersion": 2,
                "Results": [
                    {
                        "Target": "test-image",
                        "Vulnerabilities": [
                            {
                                "VulnerabilityID": "CVE-2024-test",
                                "PkgName": "test-pkg",
                                "InstalledVersion": "1.0.0",
                                "Severity": severity,
                                "Description": "Test vuln",
                            }
                        ],
                    }
                ],
            }
        )
        verdict = parse_trivy_json(report)

        if severity in ("CRITICAL", "HIGH"):
            assert not verdict.success
        else:
            assert verdict.success or verdict.error is None

    def test_config_misconfigurations_parsing(self):
        """Test parsing of Trivy config misconfigurations."""
        report = json.dumps(
            {
                "SchemaVersion": 2,
                "Results": [
                    {
                        "Target": "terraform/main.tf",
                        "Misconfigurations": [
                            {
                                "ID": "AVD-AZU-0001",
                                "Title": "Test Policy",
                                "Description": "Test description",
                                "Severity": "HIGH",
                            }
                        ],
                    }
                ],
            }
        )
        verdict = parse_trivy_json(report, scanner_type="config")

        assert not verdict.success
        assert verdict.critical_count + verdict.high_count > 0


# ============================================================================
# Grype parser tests
# ============================================================================


class TestGrypeParser:
    """Test Grype JSON parser."""

    def test_empty_report_failure(self):
        """Empty report should fail."""
        verdict = parse_grype_json("")
        assert not verdict.success

    def test_empty_matches_success(self):
        """Empty matches should succeed."""
        report = json.dumps(
            {
                "matches": [],
                "metadata": {"version": "0.65.0"},
            }
        )
        verdict = parse_grype_json(report)
        assert verdict.success

    @given(severity=st.sampled_from(["critical", "high", "medium", "low", "unknown"]))
    def test_severity_classification(self, severity: str):
        """Test severity classification in Grype output."""
        report = json.dumps(
            {
                "matches": [
                    {
                        "vulnerability": {
                            "id": f"CVE-2024-{severity}",
                            "severity": severity,
                            "description": "Test",
                            "fix": {"versions": ["2.0.0"]},
                        },
                        "artifact": {
                            "name": "test-pkg",
                            "version": "1.0.0",
                        },
                    }
                ],
                "metadata": {"version": "0.65.0"},
            }
        )
        verdict = parse_grype_json(report)

        if severity in ("critical", "high"):
            assert not verdict.success
        else:
            assert verdict.success or verdict.error is None


# ============================================================================
# Checkov parser tests
# ============================================================================


class TestCheckovParser:
    """Test Checkov JSON parser."""

    def test_empty_report_success(self):
        """Report with no failed checks should succeed."""
        report = json.dumps(
            {
                "check_type": "terraform",
                "summary": {"passed": 10, "failed": 0},
                "results": {"failed_checks": [], "passed_checks": []},
            }
        )
        verdict = parse_checkov_json(report)
        assert verdict.success

    def test_high_severity_failures_block(self):
        """HIGH severity Checkov checks should block."""
        report = json.dumps(
            {
                "check_type": "terraform",
                "summary": {"passed": 0, "failed": 1},
                "results": {
                    "failed_checks": [
                        {
                            "check_id": "CKV_AWS_123",
                            "check_name": "Test Check",
                            "severity": "high",
                            "file_path": "main.tf",
                            "resource": "aws_bucket",
                        }
                    ],
                    "passed_checks": [],
                },
            }
        )
        verdict = parse_checkov_json(report)

        assert not verdict.success
        assert verdict.high_count > 0


# ============================================================================
# gitleaks parser tests
# ============================================================================


class TestGitleaksParser:
    """Test gitleaks JSON parser."""

    def test_empty_report_success(self):
        """Empty/no findings should succeed."""
        verdict = parse_gitleaks_json("")
        assert verdict.success
        assert len(verdict.findings) == 0

    def test_single_secret_failure(self):
        """Finding a secret should fail."""
        report = json.dumps(
            {
                "RuleID": "gitlab-pat",
                "Description": "GitLab Personal Access Token",
                "File": ".env",
                "StartLine": 5,
                "Secret": "glpat-...",
            }
        )
        verdict = parse_gitleaks_json(report)

        assert not verdict.success
        assert verdict.critical_count == 1

    def test_multiple_secrets_failure(self):
        """Multiple secrets should fail."""
        report = json.dumps(
            [
                {
                    "RuleID": "gitlab-pat",
                    "Description": "GitLab PAT",
                    "File": ".env",
                    "StartLine": 1,
                },
                {
                    "RuleID": "aws-key",
                    "Description": "AWS Key",
                    "File": ".env",
                    "StartLine": 2,
                },
            ]
        )
        verdict = parse_gitleaks_json(report)

        assert not verdict.success
        assert verdict.critical_count == 2


# ============================================================================
# Policy tests
# ============================================================================


class TestZeroHighCriticalPolicy:
    """Test zero High/Critical policy enforcement."""

    @given(findings=st.lists(finding_strategy(), max_size=10))
    def test_policy_blocks_high_critical(self, findings: List[Finding]):
        """Policy should reject any HIGH or CRITICAL findings."""
        # Filter to only HIGH/CRITICAL
        blocking_findings = [f for f in findings if f.severity.is_blocking()]

        if blocking_findings:
            result = ZeroHighCriticalPolicy.compute_verdict(findings)
            assert not result
        else:
            result = ZeroHighCriticalPolicy.compute_verdict(findings)
            assert result

    @given(
        findings=st.lists(
            st.builds(
                Finding,
                id=st.text(min_size=1),
                severity=st.sampled_from(
                    [SeverityLevel.MEDIUM, SeverityLevel.LOW, SeverityLevel.INFO]
                ),
                description=st.text(),
                path=st.text(),
            ),
            min_size=0,
            max_size=10,
        )
    )
    def test_policy_allows_medium_and_below(self, findings: List[Finding]):
        """Policy should allow MEDIUM, LOW, and INFO findings."""
        result = ZeroHighCriticalPolicy.compute_verdict(findings)
        assert result

    def test_validation_no_suppressions_detects_patterns(self):
        """Validate_no_suppressions should detect common suppression patterns."""
        test_cases = [
            ("pip-audit", "pip-audit --ignore CVE-2024-1234", False),
            ("npm", "MAX_HIGH: 5", False),
            ("trivy", "--ignore-unfixed", False),
            ("grype", "--ignore-file", False),
            ("checkov", "--skip-check", False),
            ("gitleaks", "allowlist", False),
            ("pip-audit", "no suppressions here", True),
        ]

        for scanner, content, should_pass in test_cases:
            is_valid, _ = ZeroHighCriticalPolicy.validate_no_suppressions(
                content, scanner
            )
            if should_pass:
                assert is_valid, f"Expected pass for {scanner}: {content}"
            else:
                assert not is_valid, f"Expected fail for {scanner}: {content}"


# ============================================================================
# Edge case and malformed report tests
# ============================================================================


class TestMalformedReports:
    """Test handling of malformed and edge-case reports."""

    def test_pip_audit_null_vulnerabilities(self):
        """pip-audit with null vulnerabilities should fail."""
        report = json.dumps({"vulnerabilities": None})
        verdict = parse_pip_audit_json(report)
        assert not verdict.success

    def test_npm_non_object_vulnerabilities(self):
        """npm with non-object vulnerabilities should fail."""
        report = json.dumps({"vulnerabilities": []})  # Should be object
        verdict = parse_npm_audit_json(report)
        # npm rejects array where object is expected
        assert not verdict.success

    def test_trivy_non_array_results(self):
        """Trivy with non-array Results should fail."""
        report = json.dumps({"SchemaVersion": 2, "Results": {}})
        verdict = parse_trivy_json(report)
        assert not verdict.success

    @given(content=st.just("not json at all"))
    def test_all_parsers_handle_invalid_json(self, content: str):
        """All parsers should handle invalid JSON gracefully."""
        parsers = [
            (parse_pip_audit_json, "pip-audit"),
            (parse_npm_audit_json, "npm"),
            (parse_trivy_json, "trivy"),
            (parse_grype_json, "grype"),
            (parse_checkov_json, "checkov"),
            (parse_gitleaks_json, "gitleaks"),
        ]

        for parser, name in parsers:
            verdict = parser(content)
            assert not verdict.success, f"{name} should fail on invalid JSON"
            assert verdict.error, f"{name} should have error message"


# ============================================================================
# Verdict merging tests
# ============================================================================


class TestVerdictMerging:
    """Test merging multiple verdicts into aggregate."""

    def test_all_success_verdicts_merge_to_success(self):
        """All successful verdicts should merge to success."""
        verdicts = [
            ScannerVerdict(success=True, findings=[], high_count=0, critical_count=0),
            ScannerVerdict(success=True, findings=[], high_count=0, critical_count=0),
        ]
        merged = merge_verdicts(verdicts)
        assert merged.success

    def test_any_failure_verdict_fails_merge(self):
        """Any failed verdict should fail merge."""
        verdicts = [
            ScannerVerdict(success=True, findings=[], high_count=0, critical_count=0),
            ScannerVerdict(success=False, error="Test error", findings=[]),
        ]
        merged = merge_verdicts(verdicts)
        assert not merged.success

    def test_merged_verdict_counts_findings(self):
        """Merged verdict should count findings correctly."""
        verdicts = [
            ScannerVerdict(
                success=False,
                findings=[
                    Finding("CVE-1", SeverityLevel.HIGH, "Test", "pkg1", "scanner1")
                ],
                high_count=1,
                critical_count=0,
            ),
            ScannerVerdict(
                success=False,
                findings=[
                    Finding("CVE-2", SeverityLevel.CRITICAL, "Test", "pkg2", "scanner2")
                ],
                high_count=0,
                critical_count=1,
            ),
        ]
        merged = merge_verdicts(verdicts)

        assert merged.high_count == 1
        assert merged.critical_count == 1
        assert len(merged.findings) == 2
        assert not merged.success


# ============================================================================
# Exception validation tests
# ============================================================================


class TestSeverityExceptionValidation:
    """Test validation that findings have no exceptions/waivers."""

    def test_waived_finding_detected(self):
        """Findings with waived markers should be detected."""
        findings = [
            Finding(
                "CVE-waived-2024", SeverityLevel.CRITICAL, "Test", "pkg", "scanner"
            ),
        ]
        is_valid, errors = validate_no_severity_exceptions(findings)
        assert not is_valid
        assert len(errors) > 0

    def test_exception_in_description_detected(self):
        """Exception markers in description should be detected."""
        findings = [
            Finding(
                "CVE-2024-001",
                SeverityLevel.HIGH,
                "Exception granted until 2025-01-01",
                "pkg",
                "scanner",
            ),
        ]
        is_valid, errors = validate_no_severity_exceptions(findings)
        assert not is_valid

    def test_clean_findings_pass_validation(self):
        """Clean findings should pass validation."""
        findings = [
            Finding(
                "CVE-2024-001",
                SeverityLevel.MEDIUM,
                "Test vulnerability",
                "pkg",
                "scanner",
            ),
        ]
        is_valid, errors = validate_no_severity_exceptions(findings)
        assert is_valid
        assert len(errors) == 0
