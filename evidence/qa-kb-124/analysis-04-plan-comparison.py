"""QA-KB-124 analysis 04: compile the built-in ex_A1_loop and merge the admin's saved override onto it
(the exact call run_commands.py:3676 makes at launch), then print each step's effective grants and data edges.
run: cd backend && PYTHONPATH=. <venv python> ../evidence/qa-kb-124/analysis-04-plan-comparison.py"""
import json, pathlib, warnings
warnings.filterwarnings("ignore")
HERE = pathlib.Path(__file__).resolve().parent
steps = json.loads((HERE / "analysis-01-override-row-bdf009f2.json").read_text())["manifest_json"]["steps"]
from agents.execution_engine.engine import compile_for_run, _CAPABILITY_REGISTRY
from agents.execution_engine.overrides import merge_override_steps
base = compile_for_run("ex_A1_loop")
merged = merge_override_steps(base, steps, _CAPABILITY_REGISTRY)
print("merge applied (returned a new plan, not the file plan):", merged is not base)
def show(tag, plan):
    print("==", tag)
    for s in plan.steps:
        t = s.tools
        print(f"  {s.agent_id:22s} read={t.read_files!s:5} write={t.write_files!s:5} exec={t.exec!s:5} produces={s.produces} consumes={s.consumes} depends_on={s.depends_on} gates={s.gates}")
show("BUILT-IN (file manifest, compile_for_run('ex_A1_loop'))", base)
show("MERGED (admin's saved override bdf009f2, merge_override_steps)", merged)
