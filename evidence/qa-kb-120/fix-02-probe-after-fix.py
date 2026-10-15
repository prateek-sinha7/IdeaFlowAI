"""QA-KB-120 fix-phase probe (5-fixer, 2026-10-09). Offline, real git, no model call, no DB.

After FIX (ISS-1159 prune in build_flat_payload, ISS-1179 all-or-nothing FakeSandbox.stage_exact):
  [1] the shared double now fails like LocalWorkspace.stage_exact: one missing pathspec stages
      nothing, whatever the order of the paths;
  [2] build_flat_payload on an unmaterialized output, through the double, is the same for every
      PYTHONHASHSEED: output not allowlisted, logs.jsonl + summary.md staged, no stage_exact warning;
  [3] on a real RunSandbox whose .chain/greeting.md an earlier commit tracks, an unmaterialized
      greeting.md is untracked by the stale reconciliation (a staged deletion, as git add gave before).

Run from backend/:  ./.venv/bin/python -I ../evidence/qa-kb-120/fix-02-probe-after-fix.py
"""
from __future__ import annotations

import itertools
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
SEEDS = [str(i) for i in range(8)]

if os.environ.get("QA_KB_120_FIX_CHILD") != "1":
    lines = ["QA-KB-120 fix probe (working tree)"]
    for seed in SEEDS:
        env = {**os.environ, "PYTHONHASHSEED": seed, "QA_KB_120_FIX_CHILD": "1"}
        r = subprocess.run([sys.executable, "-I", __file__], env=env, capture_output=True, text=True, cwd=BACKEND)
        lines.append(f"PYTHONHASHSEED={seed}: {r.stdout.strip() or r.stderr.strip()[-400:]}")
    text = "\n".join(lines)
    print(text)
    Path(__file__).with_name("fix-02-probe-after-fix.txt").write_text(text + "\n", encoding="utf-8")
    sys.exit(0)

# ---- child: one interpreter, one hash seed ----------------------------------------------------
os.environ["DATABASE_URL"] = "postgresql://nobody:nobody@127.0.0.1:1/none"  # dead port on purpose
os.environ["RUNS_ROOT"] = tempfile.mkdtemp(prefix="qa-kb-120-fix-")
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "tests" / "agents"))

import test_finalizer_v2 as T  # noqa: E402
from agents.execution_engine.engine import build_flat_payload  # noqa: E402

# [1] the double, all path orders, one of them missing
outcomes = set()
for order in itertools.permutations([".chain/logs.jsonl", ".chain/summary.md", ".chain/missing.html"]):
    sb, _ = T._setup_sandbox(Path(tempfile.mkdtemp(prefix="qa-kb-120-fix-d-")))
    (sb.root / ".chain").mkdir(exist_ok=True)
    (sb.root / ".chain" / "logs.jsonl").write_text("{}\n", encoding="utf-8")
    (sb.root / ".chain" / "summary.md").write_text("s\n", encoding="utf-8")
    try:
        sb.stage_exact(list(order))
        raised = False
    except RuntimeError:
        raised = True
    outcomes.add((raised, tuple(T._run_git("diff", "--cached", "--name-only", cwd=sb.root).splitlines())))

# [2] build_flat_payload, unmaterialized output.html, through the double
records: list[logging.LogRecord] = []
handler = logging.Handler()
handler.emit = records.append  # type: ignore[method-assign]
logging.getLogger("agents.execution_engine.engine").addHandler(handler)
tmp = Path(tempfile.mkdtemp(prefix="qa-kb-120-fix-sb-"))
sandbox, run_id = T._setup_sandbox(tmp)
T._plant_logs(sandbox, run_id)  # output.html is NOT written
payload = build_flat_payload(run_id, T._make_ectx(run_id, sandbox))
staged = sorted(T._run_git("diff", "--cached", "--name-only", cwd=sandbox.root).splitlines())
warned = sum("stage_exact failed" in r.getMessage() for r in records)

# [3] real RunSandbox: .chain/greeting.md tracked by an earlier commit, not materialized this time
import types  # noqa: E402
import uuid  # noqa: E402

from app.agents.sandbox import RunSandbox  # noqa: E402

records.clear()
rid = str(uuid.uuid4())
rsb = RunSandbox("u", rid, runs_root=tempfile.mkdtemp(prefix="qa-kb-120-fix-real-"))
rsb.ensure()
rsb._ws().git_init_sandbox()
(rsb.root / ".chain").mkdir(exist_ok=True)
(rsb.root / ".chain" / "greeting.md").write_text("old\n", encoding="utf-8")
T._run_git("-c", "user.email=p@p.p", "-c", "user.name=p", "add", "--force", ".chain/greeting.md", cwd=rsb.root)
T._run_git("-c", "user.email=p@p.p", "-c", "user.name=p", "commit", "-qm", "prior snapshot", cwd=rsb.root)
rsb.run_log_path.parent.mkdir(parents=True, exist_ok=True)
rsb.run_log_path.write_text('{"event":"run_terminal"}\n', encoding="utf-8")
ectx3 = types.SimpleNamespace(
    run_id=rid, user_id="u", owner_id="u", workspace_id="w",
    runner=types.SimpleNamespace(sandbox=rsb, registry=None, engine=None), final_status="failed",
    deliverable=types.SimpleNamespace(name="greeting.md", strategy="single_file", text_name=None),
    revision_ordinal=1, step_visit_counts={}, last_commit_blocked=False, completed_tasks=[], run_trace=None,
    last_streamed="",
)
p3 = build_flat_payload(rid, ectx3)
status3 = sorted(T._run_git("diff", "--cached", "--name-status", cwd=rsb.root).splitlines())
warned3 = sum("stage_exact failed" in r.getMessage() for r in records)

print(
    f"[1] double over 6 orders with one missing path: {sorted(outcomes)} | "
    f"[2] materialized={payload.materialized} output_allowlisted={'.chain/output.html' in payload.allowlist} "
    f"staged={staged} stage_exact_warnings={warned} | "
    f"[3] real sandbox, greeting.md tracked earlier: output_allowlisted={'.chain/greeting.md' in p3.allowlist} "
    f"index={status3} stage_exact_warnings={warned3}"
)
