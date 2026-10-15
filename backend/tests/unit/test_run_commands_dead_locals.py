"""ISS-689 — run_commands.py must carry no dead locals / undefined names (the unused
``degraded`` / ``failed`` assignments in ``_reconcile_terminal_status``)."""

import subprocess
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]


@pytest.mark.issue("ISS-689")
@pytest.mark.allow_io("runs ruff on run_commands.py as a black-box subprocess")
def test_run_commands_has_no_unused_locals():
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "app/api/run_commands.py",
            "--select",
            "F841,F821",
            "--output-format",
            "concise",
        ],
        cwd=_BACKEND,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
