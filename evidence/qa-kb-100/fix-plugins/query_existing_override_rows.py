"""Read-only: every override row in the dev DB, and whether its steps pass the new check."""
import os, json
from sqlalchemy import create_engine, text
url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
eng = create_engine(url)
SQL = ("SELECT id, user_id, overrides_pipeline_type, override_enabled, manifest_json "
       "FROM workflows WHERE overrides_pipeline_type IS NOT NULL ORDER BY overrides_pipeline_type, id")
print("query:", SQL.replace("manifest_json", "manifest_json (steps compiled below, not printed)"))
with eng.connect() as c:
    c.execute(text("SET TRANSACTION READ ONLY"))
    rows = c.execute(text(SQL)).fetchall()
from agents.execution_engine.engine import _CAPABILITY_REGISTRY
from agents.execution_engine.overrides import compile_override_steps
from agents.workflows.compiler import CompilerError
from agents.workflows.manifest import ManifestValidationError
print(f"{len(rows)} override row(s)")
for r in rows:
    mj = r.manifest_json if isinstance(r.manifest_json, dict) else (json.loads(r.manifest_json) if r.manifest_json else None)
    steps = (mj or {}).get("steps") if isinstance(mj, dict) else None
    if not steps:
        verdict = "no steps (never merged)"
    else:
        try:
            compile_override_steps(r.overrides_pipeline_type, steps, _CAPABILITY_REGISTRY)
            verdict = "PASSES trust=user (still applies)"
        except (ManifestValidationError, CompilerError) as e:
            verdict = f"REFUSED at trust=user -> file plan: {type(e).__name__}: {str(e)[:110]}"
    print(f"  id={r.id} user={str(r.user_id)[:8]}... overrides={r.overrides_pipeline_type} enabled={r.override_enabled} steps={len(steps or [])} :: {verdict}")
