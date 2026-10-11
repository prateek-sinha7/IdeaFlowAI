"""
Scanner verdict types and severity classification.

Provides typed models for representing vulnerability findings from various
security scanners with consistent severity classification.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SeverityLevel(str, Enum):
    """Standard severity levels for security findings."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

    def is_blocking(self) -> bool:
        """Return True if this severity blocks CI."""
        return self in (SeverityLevel.CRITICAL, SeverityLevel.HIGH)


@dataclass
class Finding:
    """A single security finding from a scanner."""

    id: str
    """Unique finding ID (CVE, advisory ID, etc.)"""

    severity: SeverityLevel
    """Classified severity level"""

    description: str
    """Human-readable description"""

    path: str
    """Path, component, or package affected (e.g., file path or package@version)"""

    scanner: str = ""
    """Scanner that produced this finding"""

    fixed_version: Optional[str] = None
    """Fixed version if available"""


@dataclass
class ScannerVerdict:
    """Verdict for a complete scanner report."""

    success: bool
    """True if report is valid and policy compliant"""

    findings: list[Finding] = field(default_factory=list)
    """All findings from the report"""

    high_count: int = 0
    """Number of HIGH severity findings"""

    critical_count: int = 0
    """Number of CRITICAL severity findings"""

    error: Optional[str] = None
    """Error message if parsing/validation failed"""

    @property
    def blocking_count(self) -> int:
        """Total count of HIGH and CRITICAL findings."""
        return self.high_count + self.critical_count

    def has_blocking_findings(self) -> bool:
        """Return True if any HIGH or CRITICAL findings present."""
        return self.blocking_count > 0


def map_severity(scanner_name: str, raw_severity: str) -> SeverityLevel:
    """
    Map scanner-specific severity to standard SeverityLevel.

    Args:
        scanner_name: Name of the scanner (pip-audit, npm, trivy, etc.)
        raw_severity: Raw severity string from scanner output

    Returns:
        SeverityLevel: Normalized severity level

    Raises:
        ValueError: If severity cannot be mapped
    """
    # Normalize input
    normalized = raw_severity.lower().strip()

    # Direct matches
    if normalized in ("critical", "c"):
        return SeverityLevel.CRITICAL
    if normalized in ("high", "h"):
        return SeverityLevel.HIGH
    if normalized in ("medium", "m", "moderate"):  # npm uses "moderate"
        return SeverityLevel.MEDIUM
    if normalized in ("low", "l"):
        return SeverityLevel.LOW
    if normalized in ("info", "i", "information"):
        return SeverityLevel.INFO
    if normalized in ("negligible",):  # Grype v0.119.0+ uses "negligible"
        return SeverityLevel.INFO

    # Scanner-specific mappings
    if scanner_name.lower() in ("trivy", "grype"):
        # Trivy/Grype may use UNKNOWN
        if normalized == "unknown":
            # Treat unknown conservatively as HIGH
            return SeverityLevel.HIGH

    if scanner_name.lower() == "npm":
        # npm uses "moderate"
        if normalized == "moderate":
            return SeverityLevel.MEDIUM

    if scanner_name.lower() == "checkov":
        # Checkov uses different severity levels
        severity_map = {
            "critical": SeverityLevel.CRITICAL,
            "high": SeverityLevel.HIGH,
            "medium": SeverityLevel.MEDIUM,
            "low": SeverityLevel.LOW,
            "info": SeverityLevel.INFO,
        }
        if normalized in severity_map:
            return severity_map[normalized]

    raise ValueError(f"Unknown severity '{raw_severity}' for scanner '{scanner_name}'")
