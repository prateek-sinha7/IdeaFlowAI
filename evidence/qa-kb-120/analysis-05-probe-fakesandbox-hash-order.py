"""QA-KB-120 analysis probe (3-analyzer, 2026-10-09). NO test or application file is edited.

Question: does the test double the finalizer tests use (tests/agents/test_finalizer_v2.py::FakeSandbox)
reproduce the real failure faithfully? Its stage_exact stages ONE PATH PER git call and stops at the
first failure; the real LocalWorkspace.stage_exact (local.py:1426-1434) is ONE `git add --force --
<all paths>` that stages nothing when any pathspec is missing. build_flat_payload passes
`list(_allowlist)`, a frozenset of str, so the order depends on PYTHONHASHSEED.

Run (from backend/, offline, a few seconds):

    cd backend && ./.venv/bin/python -I ../evidence/qa-kb-120/analysis-05-probe-fakesandbox-hash-order.py

The script re-executes itself once per PYTHONHASHSEED so each value is a fresh interpreter.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
SEEDS = [str(i) for i in range(8)]

if os.environ.get("QA_KB_120_CHILD") != "1":
    lines = ["QA-KB-120 probe: FakeSandbox.stage_exact (per path) vs PYTHONHASHSEED, unmaterialized output.html"]
    seen = set()
    for seed in SEEDS:
        env = {**os.environ, "PYTHONHASHSEED": seed, "QA_KB_120_CHILD": "1"}
        out = subprocess.run([sys.executable, "-I", __file__], env=env, capture_output=True, text=True, cwd=BACKEND).stdout.strip()
        lines.append(f"PYTHONHASHSEED={seed}: {out}")
        seen.add(out.split("staged=")[-1])
    lines.append(f"distinct staged sets across {len(SEEDS)} seeds = {len(seen)}  (1 would mean deterministic)")
    text = "\n".join(lines)
    print(text)
    Path(__file__).with_name("analysis-05-probe-fakesandbox-hash-order.txt").write_text(text + "\n", encoding="utf-8")
    sys.exit(0)

# ---- child: one interpreter, one hash seed -------------------------------------------------
os.environ["DATABASE_URL"] = "postgresql://nobody:nobody@127.0.0.1:1/none"  # dead port on purpose
os.environ["RUNS_ROOT"] = tempfile.mkdtemp(prefix="qa-kb-120-fake-")
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "tests" / "agents"))

import test_finalizer_v2 as T  # noqa: E402  (the module the finalizer tests live in)
from agents.execution_engine.engine import build_flat_payload  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="qa-kb-120-fake-sb-"))
sandbox, run_id = T._setup_sandbox(tmp)
T._plant_logs(sandbox, run_id)  # output.html is NOT written
ectx = T._make_ectx(run_id, sandbox)  # deliverable_name defaults to output.html
payload = build_flat_payload(run_id, ectx)
staged = sorted(T._run_git("diff", "--cached", "--name-only", cwd=sandbox.root).splitlines())
print(f"materialized={payload.materialized} allowlist_names_missing_output={'.chain/output.html' in payload.allowlist} staged={staged}")
