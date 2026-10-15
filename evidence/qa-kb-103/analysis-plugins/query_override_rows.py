"""Read-only (QA-KB-103 analysis): every override row in the dev DB, the step KEYS it stores,
and whether each row's steps pass the shared trust="user" check. No write, no secrets printed."""
import json
from sqlalchemy import create_engine, text

url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
eng = create_engine(url)
SQL = (
    "SELECT id, overrides_pipeline_type, override_enabled, created_at, updated_at, manifest_json "
    "FROM workflows WHERE overrides_pipeline_type IS NOT NULL "
    "ORDER BY overrides_pipeline_type, updated_at"
)
print("query:", SQL.replace("manifest_json", "manifest_json (step KEYS printed, not values)"))
with eng.connect() as c:
    c.execute(text("SET TRANSACTION READ ONLY"))
    rows = c.execute(text(SQL)).fetchall()

from agents.execution_engine.engine import _CAPABILITY_REGISTRY
from agents.execution_engine.overrides import compile_override_steps
from agents.workflows.compiler import CompilerError
from agents.workflows.manifest import ManifestValidationError

print(f"{len(rows)} override row(s)")
for r in rows:
    mj = r.manifest_json
    if isinstance(mj, str):
        mj = json.loads(mj)
    steps = (mj or {}).get("steps") if isinstance(mj, dict) else None
    print(f"- id={r.id} overrides={r.overrides_pipeline_type} enabled={r.override_enabled} updated={r.updated_at}")
    if not steps:
        print("    no steps")
        continue
    union = set()
    for s in steps:
        union |= set(s.keys())
    print(f"    steps={len(steps)} union_of_step_keys={sorted(union)}")
    for s in steps:
        print(f"      agent={s.get('agent')} instance={s.get('instance_id')} keys={sorted(s.keys())}")
    try:
        compile_override_steps(r.overrides_pipeline_type, steps, _CAPABILITY_REGISTRY)
        print("    trust=user check: PASSES")
    except (ManifestValidationError, CompilerError) as e:
        print(f"    trust=user check: REFUSED {type(e).__name__}: {str(e)[:160]}")
