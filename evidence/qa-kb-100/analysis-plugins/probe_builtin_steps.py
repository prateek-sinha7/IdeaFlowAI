"""READ-ONLY probe (QA-KB-100 analysis): regression surface of compiling override steps at
trust="user". For every built-in workflow, take its OWN manifest steps verbatim (what a client
posting 'the built-in's steps as my override' or sync-from-file would store) and compile them in
the override isolation recipe at trust=db and trust=user. A row that is accepted at db and refused
at user is a built-in whose own steps would stop applying as an override under option A."""
from pathlib import Path
from agents.execution_engine.engine import _CAPABILITY_REGISTRY as R
from agents.execution_engine.overrides import _PLACEHOLDER_DELIVERABLE, _PLACEHOLDER_CLARIFY
from agents.workflows.compiler import CompilerError, WorkflowCompiler
from agents.workflows.manifest import ManifestValidationError, build_manifest_from_dict, load_manifest
from agents.loader import SUPPORTED_PIPELINE_TYPES

WF_DIR = Path("agents/workflows")
ids = sorted(p.parent.name for p in WF_DIR.glob("*/workflow.yaml"))


def compile_at(wid, steps, trust):
    raw = {"id": wid, "steps": steps, "deliverable": _PLACEHOLDER_DELIVERABLE,
           "planner": "skip", "clarify": _PLACEHOLDER_CLARIFY}
    try:
        WorkflowCompiler().compile(build_manifest_from_dict(raw, f"override:{wid}"), R, trust=trust)
        return None
    except (ManifestValidationError, CompilerError) as exc:
        return f"{type(exc).__name__}: {exc}"


rows = []
for wid in ids:
    try:
        m = load_manifest(wid, WF_DIR)
    except Exception as exc:  # noqa: BLE001
        rows.append((wid, "LOAD-ERR", str(exc)[:120], ""))
        continue
    steps = [dict(s) for s in (m.steps or [])]
    db = compile_at(wid, steps, "db")
    user = compile_at(wid, steps, "user")
    rows.append((wid, "ok" if db is None else "db-err", db, user))

print(f"{len(ids)} built-in workflow.yaml files; SUPPORTED_PIPELINE_TYPES includes them? "
      f"{sum(1 for i in ids if i in SUPPORTED_PIPELINE_TYPES)}/{len(ids)}")
print()
print("Built-ins whose OWN steps compile at db but are REFUSED at user (would stop applying as an override under option A):")
n = 0
for wid, dbs, dberr, usererr in rows:
    if dbs == "ok" and usererr:
        n += 1
        print(f"  {wid:32s} {usererr[:210]}")
print(f"  -> {n} workflow(s)")
print()
print("Built-ins whose own steps compile at BOTH levels (override of these keeps working under option A):")
print("  " + ", ".join(w for w, dbs, dberr, usererr in rows if dbs == "ok" and not usererr))
print()
print("Built-ins whose own steps do not compile in ISOLATION at either level (cross-step refs etc.; not trust related):")
for wid, dbs, dberr, usererr in rows:
    if dbs != "ok":
        print(f"  {wid:32s} {dbs}: {(dberr or '')[:150]}")
