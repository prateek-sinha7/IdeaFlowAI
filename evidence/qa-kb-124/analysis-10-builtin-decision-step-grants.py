"""QA-KB-124 re-analysis 10: which SHIPPED workflows have a decision step, and does any of them hold a write grant?

Answers the blast-radius question 'who does the fix touch': a step is hurt by the delivery block only if it is BOTH
a decision source (declares produces: [route_decision]) AND write-granted. Compiles every shipped workflow with the
real compiler (offline) and lists each such step with its effective grants.

    cd backend && PYTHONPATH=. .venv/bin/python ../evidence/qa-kb-124/analysis-10-builtin-decision-step-grants.py 2>/dev/null
"""
import os, sys, warnings
from pathlib import Path

warnings.filterwarnings("ignore")
os.environ.setdefault("ENV", "development")
sys.path.insert(0, ".")
from agents.execution_engine.engine import compile_for_run  # noqa: E402

rows = []
for d in sorted(p for p in Path("agents/workflows").iterdir() if (p / "workflow.yaml").exists()):
    try:
        plan = compile_for_run(d.name)
    except Exception as e:  # a fixture that does not compile on its own is reported, not hidden
        rows.append((d.name, "COMPILE-ERR", type(e).__name__, ""))
        continue
    for s in plan.steps:
        if "route_decision" in (getattr(s, "produces", None) or []):
            t = s.tools
            rows.append((d.name, s.agent_id, f"read={t.read_files} write={t.write_files} exec={t.exec}", f"gates={list(s.gates)}"))
for r in rows:
    print(*r, sep=" | ")
hurt = [r for r in rows if r[1] != "COMPILE-ERR" and "write=True" in r[2]]
print(f"decision steps: {len([r for r in rows if r[1] != 'COMPILE-ERR'])}; with a write grant (hurt by the delivery block): {len(hurt)}")
