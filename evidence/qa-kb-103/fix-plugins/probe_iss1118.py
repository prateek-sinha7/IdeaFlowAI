"""Probe for ISS-1118: re-attach + the card's refusal controls. Not a test file."""
import copy
from pathlib import Path

from agents.execution_engine.engine import _CAPABILITY_REGISTRY as R, compile_for_run
from agents.execution_engine.overrides import compile_override_steps, merge_override_steps
from agents.workflows.compiler import CompilerError
from agents.workflows.manifest import load_manifest

WF = Path("agents/workflows")


def steps(wid):
    return copy.deepcopy(list(load_manifest(wid, WF).steps))


def by_id(c):
    return {s.agent_id: s for s in c.steps}


def refused(label, wid, st):
    try:
        compile_override_steps(wid, st, R)
    except CompilerError as e:
        print(f"REFUSED  {label}: {str(e)[:110]}")
        return
    print(f"ADMITTED {label}  <-- WRONG")


# 1. re-attached values equal the file plan's
for wid in ["app_builder", "prototype", "prototype_feature_revision", "prototype_large_revision", "prototype_revision"]:
    st = steps(wid)
    before = copy.deepcopy(st)
    got = by_id(compile_override_steps(wid, st, R))
    base = by_id(compile_for_run(wid))
    diffs = [(a, k) for a, s in base.items() for k in ("compaction", "post_step") if getattr(s, k) != getattr(got[a], k)]
    print(f"{wid}: refs equal file plan={not diffs} caller-steps-untouched={st == before}",
          {a: (s.compaction, s.post_step) for a, s in got.items() if s.compaction or s.post_step})

# 2. controls that must keep refusing
st = steps("app_builder")
ids = [s["agent"] for s in st]
for s in st:
    if s.get("post_step"):
        s.pop("post_step")
st[ids.index("app-code-generator")]["post_step"] = "api_prefix_audit"
refused("post_step moved to app-code-generator", "app_builder", st)

st = steps("app_builder")
for s in st:
    if s.get("post_step"):
        s["post_step"] = "revision_validation"
refused("post_step value swapped", "app_builder", st)

st = steps("prototype"); st[0]["gates"] = ["security"]
refused("gates: [security] added", "prototype", st)

st = steps("prototype"); st[0]["tools"] = {"exec": True}
refused("tools.exec granted", "prototype", st)

st = steps("prototype"); st[0]["tools"] = {"spawn_subagents": True}
refused("tools.spawn_subagents granted", "prototype", st)

for wid in ["sample_fanout", "sample_subagents_parallel", "sample_wave"]:
    refused(f"{wid} own steps (spawn trio)", wid, steps(wid))

refused("prototype steps under override target ppt", "ppt", steps("prototype"))

# 3. merge applies, and the cached plan is not mutated
plan = compile_for_run("prototype")
snap = [(s.agent_id, s.compaction, s.post_step) for s in plan.steps]
merged = merge_override_steps(plan, steps("prototype"), R)
print("merge applied:", merged is not plan,
      "| prototype-build compaction:", by_id(merged)["prototype-build"].compaction,
      "| cache untouched:", snap == [(s.agent_id, s.compaction, s.post_step) for s in compile_for_run("prototype").steps])
