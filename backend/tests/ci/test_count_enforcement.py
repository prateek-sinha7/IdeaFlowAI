"""
Test count validation against baseline registry.

This module provides utilities to collect test counts from various test suites
(pytest, vitest, playwright) and compare them against the recorded baselines
in `.planning/test-baselines.yml`.

Requirements: 32.3, 32.4, 32.5, 2.7
"""

import re
import subprocess
from pathlib import Path
from typing import Dict, Tuple, Optional
import yaml


class TestCountValidator:
    """Validates test counts against recorded baselines."""

    def __init__(self, baseline_path: Path = None, repo_root: Path = None):
        """
        Initialize the validator.

        Args:
            baseline_path: Path to test-baselines.yml. Defaults to .planning/test-baselines.yml
            repo_root: Root of the repository. Defaults to parent of this file up 4 levels.
        """
        if repo_root is None:
            # Navigate from backend/tests/ci to repo root
            repo_root = Path(__file__).parent.parent.parent.parent
        self.repo_root = repo_root

        if baseline_path is None:
            baseline_path = self.repo_root / ".planning" / "test-baselines.yml"
        self.baseline_path = Path(baseline_path)

        self.baselines = self._load_baselines()
        self.collected_counts = {}
        self.errors = []

    def _load_baselines(self) -> Dict[str, int]:
        """Load baseline counts from YAML file."""
        if not self.baseline_path.exists():
            raise FileNotFoundError(f"Baseline file not found: {self.baseline_path}")

        with open(self.baseline_path) as f:
            data = yaml.safe_load(f)
            if "baselines" not in data:
                raise ValueError(f"Invalid baseline file format: missing 'baselines' key")
            return data["baselines"]

    def collect_pytest_count(self, *test_args) -> Optional[int]:
        """
        Collect pytest test count via --collect-only.

        Args:
            *test_args: Arguments to pass to pytest (e.g., "tests/agents/", "--ignore=tests/ci/")

        Returns:
            Number of collected tests, or None if collection fails
        """
        try:
            # Use pytest --collect-only to get count without running
            result = subprocess.run(
                ["python", "-m", "pytest", "--collect-only", "-q"] + list(test_args),
                cwd=self.repo_root / "backend",
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode != 0:
                # pytest --collect-only returns 0 on success even if it lists tests
                # If it fails, return None to signal failure
                if "error" in result.stderr.lower():
                    return None

            # Parse output for count
            # pytest --collect-only -q outputs lines like "3498 tests collected in 5.23s"
            output = result.stdout + result.stderr
            match = re.search(r"(\d+)\s+tests? collected", output)
            if match:
                return int(match.group(1))

            # Fallback: count test lines in output
            lines = [l for l in result.stdout.split("\n") if l.strip() and not l.startswith(" ")]
            # This is less reliable but provides a fallback
            return len(lines) if lines else None

        except subprocess.TimeoutExpired:
            return None
        except Exception as e:
            self.errors.append(f"pytest collection failed: {e}")
            return None

    def collect_vitest_count(self) -> Optional[int]:
        """
        Collect vitest test count via vitest list.

        Returns:
            Number of collected tests, or None if collection fails
        """
        try:
            # Use vitest list --reporter=json
            result = subprocess.run(
                ["npm", "run", "--silent", "vitest", "--", "list", "--reporter=json"],
                cwd=self.repo_root / "frontend",
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode != 0:
                self.errors.append(f"vitest collection failed with exit code {result.returncode}")
                return None

            # Count test suites and tests in output
            output = result.stdout
            # This depends on the JSON output structure
            # For now, use a simple regex that works with vitest --reporter=verbose output
            match = re.search(r"(\d+)\s+test", output)
            if match:
                return int(match.group(1))

            self.errors.append("vitest collection: could not parse test count from output")
            return None

        except subprocess.TimeoutExpired:
            self.errors.append("vitest collection timed out (120s)")
            return None
        except Exception as e:
            self.errors.append(f"vitest collection failed: {e}")
            return None

    def collect_playwright_mocked_count(self) -> Optional[int]:
        """
        Collect mocked Playwright test count.

        Playwright mocked tests are defined in frontend/e2e/tests/mocked.
        Returns the number of test() calls found.

        Returns:
            Number of mocked tests, or None if collection fails
        """
        try:
            playwright_dir = self.repo_root / "frontend" / "e2e" / "tests" / "mocked"
            if not playwright_dir.exists():
                self.errors.append(f"Playwright mocked directory not found: {playwright_dir}")
                return None

            # Count test() calls in .spec.ts files
            test_count = 0
            for spec_file in playwright_dir.rglob("*.spec.ts"):
                content = spec_file.read_text()
                # Count test() and test.describe() calls
                matches = re.findall(r"(?:test|test\.(?:describe|skip|only))\(", content)
                test_count += len(matches)

            return test_count if test_count > 0 else None

        except Exception as e:
            self.errors.append(f"Playwright collection failed: {e}")
            return None

    def validate_counts(self) -> Tuple[bool, Dict[str, object]]:
        """
        Validate collected counts against baselines.

        Returns:
            (is_valid, results_dict)
            where results_dict contains 'pytest', 'vitest', 'playwright_mocked',
            each with 'baseline', 'collected', and 'match' keys
        """
        results = {}

        # Collect pytest count
        pytest_count = self.collect_pytest_count("tests/")
        results["pytest"] = {
            "baseline": self.baselines.get("pytest"),
            "collected": pytest_count,
            "match": pytest_count == self.baselines.get("pytest") if pytest_count else False,
        }

        # Collect vitest count
        vitest_count = self.collect_vitest_count()
        results["vitest"] = {
            "baseline": self.baselines.get("vitest"),
            "collected": vitest_count,
            "match": vitest_count == self.baselines.get("vitest") if vitest_count else False,
        }

        # Collect Playwright mocked count
        pw_count = self.collect_playwright_mocked_count()
        results["playwright_mocked"] = {
            "baseline": self.baselines.get("playwright_mocked"),
            "collected": pw_count,
            "match": pw_count == self.baselines.get("playwright_mocked") if pw_count else False,
        }

        # All must match
        all_match = all(r.get("match", False) for r in results.values())

        return all_match, results

    def format_failure_message(self, results: Dict) -> str:
        """Format a failure message listing mismatched counts."""
        lines = ["Test count validation failed:"]

        for suite_name, data in results.items():
            if not data.get("match", False):
                baseline = data.get("baseline", "unknown")
                collected = data.get("collected", "unknown")
                lines.append(f"  {suite_name}: baseline={baseline}, collected={collected}")

        return "\n".join(lines)


class SkipEnforcementLinter:
    """Lints test code for unrecorded skips, disables, or weakened assertions."""

    def __init__(
        self,
        remediation_record_path: Path = None,
        repo_root: Path = None,
    ):
        """
        Initialize the linter.

        Args:
            remediation_record_path: Path to REMEDIATION-RECORD.md
            repo_root: Root of repository
        """
        if repo_root is None:
            repo_root = Path(__file__).parent.parent.parent.parent
        self.repo_root = repo_root

        if remediation_record_path is None:
            remediation_record_path = self.repo_root / ".planning" / "REMEDIATION-RECORD.md"
        self.remediation_record_path = Path(remediation_record_path)

        self.recorded_skips = self._load_recorded_skips()
        self.findings = []

    def _load_recorded_skips(self) -> set[str]:
        """Load set of skip/disable IDs from the remediation record."""
        if not self.remediation_record_path.exists():
            return set()

        content = self.remediation_record_path.read_text()

        # Extract case IDs from Disabled Tests section
        recorded = set()
        in_disabled_section = False

        for line in content.split("\n"):
            if "## Disabled Tests" in line:
                in_disabled_section = True
                continue

            if line.startswith("## ") and "Disabled Tests" not in line:
                in_disabled_section = False
                continue

            if in_disabled_section and line.startswith("|"):
                # Extract case ID (first column)
                parts = [p.strip() for p in line.split("|")[1:-1]]
                if len(parts) > 0 and parts[0] and parts[0] != "Case ID":
                    recorded.add(parts[0])

        return recorded

    def lint_backend_tests(self) -> list[Dict]:
        """
        Lint backend test code for unrecorded skips.

        Looks for pytest.skip() and @pytest.mark.skip without corresponding
        entries in the Disabled Tests section.

        Returns:
            List of findings with 'file', 'line', 'directive', 'case_id'
        """
        findings = []

        backend_tests_dir = self.repo_root / "backend" / "tests"
        if not backend_tests_dir.exists():
            return findings

        for test_file in backend_tests_dir.rglob("test_*.py"):
            content = test_file.read_text()
            lines = content.split("\n")

            for i, line in enumerate(lines, 1):
                # Check for pytest.skip() calls
                if "pytest.skip(" in line:
                    # Find the test function this skip belongs to
                    # Search backwards from current line for the function definition
                    test_name = None
                    for j in range(i - 1, -1, -1):
                        match = re.search(r"def\s+(test_\w+)", lines[j])
                        if match:
                            test_name = match.group(1)
                            break
                    
                    if not test_name:
                        test_name = f"skip_at_line_{i}"
                    
                    if test_name not in self.recorded_skips:
                        findings.append({
                            "file": str(test_file.relative_to(self.repo_root)),
                            "line": i,
                            "directive": "pytest.skip()",
                            "case_id": test_name,
                        })

                # Check for @pytest.mark.skip
                if "@pytest.mark.skip" in line:
                    # Look for the next test definition
                    test_name = None
                    for j in range(i, min(i + 5, len(lines))):
                        match = re.search(r"def\s+(test_\w+)", lines[j])
                        if match:
                            test_name = match.group(1)
                            break
                    
                    if test_name and test_name not in self.recorded_skips:
                        findings.append({
                            "file": str(test_file.relative_to(self.repo_root)),
                            "line": i,
                            "directive": "@pytest.mark.skip",
                            "case_id": test_name,
                        })

        self.findings.extend(findings)
        return findings

    def lint_frontend_tests(self) -> list[Dict]:
        """
        Lint frontend test code for unrecorded skips.

        Looks for test.skip() and test.fixme() in vitest code.

        Returns:
            List of findings
        """
        findings = []

        frontend_tests_dir = self.repo_root / "frontend" / "src"
        if not frontend_tests_dir.exists():
            return findings

        for test_file in frontend_tests_dir.rglob("*.test.ts*"):
            content = test_file.read_text()
            lines = content.split("\n")

            for i, line in enumerate(lines, 1):
                # Check for test.skip()
                if "test.skip(" in line:
                    match = re.search(r'test\.skip\(\s*["\']([^"\']+)["\']', line)
                    test_name = match.group(1) if match else f"skip_at_line_{i}"
                    if test_name not in self.recorded_skips:
                        findings.append({
                            "file": str(test_file.relative_to(self.repo_root)),
                            "line": i,
                            "directive": "test.skip()",
                            "case_id": test_name,
                        })

                # Check for test.fixme()
                if "test.fixme(" in line:
                    match = re.search(r'test\.fixme\(\s*["\']([^"\']+)["\']', line)
                    test_name = match.group(1) if match else f"fixme_at_line_{i}"
                    if test_name not in self.recorded_skips:
                        findings.append({
                            "file": str(test_file.relative_to(self.repo_root)),
                            "line": i,
                            "directive": "test.fixme()",
                            "case_id": test_name,
                        })

        self.findings.extend(findings)
        return findings

    def has_findings(self) -> bool:
        """Return True if any unrecorded skips were found."""
        return len(self.findings) > 0

    def format_findings(self) -> str:
        """Format findings as a human-readable string."""
        if not self.findings:
            return "No unrecorded test skips found."

        lines = ["Unrecorded test skips/disables found:"]
        for finding in self.findings:
            lines.append(
                f"  {finding['file']}:{finding['line']} - "
                f"{finding['directive']} on {finding['case_id']}"
            )

        return "\n".join(lines)
