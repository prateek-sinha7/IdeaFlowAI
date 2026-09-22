"""Property-based tests for scanner policy and zero-tolerance enforcement.

Validates: Requirements 2.8 (zero High/Critical policy)
"""

import json
import tempfile
from pathlib import Path
from hypothesis import given, strategies as st
import pytest
from tools.ci.scanner_policy import Finding, ScannerPolicy, Severity


class TestScannerPolicy:
    """Test zero-tolerance security policy enforcement."""

    def test_policy_zero_high_critical(self):
        """Test that any High/Critical finding fails policy."""
        policy = ScannerPolicy()

        high_finding = Finding(
            scanner="pip-audit",
            package="vulnerable-package",
            version="1.0.0",
            vulnerability_id="CVE-2024-1234",
            severity=Severity.HIGH,
            description="High severity vulnerability",
        )

        passes, blocking = policy.check_policy([high_finding])
        assert passes is False
        assert len(blocking) == 1
        assert blocking[0].severity == Severity.HIGH

    def test_policy_zero_critical(self):
        """Test that Critical findings fail policy."""
        policy = ScannerPolicy()

        critical_finding = Finding(
            scanner="trivy",
            package="system-package",
            version="2.0.0",
            vulnerability_id="CVE-2024-9999",
            severity=Severity.CRITICAL,
            description="Critical vulnerability",
        )

        passes, blocking = policy.check_policy([critical_finding])
        assert passes is False
        assert len(blocking) == 1
        assert blocking[0].severity == Severity.CRITICAL

    def test_policy_allows_medium_low(self):
        """Test that Medium and Low findings pass policy."""
        policy = ScannerPolicy()

        medium_finding = Finding(
            scanner="npm-audit",
            package="dev-package",
            version="1.5.0",
            vulnerability_id="GHSA-2024-5678",
            severity=Severity.MEDIUM,
            description="Medium severity issue",
        )

        low_finding = Finding(
            scanner="gitleaks",
            package="test-file",
            version="0.0.1",
            vulnerability_id="low-issue",
            severity=Severity.LOW,
            description="Low severity finding",
        )

        passes, blocking = policy.check_policy([medium_finding, low_finding])
        assert passes is True
        assert len(blocking) == 0

    def test_policy_mixed_findings_with_high(self):
        """Test that one High finding fails even with many Low findings."""
        policy = ScannerPolicy()

        findings = [
            Finding(
                scanner="pip-audit",
                package="pkg1",
                version="1.0",
                vulnerability_id="LOW1",
                severity=Severity.LOW,
                description="Low 1",
            ),
            Finding(
                scanner="pip-audit",
                package="pkg2",
                version="1.0",
                vulnerability_id="MED1",
                severity=Severity.MEDIUM,
                description="Medium 1",
            ),
            Finding(
                scanner="pip-audit",
                package="pkg3",
                version="1.0",
                vulnerability_id="HIGH1",
                severity=Severity.HIGH,
                description="High 1",
            ),
            Finding(
                scanner="pip-audit",
                package="pkg4",
                version="1.0",
                vulnerability_id="LOW2",
                severity=Severity.LOW,
                description="Low 2",
            ),
        ]

        passes, blocking = policy.check_policy(findings)
        assert passes is False
        assert len(blocking) == 1
        assert blocking[0].severity == Severity.HIGH

    def test_policy_ignores_fix_availability(self):
        """Test that policy fails on High/Critical regardless of fix availability."""
        policy = ScannerPolicy()

        # Finding with fix available
        unfixed_finding = Finding(
            scanner="pip-audit",
            package="pkg-unfixed",
            version="1.0.0",
            vulnerability_id="CVE-2024-0001",
            severity=Severity.HIGH,
            description="High severity with no fix",
            fixed_version=None,
        )

        # Finding with fix available
        fixed_finding = Finding(
            scanner="pip-audit",
            package="pkg-fixed",
            version="1.0.0",
            vulnerability_id="CVE-2024-0002",
            severity=Severity.HIGH,
            description="High severity with fix available",
            fixed_version="1.0.1",
        )

        # Both should fail regardless of fix availability
        for finding in [unfixed_finding, fixed_finding]:
            passes, blocking = policy.check_policy([finding])
            assert passes is False, "Policy should fail on High regardless of fix"
            assert len(blocking) == 1

    @given(
        severity_str=st.sampled_from(
            [
                "CRITICAL",
                "HIGH",
                "MEDIUM",
                "LOW",
                "UNKNOWN",
                "critical",
                "high",
                "medium",
                "low",
            ]
        )
    )
    def test_severity_parsing(self, severity_str):
        """Property: Severity parsing is case-insensitive and consistent."""
        severity = Severity.from_string(severity_str)

        if severity_str.upper() in [s.value for s in Severity]:
            assert severity is not None
            assert severity.value == severity_str.upper()
        else:
            assert severity is None

    def test_empty_findings_passes(self):
        """Test that zero findings passes policy."""
        policy = ScannerPolicy()
        passes, blocking = policy.check_policy([])
        assert passes is True
        assert len(blocking) == 0

    def test_report_formatting(self):
        """Test that policy reports are formatted correctly."""
        policy = ScannerPolicy()

        findings = [
            Finding(
                scanner="pip-audit",
                package="bad-pkg",
                version="1.0",
                vulnerability_id="CVE-2024-1",
                severity=Severity.HIGH,
                description="Test finding",
            ),
        ]

        passes, blocking = policy.check_policy(findings)
        report = policy.format_report(findings, passes)

        assert "FAIL" in report
        assert "1" in report
        assert "HIGH" in report
        assert "bad-pkg" in report

    def test_severity_is_blocking(self):
        """Test severity blocking classification."""
        assert Severity.CRITICAL.is_blocking() is True
        assert Severity.HIGH.is_blocking() is True
        assert Severity.MEDIUM.is_blocking() is False
        assert Severity.LOW.is_blocking() is False
        assert Severity.UNKNOWN.is_blocking() is False


class TestScannerPolicyParsing:
    """Test scanner report parsing implementations."""

    def test_parse_pip_audit_json(self):
        """Test parsing pip-audit JSON output."""
        policy = ScannerPolicy()

        report_data = {
            "vulnerabilities": [
                {
                    "name": "test-pkg",
                    "version": "1.0.0",
                    "id": "PYSEC-2024-1",
                    "fix_available": True,
                    "fix_versions": ["1.0.1"],
                    "advisories": [
                        {
                            "description": "Test vulnerability",
                            "cve": "CVE-2024-1234",
                        }
                    ],
                }
            ]
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(report_data, f)
            temp_path = Path(f.name)

        try:
            findings = policy.parse_pip_audit_json(temp_path)
            assert len(findings) == 1
            assert findings[0].package == "test-pkg"
            assert findings[0].scanner == "pip-audit"
        finally:
            temp_path.unlink()

    def test_parse_npm_audit_json(self):
        """Test parsing npm audit JSON output."""
        policy = ScannerPolicy()

        report_data = {
            "vulnerabilities": {
                "test-pkg": {
                    "nodes": ["test-pkg"],
                    "severity": "high",
                    "via": [
                        {
                            "source": 1,
                            "type": "package",
                            "package": "test-pkg",
                            "dependency": "test-pkg",
                            "title": "Test vulnerability",
                            "cves": ["CVE-2024-5678"],
                        }
                    ],
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(report_data, f)
            temp_path = Path(f.name)

        try:
            findings = policy.parse_npm_audit_json(temp_path)
            assert len(findings) == 1
            assert findings[0].package == "test-pkg"
            assert findings[0].scanner == "npm-audit"
            assert findings[0].severity == Severity.HIGH
        finally:
            temp_path.unlink()

    def test_parse_trivy_json(self):
        """Test parsing Trivy JSON output."""
        policy = ScannerPolicy()

        report_data = {
            "Results": [
                {
                    "Type": "library",
                    "Misconfigurations": [],
                    "Vulnerabilities": [
                        {
                            "VulnerabilityID": "CVE-2024-9999",
                            "PkgName": "vuln-lib",
                            "InstalledVersion": "1.0.0",
                            "FixedVersion": "1.0.1",
                            "Severity": "CRITICAL",
                            "Description": "Critical vulnerability",
                        }
                    ],
                }
            ]
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(report_data, f)
            temp_path = Path(f.name)

        try:
            findings = policy.parse_trivy_json(temp_path)
            assert len(findings) == 1
            assert findings[0].scanner == "trivy"
            assert findings[0].severity == Severity.CRITICAL
        finally:
            temp_path.unlink()

    def test_parse_missing_file(self):
        """Test that parsing missing file returns empty list."""
        policy = ScannerPolicy()
        missing_path = Path("/nonexistent/file.json")

        findings = policy.parse_pip_audit_json(missing_path)
        assert len(findings) == 0

        findings = policy.parse_npm_audit_json(missing_path)
        assert len(findings) == 0

        findings = policy.parse_trivy_json(missing_path)
        assert len(findings) == 0

    def test_parse_malformed_json(self):
        """Test that parsing malformed JSON returns empty list."""
        policy = ScannerPolicy()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{ invalid json }")
            temp_path = Path(f.name)

        try:
            findings = policy.parse_pip_audit_json(temp_path)
            assert len(findings) == 0
        finally:
            temp_path.unlink()
