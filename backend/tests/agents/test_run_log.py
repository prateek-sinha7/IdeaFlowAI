"""Unit tests for agents/execution_engine/run_log.py — RunLog (R-23, AC-13, F-09).

Covers:
  - write() appends one JSON object per line to <root>/.logs/run-logs.jsonl.
  - Every line carries `ts` (ISO-8601) and `event`.
  - Multiple writes append (not overwrite).
  - A non-serializable field degrades to repr() instead of raising.
  - An unwritable sandbox root never raises (logging must not fail a run).
"""

from __future__ import annotations

import json
import stat
from datetime import datetime
from pathlib import Path

from agents.execution_engine.run_log import RunLog


def test_write_creates_logs_file_at_expected_path(tmp_path: Path) -> None:
    log = RunLog(tmp_path)
    log.write("step_start", agent_id="a1")

    log_path = tmp_path / ".logs" / "run-logs.jsonl"
    assert log_path.exists()


def test_write_line_carries_ts_and_event(tmp_path: Path) -> None:
    log = RunLog(tmp_path)
    log.write("step_start", agent_id="a1", instance_id="i1")

    log_path = tmp_path / ".logs" / "run-logs.jsonl"
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    entry = json.loads(lines[0])
    assert entry["event"] == "step_start"
    assert entry["agent_id"] == "a1"
    assert entry["instance_id"] == "i1"

    # ts is ISO-8601 and parseable.
    datetime.fromisoformat(entry["ts"])


def test_write_appends_across_multiple_calls(tmp_path: Path) -> None:
    log = RunLog(tmp_path)
    log.write("step_start", agent_id="a1")
    log.write("step_end", agent_id="a1")
    log.write("agent_error", agent_id="a2", error="boom")

    log_path = tmp_path / ".logs" / "run-logs.jsonl"
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3

    events = [json.loads(line)["event"] for line in lines]
    assert events == ["step_start", "step_end", "agent_error"]


def test_non_serializable_value_degrades_to_repr(tmp_path: Path) -> None:
    class Unserializable:
        def __repr__(self) -> str:
            return "<Unserializable-thing>"

    log = RunLog(tmp_path)
    log.write("tool_call", tool="internet", payload=Unserializable())

    log_path = tmp_path / ".logs" / "run-logs.jsonl"
    entry = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
    assert entry["payload"] == "<Unserializable-thing>"


def test_unwritable_root_does_not_raise(tmp_path: Path) -> None:
    root = tmp_path / "readonly_root"
    root.mkdir()
    root.chmod(stat.S_IREAD | stat.S_IEXEC)  # read+execute only, no write

    try:
        log = RunLog(root)
        # Must not raise — a logging failure must never fail a run.
        log.write("step_start", agent_id="a1")

        log_path = root / ".logs" / "run-logs.jsonl"
        assert not log_path.exists()
    finally:
        # Restore permissions so tmp_path cleanup can remove the directory.
        root.chmod(stat.S_IRWXU)
