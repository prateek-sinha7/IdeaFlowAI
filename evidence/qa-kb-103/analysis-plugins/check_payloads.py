"""QA-KB-103 analysis probe, part 2 (read-only, no DB, no write).

Feeds each canvas payload (qa103_serializer_out.json, produced by running the REAL frontend serializer)
to the shared backend check, compile_override_steps() at trust="user", and reports
 (a) the verdict (201-equivalent PASS or the 422 reason), and
 (b) what a PASSING payload silently drops or changes against the built-in's own file steps.
"""
import json
import sys
from pathlib import Path

from agents.execution_engine.engine import _CAPABILITY_REGISTRY
from agents.execution_engine.overrides import compile_override_steps
from agents.workflows.compiler import CompilerError
from agents.workflows.manifest import ManifestValidationError

data = json.load(open(sys.argv[1]))

SCENARIOS = [
    "wizard_plan_seeded",
    "library_seeded",
    "ideainput_manifest_agents",
    "plan_seeded_with_manifest_selections",
]


def ident(step):
    if step.get("agent") == "custom-agent":
        return f"custom-agent:{step.get('instance_id')}"
    return step.get("agent")


def flat(steps):
    for s in steps:
        yield s
        sub = s.get("subagents")
        if isinstance(sub, dict):
            yield from flat(sub.get("steps") or [])


def diff(file_steps, posted_steps):
    fmap = {ident(s): s for s in flat(file_steps)}
    pmap = {ident(s): s for s in flat(posted_steps)}
    lost, changed = [], []
    for k, fs in fmap.items():
        ps = pmap.get(k)
        if ps is None:
            lost.append(f"STEP {k} missing")
            continue
        for key, val in fs.items():
            if key in ("gates", "depends_on", "subagents"):
                continue
            if key not in ps:
                lost.append(f"{k}.{key}={json.dumps(val)[:60]}")
            elif ps[key] != val:
                changed.append(f"{k}.{key}: {json.dumps(val)[:50]} -> {json.dumps(ps[key])[:50]}")
    return lost, changed


for wid, rec in data.items():
    print(f"== {wid}  (library roster ids: {len(rec['library_roster_ids'])}, file steps: {len(rec['file_steps'])})")
    for sc in SCENARIOS:
        man = rec.get(sc)
        if not man:
            print(f"   {sc:40s} (no roster)")
            continue
        steps = man["steps"]
        try:
            compile_override_steps(wid, steps, _CAPABILITY_REGISTRY)
            verdict = "PASS (201-equivalent)"
            lost, changed = diff(rec["file_steps"], steps)
            tail = ""
            if lost or changed:
                tail = f"  DROPPED={lost[:6]}{'...' if len(lost) > 6 else ''}  CHANGED={changed[:4]}{'...' if len(changed) > 4 else ''}"
        except (CompilerError, ManifestValidationError) as e:
            verdict = f"422: {str(e)[:150]}"
            tail = ""
        print(f"   {sc:40s} {verdict}{tail}")
