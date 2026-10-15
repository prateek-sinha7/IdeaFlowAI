"""Read-only (SET TRANSACTION READ ONLY, SELECT only): saved user rows by shape and owner tier.

The population a fix that keys trust or entitlement on base_pipeline_type would touch:
plain (non-override) manifest-backed rows, grouped by base type and by the owner's advisory users.tier.
"""
from sqlalchemy import create_engine, text

url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
eng = create_engine(url)
Q0 = "SELECT (SELECT count(*) FROM workflows) AS workflows_rows, (SELECT count(*) FROM users) AS users_rows"
Q1 = (
    "SELECT w.source, (w.manifest_json IS NOT NULL) AS has_manifest, "
    "(w.overrides_pipeline_type IS NOT NULL) AS is_override, w.base_pipeline_type, u.tier, count(*) AS n "
    "FROM workflows w LEFT JOIN users u ON u.id = w.user_id "
    "GROUP BY 1, 2, 3, 4, 5 ORDER BY 1, 2, 3, 4, 5"
)
Q2 = (
    "SELECT w.id, w.base_pipeline_type, u.tier, w.manifest_json::text AS mj FROM workflows w "
    "LEFT JOIN users u ON u.id = w.user_id WHERE w.source = 'user' AND w.manifest_json IS NOT NULL "
    "AND w.overrides_pipeline_type IS NULL ORDER BY w.created_at"
)
print("Q0:", Q0)
print("Q1:", Q1)
print("Q2:", Q2.replace("w.manifest_json::text AS mj", "w.manifest_json::text AS mj (privilege scan below, not printed)"))
with eng.connect() as c:
    c.execute(text("SET TRANSACTION READ ONLY"))
    print("Q0 ->", dict(c.execute(text(Q0)).mappings().first()))
    rows = c.execute(text(Q1)).mappings().all()
    print(f"Q1 -> {len(rows)} group(s)")
    for r in rows:
        print("   ", dict(r))
    plain = c.execute(text(Q2)).mappings().all()
import json

print(f"Q2 -> {len(plain)} plain manifest-backed row(s)")
for r in plain:
    mj = json.loads(r["mj"])
    steps = mj.get("steps") or []
    flat = []

    def walk(ss):
        for s in ss:
            if isinstance(s, dict):
                flat.append(s)
                sub = s.get("subagents")
                if isinstance(sub, dict):
                    walk(sub.get("steps") or [])

    walk(steps)
    exec_n = sum(1 for s in flat if (s.get("tools") or {}).get("exec"))
    spawn_n = sum(1 for s in flat if (s.get("tools") or {}).get("spawn_subagents"))
    gates = sorted({g for s in flat for g in (s.get("gates") or [])})
    print(
        f"    id={r['id']} base={r['base_pipeline_type']} owner_tier={r['tier']} steps={len(flat)} "
        f"exec_steps={exec_n} spawn_steps={spawn_n} gates={gates}"
    )
