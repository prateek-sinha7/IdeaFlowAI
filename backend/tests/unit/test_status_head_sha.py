"""QA-KB-003 / BUG-128 -- status.py must report the commit sha, not DOMAIN card text."""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
STATUS = ROOT / "tools" / "knowledge" / "status.py"


def _run(*args):
    return subprocess.run(
        [sys.executable, str(STATUS), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    ).stdout


@pytest.mark.allow_io("runs the status.py CLI as a black-box subprocess")
@pytest.mark.issue("BUG-128")
def test_json_head_is_commit_sha():
    """BUG-128 -- --json `head` must equal `git rev-parse HEAD`."""
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()
    d = json.loads(_run("--json"))
    assert re.fullmatch(r"[0-9a-f]{40}", d["head"]), repr(d["head"][:40])
    assert d["head"] == sha


@pytest.mark.allow_io("runs the status.py CLI as a black-box subprocess")
@pytest.mark.issue("BUG-128")
def test_branch_line_shows_sha():
    """BUG-128 -- the branch line must read `branch: X @ <8 hex>`."""
    line = next(l for l in _run().splitlines() if l.startswith("branch:"))
    assert re.match(r"^branch: \S+ @ [0-9a-f]{8}\b", line), line
