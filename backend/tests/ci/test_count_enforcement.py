"""
Test count validation against baseline registry.

This module provides utilities to collect test counts from various test suites
(pytest, vitest, playwright) and compare them against the recorded baselines
in `.planning/test-baselines.yml`.

Requirements: 32.3, 32.4, 32.5, 2.7
"""

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import yaml


def _node_cmd(tool: str) -> str:
    """Return the platform-correct executable name for a Node CLI shim."""
    return f"{tool}.cmd" if sys.platform == "win32" else tool


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
        args = list(test_args) or ["tests/"]
        try:
            # Use the interpreter running this process so the collection happens
            # inside the same resolved environment as the suite itself.
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "--collect-only", "-q"] + args,
                cwd=self.repo_root / "backend",
                capture_output=True,
                text=True,
                timeout=300,
            )

            output = result.stdout + result.stderr

            # A collection error must not be reported as a count.
            if re.search(r"\d+\s+error", output) or result.returncode not in (0, 5):
                self.errors.append(
                    f"pytest collection exited {result.returncode}: "
                    f"{output.strip().splitlines()[-1] if output.strip() else 'no output'}"
                )
                return None

            # `pytest --collect-only -q` ends with "3498 tests collected in 5.23s".
            match = re.search(r"(\d+)\s+tests? collected", output)
            if match:
                return int(match.group(1))

            self.errors.append("pytest collection: could not parse collected count")
            return None

        except subprocess.TimeoutExpired:
            self.errors.append("pytest collection timed out (300s)")
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
            # `vitest list --json` prints one JSON array entry per collected case.
            result = subprocess.run(
                [_node_cmd("npx"), "vitest", "list", "--json", "--run"],
                cwd=self.repo_root / "frontend",
                capture_output=True,
                text=True,
                timeout=600,
            )

            if result.returncode != 0:
                self.errors.append(
                    f"vitest collection failed with exit code {result.returncode}: "
                    f"{result.stderr.strip()[-300:]}"
                )
                return None

            return self._count_vitest_json(result.stdout)

        except FileNotFoundError:
            self.errors.append("vitest collection: npx not found on PATH")
            return None
        except subprocess.TimeoutExpired:
            self.errors.append("vitest collection timed out (600s)")
            return None
        except Exception as e:
            self.errors.append(f"vitest collection failed: {e}")
            return None

    @staticmethod
    def _count_vitest_json(stdout: str) -> Optional[int]:
        """Count collected cases from `vitest list --json` output."""
        # The JSON payload may be preceded by CLI banner lines.
        start = stdout.find("[")
        if start == -1:
            return None
        try:
            data = json.loads(stdout[start:])
        except json.JSONDecodeError:
            return None
        if isinstance(data, list):
            return len(data)
        return None

    def collect_playwright_mocked_count(self) -> Optional[int]:
        """
        Collect the mocked Playwright case count from the runner itself.

        Uses `playwright test --list --project=mocked`, which is the authoritative
        collection for the project defined in `frontend/playwright.config.ts`
        (all `*.spec.ts` under `e2e/tests` except `*.live.spec.ts`).

        Returns:
            Number of mocked cases, or None if collection fails
        """
        frontend = self.repo_root / "frontend"
        if not (frontend / "playwright.config.ts").exists():
            self.errors.append(
                f"Playwright config not found: {frontend / 'playwright.config.ts'}"
            )
            return None

        try:
            result = subprocess.run(
                [
                    _node_cmd("npx"),
                    "playwright",
                    "test",
                    "--list",
                    "--project=mocked",
                    "--reporter=json",
                ],
                cwd=frontend,
                capture_output=True,
                text=True,
                timeout=600,
            )

            count = self._count_playwright_json(result.stdout)
            if count is not None:
                return count

            # `--reporter=list` style tail: "Total: 194 tests in 41 files"
            match = re.search(r"Total:\s+(\d+)\s+tests?", result.stdout + result.stderr)
            if match:
                return int(match.group(1))

            self.errors.append(
                f"Playwright collection: could not parse case count "
                f"(exit {result.returncode})"
            )
            return None

        except FileNotFoundError:
            self.errors.append("Playwright collection: npx not found on PATH")
            return None
        except subprocess.TimeoutExpired:
            self.errors.append("Playwright collection timed out (600s)")
            return None

    @staticmethod
    def _count_playwright_json(stdout: str) -> Optional[int]:
        """Count leaf cases in `playwright test --list --reporter=json` output."""
        start = stdout.find("{")
        if start == -1:
            return None
        try:
            data = json.loads(stdout[start:])
        except json.JSONDecodeError:
            return None

        def count_specs(suites: List[dict]) -> int:
            total = 0
            for suite in suites or []:
                total += len(suite.get("specs", []) or [])
                total += count_specs(suite.get("suites", []) or [])
            return total

        if isinstance(data, dict) and "suites" in data:
            return count_specs(data["suites"])
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

        content = self.remediation_record_path.read_text(encoding="utf-8", errors="replace")

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
            content = test_file.read_text(encoding="utf-8", errors="replace")
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
            content = test_file.read_text(encoding="utf-8", errors="replace")
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
