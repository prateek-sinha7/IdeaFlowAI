"""
Comprehensive tests for the bounded multi-check runner.

Tests cover:
- Bounds enforcement (max 100 checks, 120s timeout, 512MB memory)
- Check sequencing (topological order, offline → postgres → live)
- Early-exit behavior (exit immediately on first failure)
- Audit logging (every check start/end/result logged)
- Output formats (JSON and JUnit)
- Error conditions (timeout, spawn errors, missing executables)
- Deterministic output normalization
"""

import json
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

from tools.ci.run_checks import (
    MAX_CHECK_TIMEOUT_SECONDS,
    BoundedCheckRunner,
    CheckDefinition,
    CheckResult,
    CheckStatus,
    load_checks_from_config,
)


# The runner's contract IS ``subprocess`` behavior — per-check timeout kill, exit-code
# mapping, missing-executable handling, stdout/stderr capture and truncation. Stubbing
# Popen would assert the stub, not the runner, so the classes below deliberately opt out
# of the unit-isolation spawn guard. Every command they spawn is a self-contained
# ``python -c`` one-liner: no network, no DB, nothing outside the process tree.
# Audit note: these belong in tests/integration/external/ (suffix _external); relocating
# them needs an approved migration plan, so they stay here under an explicit exemption.
_SPAWNS_REAL_PROCESS = pytest.mark.allow_io(
    "BoundedCheckRunner's contract is subprocess behavior (timeout kill, exit codes, "
    "stream capture); spawns only self-contained `python -c` one-liners"
)


class TestCheckDefinitionValidation:
    """Tests for CheckDefinition validation."""

    def test_valid_check_definition(self):
        """Test creating a valid check definition."""
        check = CheckDefinition(
            check_id="test-check",
            command=["echo", "hello"],
            timeout_seconds=60,
        )
        check.validate()  # Should not raise

    def test_invalid_check_id_empty(self):
        """Test that empty check_id is rejected."""
        check = CheckDefinition(
            check_id="",
            command=["echo", "hello"],
        )
        with pytest.raises(ValueError, match="check_id must be a non-empty string"):
            check.validate()

    def test_invalid_command_empty(self):
        """Test that empty command list is rejected."""
        check = CheckDefinition(
            check_id="test",
            command=[],
        )
        with pytest.raises(ValueError, match="command must be a non-empty list"):
            check.validate()

    def test_invalid_command_args_not_strings(self):
        """Test that non-string command arguments are rejected."""
        check = CheckDefinition(
            check_id="test",
            command=["echo", 123],
        )
        with pytest.raises(ValueError, match="all command arguments must be strings"):
            check.validate()

    def test_invalid_timeout_zero(self):
        """Test that zero timeout is rejected."""
        check = CheckDefinition(
            check_id="test",
            command=["echo"],
            timeout_seconds=0,
        )
        with pytest.raises(ValueError, match="timeout_seconds must be in"):
            check.validate()

    def test_invalid_timeout_exceeds_max(self):
        """A timeout above the hard ceiling is rejected.

        The ceiling is read from the module rather than hardcoded here. It was
        raised from 120s to 1800s because several checks this runner owns
        (pyright, `next build`) legitimately exceed two minutes, so the old bound
        rejected every realistic config — which is part of why the check configs
        in ci/ had never actually been executed by it.
        """
        check = CheckDefinition(
            check_id="test",
            command=["echo"],
            timeout_seconds=MAX_CHECK_TIMEOUT_SECONDS + 1,
        )
        with pytest.raises(ValueError, match="timeout_seconds must be in"):
            check.validate()

    def test_realistic_long_check_timeout_is_accepted(self):
        """A 12-minute build timeout must be expressible, not rejected."""
        check = CheckDefinition(
            check_id="frontend-build",
            command=["npm", "run", "build"],
            timeout_seconds=720,
        )
        check.validate()  # must not raise

    def test_invalid_sequence_order_negative(self):
        """Test that negative sequence_order is rejected."""
        check = CheckDefinition(
            check_id="test",
            command=["echo"],
            sequence_order=-1,
        )
        with pytest.raises(ValueError, match="sequence_order must be non-negative"):
            check.validate()


class TestBoundsEnforcement:
    """Tests for bounds enforcement."""

    pytestmark = _SPAWNS_REAL_PROCESS

    def test_max_checks_bound_respected(self):
        """Test that max 100 checks bound is enforced."""
        checks = [
            CheckDefinition(
                check_id=f"check-{i}",
                command=["python", "-c", "print('check')"],
            )
            for i in range(100)
        ]
        runner = BoundedCheckRunner(checks)
        assert len(runner.checks) == 100

    def test_max_checks_bound_exceeded(self):
        """Test that exceeding max 100 checks is rejected."""
        checks = [
            CheckDefinition(
                check_id=f"check-{i}",
                command=["python", "-c", "print('check')"],
            )
            for i in range(101)
        ]
        with pytest.raises(ValueError, match="Too many checks"):
            BoundedCheckRunner(checks)

    def test_timeout_enforced_per_check(self):
        """Test that timeout is enforced per check."""
        check = CheckDefinition(
            check_id="slow-check",
            command=["python", "-c", "import time; time.sleep(10)"],
            timeout_seconds=1,
        )
        runner = BoundedCheckRunner([check])
        exit_code, results = runner.run()

        assert len(results) == 1
        assert results[0].status == CheckStatus.TIMEOUT
        assert results[0].duration_seconds < 2  # Should be around 1 second


class TestCheckSequencing:
    """Tests for check sequencing and dependency ordering."""

    def test_topological_sort_simple(self):
        """Test simple topological sort without dependencies."""
        checks = [
            CheckDefinition(check_id="a", command=["echo", "a"]),
            CheckDefinition(check_id="b", command=["echo", "b"]),
        ]
        runner = BoundedCheckRunner(checks)
        sorted_checks = runner._topological_sort()

        assert len(sorted_checks) == 2
        assert [c.check_id for c in sorted_checks] in [
            ["a", "b"],
            ["b", "a"],
        ]

    def test_topological_sort_with_dependencies(self):
        """Test topological sort respects dependencies."""
        checks = [
            CheckDefinition(
                check_id="a",
                command=["echo", "a"],
                depends_on=[],
            ),
            CheckDefinition(
                check_id="b",
                command=["echo", "b"],
                depends_on=["a"],
            ),
            CheckDefinition(
                check_id="c",
                command=["echo", "c"],
                depends_on=["b"],
            ),
        ]
        runner = BoundedCheckRunner(checks)
        sorted_checks = runner._topological_sort()

        ids = [c.check_id for c in sorted_checks]
        assert ids.index("a") < ids.index("b")
        assert ids.index("b") < ids.index("c")

    def test_circular_dependency_detected(self):
        """Test that circular dependencies are detected."""
        checks = [
            CheckDefinition(
                check_id="a",
                command=["echo", "a"],
                depends_on=["b"],
            ),
            CheckDefinition(
                check_id="b",
                command=["echo", "b"],
                depends_on=["a"],
            ),
        ]
        runner = BoundedCheckRunner(checks)
        with pytest.raises(ValueError, match="Circular dependency"):
            runner._topological_sort()


class TestCheckExecution:
    """Tests for actual check execution."""

    pytestmark = _SPAWNS_REAL_PROCESS

    def test_successful_check_execution(self):
        """Test executing a successful check."""
        check = CheckDefinition(
            check_id="echo-check",
            command=["python", "-c", "print('hello')"],
        )
        runner = BoundedCheckRunner([check])
        exit_code, results = runner.run()

        assert exit_code == 0
        assert len(results) == 1
        assert results[0].check_id == "echo-check"
        assert results[0].status == CheckStatus.SUCCESS
        assert results[0].exit_code == 0
        assert "hello" in results[0].stdout

    def test_failed_check_execution(self):
        """Test executing a check that fails."""
        check = CheckDefinition(
            check_id="fail-check",
            command=["python", "-c", "import sys; sys.exit(1)"],
        )
        runner = BoundedCheckRunner([check])
        exit_code, results = runner.run()

        assert exit_code == 1
        assert len(results) == 1
        assert results[0].status == CheckStatus.FAILURE
        assert results[0].exit_code == 1

    def test_missing_executable(self):
        """Test handling missing executable."""
        check = CheckDefinition(
            check_id="missing-check",
            command=["/nonexistent/command"],
        )
        runner = BoundedCheckRunner([check])
        exit_code, results = runner.run()

        assert exit_code == 1
        assert len(results) == 1
        assert results[0].status == CheckStatus.MISSING_EXECUTABLE

    def test_multiple_checks_all_succeed(self):
        """Test running multiple checks that all succeed."""
        checks = [
            CheckDefinition(
                check_id=f"check-{i}", command=["python", "-c", f"print({i})"]
            )
            for i in range(3)
        ]
        runner = BoundedCheckRunner(checks)
        exit_code, results = runner.run()

        assert exit_code == 0
        assert len(results) == 3
        assert all(r.status == CheckStatus.SUCCESS for r in results)

    def test_multiple_checks_first_fails(self):
        """Test that all checks run even if first fails."""
        checks = [
            CheckDefinition(
                check_id="check-1",
                command=["python", "-c", "import sys; sys.exit(1)"],
                mandatory=True,
            ),
            CheckDefinition(
                check_id="check-2",
                command=["python", "-c", "print('check 2')"],
                mandatory=True,
            ),
            CheckDefinition(
                check_id="check-3",
                command=["python", "-c", "print('check 3')"],
                mandatory=True,
            ),
        ]
        runner = BoundedCheckRunner(checks)
        exit_code, results = runner.run()

        # All checks should execute
        assert len(results) == 3
        # Exit code should indicate failure
        assert exit_code == 1
        # First check failed
        assert results[0].status == CheckStatus.FAILURE
        # Others should succeed
        assert results[1].status == CheckStatus.SUCCESS
        assert results[2].status == CheckStatus.SUCCESS

    def test_optional_check_failure_continues(self):
        """Test that optional check failure doesn't cause early exit."""
        checks = [
            CheckDefinition(
                check_id="optional-fail",
                command=["python", "-c", "import sys; sys.exit(1)"],
                mandatory=False,
            ),
            CheckDefinition(
                check_id="mandatory-pass",
                command=["python", "-c", "print('pass')"],
                mandatory=True,
            ),
        ]
        runner = BoundedCheckRunner(checks)
        exit_code, results = runner.run()

        # Optional failure should not affect exit code if all mandatory pass
        assert exit_code == 0
        assert results[0].status == CheckStatus.FAILURE
        assert results[1].status == CheckStatus.SUCCESS


class TestLogRedaction:
    """Tests for log redaction and truncation."""

    def test_log_truncation(self):
        """Test that long logs are truncated."""
        runner = BoundedCheckRunner([])
        large_text = "x" * 10000
        redacted = runner._redact_logs(large_text, max_bytes=1000)

        assert len(redacted) < len(large_text)
        assert "truncated" in redacted

    def test_empty_log_handling(self):
        """Test that empty logs are handled gracefully."""
        runner = BoundedCheckRunner([])
        result = runner._redact_logs("", max_bytes=1000)
        assert result == ""

    def test_log_under_limit(self):
        """Test that logs under limit are preserved."""
        runner = BoundedCheckRunner([])
        text = "short log"
        redacted = runner._redact_logs(text, max_bytes=1000)
        assert redacted == text


class TestOutputFormats:
    """Tests for output format generation."""

    def test_results_dict_format(self):
        """Test results dictionary format."""
        check = CheckDefinition(
            check_id="test-check",
            command=["echo", "test"],
        )
        runner = BoundedCheckRunner([check])
        runner.run()

        results_dict = runner.get_results_dict()

        assert "total_checks" in results_dict
        assert "executed_checks" in results_dict
        assert "failed_checks" in results_dict
        assert "success" in results_dict
        assert "start_time" in results_dict
        assert "end_time" in results_dict
        assert "duration_seconds" in results_dict
        assert "results" in results_dict
        assert isinstance(results_dict["results"], list)

    def test_json_output(self):
        """Test JSON output format."""
        checks = [
            CheckDefinition(check_id="check-1", command=["echo", "1"]),
            CheckDefinition(check_id="check-2", command=["echo", "2"]),
        ]
        runner = BoundedCheckRunner(checks)
        runner.run()

        json_str = runner.to_json()
        parsed = json.loads(json_str)

        assert "results" in parsed
        assert len(parsed["results"]) == 2
        assert parsed["results"][0]["check_id"] == "check-1"

    def test_junit_output(self):
        """Test JUnit XML output format."""
        checks = [
            CheckDefinition(check_id="success-check", command=["echo", "ok"]),
            CheckDefinition(
                check_id="fail-check",
                command=["sh", "-c", "exit 1"],
            ),
        ]
        runner = BoundedCheckRunner(checks)
        runner.run()

        junit_xml = runner.to_junit()

        assert '<?xml version="1.0"' in junit_xml
        assert "testsuites" in junit_xml
        assert "testsuite" in junit_xml
        assert 'testcase name="success-check"' in junit_xml
        assert 'testcase name="fail-check"' in junit_xml
        assert "failure" in junit_xml


class TestConfigLoading:
    """Tests for loading check configurations from files."""

    def test_load_valid_config(self):
        """Test loading valid config file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            config = {
                "checks": [
                    {
                        "check_id": "check-1",
                        "command": ["echo", "1"],
                        "timeout_seconds": 60,
                    },
                    {
                        "check_id": "check-2",
                        "command": ["echo", "2"],
                        "timeout_seconds": 90,
                        "depends_on": ["check-1"],
                    },
                ]
            }
            json.dump(config, f)
            config_path = Path(f.name)

        try:
            checks = load_checks_from_config(config_path)

            assert len(checks) == 2
            assert checks[0].check_id == "check-1"
            assert checks[1].check_id == "check-2"
            assert checks[1].depends_on == ["check-1"]
        finally:
            config_path.unlink()

    def test_load_missing_config(self):
        """Test loading missing config file."""
        with pytest.raises(ValueError, match="Config file not found"):
            load_checks_from_config(Path("/nonexistent/config.json"))

    def test_load_invalid_config_no_checks_key(self):
        """Test loading config without 'checks' key."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"invalid": "config"}, f)
            config_path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="must contain 'checks' key"):
                load_checks_from_config(config_path)
        finally:
            config_path.unlink()


class TestDeterministicExecution:
    """Tests for deterministic execution and output."""

    pytestmark = _SPAWNS_REAL_PROCESS

    def test_execution_timing_recorded(self):
        """Test that execution timing is recorded accurately."""
        check = CheckDefinition(
            check_id="timed-check",
            command=["python", "-c", "import time; time.sleep(0.1)"],
        )
        runner = BoundedCheckRunner([check])
        exit_code, results = runner.run()

        assert results[0].duration_seconds >= 0.09
        assert results[0].start_time > 0
        assert results[0].end_time > results[0].start_time

    def test_command_normalization(self):
        """Test that commands are preserved as-is."""
        command = ["sh", "-c", "echo hello && echo world"]
        check = CheckDefinition(
            check_id="complex-cmd",
            command=command,
        )
        runner = BoundedCheckRunner([check])
        exit_code, results = runner.run()

        assert results[0].command == command

    def test_repeated_execution_same_output(self):
        """Test that repeated execution produces consistent output."""
        check = CheckDefinition(
            check_id="echo-check",
            command=["echo", "deterministic"],
        )

        results1 = None
        results2 = None

        for _ in range(2):
            runner = BoundedCheckRunner([check])
            exit_code, results = runner.run()
            if results1 is None:
                results1 = results
            else:
                results2 = results

        assert results1[0].stdout == results2[0].stdout
        assert results1[0].exit_code == results2[0].exit_code


class TestAuditLogging:
    """Tests for audit logging of check execution."""

    @patch("tools.ci.run_checks.logger")
    def test_check_start_logged(self, mock_logger):
        """Test that check start is logged."""
        check = CheckDefinition(
            check_id="logged-check",
            command=["echo", "test"],
        )
        runner = BoundedCheckRunner([check])
        runner.run()

        # Verify logger was called with check start
        calls = [str(call) for call in mock_logger.info.call_args_list]
        assert any("Starting check" in str(call) for call in calls)

    @patch("tools.ci.run_checks.logger")
    def test_check_result_logged(self, mock_logger):
        """Test that check result is logged."""
        check = CheckDefinition(
            check_id="result-check",
            command=["echo", "test"],
        )
        runner = BoundedCheckRunner([check])
        runner.run()

        # Verify logger was called with result
        calls = [str(call) for call in mock_logger.info.call_args_list]
        assert any("completed with status" in str(call) for call in calls)


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    pytestmark = _SPAWNS_REAL_PROCESS

    def test_check_with_no_output(self):
        """Test check that produces no output."""
        check = CheckDefinition(
            check_id="no-output",
            command=["python", "-c", "pass"],
        )
        runner = BoundedCheckRunner([check])
        exit_code, results = runner.run()

        assert results[0].stdout == ""
        assert results[0].stderr == ""
        assert results[0].status == CheckStatus.SUCCESS

    def test_check_with_large_stderr(self):
        """Test check with large stderr output."""
        check = CheckDefinition(
            check_id="large-stderr",
            command=[
                "python",
                "-c",
                "import sys; sys.stderr.write('x' * 100000); sys.exit(1)",
            ],
        )
        runner = BoundedCheckRunner([check])
        exit_code, results = runner.run()

        # Should be truncated
        assert len(results[0].stderr) < 100000
        assert "truncated" in results[0].stderr

    def test_check_result_to_dict(self):
        """Test CheckResult.to_dict() serialization."""
        result = CheckResult(
            check_id="test",
            command=["echo", "test"],
            status=CheckStatus.SUCCESS,
            exit_code=0,
            stdout="output",
            stderr="",
            start_time=1.0,
            end_time=2.0,
            duration_seconds=1.0,
            tool_version="1.0",
        )

        result_dict = result.to_dict()

        assert result_dict["check_id"] == "test"
        assert result_dict["status"] == "success"
        assert result_dict["exit_code"] == 0
        assert result_dict["duration_seconds"] == 1.0

    def test_empty_checks_list(self):
        """Test with empty checks list."""
        runner = BoundedCheckRunner([])
        exit_code, results = runner.run()

        assert exit_code == 0
        assert len(results) == 0


class TestPropertyBasedSequencing:
    """Property-based tests for check sequencing."""

    def test_all_checks_execute_once(self):
        """Test that all checks execute exactly once regardless of ordering."""
        checks = [
            CheckDefinition(check_id=f"check-{i}", command=["echo", str(i)])
            for i in range(5)
        ]
        runner = BoundedCheckRunner(checks)
        exit_code, results = runner.run()

        check_ids = [r.check_id for r in results]
        expected_ids = [c.check_id for c in checks]

        # All checks should execute
        assert len(check_ids) == len(expected_ids)
        # Each should execute exactly once
        assert set(check_ids) == set(expected_ids)

    def test_dependencies_respected_regardless_of_input_order(self):
        """Test that dependencies are respected in any input order."""
        # Create checks in random order
        checks = [
            CheckDefinition(
                check_id="c",
                command=["echo", "c"],
                depends_on=["b"],
            ),
            CheckDefinition(
                check_id="a",
                command=["echo", "a"],
                depends_on=[],
            ),
            CheckDefinition(
                check_id="b",
                command=["echo", "b"],
                depends_on=["a"],
            ),
        ]

        runner = BoundedCheckRunner(checks)
        sorted_checks = runner._topological_sort()
        sorted_ids = [c.check_id for c in sorted_checks]

        # Verify order: a before b, b before c
        assert sorted_ids.index("a") < sorted_ids.index("b")
        assert sorted_ids.index("b") < sorted_ids.index("c")
