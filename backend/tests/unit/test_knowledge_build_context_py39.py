"""BUG-127 / QA-KB-051 -- tools/knowledge/build_context.py must run under the
bare ``python3`` the docs name (macOS /usr/bin/python3, 3.9). It calls
``Path.write_text(..., newline=...)`` (3.10+), so the context stage dies with
TypeError after the index stage already rewrote INDEX.md / state.yaml.

Runs main() under /usr/bin/python3 with OUT_PATH redirected to a temp dir so the
real CONTEXT.md is never touched. That run is only defined where the interpreter is 3.9; CI's offline partition forbids
run-time skips, so the portable AST guard below runs everywhere instead.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
PY39 = "/usr/bin/python3"

_DRIVER = textwrap.dedent(
    """
    import sys, tempfile, pathlib
    sys.path.insert(0, {tools!r})
    import build_context as b
    b.OUT_PATH = pathlib.Path(tempfile.mkdtemp()) / "CONTEXT.md"
    b.main()
    assert b.OUT_PATH.exists()
    assert b"\\r" not in b.OUT_PATH.read_bytes()
    """
)


def _is_py39() -> bool:
    try:
        out = subprocess.run(
            [PY39, "-c", "import sys; print(sys.version_info[:2] < (3, 10))"],
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.strip()
    except OSError:
        return False
    return out == "True"


@pytest.mark.issue("BUG-127")
def test_build_context_avoids_py310_only_text_io_kwargs():
    """BUG-127 -- no ``newline=`` on Path.write_text/read_text (3.10+), on any interpreter."""
    tree = ast.parse(
        (REPO / "tools" / "knowledge" / "build_context.py").read_text(encoding="utf-8")
    )
    bad = [
        n.lineno
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr in {"write_text", "read_text"}
        and any(k.arg == "newline" for k in n.keywords)
    ]
    assert not bad, f"3.10+-only newline= at build_context.py lines {bad}"


if _is_py39():

    @pytest.mark.allow_io(
        "runs the real build_context under the system 3.9 interpreter"
    )
    @pytest.mark.issue("BUG-127")
    def test_build_context_runs_under_python39():
        """BUG-127 -- the context stage must not raise TypeError on 3.9."""
        proc = subprocess.run(
            [PY39, "-c", _DRIVER.format(tools=str(REPO / "tools" / "knowledge"))],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=REPO,
        )
        assert proc.returncode == 0, proc.stderr[-800:]
