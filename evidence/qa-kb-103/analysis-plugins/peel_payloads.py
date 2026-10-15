"""QA-KB-103 analysis probe, part 3 (read-only): peel EVERY refusal off the plan-seeded canvas payload
(the exact steps the real serializer emits for an UNCHANGED save), and show that each peeled capability
is inherited verbatim from the built-in's own file step -- i.e. a baseline-aware check would admit
exactly this set and nothing else.
"""
import copy
import json
import re
import sys

from agents.execution_engine.engine import _CAPABILITY_REGISTRY
from agents.execution_engine.overrides import compile_override_steps
from agents.workflows.compiler import CompilerError
from agents.workflows.manifest import ManifestValidationError

data = json.load(open(sys.argv[1]))
TARGETS = [
    "app_builder", "prototype", "prototype_feature_revision", "prototype_large_revision",
    "prototype_revision", "sample_fanout", "sample_subagents_parallel", "sample_wave",
]
CAP_RE = re.compile(r"capability \('([a-z_]+)', '([^']+)'\) is not user-allowed in (?:step )?'([^']+)'")
GRANT_RE = re.compile(r"step grant of \[(.*?)\] is not permitted for 'user'-trust manifests in step '([^']+)'")


def ident(s):
    return f"custom-agent:{s.get('instance_id')}" if s.get("agent") == "custom-agent" else s.get("agent")


def flat(steps):
    for s in steps:
        yield s
        sub = s.get("subagents")
        if isinstance(sub, dict):
            yield from flat(sub.get("steps") or [])


def find(steps, where):
    for s in flat(steps):
        if s.get("agent") == where or ident(s) == where or s.get("instance_id") == where:
            return s
    return None


for wid in TARGETS:
    rec = data[wid]
    file_steps = rec["file_steps"]
    steps = copy.deepcopy(rec["wizard_plan_seeded"]["steps"])
    peeled = []
    for _ in range(20):
        try:
            compile_override_steps(wid, steps, _CAPABILITY_REGISTRY)
            break
        except (CompilerError, ManifestValidationError) as e:
            msg = str(e)
            m = CAP_RE.search(msg)
            if m:
                kind, name, where = m.groups()
                key = {"post_step": "post_step", "compaction": "compaction"}.get(kind, kind)
                st = find(steps, where)
                fs = find(file_steps, where)
                inherited = bool(fs and fs.get(key) == name)
                st.pop(key, None)
                peeled.append((kind, name, where, "INHERITED (== file step)" if inherited else "NOT in file step"))
                continue
            m = GRANT_RE.search(msg)
            if m:
                grants, where = m.groups()
                st = find(steps, where)
                fs = find(file_steps, where)
                for g in [x.strip().strip("'") for x in grants.split(",")]:
                    inherited = bool(fs and (fs.get("tools") or {}).get(g))
                    (st.get("tools") or {}).pop(g, None)
                    peeled.append(("tool-grant", g, where, "INHERITED (== file step)" if inherited else "NOT in file step"))
                continue
            peeled.append(("UNPEELABLE", msg[:160], "", ""))
            break
    print(f"{wid}: unchanged canvas payload is refused for {len(peeled)} capability reference(s):")
    for p in peeled:
        print(f"    {p[0]}:{p[1]} @ step '{p[2]}'  -> {p[3]}")
    try:
        compile_override_steps(wid, steps, _CAPABILITY_REGISTRY)
        print("    after removing exactly those references the payload passes the user-trust compile")
    except (CompilerError, ManifestValidationError) as e:
        print("    STILL refused:", str(e)[:160])
