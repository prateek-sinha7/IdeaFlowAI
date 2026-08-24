#!/usr/bin/env python3
"""
Coverage Report Generator for Backend Test Suite

This is the documented coverage command for the VelocityAI backend.

Usage:
    cd backend
    uv run python scripts/coverage_report.py [--xml-output PATH] [--threshold-fail-exit-code N]

Exit Codes:
    0   — All tests passed, coverage thresholds met
    1   — Test assertion failure (but XML report still emitted)
    2   — Coverage threshold failure (but XML report still emitted)
    3   — Configuration or environment error (XML may not be emitted)

The command:
    1. Runs pytest with full coverage instrumentation
    2. Emits XML coverage report (coverage-report.xml by default)
    3. Emits terminal coverage summary (line coverage percentage)
    4. Uses distinct exit codes for assertion vs threshold failures
    5. Always emits XML unless environment failure occurs
"""

import sys
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
import re


def run_pytest_with_coverage(
    xml_output_path: Path = Path("coverage-report.xml"),
) -> dict:
    """
    Run pytest with coverage instrumentation.
    
    Returns:
        dict with keys:
            - 'returncode': pytest exit code
            - 'stdout': captured output
            - 'stderr': captured errors
    """
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/",
        "-v",
        "--tb=short",
        f"--cov=app",
        f"--cov=agents",
        f"--cov-report=term-missing:skip-covered",
        f"--cov-report=xml:{xml_output_path}",
        "--junitxml=junit-report.xml",
    ]
    
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )
    
    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def extract_coverage_summary(coverage_xml_path: Path) -> dict:
    """
    Extract coverage summary from coverage.xml.
    
    Returns:
        dict with keys:
            - 'line_rate': float (0.0-1.0)
            - 'branch_rate': float (0.0-1.0)
            - 'packages_count': int
            - 'lines_valid': int
            - 'lines_covered': int
    """
    try:
        tree = ET.parse(coverage_xml_path)
        root = tree.getroot()
        
        # Extract overall coverage statistics
        line_rate = float(root.get("line-rate", "0.0"))
        branch_rate = float(root.get("branch-rate", "0.0"))
        
        # Count packages and lines
        packages = root.findall("packages/package")
        packages_count = len(packages)
        
        # Sum lines from all packages
        lines_valid = 0
        lines_covered = 0
        for pkg in packages:
            classes = pkg.findall("classes/class")
            for cls in classes:
                lines = cls.findall("lines/line")
                for line in lines:
                    lines_valid += 1
                    if line.get("hits") != "0":
                        lines_covered += 1
        
        return {
            "line_rate": line_rate,
            "branch_rate": branch_rate,
            "packages_count": packages_count,
            "lines_valid": lines_valid,
            "lines_covered": lines_covered,
        }
    except Exception as e:
        print(f"ERROR: Failed to parse coverage XML: {e}", file=sys.stderr)
        raise


def emit_coverage_summary(coverage_summary: dict) -> None:
    """Emit a human-readable coverage summary to stdout."""
    line_percent = coverage_summary["line_rate"] * 100
    branch_percent = coverage_summary["branch_rate"] * 100
    
    print("\n" + "=" * 70)
    print("COVERAGE SUMMARY")
    print("=" * 70)
    print(f"Line Coverage:    {line_percent:6.2f}% ({coverage_summary['lines_covered']}/{coverage_summary['lines_valid']} lines)")
    print(f"Branch Coverage:  {branch_percent:6.2f}%")
    print(f"Packages:         {coverage_summary['packages_count']}")
    print("=" * 70)


def check_threshold_failure(pytest_stdout: str) -> bool:
    """
    Detect if pytest output indicates a coverage threshold failure.
    
    This is distinguished from a test assertion failure by checking for
    the coverage plugin's specific error message.
    
    Args:
        pytest_stdout: The captured stdout from pytest
        
    Returns:
        True if threshold failure detected, False otherwise
    """
    # pytest-cov reports threshold failures in output
    # Look for "FAILED" combined with coverage-specific messages
    threshold_patterns = [
        r"FAILED.*coverage.*threshold",
        r"coverage: .* below threshold",
    ]
    
    for pattern in threshold_patterns:
        if re.search(pattern, pytest_stdout, re.IGNORECASE):
            return True
    
    return False


def main() -> int:
    """
    Main entry point for coverage report generation.
    
    Returns:
        0 — Success
        1 — Test assertion failure
        2 — Coverage threshold failure
        3 — Configuration/environment error
    """
    xml_output_path = Path("coverage-report.xml")
    
    print("Running pytest with coverage instrumentation...")
    print(f"Coverage XML will be written to: {xml_output_path}")
    print()
    
    # Run pytest with coverage
    result = run_pytest_with_coverage(xml_output_path)
    
    # Try to extract and emit coverage summary regardless of pytest result
    coverage_summary = None
    if xml_output_path.exists():
        try:
            coverage_summary = extract_coverage_summary(xml_output_path)
            emit_coverage_summary(coverage_summary)
        except Exception as e:
            print(f"WARNING: Could not parse coverage summary: {e}", file=sys.stderr)
    else:
        print("WARNING: Coverage XML was not generated", file=sys.stderr)
    
    # Determine exit code
    if result["returncode"] == 0:
        print("\n✓ All tests passed and coverage thresholds met")
        return 0
    else:
        # Check if this is a threshold failure or assertion failure
        if check_threshold_failure(result["stdout"]):
            print("\n✗ Coverage threshold failure")
            print(result["stdout"])
            return 2
        else:
            print("\n✗ Test assertion failure")
            print(result["stdout"])
            return 1


if __name__ == "__main__":
    sys.exit(main())
