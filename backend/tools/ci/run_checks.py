"""
Bounded multi-check runner for CI checks with strict enforcement.

This module implements ci/run_checks.py as a standard-library runner over
committed, schema-validated, allow-listed argv arrays. It enforces:
- Bounds: max 100 total checks per CI evaluation
- Timeout: a per-check wall-clock timeout (hard ceiling MAX_CHECK_TIMEOUT_SECONDS)
- Sequencing: topological order; EVERY check runs to completion so each gets
  its own sub-verdict, and the runner exits non-zero if any mandatory one failed
- Audit logging: complete execution trail for every check
- Visibility: a failed check's captured output is printed to the job log (as a
  collapsible group + an error annotation under GitHub Actions) and summarised
  in ``$GITHUB_STEP_SUMMARY`` — not only buried in the JSON evidence artifact
"""

import importlib.metadata
import json
import logging
import os
import platform
import secrets
import subprocess
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Any, TextIO
from xml.sax.saxutils import escape as _xml_escape
from xml.sax.saxutils import quoteattr as _xml_quoteattr


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
    #: Untruncated output, written to a per-check ``.log`` file by
    #: ``write_full_logs``. Deliberately NOT in ``to_dict``: the JSON evidence
    #: carries the bounded head+tail excerpt in ``stdout``/``stderr``.
    full_stdout: str = field(default="", repr=False)
    full_stderr: str = field(default="", repr=False)

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
        }


#: Hard upper bound on a single check's wall-clock time. Every calling job also
#: declares its own `timeout-minutes`, so this is the inner of two bounds.
MAX_CHECK_TIMEOUT_SECONDS = 1800

#: ``uv run`` options that consume the following argv element as their value.
#: Used only to find the real tool behind a ``uv run [opts] <tool> ...`` wrapper.
_UV_RUN_VALUE_OPTIONS = frozenset(
    {"--with", "--group", "--extra", "--python", "-p", "--project", "--directory"}
)


def _tool_executable(command: list[str]) -> str:
    """Return the tool a check actually runs, unwrapping ``uv run [opts]``."""
    argv = list(command)
    if len(argv) >= 2 and Path(argv[0]).name in ("uv", "uv.exe") and argv[1] == "run":
        rest = argv[2:]
        i = 0
        while i < len(rest) and rest[i].startswith("-"):
            has_inline_value = "=" in rest[i]
            i += 2 if rest[i] in _UV_RUN_VALUE_OPTIONS and not has_inline_value else 1
        argv = rest[i:]
    return Path(argv[0]).name if argv else ""


def detect_tool_version(command: list[str]) -> str:
    """Best-effort version of the tool a check runs, without spawning anything.

    The runner itself executes under ``uv run --frozen`` in the same locked venv
    as the checks, so a console script's owning distribution (``lint-imports`` ->
    ``import-linter``) reports the exact version the check used. ``python`` maps
    to the interpreter version. Anything not installed as a Python console script
    (npm, shell tools) returns ``""`` — the evidence then says "unknown" rather
    than a guessed number.
    """
    exe = _tool_executable(command)
    if not exe:
        return ""
    if exe.startswith("python"):
        return f"python {platform.python_version()}"
    name = exe[:-4] if exe.endswith(".exe") else exe
    for ep in importlib.metadata.entry_points(group="console_scripts", name=name):
        dist = ep.dist
        if dist is not None:
            return f"{dist.name} {dist.version}"
    # Native-binary wheels (ruff) install the executable as a data script, not a
    # console_scripts entry point; their distribution carries the same name.
    try:
        return f"{name} {importlib.metadata.version(name)}"
    except importlib.metadata.PackageNotFoundError:
        return ""


def _gh_escape_data(value: str) -> str:
    """Escape a GitHub Actions workflow-command message."""
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _gh_escape_property(value: str) -> str:
    """Escape a GitHub Actions workflow-command property (e.g. ``title=``)."""
    return _gh_escape_data(value).replace(":", "%3A").replace(",", "%2C")


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
    #: Max characters of each stream kept INLINE (JSON evidence, job log, step
    #: summary). Split evenly between the head and the tail: tools print their
    #: first findings at the top and their summary ("✖ 150 problems", pytest's
    #: short summary) at the bottom, so a head-only cut dropped the verdict.
    #: The untruncated streams go to per-check .log files (write_full_logs).
    LOG_MAX_BYTES = 16384

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

    @staticmethod
    def _truncate_log(text: str, max_bytes: int = LOG_MAX_BYTES) -> str:
        """Bound ``text`` to about ``max_bytes`` characters, keeping head AND tail.

        This only truncates; it does not redact. Secrets must not reach a check's
        output in the first place (GitHub masks registered secrets in the job
        log, but not inside uploaded artifacts).

        Args:
            text: The captured stream.
            max_bytes: Characters to keep in total (half from each end).

        Returns:
            ``text`` unchanged if it fits, else head + an omission marker + tail.
        """
        if not text or len(text) <= max_bytes:
            return text or ""
        head = max_bytes // 2
        tail = max_bytes - head
        omitted = len(text) - head - tail
        return (
            f"{text[:head]}\n"
            f"... (truncated, {omitted} characters omitted; "
            f"full output is in the check's .log evidence file) ...\n"
            f"{text[-tail:]}"
        )

    def write_full_logs(self, directory: Path, prefix: str) -> list[Path]:
        """Write each executed check's untruncated output to ``<prefix>-<id>.log``.

        Args:
            directory: Evidence directory (created if missing).
            prefix: File-name prefix, normally the results file's producer stem.

        Returns:
            The paths written, in execution order.
        """
        directory.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for result in self.results:
            path = directory / f"{prefix}-{result.check_id}.log"
            body = (
                f"$ {' '.join(result.command)}\n"
                f"# status={result.status.value} exit_code={result.exit_code} "
                f"duration={result.duration_seconds:.2f}s\n"
                f"----- stdout -----\n{result.full_stdout or result.stdout}\n"
                # Timeout / spawn errors set only the short ``stderr`` message.
                f"----- stderr -----\n{result.full_stderr or result.stderr}\n"
            )
            path.write_text(body, encoding="utf-8")
            written.append(path)
        return written

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
            # An explicit config value wins; otherwise read the installed version.
            tool_version=check.tool_version or detect_tool_version(check.command),
        )

        try:
            logger.info(f"Starting check: {check.check_id}")
            logger.debug(f"Command: {' '.join(check.command)}")

            proc = subprocess.Popen(
                check.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                # Critical: never enable shell execution — argv-list only. The
                # IN-02 ledger ratchet greps backend/ for the literal enabled form,
                # so do not spell it out here (even in prose) or the guard trips.
                shell=False,
                text=True,
                # Explicit UTF-8 (tools print ▲ ✓ ✖), and never crash the runner
                # on a stray undecodable byte.
                encoding="utf-8",
                errors="replace",
            )

            try:
                stdout, stderr = proc.communicate(timeout=check.timeout_seconds)
                result.exit_code = proc.returncode
                result.full_stdout = stdout or ""
                result.full_stderr = stderr or ""
                result.stdout = self._truncate_log(result.full_stdout)
                result.stderr = self._truncate_log(result.full_stderr)
                result.status = (
                    CheckStatus.SUCCESS if proc.returncode == 0 else CheckStatus.FAILURE
                )

            except subprocess.TimeoutExpired:
                proc.kill()
                # Reap with communicate(), NOT wait(): communicate() already started
                # reader threads on the stdout/stderr pipes, and wait() does not drain
                # or join them — it blocked for the full 5s grace on every timeout
                # (observed: a 1s-timeout check reporting ~6s). communicate() closes the
                # pipes and joins those threads, so a killed child is reaped promptly.
                try:
                    proc.communicate(timeout=5)
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
        Execute every check in dependency order; a failure never stops the run.

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

    @staticmethod
    def _failure_output(result: CheckResult) -> str:
        """The captured stdout + stderr of a check, whichever are non-empty."""
        parts = [p.rstrip() for p in (result.stdout, result.stderr) if p.strip()]
        return "\n".join(parts) if parts else "(no output captured)"

    def report_failures(self, stream: TextIO, *, github_actions: bool) -> None:
        """Print every non-successful check's captured output to ``stream``.

        Without this the job log only says "status: failure" and the reason is
        hidden in the JSON evidence artifact. Under GitHub Actions each failure
        becomes a collapsible ``::group::`` plus an ``::error::`` annotation.
        The tool output is fenced with ``::stop-commands::`` so text a tool
        prints (e.g. a test that echoes ``::set-env``) can never be interpreted
        as a workflow command.
        """
        failed = [r for r in self.results if r.status != CheckStatus.SUCCESS]
        if not failed:
            return
        for result in failed:
            header = (
                f"{result.check_id} — {result.status.value} "
                f"(exit_code={result.exit_code})"
            )
            output = self._failure_output(result)
            if github_actions:
                token = secrets.token_hex(16)
                stream.write(f"::group::FAILED {header}\n")
                stream.write(f"::stop-commands::{token}\n")
                stream.write(f"{output}\n")
                stream.write(f"::{token}::\n")
                stream.write("::endgroup::\n")
                first_line = next(
                    (ln for ln in output.splitlines() if ln.strip()), output
                )
                stream.write(
                    f"::error title={_gh_escape_property(result.check_id)}::"
                    f"{_gh_escape_data(f'{header}: {first_line}')}\n"
                )
            else:
                stream.write(f"----- FAILED {header} -----\n{output}\n")
        stream.flush()

    def to_step_summary(self) -> str:
        """Markdown verdict table (plus failure output) for ``$GITHUB_STEP_SUMMARY``."""
        lines = [
            "### Check results",
            "",
            "| Check | Result | Exit code | Duration | Tool |",
            "|---|---|---|---|---|",
        ]
        for r in self.results:
            icon = "✅" if r.status == CheckStatus.SUCCESS else "❌"
            lines.append(
                f"| `{r.check_id}` | {icon} {r.status.value} | {r.exit_code} "
                f"| {r.duration_seconds:.1f}s | {r.tool_version or '—'} |"
            )
        for r in self.results:
            if r.status == CheckStatus.SUCCESS:
                continue
            # A fence longer than any backtick run in the output cannot be closed
            # early by that output.
            output = self._failure_output(r)
            fence = "`" * max(3, _longest_backtick_run(output) + 1)
            lines += [
                "",
                f"<details><summary>{_xml_escape(r.check_id)} output</summary>",
                "",
                fence,
                output,
                fence,
                "",
                "</details>",
            ]
        return "\n".join(lines) + "\n"

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
            # Every interpolated value is escaped: tool output routinely contains
            # quotes, `<`, `&` (import-linter's `->`, pytest reprs), which made
            # the raw-attribute form unparseable XML.
            xml_lines.append(
                f"    <testcase name={_xml_quoteattr(result.check_id)} "
                f'time="{result.duration_seconds:.2f}">'
            )

            if result.status != CheckStatus.SUCCESS:
                message = (
                    f"Status: {result.status.value}, exit_code: {result.exit_code}"
                )
                details = self._failure_output(result)
                xml_lines.append(
                    f"      <failure message={_xml_quoteattr(message)}>"
                    f"{_xml_escape(details)}</failure>"
                )

            xml_lines.append("    </testcase>")

        xml_lines.extend(
            [
                "  </testsuite>",
                "</testsuites>",
            ]
        )

        return "\n".join(xml_lines)


def _longest_backtick_run(text: str) -> int:
    """Length of the longest run of consecutive backticks in ``text``."""
    longest = current = 0
    for ch in text:
        current = current + 1 if ch == "`" else 0
        longest = max(longest, current)
    return longest


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

    # utf-8-sig: explicit UTF-8 (not the platform default, cp1252 on Windows) and
    # tolerant of the BOM some Windows editors prepend to JSON files.
    with open(config_path, encoding="utf-8-sig") as f:
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

        # Surface the reason for every failure in the job log itself.
        runner.report_failures(
            sys.stdout, github_actions=os.environ.get("GITHUB_ACTIONS") == "true"
        )
        step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if step_summary:
            try:
                with open(step_summary, "a", encoding="utf-8") as f:
                    f.write(runner.to_step_summary())
            except OSError as e:
                logger.warning(f"Could not write step summary: {e}")

        # Untruncated per-check logs beside the JSON evidence, so the uploaded
        # artifact always holds the complete tool output.
        if output_json:
            prefix = output_json.stem.removesuffix("-results")
            for path in runner.write_full_logs(output_json.parent, prefix):
                logger.info(f"Full output written to {path}")

        # Output results
        if output_json:
            with open(output_json, "w", encoding="utf-8") as f:
                f.write(runner.to_json())
            logger.info(f"Results written to {output_json}")

        if output_junit:
            with open(output_junit, "w", encoding="utf-8") as f:
                f.write(runner.to_junit())
            logger.info(f"JUnit results written to {output_junit}")

        return exit_code

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
