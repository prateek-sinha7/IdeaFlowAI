#!/usr/bin/env python3
"""Run the builder's live eval set (operator only: it calls a paid model; never CI).

A thin wrapper: the harness needs the Velocity backend (the real builder turn, its
tools and model), so it lives in ``backend/tools/builder_eval/``. This script finds
that backend from its own location and runs the eval-set runner there with ``uv``,
passing every argument through. It is not in the builder's script allow-list.

Usage:
  python run_evals.py --out <folder> [--effort default|highest] [--critic] [--only R3 H1]

See ``backend/tools/builder_eval/run_eval_set.py`` and ``requests.md`` there.
Standard library only.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

# <backend>/app/agents/workflow_builder/skills/velocity-workflow-creator/scripts/run_evals.py
BACKEND = Path(__file__).resolve().parents[6]


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not (BACKEND / "tools" / "builder_eval" / "run_eval_set.py").is_file():
        print(f"no backend checkout found at {BACKEND}", file=sys.stderr)
        return 2
    uv = shutil.which("uv")
    if uv is None:
        print("uv is not installed; run from backend/: uv run python -m tools.builder_eval.run_eval_set ...",
              file=sys.stderr)
        return 2
    return subprocess.call([uv, "run", "python", "-m", "tools.builder_eval.run_eval_set", *args], cwd=BACKEND)  # noqa: S603


if __name__ == "__main__":
    raise SystemExit(main())
