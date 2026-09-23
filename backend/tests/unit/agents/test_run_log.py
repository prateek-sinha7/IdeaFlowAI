"""Unit tests for agents/execution_engine/run_log.py — RunLog (Requirement 24).

Covers:
  - write() appends one JSON object per line to the supplied log_path.
  - The caller is responsible for supplying a per-run path
    (RunSandbox.run_log_path → <root>/.logs/{run_id}.jsonl).
  - Every line carries `ts` (ISO-8601) and `event`.
  - Multiple writes append (not overwrite).
  - A non-serializable field degrades to repr() instead of raising.
  - An unwritable parent directory never raises (logging must not fail a run).
"""

from __future__ import annotations

import json
import stat
import sys
from datetime import datetime
from pathlib import Path

import pytest

from agents.execution_engine.run_log import RunLog

# Canonical per-run log filename the engine uses via RunSandbox.run_log_path.
_LOG_NAME = "abc-run-id.jsonl"


def _log_path(root: Path) -> Path:
    """Mirrors RunSandbox.run_log_path: <root>/.logs/{run_id}.jsonl."""
    return root / ".logs" / _LOG_NAME


def test_write_creates_logs_file_at_expected_path(tmp_path: Path) -> None:
    path = _log_path(tmp_path)
    log = RunLog(path)
    log.write("step_start", agent_id="a1")

    assert path.exists()


def test_write_line_carries_ts_and_event(tmp_path: Path) -> None:
    path = _log_path(tmp_path)
    log = RunLog(path)
    log.write("step_start", agent_id="a1", instance_id="i1")

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    entry = json.loads(lines[0])
    assert entry["event"] == "step_start"
    assert entry["agent_id"] == "a1"
    assert entry["instance_id"] == "i1"

    # ts is ISO-8601 and parseable.
    datetime.fromisoformat(entry["ts"])


def test_write_appends_across_multiple_calls(tmp_path: Path) -> None:
    path = _log_path(tmp_path)
    log = RunLog(path)
    log.write("step_start", agent_id="a1")
    log.write("step_end", agent_id="a1")
    log.write("agent_error", agent_id="a2", error="boom")

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3

    events = [json.loads(line)["event"] for line in lines]
    assert events == ["step_start", "step_end", "agent_error"]


def test_non_serializable_value_degrades_to_repr(tmp_path: Path) -> None:
    class Unserializable:
        def __repr__(self) -> str:
            return "<Unserializable-thing>"

    path = _log_path(tmp_path)
    log = RunLog(path)
    log.write("tool_call", tool="internet", payload=Unserializable())

    entry = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert entry["payload"] == "<Unserializable-thing>"


@pytest.mark.skipif(
    sys.platform == "win32",
    reason=(
        "os.chmod(dir, read-only) does not block the owning user's writes on "
        "Windows the way it does on POSIX — a platform/harness gap, not a "
        "RunLog product defect. Real production target is Linux."
    ),
)
def test_unwritable_parent_does_not_raise(tmp_path: Path) -> None:
    root = tmp_path / "readonly_root"
    root.mkdir()
    root.chmod(stat.S_IREAD | stat.S_IEXEC)  # read+execute only, no write

    try:
        path = root / ".logs" / _LOG_NAME
        log = RunLog(path)
        # Must not raise — a logging failure must never fail a run.
        log.write("step_start", agent_id="a1")

        assert not path.exists()
    finally:
        # Restore permissions so tmp_path cleanup can remove the directory.
        root.chmod(stat.S_IRWXU)
