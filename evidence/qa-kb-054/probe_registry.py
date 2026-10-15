"""QA-KB-054 / ISS-687 evidence. Plain script, read-only: no server, no DB, no run.
Run from the repo root:  backend/.venv/bin/python evidence/qa-kb-054/probe_registry.py   (cwd = backend/ is set below)
Shows, for every file workflow with a custom-agent step: its compiled step ids, its registry roster, and
what allowed_custom_agent_ids() returns for it (the allow-list launch_run and create_user_workflow check)."""
import os, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[2] / "backend"
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from agents.execution_engine.engine import compile_for_run  # noqa: E402
from agents.registry import (  # noqa: E402
    PIPELINE_AGENTS,
    _own_manifest_step_agents,
    allowed_custom_agent_ids,
)
from agents.workflows.artifacts import CUSTOM_AGENT_PREFIX  # noqa: E402
from agents.loader import load_agent_spec  # noqa: E402

wfs = [d.name for d in sorted(pathlib.Path("agents/workflows").iterdir()) if (d / "workflow.yaml").exists()]
cust = [w for w in wfs if re.search(r"agent:\s*custom-agent", (pathlib.Path("agents/workflows") / w / "workflow.yaml").read_text())]
print(f"workflow.yaml files: {len(wfs)}   with a custom-agent step: {len(cust)}\n")
print(f"{'workflow':32s} steps custom reg  PIPELINE_AGENTS  allowed_custom_agent_ids  _own_manifest_step_agents")
for w in cust:
    ids = [s.agent_id for s in compile_for_run(w).steps]
    c = [i for i in ids if i.startswith(CUSTOM_AGENT_PREFIX)]
    print(f"{w:32s} {len(ids):5d} {len(c):6d} {len(ids)-len(c):3d}  {len(PIPELINE_AGENTS.get(w) or []):14d}  {len(allowed_custom_agent_ids(w)):24d}  {sorted(_own_manifest_step_agents(w))}")
print("\nprototype_v2 compiled ids:", [s.agent_id for s in compile_for_run("prototype_v2").steps])
try:
    print("load_agent_spec('custom-agent:fi-planner') ->", load_agent_spec("custom-agent:fi-planner").id)
except Exception as exc:  # noqa: BLE001
    print("load_agent_spec raised", type(exc).__name__, exc)
