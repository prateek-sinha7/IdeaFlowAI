"""QA-KB-103 analysis probe (read-only, no DB, no write): for each built-in whose OWN steps are
refused at trust="user", peel refusals one at a time and list EVERY engineer-only key the
override would carry, plus whether the user-trust compile then passes.

Mirrors evidence/qa-kb-100/analysis-plugins/probe_builtin_steps.py: it loads each built-in's raw
manifest steps (what GET /api/workflows/{id} serves as manifest_steps) and calls the shared
compile_override_steps().
"""
import copy
import re
import sys

from agents.execution_engine.engine import _CAPABILITY_REGISTRY
from agents.execution_engine.overrides import compile_override_steps
from agents.workflows.compiler import CompilerError
from agents.workflows.manifest import ManifestValidationError, load_manifest
from pathlib import Path

WF_DIR = Path("agents/workflows")
TARGETS = [
    "app_builder", "prototype", "prototype_feature_revision", "prototype_large_revision",
    "prototype_revision", "sample_fanout", "sample_subagents_parallel", "sample_wave",
]

CAP_RE = re.compile(r"capability \('([a-z_]+)', '([^']+)'\) is not user-allowed in (?:step )?'([^']+)'")
GRANT_RE = re.compile(r"step grant of \[(.*?)\] is not permitted for 'user'-trust manifests in step '([^']+)'")


def walk(steps):
    for s in steps:
        yield s
        sub = s.get("subagents")
        if isinstance(sub, dict):
            yield from walk(sub.get("steps") or [])


def find_step(steps, where):
    for s in walk(steps):
        if s.get("agent") == where or s.get("instance_id") == where or f"custom-agent:{s.get('instance_id')}" == where:
            return s
    return None


def peel(steps, msg):
    m = CAP_RE.search(msg)
    if m:
        kind, name, where = m.groups()
        st = find_step(steps, where)
        if st is None:
            return None
        key = {"post_step": "post_step", "compaction": "compaction", "gate": "gates", "validator": "validators"}.get(kind, kind)
        if key in ("gates", "validators"):
            st[key] = [x for x in st.get(key, []) if x != name]
        else:
            st.pop(key, None)
        return f"{kind}:{name} @ {where}"
    m = GRANT_RE.search(msg)
    if m:
        grants, where = m.groups()
        st = find_step(steps, where)
        if st is None:
            return None
        for g in [x.strip().strip("'") for x in grants.split(",")]:
            (st.get("tools") or {}).pop(g, None)
        return f"tool-grant:{grants} @ {where}"
    return None


for wid in TARGETS:
    manifest = load_manifest(wid, WF_DIR)
    steps = copy.deepcopy(list(manifest.steps))
    print(f"== {wid}: {len(steps)} file step(s)")
    peeled = []
    for _ in range(25):
        try:
            compile_override_steps(wid, steps, _CAPABILITY_REGISTRY)
            print(f"   passes at trust=user after stripping {len(peeled)} key(s): {peeled}")
            break
        except (CompilerError, ManifestValidationError) as e:
            msg = str(e)
            what = peel(steps, msg)
            if what is None:
                print(f"   UNPEELABLE refusal after {peeled}: {type(e).__name__}: {msg[:220]}")
                break
            peeled.append(what)
    else:
        print("   did not converge", peeled)
