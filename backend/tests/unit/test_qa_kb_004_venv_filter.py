"""QA-KB-004 / BUG-129: scan_source_files() must skip every virtualenv dir, not just `.venv`/`venv`."""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]


@pytest.mark.allow_io(
    reason="builds a tmp_path tree; REPO_ROOT patched so the real backend/ is never touched"
)
@pytest.mark.issue("BUG-129")
def test_scan_source_files_skips_prefixed_venvs(tmp_path, monkeypatch):
    """BUG-129 — .venv312 / .venv-3.13 / .venv311 must be excluded; venv_tools and environment.py stay."""
    monkeypatch.syspath_prepend(str(REPO / "tools" / "knowledge"))
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    import build_architecture as ba

    keep = [
        "backend/app/main.py",
        "backend/venv_tools/x.py",
        "backend/app/environment.py",
    ]
    drop = [
        f"backend/{d}/lib/a.py"
        for d in (
            ".venv",
            "venv",
            ".venv312",
            ".venv-3.13",
            ".venv311",
            "tests",
            "runs",
            "__pycache__",
        )
    ]
    for rel in keep + drop:
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x = 1\n")
    monkeypatch.setattr(ba, "REPO_ROOT", tmp_path)

    assert ba.scan_source_files() == sorted(keep)
