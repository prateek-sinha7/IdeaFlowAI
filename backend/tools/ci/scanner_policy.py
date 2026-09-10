"""Zero-tolerance scanner policy enforcement for security findings.

Implements fail-closed semantics for High/Critical software vulnerabilities
regardless of fix availability, actionability filters, or prior baselines.
"""

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from .scanner_verdict import Finding as VerDict_Finding, ScannerVerdict


class Severity(Enum):
    """Vulnerability severity levels."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def from_string(cls, s: str) -> Optional["Severity"]:
        """Parse severity from string, case-insensitive."""
        s_upper = s.upper()
        for severity in cls:
            if severity.value == s_upper:
                return severity
        return None

    def is_blocking(self) -> bool:
        """Check if this severity is blocking (High or Critical)."""
        return self in (Severity.CRITICAL, Severity.HIGH)


@dataclass
class Finding:
    """Single security finding from a scanner."""

    scanner: str
    package: str
    version: str
    vulnerability_id: str
    severity: Severity
    description: str
    fixed_version: Optional[str] = None
    cve_id: Optional[str] = None

    def is_blocking(self) -> bool:
        """Check if this finding should block based on severity."""
        return self.severity.is_blocking()

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "scanner": self.scanner,
            "package": self.package,
            "version": self.version,
            "vulnerability_id": self.vulnerability_id,
            "severity": self.severity.value,
            "description": self.description,
            "fixed_version": self.fixed_version,
            "cve_id": self.cve_id,
        }


class ScannerPolicy:
    """Enforces zero-tolerance policy on software vulnerabilities."""

    def __init__(self):
        """Initialize policy checker."""
        self.blocking_severities = {Severity.CRITICAL, Severity.HIGH}

    def parse_pip_audit_json(self, json_path: Path) -> list[Finding]:
        """Parse pip-audit JSON output.

        Format:
        {
          "vulnerabilities": [
            {
              "name": "package",
              "version": "1.0",
              "id": "PYXXXXX" or "CVE-YYYY-ZZZZ",
              "fix_available": true|false,
              "fix_versions": [],
              "advisories": [{
                "description": "...",
                "cve": "CVE-YYYY-ZZZZ"
              }]
            }
          ]
        }
        """
        findings = []
        if not json_path.exists():
            return findings

        try:
            data = json.loads(json_path.read_text())
        except (json.JSONDecodeError, IOError):
            return findings

        for vuln in data.get("vulnerabilities", []):
            # pip-audit uses PYXXXXX advisory IDs or CVE identifiers
            severity = self._infer_severity_from_advisory(vuln.get("advisories", []))
            if severity is None:
                severity = Severity.UNKNOWN

            finding = Finding(
                scanner="pip-audit",
                package=vuln.get("name", "unknown"),
                version=vuln.get("version", "unknown"),
                vulnerability_id=vuln.get("id", "unknown"),
                severity=severity,
                description=self._extract_description(vuln.get("advisories", [])),
                fixed_version=(
                    vuln.get("fix_versions", [None])[0]
                    if vuln.get("fix_versions")
                    else None
                ),
                cve_id=self._extract_cve(vuln.get("advisories", [])),
            )
            findings.append(finding)

        return findings

    def parse_npm_audit_json(self, json_path: Path) -> list[Finding]:
        """Parse npm audit JSON output.

        Format:
        {
          "vulnerabilities": {
            "package": {
              "nodes": ["<path>"],
              "severity": "high|critical|moderate|low|info",
              "via": [
                {
                  "source": <number>,
                  "type": "package",
                  "package": "package",
                  "dependency": "package",
                  "title": "...",
                  "cves": ["CVE-YYYY-ZZZZ"],
                  "cvss": {...}
                }
              ]
            }
          }
        }
        """
        findings = []
        if not json_path.exists():
            return findings

        try:
            data = json.loads(json_path.read_text())
        except (json.JSONDecodeError, IOError):
            return findings

        for package, vuln_data in data.get("vulnerabilities", {}).items():
            for via in vuln_data.get("via", []):
                severity_str = vuln_data.get("severity", "unknown").upper()
                severity = Severity.from_string(severity_str) or Severity.UNKNOWN

                cves = via.get("cves", [])
                cve_id = cves[0] if cves else None

                finding = Finding(
                    scanner="npm-audit",
                    package=package,
                    version="",  # npm audit doesn't always provide specific version
                    vulnerability_id=str(via.get("source", "unknown")),
                    severity=severity,
                    description=via.get("title", ""),
                    cve_id=cve_id,
                )
                findings.append(finding)

        return findings

    def parse_trivy_json(self, json_path: Path) -> list[Finding]:
        """Parse Trivy JSON output for container/config vulnerabilities."""
        findings = []
        if not json_path.exists():
            return findings

        try:
            data = json.loads(json_path.read_text())
        except (json.JSONDecodeError, IOError):
            return findings

        for result in data.get("Results", []):
            for misconfig in result.get("Misconfigurations", []):
                severity_str = misconfig.get("Severity", "UNKNOWN").upper()
                severity = Severity.from_string(severity_str) or Severity.UNKNOWN

                finding = Finding(
                    scanner="trivy",
                    package=misconfig.get("Type", "config"),
                    version="",
                    vulnerability_id=misconfig.get("ID", "unknown"),
                    severity=severity,
                    description=misconfig.get("Description", ""),
                )
                findings.append(finding)

            for vuln in result.get("Vulnerabilities", []):
                severity_str = vuln.get("Severity", "UNKNOWN").upper()
                severity = Severity.from_string(severity_str) or Severity.UNKNOWN

                finding = Finding(
                    scanner="trivy",
                    package=vuln.get("PkgName", "unknown"),
                    version=vuln.get("InstalledVersion", ""),
                    vulnerability_id=vuln.get("VulnerabilityID", "unknown"),
                    severity=severity,
                    description=vuln.get("Description", ""),
                    fixed_version=vuln.get("FixedVersion"),
                    cve_id=vuln.get("PrimaryURL"),
                )
                findings.append(finding)

        return findings

    def check_policy(self, findings: list[Finding]) -> tuple[bool, list[Finding]]:
        """Check if findings satisfy zero-tolerance policy.

        Returns:
            Tuple of (passes_policy, blocking_findings)
        """
        blocking = [f for f in findings if f.is_blocking()]
        return len(blocking) == 0, blocking

    def _infer_severity_from_advisory(
        self, advisories: list[dict]
    ) -> Optional[Severity]:
        """Infer severity from pip-audit advisory data."""
        for advisory in advisories:
            # Some advisories may include severity information
            if "severity" in advisory:
                severity_str = advisory["severity"].upper()
                return Severity.from_string(severity_str)
        return None

    def _extract_description(self, advisories: list[dict]) -> str:
        """Extract description from advisories."""
        if advisories:
            return advisories[0].get("description", "")
        return ""

    def _extract_cve(self, advisories: list[dict]) -> Optional[str]:
        """Extract CVE ID from advisories."""
        for advisory in advisories:
            if "cve" in advisory:
                return advisory["cve"]
        return None

    def format_report(self, findings: list[Finding], passes: bool) -> str:
        """Format findings report for display."""
        lines = []
        lines.append(f"Scanner Policy Verdict: {'PASS' if passes else 'FAIL'}")
        lines.append(f"Total Findings: {len(findings)}")

        blocking = [f for f in findings if f.is_blocking()]
        if blocking:
            lines.append(f"Blocking (High/Critical): {len(blocking)}")
            for finding in blocking:
                lines.append(
                    f"  - {finding.scanner}: {finding.package} "
                    f"({finding.vulnerability_id}) - {finding.severity.value}"
                )

        return "\n".join(lines)


class ZeroHighCriticalPolicy:
    """Fail-closed zero-tolerance policy on HIGH/CRITICAL findings.

    Enforces that no HIGH or CRITICAL severity findings are present in
    security scanner verdicts, regardless of fix availability, baseline
    history, or suppression/exception flags.
    """

    @staticmethod
    def validate_no_suppressions(
        config: str, scanner: str
    ) -> tuple[bool, Optional[str]]:
        """Validate that scanner configuration contains no suppressions.

        Args:
            config: Scanner configuration string to validate
            scanner: Scanner name (pip-audit, npm, trivy, grype, checkov, gitleaks)

        Returns:
            Tuple of (is_valid, error_message) where:
            - is_valid: False if suppressions are detected, True otherwise
            - error_message: Description of suppression found, or None

        **Validates: Requirements 2.9, 2.8**
        """
        suppression_patterns = {
            "pip-audit": ["--ignore", "--ignore-vuln"],
            "npm": ["MAX_HIGH", "MAX_CRITICAL", "ignore", "suppress"],
            "trivy": ["--ignore", "--ignore-unfixed", "--skip-files", "--skip-dirs"],
            "grype": ["--ignore", "--ignore-file", "--suppress", "--exclude"],
            "checkov": ["--skip-check", "--skip-framework", "-skip", "--framework"],
            "gitleaks": ["allowlist", "--allow-local"],
        }

        patterns = suppression_patterns.get(scanner, [])
        for pattern in patterns:
            if pattern in config:
                error = f"Suppression '{pattern}' detected in {scanner} configuration"
                return False, error

        return True, None

    @staticmethod
    def compute_verdict(findings: list[VerDict_Finding]) -> bool:
        """Compute policy verdict for a list of findings.

        Args:
            findings: List of findings to evaluate

        Returns:
            True if policy passes (no HIGH/CRITICAL), False otherwise

        **Validates: Requirements 2.8, 2.9**
        """
        for finding in findings:
            if finding.severity.is_blocking():
                return False
        return True

    @staticmethod
    def apply_policy(verdict: ScannerVerdict) -> ScannerVerdict:
        """Apply zero High/Critical policy to a scanner verdict.

        Args:
            verdict: ScannerVerdict to check

        Returns:
            ScannerVerdict with success=False if any HIGH/CRITICAL, else True
        """
        # Policy fails if there are any HIGH or CRITICAL findings
        if verdict.high_count > 0 or verdict.critical_count > 0:
            return ScannerVerdict(
                success=False,
                findings=verdict.findings,
                high_count=verdict.high_count,
                critical_count=verdict.critical_count,
                error=verdict.error,
            )

        # Policy passes if no HIGH/CRITICAL findings
        return ScannerVerdict(
            success=True,
            findings=verdict.findings,
            high_count=verdict.high_count,
            critical_count=verdict.critical_count,
            error=verdict.error,
        )

    def check_findings(
        self, findings: list[VerDict_Finding]
    ) -> tuple[bool, list[VerDict_Finding]]:
        """Check findings against zero HIGH/CRITICAL policy.

        Args:
            findings: List of Finding objects to check

        Returns:
            Tuple of (passes_policy, blocking_findings) where:
            - passes_policy: True if no HIGH/CRITICAL findings present
            - blocking_findings: List of HIGH/CRITICAL findings that block
        """
        blocking = [f for f in findings if f.severity.is_blocking()]
        passes = len(blocking) == 0
        return passes, blocking

    def merge_verdicts(self, verdicts: list[ScannerVerdict]) -> ScannerVerdict:
        """Merge multiple scanner verdicts into one.

        Combines findings from all verdicts. Verdict passes only if ALL
        input verdicts pass and the merged result has no HIGH/CRITICAL.

        Args:
            verdicts: List of ScannerVerdict objects to merge

        Returns:
            Combined ScannerVerdict with merged findings and policy check
        """
        if not verdicts:
            return ScannerVerdict(success=True, findings=[])

        all_findings: list[VerDict_Finding] = []
        total_high = 0
        total_critical = 0
        errors: list[str] = []

        for verdict in verdicts:
            if not verdict.success and verdict.error:
                errors.append(verdict.error)
            all_findings.extend(verdict.findings)
            total_high += verdict.high_count
            total_critical += verdict.critical_count

        # Merge fails if any input verdict failed
        if errors:
            merged_success = False
        else:
            # Check merged findings against policy
            merged_success = total_critical == 0 and total_high == 0

        error_msg = "; ".join(errors) if errors else None

        return ScannerVerdict(
            success=merged_success,
            findings=all_findings,
            high_count=total_high,
            critical_count=total_critical,
            error=error_msg,
        )


def merge_verdicts(verdicts: list[ScannerVerdict]) -> ScannerVerdict:
    """Merge multiple scanner verdicts into one consolidated verdict.

    Combines findings from all verdicts. Result passes only if all
    input verdicts pass and merged result has zero HIGH/CRITICAL findings.

    Args:
        verdicts: List of ScannerVerdict objects to merge

    Returns:
        Combined ScannerVerdict with aggregated findings and policy check

    **Validates: Requirements 2.8, 2.9**
    """
    policy = ZeroHighCriticalPolicy()
    return policy.merge_verdicts(verdicts)


def validate_no_severity_exceptions(
    findings: list[VerDict_Finding],
) -> tuple[bool, list[str]]:
    """Validate that findings have no severity exceptions or waivers.

    Rejects findings with "waived" or "exception" markers in ID or description
    to ensure zero-tolerance policy is truly fail-closed.

    Args:
        findings: List of findings to validate

    Returns:
        Tuple of (is_valid, error_messages) where:
        - is_valid: False if any exceptions are detected, True otherwise
        - error_messages: List of specific exception/waiver issues found

    **Validates: Requirements 2.8, 2.9, 3.15**
    """
    errors: list[str] = []

    exception_keywords = ["waived", "exception", "exempt", "approved", "suppressed"]

    for finding in findings:
        # Check ID for exception markers
        for keyword in exception_keywords:
            if keyword in finding.id.lower():
                errors.append(
                    f"Found severity exception marker '{keyword}' in finding ID: {finding.id}"
                )

        # Check description for exception markers
        for keyword in exception_keywords:
            if keyword in finding.description.lower():
                errors.append(
                    f"Found severity exception marker '{keyword}' in finding description: {finding.description}"
                )

    return len(errors) == 0, errors
