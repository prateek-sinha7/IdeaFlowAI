"""READ-ONLY PROBE (not a product test), QA-KB-126 analysis.

Regression surface of a fix that compiles a NON-Composer saved row at trust="user": what would stop
compiling if a basic/pro/hexaware owner held a plain row whose manifest is a verbatim copy of a pipeline
that tier is ENTITLED to run (the shape sync-from-file stores: `_load_file_manifest_dict`).

For every pipeline some tier may run, with a workflow.yaml on disk:
  db   : the compile every plain row gets today (launch Case 3 / trigger / save).
  user : compile_with_baseline(..., trust="user", overrides=<that pipeline>) = the best case a fix could offer
         (the row keeps compaction / post_step its own built-in declares on the same step, ISS-1118).
Prints which tiers hold each pipeline and the first refusal. No server, no DB, no model, no run.
"""
import sys

from agents.capabilities.registry import discover
from agents.execution_engine.engine import _CAPABILITY_REGISTRY
from agents.execution_engine.overrides import compile_with_baseline
from agents.workflows.compiler import CompilerError
from agents.workflows.manifest import ManifestValidationError, build_manifest_from_dict
from app.api.user_workflows import _load_file_manifest_dict
from app.core.entitlements import TIER_PIPELINES

discover()
entitled: dict[str, list[str]] = {}
for tier, pipelines in TIER_PIPELINES.items():
    for p in pipelines:
        entitled.setdefault(p, []).append(tier)

rows = []
for p in sorted(entitled):
    try:
        raw = _load_file_manifest_dict(p)
    except Exception as exc:  # no workflow.yaml (e.g. the "migration" UI grouping)
        rows.append((p, entitled[p], "no-file", f"{type(exc).__name__}"))
        continue
    res = {}
    for label, trust, ov in (("db", "db", None), ("user", "user", p)):
        try:
            compile_with_baseline(build_manifest_from_dict(dict(raw), f"probe:{p}"), _CAPABILITY_REGISTRY, trust=trust, overrides=ov)
            res[label] = "ok"
        except (CompilerError, ManifestValidationError) as exc:
            res[label] = f"{type(exc).__name__}: {str(exc)[:120]}"
    rows.append((p, entitled[p], res["db"], res["user"]))

ok = [r for r in rows if r[2] == "ok" and r[3] == "ok"]
regress = [r for r in rows if r[2] == "ok" and r[3] != "ok"]
nofile = [r for r in rows if r[2] == "no-file"]
other = [r for r in rows if r not in ok and r not in regress and r not in nofile]
print(f"pipelines some tier may run: {len(rows)}; compile at db AND at user-with-own-baseline: {len(ok)}; "
      f"compile at db but REFUSED at user: {len(regress)}; no workflow.yaml: {len(nofile)}; neither: {len(other)}")
print()
print("REFUSED at user (would stop launching as a plain row of a non-Composer owner):")
for p, tiers, _db, user in regress:
    print(f"  {p:<34} tiers={sorted(tiers)}  {user}")
print()
print("compile at both:")
print("  " + ", ".join(f"{r[0]}[{','.join(sorted(r[1]))}]" for r in ok))
if nofile or other:
    print()
    print("no file / other:", [(r[0], r[2][:60], r[3][:60]) for r in nofile + other])
sys.exit(0)
