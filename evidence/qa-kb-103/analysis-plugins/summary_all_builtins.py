"""Summary over ALL built-ins: per roster seed, verdict at trust=user and the count of file-step keys a PASSING payload drops or alters."""
import json, sys
from agents.execution_engine.engine import _CAPABILITY_REGISTRY
from agents.execution_engine.overrides import compile_override_steps
from agents.workflows.compiler import CompilerError
from agents.workflows.manifest import ManifestValidationError

data = json.load(open(sys.argv[1]))

def ident(s):
    return f"custom-agent:{s.get('instance_id')}" if s.get("agent") == "custom-agent" else s.get("agent")

def flat(steps):
    for s in steps:
        yield s
        sub = s.get("subagents")
        if isinstance(sub, dict):
            yield from flat(sub.get("steps") or [])

def lost_changed(file_steps, posted):
    fmap = {ident(s): s for s in flat(file_steps)}
    pmap = {ident(s): s for s in flat(posted)}
    lost, changed = [], []
    for k, fs in fmap.items():
        ps = pmap.get(k)
        if ps is None:
            lost.append(f"{k}:<step>")
            continue
        for key, val in fs.items():
            if key in ("gates", "depends_on", "subagents", "tools"):
                continue
            if key not in ps:
                lost.append(f"{k}.{key}")
            elif ps[key] != val:
                changed.append(f"{k}.{key}")
    return lost, changed

SEEDS = ["plan_seeded_with_manifest_selections", "library_seeded", "ideainput_manifest_agents"]
rows = []
for wid, rec in data.items():
    row = [wid]
    for sc in SEEDS:
        man = rec.get(sc)
        if not man:
            row.append("n/a (no library roster)")
            continue
        try:
            compile_override_steps(wid, man["steps"], _CAPABILITY_REGISTRY)
            lost, changed = lost_changed(rec["file_steps"], man["steps"])
            row.append("201" + (f" LOSES {len(lost)} key(s), ALTERS {len(changed)}: {(lost+changed)[:4]}" if (lost or changed) else " faithful"))
        except (CompilerError, ManifestValidationError) as e:
            row.append("422")
    rows.append(row)
w = max(len(r[0]) for r in rows)
print(f"{'built-in':{w}}  | plan-seeded (agentsFromManifest, declared gates kept) | library-seeded | IdeaInputPage manifestAgents")
for r in rows:
    print(f"{r[0]:{w}}  | {r[1]} | {r[2]} | {r[3]}")
