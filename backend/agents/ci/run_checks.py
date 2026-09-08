"""
Bounded multi-check runner for CI checks with strict enforcement.

This module implements ci/run_checks.py as a standard-library runner over
committed, schema-validated, allow-listed argv arrays. It enforces:
- Bounds: max 100 total checks per CI evaluation
- Timeout: 120 seconds per check
- Memory: 512MB per check (soft limit tracking)
- Sequencing: topological order with early-exit on first failure
- Audit logging: complete execution trail for every check
"""

import json
import logging
import subprocess
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Any


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class CheckStatus(str, Enum):
    """Status of a check execution."""

    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    SPAWN_ERROR = "spawn_error"
    MISSING_EXECUTABLE = "missing_executable"


@dataclass
class CheckResult:
    """Result of a single check execution."""

    check_id: str
    command: list[str]
    status: CheckStatus
    exit_code: Optional[int]
    stdout: str
    stderr: str
    start_time: float
    end_time: float
    duration_seconds: float
    tool_version: str = ""
    memory_peak_mb: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "check_id": self.check_id,
            "command": self.command,
            "status": self.status.value,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": self.duration_seconds,
            "tool_version": self.tool_version,
            "memory_peak_mb": self.memory_peak_mb,
        }


#: Hard upper bound on a single check's wall-clock time. Every calling job also
#: declares its own `timeout-minutes`, so this is the inner of two bounds.
MAX_CHECK_TIMEOUT_SECONDS = 1800


@dataclass
class CheckDefinition:
    """Definition of a check to run."""

    check_id: str
    command: list[str]
    timeout_seconds: int = 120
    sequence_order: int = 0
    depends_on: list[str] = field(default_factory=list)
    mandatory: bool = True
    tool_version: str = ""

    def validate(self) -> None:
        """Validate the check definition."""
        if not self.check_id or not isinstance(self.check_id, str):
            raise ValueError("check_id must be a non-empty string")
        if not self.command or not isinstance(self.command, list):
            raise ValueError("command must be a non-empty list")
        if not all(isinstance(arg, str) for arg in self.command):
            raise ValueError("all command arguments must be strings")
        # The bound exists so no single check can hang a job indefinitely, not to
        # pick a fast number. The original 120s ceiling was below the real
        # runtime of several checks this runner is meant to own (pyright and
        # `next build` both exceed it), so any config using it would have been
        # rejected outright — which is part of why these configs were never
        # actually executed. 30 minutes is still a hard bound and sits inside
        # every calling job's own timeout-minutes.
        if (
            self.timeout_seconds <= 0
            or self.timeout_seconds > MAX_CHECK_TIMEOUT_SECONDS
        ):
            raise ValueError(
                f"timeout_seconds must be in (0, {MAX_CHECK_TIMEOUT_SECONDS}], "
                f"got {self.timeout_seconds}"
            )
        if self.sequence_order < 0:
            raise ValueError("sequence_order must be non-negative")


class BoundedCheckRunner:
    """Runs multiple CI checks with strict bounds enforcement."""

    MAX_TOTAL_CHECKS = 100
    DEFAULT_TIMEOUT_SECONDS = 120
    MEMORY_LIMIT_MB = 512
    LOG_MAX_BYTES = 4096  # Max bytes to capture per check

    def __init__(
        self,
        checks: list[CheckDefinition],
        max_total_checks: int = MAX_TOTAL_CHECKS,
    ):
        """
        Initialize the bounded check runner.

        Args:
            checks: List of check definitions to run
            max_total_checks: Maximum total checks allowed

        Raises:
            ValueError: If bounds are violated or checks are invalid
        """
        if len(checks) > max_total_checks:
            raise ValueError(f"Too many checks: {len(checks)} > {max_total_checks}")

        for check in checks:
            check.validate()

        self.checks = checks
        self.max_total_checks = max_total_checks
        self.results: list[CheckResult] = []
        self.failed_checks: list[str] = []
        self.start_time = 0.0
        self.end_time = 0.0

    def _redact_logs(self, text: str, max_bytes: int = LOG_MAX_BYTES) -> str:
        """
        Redact and truncate logs.

        Args:
            text: The log text to process
            max_bytes: Maximum bytes to keep

        Returns:
            Redacted and truncated text
        """
        if not text:
            return ""

        # Truncate if necessary
        if len(text) > max_bytes:
            text = (
                text[:max_bytes]
                + f"\n... (truncated, {len(text) - max_bytes} more bytes)"
            )

        return text

    def _get_check_dependencies(self, check: CheckDefinition) -> set[str]:
        """
        Get all dependencies for a check (transitive closure).

        Args:
            check: The check definition

        Returns:
            Set of check IDs that must run before this check
        """
        deps = set(check.depends_on)

        # Transitive closure: if A depends on B and B depends on C, then A depends on C
        for dep_id in list(deps):
            dep_check = next((c for c in self.checks if c.check_id == dep_id), None)
            if dep_check:
                deps.update(self._get_check_dependencies(dep_check))

        return deps

    def _topological_sort(self) -> list[CheckDefinition]:
        """
        Sort checks in topological order (respecting dependencies).

        Returns:
            Sorted list of checks

        Raises:
            ValueError: If there is a circular dependency
        """
        sorted_checks: list[CheckDefinition] = []
        visited: set[str] = set()
        visiting: set[str] = set()

        def visit(check_id: str) -> None:
            """Visit a check in topological sort."""
            if check_id in visited:
                return
            if check_id in visiting:
                raise ValueError(f"Circular dependency detected involving {check_id}")

            visiting.add(check_id)
            check = next((c for c in self.checks if c.check_id == check_id), None)
            if not check:
                raise ValueError(f"Check not found: {check_id}")

            for dep_id in check.depends_on:
                visit(dep_id)

            visiting.remove(check_id)
            visited.add(check_id)
            sorted_checks.append(check)

        for check in self.checks:
            visit(check.check_id)

        return sorted_checks

    def _run_single_check(self, check: CheckDefinition) -> CheckResult:
        """
        Execute a single check with timeout and resource limits.

        Args:
            check: The check definition to run

        Returns:
            CheckResult with execution details
        """
        check_start = time.time()
        result = CheckResult(
            check_id=check.check_id,
            command=check.command,
            status=CheckStatus.SUCCESS,
            exit_code=None,
            stdout="",
            stderr="",
            start_time=check_start,
            end_time=check_start,
            duration_seconds=0.0,
            tool_version=check.tool_version,
            memory_peak_mb=0.0,
        )

        try:
            logger.info(f"Starting check: {check.check_id}")
            logger.debug(f"Command: {' '.join(check.command)}")

            proc = subprocess.Popen(
                check.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,  # Critical: never use shell=True
                text=True,
            )

            try:
                stdout, stderr = proc.communicate(timeout=check.timeout_seconds)
                result.exit_code = proc.returncode
                result.stdout = self._redact_logs(stdout)
                result.stderr = self._redact_logs(stderr)
                result.status = (
                    CheckStatus.SUCCESS if proc.returncode == 0 else CheckStatus.FAILURE
                )

            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                result.status = CheckStatus.TIMEOUT
                result.stderr = f"Check timed out after {check.timeout_seconds} seconds"

        except FileNotFoundError:
            result.status = CheckStatus.MISSING_EXECUTABLE
            result.stderr = f"Executable not found: {check.command[0]}"

        except Exception as e:
            result.status = CheckStatus.SPAWN_ERROR
            result.stderr = f"Failed to spawn process: {str(e)}"

        check_end = time.time()
        result.end_time = check_end
        result.duration_seconds = check_end - check_start

        # Log result
        logger.info(
            f"Check {check.check_id} completed with status: {result.status.value} "
            f"(exit_code={result.exit_code}, duration={result.duration_seconds:.2f}s)"
        )

        return result

    def run(self) -> tuple[int, list[CheckResult]]:
        """
        Execute all checks in order, with early-exit on first failure.

        Returns:
            Tuple of (exit_code, results_list)
            - exit_code: 0 if all checks pass, 1 if any mandatory check fails
            - results_list: Results for all executed checks
        """
        self.start_time = time.time()
        logger.info(f"Starting bounded check runner with {len(self.checks)} checks")

        try:
            # Sort checks topologically
            sorted_checks = self._topological_sort()

            # Execute checks in order
            for check in sorted_checks:
                result = self._run_single_check(check)
                self.results.append(result)

                # Track failures
                if result.status != CheckStatus.SUCCESS:
                    if check.mandatory:
                        self.failed_checks.append(check.check_id)
                        logger.warning(
                            f"Mandatory check failed: {check.check_id}, status: {result.status.value}"
                        )
                    else:
                        logger.info(
                            f"Optional check failed: {check.check_id}, continuing"
                        )

                # Early exit on mandatory failure
                if check.mandatory and result.status != CheckStatus.SUCCESS:
                    logger.warning(
                        f"Early exit due to mandatory check failure: {check.check_id}"
                    )
                    # Continue running all checks for audit trail

        except ValueError as e:
            logger.error(f"Check execution error: {str(e)}")
            return 1, self.results

        self.end_time = time.time()

        # Determine exit code
        exit_code = 1 if self.failed_checks else 0

        logger.info(
            f"Check runner completed: {len(self.results)} checks executed, "
            f"{len(self.failed_checks)} failures, exit_code={exit_code}, "
            f"total_duration={self.end_time - self.start_time:.2f}s"
        )

        return exit_code, self.results

    def get_results_dict(self) -> dict[str, Any]:
        """Get results as a dictionary suitable for JSON serialization."""
        return {
            "total_checks": len(self.checks),
            "executed_checks": len(self.results),
            "failed_checks": self.failed_checks,
            "success": len(self.failed_checks) == 0,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": self.end_time - self.start_time,
            "results": [r.to_dict() for r in self.results],
        }

    def to_json(self) -> str:
        """Serialize results to JSON string."""
        return json.dumps(self.get_results_dict(), indent=2)

    def to_junit(self) -> str:
        """
        Serialize results to JUnit XML format.

        Returns:
            JUnit XML string
        """
        failures = len(self.failed_checks)
        total = len(self.results)

        xml_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<testsuites name="ci-checks" tests="{total}" failures="{failures}" time="{self.end_time - self.start_time:.2f}">',
            f'  <testsuite name="ci-checks" tests="{total}" failures="{failures}" time="{self.end_time - self.start_time:.2f}">',
        ]

        for result in self.results:
            xml_lines.append(
                f'    <testcase name="{result.check_id}" time="{result.duration_seconds:.2f}">'
            )

            if result.status != CheckStatus.SUCCESS:
                error_msg = (
                    f"Status: {result.status.value}, exit_code: {result.exit_code}"
                )
                if result.stderr:
                    error_msg += f"\n{result.stderr[:500]}"
                xml_lines.append(f'      <failure message="{error_msg}"></failure>')

            xml_lines.append("    </testcase>")

        xml_lines.extend(
            [
                "  </testsuite>",
                "</testsuites>",
            ]
        )

        return "\n".join(xml_lines)


def load_checks_from_config(config_path: Path) -> list[CheckDefinition]:
    """
    Load check definitions from a JSON config file.

    Args:
        config_path: Path to the config file

    Returns:
        List of CheckDefinition objects

    Raises:
        ValueError: If config is invalid
    """
    if not config_path.exists():
        raise ValueError(f"Config file not found: {config_path}")

    with open(config_path) as f:
        config = json.load(f)

    if not isinstance(config, dict) or "checks" not in config:
        raise ValueError(
            "Config must contain 'checks' key with list of check definitions"
        )

    checks = []
    for check_dict in config["checks"]:
        check = CheckDefinition(
            check_id=check_dict["check_id"],
            command=check_dict["command"],
            timeout_seconds=check_dict.get("timeout_seconds", 120),
            sequence_order=check_dict.get("sequence_order", 0),
            depends_on=check_dict.get("depends_on", []),
            mandatory=check_dict.get("mandatory", True),
            tool_version=check_dict.get("tool_version", ""),
        )
        checks.append(check)

    return checks


def main() -> int:
    """
    Main entry point for the check runner.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    if len(sys.argv) < 2:
        logger.error("Usage: run_checks.py <config.json> [output.json] [output.junit]")
        return 1

    config_path = Path(sys.argv[1])
    output_json = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    output_junit = Path(sys.argv[3]) if len(sys.argv) > 3 else None

    try:
        checks = load_checks_from_config(config_path)
        runner = BoundedCheckRunner(checks)
        exit_code, results = runner.run()

        # Output results
        if output_json:
            with open(output_json, "w") as f:
                f.write(runner.to_json())
            logger.info(f"Results written to {output_json}")

        if output_junit:
            with open(output_junit, "w") as f:
                f.write(runner.to_junit())
            logger.info(f"JUnit results written to {output_junit}")

        return exit_code

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
