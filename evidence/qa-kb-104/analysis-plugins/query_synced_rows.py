"""Read-only: do any stored user rows already carry a FILE workflow's manifest (the signature sync-from-file leaves)?

A file manifest has a top-level `id` (plus deliverable/planner/clarify); a Composer or canvas save is `{"steps": [...]}` and
launch synthesizes `id` (run_commands.py `raw_manifest.setdefault("id", ...)`). So `manifest_json ? 'id'` marks a row that
was filled from a file (sync-from-file, or a hand-built dict). Prints counts and, per such row, the owner's tier PROJECTION
(users.tier, advisory) against can_run_pipeline(tier, manifest.id). No manifest content is printed.
One SELECT per query, SET TRANSACTION READ ONLY, no write.
"""
import json
from sqlalchemy import create_engine, text

url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
eng = create_engine(url)
Q0 = "SELECT (SELECT count(*) FROM workflows) AS workflows_rows, (SELECT count(*) FROM users) AS users_rows"
Q1 = "SELECT source, count(*) AS n, count(manifest_json) AS with_manifest FROM workflows GROUP BY source ORDER BY source"
Q2 = (
    "SELECT w.id, w.user_id, u.tier, w.base_pipeline_type, w.overrides_pipeline_type, w.manifest_json "
    "FROM workflows w LEFT JOIN users u ON u.id = w.user_id "
    "WHERE w.source = 'user' AND w.manifest_json IS NOT NULL AND (w.manifest_json::jsonb) ? 'id' ORDER BY w.created_at"
)
print("Q0:", Q0)
print("Q1:", Q1)
print("Q2:", Q2.replace("w.manifest_json,", "w.manifest_json (only its top-level id is used below),", 1))
with eng.connect() as c:
    c.execute(text("SET TRANSACTION READ ONLY"))
    q0 = c.execute(text(Q0)).fetchone()
    q1 = c.execute(text(Q1)).fetchall()
    q2 = c.execute(text(Q2)).fetchall()
print(f"Q0: workflows table has {q0.workflows_rows} row(s); users table has {q0.users_rows} row(s)")
for r in q1:
    print(f"  workflows.source={r.source!r}: {r.n} row(s), {r.with_manifest} with manifest_json")
from app.core.entitlements import can_run_pipeline
print(f"Q2: {len(q2)} user row(s) whose manifest_json has a top-level 'id'")
for r in q2:
    mj = r.manifest_json if isinstance(r.manifest_json, dict) else json.loads(r.manifest_json)
    mid = mj.get("id")
    tier = r.tier or "basic"
    ok = can_run_pipeline(tier, mid)[0] if isinstance(mid, str) else None
    print(f"  row={r.id[:8]} owner_tier={tier} base={r.base_pipeline_type} overrides={r.overrides_pipeline_type} manifest.id={mid!r} owner_may_run_it={ok}")
