"""Read-only: saved rows whose manifest routes trigger a workflow, and run rows' persisted _trust."""
import json
from sqlalchemy import create_engine, text

url = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("DATABASE_URL=")][0]
eng = create_engine(url)
Q1 = ("SELECT w.id, w.base_pipeline_type, w.overrides_pipeline_type, u.tier, w.manifest_json::text AS mj "
      "FROM workflows w LEFT JOIN users u ON u.id = w.user_id "
      "WHERE w.source = 'user' AND w.manifest_json::text LIKE '%\"trigger\": \"workflow\"%'")
Q2 = ("SELECT manifest_json->>'_trust' AS trust, count(*) AS n FROM workflow_runs "
      "WHERE manifest_json IS NOT NULL GROUP BY 1 ORDER BY 1")
print("Q1:", Q1)
print("Q2:", Q2)
with eng.connect() as c:
    c.execute(text("SET TRANSACTION READ ONLY"))
    rows = c.execute(text(Q1)).mappings().all()
    print(f"Q1 -> {len(rows)} row(s)")
    for r in rows:
        mj = json.loads(r["mj"])
        targets = []
        def walk(n):
            if not isinstance(n, dict):
                return
            route = n.get("route")
            outs = route.get("outcomes") if isinstance(route, dict) else None
            for o in (outs.values() if isinstance(outs, dict) else []):
                if isinstance(o, dict) and o.get("trigger") == "workflow":
                    targets.append(o.get("target"))
            for s in n.get("steps") or []:
                walk(s)
            walk(n.get("subagents"))
        walk(mj)
        print(f"    id={r['id']} base={r['base_pipeline_type']} override={r['overrides_pipeline_type']} owner_tier={r['tier']} trigger_targets={targets}")
    print("Q2 ->", [dict(r) for r in c.execute(text(Q2)).mappings().all()])
